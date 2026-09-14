"""
Servidor FastAPI para o Yoga Studio App (PWA com visual de WhatsApp).
Fornece rotas da API REST, serviços de IA, cobranças no WhatsApp e arquivos estáticos.
"""
import os
import sys
import io
import datetime
import asyncio
import re
import time
import hmac
import hashlib
import base64
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Response, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image
import urllib.parse

import backend.database as db
import backend.ai_service as ai
import backend.pdf_service as pdf_service
import backend.contract_service as contract_service
import backend.autentique_service as autentique_service

app = FastAPI(title="Yoga Studio - WhatsApp AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    # Evitar cache de HTML/CSS/JS e rotas de API para sincronização 100% em tempo real entre celulares
    if any(request.url.path.endswith(ext) for ext in [".html", ".css", ".js", "/"]) or request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# --- Monitoramento e Observabilidade do Servidor (Render vs. Gemini) ---
SERVER_START_TIME = datetime.datetime.now(datetime.timezone.utc)
LAST_KEEPALIVE_PING = datetime.datetime.now(datetime.timezone.utc)
LAST_KEEPALIVE_DB_LOG = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)

def obter_info_servidor_uptime() -> Dict[str, Any]:
    """Calcula uptime e detecta se o servidor está em cold start (< 3 minutos desde inicialização)."""
    agora = datetime.datetime.now(datetime.timezone.utc)
    segundos = max(0, int((agora - SERVER_START_TIME).total_seconds()))
    cold_start = segundos < 180  # Menos de 3 minutos é cold start recente no Render
    
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segs = segundos % 60
    
    if horas > 0:
        uptime_fmt = f"{horas}h {minutos}m"
    elif minutos > 0:
        uptime_fmt = f"{minutos}m {segs}s"
    else:
        uptime_fmt = f"{segs}s"
        
    return {
        "uptime_segundos": segundos,
        "uptime_formatado": uptime_fmt,
        "cold_start": cold_start,
        "status_servidor": "iniciando" if cold_start else "ok",
        "started_at": SERVER_START_TIME.isoformat()
    }

# --- Modelos Pydantic ---

class AlunoCreate(BaseModel):
    nome: str
    telefone: str
    cpf: Optional[str] = ""
    email: Optional[str] = ""
    plano: Optional[str] = "2x na semana"
    dia_semana_1x: Optional[str] = None
    dia_vencimento: int = 10
    valor_mensalidade: float = 150.0
    tipo_pagamento: Optional[str] = "PIX"
    observacoes: Optional[str] = ""
    mes_matricula: Optional[str] = None
    data_nascimento: Optional[str] = ""
    autoriza_imagem: Optional[int] = 1
    turma_ids: Optional[List[int]] = None
    aprovacao_pagamento: Optional[str] = "aprovado"

class AlunoUpdate(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    cpf: Optional[str] = None
    email: Optional[str] = None
    plano: Optional[str] = None
    dia_semana_1x: Optional[str] = None
    dia_vencimento: Optional[int] = None
    valor_mensalidade: Optional[float] = None
    tipo_pagamento: Optional[str] = None
    data_nascimento: Optional[str] = None
    observacoes: Optional[str] = None
    autoriza_imagem: Optional[int] = None
    turma_ids: Optional[List[int]] = None
    aprovacao_pagamento: Optional[str] = None
    pausar_alerta_ausencia: Optional[int] = None
    motivo_pausa_alerta: Optional[str] = None

class TurmaMatriculaRequest(BaseModel):
    turma_id: int

class InativarAlunoRequest(BaseModel):
    motivo: str = "Desistência"

class PagamentoCreate(BaseModel):
    aluno_id: int
    valor: float
    forma_pagamento: str = "PIX"
    mes_referencia: Optional[str] = None
    data_pagamento: Optional[str] = None

class PresencaCreate(BaseModel):
    aluno_id: int
    data: Optional[str] = None
    horario: Optional[str] = None
    modalidade: Optional[str] = "Yoga Regular"
    observacao: Optional[str] = ""

class CalendarioPresencaRequest(BaseModel):
    aluno_id: int
    turma_id: int
    data: str
    status: str = "pendente"
    justificativa: Optional[str] = ""

class CalendarioLoteRequest(BaseModel):
    turma_id: int
    data: str

class PausarAlertaRequest(BaseModel):
    pausar: bool = True
    motivo: Optional[str] = ""

class DespesaCreate(BaseModel):
    descricao: str
    valor: float
    categoria: Optional[str] = "Geral"
    data: Optional[str] = None
    data_vencimento: Optional[str] = None
    status: Optional[str] = "pago"
    observacao: Optional[str] = ""
    parcelado: Optional[bool] = False
    total_parcelas: Optional[int] = 1
    tipo_calculo_parcela: Optional[str] = "total"
    primeira_parcela_paga: Optional[bool] = False

class DespesaUpdate(BaseModel):
    descricao: Optional[str] = None
    valor: Optional[float] = None
    categoria: Optional[str] = None
    data: Optional[str] = None
    data_vencimento: Optional[str] = None
    status: Optional[str] = None
    observacao: Optional[str] = None

class EventoCreate(BaseModel):
    titulo: str
    data: str
    horario_inicio: str
    horario_fim: Optional[str] = None
    local: Optional[str] = None
    observacoes: Optional[str] = None
    tipo: Optional[str] = "externo"

class EventoUpdate(BaseModel):
    titulo: Optional[str] = None
    data: Optional[str] = None
    horario_inicio: Optional[str] = None
    horario_fim: Optional[str] = None
    local: Optional[str] = None
    observacoes: Optional[str] = None
    tipo: Optional[str] = None

class ChatRequest(BaseModel):
    mensagem: str

class LiveChatRequest(BaseModel):
    mensagem: str
    voz: Optional[str] = "Aoede"

class TTSRequest(BaseModel):
    texto: str
    voz: Optional[str] = "Aoede"

class ConfigUpdate(BaseModel):
    configs: Dict[str, str]

class LoginRequest(BaseModel):
    username: str
    senha: str
    lembrar: Optional[bool] = True

class AlterarSenhaRequest(BaseModel):
    username: str
    senha_atual: str
    nova_senha: str

# --- Autenticação e Sessão Segura (Studio Shanti) ---
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY") or "shanti-studio-secure-auth-secret-2026"

def gerar_token_sessao(username: str, role: str) -> str:
    """Gera um token seguro assinado com HMAC-SHA256 para persistência no celular."""
    ts = int(time.time())
    payload = f"{username}:{role}:{ts}"
    sig = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token_str = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(token_str.encode("utf-8")).decode("utf-8")

def validar_token_sessao(token: str) -> Optional[Dict[str, Any]]:
    """Valida a assinatura criptográfica do token e retorna os dados do usuário."""
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        parts = decoded.split(":")
        if len(parts) != 4:
            return None
        username, role, ts_str, sig = parts
        payload = f"{username}:{role}:{ts_str}"
        expected_sig = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        user = db.obter_usuario(username)
        return user
    except Exception:
        return None

# --- Rotas da API de Autenticação ---

@app.get("/api/auth/perfis")
def api_auth_perfis():
    """Retorna os perfis do Studio Shanti para seleção rápida (Natália Garufe & Bruno Dev)."""
    return db.listar_perfis_rapidos()

@app.post("/api/auth/login")
def api_auth_login(req: LoginRequest):
    """Valida credenciais e retorna o token de acesso seguro com os dados do usuário."""
    user = db.autenticar_usuario(req.username, req.senha)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Senha ou usuário incorretos. Por favor, verifique seus dados."
        )
    token = gerar_token_sessao(user["username"], user.get("role", "admin"))
    return {
        "sucesso": True,
        "token": token,
        "user": user
    }

@app.get("/api/auth/verificar")
def api_auth_verificar(request: Request):
    """Verifica se o token salvo no celular ainda é válido."""
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif "token" in request.query_params:
        token = request.query_params.get("token")

    if not token:
        return {"autenticado": False, "mensagem": "Nenhum token fornecido"}

    user = validar_token_sessao(token)
    if not user:
        return {"autenticado": False, "mensagem": "Sessão inválida ou expirada"}

    return {
        "autenticado": True,
        "user": user
    }

@app.post("/api/auth/alterar-senha")
def api_auth_alterar_senha(req: AlterarSenhaRequest):
    """Permite ao usuário alterar sua senha informando a senha atual."""
    user = db.autenticar_usuario(req.username, req.senha_atual)
    if not user:
        raise HTTPException(status_code=400, detail="A senha atual informada está incorreta.")

    nova_senha_limpa = str(req.nova_senha).strip()
    if len(nova_senha_limpa) < 4:
        raise HTTPException(status_code=400, detail="A nova senha deve possuir pelo menos 4 caracteres.")

    sucesso = db.alterar_senha(req.username, nova_senha_limpa)
    if not sucesso:
        raise HTTPException(status_code=500, detail="Erro interno ao gravar nova senha.")

    novo_token = gerar_token_sessao(user["username"], user.get("role", "admin"))
    return {
        "sucesso": True,
        "mensagem": "Senha alterada com sucesso!",
        "token": novo_token,
        "user": user
    }

# --- Rotas da API Gerais ---

@app.get("/status-servidor")
@app.get("/api/status-servidor")
def api_status_servidor():
    """
    Endpoint ultraleve para verificação de saúde do servidor Render.
    Não realiza nenhuma consulta a banco de dados nem chamada de IA.
    Responde em menos de 10ms.
    """
    global LAST_KEEPALIVE_PING
    LAST_KEEPALIVE_PING = datetime.datetime.now(datetime.timezone.utc)
    info = obter_info_servidor_uptime()
    return {
        "status": "online",
        "servidor": info["status_servidor"],
        "cold_start": info["cold_start"],
        "uptime_segundos": info["uptime_segundos"],
        "uptime_formatado": info["uptime_formatado"],
        "started_at": info["started_at"],
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

@app.get("/status-ia")
@app.get("/api/status-ia")
async def api_status_ia():
    """
    Endpoint isolado para teste de conectividade e latência do Google Gemini.
    Mede a velocidade em milissegundos e retorna causas de erro simplificadas.
    """
    info_serv = obter_info_servidor_uptime()
    res = await ai.testar_conexao_gemini_isolada()
    
    # Gravar log do teste isolado
    db.registrar_log_diagnostico(
        tipo_evento="teste_diagnostico",
        status_servidor="ok",
        status_ia=res.get("status_ia", "ok"),
        servidor_cold_start=1 if info_serv["cold_start"] else 0,
        tempo_servidor_ms=5,
        tempo_ia_ms=res.get("latencia_ms", 0),
        sucesso=1 if res.get("sucesso", True) else 0,
        mensagem_erro=None if res.get("sucesso", True) else res.get("mensagem"),
        detalhes=res.get("detalhes")
    )
    return res

@app.get("/api/diagnostico/resumo")
def api_diagnostico_resumo():
    """Retorna dados consolidados para o painel visual de diagnóstico na tela de Ajustes."""
    info_serv = obter_info_servidor_uptime()
    status_kp = db.obter_status_keepalive()
    ultimos_logs = db.obter_ultimos_logs_diagnostico(limite=15)
    
    # Calcular se o keepalive está ativo
    agora_utc = datetime.datetime.now(datetime.timezone.utc)
    diff_mem_min = max(0, int((agora_utc - LAST_KEEPALIVE_PING).total_seconds() // 60))
    
    minutos_kp = diff_mem_min
    if status_kp.get("minutos_atras") is not None:
        minutos_kp = min(diff_mem_min, status_kp["minutos_atras"])
        
    keepalive_ativo = minutos_kp <= 15
    msg_kp = f"Último ping há {minutos_kp} min" if minutos_kp > 0 else "Último ping há menos de 1 minuto"
    
    return {
        "servidor": {
            "status": "online",
            "cold_start": info_serv["cold_start"],
            "uptime_segundos": info_serv["uptime_segundos"],
            "uptime_formatado": info_serv["uptime_formatado"],
            "started_at": info_serv["started_at"]
        },
        "keepalive": {
            "ativo": keepalive_ativo,
            "minutos_atras": minutos_kp,
            "mensagem": msg_kp
        },
        "logs": ultimos_logs
    }

@app.get("/api/health")
def api_health_check():
    """Endpoint leve para monitoramento e keep-alive 24/7 sem hibernação."""
    global LAST_KEEPALIVE_PING, LAST_KEEPALIVE_DB_LOG
    agora_utc = datetime.datetime.now(datetime.timezone.utc)
    LAST_KEEPALIVE_PING = agora_utc
    
    # Registrar no banco de dados com rate-limit de 2 minutos para manter histórico limpo
    if (agora_utc - LAST_KEEPALIVE_DB_LOG).total_seconds() >= 120:
        LAST_KEEPALIVE_DB_LOG = agora_utc
        info = obter_info_servidor_uptime()
        db.registrar_log_diagnostico(
            tipo_evento="ping_keepalive",
            status_servidor="ok",
            status_ia="nao_aplicavel",
            servidor_cold_start=1 if info["cold_start"] else 0,
            tempo_servidor_ms=2,
            tempo_ia_ms=0,
            sucesso=1,
            mensagem_erro=None,
            detalhes="Ping UptimeRobot"
        )
        
    return {"status": "online", "service": "Studio Shanti API", "timestamp": datetime.datetime.now().isoformat()}

@app.get("/api/alunos")
def api_listar_alunos(status: Optional[str] = None):
    return db.listar_alunos(status=status)

@app.post("/api/alunos")
def api_cadastrar_aluno(dados: AlunoCreate):
    aluno_id = db.cadastrar_aluno(dados.dict())
    
    avisos = []
    if dados.turma_ids:
        for tid in dados.turma_ids:
            turma = db.obter_turma(tid)
            if turma:
                cap = turma.get("capacidade_vagas", 16) or 16
                total = turma.get("total_matriculados", 0)
                if total >= cap:
                    avisos.append(f"⚠️ Atenção: A turma '{turma['nome']}' atingiu o limite máximo de {cap} alunos!")
                elif total == cap - 1:
                    avisos.append(f"⚡ Aviso: A turma '{turma['nome']}' tem apenas 1 vaga livre restante ({total}/{cap}).")

    resp = {
        "status": "ok",
        "id": aluno_id,
        "aluno_id": aluno_id,
        "mensagem": f"Aluno {dados.nome} cadastrado com sucesso!"
    }
    if avisos:
        resp["avisos"] = avisos
        resp["aviso_lotacao"] = " | ".join(avisos)
    return resp

@app.get("/api/alunos/{aluno_id}")
def api_obter_aluno(aluno_id: int):
    aluno = db.obter_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    pagamentos = db.listar_pagamentos_aluno(aluno_id)
    return {"aluno": aluno, "pagamentos": pagamentos}

@app.put("/api/alunos/{aluno_id}")
def api_atualizar_aluno(aluno_id: int, dados: AlunoUpdate):
    dados_dict = {k: v for k, v in dados.dict().items() if v is not None}
    db.atualizar_aluno(aluno_id, dados_dict)
    
    avisos = []
    if dados.turma_ids:
        for tid in dados.turma_ids:
            turma = db.obter_turma(tid)
            if turma:
                cap = turma.get("capacidade_vagas", 16) or 16
                total = turma.get("total_matriculados", 0)
                if total >= cap:
                    avisos.append(f"⚠️ Atenção: A turma '{turma['nome']}' atingiu o limite máximo de {cap} alunos!")
                elif total == cap - 1:
                    avisos.append(f"⚡ Aviso: A turma '{turma['nome']}' tem apenas 1 vaga livre restante ({total}/{cap}).")

    resp = {"status": "ok", "mensagem": "Aluno atualizado com sucesso!"}
    if avisos:
        resp["avisos"] = avisos
        resp["aviso_lotacao"] = " | ".join(avisos)
    return resp

@app.post("/api/alunos/{aluno_id}/inativar")
def api_inativar_aluno(aluno_id: int, req: InativarAlunoRequest):
    sucesso = db.inativar_aluno(aluno_id, req.motivo)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    return {"status": "ok", "mensagem": "Aluno inativado com sucesso!"}

@app.post("/api/alunos/{aluno_id}/reativar")
def api_reativar_aluno(aluno_id: int):
    sucesso = db.reativar_aluno(aluno_id)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    return {"status": "ok", "mensagem": "Aluno reativado com sucesso!"}

@app.delete("/api/alunos/{aluno_id}")
def api_excluir_aluno(aluno_id: int):
    sucesso = db.excluir_aluno(aluno_id)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    return {"status": "ok", "mensagem": "Aluno excluído com sucesso!"}

# --- Rotas de Turmas (Fase 2) ---

@app.get("/api/turmas")
def api_listar_turmas(ativas_somente: bool = True):
    return db.listar_turmas(ativas_somente=ativas_somente)

@app.get("/api/turmas/completo")
def api_listar_turmas_completo(ativas_somente: bool = True):
    return db.listar_turmas_com_alunos(ativas_somente=ativas_somente)

@app.get("/api/turmas/{turma_id}")
def api_obter_turma(turma_id: int):
    turma = db.obter_turma(turma_id)
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    return turma

@app.get("/api/turmas/{turma_id}/alunos")
def api_listar_alunos_turma(turma_id: int):
    turma = db.obter_turma(turma_id)
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    alunos = db.listar_alunos_turma(turma_id)
    return {"turma": turma, "alunos": alunos}

@app.post("/api/alunos/{aluno_id}/turmas")
def api_matricular_aluno_turma(aluno_id: int, req: TurmaMatriculaRequest):
    sucesso = db.matricular_aluno_turma(aluno_id, req.turma_id)
    if not sucesso:
        raise HTTPException(status_code=400, detail="Não foi possível matricular o aluno nesta turma")
    
    turma = db.obter_turma(req.turma_id)
    aviso = None
    if turma:
        cap = turma.get("capacidade_vagas", 16) or 16
        total = turma.get("total_matriculados", 0)
        if total >= cap:
            aviso = f"⚠️ Atenção: A turma '{turma['nome']}' atingiu o limite máximo de {cap} alunos!"
        elif total == cap - 1:
            aviso = f"⚡ Aviso: A turma '{turma['nome']}' tem apenas 1 vaga livre restante ({total}/{cap})."

    resp = {"status": "ok", "mensagem": "Aluno matriculado na turma com sucesso!", "turma": turma}
    if aviso:
        resp["aviso_lotacao"] = aviso
    return resp

@app.delete("/api/alunos/{aluno_id}/turmas/{turma_id}")
def api_desmatricular_aluno_turma(aluno_id: int, turma_id: int):
    sucesso = db.desmatricular_aluno_turma(aluno_id, turma_id)
    return {"status": "ok", "mensagem": "Aluno removido da turma com sucesso!"}

@app.post("/api/pagamentos")
def api_registrar_pagamento(dados: PagamentoCreate):
    pid = db.registrar_pagamento(
        aluno_id=dados.aluno_id,
        valor=dados.valor,
        forma_pagamento=dados.forma_pagamento,
        mes_referencia=dados.mes_referencia,
        data_pagamento=dados.data_pagamento
    )
    return {"status": "ok", "id": pid, "mensagem": "Pagamento registrado com sucesso!"}

@app.get("/api/inadimplentes")
def api_obter_inadimplentes():
    return db.obter_inadimplentes()

@app.get("/api/quantitativo")
def api_obter_quantitativo():
    return db.obter_quantitativo()

@app.get("/api/relatorio")
def api_obter_relatorio(mes_ano: Optional[str] = None):
    return db.obter_relatorio_mensal(mes_ano=mes_ano)

@app.get("/api/pagamentos")
def api_listar_pagamentos(mes_ano: Optional[str] = None):
    """Retorna lista detalhada de pagamentos recebidos no mês com nomes dos alunos e datas."""
    return db.listar_pagamentos_mes(mes_ano=mes_ano)

@app.get("/api/relatorio/pdf")
def api_baixar_relatorio_pdf(mes_ano: Optional[str] = None):
    """Gera e retorna o PDF oficial do balanço financeiro mensal do Studio Shanti."""
    buffer = pdf_service.gerar_pdf_relatorio_financeiro(mes_ano=mes_ano)
    ref_mes = mes_ano or datetime.date.today().strftime("%Y-%m")
    nome_arquivo = f"Relatorio_Financeiro_Shanti_{ref_mes}.pdf"
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={nome_arquivo}"
        }
    )

@app.get("/api/cobrancas")
def api_obter_cobrancas(tipo: str = "atrasados"):
    """Retorna lista de lembretes e links 'wa.me' prontos para disparar no WhatsApp com 1 clique."""
    return db.gerar_mensagens_cobranca(tipo=tipo)

@app.get("/api/pagamentos/{pagamento_id}/recibo")
def api_obter_recibo_pagamento(pagamento_id: int):
    recibo = db.gerar_comprovante_pagamento(pagamento_id)
    if not recibo:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")
    return recibo

@app.get("/api/frequencias")
def api_listar_frequencias(aluno_id: Optional[int] = None, data: Optional[str] = None):
    return db.listar_presencas(aluno_id=aluno_id, data=data)

@app.post("/api/frequencias")
def api_registrar_frequencia(dados: PresencaCreate):
    fid = db.registrar_presenca(
        aluno_id=dados.aluno_id,
        data=dados.data,
        horario=dados.horario,
        modalidade=dados.modalidade or "Yoga Regular",
        observacao=dados.observacao or ""
    )
    return {"status": "ok", "id": fid, "mensagem": "Presença registrada com sucesso!"}

@app.get("/api/frequencias/ausentes")
def api_obter_alunos_ausentes(dias: int = 10):
    return db.obter_alunos_ausentes(dias_sem_aula=dias)

# --- Rotas do Calendário, Check-in & Retenção de Presença ---

@app.get("/api/calendario/mes")
def api_obter_calendario_mes(ano: Optional[int] = None, mes: Optional[int] = None):
    hoje = db.obter_hoje_sp()
    if not ano:
        ano = hoje.year
    if not mes:
        mes = hoje.month
    return db.obter_grade_calendario_mes(ano, mes)

@app.get("/api/calendario/dia")
def api_obter_calendario_dia(data: Optional[str] = None):
    if not data:
        data = db.obter_hoje_sp().strftime("%Y-%m-%d")
    return db.obter_chamada_dia(data)

@app.post("/api/calendario/presenca")
def api_salvar_calendario_presenca(dados: CalendarioPresencaRequest):
    return db.salvar_status_presenca(
        aluno_id=dados.aluno_id,
        turma_id=dados.turma_id,
        data_str=dados.data,
        status=dados.status,
        justificativa=dados.justificativa or ""
    )

@app.post("/api/calendario/turma-presenca-lote")
def api_marcar_todos_presentes_turma(dados: CalendarioLoteRequest):
    return db.marcar_todos_presentes_turma(
        turma_id=dados.turma_id,
        data_str=dados.data
    )

@app.get("/api/calendario/retencao")
def api_obter_retencao_ausentes(dias: int = 14):
    return db.obter_alunos_retencao_ausentes(dias_janela=dias)

# --- Rotas da Agenda de Eventos & Compromissos Externos (Natália) ---

@app.get("/api/eventos")
def api_listar_eventos(mes_ano: Optional[str] = None, data: Optional[str] = None):
    """Lista eventos por data específica ou por mês/ano."""
    if data:
        return db.listar_eventos_dia(data)
    if mes_ano:
        try:
            partes = mes_ano.split("-")
            return db.listar_eventos_mes(int(partes[0]), int(partes[1]))
        except Exception:
            pass
    hoje = db.obter_hoje_sp()
    return db.listar_eventos_mes(hoje.year, hoje.month)

@app.get("/api/eventos/{evento_id}")
def api_obter_evento(evento_id: int):
    ev = db.obter_evento(evento_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Compromisso não encontrado")
    return ev

@app.post("/api/eventos")
def api_criar_evento(dados: EventoCreate):
    if not dados.titulo or not dados.titulo.strip():
        raise HTTPException(status_code=400, detail="Título é obrigatório")
    if not dados.data or not dados.data.strip() or not dados.horario_inicio or not dados.horario_inicio.strip():
        raise HTTPException(status_code=400, detail="Data e horário de início são obrigatórios")

    placeholders = {"informe usuário", "não informado", "nenhum", "null", "undefined"}
    titulo = dados.titulo.strip()
    if titulo.lower() in placeholders:
        raise HTTPException(status_code=400, detail="Título inválido")

    ev_id = db.criar_evento(
        titulo=titulo,
        data=dados.data.strip(),
        horario_inicio=dados.horario_inicio.strip(),
        horario_fim=dados.horario_fim.strip() if dados.horario_fim and dados.horario_fim.strip() else None,
        local=dados.local.strip() if dados.local and dados.local.strip() else None,
        observacoes=dados.observacoes.strip() if dados.observacoes and dados.observacoes.strip() else None,
        tipo=dados.tipo or "externo"
    )
    return {"sucesso": True, "id": ev_id, "mensagem": "Compromisso agendado com sucesso"}

@app.put("/api/eventos/{evento_id}")
def api_atualizar_evento(evento_id: int, dados: EventoUpdate):
    # Regras 1 e 2 de Integridade: atualização parcial apenas dos campos enviados
    payload = {k: v for k, v in dados.model_dump().items() if v is not None}
    if not payload:
        return {"sucesso": True, "id": evento_id, "mensagem": "Nenhum campo para atualizar"}

    ok = db.atualizar_evento(evento_id, payload)
    if not ok:
        raise HTTPException(status_code=404, detail="Compromisso não encontrado")
    return {"sucesso": True, "id": evento_id, "mensagem": "Compromisso atualizado com sucesso"}

@app.delete("/api/eventos/{evento_id}")
def api_excluir_evento(evento_id: int):
    ok = db.excluir_evento(evento_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Compromisso não encontrado")
    return {"sucesso": True, "id": evento_id, "mensagem": "Compromisso excluído com sucesso"}

@app.post("/api/alunos/{aluno_id}/pausar-alerta")
def api_pausar_alerta_aluno(aluno_id: int, dados: PausarAlertaRequest):
    ok = db.alternar_pausa_alerta(
        aluno_id=aluno_id,
        pausar=dados.pausar,
        motivo=dados.motivo or ""
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    return {"sucesso": True, "aluno_id": aluno_id, "pausado": dados.pausar, "motivo": dados.motivo}

@app.get("/api/despesas")
def api_listar_despesas(mes_ano: Optional[str] = None):
    return db.listar_despesas(mes_ano=mes_ano)

@app.get("/api/despesas/alertas")
def api_obter_alertas_despesas():
    return db.obter_alertas_despesas()

@app.get("/api/despesas/{despesa_id}")
def api_obter_despesa(despesa_id: int):
    desp = db.obter_despesa(despesa_id)
    if not desp:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    return desp

@app.post("/api/despesas")
def api_cadastrar_despesa(dados: DespesaCreate):
    if dados.parcelado and (dados.total_parcelas or 1) > 1:
        ids = db.registrar_despesa_parcelada(
            descricao=dados.descricao,
            valor=dados.valor,
            categoria=dados.categoria or "Geral",
            data=dados.data,
            data_vencimento=dados.data_vencimento,
            total_parcelas=dados.total_parcelas or 2,
            tipo_calculo_parcela=dados.tipo_calculo_parcela or "total",
            primeira_parcela_paga=bool(dados.primeira_parcela_paga),
            observacao=dados.observacao or ""
        )
        return {
            "status": "ok",
            "parcelado": True,
            "ids": ids,
            "total_parcelas": len(ids),
            "mensagem": f"Despesa parcelada em {len(ids)}x registrada com sucesso!"
        }
    else:
        did = db.registrar_despesa(
            descricao=dados.descricao,
            valor=dados.valor,
            categoria=dados.categoria or "Geral",
            data=dados.data,
            data_vencimento=dados.data_vencimento,
            status=dados.status or "pago",
            observacao=dados.observacao or ""
        )
        return {"status": "ok", "parcelado": False, "id": did, "mensagem": "Despesa registrada com sucesso!"}

@app.put("/api/despesas/{despesa_id}")
def api_atualizar_despesa(despesa_id: int, dados: DespesaUpdate):
    dados_dict = {k: v for k, v in dados.dict().items() if v is not None}
    sucesso = db.atualizar_despesa(despesa_id, dados_dict)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    desp_atualizada = db.obter_despesa(despesa_id)
    return {"status": "ok", "sucesso": True, "mensagem": "Despesa atualizada com sucesso!", "despesa": desp_atualizada, **(desp_atualizada or {})}

@app.delete("/api/despesas/{despesa_id}")
def api_excluir_despesa(despesa_id: int, excluir_grupo: bool = False):
    sucesso = db.excluir_despesa(despesa_id, excluir_grupo=excluir_grupo)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    msg = "Parcelamento completo excluído com sucesso!" if excluir_grupo else "Despesa excluída com sucesso!"
    return {"status": "ok", "sucesso": True, "mensagem": msg}

# --- FASE 4: Rotas de Contratos Digitais, Matrícula Online & 'Entrou, Pagou' ---

UPLOAD_CONTRATOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "contratos")
os.makedirs(UPLOAD_CONTRATOS_DIR, exist_ok=True)

@app.get("/matricula")
def get_pagina_matricula():
    """Serve a página pública de auto-matrícula do aluno."""
    html_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "matricula.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    raise HTTPException(status_code=404, detail="Página de matrícula não encontrada")

@app.post("/api/matricula/publica")
def api_cadastrar_matricula_publica(dados: AlunoCreate):
    """Permite que um novo aluno preencha o formulário online e se inscreva."""
    aluno_id = db.cadastrar_matricula_publica(dados.dict())
    return {
        "sucesso": True,
        "aluno_id": aluno_id,
        "aprovacao_pagamento": "pendente",
        "mensagem": "Matrícula recebida com sucesso! Aguardando confirmação de pagamento pela professora Natália."
    }

@app.post("/api/alunos/{aluno_id}/aprovar-pagamento")
def api_aprovar_matricula_pagamento(aluno_id: int, payload: Optional[Dict[str, Any]] = None):
    """Regra 'Entrou, Pagou': Natália confirma pagamento, lança 1ª mensalidade como paga e ativa aluno."""
    try:
        forma = "PIX"
        if payload and isinstance(payload, dict):
            forma = payload.get("forma_pagamento", "PIX")
        res = db.aprovar_matricula_pagamento(aluno_id, forma_pagamento=forma)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/contratos")
def api_listar_contratos(filtro: Optional[str] = None):
    """Retorna listagem de contratos com cálculo dinâmico de vigência e status."""
    return db.listar_contratos(filtro=filtro)

@app.get("/api/contratos/alertas")
def api_obter_alertas_contratos():
    """Retorna contadores de contratos a vencer (30 dias), pendentes e vencidos."""
    return db.obter_alertas_contratos()

@app.get("/api/alunos/{aluno_id}/contrato/pdf")
def api_baixar_contrato_aluno_pdf(aluno_id: int):
    """Gera e retorna o PDF oficial do contrato preenchido com as cláusulas 1 a 13 congeladas."""
    aluno = db.obter_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    buffer = contract_service.gerar_pdf_contrato(aluno_id)
    nome_limpo = re.sub(r'[^a-zA-Z0-9_]', '_', aluno.get("nome", "Aluno"))
    nome_arquivo = f"Contrato_Studio_Shanti_{nome_limpo}.pdf"
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename={nome_arquivo}"
        }
    )

@app.get("/api/alunos/{aluno_id}/contrato/whatsapp")
def api_obter_link_whatsapp_contrato(aluno_id: int):
    """Retorna mensagem e link do WhatsApp para envio do contrato ao aluno."""
    aluno = db.obter_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    
    configs = db.obter_configuracoes()
    studio_nome = configs.get("nome_studio", "Studio Shanti")
    nome = aluno.get("nome", "")
    plano = aluno.get("plano", "")
    
    msg = (
        f"📜 *CONTRATO DE MATRÍCULA - {studio_nome}* 🧘‍♀️\n\n"
        f"Olá, *{nome}*! Seja muito bem-vindo(a) à nossa família Shanti! 🙏\n\n"
        f"Preparamos o seu Contrato de Prestação de Serviços (Plano {plano}) com todo carinho. "
        f"A professora Natália já assinou o documento oficial.\n\n"
        f"Por favor, acesse o link abaixo para visualizar, assinar a sua via e nos enviar de volta para validação no estúdio:\n"
        f"👉 https://shanti-studio-yoga.onrender.com/api/alunos/{aluno_id}/contrato/pdf\n\n"
        f"Qualquer dúvida estamos à disposição! Namastê. ✨"
    )
    
    tel_limpo = "".join(filter(str.isdigit, aluno.get("telefone", "")))
    if tel_limpo and not tel_limpo.startswith("55"):
        tel_limpo = "55" + tel_limpo
        
    link_wa = f"https://wa.me/{tel_limpo}?text={urllib.parse.quote(msg)}"
    return {
        "aluno_id": aluno_id,
        "mensagem": msg,
        "link_whatsapp": link_wa
    }

@app.post("/api/alunos/{aluno_id}/contrato/upload")
async def api_upload_contrato_assinado(aluno_id: int, file: UploadFile = File(...)):
    """Recebe o arquivo com as DUAS assinaturas (Natália + Aluno) e atualiza para 'Em dia'."""
    aluno = db.obter_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
        
    ext = os.path.splitext(file.filename)[1].lower() or ".pdf"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    novo_nome = f"contrato_assinado_{aluno_id}_{timestamp}{ext}"
    destino = os.path.join(UPLOAD_CONTRATOS_DIR, novo_nome)
    
    conteudo = await file.read()
    with open(destino, "wb") as f:
        f.write(conteudo)
        
    caminho_relativo = f"uploads/contratos/{novo_nome}"
    db.salvar_contrato_assinado(aluno_id, caminho_relativo)
    aluno_atualizado = db.obter_aluno(aluno_id) or {}
    return {
        "sucesso": True,
        "mensagem": "Contrato assinado anexado com sucesso! Status atualizado para 'Em dia' com vigência de 1 ano.",
        "arquivo": caminho_relativo,
        "status_contrato": aluno_atualizado.get("status_contrato", "em_dia"),
        "data_vigencia_contrato": aluno_atualizado.get("data_vigencia_contrato")
    }

@app.get("/api/alunos/{aluno_id}/contrato/arquivo")
def api_obter_arquivo_contrato_assinado(aluno_id: int):
    """Permite visualizar/baixar o arquivo assinado armazenado."""
    aluno = db.obter_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    arq_relativo = aluno.get("contrato_assinado_arquivo")
    if not arq_relativo:
        raise HTTPException(status_code=404, detail="Nenhum contrato assinado anexado para este aluno.")
    
    caminho_completo = os.path.join(os.path.dirname(os.path.abspath(__file__)), arq_relativo.replace("/", os.sep))
    if not os.path.exists(caminho_completo):
        raise HTTPException(status_code=404, detail="Arquivo físico do contrato não encontrado no servidor.")
    return FileResponse(caminho_completo)

@app.delete("/api/alunos/{aluno_id}/contrato/arquivo")
def api_remover_arquivo_contrato_assinado(aluno_id: int):
    """Remove a vinculação do arquivo assinado."""
    aluno = db.obter_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    db.remover_contrato_assinado(aluno_id)
    return {"sucesso": True, "mensagem": "Contrato assinado removido com sucesso. Status retornado para pendente."}

# --- FASE 6: Assinaturas Digitais Autentique (API v2 GraphQL & Webhooks) ---

class EnviarAutentiqueRequest(BaseModel):
    sandbox: Optional[bool] = None

class ConfigAutentiqueRequest(BaseModel):
    token: Optional[str] = None
    sandbox: Optional[bool] = True

@app.post("/api/alunos/{aluno_id}/contrato/autentique/enviar")
async def api_enviar_contrato_autentique(aluno_id: int, req: Optional[EnviarAutentiqueRequest] = None):
    """Gera o contrato com cláusulas 1 a 13 e envia para assinatura via Autentique."""
    aluno = db.obter_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")
    
    sandbox_param = req.sandbox if req else None
    try:
        resultado = autentique_service.criar_documento_contrato(aluno_id, sandbox=sandbox_param)
        return resultado
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/alunos/{aluno_id}/contrato/autentique/status")
def api_verificar_status_autentique(aluno_id: int):
    """Consulta em tempo real o status do contrato do aluno no Autentique."""
    aluno = db.obter_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")
    
    doc_id = aluno.get("autentique_doc_id")
    if not doc_id:
        return {
            "enviado": False,
            "status": aluno.get("status_contrato", "pendente"),
            "mensagem": "Nenhum contrato foi enviado ao Autentique para este aluno."
        }
    
    try:
        info = autentique_service.consultar_status_documento(doc_id)
        # Atualiza a etapa e links no banco de dados
        if info.get("etapa"):
            db.atualizar_status_autentique(aluno_id, info["etapa"])
        dados_atualizacao = {}
        if info.get("link_natalia"):
            dados_atualizacao["autentique_link_natalia"] = info["link_natalia"]
        if info.get("link_aluno"):
            dados_atualizacao["autentique_link"] = info["link_aluno"]
        if dados_atualizacao:
            db.atualizar_aluno(aluno_id, dados_atualizacao)

        # Se foi finalizado e ainda não foi baixado localmente
        if info.get("finalizado") and aluno.get("status_contrato") != "em_dia":
            url_assinado = info.get("url_assinado")
            if url_assinado:
                caminho_local = autentique_service.baixar_e_salvar_contrato_assinado(aluno_id, doc_id, url_assinado)
                info["arquivo_baixado"] = caminho_local
                info["status_atualizado"] = "em_dia"
        return info
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/webhooks/autentique")
async def api_webhook_autentique(request: Request):
    """
    Webhook público para notificações de eventos do Autentique.
    Quando o documento é concluído ('document.finished'), baixa o PDF assinado
    e atualiza a vigência do contrato para 'em_dia'.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "error", "mensagem": "Invalid JSON payload"}
    
    event = payload.get("event", {})
    event_type = event.get("type", "")
    event_data = event.get("data", {})
    event_object = event_data.get("object", {})
    
    doc_id = event_object.get("id") or event_data.get("id") or ""
    
    if not doc_id:
        return {"status": "ignored", "mensagem": "Sem document_id no payload"}
    
    aluno = db.obter_aluno_por_autentique_doc_id(doc_id)
    if not aluno:
        return {"status": "ignored", "mensagem": f"Nenhum aluno vinculado ao doc_id {doc_id}"}
    
    aluno_id = aluno["id"]
    
    if event_type == "document.finished":
        files = event_object.get("files", {})
        url_assinado = files.get("signed") or files.get("certified") or files.get("pades")
        if url_assinado:
            try:
                autentique_service.baixar_e_salvar_contrato_assinado(aluno_id, doc_id, url_assinado)
                return {"status": "success", "acao": "contrato_concluido", "aluno_id": aluno_id}
            except Exception as e:
                return {"status": "error", "erro": str(e)}
    elif event_type == "signature.rejected":
        db.atualizar_status_autentique(aluno_id, "rejeitado")
        return {"status": "success", "acao": "marcado_rejeitado"}
    
    return {"status": "success", "event_type": event_type}

@app.get("/api/configuracoes/autentique/testar")
def api_testar_conexao_autentique():
    """Testa a conexão e credenciais com a API do Autentique."""
    return autentique_service.testar_conexao()

@app.post("/api/configuracoes/autentique/salvar")
def api_salvar_config_autentique(req: ConfigAutentiqueRequest):
    """Salva token e modo sandbox do Autentique nas configurações."""
    if req.token is not None and req.token.strip():
        # Não sobrescrever com máscara se o usuário não alterou
        if not req.token.startswith("••••"):
            db.salvar_configuracao("autentique_api_token", req.token.strip())
    
    if req.sandbox is not None:
        db.salvar_configuracao("autentique_sandbox", "true" if req.sandbox else "false")
    
    return autentique_service.testar_conexao()

@app.get("/api/aniversariantes")
def api_obter_aniversariantes(mes: Optional[int] = None):
    return db.obter_aniversariantes_mes(mes=mes)

@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    """Envia texto para o assistente IA com rastreamento isolado de métricas."""
    if not req.mensagem.strip():
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    
    t0 = time.perf_counter()
    info_serv = obter_info_servidor_uptime()
    
    msg_lower = req.mensagem.lower()
    termos_atalho = [
        "atraso", "atrasada", "atrasadas", "atrasados", "devedor", "inadimplente", "quem deve", "não pagou", "vencid",
        "cobrança", "cobrar", "lembrete", "quem já pagou", "quem pagou", "relatorio", "relatório", "faturamento",
        "despesa", "despesas", "gastei", "contrato", "contratos", "quantitativo", "alunos ativos", "turma",
        "presença", "presenca", "ausente", "ausentes", "aniversariante", "matricula", "matrícula"
    ]
    e_atalho = any(t in msg_lower for t in termos_atalho)
    tipo_ev = "atalho" if e_atalho else "chat"
    
    try:
        resultado = await ai.processar_mensagem_ia(req.mensagem)
        tempo_total_ms = max(1, int((time.perf_counter() - t0) * 1000))
        tempo_ia_ms = 0 if e_atalho else max(0, tempo_total_ms - 10)
        status_ia = "local" if e_atalho else ("lento" if tempo_ia_ms > 3000 else "ok")
        
        db.registrar_log_diagnostico(
            tipo_evento=tipo_ev,
            status_servidor="lento" if tempo_total_ms > 4000 else "ok",
            status_ia=status_ia,
            servidor_cold_start=1 if info_serv["cold_start"] else 0,
            tempo_servidor_ms=tempo_total_ms,
            tempo_ia_ms=tempo_ia_ms,
            sucesso=1,
            mensagem_erro=None,
            detalhes=f"Intenção: {resultado.get('tipo', 'geral')}"
        )
        return resultado
    except Exception as e:
        tempo_total_ms = max(1, int((time.perf_counter() - t0) * 1000))
        db.registrar_log_diagnostico(
            tipo_evento=tipo_ev,
            status_servidor="ok",
            status_ia="erro",
            servidor_cold_start=1 if info_serv["cold_start"] else 0,
            tempo_servidor_ms=tempo_total_ms,
            tempo_ia_ms=tempo_total_ms,
            sucesso=0,
            mensagem_erro=str(e)[:120],
            detalhes="Erro no processamento do chat"
        )
        raise

@app.post("/api/chat/audio")
async def api_chat_audio(audio: UploadFile = File(...), texto_transcrito: Optional[str] = Form(None)):
    """
    Recebe arquivo de áudio gravado no app e transcreve com a IA Gemini multimodal.
    Registra diagnóstico completo de latência de áudio.
    """
    t0 = time.perf_counter()
    info_serv = obter_info_servidor_uptime()
    
    texto = (texto_transcrito or "").strip()
    if not texto:
        conteudo = await audio.read()
        raw_mime = (audio.content_type or "audio/webm").lower()
        if "mp4" in raw_mime or "m4a" in raw_mime or "aac" in raw_mime:
            mime_type = "audio/mp4"
            ext = "m4a"
        elif "ogg" in raw_mime:
            mime_type = "audio/ogg"
            ext = "ogg"
        elif "wav" in raw_mime:
            mime_type = "audio/wav"
            ext = "wav"
        else:
            mime_type = "audio/webm"
            ext = "webm"

        # 1. Tentar Groq Whisper (Ultra-rápido ~400ms)
        groq_key = ai.get_groq_api_key()
        if groq_key and len(conteudo) > 300:
            try:
                texto = await ai.transcrever_audio_groq(
                    audio_bytes=conteudo,
                    filename=f"audio.{ext}",
                    mime_type=mime_type,
                    api_key=groq_key
                )
            except Exception as eg:
                print(f"Erro ao transcrever com Groq Whisper: {eg}. Tentando Gemini como fallback...")
                texto = ""

        # 2. Fallback para Google Gemini Multimodal
        if not texto and len(conteudo) > 500:
            gemini_key = ai.get_gemini_api_key()
            if gemini_key:
                try:
                    from google import genai
                    from google.genai import types
                    client = genai.Client(api_key=gemini_key)

                    candidate_models = [
                        "gemini-3.5-flash-lite",
                        "gemini-3.1-flash-lite",
                        "gemini-flash-latest"
                    ]
                    for modelo in candidate_models:
                        try:
                            response = await asyncio.wait_for(
                                asyncio.to_thread(
                                    client.models.generate_content,
                                    model=modelo,
                                    contents=[
                                        types.Part.from_bytes(data=conteudo, mime_type=mime_type),
                                        "Você é um assistente do estúdio de yoga. Transcreva com fidelidade absoluta o que foi falado neste áudio em português do Brasil (pt-BR). Retorne APENAS o texto transcrito, sem aspas, sem pontuações extras e sem explicações. Se houver apenas silêncio ou ruído inaudível, responda SILENCIO."
                                    ]
                                ),
                                timeout=15.0
                            )
                            texto_resp = (response.text or "").strip()
                            texto_resp = re.sub(r'^["\'\s]+|["\'\s]+$', '', texto_resp)
                            if any(texto_resp.lower().startswith(x) for x in ["silêncio", "silencio", "sem fala", "inaudível", "inaudivel", "ruído", "ruido", "nenhum som"]):
                                texto = ""
                                break
                            if texto_resp:
                                texto = texto_resp
                                break
                        except Exception as err_m:
                            print(f"Modelo áudio {modelo} falhou ou expirou: {err_m}. Tentando próximo...")
                            continue
                except Exception as e:
                    print(f"Erro ao transcrever áudio com Gemini: {e}")
                    texto = ""


    if not texto:
        tempo_total_ms = max(1, int((time.perf_counter() - t0) * 1000))
        db.registrar_log_diagnostico(
            tipo_evento="audio",
            status_servidor="ok",
            status_ia="ok",
            servidor_cold_start=1 if info_serv["cold_start"] else 0,
            tempo_servidor_ms=tempo_total_ms,
            tempo_ia_ms=max(0, tempo_total_ms - 20),
            sucesso=1,
            mensagem_erro=None,
            detalhes="Áudio inaudível ou silêncio"
        )
        return {
            "resposta": "🧘 Não consegui compreender o seu áudio com clareza. Por favor, aproxime-se um pouco mais do microfone ou tente falar novamente!",
            "tipo": "audio_incompreensivel",
            "transcricao": "Voz não identificada",
            "dados": []
        }

    resultado = await ai.processar_mensagem_ia(texto)
    resultado["transcricao"] = texto
    
    tempo_total_ms = max(1, int((time.perf_counter() - t0) * 1000))
    tempo_ia_ms = max(0, tempo_total_ms - 30)
    db.registrar_log_diagnostico(
        tipo_evento="audio",
        status_servidor="lento" if tempo_total_ms > 4000 else "ok",
        status_ia="lento" if tempo_ia_ms > 3000 else "ok",
        servidor_cold_start=1 if info_serv["cold_start"] else 0,
        tempo_servidor_ms=tempo_total_ms,
        tempo_ia_ms=tempo_ia_ms,
        sucesso=1,
        mensagem_erro=None,
        detalhes=f"Transcrição: '{texto[:35]}'"
    )
    return resultado

@app.post("/api/chat/live")
async def api_chat_live(req: LiveChatRequest):
    """
    Processa mensagem no modo Gemini Live em tempo real.
    Retorna a resposta transcrita, áudio WAV de alta fidelidade com a voz Aoede e botões de ação integrados.
    """
    if not req.mensagem.strip():
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    resultado = await ai.processar_gemini_live(req.mensagem, voz=req.voz or "Aoede")
    return resultado

@app.post("/api/tts")
async def api_tts(req: TTSRequest):
    """Gera áudio WAV em Base64 para um texto utilizando a voz Aoede do Gemini."""
    if not req.texto.strip():
        raise HTTPException(status_code=400, detail="Texto vazio")
    audio_b64 = await ai.gerar_audio_gemini(req.texto, voz=req.voz or "Aoede")
    return {"status": "ok", "audio_base64": audio_b64}

@app.get("/api/configuracoes")
def api_obter_configuracoes():
    return db.obter_configuracoes()

@app.post("/api/configuracoes")
def api_salvar_configuracoes(dados: ConfigUpdate):
    for k, v in dados.configs.items():
        db.salvar_configuracao(k, v)
    return {"status": "ok", "mensagem": "Configurações salvas com sucesso!"}

@app.post("/api/configuracoes/icone")
async def api_salvar_icone(
    imagem: Optional[UploadFile] = File(None),
    escala: float = Form(0.75),
    offset_y: float = Form(0.0)
):
    """
    Atualiza o ícone do PWA e a splash screen.
    Permite enviar nova logo ou reposicionar a logo existente com margens seguras (sem corte no celular).
    """
    try:
        frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
        logo_path = os.path.join(frontend_dir, "img", "shanti_logo.png")
        
        if imagem and imagem.filename:
            content = await imagem.read()
            img = Image.open(io.BytesIO(content)).convert("RGBA")
            os.makedirs(os.path.dirname(logo_path), exist_ok=True)
            img.save(logo_path, "PNG")
        elif os.path.exists(logo_path):
            img = Image.open(logo_path).convert("RGBA")
        else:
            raise HTTPException(status_code=400, detail="Nenhuma imagem de logo encontrada no servidor.")

        # Garantir limites seguros para escala e offset
        escala_val = max(0.40, min(float(escala), 1.0))
        offset_val = max(-0.25, min(float(offset_y), 0.25))

        # Canvas 512x512 no verde floresta da marca boutique (#3F4E3A)
        bg_color = (63, 78, 58, 255)
        canvas = Image.new("RGBA", (512, 512), bg_color)

        w, h = img.size
        target_w = int(512 * escala_val)
        target_h = int(512 * escala_val)
        ratio = min(target_w / w, target_h / h)
        new_w = max(1, int(w * ratio))
        new_h = max(1, int(h * ratio))

        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        pos_x = (512 - new_w) // 2
        pos_y = (512 - new_h) // 2 + int(512 * offset_val)

        canvas.paste(resized, (pos_x, pos_y), resized)

        icons_dir = os.path.join(frontend_dir, "icons")
        os.makedirs(icons_dir, exist_ok=True)

        # Salvar tamanhos padrão do PWA com safe margins
        canvas.save(os.path.join(icons_dir, "icon-512.png"), "PNG")
        canvas.resize((192, 192), Image.Resampling.LANCZOS).save(os.path.join(icons_dir, "icon-192.png"), "PNG")
        canvas.resize((96, 96), Image.Resampling.LANCZOS).save(os.path.join(icons_dir, "icon-96.png"), "PNG")
        canvas.resize((64, 64), Image.Resampling.LANCZOS).save(os.path.join(frontend_dir, "favicon.png"), "PNG")

        db.salvar_configuracao("icone_escala", str(escala_val))
        db.salvar_configuracao("icone_offset_y", str(offset_val))

        timestamp = int(datetime.datetime.now().timestamp())
        return {
            "status": "ok",
            "mensagem": "Ícones do PWA e Splash Screen atualizados com sucesso!",
            "versao": timestamp
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar ícone: {str(e)}")

# --- Montar Arquivos Estáticos do Frontend (PWA) ---

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

if not os.path.exists(FRONTEND_DIR):
    os.makedirs(FRONTEND_DIR, exist_ok=True)

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

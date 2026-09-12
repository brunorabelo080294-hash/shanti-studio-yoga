"""
Servidor FastAPI para o Yoga Studio App (PWA com visual de WhatsApp).
Fornece rotas da API REST, serviços de IA, cobranças no WhatsApp e arquivos estáticos.
"""
import os
import sys
import io
import datetime
import re
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image

import backend.database as db
import backend.ai_service as ai
import backend.pdf_service as pdf_service

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
    # Evitar cache de HTML/CSS/JS para atualizações visuais imediatas
    if any(request.url.path.endswith(ext) for ext in [".html", ".css", ".js", "/"]):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# --- Modelos Pydantic ---

class AlunoCreate(BaseModel):
    nome: str
    telefone: str
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

class AlunoUpdate(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
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

class DespesaCreate(BaseModel):
    descricao: str
    valor: float
    categoria: Optional[str] = "Geral"
    data: Optional[str] = None
    data_vencimento: Optional[str] = None
    status: Optional[str] = "pago"
    observacao: Optional[str] = ""

class DespesaUpdate(BaseModel):
    descricao: Optional[str] = None
    valor: Optional[float] = None
    categoria: Optional[str] = None
    data: Optional[str] = None
    data_vencimento: Optional[str] = None
    status: Optional[str] = None
    observacao: Optional[str] = None

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

# --- Rotas da API ---

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
    did = db.registrar_despesa(
        descricao=dados.descricao,
        valor=dados.valor,
        categoria=dados.categoria or "Geral",
        data=dados.data,
        data_vencimento=dados.data_vencimento,
        status=dados.status or "pago",
        observacao=dados.observacao or ""
    )
    return {"status": "ok", "id": did, "mensagem": "Despesa registrada com sucesso!"}

@app.put("/api/despesas/{despesa_id}")
def api_atualizar_despesa(despesa_id: int, dados: DespesaUpdate):
    dados_dict = {k: v for k, v in dados.dict().items() if v is not None}
    sucesso = db.atualizar_despesa(despesa_id, dados_dict)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    desp_atualizada = db.obter_despesa(despesa_id)
    return {"status": "ok", "sucesso": True, "mensagem": "Despesa atualizada com sucesso!", "despesa": desp_atualizada, **(desp_atualizada or {})}

@app.delete("/api/despesas/{despesa_id}")
def api_excluir_despesa(despesa_id: int):
    sucesso = db.excluir_despesa(despesa_id)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    return {"status": "ok", "sucesso": True, "mensagem": "Despesa excluída com sucesso!"}

@app.get("/api/aniversariantes")
def api_obter_aniversariantes(mes: Optional[int] = None):
    return db.obter_aniversariantes_mes(mes=mes)

@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    """Envia texto para o assistente IA."""
    if not req.mensagem.strip():
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    resultado = await ai.processar_mensagem_ia(req.mensagem)
    return resultado

@app.post("/api/chat/audio")
async def api_chat_audio(audio: UploadFile = File(...), texto_transcrito: Optional[str] = Form(None)):
    """
    Recebe arquivo de áudio gravado no app e transcreve com a IA Gemini multimodal.
    """
    texto = (texto_transcrito or "").strip()
    if not texto:
        conteudo = await audio.read()
        api_key = ai.get_api_key()
        if api_key and len(conteudo) > 500:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)

                raw_mime = (audio.content_type or "audio/webm").lower()
                if "mp4" in raw_mime or "m4a" in raw_mime or "aac" in raw_mime:
                    mime_type = "audio/mp4"
                elif "ogg" in raw_mime:
                    mime_type = "audio/ogg"
                elif "wav" in raw_mime:
                    mime_type = "audio/wav"
                else:
                    mime_type = "audio/webm"

                candidate_models = [
                    "gemini-3.6-flash",
                    "gemini-3.5-flash",
                    "gemini-flash-lite-latest",
                    "gemini-3.5-flash-lite",
                    "gemini-flash-latest"
                ]
                for modelo in candidate_models:
                    try:
                        response = await client.aio.models.generate_content(
                            model=modelo,
                            contents=[
                                types.Part.from_bytes(data=conteudo, mime_type=mime_type),
                                "Você é um assistente do estúdio de yoga. Transcreva com fidelidade absoluta o que foi falado neste áudio em português do Brasil (pt-BR). Retorne APENAS o texto transcrito, sem aspas, sem pontuações extras e sem explicações. Se houver apenas silêncio ou ruído inaudível, responda SILENCIO."
                            ]
                        )
                        texto = (response.text or "").strip()
                        texto = re.sub(r'^["\'\s]+|["\'\s]+$', '', texto)
                        if any(texto.lower().startswith(x) for x in ["silêncio", "silencio", "sem fala", "inaudível", "inaudivel", "ruído", "ruido", "nenhum som"]):
                            texto = ""
                        if texto:
                            break
                    except Exception as err_m:
                        print(f"Modelo áudio {modelo} falhou: {err_m}. Tentando próximo...")
                        continue
            except Exception as e:
                print(f"Erro ao transcrever áudio com Gemini: {e}")
                texto = ""

    if not texto:
        return {
            "resposta": "🧘 Não consegui compreender o seu áudio com clareza. Por favor, aproxime-se um pouco mais do microfone ou tente falar novamente!",
            "tipo": "audio_incompreensivel",
            "transcricao": "Voz não identificada",
            "dados": []
        }

    resultado = await ai.processar_mensagem_ia(texto)
    resultado["transcricao"] = texto
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

        # Canvas 512x512 no verde escuro da marca (#1C2B24)
        bg_color = (28, 43, 36, 255)
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

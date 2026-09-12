"""
Servidor FastAPI para o Yoga Studio App (PWA com visual de WhatsApp).
Fornece rotas da API REST, serviços de IA, cobranças no WhatsApp e arquivos estáticos.
"""
import os
import sys
import datetime
import re
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import backend.database as db
import backend.ai_service as ai

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
    plano: Optional[str] = "Yoga Regular"
    dia_vencimento: int = 10
    valor_mensalidade: float = 150.0
    tipo_pagamento: Optional[str] = "PIX"
    observacoes: Optional[str] = ""
    mes_matricula: Optional[str] = None

class AlunoUpdate(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    plano: Optional[str] = None
    dia_vencimento: Optional[int] = None
    valor_mensalidade: Optional[float] = None
    tipo_pagamento: Optional[str] = None
    observacoes: Optional[str] = None

class InativarAlunoRequest(BaseModel):
    motivo: str = "Desistência"

class PagamentoCreate(BaseModel):
    aluno_id: int
    valor: float
    forma_pagamento: str = "PIX"
    mes_referencia: Optional[str] = None
    data_pagamento: Optional[str] = None

class ChatRequest(BaseModel):
    mensagem: str

class ConfigUpdate(BaseModel):
    configs: Dict[str, str]

# --- Rotas da API ---

@app.get("/api/alunos")
def api_listar_alunos(status: Optional[str] = None):
    return db.listar_alunos(status=status)

@app.post("/api/alunos")
def api_cadastrar_aluno(dados: AlunoCreate):
    aluno_id = db.cadastrar_aluno(dados.dict())
    return {"status": "ok", "id": aluno_id, "mensagem": f"Aluno {dados.nome} cadastrado com sucesso!"}

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
    return {"status": "ok", "mensagem": "Aluno atualizado com sucesso!"}

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

@app.get("/api/cobrancas")
def api_obter_cobrancas(tipo: str = "atrasados"):
    """Retorna lista de lembretes e links 'wa.me' prontos para disparar no WhatsApp com 1 clique."""
    return db.gerar_mensagens_cobranca(tipo=tipo)

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

                response = await client.aio.models.generate_content(
                    model="gemini-flash-latest",
                    contents=[
                        types.Part.from_bytes(data=conteudo, mime_type=mime_type),
                        "Transcreva com máxima precisão o que foi falado neste áudio em português. Retorne EXCLUSIVAMENTE o texto transcrito, sem introduções, sem aspas e sem explicações adicionais."
                    ]
                )
                texto = (response.text or "").strip()
                texto = re.sub(r'^["\'\s]+|["\'\s]+$', '', texto)
                if any(texto.lower().startswith(x) for x in ["silêncio", "silencio", "sem fala", "inaudível", "inaudivel", "ruído", "ruido", "nenhum som"]):
                    texto = ""
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

@app.get("/api/configuracoes")
def api_obter_configuracoes():
    return db.obter_configuracoes()

@app.post("/api/configuracoes")
def api_salvar_configuracoes(dados: ConfigUpdate):
    for k, v in dados.configs.items():
        db.salvar_configuracao(k, v)
    return {"status": "ok", "mensagem": "Configurações salvas com sucesso!"}

# --- Montar Arquivos Estáticos do Frontend (PWA) ---

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

if not os.path.exists(FRONTEND_DIR):
    os.makedirs(FRONTEND_DIR, exist_ok=True)

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

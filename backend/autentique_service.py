"""
Serviço de integração com a plataforma Autentique (API v2 GraphQL).
Permite criar documentos com upload de PDF (multipart), configurar signatários
(Natália + Aluno) com envio via WhatsApp/E-mail, consultar status de assinaturas,
tratar webhooks e baixar automaticamente o documento final assinado.
"""

import os
import io
import json
import logging
import urllib.parse
from typing import Dict, Any, Optional, List, Tuple
import requests

import backend.database as db
import backend.contract_service as contract_service

logger = logging.getLogger("autentique_service")
AUTENTIQUE_GRAPHQL_URL = "https://api.autentique.com.br/v2/graphql"


def obter_token_autentique() -> Optional[str]:
    """
    Retorna o token da API Autentique.
    Prioridade:
    1. Tabela 'configuracoes' do banco SQLite (chave 'autentique_api_token')
    2. Variável de ambiente AUTENTIQUE_API_TOKEN
    3. Token configurado pelo proprietário
    """
    try:
        configs = db.obter_configuracoes()
        if "autentique_api_token" in configs:
            db_token = configs.get("autentique_api_token")
            if db_token and db_token.strip():
                return db_token.strip()
            # Explicitamente vazio nas configurações
            return None
    except Exception as e:
        logger.error(f"Erro ao obter token do Autentique das configurações: {e}")

    token = os.getenv("AUTENTIQUE_API_TOKEN", "fc2c3926514c154c5f25a5baa6dc32a95455135b0fcd52b278599ce6c4a36f6c")
    if token and token.strip():
        return token.strip()

    return None


def is_sandbox_mode() -> bool:
    """
    Verifica se o modo Sandbox (testes gratuitos) está ativo.
    Padrão: True (seguro por padrão para evitar consumo da cota de 20 docs).
    Pode ser desativado definindo 'autentique_sandbox' como 'false' nas configurações ou env.
    """
    env_sandbox = os.getenv("AUTENTIQUE_SANDBOX")
    if env_sandbox is not None:
        return env_sandbox.strip().lower() in ("1", "true", "yes", "on")

    try:
        configs = db.obter_configuracoes()
        val = configs.get("autentique_sandbox")
        if val is not None:
            return val.strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        pass

    return True  # Por padrão, ativo para segurança


def formatar_telefone_e164(telefone: str) -> Optional[str]:
    """Formata telefone para o padrão internacional E.164 exigido pelo Autentique (+55DDDXXXXXXXXX)."""
    if not telefone:
        return None
    digitos = "".join(filter(str.isdigit, telefone))
    if not digitos:
        return None
    if not digitos.startswith("55"):
        digitos = "55" + digitos
    return f"+{digitos}"


def testar_conexao(token: Optional[str] = None) -> Dict[str, Any]:
    """
    Testa a conectividade com o Autentique executando uma query GraphQL simples
    que busca os dados da conta autenticada via 'me'.
    """
    api_token = token or obter_token_autentique()
    if not api_token:
        return {
            "sucesso": False,
            "mensagem": "Token da API Autentique não configurado. Por favor, insira o token em Ajustes."
        }

    query = """
    query {
      me {
        id
        name
        email
      }
    }
    """
    try:
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        res = requests.post(AUTENTIQUE_GRAPHQL_URL, json={"query": query}, headers=headers, timeout=15)
        if res.status_code == 401:
            return {
                "sucesso": False,
                "mensagem": "Token da API Autentique inválido ou expirado (HTTP 401)."
            }
        
        data = res.json()
        if "errors" in data and data["errors"]:
            msg_erro = data["errors"][0].get("message", "Erro GraphQL desconhecido.")
            return {"sucesso": False, "mensagem": f"Erro retornado pelo Autentique: {msg_erro}"}

        usuario = data.get("data", {}).get("me", {})
        return {
            "sucesso": True,
            "mensagem": f"Conexão com Autentique validada com sucesso! Conta: {usuario.get('name')} ({usuario.get('email')})",
            "usuario": usuario,
            "sandbox": is_sandbox_mode()
        }
    except requests.exceptions.RequestException as e:
        return {"sucesso": False, "mensagem": f"Falha na comunicação com a API Autentique: {str(e)}"}


def criar_documento_contrato(aluno_id: int, sandbox: Optional[bool] = None) -> Dict[str, Any]:
    """
    Gera o PDF oficial do contrato do aluno e envia para assinatura via Autentique.
    Signatários configurados:
    1. Natália de Carvalho Garufe (Studio Shanti)
    2. Aluno (com telefone WhatsApp e e-mail se houver)
    """
    api_token = obter_token_autentique()
    if not api_token:
        raise ValueError("Token da API Autentique não configurado. Insira o token na aba Ajustes.")

    aluno = db.obter_aluno(aluno_id)
    if not aluno:
        raise ValueError(f"Aluno {aluno_id} não encontrado no banco de dados.")

    configs = db.obter_configuracoes()
    modo_sandbox = is_sandbox_mode() if sandbox is None else bool(sandbox)

    # 1. Gerar PDF oficial com cláusulas 1 a 13 rigorosamente congeladas
    pdf_buffer = contract_service.gerar_pdf_contrato(aluno_id)
    pdf_bytes = pdf_buffer.getvalue()
    if not pdf_bytes or len(pdf_bytes) < 100:
        raise ValueError("Erro ao gerar PDF do contrato.")

    # 2. Montar signatários
    nome_studio = configs.get("nome_studio", "Studio Shanti")
    email_natalia = configs.get("email_natalia", "nataliagarufeyoga@gmail.com")
    tel_natalia = configs.get("telefone_natalia", "32999999999")
    tel_natalia_e164 = formatar_telefone_e164(tel_natalia)

    signatario_natalia: Dict[str, Any] = {
        "name": "Natalia de Carvalho Garufe",
        "action": "SIGN",
        "delivery_method": "DELIVERY_METHOD_LINK"
    }
    # Autentique v2: Apenas UM meio de contato permitido por signatário (email OU phone, nunca ambos)
    if email_natalia and "@" in email_natalia:
        signatario_natalia["email"] = email_natalia.strip()
    elif tel_natalia_e164:
        signatario_natalia["phone"] = tel_natalia_e164

    # Signatário 2: Aluno
    nome_aluno = (aluno.get("nome") or "Aluno").strip()
    email_aluno = (aluno.get("email") or "").strip()
    tel_aluno_e164 = formatar_telefone_e164(aluno.get("telefone", ""))

    signatario_aluno: Dict[str, Any] = {
        "name": nome_aluno,
        "action": "SIGN",
        "delivery_method": "DELIVERY_METHOD_LINK"
    }
    # Autentique v2: Apenas UM meio de contato permitido por signatário (email OU phone, nunca ambos)
    if email_aluno and "@" in email_aluno:
        signatario_aluno["email"] = email_aluno
    elif tel_aluno_e164:
        signatario_aluno["phone"] = tel_aluno_e164

    signers_list = [signatario_natalia, signatario_aluno]

    # 3. Montar query GraphQL multipart (especificação Autentique v2)
    doc_name = f"Contrato de Prestação de Serviços - {nome_aluno} - {nome_studio}"
    sandbox_literal = "true" if modo_sandbox else "false"

    mutation = f"""
    mutation CreateDocumentMutation($document: DocumentInput!, $signers: [SignerInput!]!, $file: Upload!) {{
      createDocument(sandbox: {sandbox_literal}, document: $document, signers: $signers, file: $file) {{
        id
        name
        refusable
        sortable
        created_at
        signatures {{
          public_id
          name
          email
          action {{
            name
          }}
          link {{
            short_link
          }}
          user {{
            id
            name
            email
          }}
        }}
      }}
    }}
    """

    operations = {
        "query": mutation,
        "variables": {
            "document": {
                "name": doc_name,
                "message": f"Olá! Este é o seu Contrato de Prestação de Serviços com o {nome_studio}. Por favor, assine digitalmente.",
                "whatsapp_template": "STANDARD"
            },
            "signers": signers_list,
            "file": None
        }
    }

    map_payload = {
        "0": ["variables.file"]
    }

    payload = {
        "operations": json.dumps(operations, ensure_ascii=False),
        "map": json.dumps(map_payload)
    }

    files = {
        "0": (f"Contrato_{aluno_id}.pdf", pdf_bytes, "application/pdf")
    }

    headers = {
        "Authorization": f"Bearer {api_token}"
    }

    logger.info(f"Disparando contrato para Autentique (Aluno ID {aluno_id}, Sandbox: {modo_sandbox})")
    res = requests.post(AUTENTIQUE_GRAPHQL_URL, headers=headers, data=payload, files=files, timeout=40)

    if res.status_code == 401:
        logger.error(f"Erro 401 no Autentique: Token inválido ou não autorizado.")
        raise ValueError(
            "Token da API do Autentique não configurado ou inválido (HTTP 401). "
            "Por favor, acesse o menu 'Ajustes' (ícone de engrenagem no topo) "
            "e insira o Token gerado em painel.autentique.com.br."
        )
    elif res.status_code != 200:
        logger.error(f"Erro HTTP {res.status_code} na resposta do Autentique: {res.text}")
        raise RuntimeError(f"Falha na API Autentique (HTTP {res.status_code}): {res.text}")

    resp_json = res.json()
    if "errors" in resp_json and resp_json["errors"]:
        err = resp_json["errors"][0]
        msg = err.get("message", "Erro retornado pelo Autentique")
        ext = err.get("extensions", {})
        if "validation" in ext and isinstance(ext["validation"], dict):
            detalhes = []
            for campo, msgs in ext["validation"].items():
                detalhes.append(f"{campo}: {', '.join(msgs) if isinstance(msgs, list) else msgs}")
            msg = f"Validação Autentique: {'; '.join(detalhes)}"
        elif "detail" in ext:
            msg = f"Autentique: {ext['detail']}"
        logger.error(f"Erro GraphQL Autentique: {resp_json['errors']}")
        raise RuntimeError(f"Falha no Autentique: {msg}")

    doc_data = resp_json.get("data", {}).get("createDocument", {})
    doc_id = doc_data.get("id")
    signatures = doc_data.get("signatures", [])

    # Extrair links curtos de assinatura
    link_aluno = ""
    link_natalia = ""
    for sig in signatures:
        sig_name = (sig.get("name") or "").lower()
        sig_link = (sig.get("link") or {}).get("short_link") or ""
        if "natalia" in sig_name:
            link_natalia = sig_link
        elif sig_name:
            link_aluno = sig_link

    # Fallback se não distinguiu por nome
    signatarios_reais = [s for s in signatures if s.get("action")]
    if not link_natalia and len(signatarios_reais) > 0:
        link_natalia = (signatarios_reais[0].get("link") or {}).get("short_link") or ""
    if not link_aluno and len(signatarios_reais) > 1:
        link_aluno = (signatarios_reais[1].get("link") or {}).get("short_link") or ""

    # 4. Gravar no banco de dados SQLite
    db.registrar_disparo_autentique(
        aluno_id=aluno_id,
        doc_id=doc_id,
        link_aluno=link_aluno,
        link_natalia=link_natalia,
        sandbox=modo_sandbox
    )

    return {
        "sucesso": True,
        "document_id": doc_id,
        "nome_documento": doc_name,
        "sandbox": modo_sandbox,
        "link_aluno": link_aluno,
        "link_natalia": link_natalia,
        "signers": signatures,
        "mensagem": f"Contrato enviado com sucesso para assinatura no Autentique! ({'Modo Sandbox' if modo_sandbox else 'Produção'})"
    }


def consultar_status_documento(doc_id: str) -> Dict[str, Any]:
    """
    Consulta em tempo real o status de um documento no Autentique.
    Retorna se ambas as partes já assinaram e os links para download dos arquivos.
    """
    api_token = obter_token_autentique()
    if not api_token:
        raise ValueError("Token da API Autentique não configurado.")

    query = """
    query GetDoc($id: String!) {
      document(id: $id) {
        id
        name
        refusable
        sortable
        created_at
        files {
          original
          signed
        }
        signatures {
          public_id
          name
          email
          action {
            name
          }
          link {
            short_link
          }
          signed {
            created_at
          }
          rejected {
            created_at
          }
          viewed {
            created_at
          }
        }
      }
    }
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    res = requests.post(
        AUTENTIQUE_GRAPHQL_URL,
        headers=headers,
        json={"query": query, "variables": {"id": doc_id}},
        timeout=20
    )
    if res.status_code != 200:
        raise RuntimeError(f"Erro HTTP {res.status_code} ao consultar documento: {res.text}")

    resp_json = res.json()
    if "errors" in resp_json and resp_json["errors"]:
        raise RuntimeError(f"Erro Autentique: {resp_json['errors'][0].get('message')}")

    doc = resp_json.get("data", {}).get("document")
    if not doc:
        return {"encontrado": False, "mensagem": "Documento não encontrado no Autentique."}

    signatures = doc.get("signatures", [])
    total_signers = len(signatures)
    assinados = sum(1 for s in signatures if s.get("signed") is not None)
    rejeitados = sum(1 for s in signatures if s.get("rejected") is not None)

    totalmente_assinado = (total_signers > 0 and assinados == total_signers)
    url_assinado = doc.get("files", {}).get("signed")

    return {
        "encontrado": True,
        "document_id": doc_id,
        "nome": doc.get("name"),
        "total_signatarios": total_signers,
        "total_assinados": assinados,
        "total_rejeitados": rejeitados,
        "finalizado": totalmente_assinado,
        "url_assinado": url_assinado,
        "signatures": signatures
    }


def baixar_e_salvar_contrato_assinado(aluno_id: int, doc_id: str, url_assinado: str) -> str:
    """
    Baixa o arquivo PDF final assinado do Autentique, salva na pasta local
    'uploads/contratos/' e atualiza o aluno para 'em_dia' com vigência de 1 ano.
    """
    api_token = obter_token_autentique()
    headers = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    res = requests.get(url_assinado, headers=headers, timeout=30)
    if res.status_code != 200:
        raise RuntimeError(f"Falha ao baixar PDF assinado da URL {url_assinado}: HTTP {res.status_code}")

    conteudo_pdf = res.content
    if len(conteudo_pdf) < 500:
        raise ValueError("Arquivo baixado é inválido ou muito pequeno.")

    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "contratos")
    os.makedirs(upload_dir, exist_ok=True)

    nome_arquivo = f"contrato_autentique_{aluno_id}_{doc_id[:8]}.pdf"
    destino_completo = os.path.join(upload_dir, nome_arquivo)

    with open(destino_completo, "wb") as f:
        f.write(conteudo_pdf)

    caminho_relativo = f"uploads/contratos/{nome_arquivo}"

    # Atualiza banco de dados com documento assinado e vigência de 1 ano
    db.concluir_contrato_autentique(aluno_id=aluno_id, doc_id=doc_id, caminho_arquivo=caminho_relativo)

    logger.info(f"Contrato Autentique {doc_id} concluído e salvo em {caminho_relativo} para o aluno {aluno_id}")
    return caminho_relativo

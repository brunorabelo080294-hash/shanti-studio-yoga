"""
Módulo de Backup Automático Diário do Banco de Dados para o Google Drive.
Shanti Studio Yoga.

Responsabilidades:
1. Exportar dump completo do banco de dados (PostgreSQL/SQLite) em formato .sql universal.
2. Validar integridade e abertura do arquivo gerado.
3. Enviar o dump para pasta dedicada no Google Drive via Google Service Account (100% gratuito).
4. Excluir automaticamente backups com mais de 30 dias (política de retenção).
5. Registrar status e erros no painel de Saúde do Sistema (logs_diagnostico).
6. Disparar alertas visuais e via WhatsApp caso ocorra qualquer falha.
7. Agendador em segundo plano rodando diariamente às 03:00 (Horário de Brasília).
"""

import os
import sys
import json
import base64
import hashlib
import datetime
import time
import asyncio
import urllib.parse
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple

import requests
from google.oauth2 import service_account
import google.auth.transport.requests

import backend.database as db

# Configurações e Diretórios
FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")
HORA_BACKUP_DIARIO = 3  # 03:00 da manhã no Horário de Brasília
DIAS_RETENCAO_PADRAO = 30
DIR_BASE = os.path.dirname(os.path.abspath(__file__))
DIR_BACKUPS_LOCAL = os.path.join(DIR_BASE, "backups")

os.makedirs(DIR_BACKUPS_LOCAL, exist_ok=True)

# Estado em memória do último backup
_ULTIMO_STATUS_BACKUP: Dict[str, Any] = {
    "sucesso": None,
    "timestamp": None,
    "arquivo": None,
    "tamanho_bytes": 0,
    "tamanho_formatado": "--",
    "total_tabelas": 0,
    "total_registros": 0,
    "origem": None,
    "drive_conectado": False,
    "drive_file_id": None,
    "drive_expurgados": 0,
    "mensagem": "Nenhum backup executado nesta sessão do servidor.",
    "erro": None,
    "proxima_execucao": None
}

_DATA_ULTIMO_BACKUP_RODADO: Optional[str] = None


def obter_agora_sp() -> datetime.datetime:
    """Retorna datetime atual com fuso horário oficial de Brasília (America/Sao_Paulo)."""
    return datetime.datetime.now(FUSO_BRASILIA)


def calcular_proxima_execucao_sp() -> str:
    """Calcula a data e hora da próxima execução às 03:00 da manhã no fuso de Brasília."""
    agora = obter_agora_sp()
    alvo = agora.replace(hour=HORA_BACKUP_DIARIO, minute=0, second=0, microsecond=0)
    if agora >= alvo:
        alvo += datetime.timedelta(days=1)
    return alvo.strftime("%Y-%m-%d %H:%M:%S (Horário de Brasília)")


# =============================================================================
# 1. GERADOR E VALIDADOR DE DUMP SQL UNIVERSAL
# =============================================================================

def gerar_dump_sql(caminho_saida: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Gera exportação completa (.sql) de todas as tabelas e registros do banco ativo.
    Funciona tanto com PostgreSQL (Supabase) quanto com SQLite, sem dependências
    de binários externos (como pg_dump).
    """
    agora = obter_agora_sp()
    timestamp_str = agora.strftime("%Y-%m-%d_%H-%M-%S")
    nome_arquivo = f"backup-shanti-{timestamp_str}.sql"

    if not caminho_saida:
        caminho_saida = os.path.join(DIR_BACKUPS_LOCAL, nome_arquivo)

    conn = db.get_connection()
    cur = conn.cursor()

    is_postgres = bool(db.DATABASE_URL)
    tipo_banco = "PostgreSQL (Supabase)" if is_postgres else "SQLite Local"

    # Listar tabelas públicas
    if is_postgres:
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tabelas = [r[0] if isinstance(r, (list, tuple)) else r["table_name"] for r in cur.fetchall()]
    else:
        cur.execute("""
            SELECT name 
            FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%' 
            ORDER BY name;
        """)
        tabelas = [r[0] if isinstance(r, (list, tuple)) else r["name"] for r in cur.fetchall()]

    linhas: List[str] = []
    linhas.append("-- =============================================================================")
    linhas.append("-- SHANTI STUDIO DE YOGA - BACKUP AUTOMATICO DO BANCO DE DADOS")
    linhas.append(f"-- Gerado em: {agora.strftime('%Y-%m-%d %H:%M:%S')} (Horário de Brasília)")
    linhas.append(f"-- Banco de Origem: {tipo_banco}")
    linhas.append(f"-- Total de Tabelas: {len(tabelas)}")
    linhas.append("-- Arquivo autossuficiente compatível com restauração SQL padrão.")
    linhas.append("-- =============================================================================\n")
    linhas.append("BEGIN;\n")

    total_registros = 0
    tabelas_metadados = {}

    for tabela in tabelas:
        cur.execute(f'SELECT * FROM "{tabela}"' if is_postgres else f"SELECT * FROM `{tabela}`")
        rows = cur.fetchall()
        col_names = [desc[0] for desc in cur.description] if cur.description else []
        qtd_tabela = len(rows)
        total_registros += qtd_tabela
        tabelas_metadados[tabela] = qtd_tabela

        linhas.append(f"-- -----------------------------------------------------------------------------")
        linhas.append(f"-- Tabela: {tabela} ({qtd_tabela} registros)")
        linhas.append(f"-- -----------------------------------------------------------------------------")

        if not rows:
            linhas.append(f"-- Tabela '{tabela}' está vazia no momento deste backup.\n")
            continue

        for row in rows:
            valores = []
            for col in col_names:
                v = row[col] if isinstance(row, dict) else row[col_names.index(col)]
                if v is None:
                    valores.append("NULL")
                elif isinstance(v, bool):
                    valores.append("TRUE" if v else "FALSE")
                elif isinstance(v, (int, float)):
                    valores.append(str(v))
                elif isinstance(v, (datetime.date, datetime.datetime)):
                    valores.append(f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'")
                elif isinstance(v, (dict, list)):
                    s_json = json.dumps(v, ensure_ascii=False).replace("'", "''")
                    valores.append(f"'{s_json}'")
                else:
                    s_str = str(v).replace("'", "''")
                    valores.append(f"'{s_str}'")

            cols_quoted = ", ".join([f'"{c}"' for c in col_names])
            vals_joined = ", ".join(valores)
            linhas.append(f'INSERT INTO "{tabela}" ({cols_quoted}) VALUES ({vals_joined});')

        linhas.append("")

    linhas.append("COMMIT;\n")
    linhas.append("-- =============================================================================")
    linhas.append(f"-- FIM DO BACKUP - TOTAL DE REGISTROS EXPORTADOS: {total_registros}")
    linhas.append("-- =============================================================================\n")

    conn.close()

    conteudo_sql = "\n".join(linhas)
    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write(conteudo_sql)

    tamanho_bytes = os.path.getsize(caminho_saida)
    sha256 = hashlib.sha256(conteudo_sql.encode("utf-8")).hexdigest()

    metadados = {
        "arquivo": os.path.basename(caminho_saida),
        "caminho_completo": caminho_saida,
        "tamanho_bytes": tamanho_bytes,
        "tamanho_kb": round(tamanho_bytes / 1024, 2),
        "sha256": sha256,
        "total_tabelas": len(tabelas),
        "total_registros": total_registros,
        "tabelas": tabelas_metadados,
        "timestamp_sp": agora.strftime("%Y-%m-%d %H:%M:%S")
    }

    return caminho_saida, metadados


def validar_arquivo_dump(caminho_arquivo: str) -> Dict[str, Any]:
    """
    Inspeciona e valida o arquivo de backup gerado:
    Garante que existe, abre como UTF-8, possui transação BEGIN/COMMIT e registros válidos.
    """
    if not os.path.exists(caminho_arquivo):
        return {"valido": False, "erro": "Arquivo de backup não encontrado no disco."}

    tamanho = os.path.getsize(caminho_arquivo)
    if tamanho == 0:
        return {"valido": False, "erro": "Arquivo de backup gerado está vazio (0 bytes)."}

    try:
        with open(caminho_arquivo, "r", encoding="utf-8") as f:
            conteudo = f.read()

        tem_begin = "BEGIN;" in conteudo
        tem_commit = "COMMIT;" in conteudo
        tem_shanti = "SHANTI STUDIO DE YOGA" in conteudo
        qtd_inserts = conteudo.count("INSERT INTO")

        if not (tem_begin and tem_commit and tem_shanti):
            return {
                "valido": False,
                "erro": "O arquivo gerado não contém os marcadores estruturais obrigatórios (BEGIN, COMMIT)."
            }

        return {
            "valido": True,
            "tamanho_bytes": tamanho,
            "total_inserts": qtd_inserts,
            "tem_begin": tem_begin,
            "tem_commit": tem_commit
        }
    except UnicodeDecodeError:
        return {"valido": False, "erro": "Erro de codificação UTF-8 ao ler o arquivo de backup."}
    except Exception as e:
        return {"valido": False, "erro": f"Erro inesperado ao validar arquivo: {str(e)}"}


# =============================================================================
# 2. CLIENTE GOOGLE DRIVE VIA SERVICE ACCOUNT (100% GRATUITO)
# =============================================================================

class GoogleDriveBackupManager:
    """
    Gerencia autenticação e operações no Google Drive usando a REST API v3.
    Requer apenas uma Conta de Serviço (gratuita) com pasta compartilhada.
    """

    def __init__(self):
        self.folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        self.service_account_json_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        self.service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        self._token: Optional[str] = None
        self._token_expiry: float = 0
        self._service_email: Optional[str] = None

    def esta_configurado(self) -> bool:
        """Verifica se as variáveis mínimas do Google Drive estão configuradas."""
        tem_credencial = bool(self.service_account_json_raw or (self.service_account_file and os.path.exists(self.service_account_file)))
        tem_pasta = bool(self.folder_id)
        return tem_credencial and tem_pasta

    def obter_status_resumido(self) -> Dict[str, Any]:
        """Retorna status sem jamais expor dados confidenciais da credencial."""
        configurado = self.esta_configurado()
        email_mascarado = None
        if configurado and self._service_email:
            partes = self._service_email.split("@")
            if len(partes) == 2:
                prefixo = partes[0]
                mascara = prefixo[:3] + "..." + prefixo[-2:] if len(prefixo) > 5 else "***"
                email_mascarado = f"{mascara}@{partes[1]}"

        pasta_mascarada = None
        if self.folder_id:
            pasta_mascarada = self.folder_id[:4] + "..." + self.folder_id[-4:] if len(self.folder_id) > 8 else "***"

        return {
            "configurado": configurado,
            "pasta_id": pasta_mascarada,
            "email_servico": email_mascarado,
            "modo": "service_account_v3"
        }

    def _obter_credenciais_dict(self) -> Dict[str, Any]:
        """Carrega e decodifica a credencial da conta de serviço."""
        if self.service_account_json_raw:
            raw = self.service_account_json_raw
            # Suporte para string em base64
            if raw.startswith("ey") or not raw.strip().startswith("{"):
                try:
                    raw = base64.b64decode(raw).decode("utf-8")
                except Exception:
                    pass
            return json.loads(raw)
        elif self.service_account_file and os.path.exists(self.service_account_file):
            with open(self.service_account_file, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            raise ValueError("Nenhuma credencial de conta de serviço Google fornecida.")

    def obter_token_acesso(self) -> str:
        """Obtém ou renova token de acesso OAuth2 usando a Conta de Serviço."""
        agora = time.time()
        if self._token and agora < (self._token_expiry - 60):
            return self._token

        cred_info = self._obter_credenciais_dict()
        self._service_email = cred_info.get("client_email")

        credentials = service_account.Credentials.from_service_account_info(
            cred_info,
            scopes=["https://www.googleapis.com/auth/drive"]
        )

        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)

        self._token = credentials.token
        self._token_expiry = agora + 3500
        return self._token

    def fazer_upload(self, caminho_arquivo: str, nome_arquivo: str) -> Dict[str, Any]:
        """
        Envia o arquivo para a pasta do Google Drive via multipart upload.
        """
        if not self.esta_configurado():
            raise RuntimeError("Google Drive não está configurado.")

        token = self.obter_token_acesso()
        url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"

        metadata = {
            "name": nome_arquivo,
            "parents": [self.folder_id],
            "description": f"Backup automático Shanti Studio de Yoga - {obter_agora_sp().strftime('%Y-%m-%d %H:%M:%S')}"
        }

        with open(caminho_arquivo, "rb") as f:
            conteudo_bytes = f.read()

        boundary = "===============ShantiBackupBoundary=="
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}"
        }

        body = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: application/sql\r\n\r\n"
        ).encode("utf-8") + conteudo_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        res = requests.post(url, headers=headers, data=body, timeout=60)
        if res.status_code not in (200, 201):
            raise RuntimeError(f"Falha no upload para o Google Drive ({res.status_code}): {res.text}")

        dados_criados = res.json()
        return {
            "sucesso": True,
            "file_id": dados_criados.get("id"),
            "nome": dados_criados.get("name"),
            "tamanho": len(conteudo_bytes)
        }

    def listar_backups(self) -> List[Dict[str, Any]]:
        """
        Lista todos os backups existentes na pasta do Google Drive ordenados do mais recente ao mais antigo.
        """
        if not self.esta_configurado():
            return []

        token = self.obter_token_acesso()
        q = f"'{self.folder_id}' in parents and trashed = false and name contains 'backup-shanti'"
        url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(q)}&orderBy=createdTime desc&fields=files(id, name, createdTime, size)"

        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(url, headers=headers, timeout=30)
        if res.status_code != 200:
            raise RuntimeError(f"Erro ao listar arquivos do Google Drive ({res.status_code}): {res.text}")

        arquivos = res.json().get("files", [])
        return arquivos

    def expurgar_backups_antigos(self, dias_retencao: int = DIAS_RETENCAO_PADRAO) -> List[str]:
        """
        Remove backups com mais de X dias no Google Drive e no armazenamento local.
        Garante que o histórico dos últimos 30 dias seja mantido, evitando acúmulo infinito.
        """
        removidos: List[str] = []
        agora = obter_agora_sp()
        limite_data = agora - datetime.timedelta(days=dias_retencao)

        # 1. Expurgar no Google Drive se configurado
        if self.esta_configurado():
            try:
                token = self.obter_token_acesso()
                arquivos = self.listar_backups()
                for arq in arquivos:
                    nome = arq.get("name", "")
                    created_str = arq.get("createdTime")
                    deve_deletar = False

                    if created_str:
                        try:
                            dt_criacao = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                            if dt_criacao < limite_data:
                                deve_deletar = True
                        except Exception:
                            pass

                    # Fallback pelo nome do arquivo: backup-shanti-YYYY-MM-DD_...
                    if not deve_deletar and nome.startswith("backup-shanti-"):
                        try:
                            partes = nome.replace("backup-shanti-", "").split("_")[0]
                            dt_nome = datetime.datetime.strptime(partes, "%Y-%m-%d").replace(tzinfo=FUSO_BRASILIA)
                            if dt_nome < limite_data:
                                deve_deletar = True
                        except Exception:
                            pass

                    if deve_deletar:
                        fid = arq.get("id")
                        del_url = f"https://www.googleapis.com/drive/v3/files/{fid}"
                        del_res = requests.delete(del_url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
                        if del_res.status_code in (200, 204):
                            removidos.append(f"drive:{nome}")
            except Exception as e:
                print(f"Aviso ao expurgar arquivos no Google Drive: {e}")

        # 2. Expurgar também no diretório local
        if os.path.exists(DIR_BACKUPS_LOCAL):
            for fname in os.listdir(DIR_BACKUPS_LOCAL):
                if not fname.startswith("backup-shanti-") or not fname.endswith(".sql"):
                    continue
                caminho = os.path.join(DIR_BACKUPS_LOCAL, fname)
                try:
                    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(caminho), tz=FUSO_BRASILIA)
                    if mtime < limite_data:
                        os.remove(caminho)
                        removidos.append(f"local:{fname}")
                except Exception as e:
                    print(f"Aviso ao expurgar arquivo local {fname}: {e}")

        return removidos

    def baixar_backup(self, file_id: str, caminho_destino: str) -> bool:
        """Baixa um arquivo do Google Drive para conferência de conteúdo."""
        if not self.esta_configurado():
            return False

        token = self.obter_token_acesso()
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(url, headers=headers, stream=True, timeout=60)
        if res.status_code == 200:
            with open(caminho_destino, "wb") as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        return False


# Instância global do gerenciador Google Drive
gdrive_manager = GoogleDriveBackupManager()


# =============================================================================
# 3. SISTEMA DE ALERTA DE FALHA
# =============================================================================

def enviar_alerta_falha(erro_msg: str, origem: str = "rotina_diaria") -> str:
    """
    Dispara notificação de falha:
    1. Registra no banco de dados (logs_diagnostico).
    2. Se configurado WHATSAPP_ALERT_WEBHOOK_URL, envia webhook para WhatsApp.
    """
    agora_str = obter_agora_sp().strftime("%d/%m/%Y às %H:%M")
    msg_alerta = (
        f"🚨 *ALERTA SHANTI STUDIO: Falha no Backup do Banco de Dados*\n\n"
        f"• Data/Hora: {agora_str}\n"
        f"• Origem: {origem}\n"
        f"• Erro: {erro_msg}\n\n"
        f"⚠️ Os dados continuam operando normalmente, mas a rotina de segurança diária precisa de atenção técnica."
    )

    # Webhook opcional
    webhook_url = os.getenv("WHATSAPP_ALERT_WEBHOOK_URL")
    if webhook_url:
        try:
            payload = {
                "mensagem": msg_alerta,
                "tipo": "alerta_backup",
                "timestamp": agora_str
            }
            requests.post(webhook_url, json=payload, timeout=10)
        except Exception as e:
            print(f"Erro ao enviar webhook de alerta do backup: {e}")

    return msg_alerta


# =============================================================================
# 4. ORQUESTRADOR DA ROTINA DE BACKUP
# =============================================================================

def executar_rotina_backup(origem: str = "agendador_automatico") -> Dict[str, Any]:
    """
    Executa a rotina completa de backup diário:
    1. Gera dump .sql completo das 14 tabelas.
    2. Valida integridade do arquivo gerado.
    3. Faz upload para o Google Drive se configurado.
    4. Aplica expurgo de backups com > 30 dias.
    5. Registra sucesso ou falha em logs_diagnostico.
    """
    global _ULTIMO_STATUS_BACKUP, _DATA_ULTIMO_BACKUP_RODADO
    t0 = time.time()
    agora = obter_agora_sp()
    hoje_str = agora.strftime("%Y-%m-%d")

    try:
        # 1. Geração do Dump
        caminho_sql, meta = gerar_dump_sql()

        # 2. Validação do Dump
        val = validar_arquivo_dump(caminho_sql)
        if not val["valido"]:
            raise RuntimeError(f"Arquivo de backup inválido: {val.get('erro')}")

        # 3. Upload para Google Drive (se configurado)
        drive_status = gdrive_manager.obter_status_resumido()
        drive_ok = False
        drive_fid = None
        expurgados = []

        if drive_status["configurado"]:
            upload_res = gdrive_manager.fazer_upload(caminho_sql, meta["arquivo"])
            drive_ok = upload_res["sucesso"]
            drive_fid = upload_res.get("file_id")
            expurgados = gdrive_manager.expurgar_backups_antigos(DIAS_RETENCAO_PADRAO)
            msg_drive = f"Enviado para o Google Drive (ID: {drive_fid}). Expurgados: {len(expurgados)} antigos."
        else:
            # Expurgar arquivos locais mesmo sem Drive
            expurgados = gdrive_manager.expurgar_backups_antigos(DIAS_RETENCAO_PADRAO)
            msg_drive = "Cópia local salva com sucesso (Google Drive aguardando configuração de credenciais no servidor)."

        tempo_total_ms = int((time.time() - t0) * 1000)

        # 4. Registrar em logs_diagnostico (Painel de Saúde)
        detalhes_log = (
            f"Arquivo: {meta['arquivo']} ({meta['tamanho_kb']} KB). "
            f"Tabelas: {meta['total_tabelas']}, Registros: {meta['total_registros']}. "
            f"{msg_drive}"
        )
        db.registrar_log_diagnostico(
            tipo_evento="backup_automatico",
            status_servidor="ok",
            status_ia="nao_aplicavel",
            tempo_servidor_ms=tempo_total_ms,
            sucesso=1,
            detalhes=detalhes_log
        )

        _DATA_ULTIMO_BACKUP_RODADO = hoje_str
        _ULTIMO_STATUS_BACKUP = {
            "sucesso": True,
            "timestamp": agora.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp_formatado": agora.strftime("%d/%m/%Y às %H:%M"),
            "arquivo": meta["arquivo"],
            "tamanho_bytes": meta["tamanho_bytes"],
            "tamanho_formatado": f"{meta['tamanho_kb']} KB",
            "total_tabelas": meta["total_tabelas"],
            "total_registros": meta["total_registros"],
            "origem": origem,
            "drive_conectado": drive_ok,
            "drive_file_id": drive_fid,
            "drive_expurgados": len(expurgados),
            "mensagem": f"Backup concluído com sucesso em {tempo_total_ms}ms! {msg_drive}",
            "erro": None,
            "proxima_execucao": calcular_proxima_execucao_sp()
        }

        return _ULTIMO_STATUS_BACKUP

    except Exception as e:
        tempo_total_ms = int((time.time() - t0) * 1000)
        erro_str = str(e)

        # Disparar alerta e registrar falha
        alerta_msg = enviar_alerta_falha(erro_str, origem=origem)

        db.registrar_log_diagnostico(
            tipo_evento="backup_automatico",
            status_servidor="erro",
            status_ia="nao_aplicavel",
            tempo_servidor_ms=tempo_total_ms,
            sucesso=0,
            mensagem_erro=erro_str,
            detalhes=f"Falha na rotina de backup iniciada por '{origem}'."
        )

        _ULTIMO_STATUS_BACKUP = {
            "sucesso": False,
            "timestamp": agora.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp_formatado": agora.strftime("%d/%m/%Y às %H:%M"),
            "arquivo": None,
            "tamanho_bytes": 0,
            "tamanho_formatado": "--",
            "total_tabelas": 0,
            "total_registros": 0,
            "origem": origem,
            "drive_conectado": False,
            "drive_file_id": None,
            "drive_expurgados": 0,
            "mensagem": f"Falha no backup: {erro_str}",
            "erro": erro_str,
            "alerta_whatsapp_texto": alerta_msg,
            "proxima_execucao": calcular_proxima_execucao_sp()
        }

        return _ULTIMO_STATUS_BACKUP


def obter_status_backup() -> Dict[str, Any]:
    """Retorna status atualizado para a API e o painel de Saúde do Sistema."""
    global _ULTIMO_STATUS_BACKUP
    status_drive = gdrive_manager.obter_status_resumido()

    # Se ainda não rodou nesta sessão, tentar ler do banco o último log de backup
    if _ULTIMO_STATUS_BACKUP.get("timestamp") is None:
        try:
            logs = db.obter_ultimos_logs_diagnostico(limite=50)
            logs_backup = [l for l in logs if l.get("tipo_evento") == "backup_automatico"]
            if logs_backup:
                ultimo_log = logs_backup[0]
                _ULTIMO_STATUS_BACKUP["sucesso"] = bool(ultimo_log.get("sucesso"))
                _ULTIMO_STATUS_BACKUP["timestamp"] = ultimo_log.get("timestamp")
                _ULTIMO_STATUS_BACKUP["mensagem"] = ultimo_log.get("detalhes") or "Último backup recuperado dos logs de diagnóstico."
                _ULTIMO_STATUS_BACKUP["erro"] = ultimo_log.get("mensagem_erro")
        except Exception:
            pass

    resultado = dict(_ULTIMO_STATUS_BACKUP)
    resultado["drive"] = status_drive
    resultado["proxima_execucao"] = calcular_proxima_execucao_sp()
    resultado["horario_agendado"] = f"{HORA_BACKUP_DIARIO:02d}:00 (Brasília)"
    resultado["retencao_dias"] = DIAS_RETENCAO_PADRAO

    # Lista de arquivos locais disponíveis
    arquivos_locais = []
    if os.path.exists(DIR_BACKUPS_LOCAL):
        for f in sorted(os.listdir(DIR_BACKUPS_LOCAL), reverse=True):
            if f.startswith("backup-shanti-") and f.endswith(".sql"):
                p = os.path.join(DIR_BACKUPS_LOCAL, f)
                arquivos_locais.append({
                    "nome": f,
                    "tamanho_kb": round(os.path.getsize(p) / 1024, 2),
                    "modificado": datetime.datetime.fromtimestamp(os.path.getmtime(p), tz=FUSO_BRASILIA).strftime("%Y-%m-%d %H:%M:%S")
                })
    resultado["backups_locais"] = arquivos_locais[:10]
    resultado["total_backups_locais"] = len(arquivos_locais)

    return resultado


def obter_caminho_ultimo_backup() -> Optional[str]:
    """Retorna o caminho do arquivo de backup .sql mais recente salvo localmente."""
    if not os.path.exists(DIR_BACKUPS_LOCAL):
        return None
    arquivos = [f for f in os.listdir(DIR_BACKUPS_LOCAL) if f.startswith("backup-shanti-") and f.endswith(".sql")]
    if not arquivos:
        return None
    arquivos.sort(reverse=True)
    return os.path.join(DIR_BACKUPS_LOCAL, arquivos[0])


# =============================================================================
# 5. AGENDADOR EM SEGUNDO PLANO (CRON ASSÍNCRONO DIÁRIO)
# =============================================================================

async def loop_agendador_backup():
    """
    Loop assíncrono executado em segundo plano pelo FastAPI.
    Verifica a cada 60 segundos se o horário atual de Brasília atingiu 03:00
    e executa a rotina uma única vez por dia.
    """
    global _DATA_ULTIMO_BACKUP_RODADO
    print(f"🕒 Agendador de Backup Diário iniciado: configurado para rodar diariamente às {HORA_BACKUP_DIARIO:02d}:00 (Brasília).")

    while True:
        try:
            agora = obter_agora_sp()
            hoje_str = agora.strftime("%Y-%m-%d")

            # Dispara se for 03:00 ou posterior e ainda não rodou hoje
            if agora.hour >= HORA_BACKUP_DIARIO and _DATA_ULTIMO_BACKUP_RODADO != hoje_str:
                print(f"🚀 Disparando backup diário automático para o dia {hoje_str}...")
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, executar_rotina_backup, "agendador_automatico_03h")

            await asyncio.sleep(60)
        except asyncio.CancelledError:
            print("Agendador de Backup Diário cancelado.")
            break
        except Exception as e:
            print(f"Erro no loop do agendador de backup: {e}")
            await asyncio.sleep(60)


def iniciar_agendador_background(app):
    """Inicia a tarefa do agendador no ciclo de vida do FastAPI."""
    @app.on_event("startup")
    async def startup_backup_scheduler():
        asyncio.create_task(loop_agendador_backup())


# =============================================================================
# 6. PONTO DE ENTRADA CLI (Para testes manuais ou Cron do Render)
# =============================================================================

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("\n--- SHANTI STUDIO YOGA | ROTINA DE BACKUP AUTOMATICO ---")
    print(f"Horario de Brasilia: {obter_agora_sp().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Diretorio local: {DIR_BACKUPS_LOCAL}")
    status = gdrive_manager.obter_status_resumido()
    print(f"Google Drive configurado: {'SIM' if status['configurado'] else 'NAO'}")

    res = executar_rotina_backup(origem="cli_manual")
    if res["sucesso"]:
        print("\n[SUCESSO] BACKUP CONCLUIDO COM SUCESSO!")
        print(f"* Arquivo: {res['arquivo']} ({res['tamanho_formatado']})")
        print(f"* Tabelas: {res['total_tabelas']}, Registros: {res['total_registros']}")
        print(f"* Drive conectado: {res['drive_conectado']}")
        sys.exit(0)
    else:
        print(f"\n[ERRO] NO BACKUP: {res['erro']}")
        sys.exit(1)

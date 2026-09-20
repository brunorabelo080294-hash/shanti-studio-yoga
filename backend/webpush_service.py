import os
import json
import logging
from typing import Optional, Dict, Any
from pywebpush import webpush, WebPushException
from py_vapid import Vapid

logger = logging.getLogger(__name__)

VAPID_PUBLIC_KEY = os.environ.get(
    "VAPID_PUBLIC_KEY",
    "BPxEPPlvvku_lBLK6ZaSzwRSe_1OjcY0axuRWm9LFglIOSHyVZ0gNe5Gz0WBKS6z3PW5RibFYLZhUmnMsaAEo-Q"
)

VAPID_PRIVATE_KEY_PEM = os.environ.get(
    "VAPID_PRIVATE_KEY",
    "-----BEGIN PRIVATE KEY-----\nMIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg9qW3ZV1M+BgtdMqq\nlA4zXtRY319sIViQm9cjZrshySOhRANCAAT8RDz5b75Lv5QSyumWks8EUnv9To3G\nNGsbkVpvSxYJSDkh8lWdIDXuRs9FgSkus9z1uUYmxWC2YVJpzLGgBKPk\n-----END PRIVATE KEY-----\n"
)

VAPID_CLAIMS = {
    "sub": os.environ.get("VAPID_CLAIM_EMAIL", "mailto:contato@studioshanti.com.br")
}

try:
    VAPID_OBJ = Vapid.from_pem(VAPID_PRIVATE_KEY_PEM.encode("utf-8"))
except Exception as e:
    logger.error(f"Erro ao carregar chave VAPID: {e}")
    VAPID_OBJ = None

def enviar_push_para_subscription(subscription_data: Any, payload: Dict[str, Any]) -> bool:
    """
    Envia uma notificação Web Push para o endpoint da subscription (Google FCM/Mozilla/Apple).
    Funciona mesmo com o aplicativo do aluno totalmente fechado e tela bloqueada.
    """
    if not subscription_data or not VAPID_OBJ:
        return False

    sub_info = subscription_data
    if isinstance(subscription_data, str):
        try:
            sub_info = json.loads(subscription_data)
        except Exception:
            return False

    if not isinstance(sub_info, dict) or "endpoint" not in sub_info:
        return False

    endpoint = str(sub_info.get("endpoint", ""))
    if not endpoint.startswith("http"):
        return False

    try:
        data_str = json.dumps(payload)
        resp = webpush(
            subscription_info=sub_info,
            data=data_str,
            vapid_private_key=VAPID_OBJ,
            vapid_claims=VAPID_CLAIMS,
            ttl=86400
        )
        logger.info(f"Web Push enviado com sucesso ({getattr(resp, 'status_code', 200)}) para {endpoint[:45]}...")
        return True
    except WebPushException as ex:
        logger.warning(f"Falha ao enviar Web Push: {ex}")
        status = getattr(getattr(ex, 'response', None), 'status_code', None)
        if status in (404, 410) or "unsubscribed or expired" in str(ex):
            try:
                from backend import database as db
                db.limpar_device_token_expirado(sub_info)
                logger.info("Token expirado removido automaticamente do banco de dados.")
            except Exception as e_clean:
                logger.error(f"Erro ao remover token expirado: {e_clean}")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado no Web Push: {e}")
        return False


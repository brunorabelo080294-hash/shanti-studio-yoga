"""
Iniciador do Yoga Studio App (PWA + WhatsApp UI + IA).
Inicia o servidor e exibe o endereço para acessar no computador e no celular.
"""
import socket
import sys
import os

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main():
    import uvicorn
    import threading

    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    local_ip = get_local_ip()
    port_http = 8000
    port_https = 8443

    print("=" * 65)
    print("[SHANTI STUDIO DE YOGA] - ASSISTENTE IA & WHATSAPP LUXE")
    print("=" * 65)
    print(f"\n* NO COMPUTADOR (Acesso Direto com Microfone):")
    print(f"   -> http://localhost:{port_http}")
    print(f"\n* NO CELULAR:")
    print(f"   Opcao 1 (Padrao com Gravador Nativo de Voz):")
    print(f"   -> http://{local_ip}:{port_http}")
    print(f"   Opcao 2 (Conexao Segura HTTPS com Microfone em Tempo Real):")
    print(f"   -> https://{local_ip}:{port_https}")
    print("=" * 65)
    print("\nIniciando servidores HTTP e HTTPS... Pressione Ctrl+C para encerrar.\n")

    # Iniciar HTTPS se certificados existirem, ou HTTP diretamente
    if os.path.exists("key.pem") and os.path.exists("cert.pem"):
        threading.Thread(target=lambda: uvicorn.run("backend.app:app", host="0.0.0.0", port=port_http, log_level="warning"), daemon=True).start()
        uvicorn.run("backend.app:app", host="0.0.0.0", port=port_https, ssl_keyfile="key.pem", ssl_certfile="cert.pem", log_level="info")
    else:
        uvicorn.run("backend.app:app", host="0.0.0.0", port=port_http, log_level="info")

if __name__ == "__main__":
    main()

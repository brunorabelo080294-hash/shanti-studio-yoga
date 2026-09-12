"""
Módulo de Inteligência Artificial para o Studio de Yoga.
Suporta Google Gemini API (google-genai) com Function Calling e fallback inteligente.
"""
import os
import re
import json
import datetime
from typing import Dict, Any, List, Optional
import backend.database as db

def get_api_key() -> str:
    # 1. Tentar pegar do banco de dados
    configs = db.obter_configuracoes()
    db_key = configs.get("gemini_api_key", "").strip()
    if db_key:
        return db_key
    # 2. Tentar variável de ambiente
    return os.environ.get("GEMINI_API_KEY", "").strip()

def processar_comando_local(texto: str) -> Dict[str, Any]:
    """
    Motor local de linguagem natural para responder imediatamente
    caso a chave do Gemini ainda não tenha sido configurada.
    """
    texto_lower = texto.lower()

    # 1. Inadimplência / Atraso
    if any(p in texto_lower for p in ["atraso", "atrasada", "atrasadas", "atrasados", "devedor", "inadimplente", "quem deve", "não pagou", "vencid"]):
        inadimplentes = db.obter_inadimplentes()
        if not inadimplentes:
            return {
                "resposta": "🧘 Excelente notícia! Não há nenhum aluno com mensalidade atrasada no momento. Todas as contas estão em dia!",
                "tipo": "inadimplencia",
                "dados": []
            }
        
        nomes = []
        links_whatsapp = db.gerar_mensagens_cobranca(tipo="atrasados")
        resposta = f"📋 *Alunos com mensalidade em atraso:* ({len(inadimplentes)})\n\n"
        
        for idx, al in enumerate(inadimplentes, 1):
            resposta += f"{idx}. *{al['nome']}*\n   • Venceu dia: {al['dia_vencimento']:02d} ({al['dias_atraso']} dias de atraso)\n   • Valor: R$ {al['valor_mensalidade']:.2f}\n   • Plano: {al['plano']}\n   • Telefone: {al['telefone']}\n\n"
        
        resposta += "💡 *Dica:* Você pode tocar no botão abaixo de cada aluno para abrir o WhatsApp dele com a mensagem de cobrança já pronta!"
        
        return {
            "resposta": resposta,
            "tipo": "inadimplencia",
            "dados": links_whatsapp
        }

    # 2. Cobrança no WhatsApp / Lembretes
    if any(p in texto_lower for p in ["cobrança", "cobrar", "lembrete", "mandar mensagem", "enviar mensagem", "aviso de vencimento", "aviso whatsapp"]):
        links_whatsapp = db.gerar_mensagens_cobranca(tipo="atrasados")
        if not links_whatsapp:
            return {
                "resposta": "🧘 Nenhum aluno precisa de cobrança no momento! Todas as mensalidades estão regulares.",
                "tipo": "cobranca",
                "dados": []
            }
        resposta = f"📲 *Mensagens de WhatsApp Geradas!*\nPreparei as mensagens personalizadas com sua chave PIX para {len(links_whatsapp)} aluno(s) atrasado(s):\n\n"
        for al in links_whatsapp:
            resposta += f"• *{al['nome']}* (R$ {al['valor']:.2f} - Venceu dia {al['dia_vencimento']:02d})\n"
        resposta += "\nToque em *'Enviar WhatsApp'* abaixo para abrir a conversa de cada um com o texto pronto."
        return {
            "resposta": resposta,
            "tipo": "cobranca",
            "dados": links_whatsapp
        }

    # 3. Relatório Mensal / Financeiro
    if any(p in texto_lower for p in ["relatorio", "relatório", "faturamento", "receita", "financeiro", "balanço", "quanto recebi"]):
        relatorio = db.obter_relatorio_mensal()
        resposta = (
            f"📊 *Relatório Financeiro do Mês ({relatorio['mes_referencia']})*\n\n"
            f"• *Faturamento Previsto:* R$ {relatorio['faturamento_previsto']:.2f}\n"
            f"• *Faturamento Realizado:* R$ {relatorio['faturamento_realizado']:.2f}\n"
            f"• *Total Pendente/Atrasado:* R$ {relatorio['total_pendente_ou_atrasado']:.2f}\n"
            f"• *Mensalidades Recebidas:* {relatorio['qtd_pagamentos_recebidos']}\n"
            f"• *Alunos Atrasados:* {relatorio['total_alunos_atrasados']}\n\n"
        )
        if relatorio["por_forma_pagamento"]:
            resposta += "*Formas de Pagamento:* \n"
            for f in relatorio["por_forma_pagamento"]:
                resposta += f"  - {f['forma_pagamento']}: R$ {f['total']:.2f} ({f['qtd']} pagamentos)\n"

        return {
            "resposta": resposta,
            "tipo": "relatorio",
            "dados": relatorio
        }

    # 4. Quantitativo de Alunos / Métricas
    if any(p in texto_lower for p in ["quantitativo", "quantos alunos", "total de alunos", "número de alunos", "alunos ativos", "evasão", "saídas"]):
        quant = db.obter_quantitativo()
        resposta = (
            f"🧘‍♀️ *Quantitativo do Studio de Yoga*\n\n"
            f"• *Alunos Ativos:* {quant['alunos_ativos']}\n"
            f"• *Alunos Inativos:* {quant['alunos_inativos']}\n"
            f"• *Total Cadastrados:* {quant['total_alunos']}\n"
            f"• *Novas Matrículas no Mês:* {quant['novos_matriculados_mes']}\n"
            f"• *Saídas no Mês:* {quant['saidas_mes']}\n"
            f"• *Inadimplentes Atuais:* {quant['inadimplentes_mes']}\n"
        )
        return {
            "resposta": resposta,
            "tipo": "quantitativo",
            "dados": quant
        }

    # 5. Registrar Pagamento via Chat
    if any(p in texto_lower for p in ["pagou", "recebi", "pagamento de", "baixar mensalidade"]):
        # Tentar achar o nome do aluno
        alunos = db.listar_alunos(status="ativo")
        aluno_encontrado = None
        for al in alunos:
            if al["nome"].lower() in texto_lower or al["nome"].split()[0].lower() in texto_lower:
                aluno_encontrado = al
                break

        if aluno_encontrado:
            # Tentar achar a forma
            forma = "PIX"
            if "cartão" in texto_lower or "cartao" in texto_lower:
                forma = "Cartão"
            elif "dinheiro" in texto_lower:
                forma = "Dinheiro"

            # Tentar achar valor
            match_valor = re.search(r"r\$\s*(\d+(?:[.,]\d+)?)|\b(\d{2,4})\b", texto_lower)
            valor = aluno_encontrado["valor_mensalidade"]
            if match_valor:
                val_str = match_valor.group(1) or match_valor.group(2)
                try:
                    valor = float(val_str.replace(",", "."))
                except:
                    pass

            db.registrar_pagamento(aluno_encontrado["id"], valor, forma)
            return {
                "resposta": f"✅ *Pagamento registrado com sucesso!*\n\n• Aluno: *{aluno_encontrado['nome']}*\n• Valor: R$ {valor:.2f}\n• Forma: {forma}\n• Data: {datetime.date.today().strftime('%d/%m/%Y')}\n\nA mensalidade deste mês foi dada como quitada!",
                "tipo": "pagamento_registrado",
                "dados": {"aluno": aluno_encontrado["nome"], "valor": valor, "forma": forma}
            }

    # 6. Saída / Desistência de Aluno
    if any(p in texto_lower for p in ["saiu", "desistiu", "cancelou", "inativar", "trancar", "parou"]):
        alunos = db.listar_alunos(status="ativo")
        aluno_encontrado = None
        for al in alunos:
            if al["nome"].lower() in texto_lower or al["nome"].split()[0].lower() in texto_lower:
                aluno_encontrado = al
                break

        if aluno_encontrado:
            motivo = "Cancelamento informado via assistente"
            db.inativar_aluno(aluno_encontrado["id"], motivo)
            return {
                "resposta": f"⚠️ *Aluno inativado com sucesso.*\n\n• Nome: *{aluno_encontrado['nome']}*\n• Status atual: Inativo\n• Data da saída: {datetime.date.today().strftime('%d/%m/%Y')}\n\nO histórico de pagamentos continua salvo e o quantitativo foi atualizado.",
                "tipo": "aluno_inativado",
                "dados": {"aluno": aluno_encontrado["nome"]}
            }

    # Resposta padrão / orientativa
    return {
        "resposta": (
            "🧘 *Olá! Eu sou sua Assistente Inteligente do Studio de Yoga.*\n\n"
            "Você pode falar comigo por áudio ou texto. Experimente me perguntar:\n\n"
            "👉 *'Quem está com a mensalidade atrasada?'*\n"
            "👉 *'Envie cobrança para os alunos atrasados'* (gera os links do WhatsApp)\n"
            "👉 *'Me envie o relatório mensal'* (faturamento e previsões)\n"
            "👉 *'Qual o quantitativo de alunos?'*\n"
            "👉 *'A Camila pagou a mensalidade hoje via PIX'* (baixa automática)\n"
            "👉 *'O aluno Lucas desistiu das aulas'*\n\n"
            "Como posso ajudar o seu Studio hoje? Namastê! 🙏"
        ),
        "tipo": "ajuda",
        "dados": {}
    }

async def processar_mensagem_ia(texto: str) -> Dict[str, Any]:
    """
    Processa a mensagem com o Gemini 2.5 / Flash se a chave estiver configurada,
    ou usa o motor local inteligente.
    """
    api_key = get_api_key()

    if not api_key:
        return processar_comando_local(texto)

    # Se tiver API Key, usar o Google GenAI SDK
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # Buscar contexto do estúdio para a IA saber o estado atual
        quantitativo = db.obter_quantitativo()
        relatorio = db.obter_relatorio_mensal()
        inadimplentes = db.obter_inadimplentes()
        configs = db.obter_configuracoes()

        system_instruction = f"""
        Você é a Assistente Virtual e Gerente de IA do '{configs.get('nome_studio', 'Studio de Yoga')}'.
        Você conversa diretamente com o proprietário(a) ou recepcionista do estúdio de yoga.
        O seu estilo de comunicação é calmo, acolhedor, objetivo e profissional, no tom 'Namastê' do universo do Yoga.
        
        DADOS ATUAIS EM TEMPO REAL DO STUDIO:
        - Alunos Ativos: {quantitativo['alunos_ativos']}
        - Alunos Inativos: {quantitativo['alunos_inativos']}
        - Total de Alunos: {quantitativo['total_alunos']}
        - Inadimplentes Atuais ({len(inadimplentes)}): {[a['nome'] + ' (venceu dia ' + str(a['dia_vencimento']) + ', R$ ' + str(a['valor_mensalidade']) + ')' for a in inadimplentes]}
        - Faturamento Previsto: R$ {relatorio['faturamento_previsto']:.2f}
        - Faturamento Recebido: R$ {relatorio['faturamento_realizado']:.2f}
        - Total Pendente: R$ {relatorio['total_pendente_ou_atrasado']:.2f}
        - Chave PIX: {configs.get('chave_pix')} ({configs.get('tipo_chave_pix')})

        Regras:
        1. Formate suas mensagens como se fossem no WhatsApp (use *negrito*, listas limpas e emojis de yoga 🧘‍♀️ 🙏 🕉️).
        2. Seja clara e precisa com valores em reais (R$).
        3. Se o usuário pedir para cobrar atrasados ou enviar mensagens, informe quem deve receber e que os links diretos do WhatsApp estão disponíveis.
        4. Mantenha respostas concisas para facilitar a leitura no celular.
        """

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=texto,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3
            )
        )

        resposta_texto = response.text or ""
        
        # Verificar se deve anexar dados adicionais (como links de cobrança)
        texto_lower = texto.lower()
        dados_extras = []
        tipo = "chat"

        if any(p in texto_lower for p in ["atraso", "atrasada", "atrasados", "cobrança", "cobrar", "devedor", "lembrete"]):
            dados_extras = db.gerar_mensagens_cobranca(tipo="atrasados")
            tipo = "inadimplencia" if "quem" in texto_lower else "cobranca"

        return {
            "resposta": resposta_texto,
            "tipo": tipo,
            "dados": dados_extras
        }

    except Exception as e:
        print(f"Erro na chamada Gemini: {e}. Usando motor local de fallback.")
        return processar_comando_local(texto)

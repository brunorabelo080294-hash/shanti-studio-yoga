"""
Módulo de Inteligência Artificial para o Studio de Yoga.
Suporta Google Gemini API (google-genai) com Function Calling e fallback inteligente.
"""
import os
import re
import io
import wave
import base64
import json
import asyncio
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
        alunos = db.listar_alunos(status="ativo")
        aluno_encontrado = None
        for al in alunos:
            if al["nome"].lower() in texto_lower or al["nome"].split()[0].lower() in texto_lower:
                aluno_encontrado = al
                break

        if aluno_encontrado:
            forma = "PIX"
            if "cartão" in texto_lower or "cartao" in texto_lower:
                forma = "Cartão"
            elif "dinheiro" in texto_lower:
                forma = "Dinheiro"

            match_valor = re.search(r"r\$\s*(\d+(?:[.,]\d+)?)|\b(\d{2,4})\b", texto_lower)
            valor = aluno_encontrado["valor_mensalidade"]
            if match_valor:
                val_str = match_valor.group(1) or match_valor.group(2)
                try:
                    valor = float(val_str.replace(",", "."))
                except:
                    pass

            pid = db.registrar_pagamento(aluno_encontrado["id"], valor, forma)
            recibo = db.gerar_comprovante_pagamento(pid)
            return {
                "resposta": f"✅ *Pagamento registrado com sucesso!*\n\n• Aluno: *{aluno_encontrado['nome']}*\n• Valor: R$ {valor:.2f}\n• Forma: {forma}\n• Data: {datetime.date.today().strftime('%d/%m/%Y')}\n\nA mensalidade deste mês foi dada como quitada! Você pode tocar no botão abaixo para enviar o comprovante com 1 clique no WhatsApp:",
                "tipo": "pagamento_registrado",
                "dados": [recibo] if recibo else []
            }

    # 6. Registrar Presença / Frequência de Aluno
    if any(p in texto_lower for p in ["presença", "presenca", "veio", "veio na aula", "presente", "chegou", "frequencia"]):
        alunos = db.listar_alunos(status="ativo")
        aluno_encontrado = None
        for al in alunos:
            if al["nome"].lower() in texto_lower or al["nome"].split()[0].lower() in texto_lower:
                aluno_encontrado = al
                break

        if aluno_encontrado:
            fid = db.registrar_presenca(aluno_encontrado["id"])
            return {
                "resposta": f"🧘‍♀️ *Presença confirmada!*\n\n• Aluna(o): *{aluno_encontrado['nome']}*\n• Data: {datetime.date.today().strftime('%d/%m/%Y')}\n• Horário: {datetime.datetime.now().strftime('%H:%M')}\n\nA presença foi adicionada ao histórico de práticas com sucesso!",
                "tipo": "presenca_registrada",
                "dados": {"aluno": aluno_encontrado["nome"]}
            }

    # 7. Registrar Despesa via Chat
    if any(p in texto_lower for p in ["gastei", "despesa", "comprei", "paguei conta", "gasto"]):
        match_valor = re.search(r"r\$\s*(\d+(?:[.,]\d+)?)|\b(\d{1,4}(?:[.,]\d{2})?)\b", texto_lower)
        if match_valor:
            val_str = match_valor.group(1) or match_valor.group(2)
            try:
                valor_desp = float(val_str.replace(",", "."))
            except:
                valor_desp = 0.0

            if valor_desp > 0:
                desc = texto.strip()
                cat = "Geral"
                if any(x in texto_lower for x in ["aluguel", "sala"]):
                    cat = "Aluguel"
                elif any(x in texto_lower for x in ["luz", "energia", "água", "agua", "internet"]):
                    cat = "Energia/Água"
                elif any(x in texto_lower for x in ["incenso", "óleo", "tapete", "material", "limpeza"]):
                    cat = "Materiais"
                elif any(x in texto_lower for x in ["anúncio", "marketing", "insta"]):
                    cat = "Marketing"

                did = db.registrar_despesa(descricao=desc, valor=valor_desp, categoria=cat)
                relatorio = db.obter_relatorio_mensal()
                return {
                    "resposta": f"💸 *Despesa registrada com sucesso!*\n\n• Descrição: *{desc}*\n• Valor: R$ {valor_desp:.2f}\n• Categoria: {cat}\n• Total de Despesas no Mês: R$ {relatorio['total_despesas']:.2f}\n• Lucro Líquido Atual: R$ {relatorio['lucro_liquido_real']:.2f}",
                    "tipo": "despesa_registrada",
                    "dados": {"id": did, "valor": valor_desp, "categoria": cat}
                }

    # 8. Alunos Ausentes / Sumidos
    if any(p in texto_lower for p in ["ausente", "ausentes", "sumido", "sumidos", "faltou", "faltas"]):
        ausentes = db.obter_alunos_ausentes(dias_sem_aula=10)
        if not ausentes:
            return {
                "resposta": "🧘 Que maravilha! Todos os alunos ativos estão frequentando as práticas com regularidade nos últimos 10 dias!",
                "tipo": "ausentes",
                "dados": []
            }
        resposta = f"🌸 *Alunos que não vêm às aulas há mais de 10 dias:* ({len(ausentes)})\n\n"
        for al in ausentes:
            resposta += f"• *{al['nome']}* — Sem vir há *{al['dias_ausente']} dias* (Última: {al['ultima_presenca']})\n"
        resposta += "\nToque abaixo para enviar uma mensagem carinhosa de acolhimento no WhatsApp de cada um:"
        return {
            "resposta": resposta,
            "tipo": "ausentes",
            "dados": ausentes
        }

    # 9. Aniversariantes do Mês
    if any(p in texto_lower for p in ["aniversariante", "aniversariantes", "aniversario", "aniversário"]):
        niver = db.obter_aniversariantes_mes()
        if not niver:
            return {
                "resposta": "🎂 Não temos nenhum aniversariante registrado para este mês!",
                "tipo": "aniversariantes",
                "dados": []
            }
        resposta = f"🎉 *Aniversariantes do Mês!*\n\n"
        for al in niver:
            status_dia = "Já comemorou" if al["ja_fez"] else "Está chegando"
            resposta += f"• *{al['nome']}* — Dia {al['dia']:02d} ({status_dia})\n"
        resposta += "\nToque abaixo para parabenizar no WhatsApp com 1 clique:"
        return {
            "resposta": resposta,
            "tipo": "aniversariantes",
            "dados": niver
        }

    # 10. Saída / Desistência de Aluno
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
            "👉 *'Marque presença para a Camila hoje'*\n"
            "👉 *'Quais alunos estão sumidos ou sem vir?'*\n"
            "👉 *'Quem faz aniversário esse mês?'*\n"
            "👉 *'Gastei R$ 80 em incensos e óleos'*\n"
            "👉 *'Me envie o relatório e lucro do mês'*\n"
            "👉 *'A Camila pagou a mensalidade hoje via PIX'*\n\n"
            "Como posso ajudar o seu Studio hoje? Namastê! 🙏"
        ),
        "tipo": "ajuda",
        "dados": {}
    }

async def processar_mensagem_ia(texto: str) -> Dict[str, Any]:
    """
    Processa a mensagem com o Gemini Flash Lite com fallback inteligente
    e motor de execução em tempo real.
    """
    texto_lower = texto.lower()

    # Se for comando de registrar ação direta no banco, executar de imediato
    if any(p in texto_lower for p in ["pagou", "recebi pagamento", "baixar mensalidade", "marque presença", "marque presenca", "veio na aula", "gastei", "despesa de"]):
        return processar_comando_local(texto)

    api_key = get_api_key()

    if not api_key:
        return processar_comando_local(texto)

    # Se tiver API Key, usar o Google GenAI SDK
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # Buscar contexto completo do estúdio
        quantitativo = db.obter_quantitativo()
        relatorio = db.obter_relatorio_mensal()
        inadimplentes = db.obter_inadimplentes()
        ausentes = db.obter_alunos_ausentes()
        aniversariantes = db.obter_aniversariantes_mes()
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
        - Total de Despesas do Mês: R$ {relatorio.get('total_despesas', 0):.2f}
        - Lucro Líquido Real do Mês: R$ {relatorio.get('lucro_liquido_real', 0):.2f}
        - Alunos Ausentes / Sem Praticar há mais de 10 dias ({len(ausentes)}): {[a['nome'] + ' (' + str(a['dias_ausente']) + ' dias sem vir)' for a in ausentes]}
        - Aniversariantes do Mês ({len(aniversariantes)}): {[a['nome'] + ' (dia ' + str(a['dia']) + ')' for a in aniversariantes]}
        - Chave PIX: {configs.get('chave_pix')} ({configs.get('tipo_chave_pix')})

        Regras:
        1. Formate suas mensagens como se fossem no WhatsApp (use *negrito*, listas limpas e emojis de yoga 🧘‍♀️ 🙏 🕉️).
        2. Seja clara e precisa com valores em reais (R$), lucro líquido e métricas.
        3. Se o usuário pedir para cobrar atrasados, parabenizar aniversariantes ou acolher alunos ausentes, informe que os botões com links prontos do WhatsApp estão disponíveis na tela.
        4. Mantenha respostas concisas para facilitar a leitura no celular e para poder ser ouvida em voz alta com naturalidade.
        5. Se o usuário fizer perguntas gerais, históricas, curiosidades ou bater papo (ex: 'Quem foi Dom Pedro?', 'Qual a capital do Brasil?'), responda com clareza, riqueza de detalhes e sabedoria, mantendo sempre o tom acolhedor e atencioso.
        """

        candidate_models = [
            "gemini-flash-lite-latest",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.6-flash"
        ]

        resposta_texto = ""
        ultimo_erro = None

        for modelo in candidate_models:
            try:
                response = await client.aio.models.generate_content(
                    model=modelo,
                    contents=texto,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3
                    )
                )
                resposta_texto = (response.text or "").strip()
                if resposta_texto:
                    break
            except Exception as ex:
                ultimo_erro = ex
                print(f"Modelo {modelo} falhou: {ex}. Tentando próximo modelo...")
                continue

        if not resposta_texto and ultimo_erro:
            raise ultimo_erro
        
        # Verificar dados adicionais anexos
        dados_extras = []
        tipo = "chat"

        if any(p in texto_lower for p in ["atraso", "atrasada", "atrasados", "cobrança", "cobrar", "devedor", "lembrete"]):
            dados_extras = db.gerar_mensagens_cobranca(tipo="atrasados")
            tipo = "inadimplencia" if "quem" in texto_lower else "cobranca"
        elif any(p in texto_lower for p in ["aniversariante", "aniversario", "aniversário"]):
            dados_extras = db.obter_aniversariantes_mes()
            tipo = "aniversariantes"
        elif any(p in texto_lower for p in ["ausente", "ausentes", "sumido", "sumidos", "faltou", "faltas"]):
            dados_extras = db.obter_alunos_ausentes()
            tipo = "ausentes"

        return {
            "resposta": resposta_texto,
            "tipo": tipo,
            "dados": dados_extras
        }

    except Exception as e:
        print(f"Erro na chamada Gemini: {e}. Usando motor local de fallback.")
        return processar_comando_local(texto)

def pcm_to_wav_base64(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, sampwidth: int = 2) -> str:
    """Converte bytes PCM brutos (24kHz 16-bit mono) em arquivo RIFF WAV codificado em Base64."""
    if not pcm_data:
        return ""
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return base64.b64encode(wav_io.getvalue()).decode("utf-8")

async def processar_gemini_live(texto: str, voz: str = "Aoede") -> Dict[str, Any]:
    """
    Processa a conversa em tempo real estilo Gemini Live, retornando:
    - resposta em texto transcrita
    - áudio sintetizado em alta resolução com voz feminina natural (Aoede)
    - botões e cartões de ação integrados com o estúdio
    """
    texto_lower = texto.lower()
    api_key = get_api_key()

    # Identificar dados e botões de ação com base na intenção
    dados_extras = []
    tipo = "live_chat"
    if any(p in texto_lower for p in ["atraso", "atrasada", "atrasados", "cobrança", "cobrar", "devedor", "lembrete"]):
        dados_extras = db.gerar_mensagens_cobranca(tipo="atrasados")
        tipo = "inadimplencia" if "quem" in texto_lower else "cobranca"
    elif any(p in texto_lower for p in ["aniversariante", "aniversario", "aniversário"]):
        dados_extras = db.obter_aniversariantes_mes()
        tipo = "aniversariantes"
    elif any(p in texto_lower for p in ["ausente", "ausentes", "sumido", "sumidos", "faltou", "faltas"]):
        dados_extras = db.obter_alunos_ausentes()
        tipo = "ausentes"
    elif any(p in texto_lower for p in ["relatorio", "relatório", "faturamento", "lucro", "despesa"]):
        dados_extras = db.obter_relatorio_mensal()
        tipo = "relatorio"
    elif any(p in texto_lower for p in ["quantitativo", "quantos alunos", "total de alunos"]):
        dados_extras = db.obter_quantitativo()
        tipo = "quantitativo"

    # Se não houver API key, fallback para motor local sem áudio Gemini
    if not api_key:
        resp_local = processar_comando_local(texto)
        return {
            "resposta": resp_local.get("resposta", ""),
            "tipo": resp_local.get("tipo", tipo),
            "dados": resp_local.get("dados", dados_extras),
            "audio_base64": None,
            "voz": voz
        }

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # Contexto atualizado do banco de dados em tempo real
        quantitativo = db.obter_quantitativo()
        relatorio = db.obter_relatorio_mensal()
        inadimplentes = db.obter_inadimplentes()
        ausentes = db.obter_alunos_ausentes()
        aniversariantes = db.obter_aniversariantes_mes()
        configs = db.obter_configuracoes()

        system_instruction = f"""
        Você é Shanti, a assistente virtual e instrutora de Yoga do '{configs.get('nome_studio', 'Studio de Yoga')}'.
        Você está conversando por voz em tempo real (Gemini Live) com o proprietário(a) do estúdio.
        
        Tom e Estilo de Voz:
        - Fale com voz calma, acolhedora, serena, harmoniosa e com dicção perfeita em português do Brasil (no espírito Namastê).
        - Responda de forma falada e concisa (máximo de 2 a 3 frases fluidas).
        - Nunca leia listas longas de nomes ou números em voz alta. Em vez disso, resuma o total e diga que os botões prontos para WhatsApp ou detalhes já estão visíveis na tela.
        
        DADOS ATUAIS DO STUDIO:
        - Alunos Ativos: {quantitativo['alunos_ativos']} (Total cadastrados: {quantitativo['total_alunos']})
        - Inadimplentes Atuais ({len(inadimplentes)}): {[a['nome'] for a in inadimplentes]}
        - Faturamento Recebido no Mês: R$ {relatorio['faturamento_realizado']:.2f}
        - Total de Despesas do Mês: R$ {relatorio.get('total_despesas', 0):.2f}
        - Lucro Líquido Real: R$ {relatorio.get('lucro_liquido_real', 0):.2f}
        - Alunos Ausentes há mais de 10 dias ({len(ausentes)}): {[a['nome'] for a in ausentes]}
        - Aniversariantes deste mês ({len(aniversariantes)}): {[a['nome'] for a in aniversariantes]}
        - Chave PIX: {configs.get('chave_pix')} ({configs.get('tipo_chave_pix')})
        """

        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)
                )
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(
                parts=[types.Part(text=system_instruction)]
            )
        )

        pcm_chunks = bytearray()
        text_chunks = []

        # Conectar via WebSocket ao Gemini 3.1 Flash Live
        async with client.aio.live.connect(model="gemini-3.1-flash-live-preview", config=config) as session:
            await session.send_realtime_input(text=texto)
            async for resp in session.receive():
                sc = resp.server_content
                if sc:
                    if sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                pcm_chunks.extend(part.inline_data.data)
                    if sc.output_transcription and sc.output_transcription.text:
                        text_chunks.append(sc.output_transcription.text)
                    if sc.turn_complete:
                        break

        resposta_texto = "".join(text_chunks).strip()
        wav_b64 = pcm_to_wav_base64(bytes(pcm_chunks)) if pcm_chunks else None

        if not resposta_texto:
            resposta_texto = "Namastê! Como posso ajudar você e o estúdio de yoga agora?"

        return {
            "resposta": resposta_texto,
            "tipo": tipo,
            "dados": dados_extras,
            "audio_base64": wav_b64,
            "voz": voz
        }

    except Exception as e:
        print(f"Erro no Gemini Live WebSocket: {e}. Executando fallback inteligente...")
        resp_fallback = await processar_mensagem_ia(texto)
        return {
            "resposta": resp_fallback.get("resposta", ""),
            "tipo": resp_fallback.get("tipo", tipo),
            "dados": resp_fallback.get("dados", dados_extras),
            "audio_base64": None,
            "voz": voz
        }

async def gerar_audio_gemini(texto: str, voz: str = "Aoede") -> Optional[str]:
    """Gera áudio WAV em Base64 sob demanda para qualquer texto com a voz oficial Aoede."""
    api_key = get_api_key()
    if not api_key or not texto.strip():
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text="Você é uma locutora e instrutora de Yoga. Fale o texto fornecido com naturalidade, clareza, serenidade e acolhimento em português.")]
            )
        )

        pcm_chunks = bytearray()
        async with client.aio.live.connect(model="gemini-3.1-flash-live-preview", config=config) as session:
            await session.send_realtime_input(text=f"Fale com naturalidade o seguinte texto: {texto}")
            async for resp in session.receive():
                sc = resp.server_content
                if sc:
                    if sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                pcm_chunks.extend(part.inline_data.data)
                    if sc.turn_complete:
                        break

        return pcm_to_wav_base64(bytes(pcm_chunks)) if pcm_chunks else None

    except Exception as e:
        print(f"Erro em gerar_audio_gemini: {e}")
        return None

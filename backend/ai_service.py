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
            f"*Relatório Financeiro do Mês ({relatorio['mes_referencia']})*\n\n"
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

    # Consulta Detalhada de Despesas & Contas a Pagar (Fase 3)
    if any(p in texto_lower for p in ["despesa", "despesas", "gastei", "quanto gastou", "contas a pagar", "contas a vencer", "vencimento de conta", "detalhe das contas", "contas pendentes"]):
        hoje = datetime.date.today()
        mes_atual = hoje.strftime("%Y-%m")
        despesas = db.listar_despesas(mes_atual)
        alertas = db.obter_alertas_despesas()

        if not despesas:
            return {
                "resposta": "💸 Nenhuma despesa registrada para o mês atual.",
                "tipo": "despesas",
                "dados": []
            }

        total_desp = sum(d.get("valor", 0.0) for d in despesas)
        resposta = f"💸 *Despesas Detalhadas do Mês ({mes_atual})*\n"
        resposta += f"• Total de Lançamentos: {len(despesas)}\n"
        resposta += f"• Valor Total das Despesas: R$ {total_desp:.2f}\n\n"

        if alertas["total_vencidas"] > 0:
            resposta += f"⚠️ *ATENÇÃO:* Há {alertas['total_vencidas']} conta(s) VENCIDA(S) pendente(s) de pagamento!\n"
        if alertas["total_vence_hoje"] > 0:
            resposta += f"⚡ *ALERTA:* Há {alertas['total_vence_hoje']} conta(s) VENCENDO HOJE!\n"

        resposta += "\n*Relação de Despesas:*\n"
        for idx, d in enumerate(despesas, 1):
            st = "Paga" if d.get("status") == "pago" else "⚠️ PENDENTE"
            dt_venc = d.get("data_vencimento") or d.get("data")
            p = dt_venc.split("-")
            dt_fmt = f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else dt_venc
            resposta += f"{idx}. *{d['descricao']}* — R$ {d['valor']:.2f}\n   • Categoria: {d.get('categoria', 'Geral')} | Vencimento: {dt_fmt} | Status: {st}\n"

        return {
            "resposta": resposta.strip(),
            "tipo": "despesas",
            "dados": despesas
        }

    # Gestão de Contratos Digitais (Fase 4)
    if any(p in texto_lower for p in ["contrato", "contratos", "vigência", "vigencia", "30 dias", "assinatura de contrato", "pendente de assinatura", "contratos a vencer"]):
        alertas = db.obter_alertas_contratos()
        contratos = db.listar_contratos()
        
        resposta = "📜 *Gestão de Contratos Digitais - Studio Shanti*\n\n"
        resposta += f"• *Total de Alunos:* {alertas['total_geral']}\n"
        resposta += f"• *Contratos em Dia:* {alertas['total_em_dia']}\n"
        resposta += f"• *Pendentes de Assinatura:* {alertas['total_pendentes']}\n"
        resposta += f"• *A Vencer nos próximos 30 dias:* {alertas['total_a_vencer']}\n"
        resposta += f"• *Vencidos:* {alertas['total_vencidos']}\n\n"

        if alertas["total_a_vencer"] > 0:
            resposta += "⚠️ *CONTRATOS A VENCER (FALTAM MENOS DE 30 DIAS):*\n"
            for c in alertas["alunos_a_vencer"]:
                resposta += f"• *{c['nome']}* — Vence em {c['dias_restantes']} dias ({c['data_vigencia']})\n"
            resposta += "\n"

        if alertas["total_pendentes"] > 0:
            resposta += "📝 *CONTRATOS PENDENTES DE ASSINATURA:*\n"
            for c in alertas["alunos_pendentes"][:5]:
                resposta += f"• *{c['nome']}* ({c['plano']}) - Aguardando documento assinado\n"
            if len(alertas["alunos_pendentes"]) > 5:
                resposta += f"  _...e mais {len(alertas['alunos_pendentes']) - 5} aluno(s)._\n"
            resposta += "\n"

        resposta += "💡 *Dica:* Na nova aba **Contratos**, você pode baixar o PDF para assinar, enviar direto no WhatsApp do aluno ou anexar a via com as duas assinaturas!"

        return {
            "resposta": resposta.strip(),
            "tipo": "contratos",
            "dados": alertas
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

    # 5. Turmas, Horários e Vagas (Fase 2)
    if any(p in texto_lower for p in ["turma", "turmas", "horário", "horario", "horários", "horarios", "vaga", "vagas", "aula", "aulas"]):
        turmas = db.listar_turmas(ativas_somente=True)
        if not turmas:
            return {
                "resposta": "🧘 Nenhuma turma cadastrada no momento.",
                "tipo": "turmas",
                "dados": []
            }
        resposta = "🕉️ *Turmas e Ocupação do Studio Shanti (Máximo 16 alunos por turma):*\n\n"
        for t in turmas:
            status_tag = ""
            if t.get("lotada"):
                status_tag = " ⚠️ *LOTADA (16/16 alunos!)*"
            elif t.get("quase_lotada"):
                status_tag = " ⚡ *ÚLTIMA VAGA! (15/16)*"
            resposta += f"• *{t['nome']}*{status_tag}\n"
            resposta += f"   📅 {t['dias_semana']} às {t['horario']}\n"
            resposta += f"   🧘 Alunos matriculados: {t['total_matriculados']} de {t['capacidade_vagas']} vagas\n"
            if t.get("lotada"):
                resposta += f"   🛑 *Aviso de Lotação:* Limite de 16 alunos atingido nesta turma!\n\n"
            else:
                resposta += f"   ✨ Vagas disponíveis: {t['vagas_disponiveis']}\n\n"
        return {
            "resposta": resposta.strip(),
            "tipo": "turmas",
            "dados": turmas
        }

    # Alunos que já pagaram no mês / Pagamentos Confirmados (Fase 5)
    if any(p in texto_lower for p in ["quem já pagou", "quem pagou", "já pagou este mês", "pagamentos confirmados", "quem está em dia", "mensalidades pagas", "pagos este mês"]):
        hoje = datetime.date.today()
        mes_atual = hoje.strftime("%Y-%m")
        pagos = db.listar_pagamentos_mes(mes_atual)
        if not pagos:
            return {
                "resposta": f"🧘 Ainda não constam pagamentos registrados para o mês atual ({mes_atual}).",
                "tipo": "pagamentos_mes",
                "dados": []
            }
        
        total_arrecadado = sum(p["valor"] for p in pagos)
        comprovantes = []
        for p in pagos:
            comp = db.gerar_comprovante_pagamento(p["id"])
            if comp:
                comp["aluno"] = p["aluno_nome"]
                comp["plano"] = p.get("aluno_plano") or ""
                comp["dia_semana_1x"] = p.get("dia_semana_1x")
                comprovantes.append(comp)

        resposta = f"💰 *Alunos que já pagaram este mês ({mes_atual}):* ({len(pagos)})\n\n"
        for idx, p in enumerate(pagos, 1):
            dt = p.get("data_pagamento") or ""
            dt_fmt = ""
            if dt:
                partes = dt.split()[0].split("-")
                if len(partes) == 3:
                    dt_fmt = f" em {partes[2]}/{partes[1]}"
            plano_info = p.get("aluno_plano") or ""
            if "1x" in plano_info and p.get("dia_semana_1x"):
                plano_info += f" ({p['dia_semana_1x']})"
            resposta += f"{idx}. *{p['aluno_nome']}* — R$ {p['valor']:.2f}{dt_fmt}\n   • Plano: {plano_info} | Forma: {p.get('forma_pagamento', 'PIX')}\n"
        
        resposta += f"\n✨ *Total arrecadado no mês:* R$ {total_arrecadado:.2f}\n"
        resposta += "💡 *Dica:* Você pode tocar no botão abaixo para reenviar o comprovante de pagamento de cada aluno no WhatsApp."

        return {
            "resposta": resposta.strip(),
            "tipo": "pagamentos_mes",
            "dados": comprovantes if comprovantes else pagos
        }

    # 6. Registrar Pagamento via Chat
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
            if al.get("e_hoje"):
                status_dia = "🎂 É HOJE! 🎉"
            elif al["ja_fez"]:
                status_dia = "Já comemorou"
            else:
                status_dia = "Está chegando"
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
    Processa a mensagem com fast-path instantâneo para comandos do estúdio (0.005s)
    e Gemini Flash Lite otimizado com timeout para conversas abertas.
    """
    texto_lower = texto.lower()

    # 1. Fast-path: Se for qualquer comando ou consulta do estúdio, responder IMEDIATAMENTE (0.005s)
    termos_estudio = [
        "atraso", "atrasada", "atrasadas", "atrasados", "devedor", "inadimplente", "quem deve", "não pagou", "vencid",
        "cobrança", "cobrar", "lembrete", "mandar mensagem", "enviar mensagem", "aviso de vencimento", "aviso whatsapp",
        "quem já pagou", "quem pagou", "já pagou este mês", "pagamentos confirmados", "quem está em dia", "mensalidades pagas", "pagos este mês",
        "pagou", "recebi", "pagamento de", "baixar mensalidade",
        "relatorio", "relatório", "faturamento", "receita", "financeiro", "balanço", "quanto recebi", "lucro",
        "despesa", "despesas", "gastei", "quanto gastou", "contas a pagar", "contas a vencer", "vencimento de conta", "detalhe das contas", "contas pendentes", "paguei conta", "comprei", "gasto",
        "contrato", "contratos", "vigência", "vigencia", "30 dias", "assinatura de contrato", "pendente de assinatura", "contratos a vencer",
        "quantitativo", "quantos alunos", "total de alunos", "número de alunos", "alunos ativos", "evasão", "saídas",
        "saiu", "desistiu", "cancelou", "inativar", "trancar", "parou",
        "turma", "turmas", "horário", "horario", "horários", "horarios", "vaga", "vagas", "aula", "aulas",
        "presença", "presenca", "veio", "veio na aula", "presente", "chegou", "frequencia",
        "ausente", "ausentes", "sumido", "sumidos", "faltou", "faltas",
        "aniversariante", "aniversariantes", "aniversario", "aniversário"
    ]
    if any(t in texto_lower for t in termos_estudio):
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
        turmas = db.listar_turmas(ativas_somente=True)
        configs = db.obter_configuracoes()
        despesas_mes = db.listar_despesas(datetime.date.today().strftime("%Y-%m"))
        alertas_despesas = db.obter_alertas_despesas()
        alertas_contratos = db.obter_alertas_contratos()

        system_instruction = f"""
        Você é a Assistente Virtual e Gerente de IA do '{configs.get('nome_studio', 'Studio Shanti')}'.
        Você conversa diretamente com o proprietário(a) ou recepcionista do estúdio de yoga.
        O seu estilo de comunicação é calmo, acolhedor, objetivo e profissional, no tom 'Namastê' do universo do Yoga.
        
        DADOS ATUAIS EM TEMPO REAL DO STUDIO:
        - Turmas e Horários Ativos ({len(turmas)}): {[t['nome'] + ' (' + t['dias_semana'] + ' às ' + t['horario'] + ' - ' + str(t['total_matriculados']) + '/' + str(t['capacidade_vagas']) + ' ocupadas, ' + str(t['vagas_disponiveis']) + ' vagas livres)' for t in turmas]}
        - Planos Oficiais: 1x na semana (R$ {configs.get('valor_plano_1x', '120.00')}) e 2x na semana (R$ {configs.get('valor_plano_2x', '150.00')})
        - Alunos Ativos: {quantitativo['alunos_ativos']}
        - Alunos Inativos: {quantitativo['alunos_inativos']}
        - Total de Alunos: {quantitativo['total_alunos']}
        - Inadimplentes Atuais ({len(inadimplentes)}): {[a['nome'] + ' (venceu dia ' + str(a['dia_vencimento']) + ', R$ ' + str(a['valor_mensalidade']) + ')' for a in inadimplentes]}
        - Faturamento Previsto: R$ {relatorio['faturamento_previsto']:.2f}
        - Faturamento Recebido: R$ {relatorio['faturamento_realizado']:.2f}
        - Total Pendente: R$ {relatorio['total_pendente_ou_atrasado']:.2f}
        - Total de Despesas do Mês: R$ {relatorio.get('total_despesas', 0):.2f}
        - Despesas Lançadas ({len(despesas_mes)}): {[d['descricao'] + ' (R$ ' + str(d['valor']) + ', Venc: ' + str(d.get('data_vencimento', d.get('data'))) + ', ' + str(d.get('status', 'pago')) + ')' for d in despesas_mes]}
        - Alertas de Vencimento de Despesas: {alertas_despesas['total_vencidas']} conta(s) vencida(s), {alertas_despesas['total_vence_hoje']} vencendo hoje
        - Lucro Líquido Real do Mês: R$ {relatorio.get('lucro_liquido_real', 0):.2f}
        - Contratos Digitais: {alertas_contratos['total_em_dia']} em dia, {alertas_contratos['total_a_vencer']} a vencer nos próximos 30 dias ({[c['nome'] + ' (vence em ' + str(c['dias_restantes']) + ' dias)' for c in alertas_contratos['alunos_a_vencer']]}), {alertas_contratos['total_pendentes']} pendentes de assinatura
        - Alunos Ausentes / Sem Praticar há mais de 10 dias ({len(ausentes)}): {[a['nome'] + ' (' + str(a['dias_ausente']) + ' dias sem vir)' for a in ausentes]}
        - Aniversariantes do Mês ({len(aniversariantes)}): {[a['nome'] + ' (dia ' + str(a['dia']) + ')' for a in aniversariantes]}
        - Chave PIX: {configs.get('chave_pix')} ({configs.get('tipo_chave_pix')})

        Regras:
        1. Formate suas mensagens em texto limpo e direto (use *negrito* para destaque, NUNCA use itálico). Use no máximo 1 emoji por mensagem, e NUNCA use emojis em mensagens contendo dados numéricos, relatórios ou valores financeiros.
        2. Seja clara e precisa com valores em reais (R$), turmas, vagas livres, lucro líquido e métricas financeiras.
        3. Se o usuário pedir para cobrar atrasados, parabenizar aniversariantes ou acolher alunos ausentes, informe que os botões com links prontos do WhatsApp estão disponíveis na tela.
        4. Mantenha respostas concisas para facilitar a leitura no celular e para poder ser ouvida em voz alta com naturalidade.
        5. Se o usuário fizer perguntas gerais, históricas, curiosidades ou bater papo (ex: 'Quem foi Dom Pedro?', 'Qual a capital do Brasil?'), responda com clareza, riqueza de detalhes e sabedoria, mantendo sempre o tom acolhedor e atencioso.
        6. Capacidade Máxima das Turmas: O estúdio adota rigorosamente o teto de 16 alunos por turma. Sempre que perguntado sobre turmas, informe a ocupação (X/16) e alerte com destaque caso alguma turma atinja 16 alunos (turma lotada) ou 15 alunos (última vaga).
        7. Despesas e Contas do Estúdio: Ao ser perguntado sobre despesas, contas a pagar ou vencimentos, informe os detalhes das contas lançadas e avise com urgência sobre contas vencidas ou vencendo hoje.
        8. Contratos Digitais: Ao ser perguntada sobre contratos, informe a situação dos contratos vigentes, alerte expressamente caso haja contratos a vencer em até 30 dias ou pendentes de assinatura e indique que a Natália pode gerenciar tudo na aba Contratos.
        """

        candidate_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-flash-latest"
        ]

        resposta_texto = ""
        ultimo_erro = None

        for modelo in candidate_models:
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=modelo,
                        contents=texto,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.3
                        )
                    ),
                    timeout=5.0
                )
                resposta_texto = (response.text or "").strip()
                if resposta_texto:
                    break
            except Exception as ex:
                ultimo_erro = ex
                print(f"Modelo {modelo} falhou ou expirou: {ex}. Tentando próximo modelo...")
                continue

        if not resposta_texto and ultimo_erro:
            raise ultimo_erro
        
        # Verificar dados adicionais anexos
        dados_extras = []
        tipo = "chat"

        if any(p in texto_lower for p in ["atraso", "atrasada", "atrasados", "cobrança", "cobrar", "devedor", "lembrete"]):
            dados_extras = db.gerar_mensagens_cobranca(tipo="atrasados")
            tipo = "inadimplencia" if "quem" in texto_lower else "cobranca"
        elif any(p in texto_lower for p in ["quem já pagou", "quem pagou", "já pagou este mês", "pagamentos confirmados", "quem está em dia"]):
            pagos = db.listar_pagamentos_mes(datetime.date.today().strftime("%Y-%m"))
            dados_extras = [db.gerar_comprovante_pagamento(p["id"]) for p in pagos if db.gerar_comprovante_pagamento(p["id"])]
            tipo = "pagamentos_mes"
        elif any(p in texto_lower for p in ["aniversariante", "aniversario", "aniversário"]):
            dados_extras = db.obter_aniversariantes_mes()
            tipo = "aniversariantes"
        elif any(p in texto_lower for p in ["ausente", "ausentes", "sumido", "sumidos", "faltou", "faltas"]):
            dados_extras = db.obter_alunos_ausentes()
            tipo = "ausentes"
        elif any(p in texto_lower for p in ["contrato", "contratos", "vigência", "vigencia", "30 dias"]):
            dados_extras = db.obter_alertas_contratos()
            tipo = "contratos"
        elif any(p in texto_lower for p in ["despesa", "despesas", "gastei", "contas a pagar"]):
            dados_extras = db.listar_despesas(datetime.date.today().strftime("%Y-%m"))
            tipo = "despesas"

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

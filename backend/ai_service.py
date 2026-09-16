"""
Módulo de Inteligência Artificial para o Studio de Yoga.
Suporta Groq AI (Llama 3.3 / Qwen / Whisper) de altíssima velocidade e Google Gemini como fallback.
"""
import os
import re
import io
import wave
import base64
import json
import asyncio
import datetime
import time
from typing import Dict, Any, List, Optional
import httpx
from dotenv import load_dotenv
load_dotenv()
import backend.database as db

def get_groq_api_key() -> str:
    configs = db.obter_configuracoes()
    db_key = configs.get("groq_api_key", "").strip()
    if db_key:
        return db_key
    return os.environ.get("GROQ_API_KEY", "").strip()

def get_gemini_api_key() -> str:
    configs = db.obter_configuracoes()
    db_key = configs.get("gemini_api_key", "").strip()
    if db_key:
        return db_key
    return os.environ.get("GEMINI_API_KEY", "").strip()

def get_ai_provider() -> str:
    configs = db.obter_configuracoes()
    p = configs.get("ai_provider", "").strip().lower()
    if p in ["groq", "gemini"]:
        return p
    return os.environ.get("AI_PROVIDER", "groq").strip().lower()

def get_groq_model() -> str:
    configs = db.obter_configuracoes()
    m = configs.get("groq_model", "").strip()
    if m:
        return m
    return os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b").strip()

def get_api_key() -> str:
    """Retorna a chave da IA ativa para compatibilidade."""
    prov = get_ai_provider()
    if prov == "groq":
        k = get_groq_api_key()
        if k:
            return k
    return get_gemini_api_key()


def processar_comando_local(texto: str) -> Dict[str, Any]:
    """
    Motor local de linguagem natural para responder imediatamente
    caso a chave do Gemini ainda não tenha sido configurada.
    """
    texto_lower = texto.lower()

    # 0. Matrículas Pendentes de Pagamento / Aprovação ("Entrou, Pagou")
    termos_matr_pend = [
        "fez a matricula", "fez matrícula", "matricula e não", "matrícula e não",
        "matricula e ainda não", "matrícula e ainda não", "não se pagou", "nao se pagou",
        "matricula pendente", "matrículas pendentes", "matrícula pendente", "pendente de aprovação",
        "pendente de aprovacao", "quem se matriculou e não", "quem se matriculou e ainda",
        "aprovar matrícula", "aprovar matricula", "matriculas pendentes", "matrícula não paga", "matricula nao paga"
    ]
    if any(p in texto_lower for p in termos_matr_pend):
        pendentes = db.obter_matriculas_pendentes()
        if not pendentes:
            return {
                "resposta": "🧘 Nenhuma matrícula pendente no momento! Todos os alunos cadastrados já tiveram seus pagamentos confirmados e estão regulares.",
                "tipo": "matriculas_pendentes",
                "dados": []
            }
        
        resposta = f"📝 *Matrículas Pendentes de Pagamento:* ({len(pendentes)})\n\n"
        for idx, al in enumerate(pendentes, 1):
            dt_mat = al.get("data_matricula") or ""
            dt_fmt = ""
            if dt_mat:
                partes = dt_mat.split()[0].split("-")
                if len(partes) == 3:
                    dt_fmt = f" (cadastrado em {partes[2]}/{partes[1]})"
            resposta += f"{idx}. *{al['nome']}*{dt_fmt}\n   • Plano: {al.get('plano', 'Yoga')} (R$ {al.get('valor_mensalidade', 0):.2f})\n   • Telefone: {al.get('telefone', '-')}\n\n"
        resposta += "💡 *Regra Entrou, Pagou:* Você pode tocar no botão verde abaixo para aprovar o pagamento (a mensalidade é baixada como paga na hora) ou tocar para falar no WhatsApp do aluno!"
        return {
            "resposta": resposta.strip(),
            "tipo": "matriculas_pendentes",
            "dados": pendentes
        }

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

    # Consulta Detalhada de Despesas & Saldo / Contas a Pagar (Fase 3 & Atalho Despesas & Saldo)
    if any(p in texto_lower for p in ["despesa", "despesas", "gastei", "quanto gastou", "contas a pagar", "contas a vencer", "vencimento de conta", "detalhe das contas", "contas pendentes", "despesas e saldo", "saldo do mês", "saldo do mes", "saldo atual", "consultar saldo"]):
        hoje = datetime.date.today()
        mes_atual = hoje.strftime("%Y-%m")
        despesas = db.listar_despesas(mes_atual)
        alertas = db.obter_alertas_despesas()
        relatorio = db.obter_relatorio_mensal(mes_atual)

        total_desp = relatorio.get("total_despesas", 0.0)
        fat_real = relatorio.get("faturamento_realizado", 0.0)
        saldo_real = relatorio.get("lucro_liquido_real", 0.0)

        resposta = f"📊 *Despesas & Saldo do Studio ({mes_atual})*\n\n"
        resposta += f"• *Faturamento Recebido:* R$ {fat_real:.2f}\n"
        resposta += f"• *Total de Despesas:* R$ {total_desp:.2f}\n"
        resposta += f"• *Saldo Líquido Atual:* R$ {saldo_real:.2f}\n"

        if alertas["total_vencidas"] > 0:
            resposta += f"\n⚠️ *ATENÇÃO:* Há {alertas['total_vencidas']} conta(s) VENCIDA(S) pendente(s) de pagamento!"
        if alertas["total_vence_hoje"] > 0:
            resposta += f"\n⚡ *ALERTA:* Há {alertas['total_vence_hoje']} conta(s) VENCENDO HOJE!"

        if not despesas:
            resposta += "\n\n💸 _Nenhuma despesa lançada para este mês ainda._"
            dados_retorno = [{"vazio": True, "faturamento": fat_real, "despesas": total_desp, "saldo": saldo_real}]
        else:
            resposta += f"\n\n*Relação de Despesas ({len(despesas)}):*\n"
            for idx, d in enumerate(despesas, 1):
                st = "Paga" if d.get("status") == "pago" else "⚠️ PENDENTE"
                dt_venc = d.get("data_vencimento") or d.get("data")
                p = dt_venc.split("-")
                dt_fmt = f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else dt_venc
                resposta += f"{idx}. *{d['descricao']}* — R$ {d['valor']:.2f} ({st})\n   • Categoria: {d.get('categoria', 'Geral')} | Venc: {dt_fmt}\n"
            dados_retorno = despesas

        resposta += "\n💡 *Dica:* Toque no botão abaixo para abrir o painel financeiro ou cadastrar novas contas."

        return {
            "resposta": resposta.strip(),
            "tipo": "despesas",
            "dados": dados_retorno
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

PROMPT_ACOES_SISTEMA = """Você é a Assistente e Gerente de IA do Studio Shanti.
Quando o usuário pedir para realizar uma ação no sistema do estúdio de yoga:
- Para lançar despesas: chame a ferramenta 'lancar_despesa'.
  REGRA CRÍTICA DE OURO: Se o usuário pedir para lançar uma despesa SEM informar o valor em reais (por exemplo: 'lance uma despesa de material', 'cadastre um gasto com velas', etc.), NUNCA invente um valor nem chame a ferramenta com valor zero. Responda perguntando educadamente qual é o valor em reais.
- Para marcar pagamento de aluno: chame a ferramenta 'marcar_pagamento'.
- Para excluir aluno: chame a ferramenta 'excluir_aluno'. Essa ação é permanente e destrutiva; o sistema solicitará confirmação antes de remover qualquer dado.
- Para cadastrar aluno: chame a ferramenta 'cadastrar_aluno'.

Seja sempre acolhedora, clara, objetiva e profissional no tom do Yoga.
"""

_cached_system_instruction = None
_cached_system_instruction_time = 0.0

def build_system_instruction(forcar_atualizacao: bool = False) -> str:
    """Monta a instrução de sistema atualizada com o contexto em tempo real do Studio Shanti com cache de 120s."""
    global _cached_system_instruction, _cached_system_instruction_time
    agora = time.time()
    if not forcar_atualizacao and _cached_system_instruction and (agora - _cached_system_instruction_time < 120.0):
        return _cached_system_instruction
    try:
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
    except Exception as e:
        if _cached_system_instruction:
            return _cached_system_instruction
        return PROMPT_ACOES_SISTEMA

    return f"""
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
    9. Execução de Ações via Ferramentas:
       Você possui ferramentas para registrar ações no sistema:
       - Para lançar despesas: chame a ferramenta 'lancar_despesa'. REGRA DE OURO: Se o usuário pedir para lançar despesa SEM informar o valor (ex: 'lance uma despesa de material'), NUNCA invente um valor nem chame a ferramenta. Pergunte ao usuário educadamente qual foi o valor em reais.
       - Para registrar pagamentos: chame 'marcar_pagamento'.
       - Para excluir alunos: chame 'excluir_aluno'. O sistema exigirá confirmação explícita na mensagem seguinte.
       - Para cadastrar novos alunos: chame 'cadastrar_aluno'.
    """

IA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lancar_despesa",
            "description": "Lança uma nova despesa ou pagamento de conta no sistema financeiro do estúdio. Use SEMPRE que o usuário pedir para lançar, cadastrar ou anotar um gasto ou despesa. Se o usuário NÃO informou o valor, NÃO invente um valor nem chame a função com valor zerado — formule uma resposta perguntando o valor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descricao": {
                        "type": "string",
                        "description": "Descrição clara do item ou serviço gasto (ex: 'Material de limpeza', 'Aluguel do estúdio', 'Velas e incensos', 'Anúncio no Instagram')"
                    },
                    "valor": {
                        "type": "number",
                        "description": "Valor numérico em reais da despesa (ex: 50.0). Obrigatório e maior que zero."
                    },
                    "categoria": {
                        "type": "string",
                        "enum": ["Aluguel", "Energia/Água", "Materiais", "Marketing", "Geral"],
                        "description": "Categoria da despesa (Aluguel, Energia/Água, Materiais, Marketing, Geral)"
                    },
                    "data": {
                        "type": "string",
                        "description": "Data no formato YYYY-MM-DD. Opcional (se omitido, será hoje)."
                    }
                },
                "required": ["descricao", "valor"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "marcar_pagamento",
            "description": "Registra o pagamento da mensalidade de um aluno no sistema. Use quando o usuário pedir para registrar pagamento, dar baixa, marcar como pago ou informar que o aluno pagou.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aluno": {
                        "type": "string",
                        "description": "Nome ou parte do nome do aluno que realizou o pagamento (ex: 'Bruno', 'Mariana')"
                    },
                    "forma_pagamento": {
                        "type": "string",
                        "enum": ["PIX", "Dinheiro", "Cartão", "Transferência"],
                        "description": "Forma de pagamento utilizada (padrão: PIX)"
                    },
                    "valor": {
                        "type": "number",
                        "description": "Valor monetário pago em reais. Opcional (se omitido, o sistema utilizará o valor da mensalidade cadastrada do aluno)."
                    },
                    "data": {
                        "type": "string",
                        "description": "Data do pagamento no formato YYYY-MM-DD. Opcional (padrão é hoje)."
                    },
                    "mes_referencia": {
                        "type": "string",
                        "description": "Mês de referência do pagamento no formato YYYY-MM. Opcional (padrão é o mês atual)."
                    }
                },
                "required": ["aluno"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "excluir_aluno",
            "description": "AÇÃO DESTRUTIVA: Solicita a exclusão definitiva de um aluno e de todo o seu histórico do sistema. O sistema NÃO executará a exclusão imediatamente; ele pedirá confirmação explícita do usuário antes de qualquer remoção.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aluno": {
                        "type": "string",
                        "description": "Nome ou parte do nome do aluno a ser excluído (ex: 'Bruno Rabelo')"
                    }
                },
                "required": ["aluno"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cadastrar_aluno",
            "description": "Cadastra um novo aluno no estúdio de yoga.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {
                        "type": "string",
                        "description": "Nome completo do aluno."
                    },
                    "telefone": {
                        "type": "string",
                        "description": "Telefone ou WhatsApp do aluno com DDD (ex: '22988887777')."
                    },
                    "plano": {
                        "type": "string",
                        "enum": ["1x na semana", "2x na semana", "3x na semana", "Livre"],
                        "description": "Plano contratado pelo aluno (padrão: '2x na semana')."
                    },
                    "valor_mensalidade": {
                        "type": "number",
                        "description": "Valor da mensalidade em reais (ex: 150.0). Se omitido, utiliza o valor padrão do plano."
                    },
                    "dia_vencimento": {
                        "type": "integer",
                        "description": "Dia de vencimento da mensalidade (1 a 31). Padrão: 10."
                    }
                },
                "required": ["nome"]
            }
        }
    }
]

GROQ_CANDIDATE_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "groq/compound-mini"
]

async def chamar_groq_com_tools(
    texto: str,
    system_prompt: str,
    api_key: str,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """Chama a API OpenAI-compatible do Groq com catálogo de tools para function calling."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    model_preferido = model or get_groq_model()
    modelos_para_tentar = [model_preferido] + [m for m in ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"] if m != model_preferido]

    ultimo_erro = None
    async with httpx.AsyncClient(timeout=14.0) as client:
        for m in modelos_para_tentar:
            try:
                payload = {
                    "model": m,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": texto}
                    ],
                    "tools": IA_TOOLS,
                    "tool_choice": "auto",
                    "temperature": 0.2,
                    "max_tokens": 800
                }
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        tool_calls = msg.get("tool_calls")
                        content = (msg.get("content") or "").strip()
                        return {
                            "content": content,
                            "tool_calls": tool_calls,
                            "modelo": m
                        }
                elif resp.status_code in [400, 404]:
                    continue
                else:
                    ultimo_erro = Exception(f"Groq HTTP {resp.status_code}: {resp.text[:120]}")
            except Exception as ex:
                ultimo_erro = ex
                continue

    if ultimo_erro:
        raise ultimo_erro
    raise Exception("Nenhum modelo do Groq retornou resposta válida para tool calling.")

async def chamar_groq_chat(texto: str, system_prompt: str, api_key: str, model: Optional[str] = None) -> str:
    """Chama a API OpenAI-compatible do Groq com rotação inteligente de modelos candidatos."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    model_preferido = model or get_groq_model()
    modelos_para_tentar = [model_preferido] + [m for m in GROQ_CANDIDATE_MODELS if m != model_preferido]
    
    ultimo_erro = None
    async with httpx.AsyncClient(timeout=12.0) as client:
        for m in modelos_para_tentar:
            try:
                payload = {
                    "model": m,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": texto}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 800
                }
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = (msg.get("content") or "").strip()
                        if content:
                            return content
                elif resp.status_code == 404:
                    continue
                else:
                    ultimo_erro = Exception(f"Groq HTTP {resp.status_code}: {resp.text[:120]}")
            except Exception as ex:
                ultimo_erro = ex
                continue

    if ultimo_erro:
        raise ultimo_erro
    raise Exception("Nenhum modelo do Groq retornou resposta válida.")

async def transcrever_audio_groq(audio_bytes: bytes, filename: str = "audio.wav", mime_type: str = "audio/wav", api_key: Optional[str] = None) -> str:
    """Transcreve áudio com o modelo whisper-large-v3-turbo da Groq em menos de 500ms."""
    key = api_key or get_groq_api_key()
    if not key or len(audio_bytes) < 300:
        return ""
    
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {key}"}
    files = {"file": (filename, audio_bytes, mime_type)}
    data = {
        "model": "whisper-large-v3-turbo",
        "language": "pt",
        "response_format": "json"
    }
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, files=files, data=data)
        if resp.status_code == 200:
            res_json = resp.json()
            txt = res_json.get("text", "").strip()
            txt = re.sub(r'^["\'\s]+|["\'\s]+$', '', txt)
            if any(txt.lower().startswith(x) for x in ["silêncio", "silencio", "sem fala", "inaudível", "inaudivel", "ruído", "ruido", "nenhum som"]):
                return ""
            return txt
        else:
            raise Exception(f"Groq Whisper HTTP {resp.status_code}: {resp.text[:120]}")

async def chamar_gemini_chat(texto: str, system_prompt: str, api_key: str) -> str:
    """Chama a API do Google Gemini como fallback/alternativa."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    candidate_models = [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-flash-latest"
    ]
    ultimo_erro = None
    for modelo in candidate_models:
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=modelo,
                    contents=texto,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.3
                    )
                ),
                timeout=6.0
            )
            resp_txt = (response.text or "").strip()
            if resp_txt:
                return resp_txt
        except Exception as ex:
            ultimo_erro = ex
            continue
    if ultimo_erro:
        raise ultimo_erro
    raise Exception("Nenhum modelo Gemini retornou resposta.")

# --- Executores de Ações da IA com Validação e Log de Auditoria ---

def executar_acao_lancar_despesa(args: Dict[str, Any], usuario: str) -> Dict[str, Any]:
    """Executa o lançamento de despesa via IA com validação e log de auditoria."""
    descricao = str(args.get("descricao") or "").strip()
    valor_raw = args.get("valor")
    categoria = str(args.get("categoria") or "Geral").strip()
    data = args.get("data")

    # Regra permanente 3: placeholder não é dado
    if not descricao or descricao.lower() in ["não informado", "nao informado", "despesa", "gasto"]:
        return {
            "resposta": "Por favor, informe a descrição do que foi comprado ou pago (ex: 'material de limpeza', 'aluguel').",
            "tipo": "clarificacao_necessaria",
            "acao_executada": False
        }

    # Validação estrita do valor (nunca inventar valor)
    try:
        valor = float(valor_raw) if valor_raw is not None else 0.0
    except (ValueError, TypeError):
        valor = 0.0

    if valor <= 0:
        return {
            "resposta": f"Qual é o valor da despesa de *{descricao}*? Por favor, informe o valor em reais (ex: R$ 50,00).",
            "tipo": "clarificacao_necessaria",
            "acao_executada": False
        }

    # Mapeamento inteligente de categoria
    categorias_validas = ["Aluguel", "Energia/Água", "Materiais", "Marketing", "Geral"]
    if categoria not in categorias_validas:
        desc_lower = descricao.lower()
        if any(x in desc_lower for x in ["aluguel", "sala", "espaço"]):
            categoria = "Aluguel"
        elif any(x in desc_lower for x in ["luz", "energia", "água", "agua", "internet", "telefone"]):
            categoria = "Energia/Água"
        elif any(x in desc_lower for x in ["incenso", "óleo", "oleo", "tapete", "material", "limpeza"]):
            categoria = "Materiais"
        elif any(x in desc_lower for x in ["anúncio", "anuncio", "marketing", "insta", "instagram"]):
            categoria = "Marketing"
        else:
            categoria = "Geral"

    if not data:
        data = db.obter_hoje_sp().strftime("%Y-%m-%d")

    did = db.registrar_despesa(descricao=descricao, valor=valor, categoria=categoria, data=data)

    db.registrar_log_auditoria_ia(
        usuario=usuario,
        acao="lancar_despesa",
        parametros={"descricao": descricao, "valor": valor, "categoria": categoria, "data": data},
        resultado=f"Despesa de R$ {valor:.2f} ({descricao}) lançada com sucesso na categoria {categoria}.",
        sucesso=True,
        detalhes=f"despesa_id={did}"
    )

    return {
        "resposta": f"💸 Despesa de R$ {valor:.2f} em *{descricao}* lançada com sucesso na categoria *{categoria}*!",
        "tipo": "despesa_registrada",
        "acao_executada": True,
        "dados": {"id": did, "descricao": descricao, "valor": valor, "categoria": categoria, "data": data}
    }


def executar_acao_marcar_pagamento(args: Dict[str, Any], usuario: str) -> Dict[str, Any]:
    """Registra pagamento de mensalidade via IA com validação e log de auditoria."""
    aluno_str = str(args.get("aluno") or "").strip()
    forma = str(args.get("forma_pagamento") or "PIX").strip()
    data = args.get("data")
    mes_ref = args.get("mes_referencia")
    valor_raw = args.get("valor")

    if not aluno_str:
        return {
            "resposta": "De qual aluno você deseja registrar o pagamento?",
            "tipo": "clarificacao_necessaria",
            "acao_executada": False
        }

    # Buscar aluno no banco
    alunos = db.listar_alunos()
    aluno_alvo = None
    aluno_lower = aluno_str.lower()
    
    for a in alunos:
        if a["nome"].lower() == aluno_lower:
            aluno_alvo = a
            break
    if not aluno_alvo:
        for a in alunos:
            if aluno_lower in a["nome"].lower() or a["nome"].lower().startswith(aluno_lower):
                aluno_alvo = a
                break

    if not aluno_alvo:
        return {
            "resposta": f"Não encontrei nenhum aluno com o nome '{aluno_str}'. Verifique a lista de alunos na aba Alunos.",
            "tipo": "aluno_nao_encontrado",
            "acao_executada": False
        }

    valor = 0.0
    if valor_raw is not None:
        try:
            valor = float(valor_raw)
        except (ValueError, TypeError):
            valor = 0.0
    if valor <= 0:
        valor = float(aluno_alvo.get("valor_mensalidade") or 150.0)

    hoje_sp = db.obter_hoje_sp()
    if not data:
        data = hoje_sp.strftime("%Y-%m-%d")
    if not mes_ref:
        mes_ref = hoje_sp.strftime("%Y-%m")

    pid = db.registrar_pagamento(
        aluno_id=aluno_alvo["id"],
        valor=valor,
        forma_pagamento=forma,
        mes_referencia=mes_ref,
        data_pagamento=data
    )
    recibo = db.gerar_comprovante_pagamento(pid)

    db.registrar_log_auditoria_ia(
        usuario=usuario,
        acao="marcar_pagamento",
        parametros={
            "aluno": aluno_alvo["nome"],
            "aluno_id": aluno_alvo["id"],
            "valor": valor,
            "forma_pagamento": forma,
            "mes_referencia": mes_ref,
            "data_pagamento": data
        },
        resultado=f"Pagamento de R$ {valor:.2f} ({forma}) do aluno {aluno_alvo['nome']} registrado com sucesso para {mes_ref}.",
        sucesso=True,
        detalhes=f"pagamento_id={pid}"
    )

    return {
        "resposta": f"✅ Pagamento de *{aluno_alvo['nome']}* no valor de R$ {valor:.2f} ({forma}) registrado com sucesso para {mes_ref}!",
        "tipo": "pagamento_registrado",
        "acao_executada": True,
        "dados": [recibo] if recibo else []
    }


def executar_acao_excluir_aluno(args: Dict[str, Any], usuario: str) -> Dict[str, Any]:
    """
    AÇÃO DESTRUTIVA: NUNCA executa a exclusão diretamente.
    Cria uma confirmação pendente no banco e responde pedindo confirmação explícita ao usuário.
    """
    aluno_str = str(args.get("aluno") or "").strip()
    if not aluno_str:
        return {
            "resposta": "Qual aluno você deseja excluir do sistema?",
            "tipo": "clarificacao_necessaria",
            "acao_executada": False
        }

    alunos = db.listar_alunos()
    aluno_alvo = None
    aluno_lower = aluno_str.lower()
    for a in alunos:
        if a["nome"].lower() == aluno_lower:
            aluno_alvo = a
            break
    if not aluno_alvo:
        for a in alunos:
            if aluno_lower in a["nome"].lower() or a["nome"].lower().startswith(aluno_lower):
                aluno_alvo = a
                break

    if not aluno_alvo:
        return {
            "resposta": f"Não encontrei nenhum aluno com o nome '{aluno_str}' para exclusão.",
            "tipo": "aluno_nao_encontrado",
            "acao_executada": False
        }

    db.criar_confirmacao_ia(
        usuario=usuario,
        acao="excluir_aluno",
        alvo_id=aluno_alvo["id"],
        alvo_nome=aluno_alvo["nome"],
        dados={"aluno_id": aluno_alvo["id"], "nome": aluno_alvo["nome"]},
        validade_minutos=5
    )

    return {
        "resposta": (
            f"⚠️ Você quer mesmo excluir o aluno *{aluno_alvo['nome']}*? "
            f"Essa ação não pode ser desfeita e removerá todas as matrículas, frequências e pagamentos associados.\n\n"
            f"Responda **'sim'** para confirmar ou **'não'** para cancelar."
        ),
        "tipo": "confirmacao_necessaria",
        "acao_executada": False,
        "aguardando_confirmacao": True,
        "aluno": aluno_alvo["nome"]
    }


def executar_acao_cadastrar_aluno(args: Dict[str, Any], usuario: str) -> Dict[str, Any]:
    """Cadastra um novo aluno no estúdio via IA com validação e log de auditoria."""
    nome = str(args.get("nome") or "").strip()
    if not nome or nome.lower() in ["não informado", "nao informado", "aluno", "novo aluno"]:
        return {
            "resposta": "Por favor, informe o nome do aluno que você gostaria de cadastrar.",
            "tipo": "clarificacao_necessaria",
            "acao_executada": False
        }

    telefone = str(args.get("telefone") or "").strip()
    plano = str(args.get("plano") or "2x na semana").strip()
    valor_raw = args.get("valor_mensalidade")
    venc_raw = args.get("dia_vencimento")

    dados = {
        "nome": nome,
        "telefone": telefone or "Não informado",
        "plano": plano
    }
    if valor_raw is not None:
        try:
            dados["valor_mensalidade"] = float(valor_raw)
        except:
            pass
    if venc_raw is not None:
        try:
            dados["dia_vencimento"] = int(venc_raw)
        except:
            pass

    aid = db.cadastrar_aluno(dados)

    db.registrar_log_auditoria_ia(
        usuario=usuario,
        acao="cadastrar_aluno",
        parametros=dados,
        resultado=f"Aluno {nome} cadastrado com sucesso (ID {aid}) no plano {plano}.",
        sucesso=True,
        detalhes=f"aluno_id={aid}"
    )

    return {
        "resposta": f"✅ Aluno(a) *{nome}* cadastrado(a) com sucesso no plano *{plano}*!",
        "tipo": "aluno_cadastrado",
        "acao_executada": True,
        "dados": {"id": aid, "nome": nome, "plano": plano}
    }


def processar_acao_fallback(texto: str, usuario: str) -> Optional[Dict[str, Any]]:
    """Parser heurístico seguro de contingência caso o provedor de IA esteja indisponível."""
    texto_lower = texto.lower()

    # 1. Despesa
    if any(k in texto_lower for k in ["despesa", "gastei", "comprei", "paguei conta", "gasto"]):
        match_valor = re.search(r"r\$\s*(\d+(?:[.,]\d+)?)|\b(\d+(?:[.,]\d+)?)\s*(?:reais|real)\b", texto_lower)
        if not match_valor:
            return {
                "resposta": "Qual é o valor da despesa que você deseja lançar? Por favor, informe o valor em reais (ex: R$ 50,00).",
                "tipo": "clarificacao_necessaria",
                "acao_executada": False
            }
        val_str = match_valor.group(1) or match_valor.group(2)
        try:
            valor = float(val_str.replace(",", "."))
        except:
            valor = 0.0

        desc = re.sub(r"(?i)\b(lance|lançar|lancar|cadastrar|anotar|registre|registrar|uma|despesa|de|em|no|na|r\$|\d+(?:[.,]\d+)?|reais|real)\b", "", texto).strip()
        if not desc or len(desc) < 3:
            desc = "Gasto Diversos"

        return executar_acao_lancar_despesa({"descricao": desc, "valor": valor}, usuario)

    # 2. Pagamento
    if any(k in texto_lower for k in ["pagou", "recebi", "pagamento", "baixar mensalidade", "marcar como pago", "marcar pago"]):
        alunos = db.listar_alunos()
        aluno_nome = None
        for a in alunos:
            if a["nome"].lower() in texto_lower or a["nome"].split()[0].lower() in texto_lower:
                aluno_nome = a["nome"]
                break
        if aluno_nome:
            forma = "PIX"
            if "cartão" in texto_lower or "cartao" in texto_lower: forma = "Cartão"
            elif "dinheiro" in texto_lower: forma = "Dinheiro"
            return executar_acao_marcar_pagamento({"aluno": aluno_nome, "forma_pagamento": forma}, usuario)

    # 3. Excluir aluno
    if any(k in texto_lower for k in ["excluir", "deletar", "apagar", "remover"]) and "aluno" in texto_lower:
        alunos = db.listar_alunos()
        for a in alunos:
            if a["nome"].lower() in texto_lower or a["nome"].split()[0].lower() in texto_lower:
                return executar_acao_excluir_aluno({"aluno": a["nome"]}, usuario)

    # 4. Cadastrar aluno
    if any(k in texto_lower for k in ["cadastrar aluno", "cadastre o aluno", "matricular aluno"]):
        partes = texto.split("aluno")[-1].strip()
        nome = partes.split(",")[0].strip() if "," in partes else partes
        if nome:
            return executar_acao_cadastrar_aluno({"nome": nome}, usuario)

    return None


async def processar_mensagem_ia(texto: str, usuario: str = "Natália Garufe") -> Dict[str, Any]:
    """
    Processa mensagens da IA com suporte a Function Calling, auditoria e confirmação segura em 2 etapas.
    """
    texto_lower = texto.lower()
    usuario_ativo = usuario or "Natália Garufe"

    # 1. VERIFICAR CONFIRMAÇÃO PENDENTE DO USUÁRIO (Ação Destrutiva)
    conf_pendente = db.obter_confirmacao_ia_pendente(usuario_ativo)
    if conf_pendente:
        texto_clean = texto.strip().lower()
        palavras_afirmativas = ["sim", "s", "confirmar", "confirmo", "pode excluir", "pode apagar", "excluir", "apagar", "com certeza", "sim por favor", "sim, pode", "ok"]
        palavras_negativas = ["não", "nao", "n", "cancelar", "cancela", "deixa quieto", "não excluir", "nao excluir", "pare", "desistir"]

        eh_afirmacao = any(texto_clean == a or texto_clean.startswith(a + " ") or (" " + a) in texto_clean for a in palavras_afirmativas)
        eh_negacao = any(texto_clean == n or texto_clean.startswith(n + " ") or (" " + n) in texto_clean for n in palavras_negativas)

        if eh_afirmacao and not eh_negacao:
            if conf_pendente["acao"] == "excluir_aluno":
                aluno_id = conf_pendente["alvo_id"]
                aluno_nome = conf_pendente["alvo_nome"]
                sucesso = db.excluir_aluno(aluno_id)
                db.concluir_confirmacao_ia(conf_pendente["id"], "confirmado")
                db.registrar_log_auditoria_ia(
                    usuario=usuario_ativo,
                    acao="excluir_aluno",
                    parametros={"aluno_id": aluno_id, "aluno_nome": aluno_nome},
                    resultado=f"Aluno {aluno_nome} (ID {aluno_id}) excluído com sucesso após confirmação explícita do usuário.",
                    sucesso=sucesso,
                    detalhes=f"conf_id={conf_pendente['id']}",
                    confirmacao_previa=True
                )
                return {
                    "resposta": f"✅ O aluno *{aluno_nome}* foi excluído com sucesso do sistema.",
                    "tipo": "aluno_excluido",
                    "acao_executada": True,
                    "dados": {"id": aluno_id, "nome": aluno_nome}
                }
        elif eh_negacao:
            db.concluir_confirmacao_ia(conf_pendente["id"], "cancelado")
            db.registrar_log_auditoria_ia(
                usuario=usuario_ativo,
                acao="excluir_aluno",
                parametros={"aluno_id": conf_pendente["alvo_id"], "aluno_nome": conf_pendente["alvo_nome"]},
                resultado=f"Exclusão do aluno {conf_pendente['alvo_nome']} cancelada pelo usuário.",
                sucesso=True,
                detalhes=f"conf_id={conf_pendente['id']}",
                confirmacao_previa=True
            )
            return {
                "resposta": f"❌ Ação cancelada. O aluno *{conf_pendente['alvo_nome']}* não foi excluído e permanece cadastrado.",
                "tipo": "acao_cancelada",
                "acao_executada": False
            }
        else:
            db.concluir_confirmacao_ia(conf_pendente["id"], "cancelado_outra_mensagem")

    # 2. IDENTIFICAR SE É UMA AÇÃO DE ESCRITA
    indicadores_acao = [
        "lance uma despesa", "lançar despesa", "lancar despesa", "cadastrar despesa", "anote uma despesa", "nova despesa", "gastei", "comprei", "despesa de",
        "marcar pagamento", "marcar como pago", "marcar pago", "marcar o aluno", "dar baixa", "baixar mensalidade", "pagou a mensalidade", "pagamento do aluno",
        "excluir aluno", "excluir o aluno", "deletar aluno", "deletar o aluno", "apagar aluno", "apagar o aluno", "remover aluno", "remover o aluno",
        "cadastrar aluno", "cadastrar aluna", "cadastre o aluno", "cadastre a aluna", "matricular aluno", "matricular aluna", "novo aluno", "nova aluna"
    ]
    eh_acao_intencional = any(ind in texto_lower for ind in indicadores_acao)

    # 3. SE NÃO FOR AÇÃO, CHECAR FAST-PATH SOMENTE PARA CONSULTAS DE LEITURA
    if not eh_acao_intencional:
        consultas_estudio = [
            "atraso", "atrasada", "atrasadas", "atrasados", "devedor", "inadimplente", "quem deve", "não pagou", "vencid",
            "cobrança", "cobrar", "lembrete",
            "quem já pagou", "quem pagou", "já pagou este mês", "pagamentos confirmados", "quem está em dia", "mensalidades pagas", "pagos este mês",
            "relatorio", "relatório", "faturamento", "receita", "financeiro", "balanço", "quanto recebi", "lucro",
            "contrato", "contratos", "vigência", "vigencia", "30 dias", "assinatura de contrato", "pendente de assinatura", "contratos a vencer",
            "quantitativo", "quantos alunos", "total de alunos", "número de alunos", "alunos ativos", "evasão", "saídas",
            "turma", "turmas", "horário", "horario", "horários", "horarios", "vaga", "vagas", "aula", "aulas",
            "presença", "presenca", "veio", "veio na aula", "presente", "chegou", "frequencia",
            "ausente", "ausentes", "sumido", "sumidos", "faltou", "faltas",
            "aniversariante", "aniversariantes", "aniversario", "aniversário"
        ]
        if any(c in texto_lower for c in consultas_estudio):
            return processar_comando_local(texto)

    # 4. CHAMA GROQ COM TOOLS PARA PROCESSAMENTO INTELIGENTE
    groq_key = get_groq_api_key()
    gemini_key = get_gemini_api_key()
    provider = get_ai_provider()
    system_instruction = PROMPT_ACOES_SISTEMA if eh_acao_intencional else build_system_instruction()

    if groq_key:
        try:
            res_groq = await chamar_groq_com_tools(texto, system_instruction, groq_key)
            tool_calls = res_groq.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name")
                    fn_args_raw = fn.get("arguments", "{}")
                    try:
                        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else (fn_args_raw or {})
                    except Exception:
                        fn_args = {}

                    if fn_name == "lancar_despesa":
                        return executar_acao_lancar_despesa(fn_args, usuario_ativo)
                    elif fn_name == "marcar_pagamento":
                        return executar_acao_marcar_pagamento(fn_args, usuario_ativo)
                    elif fn_name == "excluir_aluno":
                        return executar_acao_excluir_aluno(fn_args, usuario_ativo)
                    elif fn_name == "cadastrar_aluno":
                        return executar_acao_cadastrar_aluno(fn_args, usuario_ativo)

            content = res_groq.get("content")
            if content:
                return {"resposta": content, "tipo": "chat", "dados": []}
        except Exception as eg:
            print(f"Erro no Groq com tools: {eg}. Tentando contingência...")

    # 5. CONTINGÊNCIA: Se for ação intencional mas Groq falhou, executar via parser seguro
    if eh_acao_intencional:
        res_fallback = processar_acao_fallback(texto, usuario_ativo)
        if res_fallback:
            return res_fallback

    # 6. Fallback final para Gemini ou Modo Local
    if gemini_key:
        try:
            resp_gem = await chamar_gemini_chat(texto, system_instruction, gemini_key)
            if resp_gem:
                return {"resposta": resp_gem, "tipo": "chat", "dados": []}
        except Exception as ege:
            print(f"Erro no Gemini fallback: {ege}")

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

async def testar_conexao_ia_isolada() -> Dict[str, Any]:
    """
    Testa de forma isolada e minimalista a comunicação com a IA ativa (Groq ou Gemini).
    Mede a latência exata da resposta e traduz qualquer falha para explicações claras e simplificadas.
    Nunca expõe chaves de API.
    """
    prov = get_ai_provider()
    groq_key = get_groq_api_key()
    gemini_key = get_gemini_api_key()

    usar_groq = (prov == "groq" or not gemini_key) and bool(groq_key)
    usar_gemini = (prov == "gemini" or not groq_key) and bool(gemini_key)

    if not usar_groq and not usar_gemini:
        return {
            "status_ia": "chave_ausente",
            "latencia_ms": 0,
            "provedor": "local",
            "modelo": "motor_local_integrado",
            "mensagem": "Nenhuma chave de API configurada no estúdio. O app está operando perfeitamente com o motor local integrado (respostas instantâneas a atalhos e comandos).",
            "detalhes": None,
            "sucesso": True
        }

    t0 = time.perf_counter()

    if usar_groq:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json"
            }
            model_preferido = get_groq_model()
            modelos_para_tentar = [model_preferido] + [m for m in GROQ_CANDIDATE_MODELS if m != model_preferido]
            
            resposta_texto = ""
            modelo_usado = model_preferido
            ultimo_erro = None

            async with httpx.AsyncClient(timeout=6.0) as client:
                for mod in modelos_para_tentar:
                    try:
                        modelo_usado = mod
                        payload = {
                            "model": mod,
                            "messages": [{"role": "user", "content": "Responda apenas: OK"}],
                            "temperature": 0.0,
                            "max_tokens": 10
                        }
                        resp = await client.post(url, headers=headers, json=payload)
                        if resp.status_code == 200:
                            data = resp.json()
                            choices = data.get("choices", [])
                            if choices:
                                resposta_texto = choices[0].get("message", {}).get("content", "").strip()
                                if resposta_texto:
                                    break
                        elif resp.status_code == 404:
                            continue
                        else:
                            ultimo_erro = Exception(f"Groq HTTP {resp.status_code}: {resp.text[:100]}")
                    except Exception as ex_m:
                        ultimo_erro = ex_m
                        continue

            latencia_ms = max(1, int((time.perf_counter() - t0) * 1000))
            if not resposta_texto and ultimo_erro:
                raise ultimo_erro

            status_ia = "lento" if latencia_ms > 3000 else "ok"
            msg = (
                f"Groq IA ({modelo_usado}) conectado e operando em alta velocidade ({latencia_ms}ms)."
                if status_ia == "ok"
                else f"Groq IA conectado, porém com latência elevada ({latencia_ms}ms)."
            )

            return {
                "status_ia": status_ia,
                "provedor": "groq",
                "latencia_ms": latencia_ms,
                "modelo": modelo_usado,
                "mensagem": msg,
                "detalhes": f"Resposta: '{resposta_texto[:30]}'",
                "sucesso": True
            }

        except Exception as e:
            latencia_ms = max(1, int((time.perf_counter() - t0) * 1000))
            err_str = str(e)
            err_lower = err_str.lower()

            if "429" in err_str or "rate_limit" in err_lower or "quota" in err_lower:
                motivo = "Limite de requisições gratuitas do Groq atingido. O app utiliza o motor local até renovação."
            elif any(x in err_str for x in ["401", "403"]) or "invalid_api_key" in err_lower or "permission" in err_lower:
                motivo = "Chave de API do Groq inválida. Verifique a chave inserida na aba Ajustes."
            elif "timeout" in err_lower or isinstance(e, asyncio.TimeoutError):
                motivo = "Tempo limite esgotado: os servidores da Groq demoraram mais de 6 segundos para responder."
            elif "connect" in err_lower or "network" in err_lower or "dns" in err_lower or "gaierror" in err_lower:
                motivo = "Falha de conexão com os servidores da Groq (DNS ou rede temporariamente inacessível)."
            else:
                motivo = f"Erro de comunicação com Groq: {err_str[:120]}"

            detalhes_seguros = err_str.replace(groq_key, "***CHAVE_OCULTA***") if groq_key else err_str
            return {
                "status_ia": "erro",
                "provedor": "groq",
                "latencia_ms": latencia_ms,
                "modelo": "desconhecido",
                "mensagem": motivo,
                "detalhes": detalhes_seguros[:200],
                "sucesso": False
            }

    # Testar Gemini se for o provedor ativo
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_key)
        candidate_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-flash-latest"
        ]

        modelo_usado = candidate_models[0]
        resposta_texto = ""
        ultimo_erro = None

        for mod in candidate_models:
            try:
                modelo_usado = mod
                resp = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=mod,
                        contents="Responda apenas: OK",
                        config=types.GenerateContentConfig(
                            max_output_tokens=10,
                            temperature=0.0
                        )
                    ),
                    timeout=5.0
                )
                resposta_texto = (resp.text or "").strip()
                if resposta_texto:
                    break
            except Exception as ex_m:
                ultimo_erro = ex_m
                continue

        latencia_ms = max(1, int((time.perf_counter() - t0) * 1000))
        if not resposta_texto and ultimo_erro:
            raise ultimo_erro

        status_ia = "lento" if latencia_ms > 3000 else "ok"
        msg = (
            f"Google Gemini conectado e operando normalmente ({latencia_ms}ms)."
            if status_ia == "ok"
            else f"Google Gemini conectado, porém com resposta lenta dos servidores da nuvem ({latencia_ms}ms)."
        )

        return {
            "status_ia": status_ia,
            "provedor": "gemini",
            "latencia_ms": latencia_ms,
            "modelo": modelo_usado,
            "mensagem": msg,
            "detalhes": f"Resposta: '{resposta_texto[:30]}'",
            "sucesso": True
        }

    except Exception as e:
        latencia_ms = max(1, int((time.perf_counter() - t0) * 1000))
        err_str = str(e)
        err_lower = err_str.lower()

        if "429" in err_str or "resource_exhausted" in err_lower or "quota" in err_lower:
            motivo = "Cota de requisições gratuitas da IA excedida (limite diário ou por minuto do Google atingido). O app utiliza o motor local até a renovação da cota."
        elif any(x in err_str for x in ["400", "401", "403"]) or "api_key_invalid" in err_lower or "permission" in err_lower or "unauthenticated" in err_lower:
            motivo = "Chave de API do Gemini inválida ou sem permissão. Verifique a chave inserida na aba Ajustes."
        elif "timeout" in err_lower or isinstance(e, asyncio.TimeoutError):
            motivo = "Tempo limite esgotado: os servidores do Google demoraram mais de 5 segundos para responder. Instabilidade temporária na nuvem."
        elif "connect" in err_lower or "network" in err_lower or "dns" in err_lower or "gaierror" in err_lower:
            motivo = "Falha de conexão com os servidores do Google (DNS ou rede temporariamente inacessível)."
        else:
            motivo = f"Erro de comunicação com a IA: {err_str[:120]}"

        detalhes_seguros = err_str.replace(gemini_key, "***CHAVE_OCULTA***") if gemini_key else err_str

        return {
            "status_ia": "erro",
            "provedor": "gemini",
            "latencia_ms": latencia_ms,
            "modelo": "desconhecido",
            "mensagem": motivo,
            "detalhes": detalhes_seguros[:200],
            "sucesso": False
        }

testar_conexao_gemini_isolada = testar_conexao_ia_isolada



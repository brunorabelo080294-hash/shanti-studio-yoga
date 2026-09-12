"""
Módulo para geração de relatórios financeiros oficiais em PDF do Studio Shanti.
Utiliza ReportLab para construir um documento profissional, com identidade visual harmoniosa,
gráficos/tabelas estruturadas e alta legibilidade para impressão e download.
"""

import io
import datetime
from typing import Optional, Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.pdfgen import canvas

import backend.database as db

class NumberedCanvas(canvas.Canvas):
    """Canvas de duas etapas para numeração de página precisa 'Página X de Y'."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        text_footer = f"Studio Shanti • Gestão Financeira • Página {self._pageNumber} de {page_count}"
        self.drawString(40, 25, text_footer)
        emitido_em = datetime.datetime.now().strftime("%d/%m/%Y às %H:%M")
        self.drawRightString(A4[0] - 40, 25, f"Emitido em {emitido_em}")
        self.restoreState()


def gerar_pdf_relatorio_financeiro(mes_ano: Optional[str] = None) -> io.BytesIO:
    """
    Gera um relatório financeiro mensal detalhado em memória e retorna um buffer BytesIO.
    """
    hoje = datetime.date.today()
    if not mes_ano:
        mes_ano = hoje.strftime("%Y-%m")

    # Obter dados consolidados
    relatorio = db.obter_relatorio_mensal(mes_ano)
    configs = db.obter_configuracoes()
    nome_studio = configs.get("nome_studio", "Studio Shanti")
    despesas = db.listar_despesas(mes_ano)
    inadimplentes = db.obter_inadimplentes()

    # Formatar mês/ano por extenso
    meses_pt = {
        "01": "Janeiro", "02": "Fevereiro", "03": "Março", "04": "Abril",
        "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
        "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro"
    }
    partes_mes = mes_ano.split("-")
    ano_str = partes_mes[0] if len(partes_mes) > 0 else str(hoje.year)
    mes_num = partes_mes[1] if len(partes_mes) > 1 else f"{hoje.month:02d}"
    mes_extenso = f"{meses_pt.get(mes_num, mes_num)} de {ano_str}"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()

    # Cores da identidade Shanti
    cor_primaria = colors.HexColor("#1C2B24")      # Verde Floresta Escuro
    cor_dourada = colors.HexColor("#C5A059")       # Ouro Shanti
    cor_fundo_card = colors.HexColor("#F9F7F2")    # Areia Claro
    cor_borda = colors.HexColor("#E2DCD5")
    cor_texto_escuro = colors.HexColor("#1e293b")
    cor_verde = colors.HexColor("#15803d")
    cor_vermelho = colors.HexColor("#b91c1c")

    style_titulo = ParagraphStyle(
        'TituloDoc',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=cor_primaria,
        spaceAfter=2
    )

    style_secao = ParagraphStyle(
        'SecaoTitulo',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=cor_primaria,
        spaceBefore=14,
        spaceAfter=6
    )

    style_cell = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=cor_texto_escuro
    )

    style_cell_bold = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=cor_texto_escuro
    )

    style_cell_center = ParagraphStyle(
        'CellCenter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        alignment=1,
        textColor=cor_texto_escuro
    )

    elements = []

    # 1. CABEÇALHO DO DOCUMENTO
    header_data = [
        [
            Paragraph(f"<b>{nome_studio}</b>", style_titulo),
            Paragraph(f"<b>RELATÓRIO FINANCEIRO OFICIAL</b><br/><font size=8 color='#64748b'>Competência: {mes_extenso}</font>", ParagraphStyle('HeaderRight', parent=styles['Normal'], alignment=2, fontName='Helvetica', fontSize=10, textColor=cor_primaria))
        ]
    ]
    t_header = Table(header_data, colWidths=[320, 195])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(t_header)
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=cor_dourada, spaceBefore=4, spaceAfter=14))

    # 2. CARDS DE RESUMO DO BALANÇO (4 colunas)
    fatur_prev = relatorio.get("faturamento_previsto", 0.0)
    fatur_real = relatorio.get("faturamento_realizado", 0.0)
    total_desp = relatorio.get("total_despesas", 0.0)
    lucro_real = relatorio.get("lucro_liquido_real", 0.0)

    card_col_w = 128.5
    cards_data = [
        [
            Paragraph("<font size=7 color='#64748b'>FATURAMENTO PREVISTO</font><br/><b><font size=12 color='#1C2B24'>R$ {:,.2f}</font></b>".format(fatur_prev).replace(',', 'X').replace('.', ',').replace('X', '.'), ParagraphStyle('Card1', parent=styles['Normal'], alignment=1)),
            Paragraph("<font size=7 color='#64748b'>JÁ RECEBIDO NO MÊS</font><br/><b><font size=12 color='#15803d'>R$ {:,.2f}</font></b>".format(fatur_real).replace(',', 'X').replace('.', ',').replace('X', '.'), ParagraphStyle('Card2', parent=styles['Normal'], alignment=1)),
            Paragraph("<font size=7 color='#64748b'>TOTAL DE DESPESAS</font><br/><b><font size=12 color='#b91c1c'>R$ {:,.2f}</font></b>".format(total_desp).replace(',', 'X').replace('.', ',').replace('X', '.'), ParagraphStyle('Card3', parent=styles['Normal'], alignment=1)),
            Paragraph("<font size=7 color='#64748b'>LUCRO LÍQUIDO REAL</font><br/><b><font size=12 color='#1C2B24'>R$ {:,.2f}</font></b>".format(lucro_real).replace(',', 'X').replace('.', ',').replace('X', '.'), ParagraphStyle('Card4', parent=styles['Normal'], alignment=1)),
        ]
    ]
    t_cards = Table(cards_data, colWidths=[card_col_w]*4)
    t_cards.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_fundo_card),
        ('BOX', (0, 0), (-1, -1), 0.5, cor_borda),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, cor_borda),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t_cards)
    elements.append(Spacer(1, 14))

    # 3. RECEITAS POR FORMA DE PAGAMENTO
    elements.append(Paragraph("<b>1. Recebimentos por Forma de Pagamento</b>", style_secao))
    por_forma = relatorio.get("por_forma_pagamento", [])
    if not por_forma:
        t_receitas_data = [["Forma de Pagamento", "Quantidade", "Total Recebido"]]
        t_receitas_data.append(["Nenhum recebimento registrado neste mês.", "0", "R$ 0,00"])
    else:
        t_receitas_data = [["Forma de Pagamento", "Quantidade de Pagamentos", "Total Recebido (R$)"]]
        for f in por_forma:
            v_format = "R$ {:,.2f}".format(f["total"]).replace(',', 'X').replace('.', ',').replace('X', '.')
            t_receitas_data.append([
                f["forma_pagamento"],
                str(f["qtd"]),
                v_format
            ])
        v_total_rec = "R$ {:,.2f}".format(fatur_real).replace(',', 'X').replace('.', ',').replace('X', '.')
        t_receitas_data.append(["Total Geral de Recebimentos", str(relatorio.get("qtd_pagamentos_recebidos", 0)), v_total_rec])

    t_receitas = Table(t_receitas_data, colWidths=[234, 140, 140])
    t_receitas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), cor_primaria),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, cor_borda),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, cor_fundo_card]),
        ('BACKGROUND', (0, -1), (-1, -1), cor_fundo_card),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(t_receitas)
    elements.append(Spacer(1, 14))

    # 4. DETALHAMENTO COMPLETO DE DESPESAS
    elements.append(Paragraph(f"<b>2. Detalhamento de Despesas ({len(despesas)} lançamentos)</b>", style_secao))
    
    t_desp_data = [["Descrição da Despesa", "Categoria", "Data", "Vencimento", "Valor (R$)", "Status"]]
    if not despesas:
        t_desp_data.append(["Nenhuma despesa registrada para este mês.", "-", "-", "-", "R$ 0,00", "OK"])
    else:
        for d in despesas:
            v_format = "R$ {:,.2f}".format(d.get("valor", 0.0)).replace(',', 'X').replace('.', ',').replace('X', '.')
            dt_emissao = d.get("data", "")
            dt_venc = d.get("data_vencimento", "") or dt_emissao
            status_txt = "Paga" if d.get("status") == "pago" else "Pendente"
            
            def fmt_br(ds):
                if not ds: return "-"
                p = ds.split("-")
                return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else ds

            t_desp_data.append([
                Paragraph(f"<b>{d.get('descricao', '')}</b>", style_cell),
                Paragraph(d.get('categoria', 'Geral'), style_cell),
                Paragraph(fmt_br(dt_emissao), style_cell_center),
                Paragraph(fmt_br(dt_venc), style_cell_center),
                Paragraph(f"<b>{v_format}</b>", ParagraphStyle('ValR', parent=styles['Normal'], alignment=2, fontName='Helvetica', fontSize=8.5)),
                Paragraph(f"<font color='{'#15803d' if status_txt == 'Paga' else '#b91c1c'}'><b>{status_txt}</b></font>", style_cell_center)
            ])

        v_tot_desp = "R$ {:,.2f}".format(total_desp).replace(',', 'X').replace('.', ',').replace('X', '.')
        t_desp_data.append([
            Paragraph("<b>Total das Despesas</b>", style_cell_bold),
            "", "", "",
            Paragraph(f"<b>{v_tot_desp}</b>", ParagraphStyle('TotDespR', parent=styles['Normal'], alignment=2, fontName='Helvetica-Bold', fontSize=8.5, textColor=cor_vermelho)),
            ""
        ])

    t_despesas = Table(t_desp_data, colWidths=[164, 90, 65, 65, 75, 55])
    t_despesas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), cor_primaria),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, cor_borda),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, cor_fundo_card]),
        ('BACKGROUND', (0, -1), (-1, -1), cor_fundo_card),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, -1), (3, -1)),
    ]))
    elements.append(t_despesas)
    elements.append(Spacer(1, 14))

    # 5. INADIMPLÊNCIA & ACOMPANHAMENTO DE MENSALIDADES
    elements.append(Paragraph(f"<b>3. Alunos com Mensalidade em Atraso ({len(inadimplentes)})</b>", style_secao))
    if not inadimplentes:
        t_inad_data = [
            ["Status das Mensalidades"],
            ["🧘 Excelente! Não há alunos inadimplentes ou mensalidades atrasadas no momento. Todas as contas estão regulares."]
        ]
        t_inad = Table(t_inad_data, colWidths=[514])
        t_inad.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#86efac")),
            ('TEXTCOLOR', (0, 0), (-1, -1), cor_verde),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(t_inad)
    else:
        t_inad_data = [["Nome do Aluno", "Plano", "Vencimento", "Atraso", "Valor Pendente", "Telefone"]]
        for al in inadimplentes:
            v_al = "R$ {:,.2f}".format(al.get("valor_mensalidade", 0.0)).replace(',', 'X').replace('.', ',').replace('X', '.')
            t_inad_data.append([
                Paragraph(f"<b>{al.get('nome', '')}</b>", style_cell),
                Paragraph(al.get('plano', ''), style_cell),
                Paragraph(f"Dia {al.get('dia_vencimento', 10):02d}", style_cell_center),
                Paragraph(f"<font color='#b91c1c'><b>{al.get('dias_atraso', 0)} dias</b></font>", style_cell_center),
                Paragraph(f"<b>{v_al}</b>", ParagraphStyle('VpendR', parent=styles['Normal'], alignment=2, fontName='Helvetica-Bold', fontSize=8.5, textColor=cor_vermelho)),
                Paragraph(al.get('telefone', ''), style_cell_center)
            ])
        tot_pend_val = "R$ {:,.2f}".format(relatorio.get("total_pendente_ou_atrasado", 0.0)).replace(',', 'X').replace('.', ',').replace('X', '.')
        t_inad_data.append([
            Paragraph("<b>Total Pendente / Em Atraso</b>", style_cell_bold),
            "", "", "",
            Paragraph(f"<b>{tot_pend_val}</b>", ParagraphStyle('TotPendR', parent=styles['Normal'], alignment=2, fontName='Helvetica-Bold', fontSize=8.5, textColor=cor_vermelho)),
            ""
        ])

        t_inad = Table(t_inad_data, colWidths=[154, 80, 60, 60, 80, 80])
        t_inad.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#7f1d1d")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, cor_borda),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor("#fff1f2")]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#fee2e2")),
            ('SPAN', (0, -1), (3, -1)),
        ]))
        elements.append(t_inad)

    elements.append(Spacer(1, 16))

    msg_final = (
        f"<font size=8 color='#64748b'>"
        f"<b>Observações Contábeis:</b> Este balanço considera os pagamentos efetivamente confirmados e as despesas "
        f"registradas no sistema do Studio Shanti para o mês de {mes_extenso}. "
        f"Chave PIX cadastrada para recebimento: {configs.get('chave_pix', '')} ({configs.get('tipo_chave_pix', '')})."
        f"</font>"
    )
    elements.append(Paragraph(msg_final, styles['Normal']))

    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer

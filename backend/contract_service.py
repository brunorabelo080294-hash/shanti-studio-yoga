"""
Módulo para geração de Contratos Oficiais de Prestação de Serviços do Studio Shanti.
Utiliza ReportLab para construir o documento jurídico com as cláusulas 1 a 13 rigorosamente congeladas
e substituição automática dos marcadores cadastrais do aluno.
"""

import io
import datetime
from typing import Optional, Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas

import backend.database as db

class ContractNumberedCanvas(canvas.Canvas):
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
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#64748b'))
        text_footer = f'Studio Shanti • Contrato de Prestação de Serviços • Página {self._pageNumber} de {page_count}'
        self.drawString(45, 25, text_footer)
        self.drawRightString(A4[0] - 45, 25, 'Além Paraíba/MG')
        self.restoreState()


def gerar_pdf_contrato(aluno_id: int) -> io.BytesIO:
    """
    Gera o Contrato Oficial em PDF preenchido para o aluno com as cláusulas 1 a 13 congeladas.
    """
    aluno = db.obter_aluno(aluno_id)
    if not aluno:
        raise ValueError(f'Aluno com ID {aluno_id} não encontrado.')

    configs = db.obter_configuracoes()
    nome_studio = configs.get('nome_studio', 'Studio Shanti')

    # 1. Resolução dos Marcadores
    nome_aluno = (aluno.get('nome') or '').strip()
    cpf_aluno = (aluno.get('cpf') or '').strip() or 'Não informado'
    telefone_aluno = (aluno.get('telefone') or '').strip()

    plano_aluno = aluno.get('plano', '') or '2x na semana'
    is_1x = '1x' in plano_aluno.lower()
    marca_1x = 'X' if is_1x else '  '
    marca_2x = 'X' if not is_1x else '  '

    # Turmas e horários
    turmas = aluno.get('turmas', [])
    if turmas:
        turma_info_list = []
        for t in turmas:
            dia_info = f" ({aluno.get('dia_semana_1x')})" if is_1x and aluno.get('dia_semana_1x') else ''
            turma_info_list.append(f"{t['nome']} — {t['dias_semana']} às {t['horario']}{dia_info}")
        dias_horarios_str = '; '.join(turma_info_list)
    else:
        dia_1x = f" ({aluno.get('dia_semana_1x')})" if is_1x and aluno.get('dia_semana_1x') else ''
        dias_horarios_str = f"{plano_aluno}{dia_1x}"

    # Data da matrícula / contrato
    data_mat_str = aluno.get('data_matricula') or datetime.date.today().strftime('%Y-%m-%d')
    try:
        dt_mat = datetime.date.fromisoformat(data_mat_str)
    except Exception:
        dt_mat = datetime.date.today()

    meses_pt = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    dia_contrato = f'{dt_mat.day:02d}'
    mes_contrato = meses_pt.get(dt_mat.month, str(dt_mat.month))
    ano_contrato = str(dt_mat.year)

    # Uso de Imagem (Cláusula 11)
    autoriza_img = aluno.get('autoriza_imagem', 1)
    marca_sim = 'X' if autoriza_img == 1 else '  '
    marca_nao = 'X' if autoriza_img == 0 else '  '

    # 2. Configuração do Documento ReportLab
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=45,
        rightMargin=45,
        topMargin=40,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()

    cor_primaria = colors.HexColor('#1C2B24')      # Verde Floresta
    cor_dourada = colors.HexColor('#C5A059')       # Ouro Shanti
    cor_texto = colors.HexColor('#1e293b')         # Grafite Escuro
    cor_fundo_box = colors.HexColor('#F9F7F2')     # Areia Claro
    cor_borda = colors.HexColor('#E2DCD5')

    style_title = ParagraphStyle(
        'ContratoTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        alignment=1,
        textColor=cor_primaria,
        spaceAfter=4
    )

    style_subtitle = ParagraphStyle(
        'ContratoSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=10
    )

    style_clausula_tit = ParagraphStyle(
        'ClausulaTit',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=cor_primaria,
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True
    )

    style_corpo = ParagraphStyle(
        'CorpoTexto',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=cor_texto,
        spaceAfter=4,
        alignment=4 # Justificado
    )

    style_corpo_bold = ParagraphStyle(
        'CorpoBold',
        parent=style_corpo,
        fontName='Helvetica-Bold'
    )

    style_item = ParagraphStyle(
        'ItemLista',
        parent=style_corpo,
        leftIndent=12,
        spaceAfter=2
    )

    elements = []

    # Cabeçalho do Contrato
    elements.append(Paragraph('<b>CONTRATO DE PRESTAÇÃO DE SERVIÇOS DE YOGA</b>', style_title))
    elements.append(Paragraph('Documento Oficial de Matrícula e Termos de Adesão • Studio Shanti', style_subtitle))
    elements.append(HRFlowable(width='100%', thickness=1.5, color=cor_dourada, spaceBefore=0, spaceAfter=8))

    # Box de Qualificação das Partes
    qualificacao_data = [
        [
            Paragraph(
                '<b>CONTRATADA:</b> Studio Shanti — Natália de Carvalho Garufe<br/>'
                '<b>Endereço:</b> Rua Capitão Godoy, nº 150, Porto Novo, Além Paraíba/MG.<br/>'
                '<b>CPF:</b> 117.624.777-85',
                style_corpo
            ),
            Paragraph(
                f'<b>ALUNO(A):</b> <b>{nome_aluno}</b><br/>'
                f'<b>CPF:</b> {cpf_aluno}<br/>'
                f'<b>TELEFONE:</b> {telefone_aluno}',
                style_corpo
            )
        ]
    ]
    t_qualif = Table(qualificacao_data, colWidths=[250, 255])
    t_qualif.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_fundo_box),
        ('BOX', (0, 0), (-1, -1), 0.5, cor_borda),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, cor_borda),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(t_qualif)
    elements.append(Spacer(1, 6))

    # CLÁUSULA 1
    elements.append(Paragraph('<b>1. MATRÍCULA E MENSALIDADE</b>', style_clausula_tit))
    elements.append(Paragraph('A matrícula garante ao aluno a reserva de sua vaga no dia e horário escolhidos.', style_corpo))
    
    plano_box = [
        [
            Paragraph(f'<b>Plano contratado:</b><br/>( <b>{marca_1x}</b> ) 1x por semana — R$ 120,00<br/>( <b>{marca_2x}</b> ) 2x por semana — R$ 150,00', style_corpo),
            Paragraph(f'<b>Dia(s) e horário(s):</b><br/><b>{dias_horarios_str}</b>', style_corpo)
        ]
    ]
    t_plano = Table(plano_box, colWidths=[240, 265])
    t_plano.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_fundo_box),
        ('BOX', (0, 0), (-1, -1), 0.5, cor_borda),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t_plano)
    elements.append(Spacer(1, 4))
    elements.append(Paragraph('A primeira mensalidade será paga no momento da matrícula. A data desse primeiro pagamento será considerada o vencimento das mensalidades seguintes, mantendo-se o mesmo dia de cada mês.', style_corpo))
    elements.append(Paragraph('A mensalidade corresponde à reserva da vaga e à disponibilidade das aulas, não sendo uma cobrança por aula individual.', style_corpo))

    # CLÁUSULA 2
    elements.append(Paragraph('<b>2. AULAS EM GRUPO E NATUREZA DO SERVIÇO</b>', style_clausula_tit))
    elements.append(Paragraph('As aulas do Shanti são realizadas em grupo, com exercícios planejados e orientados para toda a turma, preservando a dinâmica da aula.', style_corpo))
    elements.append(Paragraph('Caso o aluno apresente dor, limitação ou dificuldade na realização de algum exercício, a professora poderá orientá-lo quanto à adaptação do próprio exercício, respeitando seus limites e sua segurança. Não serão elaborados exercícios diferentes ou individualizados exclusivamente para um aluno.', style_corpo))
    elements.append(Paragraph('A atividade contratada é exclusivamente Yoga em grupo, não constituindo atendimento, consulta ou tratamento fisioterapêutico, mesmo que a professora seja fisioterapeuta.', style_corpo))

    # CLÁUSULA 3
    elements.append(Paragraph('<b>3. OBRIGAÇÕES DO SHANTI</b>', style_clausula_tit))
    elements.append(Paragraph('O Shanti se compromete a:', style_corpo))
    elements.append(Paragraph('• oferecer as aulas de acordo com o plano, dia e horário contratados;', style_item))
    elements.append(Paragraph('• manter o ambiente limpo, organizado e adequado à prática;', style_item))
    elements.append(Paragraph('• orientar os alunos durante as aulas, respeitando as limitações informadas;', style_item))
    elements.append(Paragraph('• zelar pela segurança e pelo bom funcionamento das atividades;', style_item))
    elements.append(Paragraph('• tratar todos os alunos com respeito e cordialidade;', style_item))
    elements.append(Paragraph('• manter sigilo sobre informações pessoais e de saúde fornecidas pelo aluno;', style_item))
    elements.append(Paragraph('• comunicar, sempre que possível, alterações de horários ou calendário;', style_item))
    elements.append(Paragraph('• realizar reposição ou oferecer alternativa equivalente quando uma aula for cancelada por responsabilidade do Shanti ou da professora.', style_item))

    # CLÁUSULA 4
    elements.append(Paragraph('<b>4. PAGAMENTO E ATRASOS</b>', style_clausula_tit))
    elements.append(Paragraph('O pagamento deverá ser realizado até a data de vencimento.', style_corpo))
    elements.append(Paragraph('Em caso de atraso, poderão ser aplicados multa de 2% e juros de 1% ao mês, conforme a legislação aplicável.', style_corpo))
    elements.append(Paragraph('A inadimplência poderá resultar na suspensão da participação nas aulas até a regularização do pagamento.', style_corpo))

    # CLÁUSULA 5
    elements.append(Paragraph('<b>5. FALTAS DO ALUNO E REPOSIÇÃO</b>', style_clausula_tit))
    elements.append(Paragraph('A falta do aluno, por qualquer motivo, não gera desconto, abatimento ou direito automático à reposição.', style_corpo))
    elements.append(Paragraph('Excepcionalmente, o aluno poderá realizar uma reposição em outra turma, desde que exista vaga e mediante autorização da professora.', style_corpo))
    elements.append(Paragraph('As reposições não são acumulativas e não poderão ser utilizadas como crédito para meses seguintes.', style_corpo))

    # CLÁUSULA 6
    elements.append(Paragraph('<b>6. VIAGENS E AUSÊNCIAS</b>', style_clausula_tit))
    elements.append(Paragraph('Em caso de viagem ou ausência prolongada, o aluno poderá solicitar a manutenção de sua vaga mediante aviso prévio e pagamento de 70% da mensalidade durante o período de afastamento.', style_corpo))
    elements.append(Paragraph('Esse pagamento é referente à manutenção e reserva da vaga e não gera direito às aulas não realizadas.', style_corpo))

    # CLÁUSULA 7
    elements.append(Paragraph('<b>7. FALTAS DA PROFESSORA E FERIADOS</b>', style_clausula_tit))
    elements.append(Paragraph('Quando uma aula for cancelada por responsabilidade do Shanti ou da professora, será realizada reposição ou oferecida alternativa equivalente.', style_corpo))
    elements.append(Paragraph('Feriados não serão considerados falta da professora e não gerarão reposição ou desconto, de acordo com o funcionamento do Shanti.', style_corpo))

    # CLÁUSULA 8
    elements.append(Paragraph('<b>8. RECESSO DE NATAL E ANO NOVO</b>', style_clausula_tit))
    elements.append(Paragraph('O Shanti terá recesso exclusivamente no período de Natal e Ano Novo, em datas previamente comunicadas aos alunos.', style_corpo))
    elements.append(Paragraph('A mensalidade referente ao período será paga integralmente, não havendo desconto ou reposição em razão do recesso programado.', style_corpo))

    # CLÁUSULA 9
    elements.append(Paragraph('<b>9. CANCELAMENTO</b>', style_clausula_tit))
    elements.append(Paragraph('O aluno poderá solicitar o cancelamento da matrícula até 20 (vinte) dias antes da data de vencimento da mensalidade.', style_corpo))
    elements.append(Paragraph('Após esse prazo, a mensalidade do período será devida integralmente, mesmo que o aluno não participe das aulas.', style_corpo))
    elements.append(Paragraph('A simples ausência às aulas não caracteriza cancelamento. Enquanto a matrícula permanecer ativa e a vaga estiver reservada, a mensalidade continuará sendo devida.', style_corpo))

    # CLÁUSULA 10
    elements.append(Paragraph('<b>10. SAÚDE E SEGURANÇA</b>', style_clausula_tit))
    elements.append(Paragraph('O aluno deverá informar à professora qualquer condição de saúde prévia.', style_corpo))
    elements.append(Paragraph('O aluno deverá respeitar seus próprios limites e seguir as orientações dadas durante as aulas.', style_corpo))
    elements.append(Paragraph('O Shanti não promete resultados específicos de saúde, estética ou desempenho, pois estes dependem das características e da participação de cada aluno.', style_corpo))

    # CLÁUSULA 11
    elements.append(Paragraph('<b>11. USO DE IMAGEM</b>', style_clausula_tit))
    elements.append(Paragraph(
        f'Autorizo o uso da minha imagem para divulgação do Shanti: &nbsp;&nbsp;&nbsp;&nbsp;'
        f'( <b>{marca_sim}</b> ) <b>SIM</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
        f'( <b>{marca_nao}</b> ) <b>NÃO</b>',
        style_corpo
    ))

    # CLÁUSULA 12
    elements.append(Paragraph('<b>12. FORO</b>', style_clausula_tit))
    elements.append(Paragraph('Para dirimir quaisquer controvérsias oriundas do presente contrato, as partes elegem o foro da Comarca de Além Paraíba/MG, com renúncia expressa a qualquer outro, por mais privilegiado que seja.', style_corpo))

    # CLÁUSULA 13
    elements.append(Paragraph('<b>13. ACEITE</b>', style_clausula_tit))
    elements.append(Paragraph('Declaro que li e estou de acordo com as condições deste contrato, especialmente em relação a pagamentos, faltas, reposições, manutenção da vaga, viagens, feriados, recesso e cancelamento.', style_corpo))

    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f'Além Paraíba/MG, {dia_contrato} de {mes_contrato} de {ano_contrato}.', style_corpo_bold))
    elements.append(Spacer(1, 14))

    # Bloco de Assinaturas (duas vias / duas assinaturas)
    assinaturas_data = [
        [
            Paragraph(
                '____________________________________________<br/>'
                '<b>ALUNO(A):</b><br/>'
                f'Nome: <b>{nome_aluno}</b><br/>'
                f'CPF: {cpf_aluno}',
                style_corpo
            ),
            Paragraph(
                '____________________________________________<br/>'
                '<b>CONTRATADA — STUDIO SHANTI</b><br/>'
                '<b>NATÁLIA DE CARVALHO GARUFE</b><br/>'
                'CPF: 117.624.777-85',
                style_corpo
            )
        ]
    ]
    t_ass = Table(assinaturas_data, colWidths=[250, 255])
    t_ass.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(KeepTogether(t_ass))

    doc.build(elements, canvasmaker=ContractNumberedCanvas)
    buffer.seek(0)
    return buffer

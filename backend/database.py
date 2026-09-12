"""
Banco de dados SQLite e regras de negócio para o Yoga Studio App.
Gerencia alunos, pagamentos, inadimplência e geração de cobranças WhatsApp.
"""
import sqlite3
import os
import datetime
import urllib.parse
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yoga_studio.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa as tabelas do banco de dados e dados padrão se vazio."""
    conn = get_connection()
    cursor = conn.cursor()

    # Tabela de configurações do Studio
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracoes (
        chave TEXT PRIMARY KEY,
        valor TEXT
    )
    """)

    # Tabela de Alunos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alunos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        telefone TEXT NOT NULL,
        email TEXT,
        plano TEXT DEFAULT 'Mensal',
        dia_vencimento INTEGER NOT NULL DEFAULT 10,
        valor_mensalidade REAL NOT NULL DEFAULT 150.0,
        tipo_pagamento TEXT DEFAULT 'PIX',
        status TEXT NOT NULL DEFAULT 'ativo', -- 'ativo' ou 'inativo'
        data_matricula TEXT NOT NULL,
        mes_matricula TEXT,
        data_saida TEXT,
        motivo_saida TEXT,
        observacoes TEXT
    )
    """)
    
    try:
        cursor.execute("ALTER TABLE alunos ADD COLUMN mes_matricula TEXT")
    except sqlite3.OperationalError:
        pass # already exists

    # Tabela de Pagamentos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pagamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        mes_referencia TEXT NOT NULL, -- Ex: '2026-09'
        valor REAL NOT NULL,
        data_pagamento TEXT NOT NULL, -- 'YYYY-MM-DD'
        forma_pagamento TEXT NOT NULL, -- 'PIX', 'Cartão', 'Dinheiro', 'Boleto'
        status TEXT NOT NULL DEFAULT 'pago',
        FOREIGN KEY (aluno_id) REFERENCES alunos (id)
    )
    """)

    # Configurações padrão
    configs_padrao = [
        ("nome_studio", "Shanti Studio de Yoga"),
        ("chave_pix", "contato@shantiyoga.com.br"),
        ("tipo_chave_pix", "E-mail"),
        ("gemini_api_key", ""),
        ("mensagem_cobranca_padrao", 
         "Olá, {nome}! 🧘‍♀️ Passando para lembrar com carinho que sua mensalidade do {studio} venceu no dia {dia_vencimento}/{mes_atual} no valor de R$ {valor:.2f}.\n\nPara facilitar, segue nossa chave PIX ({tipo_chave}): {chave_pix}\n\nQualquer dúvida estamos à disposição! Namastê. 🙏")
    ]

    for chave, valor in configs_padrao:
        cursor.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, valor))

    # Verificar se já existem alunos, senão popular com exemplos realistas
    cursor.execute("SELECT COUNT(*) FROM alunos")
    total_alunos = cursor.fetchone()[0]

    if total_alunos == 0:
        hoje = datetime.date.today()
        mes_atual = hoje.strftime("%Y-%m")
        # mês passado
        primeiro_dia_deste_mes = hoje.replace(day=1)
        mes_passado = (primeiro_dia_deste_mes - datetime.timedelta(days=1)).strftime("%Y-%m")

        alunos_exemplo = [
            ("Camila Rodrigues", "11987654321", "camila@email.com", "Yoga Integral (2x/sem)", 5, 160.0, "PIX", "ativo", "2026-01-15", None, None, "Prefere aulas matutinas"),
            ("Juliana Santos", "11991234567", "juliana@email.com", "Hatha Yoga (3x/sem)", 10, 190.0, "PIX", "ativo", "2026-02-10", None, None, "Praticante intermediária"),
            ("Lucas Oliveira", "11976543210", "lucas@email.com", "Vinyasa Yoga (2x/sem)", 15, 160.0, "Cartão", "ativo", "2026-03-01", None, None, "Foco em flexibilidade"),
            ("Beatriz Mendes", "11983456789", "beatriz@email.com", "Yin Yoga (Livre)", 5, 230.0, "PIX", "ativo", "2025-11-20", None, None, "Problemas na lombar"),
            ("Rodrigo Ferreira", "11965432198", "rodrigo@email.com", "Hatha Yoga (2x/sem)", 20, 160.0, "Dinheiro", "ativo", "2026-04-12", None, None, "Paga em mãos"),
            ("Fernanda Costa", "11954321098", "fernanda@email.com", "Yoga Gestante", 10, 180.0, "PIX", "inativo", "2025-08-01", "2026-07-30", "Mudança de cidade", "Ganhou bebê")
        ]

        cursor.executemany("""
        INSERT INTO alunos (nome, telefone, email, plano, dia_vencimento, valor_mensalidade, tipo_pagamento, status, data_matricula, data_saida, motivo_saida, observacoes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, alunos_exemplo)

        # Inserir pagamentos do mês atual e mês passado
        # Camila (vence dia 5) -> Já pagou mês passado, mas NÃO pagou este mês (atrasada!)
        cursor.execute("INSERT INTO pagamentos (aluno_id, mes_referencia, valor, data_pagamento, forma_pagamento) VALUES (1, ?, 160.0, '2026-08-05', 'PIX')", (mes_passado,))
        
        # Juliana (vence dia 10) -> Pagou mês passado, NÃO pagou este mês se hoje for pós dia 10 (atrasada!)
        cursor.execute("INSERT INTO pagamentos (aluno_id, mes_referencia, valor, data_pagamento, forma_pagamento) VALUES (2, ?, 190.0, '2026-08-10', 'PIX')", (mes_passado,))
        
        # Lucas (vence dia 15) -> Pagou adiantado este mês!
        cursor.execute("INSERT INTO pagamentos (aluno_id, mes_referencia, valor, data_pagamento, forma_pagamento) VALUES (3, ?, 160.0, '2026-09-02', 'Cartão')", (mes_atual,))

        # Beatriz (vence dia 5) -> Pagou este mês em dia!
        cursor.execute("INSERT INTO pagamentos (aluno_id, mes_referencia, valor, data_pagamento, forma_pagamento) VALUES (4, ?, 230.0, '2026-09-05', 'PIX')", (mes_atual,))

    conn.commit()
    conn.close()

# --- Funções de Configurações ---

def obter_configuracoes() -> Dict[str, str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chave, valor FROM configuracoes")
    rows = cursor.fetchall()
    conn.close()
    return {row["chave"]: row["valor"] for row in rows}

def salvar_configuracao(chave: str, valor: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))
    conn.commit()
    conn.close()

# --- Funções de Alunos ---

def listar_alunos(status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM alunos WHERE status = ? ORDER BY nome ASC", (status,))
    else:
        cursor.execute("SELECT * FROM alunos ORDER BY status ASC, nome ASC")
    rows = cursor.fetchall()
    conn.close()

    alunos = [dict(row) for row in rows]
    # Enriquecer com status financeiro do mês atual
    hoje = datetime.date.today()
    mes_atual = hoje.strftime("%Y-%m")

    for al in alunos:
        if al["status"] == "inativo":
            al["situacao_financeira"] = "Inativo"
            al["dias_atraso"] = 0
            continue

        # Verificar se pagou o mês atual
        pagou = verificar_pagamento_mes(al["id"], mes_atual)
        al["pagou_mes_atual"] = pagou
        dia_venc = al["dia_vencimento"]
        
        data_matricula = al.get("data_matricula", "")
        mes_matricula = al.get("mes_matricula")
        if not mes_matricula and data_matricula:
            mes_matricula = data_matricula[:7]

        if pagou:
            al["situacao_financeira"] = "Em dia"
            al["dias_atraso"] = 0
        elif mes_matricula and mes_matricula > mes_atual:
            # Matrícula futura
            al["situacao_financeira"] = "Matrícula Futura"
            al["dias_atraso"] = 0
        elif hoje.day > dia_venc:
            # Verifica se matriculou no mes atual DEPOIS do vencimento
            if mes_matricula == mes_atual and len(data_matricula) >= 10 and int(data_matricula[8:10]) >= dia_venc:
                al["situacao_financeira"] = "Matrícula Recente (A pagar)"
                al["dias_atraso"] = 0
            else:
                dias_atraso = hoje.day - dia_venc
                al["situacao_financeira"] = f"Atrasado ({dias_atraso}d)"
                al["dias_atraso"] = dias_atraso
        elif hoje.day == dia_venc:
            al["situacao_financeira"] = "Vence hoje"
            al["dias_atraso"] = 0
        else:
            dias_restantes = dia_venc - hoje.day
            al["situacao_financeira"] = f"A vencer em {dias_restantes}d"
            al["dias_atraso"] = 0

    return alunos

def obter_aluno(aluno_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def cadastrar_aluno(dados: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    hoje = datetime.date.today()
    hoje_str = hoje.strftime("%Y-%m-%d")
    
    mes_matricula = dados.get("mes_matricula")
    if not mes_matricula:
        mes_matricula = hoje.strftime("%Y-%m")

    cursor.execute("""
    INSERT INTO alunos (nome, telefone, email, plano, dia_vencimento, valor_mensalidade, tipo_pagamento, status, data_matricula, mes_matricula, observacoes)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'ativo', ?, ?, ?)
    """, (
        dados.get("nome"),
        dados.get("telefone", ""),
        dados.get("email", ""),
        dados.get("plano", "Yoga Regular"),
        int(dados.get("dia_vencimento", 10)),
        float(dados.get("valor_mensalidade", 150.0)),
        dados.get("tipo_pagamento", "PIX"),
        dados.get("data_matricula", hoje_str),
        mes_matricula,
        dados.get("observacoes", "")
    ))
    aluno_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return aluno_id

def atualizar_aluno(aluno_id: int, dados: Dict[str, Any]):
    conn = get_connection()
    cursor = conn.cursor()
    campos = []
    valores = []
    for k, v in dados.items():
        if k not in ("id",):
            campos.append(f"{k} = ?")
            valores.append(v)
    valores.append(aluno_id)

    query = f"UPDATE alunos SET {', '.join(campos)} WHERE id = ?"
    cursor.execute(query, valores)
    conn.commit()
    conn.close()

def inativar_aluno(aluno_id: int, motivo: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    hoje_str = datetime.date.today().strftime("%Y-%m-%d")
    cursor.execute("""
    UPDATE alunos SET status = 'inativo', data_saida = ?, motivo_saida = ? WHERE id = ?
    """, (hoje_str, motivo, aluno_id))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def reativar_aluno(aluno_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE alunos SET status = 'ativo', data_saida = NULL, motivo_saida = NULL WHERE id = ?", (aluno_id,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

# --- Funções de Pagamento ---

def verificar_pagamento_mes(aluno_id: int, mes_referencia: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT COUNT(*) FROM pagamentos 
    WHERE aluno_id = ? AND mes_referencia = ? AND status = 'pago'
    """, (aluno_id, mes_referencia))
    pago = cursor.fetchone()[0] > 0
    conn.close()
    return pago

def registrar_pagamento(aluno_id: int, valor: float, forma_pagamento: str, mes_referencia: Optional[str] = None, data_pagamento: Optional[str] = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    hoje = datetime.date.today()
    if not mes_referencia:
        mes_referencia = hoje.strftime("%Y-%m")
    if not data_pagamento:
        data_pagamento = hoje.strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO pagamentos (aluno_id, mes_referencia, valor, data_pagamento, forma_pagamento, status)
    VALUES (?, ?, ?, ?, ?, 'pago')
    """, (aluno_id, mes_referencia, float(valor), data_pagamento, forma_pagamento))
    pagamento_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return pagamento_id

def listar_pagamentos_aluno(aluno_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pagamentos WHERE aluno_id = ? ORDER BY data_pagamento DESC", (aluno_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Consultas Estratégicas para IA e Relatórios ---

def obter_inadimplentes() -> List[Dict[str, Any]]:
    """Retorna alunos ativos cuja mensalidade já venceu no mês atual e ainda não foi paga."""
    alunos = listar_alunos(status="ativo")
    inadimplentes = []
    for al in alunos:
        if "Atrasado" in al.get("situacao_financeira", ""):
            inadimplentes.append(al)
    return inadimplentes

def obter_quantitativo() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM alunos WHERE status = 'ativo'")
    ativos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM alunos WHERE status = 'inativo'")
    inativos = cursor.fetchone()[0]

    # Novos inscritos neste mês
    hoje = datetime.date.today()
    mes_atual = hoje.strftime("%Y-%m")
    cursor.execute("SELECT COUNT(*) FROM alunos WHERE status = 'ativo' AND data_matricula LIKE ?", (f"{mes_atual}%",))
    novos_mes = cursor.fetchone()[0]

    # Saídas no mês
    cursor.execute("SELECT COUNT(*) FROM alunos WHERE status = 'inativo' AND data_saida LIKE ?", (f"{mes_atual}%",))
    saidas_mes = cursor.fetchone()[0]

    conn.close()

    # Inadimplentes atuais
    atrasados = len(obter_inadimplentes())

    return {
        "total_alunos": ativos + inativos,
        "alunos_ativos": ativos,
        "alunos_inativos": inativos,
        "novos_matriculados_mes": novos_mes,
        "saidas_mes": saidas_mes,
        "inadimplentes_mes": atrasados
    }

def obter_relatorio_mensal(mes_ano: Optional[str] = None) -> Dict[str, Any]:
    hoje = datetime.date.today()
    if not mes_ano:
        mes_ano = hoje.strftime("%Y-%m")

    conn = get_connection()
    cursor = conn.cursor()

    # Total recebido no mês
    cursor.execute("""
    SELECT SUM(valor) as total, COUNT(*) as qtd
    FROM pagamentos
    WHERE mes_referencia = ? AND status = 'pago'
    """, (mes_ano,))
    row_rec = cursor.fetchone()
    total_recebido = row_rec["total"] or 0.0
    qtd_pagamentos = row_rec["qtd"] or 0

    # Pagamentos por forma de pagamento
    cursor.execute("""
    SELECT forma_pagamento, SUM(valor) as total, COUNT(*) as qtd
    FROM pagamentos
    WHERE mes_referencia = ? AND status = 'pago'
    GROUP BY forma_pagamento
    """, (mes_ano,))
    por_forma = [dict(r) for r in cursor.fetchall()]

    # Previsão total de faturamento (soma de mensalidades dos alunos ativos)
    cursor.execute("SELECT SUM(valor_mensalidade) FROM alunos WHERE status = 'ativo'")
    faturamento_previsto = cursor.fetchone()[0] or 0.0

    conn.close()

    inadimplentes = obter_inadimplentes()
    total_inadimplente = sum(a["valor_mensalidade"] for a in inadimplentes)

    return {
        "mes_referencia": mes_ano,
        "faturamento_previsto": faturamento_previsto,
        "faturamento_realizado": total_recebido,
        "total_pendente_ou_atrasado": total_inadimplente,
        "qtd_pagamentos_recebidos": qtd_pagamentos,
        "por_forma_pagamento": por_forma,
        "total_alunos_atrasados": len(inadimplentes)
    }

def gerar_mensagens_cobranca(tipo: str = "atrasados") -> List[Dict[str, Any]]:
    """
    Gera o texto de lembrete personalizado e o link wa.me para cada aluno
    com mensalidade atrasada ou vencendo hoje.
    """
    configs = obter_configuracoes()
    studio_nome = configs.get("nome_studio", "Studio de Yoga")
    chave_pix = configs.get("chave_pix", "contato@suryayoga.com.br")
    tipo_chave = configs.get("tipo_chave_pix", "PIX")

    hoje = datetime.date.today()

    alunos = listar_alunos(status="ativo")
    notificacoes = []

    for al in alunos:
        situacao = al.get("situacao_financeira", "")
        deve_notificar = False
        if tipo == "atrasados" and "Atrasado" in situacao:
            deve_notificar = True
        elif tipo == "hoje" and "Vence hoje" in situacao:
            deve_notificar = True
        elif tipo == "todos_pendentes" and ("Atrasado" in situacao or "Vence hoje" in situacao):
            deve_notificar = True

        if deve_notificar:
            mensagem = (
                f"Olá, {al['nome']}! 🧘‍♀️ Passando para lembrar com carinho que sua mensalidade do {studio_nome} "
                f"venceu dia {al['dia_vencimento']:02d}/{hoje.month:02d} no valor de R$ {al['valor_mensalidade']:.2f}.\n\n"
                f"Para sua comodidade, você pode fazer o pagamento pela chave PIX ({tipo_chave}):\n"
                f"👉 *{chave_pix}*\n\n"
                f"Após efetuar, por gentileza nos envie o comprovante por aqui. Gratidão e ótimas práticas! Namastê. 🙏"
            )

            telefone_limpo = "".join(filter(str.isdigit, al.get("telefone", "")))
            if telefone_limpo and not telefone_limpo.startswith("55"):
                telefone_limpo = "55" + telefone_limpo

            link_whatsapp = f"https://wa.me/{telefone_limpo}?text={urllib.parse.quote(mensagem)}"

            notificacoes.append({
                "aluno_id": al["id"],
                "nome": al["nome"],
                "telefone": al["telefone"],
                "valor": al["valor_mensalidade"],
                "dia_vencimento": al["dia_vencimento"],
                "situacao": situacao,
                "dias_atraso": al.get("dias_atraso", 0),
                "mensagem": mensagem,
                "link_whatsapp": link_whatsapp
            })

    return notificacoes

# Inicializar ao importar
init_db()

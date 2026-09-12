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
        data_nascimento TEXT, -- 'YYYY-MM-DD' ou 'MM-DD'
        data_saida TEXT,
        motivo_saida TEXT,
        observacoes TEXT
    )
    """)
    
    try:
        cursor.execute("ALTER TABLE alunos ADD COLUMN mes_matricula TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE alunos ADD COLUMN data_nascimento TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE alunos ADD COLUMN autoriza_imagem INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    # Tabela de Turmas do Studio Shanti
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS turmas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        dias_semana TEXT NOT NULL,
        horario TEXT NOT NULL,
        capacidade_vagas INTEGER DEFAULT 12,
        plano_associado TEXT DEFAULT '2x na semana',
        ativo INTEGER DEFAULT 1,
        criado_em TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Tabela de Relação Matrículas - Turmas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS matriculas_turmas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        turma_id INTEGER NOT NULL,
        data_matricula TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (aluno_id) REFERENCES alunos (id) ON DELETE CASCADE,
        FOREIGN KEY (turma_id) REFERENCES turmas (id) ON DELETE CASCADE,
        UNIQUE(aluno_id, turma_id)
    )
    """)

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

    # Tabela de Frequência / Presença de Alunos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS frequencias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        data TEXT NOT NULL, -- 'YYYY-MM-DD'
        horario TEXT, -- Ex: '18:00'
        modalidade TEXT DEFAULT 'Yoga Regular',
        observacao TEXT,
        FOREIGN KEY (aluno_id) REFERENCES alunos (id)
    )
    """)

    # Tabela de Despesas do Estúdio
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS despesas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descricao TEXT NOT NULL,
        valor REAL NOT NULL,
        categoria TEXT DEFAULT 'Geral', -- 'Aluguel', 'Energia/Água', 'Materiais/Incensos', 'Marketing', 'Outros'
        data TEXT NOT NULL, -- 'YYYY-MM-DD'
        observacao TEXT
    )
    """)

    # Configurações padrão
    configs_padrao = [
        ("nome_studio", "Studio Shanti"),
        ("chave_pix", "contato@shantiyoga.com.br"),
        ("tipo_chave_pix", "E-mail"),
        ("gemini_api_key", ""),
        ("valor_plano_1x", "120.00"),
        ("valor_plano_2x", "150.00"),
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

    # Atualizar datas de nascimento se nulas
    cursor.execute("UPDATE alunos SET data_nascimento = '1995-09-18' WHERE id = 1 AND (data_nascimento IS NULL OR data_nascimento = '')")
    cursor.execute("UPDATE alunos SET data_nascimento = '1992-09-25' WHERE id = 2 AND (data_nascimento IS NULL OR data_nascimento = '')")
    cursor.execute("UPDATE alunos SET data_nascimento = '1990-10-12' WHERE id = 3 AND (data_nascimento IS NULL OR data_nascimento = '')")
    cursor.execute("UPDATE alunos SET data_nascimento = '1988-04-05' WHERE id = 4 AND (data_nascimento IS NULL OR data_nascimento = '')")
    cursor.execute("UPDATE alunos SET data_nascimento = '1985-11-20' WHERE id = 5 AND (data_nascimento IS NULL OR data_nascimento = '')")

    # Inserir despesas de exemplo se a tabela estiver vazia
    cursor.execute("SELECT COUNT(*) FROM despesas")
    if cursor.fetchone()[0] == 0:
        hoje = datetime.date.today()
        cursor.execute("INSERT INTO despesas (descricao, valor, categoria, data, observacao) VALUES ('Aluguel da Sala', 450.0, 'Aluguel', ?, 'Espaço principal')", (hoje.strftime("%Y-%m-05"),))
        cursor.execute("INSERT INTO despesas (descricao, valor, categoria, data, observacao) VALUES ('Incensos e Óleos Essenciais', 75.0, 'Materiais', ?, 'Lavanda e Sândalo')", (hoje.strftime("%Y-%m-08"),))
        cursor.execute("INSERT INTO despesas (descricao, valor, categoria, data, observacao) VALUES ('Energia Elétrica', 110.0, 'Energia/Água', ?, 'Conta do estúdio')", (hoje.strftime("%Y-%m-10"),))

    # Inserir frequências de exemplo se a tabela estiver vazia
    cursor.execute("SELECT COUNT(*) FROM frequencias")
    if cursor.fetchone()[0] == 0:
        hoje = datetime.date.today()
        ontem = (hoje - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        anteontem = (hoje - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
        doze_dias_atras = (hoje - datetime.timedelta(days=12)).strftime("%Y-%m-%d")

        # Camila e Lucas vieram recentemente
        cursor.execute("INSERT INTO frequencias (aluno_id, data, horario, modalidade) VALUES (1, ?, '08:00', 'Yoga Integral')", (ontem,))
        cursor.execute("INSERT INTO frequencias (aluno_id, data, horario, modalidade) VALUES (3, ?, '18:30', 'Vinyasa Yoga')", (ontem,))
        cursor.execute("INSERT INTO frequencias (aluno_id, data, horario, modalidade) VALUES (4, ?, '19:30', 'Yin Yoga')", (anteontem,))
        # Juliana não vem há 12 dias (aluna ausente / sumida)
        cursor.execute("INSERT INTO frequencias (aluno_id, data, horario, modalidade) VALUES (2, ?, '09:00', 'Hatha Yoga')", (doze_dias_atras,))

    # --- FASE 2: Turmas Oficiais do Studio Shanti ---
    turmas_oficiais = [
        ("Pequenos Yogis (Yoga para Crianças)", "Segunda e Quarta", "17:30", 12, "2x na semana"),
        ("Essência (Hatha Yoga para Adultos)", "Segunda e Quarta", "18:30", 12, "2x na semana"),
        ("Sunrise (Hatha Yoga para Adultos)", "Terça e Quinta", "06:00", 12, "2x na semana")
    ]

    for nome_t, dias_t, hora_t, cap_t, plano_t in turmas_oficiais:
        cursor.execute("SELECT id FROM turmas WHERE nome = ?", (nome_t,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO turmas (nome, dias_semana, horario, capacidade_vagas, plano_associado, ativo)
            VALUES (?, ?, ?, ?, ?, 1)
            """, (nome_t, dias_t, hora_t, cap_t, plano_t))

    # --- FASE 2: Migração de Planos e Valores Oficiais (1x R$120 / 2x R$150) ---
    cursor.execute("""
    UPDATE alunos 
    SET plano = '1x na semana', valor_mensalidade = 120.00 
    WHERE plano IN ('Yoga Gestante', 'Hatha Yoga', '1x na semana', '1x/sem')
    """)

    cursor.execute("""
    UPDATE alunos 
    SET plano = '2x na semana', valor_mensalidade = 150.00 
    WHERE plano NOT IN ('1x na semana')
    """)

    cursor.execute("UPDATE alunos SET autoriza_imagem = 1 WHERE autoriza_imagem IS NULL")

    # Matrículas iniciais nas turmas para demonstração do painel de vagas
    cursor.execute("SELECT COUNT(*) FROM matriculas_turmas")
    if cursor.fetchone()[0] == 0:
        cursor.execute("SELECT id, nome FROM turmas")
        t_map = {row["nome"]: row["id"] for row in cursor.fetchall()}
        
        # Essência: Camila (1), Juliana (2), Rodrigo (5)
        if "Essência (Hatha Yoga para Adultos)" in t_map:
            t_essencia = t_map["Essência (Hatha Yoga para Adultos)"]
            for aid in [1, 2, 5]:
                cursor.execute("INSERT OR IGNORE INTO matriculas_turmas (aluno_id, turma_id) VALUES (?, ?)", (aid, t_essencia))

        # Sunrise: Beatriz (4), Sofia (7), Bruno (9), Natalia (10)
        if "Sunrise (Hatha Yoga para Adultos)" in t_map:
            t_sunrise = t_map["Sunrise (Hatha Yoga para Adultos)"]
            for aid in [4, 7, 9, 10]:
                cursor.execute("INSERT OR IGNORE INTO matriculas_turmas (aluno_id, turma_id) VALUES (?, ?)", (aid, t_sunrise))

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

# --- Funções de Alunos e Turmas ---

def listar_alunos(status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM alunos WHERE status = ? ORDER BY nome ASC", (status,))
    else:
        cursor.execute("SELECT * FROM alunos ORDER BY status ASC, nome ASC")
    rows = cursor.fetchall()

    # Mapear turmas de todos os alunos
    cursor.execute("""
    SELECT mt.aluno_id, t.id as turma_id, t.nome, t.horario, t.dias_semana
    FROM matriculas_turmas mt
    JOIN turmas t ON t.id = mt.turma_id
    """)
    aluno_turmas_map = {}
    for r in cursor.fetchall():
        aid = r["aluno_id"]
        if aid not in aluno_turmas_map:
            aluno_turmas_map[aid] = []
        aluno_turmas_map[aid].append(dict(r))

    conn.close()

    alunos = [dict(row) for row in rows]
    # Enriquecer com status financeiro do mês atual e turmas
    hoje = datetime.date.today()
    mes_atual = hoje.strftime("%Y-%m")

    for al in alunos:
        al["turmas"] = aluno_turmas_map.get(al["id"], [])
        if "autoriza_imagem" not in al or al["autoriza_imagem"] is None:
            al["autoriza_imagem"] = 1

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
    if not row:
        conn.close()
        return None
    aluno = dict(row)
    if "autoriza_imagem" not in aluno or aluno["autoriza_imagem"] is None:
        aluno["autoriza_imagem"] = 1

    cursor.execute("""
    SELECT t.* FROM turmas t
    JOIN matriculas_turmas mt ON mt.turma_id = t.id
    WHERE mt.aluno_id = ?
    """, (aluno_id,))
    aluno["turmas"] = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return aluno

def cadastrar_aluno(dados: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    hoje = datetime.date.today()
    hoje_str = hoje.strftime("%Y-%m-%d")
    
    mes_matricula = dados.get("mes_matricula")
    if not mes_matricula:
        mes_matricula = hoje.strftime("%Y-%m")

    autoriza_img = dados.get("autoriza_imagem")
    if autoriza_img is None:
        autoriza_img = 1
    else:
        autoriza_img = int(autoriza_img)

    plano = dados.get("plano") or "2x na semana"
    # Se valor não informado, puxar padrão das configs
    valor = dados.get("valor_mensalidade")
    if valor is None:
        valor = 120.0 if "1x" in plano else 150.0

    cursor.execute("""
    INSERT INTO alunos (nome, telefone, email, plano, dia_vencimento, valor_mensalidade, tipo_pagamento, status, data_matricula, mes_matricula, observacoes, data_nascimento, autoriza_imagem)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'ativo', ?, ?, ?, ?, ?)
    """, (
        dados.get("nome"),
        dados.get("telefone", ""),
        dados.get("email", ""),
        plano,
        int(dados.get("dia_vencimento", 10)),
        float(valor),
        dados.get("tipo_pagamento", "PIX"),
        dados.get("data_matricula", hoje_str),
        mes_matricula,
        dados.get("observacoes", ""),
        dados.get("data_nascimento") or None,
        autoriza_img
    ))
    aluno_id = cursor.lastrowid

    turma_ids = dados.get("turma_ids")
    if turma_ids:
        for tid in turma_ids:
            cursor.execute("INSERT OR IGNORE INTO matriculas_turmas (aluno_id, turma_id) VALUES (?, ?)", (aluno_id, int(tid)))

    conn.commit()
    conn.close()
    return aluno_id

def atualizar_aluno(aluno_id: int, dados: Dict[str, Any]):
    conn = get_connection()
    cursor = conn.cursor()
    turma_ids = dados.pop("turma_ids", None)

    campos = []
    valores = []
    for k, v in dados.items():
        if k not in ("id",):
            campos.append(f"{k} = ?")
            valores.append(v)
    if campos:
        valores.append(aluno_id)
        query = f"UPDATE alunos SET {', '.join(campos)} WHERE id = ?"
        cursor.execute(query, valores)

    if turma_ids is not None:
        cursor.execute("DELETE FROM matriculas_turmas WHERE aluno_id = ?", (aluno_id,))
        for tid in turma_ids:
            cursor.execute("INSERT OR IGNORE INTO matriculas_turmas (aluno_id, turma_id) VALUES (?, ?)", (aluno_id, int(tid)))

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

def excluir_aluno(aluno_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM matriculas_turmas WHERE aluno_id = ?", (aluno_id,))
    cursor.execute("DELETE FROM frequencias WHERE aluno_id = ?", (aluno_id,))
    cursor.execute("DELETE FROM pagamentos WHERE aluno_id = ?", (aluno_id,))
    cursor.execute("DELETE FROM alunos WHERE id = ?", (aluno_id,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

# --- Funções de Turmas ---

def listar_turmas(ativas_somente: bool = True) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = """
    SELECT t.*, 
           COUNT(mt.aluno_id) as total_matriculados,
           (t.capacidade_vagas - COUNT(mt.aluno_id)) as vagas_disponiveis
    FROM turmas t
    LEFT JOIN matriculas_turmas mt ON mt.turma_id = t.id
    """
    if ativas_somente:
        query += " WHERE t.ativo = 1"
    query += " GROUP BY t.id ORDER BY t.horario ASC, t.nome ASC"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obter_turma(turma_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT t.*, 
           COUNT(mt.aluno_id) as total_matriculados,
           (t.capacidade_vagas - COUNT(mt.aluno_id)) as vagas_disponiveis
    FROM turmas t
    LEFT JOIN matriculas_turmas mt ON mt.turma_id = t.id
    WHERE t.id = ?
    GROUP BY t.id
    """, (turma_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def listar_alunos_turma(turma_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT a.*, mt.data_matricula as data_entrada_turma
    FROM alunos a
    JOIN matriculas_turmas mt ON mt.aluno_id = a.id
    WHERE mt.turma_id = ?
    ORDER BY a.nome ASC
    """, (turma_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def matricular_aluno_turma(aluno_id: int, turma_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO matriculas_turmas (aluno_id, turma_id) VALUES (?, ?)", (aluno_id, turma_id))
        conn.commit()
        ok = cursor.rowcount > 0
    except:
        ok = False
    finally:
        conn.close()
    return ok

def desmatricular_aluno_turma(aluno_id: int, turma_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM matriculas_turmas WHERE aluno_id = ? AND turma_id = ?", (aluno_id, turma_id))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

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

    # Despesas do mês
    cursor.execute("""
    SELECT SUM(valor) as total, COUNT(*) as qtd
    FROM despesas
    WHERE data LIKE ?
    """, (f"{mes_ano}%",))
    row_desp = cursor.fetchone()
    total_despesas = row_desp["total"] or 0.0
    qtd_despesas = row_desp["qtd"] or 0

    cursor.execute("""
    SELECT categoria, SUM(valor) as total, COUNT(*) as qtd
    FROM despesas
    WHERE data LIKE ?
    GROUP BY categoria
    """, (f"{mes_ano}%",))
    despesas_por_categoria = [dict(r) for r in cursor.fetchall()]

    conn.close()

    inadimplentes = obter_inadimplentes()
    total_inadimplente = sum(a["valor_mensalidade"] for a in inadimplentes)
    lucro_liquido = total_recebido - total_despesas

    return {
        "mes_referencia": mes_ano,
        "faturamento_previsto": faturamento_previsto,
        "faturamento_realizado": total_recebido,
        "total_pendente_ou_atrasado": total_inadimplente,
        "total_despesas": total_despesas,
        "lucro_liquido_real": lucro_liquido,
        "qtd_pagamentos_recebidos": qtd_pagamentos,
        "qtd_despesas": qtd_despesas,
        "por_forma_pagamento": por_forma,
        "despesas_por_categoria": despesas_por_categoria,
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

# --- Gestão de Frequência e Presença ---

def registrar_presenca(aluno_id: int, data: Optional[str] = None, horario: Optional[str] = None, modalidade: str = "Yoga Regular", observacao: str = "") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    if not data:
        data = datetime.date.today().strftime("%Y-%m-%d")
    if not horario:
        horario = datetime.datetime.now().strftime("%H:%M")

    cursor.execute("""
    INSERT INTO frequencias (aluno_id, data, horario, modalidade, observacao)
    VALUES (?, ?, ?, ?, ?)
    """, (aluno_id, data, horario, modalidade, observacao))
    freq_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return freq_id

def listar_presencas(aluno_id: Optional[int] = None, data: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = """
    SELECT f.*, a.nome as aluno_nome, a.telefone as aluno_telefone, a.plano as aluno_plano
    FROM frequencias f
    JOIN alunos a ON a.id = f.aluno_id
    WHERE 1=1
    """
    params = []
    if aluno_id:
        query += " AND f.aluno_id = ?"
        params.append(aluno_id)
    if data:
        query += " AND f.data = ?"
        params.append(data)
    query += " ORDER BY f.data DESC, f.horario DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obter_alunos_ausentes(dias_sem_aula: int = 10, dias: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Identifica alunos ativos que não comparecem a nenhuma aula há mais de X dias,
    gerando mensagem carinhosa de acolhimento para o WhatsApp.
    """
    if dias is not None:
        dias_sem_aula = dias
    configs = obter_configuracoes()
    studio_nome = configs.get("nome_studio", "Studio de Yoga")
    alunos = listar_alunos(status="ativo")
    conn = get_connection()
    cursor = conn.cursor()
    hoje = datetime.date.today()

    ausentes = []
    for al in alunos:
        cursor.execute("SELECT MAX(data) as ultima_data FROM frequencias WHERE aluno_id = ?", (al["id"],))
        row = cursor.fetchone()
        ultima_data_str = row["ultima_data"] if row else None

        if ultima_data_str:
            try:
                dt_ult = datetime.date.fromisoformat(ultima_data_str)
                dias = (hoje - dt_ult).days
            except:
                dias = 0
        else:
            try:
                dt_mat = datetime.date.fromisoformat(al["data_matricula"])
                dias = (hoje - dt_mat).days
            except:
                dias = 15

        if dias >= dias_sem_aula:
            msg = (
                f"Olá, {al['nome']}! 🌸 Sentimos sua falta em nossas práticas no {studio_nome}! "
                f"Como você está? Está tudo bem por aí?\n\n"
                f"O seu tapetinho e nossa energia continuam sempre te esperando. "
                f"Conta pra gente se podemos te ajudar com novos horários ou modalidades! Namastê. 🙏🧘‍♀️"
            )
            telefone_limpo = "".join(filter(str.isdigit, al.get("telefone", "")))
            if telefone_limpo and not telefone_limpo.startswith("55"):
                telefone_limpo = "55" + telefone_limpo

            link_whatsapp = f"https://wa.me/{telefone_limpo}?text={urllib.parse.quote(msg)}"

            ausentes.append({
                "aluno_id": al["id"],
                "nome": al["nome"],
                "telefone": al["telefone"],
                "plano": al["plano"],
                "dias_ausente": dias,
                "ultima_presenca": ultima_data_str or "Nenhuma registrada",
                "mensagem": msg,
                "link_whatsapp": link_whatsapp
            })

    conn.close()
    return sorted(ausentes, key=lambda x: x["dias_ausente"], reverse=True)

# --- Gestão de Despesas do Estúdio ---

def registrar_despesa(descricao: str, valor: float, categoria: str = "Geral", data: Optional[str] = None, observacao: str = "") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    if not data:
        data = datetime.date.today().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO despesas (descricao, valor, categoria, data, observacao)
    VALUES (?, ?, ?, ?, ?)
    """, (descricao.strip(), float(valor), categoria.strip(), data, observacao.strip()))
    desp_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return desp_id

def listar_despesas(mes_ano: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if mes_ano:
        cursor.execute("SELECT * FROM despesas WHERE data LIKE ? ORDER BY data DESC, id DESC", (f"{mes_ano}%",))
    else:
        cursor.execute("SELECT * FROM despesas ORDER BY data DESC, id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def excluir_despesa(despesa_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM despesas WHERE id = ?", (despesa_id,))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

# --- Aniversariantes do Mês ---

def obter_aniversariantes_mes(mes: Optional[int] = None) -> List[Dict[str, Any]]:
    hoje = datetime.date.today()
    if not mes:
        mes = hoje.month

    configs = obter_configuracoes()
    studio_nome = configs.get("nome_studio", "Studio de Yoga")
    alunos = listar_alunos(status="ativo")

    aniversariantes = []
    for al in alunos:
        nasc = al.get("data_nascimento")
        if not nasc or len(nasc) < 5:
            continue
        try:
            nasc_limpo = str(nasc).strip().replace('/', '-')
            partes = nasc_limpo.split("-")
            m = None
            d = None
            if len(partes) == 3:
                # Se YYYY-MM-DD:
                if len(partes[0]) == 4:
                    m = int(partes[1])
                    d = int(partes[2])
                else:
                    # Se DD-MM-YYYY:
                    d = int(partes[0])
                    m = int(partes[1])
            elif len(partes) == 2:
                # Se DD-MM:
                d = int(partes[0])
                m = int(partes[1])
            else:
                continue

            if m == mes:
                e_hoje = (d == hoje.day and m == hoje.month)
                msg = (
                    f"Feliz Aniversário, {al['nome']}! 🎂🎉✨\n\n"
                    f"Toda a equipe e comunidade do {studio_nome} deseja a você um novo ciclo repleto de saúde, "
                    f"paz profunda, harmonia e muita luz no seu caminho!\n\n"
                    f"Que sua prática continue nutrindo seu corpo e mente. Parabéns pelo seu dia! Namastê. 🙏🌸"
                )
                tel_limpo = "".join(filter(str.isdigit, str(al.get("telefone", ""))))
                if tel_limpo and not tel_limpo.startswith("55"):
                    tel_limpo = "55" + tel_limpo
                link_wa = f"https://wa.me/{tel_limpo}?text={urllib.parse.quote(msg)}"

                aniversariantes.append({
                    "aluno_id": al["id"],
                    "nome": al["nome"],
                    "telefone": al["telefone"],
                    "plano": al.get("plano", "Yoga Regular"),
                    "dia": d,
                    "mes": m,
                    "data_nascimento": nasc,
                    "e_hoje": e_hoje,
                    "ja_fez": d < hoje.day if m == hoje.month else (m < hoje.month),
                    "mensagem": msg,
                    "link_whatsapp": link_wa
                })
        except Exception as err:
            continue

    return sorted(aniversariantes, key=lambda x: (not x.get("e_hoje", False), x["dia"]))

# --- Comprovante / Recibo de Pagamento no WhatsApp ---

def gerar_comprovante_pagamento(pagamento_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT p.*, a.nome, a.telefone, a.plano
    FROM pagamentos p
    JOIN alunos a ON a.id = p.aluno_id
    WHERE p.id = ?
    """, (pagamento_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    p = dict(row)
    configs = obter_configuracoes()
    studio_nome = configs.get("nome_studio", "Studio de Yoga")

    data_fmt = p["data_pagamento"]
    try:
        dt = datetime.date.fromisoformat(p["data_pagamento"])
        data_fmt = dt.strftime("%d/%m/%Y")
    except:
        pass

    msg = (
        f"🧾 *COMPROVANTE DE PAGAMENTO - {studio_nome}* 🧘‍♀️\n\n"
        f"Namastê, *{p['nome']}*! 🙏\n"
        f"Confirmamos com gratidão o recebimento da sua mensalidade:\n\n"
        f"• *Plano:* {p['plano']}\n"
        f"• *Referência:* Mês {p['mes_referencia']}\n"
        f"• *Valor:* R$ {p['valor']:.2f}\n"
        f"• *Forma de Pagamento:* {p['forma_pagamento']}\n"
        f"• *Data do Pagamento:* {data_fmt}\n\n"
        f"A sua mensalidade está 100% quitada. Gratidão imensa pela sua confiança e energia em nosso Studio! ✨🕉️"
    )

    tel_limpo = "".join(filter(str.isdigit, p.get("telefone", "")))
    if tel_limpo and not tel_limpo.startswith("55"):
        tel_limpo = "55" + tel_limpo

    link_wa = f"https://wa.me/{tel_limpo}?text={urllib.parse.quote(msg)}"

    return {
        "pagamento_id": p["id"],
        "aluno": p["nome"],
        "aluno_nome": p["nome"],
        "valor": p["valor"],
        "forma_pagamento": p["forma_pagamento"],
        "mes_referencia": p["mes_referencia"],
        "mensagem": msg,
        "texto_recibo": msg,
        "link_whatsapp": link_wa
    }

# Inicializar ao importar
init_db()

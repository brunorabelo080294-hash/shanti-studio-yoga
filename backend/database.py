"""
Banco de dados SQLite e regras de negócio para o Yoga Studio App.
Gerencia alunos, pagamentos, inadimplência e geração de cobranças WhatsApp.
"""
import sqlite3
import os
import datetime
import calendar
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
        observacoes TEXT,
        autoriza_imagem INTEGER DEFAULT 1,
        dia_semana_1x TEXT
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

    try:
        cursor.execute("ALTER TABLE alunos ADD COLUMN dia_semana_1x TEXT")
    except sqlite3.OperationalError:
        pass

    # --- FASE 4: Colunas para CPF, Contratos Digitais e Aprovação de Matrícula ---
    for col_def in [
        ("cpf", "TEXT"),
        ("aprovacao_pagamento", "TEXT DEFAULT 'aprovado'"),
        ("contrato_pdf_gerado", "TEXT"),
        ("contrato_assinado_arquivo", "TEXT"),
        ("data_assinatura_contrato", "TEXT"),
        ("data_vigencia_contrato", "TEXT"),
        ("status_contrato", "TEXT DEFAULT 'pendente'"),
        ("autentique_doc_id", "TEXT"),
        ("autentique_status", "TEXT"),
        ("autentique_link", "TEXT"),
        ("autentique_link_natalia", "TEXT"),
        ("autentique_enviado_em", "TEXT"),
        ("pausar_alerta_ausencia", "INTEGER DEFAULT 0"),
        ("motivo_pausa_alerta", "TEXT")
    ]:
        try:
            cursor.execute(f"ALTER TABLE alunos ADD COLUMN {col_def[0]} {col_def[1]}")
        except sqlite3.OperationalError:
            pass

    # Tabela de Histórico e Auditoria de Contratos Autentique
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contratos_autentique (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        autentique_doc_id TEXT UNIQUE,
        status TEXT DEFAULT 'aguardando_assinaturas',
        link_aluno TEXT,
        link_natalia TEXT,
        sandbox INTEGER DEFAULT 1,
        arquivo_local TEXT,
        criado_em TEXT,
        atualizado_em TEXT,
        FOREIGN KEY (aluno_id) REFERENCES alunos (id) ON DELETE CASCADE
    )
    """)

    # Tabela de Turmas do Studio Shanti
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS turmas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        dias_semana TEXT NOT NULL,
        horario TEXT NOT NULL,
        capacidade_vagas INTEGER DEFAULT 16,
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

    # Tabela de Histórico de Presença das Turmas (Calendário & Check-in)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historico_presenca (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        turma_id INTEGER NOT NULL,
        data TEXT NOT NULL, -- 'YYYY-MM-DD'
        status TEXT NOT NULL DEFAULT 'pendente', -- 'pendente', 'presente', 'faltou'
        justificativa TEXT,
        atualizado_em TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (aluno_id) REFERENCES alunos (id) ON DELETE CASCADE,
        FOREIGN KEY (turma_id) REFERENCES turmas (id) ON DELETE CASCADE,
        UNIQUE(aluno_id, turma_id, data)
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
        data_vencimento TEXT, -- 'YYYY-MM-DD'
        status TEXT DEFAULT 'pago', -- 'pago', 'pendente'
        observacao TEXT
    )
    """)

    # Tabela de Diagnóstico e Observabilidade do Sistema (Render vs. Gemini)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs_diagnostico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT DEFAULT (datetime('now', 'localtime')),
        tipo_evento TEXT NOT NULL, -- 'chat', 'atalho', 'audio', 'ping_keepalive', 'teste_diagnostico'
        status_servidor TEXT DEFAULT 'ok', -- 'ok', 'lento', 'iniciando'
        status_ia TEXT DEFAULT 'nao_aplicavel', -- 'ok', 'lento', 'erro', 'local', 'chave_ausente'
        servidor_cold_start INTEGER DEFAULT 0, -- 1 se cold start (<3 min), 0 se quente
        tempo_servidor_ms INTEGER DEFAULT 0,
        tempo_ia_ms INTEGER DEFAULT 0,
        sucesso INTEGER DEFAULT 1,
        mensagem_erro TEXT,
        detalhes TEXT
    )
    """)

    # Configurações padrão
    configs_padrao = [
        ("nome_studio", "Studio Shanti"),
        ("chave_pix", "contato@shantiyoga.com.br"),
        ("tipo_chave_pix", "E-mail"),
        ("groq_api_key", ""),
        ("ai_provider", "groq"),
        ("groq_model", "qwen/qwen3.8-27b"),
        ("gemini_api_key", ""),
        ("valor_plano_1x", "120.00"),
        ("valor_plano_2x", "150.00"),
        ("autentique_api_token", "fc2c3926514c154c5f25a5baa6dc32a95455135b0fcd52b278599ce6c4a36f6c"),
        ("autentique_sandbox", "true"),
        ("telefone_natalia", "22988423287"),
        ("email_natalia", "nataliagarufeyoga@gmail.com"),
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

    # --- FASE 2: Turmas Oficiais do Studio Shanti (Capacidade Máxima: 16 alunos) ---
    turmas_oficiais = [
        ("Pequenos Yogis (Yoga para Crianças)", "Segunda e Quarta", "17:30", 16, "2x na semana"),
        ("Essência (Hatha Yoga para Adultos)", "Segunda e Quarta", "18:30", 16, "2x na semana"),
        ("Sunrise (Hatha Yoga para Adultos)", "Terça e Quinta", "06:00", 16, "2x na semana")
    ]

    for nome_t, dias_t, hora_t, cap_t, plano_t in turmas_oficiais:
        cursor.execute("SELECT id FROM turmas WHERE nome = ?", (nome_t,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO turmas (nome, dias_semana, horario, capacidade_vagas, plano_associado, ativo)
            VALUES (?, ?, ?, ?, ?, 1)
            """, (nome_t, dias_t, hora_t, cap_t, plano_t))

    # Atualizar capacidade das turmas para 16 alunos
    cursor.execute("UPDATE turmas SET capacidade_vagas = 16 WHERE capacidade_vagas != 16 OR capacidade_vagas IS NULL")

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

    # Migração segura para tabela despesas (data_vencimento e status)
    try:
        cursor.execute("ALTER TABLE despesas ADD COLUMN data_vencimento TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE despesas ADD COLUMN status TEXT DEFAULT 'pago'")
    except Exception:
        pass
    cursor.execute("UPDATE despesas SET data_vencimento = data WHERE data_vencimento IS NULL OR data_vencimento = ''")
    cursor.execute("UPDATE despesas SET status = 'pago' WHERE status IS NULL OR status = ''")

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

    dia_semana_1x = dados.get("dia_semana_1x") or ""
    cpf = dados.get("cpf") or ""
    aprovacao_pagamento = dados.get("aprovacao_pagamento") or "aprovado"

    cursor.execute("""
    INSERT INTO alunos (nome, telefone, email, plano, dia_vencimento, valor_mensalidade, tipo_pagamento, status, data_matricula, mes_matricula, observacoes, data_nascimento, autoriza_imagem, dia_semana_1x, cpf, aprovacao_pagamento)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'ativo', ?, ?, ?, ?, ?, ?, ?, ?)
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
        autoriza_img,
        dia_semana_1x,
        cpf,
        aprovacao_pagamento
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
           COUNT(mt.aluno_id) as total_matriculados
    FROM turmas t
    LEFT JOIN matriculas_turmas mt ON mt.turma_id = t.id
    """
    if ativas_somente:
        query += " WHERE t.ativo = 1"
    query += " GROUP BY t.id ORDER BY t.horario ASC, t.nome ASC"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    resultado = []
    for r in rows:
        d = dict(r)
        total = d.get("total_matriculados", 0)
        capacidade = d.get("capacidade_vagas", 16) or 16
        d["capacidade_vagas"] = capacidade
        d["total_matriculados"] = total
        d["vagas_disponiveis"] = max(0, capacidade - total)
        d["lotada"] = total >= capacidade
        d["quase_lotada"] = (total == capacidade - 1)
        resultado.append(d)
    return resultado

def obter_turma(turma_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT t.*, 
           COUNT(mt.aluno_id) as total_matriculados
    FROM turmas t
    LEFT JOIN matriculas_turmas mt ON mt.turma_id = t.id
    WHERE t.id = ?
    GROUP BY t.id
    """, (turma_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    total = d.get("total_matriculados", 0)
    capacidade = d.get("capacidade_vagas", 16) or 16
    d["capacidade_vagas"] = capacidade
    d["total_matriculados"] = total
    d["vagas_disponiveis"] = max(0, capacidade - total)
    d["lotada"] = total >= capacidade
    d["quase_lotada"] = (total == capacidade - 1)
    return d

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

def listar_pagamentos_mes(mes_ano: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retorna a lista detalhada de todos os pagamentos confirmados de um mês/ano,
    incluindo o nome do aluno, telefone, plano, dia de aula (para plano 1x) e forma de pagamento.
    """
    hoje = datetime.date.today()
    if not mes_ano:
        mes_ano = hoje.strftime("%Y-%m")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT p.id, p.aluno_id, p.mes_referencia, p.valor, p.data_pagamento, p.forma_pagamento, p.status,
           a.nome as aluno_nome, a.telefone as aluno_telefone, a.plano as aluno_plano, a.dia_semana_1x
    FROM pagamentos p
    JOIN alunos a ON a.id = p.aluno_id
    WHERE (p.mes_referencia = ? OR p.data_pagamento LIKE ?) AND p.status = 'pago'
    ORDER BY p.data_pagamento ASC, a.nome ASC
    """, (mes_ano, f"{mes_ano}%"))
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
    pagamentos_detalhados = listar_pagamentos_mes(mes_ano)

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
        "total_alunos_atrasados": len(inadimplentes),
        "pagamentos_detalhados": pagamentos_detalhados
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
    Unificado com o módulo Calendário:
    - Respeita alunos com alerta pausado (pausar_alerta_ausencia = 1).
    - Considera presenças de ambas as tabelas (frequencias e historico_presenca com status='presente').
    - Status 'Pendente' NUNCA é contado como falta.
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
        # Pular alunos com alerta pausado (ex: viagem comunicada)
        if al.get("pausar_alerta_ausencia"):
            continue

        cursor.execute("""
            SELECT MAX(d) as ultima_data FROM (
                SELECT data as d FROM frequencias WHERE aluno_id = ?
                UNION
                SELECT data as d FROM historico_presenca WHERE aluno_id = ? AND status = 'presente'
            )
        """, (al["id"], al["id"]))
        row = cursor.fetchone()
        ultima_data_str = row["ultima_data"] if row else None

        if ultima_data_str:
            try:
                dt_ult = datetime.date.fromisoformat(ultima_data_str)
                dias_calculados = (hoje - dt_ult).days
            except:
                dias_calculados = 0
        else:
            try:
                dt_mat = datetime.date.fromisoformat(al["data_matricula"])
                dias_calculados = (hoje - dt_mat).days
            except:
                dias_calculados = 15

        if dias_calculados >= dias_sem_aula:
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
                "dias_ausente": dias_calculados,
                "ultima_presenca": ultima_data_str or "Nenhuma registrada",
                "mensagem": msg,
                "link_whatsapp": link_whatsapp
            })

    conn.close()
    return sorted(ausentes, key=lambda x: x["dias_ausente"], reverse=True)

# --- Módulo Calendário, Check-in de Turmas & Retenção Acolhedora ---

def parse_dias_semana(dias_str: Optional[str]) -> List[int]:
    """
    Converte texto de dias da semana em índices inteiros (0=Segunda ... 6=Domingo).
    Ex: 'Segunda e Quarta' -> [0, 2]; 'Terça e Quinta' -> [1, 3].
    """
    if not dias_str:
        return []
    texto = dias_str.lower()
    dias = set()
    mapeamento = [
        (0, ["segunda", "seg"]),
        (1, ["terça", "terca", "ter"]),
        (2, ["quarta", "qua"]),
        (3, ["quinta", "qui"]),
        (4, ["sexta", "sex"]),
        (5, ["sábado", "sabado", "sab"]),
        (6, ["domingo", "dom"])
    ]
    for dia_idx, termos in mapeamento:
        for termo in termos:
            if termo in texto:
                dias.add(dia_idx)
                break
    return sorted(list(dias))

def obter_grade_calendario_mes(ano: int, mes: int) -> Dict[str, Any]:
    """
    Calcula a grade do calendário para o mês/ano fornecido.
    Identifica quais dias possuem turmas ativas programadas e o status consolidado de presenças.
    """
    num_dias = calendar.monthrange(ano, mes)[1]
    turmas_ativas = listar_turmas(ativas_somente=True)

    turmas_com_dias = []
    for t in turmas_ativas:
        t_dias = parse_dias_semana(t.get("dias_semana"))
        turmas_com_dias.append({
            "id": t["id"],
            "nome": t["nome"],
            "horario": t["horario"],
            "capacidade": t["capacidade_vagas"],
            "total_matriculados": t["total_matriculados"],
            "dias_indices": t_dias
        })

    prefixo_mes = f"{ano:04d}-{mes:02d}-%"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT data, status, COUNT(*) as qtd
        FROM historico_presenca
        WHERE data LIKE ?
        GROUP BY data, status
    """, (prefixo_mes,))
    
    stats_por_data = {}
    for r in cursor.fetchall():
        d_str = r["data"]
        st = r["status"]
        if d_str not in stats_por_data:
            stats_por_data[d_str] = {"presente": 0, "faltou": 0, "pendente": 0}
        stats_por_data[d_str][st] = r["qtd"]
    conn.close()

    dias_com_aula = []
    total_aulas_mes = 0
    total_presencas_mes = 0
    total_faltas_mes = 0

    hoje_str = datetime.date.today().strftime("%Y-%m-%d")

    for dia in range(1, num_dias + 1):
        dt = datetime.date(ano, mes, dia)
        w = dt.weekday()
        dt_str = dt.strftime("%Y-%m-%d")

        turmas_do_dia = [t for t in turmas_com_dias if w in t["dias_indices"]]
        if turmas_do_dia:
            total_aulas_mes += len(turmas_do_dia)
            total_esperados = sum(t["total_matriculados"] for t in turmas_do_dia)
            
            p_count = stats_por_data.get(dt_str, {}).get("presente", 0)
            f_count = stats_por_data.get(dt_str, {}).get("faltou", 0)
            
            total_presencas_mes += p_count
            total_faltas_mes += f_count

            checado = p_count + f_count
            if checado == 0:
                status_dia = "pendente"
            elif total_esperados > 0 and checado >= total_esperados:
                status_dia = "concluido"
            else:
                status_dia = "parcial"

            dias_com_aula.append({
                "data": dt_str,
                "dia": dia,
                "dia_semana_idx": w,
                "turmas_count": len(turmas_do_dia),
                "turmas_nomes": [t["nome"] for t in turmas_do_dia],
                "turmas_detalhes": [{"id": t["id"], "nome": t["nome"], "horario": t["horario"], "total_matriculados": t["total_matriculados"]} for t in turmas_do_dia],
                "total_esperados": total_esperados,
                "presentes": p_count,
                "faltas": f_count,
                "pendentes": max(0, total_esperados - checado),
                "status_dia": status_dia,
                "eh_hoje": (dt_str == hoje_str)
            })

    return {
        "ano": ano,
        "mes": mes,
        "dias_com_aula": dias_com_aula,
        "turmas": turmas_ativas,
        "resumo_mes": {
            "total_dias_com_aula": len(dias_com_aula),
            "total_aulas": total_aulas_mes,
            "total_presencas": total_presencas_mes,
            "total_faltas": total_faltas_mes
        }
    }

def obter_chamada_dia(data_str: str) -> Dict[str, Any]:
    """
    Retorna a lista de chamada para uma data específica.
    Agrupa por turma ativa que tenha aula naquele dia da semana.
    Cada aluno traz seu status ('pendente', 'presente', 'faltou').
    """
    try:
        dt = datetime.date.fromisoformat(data_str)
    except Exception:
        dt = datetime.date.today()
        data_str = dt.strftime("%Y-%m-%d")

    w = dt.weekday()
    dias_semana_nomes = [
        "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
        "Sexta-feira", "Sábado", "Domingo"
    ]
    dia_semana_nome = dias_semana_nomes[w]

    turmas_ativas = listar_turmas(ativas_somente=True)
    turmas_do_dia = [t for t in turmas_ativas if w in parse_dias_semana(t.get("dias_semana"))]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT aluno_id, turma_id, status, justificativa, atualizado_em
        FROM historico_presenca
        WHERE data = ?
    """, (data_str,))
    presencas_map = {}
    for r in cursor.fetchall():
        presencas_map[(r["aluno_id"], r["turma_id"])] = dict(r)

    resultado_turmas = []
    total_esperados = 0
    total_presentes = 0
    total_faltas = 0
    total_pendentes = 0

    for t in turmas_do_dia:
        tid = t["id"]
        cursor.execute("""
            SELECT a.id, a.nome, a.telefone, a.plano, a.dia_semana_1x,
                   COALESCE(a.pausar_alerta_ausencia, 0) as pausar_alerta_ausencia,
                   COALESCE(a.motivo_pausa_alerta, '') as motivo_pausa_alerta,
                   mt.data_matricula
            FROM alunos a
            JOIN matriculas_turmas mt ON mt.aluno_id = a.id
            WHERE mt.turma_id = ? AND a.status = 'ativo'
            ORDER BY a.nome ASC
        """, (tid,))
        alunos_brutos = [dict(r) for r in cursor.fetchall()]

        alunos_turma = []
        for al in alunos_brutos:
            dias_1x = parse_dias_semana(al.get("dia_semana_1x")) if al.get("dia_semana_1x") else []
            if dias_1x and (w not in dias_1x):
                continue

            reg = presencas_map.get((al["id"], tid))
            st = reg["status"] if reg else "pendente"
            just = reg["justificativa"] if reg else ""

            if st == "presente":
                total_presentes += 1
            elif st == "faltou":
                total_faltas += 1
            else:
                total_pendentes += 1
            total_esperados += 1

            alunos_turma.append({
                "aluno_id": al["id"],
                "nome": al["nome"],
                "telefone": al["telefone"],
                "plano": al["plano"],
                "dia_semana_1x": al.get("dia_semana_1x") or "",
                "status": st,
                "justificativa": just,
                "pausar_alerta_ausencia": bool(al["pausar_alerta_ausencia"]),
                "motivo_pausa_alerta": al["motivo_pausa_alerta"]
            })

        t_presentes = sum(1 for a in alunos_turma if a["status"] == "presente")
        t_faltas = sum(1 for a in alunos_turma if a["status"] == "faltou")
        t_pendentes = sum(1 for a in alunos_turma if a["status"] == "pendente")

        resultado_turmas.append({
            "turma_id": t["id"],
            "nome": t["nome"],
            "horario": t["horario"],
            "capacidade_vagas": t["capacidade_vagas"],
            "total_matriculados": len(alunos_turma),
            "presentes": t_presentes,
            "faltas": t_faltas,
            "pendentes": t_pendentes,
            "alunos": alunos_turma
        })

    conn.close()

    return {
        "data": data_str,
        "dia_semana_nome": dia_semana_nome,
        "eh_hoje": (data_str == datetime.date.today().strftime("%Y-%m-%d")),
        "turmas": resultado_turmas,
        "totais": {
            "esperados": total_esperados,
            "presentes": total_presentes,
            "faltas": total_faltas,
            "pendentes": total_pendentes
        }
    }

def salvar_status_presenca(aluno_id: int, turma_id: int, data_str: str, status: str, justificativa: str = "") -> Dict[str, Any]:
    """
    Grava ou atualiza o status de presença ('pendente', 'presente', 'faltou') de um aluno em uma turma e data.
    Mantém compatibilidade com a tabela legada 'frequencias' quando status='presente'.
    """
    if status not in ("pendente", "presente", "faltou"):
        status = "pendente"

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO historico_presenca (aluno_id, turma_id, data, status, justificativa, atualizado_em)
        VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
        ON CONFLICT(aluno_id, turma_id, data) DO UPDATE SET
            status = excluded.status,
            justificativa = excluded.justificativa,
            atualizado_em = datetime('now', 'localtime')
    """, (aluno_id, turma_id, data_str, status, justificativa))

    # Sincronizar compatibilidade com tabela legada 'frequencias'
    if status == "presente":
        cursor.execute("SELECT id FROM frequencias WHERE aluno_id = ? AND data = ?", (aluno_id, data_str))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO frequencias (aluno_id, data, horario, modalidade, observacao)
                VALUES (?, ?, (SELECT horario FROM turmas WHERE id = ?), (SELECT nome FROM turmas WHERE id = ?), 'Check-in Calendário')
            """, (aluno_id, data_str, turma_id, turma_id))
    else:
        cursor.execute("""
            DELETE FROM frequencias 
            WHERE aluno_id = ? AND data = ? AND observacao = 'Check-in Calendário'
        """, (aluno_id, data_str))

    conn.commit()
    conn.close()

    return {
        "sucesso": True,
        "aluno_id": aluno_id,
        "turma_id": turma_id,
        "data": data_str,
        "status": status,
        "justificativa": justificativa
    }

def marcar_todos_presentes_turma(turma_id: int, data_str: str) -> Dict[str, Any]:
    """
    Ação rápida: marca todos os alunos esperados daquela turma naquele dia como 'presente'.
    """
    chamada = obter_chamada_dia(data_str)
    turma_selecionada = None
    for t in chamada.get("turmas", []):
        if t["turma_id"] == turma_id:
            turma_selecionada = t
            break

    if not turma_selecionada:
        return {"sucesso": False, "mensagem": "Turma não encontrada para este dia."}

    qtd = 0
    for al in turma_selecionada.get("alunos", []):
        salvar_status_presenca(al["aluno_id"], turma_id, data_str, "presente")
        qtd += 1

    return {"sucesso": True, "total_marcados": qtd, "turma_id": turma_id, "data": data_str}

def alternar_pausa_alerta(aluno_id: int, pausar: bool, motivo: str = "") -> bool:
    """
    Ativa ou desativa a pausa de alertas de ausência para um aluno específico (ex: aviso de viagem/férias).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE alunos
        SET pausar_alerta_ausencia = ?,
            motivo_pausa_alerta = ?
        WHERE id = ?
    """, (1 if pausar else 0, motivo, aluno_id))
    ok = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return ok

def obter_alunos_retencao_ausentes(dias_janela: int = 14) -> List[Dict[str, Any]]:
    """
    Identifica alunos em risco de evasão baseado em FALTAS EXPLÍCITAS nas aulas programadas.
    
    REGRA MANDATÓRIA:
    - 'Pendente' NUNCA conta como falta.
    - Gatilho: 2 ou mais faltas explícitas registradas nas aulas previstas nos últimos 14 dias E zero presenças.
    - Se o aluno avisou viagem/férias (pausar_alerta_ausencia = 1), o alerta é marcado como pausado.
    """
    conn = get_connection()
    cursor = conn.cursor()
    hoje = datetime.date.today()
    data_limite = hoje - datetime.timedelta(days=dias_janela)
    data_limite_str = data_limite.strftime("%Y-%m-%d")
    hoje_str = hoje.strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT a.id, a.nome, a.telefone, a.plano, a.dia_semana_1x,
               COALESCE(a.pausar_alerta_ausencia, 0) as pausar_alerta_ausencia,
               COALESCE(a.motivo_pausa_alerta, '') as motivo_pausa_alerta,
               a.data_matricula
        FROM alunos a 
        WHERE a.status = 'ativo'
        ORDER BY a.nome ASC
    """)
    alunos = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT mt.aluno_id, t.id as turma_id, t.nome, t.horario, t.dias_semana
        FROM matriculas_turmas mt
        JOIN turmas t ON t.id = mt.turma_id
        WHERE t.ativo = 1
    """)
    aluno_turmas_map = {}
    for r in cursor.fetchall():
        aid = r["aluno_id"]
        if aid not in aluno_turmas_map:
            aluno_turmas_map[aid] = []
        aluno_turmas_map[aid].append(dict(r))

    cursor.execute("""
        SELECT aluno_id, turma_id, data, status
        FROM historico_presenca
        WHERE data >= ? AND data <= ?
    """, (data_limite_str, hoje_str))
    presencas_map = {}
    for r in cursor.fetchall():
        presencas_map[(r["aluno_id"], r["data"])] = r["status"]

    cursor.execute("""
        SELECT aluno_id, data FROM frequencias
        WHERE data >= ? AND data <= ?
    """, (data_limite_str, hoje_str))
    frequencias_periodo = {(r["aluno_id"], r["data"]) for r in cursor.fetchall()}

    resultado = []

    for al in alunos:
        aid = al["id"]
        turmas_aluno = aluno_turmas_map.get(aid, [])
        if not turmas_aluno:
            continue

        dias_aulas_previstas = []
        dias_1x = parse_dias_semana(al.get("dia_semana_1x")) if al.get("dia_semana_1x") else []

        for delta in range(dias_janela, 0, -1):
            d = hoje - datetime.timedelta(days=delta)
            w = d.weekday()
            tem_aula = False
            for t in turmas_aluno:
                dias_t = parse_dias_semana(t["dias_semana"])
                if w in dias_t:
                    if dias_1x:
                        if w in dias_1x:
                            tem_aula = True
                            break
                    else:
                        tem_aula = True
                        break
            if tem_aula:
                dias_aulas_previstas.append(d.strftime("%Y-%m-%d"))

        if not dias_aulas_previstas:
            continue

        faltas_explicitas = 0
        presencas = 0
        datas_faltas = []

        for dt_str in dias_aulas_previstas:
            st = presencas_map.get((aid, dt_str))
            if not st and (aid, dt_str) in frequencias_periodo:
                st = "presente"

            if st == "presente":
                presencas += 1
            elif st == "faltou":
                faltas_explicitas += 1
                datas_faltas.append(dt_str)

        if presencas == 0 and faltas_explicitas >= 2:
            cursor.execute("""
                SELECT MAX(d) as ult_data FROM (
                    SELECT data as d FROM historico_presenca WHERE aluno_id = ? AND status = 'presente'
                    UNION
                    SELECT data as d FROM frequencias WHERE aluno_id = ?
                )
            """, (aid, aid))
            ult_row = cursor.fetchone()
            ult_presenca_str = ult_row["ult_data"] if ult_row and ult_row["ult_data"] else "Nenhuma registrada"

            pausado = bool(al["pausar_alerta_ausencia"])

            msg = (
                f"Oi {al['nome']}, tudo bem? 🧘‍♀️ "
                f"Sentimos sua falta nas aulas aqui no estúdio nas últimas semanas! Está tudo bem com você? "
                f"Quando puder, me avisa se precisa reagendar seus dias para não perder o ritmo da sua prática. Namastê! 🙏"
            )
            telefone_limpo = "".join(filter(str.isdigit, al.get("telefone", "")))
            if telefone_limpo and not telefone_limpo.startswith("55"):
                telefone_limpo = "55" + telefone_limpo

            link_whatsapp = f"https://wa.me/{telefone_limpo}?text={urllib.parse.quote(msg)}"

            resultado.append({
                "aluno_id": aid,
                "nome": al["nome"],
                "telefone": al["telefone"],
                "plano": al["plano"],
                "turmas": [t["nome"] for t in turmas_aluno],
                "faltas_consecutivas": faltas_explicitas,
                "aulas_previstas": len(dias_aulas_previstas),
                "datas_faltas": datas_faltas,
                "ultima_presenca": ult_presenca_str,
                "pausado": pausado,
                "motivo_pausa": al["motivo_pausa_alerta"] or "",
                "mensagem": msg,
                "link_whatsapp": link_whatsapp
            })

    conn.close()
    return sorted(resultado, key=lambda x: (x["pausado"], -x["faltas_consecutivas"]))

# --- Gestão de Despesas do Estúdio ---

def registrar_despesa(descricao: str, valor: float, categoria: str = "Geral", data: Optional[str] = None, observacao: str = "", data_vencimento: Optional[str] = None, status: str = "pago") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    hoje_str = datetime.date.today().strftime("%Y-%m-%d")
    if not data:
        data = hoje_str
    if not data_vencimento:
        data_vencimento = data
    if not status:
        status = "pago"

    cursor.execute("""
    INSERT INTO despesas (descricao, valor, categoria, data, data_vencimento, status, observacao)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (descricao.strip(), float(valor), categoria.strip(), data, data_vencimento, status, observacao.strip()))
    desp_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return desp_id

def obter_despesa(despesa_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM despesas WHERE id = ?", (despesa_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def atualizar_despesa(despesa_id: int, dados: Dict[str, Any]) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    campos = []
    valores = []
    for k, v in dados.items():
        if k in ("descricao", "valor", "categoria", "data", "data_vencimento", "status", "observacao"):
            campos.append(f"{k} = ?")
            valores.append(float(v) if k == "valor" else str(v).strip())
    if not campos:
        conn.close()
        return False
    valores.append(despesa_id)
    query = f"UPDATE despesas SET {', '.join(campos)} WHERE id = ?"
    cursor.execute(query, valores)
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

def listar_despesas(mes_ano: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if mes_ano:
        cursor.execute("SELECT * FROM despesas WHERE (data LIKE ? OR data_vencimento LIKE ?) ORDER BY data_vencimento DESC, data DESC, id DESC", (f"{mes_ano}%", f"{mes_ano}%"))
    else:
        cursor.execute("SELECT * FROM despesas ORDER BY data_vencimento DESC, data DESC, id DESC")
    rows = cursor.fetchall()
    conn.close()

    hoje = datetime.date.today()
    resultado = []
    for r in rows:
        d = dict(r)
        venc_str = d.get("data_vencimento") or d.get("data")
        st = d.get("status") or "pago"
        d["status"] = st
        try:
            dt_venc = datetime.datetime.strptime(venc_str, "%Y-%m-%d").date()
            diff = (dt_venc - hoje).days
            d["dias_para_vencer"] = diff
            if st == "pago":
                d["situacao_vencimento"] = "pago"
            elif diff < 0:
                d["situacao_vencimento"] = "vencida"
            elif diff == 0:
                d["situacao_vencimento"] = "vence_hoje"
            else:
                d["situacao_vencimento"] = "a_vencer"
        except Exception:
            d["dias_para_vencer"] = 0
            d["situacao_vencimento"] = st
        resultado.append(d)
    return resultado

def excluir_despesa(despesa_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM despesas WHERE id = ?", (despesa_id,))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

def obter_alertas_despesas() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    hoje = datetime.date.today()

    cursor.execute("SELECT * FROM despesas WHERE status = 'pendente' ORDER BY data_vencimento ASC")
    rows = cursor.fetchall()
    conn.close()

    pendentes = []
    vencidas = []
    vence_hoje = []
    a_vencer_breve = []

    for r in rows:
        d = dict(r)
        venc_str = d.get("data_vencimento") or d.get("data")
        try:
            dt_venc = datetime.datetime.strptime(venc_str, "%Y-%m-%d").date()
            diff = (dt_venc - hoje).days
            d["dias_para_vencer"] = diff
            if diff < 0:
                d["situacao"] = "vencida"
                vencidas.append(d)
            elif diff == 0:
                d["situacao"] = "vence_hoje"
                vence_hoje.append(d)
            elif diff <= 5:
                d["situacao"] = "a_vencer"
                a_vencer_breve.append(d)
            else:
                d["situacao"] = "no_prazo"
        except Exception:
            d["dias_para_vencer"] = 0
            d["situacao"] = "pendente"
        pendentes.append(d)

    valor_vencidas = sum(d.get("valor", 0.0) for d in vencidas)
    valor_hoje = sum(d.get("valor", 0.0) for d in vence_hoje)
    valor_a_vencer = sum(d.get("valor", 0.0) for d in a_vencer_breve)

    return {
        "total_pendentes": len(pendentes),
        "total_vencidas": len(vencidas),
        "total_atrasadas": len(vencidas),
        "total_vence_hoje": len(vence_hoje),
        "total_vencendo_hoje": len(vence_hoje),
        "total_a_vencer": len(a_vencer_breve),
        "total_proximas": len(a_vencer_breve),
        "valor_total_pendente": sum(d.get("valor", 0.0) for d in pendentes),
        "valor_total_atrasadas": valor_vencidas,
        "valor_total_hoje": valor_hoje,
        "valor_total_proximas": valor_a_vencer,
        "vencidas": vencidas,
        "vence_hoje": vence_hoje,
        "a_vencer_breve": a_vencer_breve,
        "todas_pendentes": pendentes
    }

def listar_turmas_com_alunos(ativas_somente: bool = True) -> List[Dict[str, Any]]:
    turmas = listar_turmas(ativas_somente=ativas_somente)
    for t in turmas:
        alunos_brutos = listar_alunos_turma(t["id"])
        t["alunos"] = [
            {
                "id": a["id"],
                "nome": a["nome"],
                "telefone": a.get("telefone", ""),
                "plano": a.get("plano", ""),
                "dia_semana_1x": a.get("dia_semana_1x") or "",
                "status": a.get("status", "ativo"),
                "data_entrada_turma": a.get("data_entrada_turma", "")
            }
            for a in alunos_brutos
        ]
    return turmas

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

# --- FASE 4: Gestão de Contratos Digitais, Matrícula Pública & 'Entrou, Pagou' ---

def cadastrar_matricula_publica(dados: Dict[str, Any]) -> int:
    """
    Cadastra um novo aluno vindo do formulário público online (/matricula).
    O aluno é inserido com aprovacao_pagamento = 'pendente' aguardando validação da Natália.
    """
    dados_cad = dict(dados)
    dados_cad["aprovacao_pagamento"] = "pendente"
    dados_cad["status_contrato"] = "pendente"
    return cadastrar_aluno(dados_cad)

def aprovar_matricula_pagamento(aluno_id: int, forma_pagamento: str = "PIX") -> Dict[str, Any]:
    """
    Regra 'Entrou, Pagou':
    A Natália aprova o pagamento da matrícula do aluno.
    Automaticamente:
    1. Marca aprovacao_pagamento = 'aprovado'
    2. Lança a primeira mensalidade na tabela pagamentos como 'pago' para a competência atual.
    """
    aluno = obter_aluno(aluno_id)
    if not aluno:
        raise ValueError(f"Aluno com ID {aluno_id} não encontrado.")

    hoje = datetime.date.today()
    mes_atual = hoje.strftime("%Y-%m")
    hoje_str = hoje.strftime("%Y-%m-%d")

    # Registrar pagamento inicial ("Entrou, Pagou")
    valor = float(aluno.get("valor_mensalidade", 150.0))
    pagamento_id = registrar_pagamento(
        aluno_id=aluno_id,
        valor=valor,
        forma_pagamento=forma_pagamento or "PIX",
        mes_referencia=mes_atual,
        data_pagamento=hoje_str
    )

    # Atualizar status de aprovação
    atualizar_aluno(aluno_id, {
        "aprovacao_pagamento": "aprovado"
    })

    return {
        "sucesso": True,
        "aluno_id": aluno_id,
        "aluno_nome": aluno.get("nome"),
        "aprovacao_pagamento": "aprovado",
        "pagamento_id": pagamento_id,
        "valor": valor,
        "mes_referencia": mes_atual,
        "forma_pagamento": forma_pagamento,
        "mensagem": f"Pagamento da 1ª mensalidade de {aluno.get('nome')} aprovado com sucesso! Matrícula ativada ('Entrou, Pagou')."
    }

def obter_matriculas_pendentes() -> List[Dict[str, Any]]:
    """
    Retorna todos os alunos cadastrados cuja matrícula/1ª mensalidade ainda está 
    pendente de aprovação da Natália ('Entrou, Pagou').
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.* 
        FROM alunos a
        WHERE a.aprovacao_pagamento = 'pendente' AND a.status = 'ativo'
        ORDER BY a.id DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    configs = obter_configuracoes()
    studio_nome = configs.get("nome_studio", "Studio Shanti")

    resultado = []
    for r in rows:
        al = dict(r)
        tel_limpo = "".join(filter(str.isdigit, str(al.get("telefone", ""))))
        if tel_limpo and not tel_limpo.startswith("55"):
            tel_limpo = "55" + tel_limpo
        
        msg = (
            f"Olá {al['nome']}! 🧘‍♀️ Aqui é a Natália do {studio_nome}.\n\n"
            f"Recebemos sua ficha de matrícula no plano {al.get('plano', 'Yoga')}! "
            f"Gostaria de confirmar o recebimento do seu comprovante PIX de R$ {al.get('valor_mensalidade', 0):.2f} "
            f"para já deixar sua vaga garantida e aprovada no estúdio. Namastê! 🙏"
        )
        link_wa = f"https://wa.me/{tel_limpo}?text={urllib.parse.quote(msg)}"
        al["link_whatsapp"] = link_wa
        resultado.append(al)

    return resultado

def listar_contratos(filtro: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista todos os alunos ativos e o status detalhado de seus contratos:
    - pendente: sem o arquivo com as duas assinaturas anexado.
    - em_dia: assinado por ambas as partes e com vigência superior a 30 dias.
    - a_vencer: assinado, porém faltando 30 dias ou menos para completar o ciclo de 1 ano.
    - vencido: vigência expirada (mais de 1 ano).
    """
    alunos = listar_alunos(status="ativo")
    hoje = datetime.date.today()
    contratos = []

    for al in alunos:
        assinado_arquivo = al.get("contrato_assinado_arquivo") or ""
        tem_arquivo = bool(assinado_arquivo.strip())
        data_assinatura = al.get("data_assinatura_contrato") or ""
        data_vigencia_str = al.get("data_vigencia_contrato") or ""

        # Formatar turmas
        turmas_nomes = [t["nome"] for t in al.get("turmas", [])]
        turmas_str = ", ".join(turmas_nomes) if turmas_nomes else "Sem turma associada"

        if not tem_arquivo:
            status = "pendente"
            status_label = "Pendente de Assinatura"
            dias_restantes = None
            data_vigencia_exibicao = "-"
        else:
            # Calcular vigência
            if data_vigencia_str:
                try:
                    dt_vig = datetime.date.fromisoformat(data_vigencia_str)
                except Exception:
                    dt_vig = hoje + datetime.timedelta(days=365)
            elif data_assinatura:
                try:
                    dt_ass = datetime.date.fromisoformat(data_assinatura)
                    dt_vig = dt_ass + datetime.timedelta(days=365)
                except Exception:
                    dt_vig = hoje + datetime.timedelta(days=365)
            else:
                dt_vig = hoje + datetime.timedelta(days=365)

            data_vigencia_exibicao = dt_vig.strftime("%d/%m/%Y")
            dias_restantes = (dt_vig - hoje).days

            if dias_restantes < 0:
                status = "vencido"
                status_label = f"Vencido há {abs(dias_restantes)} dias"
            elif dias_restantes <= 30:
                status = "a_vencer"
                status_label = f"Vence em {dias_restantes} dias"
            else:
                status = "em_dia"
                status_label = f"Em dia ({dias_restantes} dias restantes)"

        c_item = {
            "id": al["id"],
            "aluno_id": al["id"],
            "nome": al["nome"],
            "telefone": al["telefone"],
            "cpf": al.get("cpf") or "Não informado",
            "plano": al.get("plano") or "2x na semana",
            "dia_semana_1x": al.get("dia_semana_1x") or "",
            "turmas_str": turmas_str,
            "data_matricula": al.get("data_matricula"),
            "data_assinatura": data_assinatura,
            "data_vigencia": data_vigencia_exibicao,
            "data_vigencia_contrato": al.get("data_vigencia_contrato"),
            "dias_restantes": dias_restantes,
            "status_contrato": status,
            "status_label": status_label,
            "tem_arquivo_assinado": tem_arquivo,
            "arquivo_assinado": assinado_arquivo,
            "contrato_assinado_arquivo": assinado_arquivo,
            "aprovacao_pagamento": al.get("aprovacao_pagamento") or "aprovado",
            "autentique_doc_id": al.get("autentique_doc_id") or "",
            "autentique_status": al.get("autentique_status") or "",
            "autentique_link": al.get("autentique_link") or "",
            "autentique_link_natalia": al.get("autentique_link_natalia") or "",
            "autentique_enviado_em": al.get("autentique_enviado_em") or ""
        }

        if not filtro or filtro == "todos" or status == filtro:
            contratos.append(c_item)

    # Ordenação estratégica: primeiro os 'a_vencer', depois 'pendente', 'vencido', e por fim 'em_dia'
    ordem_status = {"a_vencer": 0, "vencido": 1, "pendente": 2, "em_dia": 3}
    return sorted(contratos, key=lambda x: (ordem_status.get(x["status_contrato"], 4), x.get("dias_restantes") or 999, x["nome"]))

def obter_alertas_contratos() -> Dict[str, Any]:
    """
    Retorna métricas consolidadas e listas de alunos para o painel de Contratos e para a IA.
    """
    contratos = listar_contratos()
    pendentes = [c for c in contratos if c["status_contrato"] == "pendente"]
    a_vencer = [c for c in contratos if c["status_contrato"] == "a_vencer"]
    vencidos = [c for c in contratos if c["status_contrato"] == "vencido"]
    em_dia = [c for c in contratos if c["status_contrato"] == "em_dia"]

    return {
        "total_geral": len(contratos),
        "total_pendentes": len(pendentes),
        "total_a_vencer": len(a_vencer),
        "total_vencidos": len(vencidos),
        "total_em_dia": len(em_dia),
        "pendentes": len(pendentes),
        "a_vencer": len(a_vencer),
        "vencidos": len(vencidos),
        "em_dia": len(em_dia),
        "alunos_a_vencer": a_vencer,
        "alunos_pendentes": pendentes,
        "alunos_vencidos": vencidos
    }

def salvar_contrato_assinado(aluno_id: int, caminho_arquivo: str) -> bool:
    """
    Registra que o documento final com as DUAS assinaturas (Natália + Aluno) foi anexado.
    Calcula automaticamente a vigência de 1 ano e define o status como 'em_dia'.
    """
    hoje = datetime.date.today()
    hoje_str = hoje.strftime("%Y-%m-%d")
    vigencia_str = (hoje + datetime.timedelta(days=365)).strftime("%Y-%m-%d")

    atualizar_aluno(aluno_id, {
        "contrato_assinado_arquivo": caminho_arquivo,
        "data_assinatura_contrato": hoje_str,
        "data_vigencia_contrato": vigencia_str,
        "status_contrato": "em_dia"
    })
    return True

def remover_contrato_assinado(aluno_id: int) -> bool:
    """Remove a vinculação do contrato assinado, retornando para 'pendente'."""
    atualizar_aluno(aluno_id, {
        "contrato_assinado_arquivo": "",
        "status_contrato": "pendente"
    })
    return True

# --- Funções de Gestão de Contratos Autentique ---

def obter_aluno_por_autentique_doc_id(doc_id: str) -> Optional[Dict[str, Any]]:
    """Localiza o aluno associado a um document_id do Autentique."""
    if not doc_id:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alunos WHERE autentique_doc_id = ?", (doc_id,))
    row = cursor.fetchone()
    if not row:
        # Tentar pela tabela de histórico
        cursor.execute("SELECT aluno_id FROM contratos_autentique WHERE autentique_doc_id = ? ORDER BY id DESC LIMIT 1", (doc_id,))
        row_hist = cursor.fetchone()
        if row_hist:
            cursor.execute("SELECT * FROM alunos WHERE id = ?", (row_hist["aluno_id"],))
            row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def registrar_disparo_autentique(
    aluno_id: int,
    doc_id: str,
    link_aluno: str = "",
    link_natalia: str = "",
    sandbox: bool = True
) -> bool:
    """Registra o envio do contrato no Autentique na tabela alunos e no histórico de contratos."""
    agora_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    atualizar_aluno(aluno_id, {
        "autentique_doc_id": doc_id,
        "autentique_status": "aguardando_natalia",
        "autentique_link": link_aluno,
        "autentique_link_natalia": link_natalia,
        "autentique_enviado_em": agora_str
    })

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO contratos_autentique (aluno_id, autentique_doc_id, status, link_aluno, link_natalia, sandbox, criado_em, atualizado_em)
        VALUES (?, ?, 'aguardando_assinaturas', ?, ?, ?, ?, ?)
        ON CONFLICT(autentique_doc_id) DO UPDATE SET
            status = excluded.status,
            link_aluno = excluded.link_aluno,
            link_natalia = excluded.link_natalia,
            atualizado_em = excluded.atualizado_em
    """, (aluno_id, doc_id, link_aluno, link_natalia, 1 if sandbox else 0, agora_str, agora_str))
    conn.commit()
    conn.close()
    return True

def concluir_contrato_autentique(aluno_id: int, doc_id: str, caminho_arquivo: str) -> bool:
    """
    Conclui o fluxo do Autentique:
    - Vincula o PDF assinado oficial
    - Define vigência de 1 ano e status 'em_dia'
    - Atualiza autentique_status para 'assinado'
    """
    hoje = datetime.date.today()
    hoje_str = hoje.strftime("%Y-%m-%d")
    vigencia_str = (hoje + datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    agora_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    atualizar_aluno(aluno_id, {
        "contrato_assinado_arquivo": caminho_arquivo,
        "data_assinatura_contrato": hoje_str,
        "data_vigencia_contrato": vigencia_str,
        "status_contrato": "em_dia",
        "autentique_status": "assinado"
    })

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE contratos_autentique
        SET status = 'assinado', arquivo_local = ?, atualizado_em = ?
        WHERE autentique_doc_id = ?
    """, (caminho_arquivo, agora_str, doc_id))
    conn.commit()
    conn.close()
    return True

def atualizar_status_autentique(identificador: Any, status: str) -> bool:
    """
    Atualiza o status/etapa do contrato Autentique.
    Aceita tanto aluno_id (int ou numérico) quanto autentique_doc_id (hash ou string).
    """
    agora_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()
    if isinstance(identificador, int) or (isinstance(identificador, str) and identificador.isdigit()):
        aluno_id = int(identificador)
        cursor.execute("UPDATE alunos SET autentique_status = ? WHERE id = ?", (status, aluno_id))
        cursor.execute("UPDATE contratos_autentique SET status = ?, atualizado_em = ? WHERE aluno_id = ?", (status, agora_str, aluno_id))
    else:
        doc_id = str(identificador)
        cursor.execute("UPDATE alunos SET autentique_status = ? WHERE autentique_doc_id = ?", (status, doc_id))
        cursor.execute("UPDATE contratos_autentique SET status = ?, atualizado_em = ? WHERE autentique_doc_id = ?", (status, agora_str, doc_id))
    conn.commit()
    conn.close()
    return True

# =============================================================================
# DIAGNÓSTICO E OBSERVABILIDADE (RENDER VS. GEMINI)
# =============================================================================

def registrar_log_diagnostico(
    tipo_evento: str,
    status_servidor: str = "ok",
    status_ia: str = "nao_aplicavel",
    servidor_cold_start: int = 0,
    tempo_servidor_ms: int = 0,
    tempo_ia_ms: int = 0,
    sucesso: int = 1,
    mensagem_erro: Optional[str] = None,
    detalhes: Optional[str] = None
) -> int:
    """Registra evento de diagnóstico e garante retenção automática dos últimos 200 registros."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        agora_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO logs_diagnostico (
                timestamp, tipo_evento, status_servidor, status_ia,
                servidor_cold_start, tempo_servidor_ms, tempo_ia_ms,
                sucesso, mensagem_erro, detalhes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            agora_str, tipo_evento, status_servidor, status_ia,
            servidor_cold_start, tempo_servidor_ms, tempo_ia_ms,
            sucesso, mensagem_erro, detalhes
        ))
        log_id = cursor.lastrowid
        # Auto-pruning: manter apenas os últimos 200 registros para otimizar espaço
        cursor.execute("""
            DELETE FROM logs_diagnostico 
            WHERE id NOT IN (SELECT id FROM logs_diagnostico ORDER BY id DESC LIMIT 200)
        """)
        conn.commit()
        conn.close()
        return log_id
    except Exception as e:
        print(f"Erro ao registrar log de diagnóstico: {e}")
        return 0

def obter_ultimos_logs_diagnostico(limite: int = 20) -> List[Dict[str, Any]]:
    """Retorna os últimos logs de diagnóstico ordenados pelo mais recente."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, tipo_evento, status_servidor, status_ia,
                   servidor_cold_start, tempo_servidor_ms, tempo_ia_ms,
                   sucesso, mensagem_erro, detalhes
            FROM logs_diagnostico
            ORDER BY id DESC
            LIMIT ?
        """, (limite,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Erro ao obter logs de diagnóstico: {e}")
        return []

def obter_status_keepalive() -> Dict[str, Any]:
    """Informa há quanto tempo o último ping do monitor (UptimeRobot) foi recebido."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp FROM logs_diagnostico 
            WHERE tipo_evento = 'ping_keepalive'
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()
        if not row or not row["timestamp"]:
            return {
                "ativo": False,
                "ultimo_ping_timestamp": None,
                "minutos_atras": None,
                "mensagem": "Nenhum ping do UptimeRobot registrado ainda."
            }
        
        ts_str = row["timestamp"]
        dt_ping = None
        try:
            dt_ping = datetime.datetime.fromisoformat(ts_str)
        except Exception:
            try:
                dt_ping = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
                
        if dt_ping:
            diff_seg = (datetime.datetime.now() - dt_ping).total_seconds()
            minutos = max(0, int(diff_seg // 60))
            ativo = minutos <= 15
            msg = f"Último ping há {minutos} min" if minutos > 0 else "Último ping há menos de 1 minuto"
            return {
                "ativo": ativo,
                "ultimo_ping_timestamp": ts_str,
                "minutos_atras": minutos,
                "mensagem": msg
            }
        return {
            "ativo": True,
            "ultimo_ping_timestamp": ts_str,
            "minutos_atras": 0,
            "mensagem": f"Último ping registrado: {ts_str}"
        }
    except Exception as e:
        print(f"Erro ao consultar status keepalive: {e}")
        return {
            "ativo": False,
            "ultimo_ping_timestamp": None,
            "minutos_atras": None,
            "mensagem": f"Erro ao ler status: {e}"
        }

# Inicializar ao importar
init_db()

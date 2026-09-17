"""
Banco de dados SQLite e regras de negócio para o Yoga Studio App.
Gerencia alunos, pagamentos, inadimplência e geração de cobranças WhatsApp.
"""
import sqlite3
import os
import json
import datetime
import calendar
import uuid
import re
import urllib.parse
import hashlib
import secrets
from typing import List, Dict, Any, Optional

try:
    import zoneinfo
    TZ_SP = zoneinfo.ZoneInfo("America/Sao_Paulo")
except Exception:
    TZ_SP = datetime.timezone(datetime.timedelta(hours=-3))

def obter_hoje_sp() -> datetime.date:
    """Retorna a data atual no fuso horário oficial do estúdio (America/Sao_Paulo)."""
    return datetime.datetime.now(TZ_SP).date()

def obter_agora_sp() -> datetime.datetime:
    """Retorna a data e hora atual no fuso horário oficial do estúdio (America/Sao_Paulo)."""
    return datetime.datetime.now(TZ_SP)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yoga_studio.db")
DEFAULT_SUPABASE_URL = "postgresql://postgres.bzvpruczqkwnilwflrgo:-3yWeW3%3FrvG%23_6D@aws-0-us-west-2.pooler.supabase.com:5432/postgres"
DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_SUPABASE_URL

class DictAndIndexRow(dict):
    """Permite acesso tanto por nome da coluna row['nome'] quanto por indice numerico row[0], identico ao sqlite3.Row"""
    def __init__(self, mapping, keys):
        super().__init__(mapping)
        self._keys = keys

    def __getitem__(self, item):
        if isinstance(item, int):
            return self[self._keys[item]]
        return super().__getitem__(item)

class PgCursorWrapper:
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None

    def execute(self, query, params=None):
        query = self._adapt_query(query)
        # Se for INSERT e não tiver RETURNING, adiciona RETURNING id para popular lastrowid
        is_insert = query.strip().upper().startswith("INSERT")
        table_without_id = any(t in query.lower() for t in ["historico_presenca", "matriculas_turmas", "configuracoes"])
        if is_insert and "RETURNING" not in query.upper() and not table_without_id:
            query_with_returning = query + " RETURNING id"
            try:
                if params:
                    self._cur.execute(query_with_returning, params)
                else:
                    self._cur.execute(query_with_returning)
                row = self._cur.fetchone()
                if row and len(row) > 0:
                    self.lastrowid = row[0]
                return self
            except Exception:
                try:
                    self._cur.connection.rollback()
                except Exception:
                    pass

        if params:
            self._cur.execute(query, params)
        else:
            self._cur.execute(query)
        return self

    def _adapt_query(self, query: str) -> str:
        q = query.replace('?', '%s')
        q = q.replace("datetime('now', 'localtime')", "CURRENT_TIMESTAMP")
        q = q.replace("datetime('now')", "CURRENT_TIMESTAMP")
        if "INSERT OR IGNORE INTO configuracoes" in q:
            q = q.replace(
                "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (%s, %s)",
                "INSERT INTO configuracoes (chave, valor) VALUES (%s, %s) ON CONFLICT (chave) DO NOTHING"
            )
        elif "INSERT OR IGNORE INTO matriculas_turmas" in q:
            q = q.replace(
                "INSERT OR IGNORE INTO matriculas_turmas (aluno_id, turma_id) VALUES (%s, %s)",
                "INSERT INTO matriculas_turmas (aluno_id, turma_id) VALUES (%s, %s) ON CONFLICT (aluno_id, turma_id) DO NOTHING"
            )
        elif "INSERT OR IGNORE INTO historico_presenca" in q:
            q = q.replace("INSERT OR IGNORE INTO historico_presenca", "INSERT INTO historico_presenca")
            if "ON CONFLICT" not in q:
                q += " ON CONFLICT (aluno_id, turma_id, data) DO NOTHING"
        elif "INSERT OR IGNORE INTO" in q:
            q = q.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            if "ON CONFLICT" not in q:
                q += " ON CONFLICT DO NOTHING"
        return q

    def _wrap_row(self, row):
        if row is None:
            return None
        if isinstance(row, DictAndIndexRow):
            return row
        keys = [d[0] for d in self._cur.description]
        mapping = dict(zip(keys, row))
        return DictAndIndexRow(mapping, keys)

    def fetchone(self):
        row = self._cur.fetchone()
        return self._wrap_row(row)

    def fetchall(self):
        rows = self._cur.fetchall()
        return [self._wrap_row(r) for r in rows]

    def __iter__(self):
        for row in self._cur:
            yield self._wrap_row(row)

    @property
    def rowcount(self):
        return self._cur.rowcount

    def __getattr__(self, name):
        return getattr(self._cur, name)

    def close(self):
        self._cur.close()

class PgConnectionWrapper:
    def __init__(self, pg_conn):
        self._conn = pg_conn

    def cursor(self):
        return PgCursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def execute(self, query, params=None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

def get_connection():
    db_url = DATABASE_URL
    if db_url and HAS_PSYCOPG2:
        try:
            # Conexão direta com Supabase PostgreSQL (com timeout de 10s)
            pg_conn = psycopg2.connect(db_url, connect_timeout=10)
            return PgConnectionWrapper(pg_conn)
        except Exception as e:
            print(f"⚠️ Erro ao conectar no PostgreSQL Supabase: {e}. Utilizando SQLite local como fallback.")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa as tabelas do banco de dados e dados padrão se vazio."""
    conn = get_connection()
    if isinstance(conn, PgConnectionWrapper):
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos_agenda (
            id SERIAL PRIMARY KEY,
            titulo TEXT NOT NULL,
            data TEXT NOT NULL,
            horario_inicio TEXT NOT NULL,
            horario_fim TEXT,
            local TEXT,
            observacoes TEXT,
            tipo TEXT DEFAULT 'externo',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS logs_auditoria_ia (
            id SERIAL PRIMARY KEY,
            usuario TEXT NOT NULL,
            acao TEXT NOT NULL,
            parametros TEXT,
            resultado TEXT,
            sucesso INTEGER DEFAULT 1,
            detalhes TEXT,
            confirmacao_previa INTEGER DEFAULT 0,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS confirmacoes_ia (
            id SERIAL PRIMARY KEY,
            usuario TEXT NOT NULL,
            acao TEXT NOT NULL,
            alvo_id INTEGER,
            alvo_nome TEXT,
            dados_json TEXT,
            status TEXT DEFAULT 'pendente',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expira_em TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS conquistas_aluno (
            id SERIAL PRIMARY KEY,
            aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
            marco INTEGER NOT NULL,
            data_alcancada TEXT NOT NULL,
            mensagem_enviada INTEGER DEFAULT 0,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(aluno_id, marco)
        );
        CREATE TABLE IF NOT EXISTS biblioteca_conteudos (
            id SERIAL PRIMARY KEY,
            titulo TEXT NOT NULL,
            subtitulo TEXT,
            tipo TEXT NOT NULL DEFAULT 'texto',
            conteudo TEXT,
            arquivo_url TEXT,
            arquivo_nome TEXT,
            arquivo_tipo TEXT,
            tamanho_bytes INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'publicado',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS solicitacoes_reposicao (
            id SERIAL PRIMARY KEY,
            aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
            turma_origem_id INTEGER,
            data_falta TEXT NOT NULL,
            turma_destino_id INTEGER,
            data_sugerida TEXT,
            motivo TEXT,
            status TEXT NOT NULL DEFAULT 'pendente',
            resposta_admin TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE alunos ADD COLUMN IF NOT EXISTS senha_hash TEXT;
        ALTER TABLE alunos ADD COLUMN IF NOT EXISTS salt TEXT;
        ALTER TABLE alunos ADD COLUMN IF NOT EXISTS primeiro_acesso INTEGER DEFAULT 1;
        ALTER TABLE alunos ADD COLUMN IF NOT EXISTS tentativas_login INTEGER DEFAULT 0;
        ALTER TABLE alunos ADD COLUMN IF NOT EXISTS bloqueado_ate TIMESTAMP;
        ALTER TABLE alunos ADD COLUMN IF NOT EXISTS codigo_recuperacao TEXT;
        ALTER TABLE alunos ADD COLUMN IF NOT EXISTS codigo_recuperacao_expira TIMESTAMP;
        """)
        conn.commit()
        conn.close()
        return
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
        ("motivo_pausa_alerta", "TEXT"),
        ("senha_hash", "TEXT"),
        ("salt", "TEXT"),
        ("primeiro_acesso", "INTEGER DEFAULT 1"),
        ("tentativas_login", "INTEGER DEFAULT 0"),
        ("bloqueado_ate", "TEXT"),
        ("codigo_recuperacao", "TEXT"),
        ("codigo_recuperacao_expira", "TEXT")
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
        parcela_atual INTEGER DEFAULT 1,
        total_parcelas INTEGER DEFAULT 1,
        grupo_parcelamento_id TEXT,
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

    # Tabela de Usuários e Autenticação (Natália & Bruno Dev)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        nome TEXT NOT NULL,
        senha_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin',
        criado_em TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        salt_nat = "77b0037dfcd9b63d9f6b4ba34ea2d707"
        hash_nat = hashlib.sha256(("shanti2026" + salt_nat).encode("utf-8")).hexdigest()
        salt_bru = "892097a4db187404de0791052be03d63"
        hash_bru = hashlib.sha256(("dev2026" + salt_bru).encode("utf-8")).hexdigest()
        cursor.execute("""
        INSERT INTO usuarios (username, nome, senha_hash, salt, role)
        VALUES (?, ?, ?, ?, ?)
        """, ("natalia", "Natalia Garufe", hash_nat, salt_nat, "admin"))
        cursor.execute("""
        INSERT INTO usuarios (username, nome, senha_hash, salt, role)
        VALUES (?, ?, ?, ?, ?)
        """, ("bruno", "Bruno Dev", hash_bru, salt_bru, "dev"))

    # Tabela de Eventos e Compromissos Avulsos da Agenda
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS eventos_agenda (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        data TEXT NOT NULL,           -- 'YYYY-MM-DD'
        horario_inicio TEXT NOT NULL, -- 'HH:MM'
        horario_fim TEXT,             -- 'HH:MM'
        local TEXT,
        observacoes TEXT,
        tipo TEXT DEFAULT 'externo',  -- 'externo', 'workshop', 'particular'
        criado_em TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # Tabela de Logs de Auditoria de Ações da IA
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs_auditoria_ia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT NOT NULL,
        acao TEXT NOT NULL,
        parametros TEXT,
        resultado TEXT,
        sucesso INTEGER DEFAULT 1,
        detalhes TEXT,
        confirmacao_previa INTEGER DEFAULT 0,
        criado_em TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # Tabela de Confirmações Pendentes da IA (para ações destrutivas)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS confirmacoes_ia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT NOT NULL,
        acao TEXT NOT NULL,
        alvo_id INTEGER,
        alvo_nome TEXT,
        dados_json TEXT,
        status TEXT DEFAULT 'pendente',
        criado_em TEXT DEFAULT (datetime('now', 'localtime')),
        expira_em TEXT
    )
    """)

    # Tabela de Conquistas do Aluno (Marcos de Frequência)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conquistas_aluno (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        marco INTEGER NOT NULL,
        data_alcancada TEXT NOT NULL,
        mensagem_enviada INTEGER DEFAULT 0,
        criado_em TEXT DEFAULT (datetime('now', 'localtime')),
        UNIQUE(aluno_id, marco),
        FOREIGN KEY (aluno_id) REFERENCES alunos (id) ON DELETE CASCADE
    )
    """)

    # Tabela da Biblioteca de Leituras
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS biblioteca_conteudos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        subtitulo TEXT,
        tipo TEXT NOT NULL DEFAULT 'texto',
        conteudo TEXT,
        arquivo_url TEXT,
        arquivo_nome TEXT,
        arquivo_tipo TEXT,
        tamanho_bytes INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'publicado',
        criado_em TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    # Tabela de Solicitações de Reposição
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS solicitacoes_reposicao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        turma_origem_id INTEGER,
        data_falta TEXT NOT NULL,
        turma_destino_id INTEGER,
        data_sugerida TEXT,
        motivo TEXT,
        status TEXT NOT NULL DEFAULT 'pendente',
        resposta_admin TEXT,
        criado_em TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (aluno_id) REFERENCES alunos (id) ON DELETE CASCADE
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

    # Migração segura para suporte a despesas parceladas
    try:
        cursor.execute("ALTER TABLE despesas ADD COLUMN parcela_atual INTEGER DEFAULT 1")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE despesas ADD COLUMN total_parcelas INTEGER DEFAULT 1")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE despesas ADD COLUMN grupo_parcelamento_id TEXT")
    except Exception:
        pass
    cursor.execute("UPDATE despesas SET parcela_atual = 1 WHERE parcela_atual IS NULL")
    cursor.execute("UPDATE despesas SET total_parcelas = 1 WHERE total_parcelas IS NULL")

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
    WHERE (data_vencimento LIKE ? OR (data_vencimento IS NULL AND data LIKE ?))
    """, (f"{mes_ano}%", f"{mes_ano}%"))
    row_desp = cursor.fetchone()
    total_despesas = row_desp["total"] or 0.0
    qtd_despesas = row_desp["qtd"] or 0

    cursor.execute("""
    SELECT categoria, SUM(valor) as total, COUNT(*) as qtd
    FROM despesas
    WHERE (data_vencimento LIKE ? OR (data_vencimento IS NULL AND data LIKE ?))
    GROUP BY categoria
    """, (f"{mes_ano}%", f"{mes_ano}%"))
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
    try:
        verificar_e_registrar_conquistas(aluno_id)
    except Exception as e:
        logger.warning(f"Erro ao verificar conquistas do aluno {aluno_id}: {e}")
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

# =============================================================================
# EVENTOS & COMPROMISSOS AVULSOS DA AGENDA (FORA DA GRADE FIXA DE TURMAS)
# =============================================================================

def criar_evento(
    titulo: str,
    data: str,
    horario_inicio: str,
    horario_fim: Optional[str] = None,
    local: Optional[str] = None,
    observacoes: Optional[str] = None,
    tipo: str = "externo"
) -> int:
    """Cria um novo compromisso/evento avulso na agenda pessoal da Natália."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO eventos_agenda (titulo, data, horario_inicio, horario_fim, local, observacoes, tipo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        titulo.strip(),
        data.strip(),
        horario_inicio.strip(),
        horario_fim.strip() if horario_fim and horario_fim.strip() else None,
        local.strip() if local and local.strip() else None,
        observacoes.strip() if observacoes and observacoes.strip() else None,
        tipo.strip() if tipo else "externo"
    ))
    ev_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ev_id

def obter_evento(evento_id: int) -> Optional[Dict[str, Any]]:
    """Retorna um evento específico pelo ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM eventos_agenda WHERE id = ?", (evento_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def listar_eventos_mes(ano: int, mes: int) -> List[Dict[str, Any]]:
    """Retorna todos os compromissos de um determinado mês/ano."""
    prefixo = f"{ano:04d}-{mes:02d}%"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM eventos_agenda
        WHERE data LIKE ?
        ORDER BY data ASC, horario_inicio ASC
    """, (prefixo,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def listar_eventos_dia(data_str: str) -> List[Dict[str, Any]]:
    """Retorna todos os compromissos agendados para um dia específico."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM eventos_agenda
        WHERE data = ?
        ORDER BY horario_inicio ASC
    """, (data_str,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def atualizar_evento(evento_id: int, dados: Dict[str, Any]) -> bool:
    """
    Atualiza parcialmente um compromisso existente (Regras Permanentes 1 e 2).
    Apenas os campos fornecidos são atualizados, preservando todos os demais.
    """
    evento_atual = obter_evento(evento_id)
    if not evento_atual:
        return False

    campos_permitidos = ["titulo", "data", "horario_inicio", "horario_fim", "local", "observacoes", "tipo"]
    placeholders_proibidos = {"informe usuário", "não informado", "nenhum", "null", "undefined"}

    updates = []
    valores = []
    for campo in campos_permitidos:
        if campo in dados and dados[campo] is not None:
            val = dados[campo]
            if isinstance(val, str):
                val_limpo = val.strip()
                if val_limpo.lower() in placeholders_proibidos:
                    val_limpo = ""
                updates.append(f"{campo} = ?")
                valores.append(val_limpo if val_limpo else None)
            else:
                updates.append(f"{campo} = ?")
                valores.append(val)

    if not updates:
        return True

    valores.append(evento_id)
    sql = f"UPDATE eventos_agenda SET {', '.join(updates)} WHERE id = ?"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, tuple(valores))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

def excluir_evento(evento_id: int) -> bool:
    """Exclui um compromisso avulso da agenda."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM eventos_agenda WHERE id = ?", (evento_id,))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

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

    hoje_str = obter_hoje_sp().strftime("%Y-%m-%d")

    # Obter eventos/compromissos externos do mês
    eventos_mes = listar_eventos_mes(ano, mes)
    mapa_eventos = {}
    for ev in eventos_mes:
        try:
            d_num = int(ev["data"].split("-")[2])
            if d_num not in mapa_eventos:
                mapa_eventos[d_num] = []
            mapa_eventos[d_num].append(ev)
        except Exception:
            pass

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
                "eh_hoje": (dt_str == hoje_str),
                "eventos_count": len(mapa_eventos.get(dia, []))
            })

    return {
        "ano": ano,
        "mes": mes,
        "dias_com_aula": dias_com_aula,
        "turmas": turmas_ativas,
        "eventos_externos": eventos_mes,
        "dias_com_evento": sorted(list(mapa_eventos.keys())),
        "mapa_eventos": mapa_eventos,
        "resumo_mes": {
            "total_dias_com_aula": len(dias_com_aula),
            "total_aulas": total_aulas_mes,
            "total_presencas": total_presencas_mes,
            "total_faltas": total_faltas_mes,
            "total_eventos_externos": len(eventos_mes)
        }
    }

def obter_chamada_dia(data_str: str) -> Dict[str, Any]:
    """
    Retorna a lista de chamada e compromissos para uma data específica.
    Agrupa por turma ativa da grade oficial e inclui separadamente os eventos avulsos da agenda.
    """
    try:
        dt = datetime.date.fromisoformat(data_str)
    except Exception:
        dt = obter_hoje_sp()
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

    # Buscar eventos avulsos da data especificada
    eventos_externos = listar_eventos_dia(data_str)

    return {
        "data": data_str,
        "dia_semana_nome": dia_semana_nome,
        "eh_hoje": (data_str == obter_hoje_sp().strftime("%Y-%m-%d")),
        "turmas": resultado_turmas,
        "eventos_externos": eventos_externos,
        "totais": {
            "esperados": total_esperados,
            "presentes": total_presentes,
            "faltas": total_faltas,
            "pendentes": total_pendentes,
            "eventos_externos": len(eventos_externos)
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
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(aluno_id, turma_id, data) DO UPDATE SET
            status = excluded.status,
            justificativa = excluded.justificativa,
            atualizado_em = CURRENT_TIMESTAMP
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

    if status == "presente":
        try:
            verificar_e_registrar_conquistas(aluno_id)
        except Exception as e:
            logger.warning(f"Erro ao verificar conquistas do aluno {aluno_id}: {e}")

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

def calcular_data_parcela(data_base: datetime.date, dia_alvo: int, incremento_meses: int) -> str:
    """Calcula a data exata da parcela após N meses respeitando dias finais de cada mês."""
    total_meses = (data_base.year * 12 + data_base.month - 1) + incremento_meses
    novo_ano = total_meses // 12
    novo_mes = (total_meses % 12) + 1
    ultimo_dia = calendar.monthrange(novo_ano, novo_mes)[1]
    dia_final = min(dia_alvo, ultimo_dia)
    return f"{novo_ano:04d}-{novo_mes:02d}-{dia_final:02d}"

def registrar_despesa(
    descricao: str,
    valor: float,
    categoria: str = "Geral",
    data: Optional[str] = None,
    observacao: str = "",
    data_vencimento: Optional[str] = None,
    status: str = "pago",
    parcela_atual: int = 1,
    total_parcelas: int = 1,
    grupo_parcelamento_id: Optional[str] = None
) -> int:
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
    INSERT INTO despesas (
        descricao, valor, categoria, data, data_vencimento, status, observacao,
        parcela_atual, total_parcelas, grupo_parcelamento_id
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        descricao.strip(),
        float(valor),
        categoria.strip(),
        data,
        data_vencimento,
        status,
        observacao.strip(),
        int(parcela_atual or 1),
        int(total_parcelas or 1),
        grupo_parcelamento_id
    ))
    desp_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return desp_id

def registrar_despesa_parcelada(
    descricao: str,
    valor: float,
    categoria: str = "Geral",
    data: Optional[str] = None,
    data_vencimento: Optional[str] = None,
    total_parcelas: int = 2,
    tipo_calculo_parcela: str = "total",
    primeira_parcela_paga: bool = False,
    observacao: str = ""
) -> List[int]:
    """
    Registra uma compra/despesa parcelada em múltiplos meses futuros.
    Calcula os vencimentos mensais automáticos e rateia os centavos com exatidão contábil.
    """
    total_parcelas = max(2, min(int(total_parcelas), 48))
    conn = get_connection()
    cursor = conn.cursor()

    hoje = datetime.date.today()
    dt_emissao_base = hoje
    if data:
        try:
            dt_emissao_base = datetime.datetime.strptime(data, "%Y-%m-%d").date()
        except Exception:
            dt_emissao_base = hoje

    dt_venc_base = dt_emissao_base
    if data_vencimento:
        try:
            dt_venc_base = datetime.datetime.strptime(data_vencimento, "%Y-%m-%d").date()
        except Exception:
            dt_venc_base = dt_emissao_base

    dia_emissao_fixo = dt_emissao_base.day
    dia_venc_fixo = dt_venc_base.day

    # Divisão de valores com precisão absoluta de centavos
    if tipo_calculo_parcela == "parcela":
        # O valor informado é o valor de cada parcela
        valores_parcelas = [round(float(valor), 2)] * total_parcelas
    else:
        # O valor informado é o valor total da compra a ser rateado
        centavos_totais = int(round(float(valor) * 100))
        centavos_por_parcela = centavos_totais // total_parcelas
        resto_centavos = centavos_totais % total_parcelas
        
        valores_parcelas = []
        for i in range(total_parcelas):
            centavos_desta = centavos_por_parcela + (1 if i < resto_centavos else 0)
            valores_parcelas.append(round(centavos_desta / 100.0, 2))

    grupo_id = f"parc_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
    ids_criados = []

    # Limpar qualquer indicação anterior de parcela no nome base
    desc_base = re.sub(r'\s*\(\d+/\d+\)$', '', descricao.strip())

    for idx in range(total_parcelas):
        num_parcela = idx + 1
        data_parc_emissao = calcular_data_parcela(dt_emissao_base, dia_emissao_fixo, idx)
        data_parc_venc = calcular_data_parcela(dt_venc_base, dia_venc_fixo, idx)
        val_parc = valores_parcelas[idx]

        status_parc = "pago" if (idx == 0 and primeira_parcela_paga) else "pendente"
        desc_formatada = f"{desc_base} ({num_parcela}/{total_parcelas})"

        cursor.execute("""
        INSERT INTO despesas (
            descricao, valor, categoria, data, data_vencimento, status, observacao,
            parcela_atual, total_parcelas, grupo_parcelamento_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            desc_formatada,
            val_parc,
            categoria.strip() or "Geral",
            data_parc_emissao,
            data_parc_venc,
            status_parc,
            observacao.strip(),
            num_parcela,
            total_parcelas,
            grupo_id
        ))
        ids_criados.append(cursor.lastrowid)

    conn.commit()
    conn.close()
    return ids_criados

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
        if k in ("descricao", "valor", "categoria", "data", "data_vencimento", "status", "observacao", "parcela_atual", "total_parcelas", "grupo_parcelamento_id"):
            campos.append(f"{k} = ?")
            valores.append(float(v) if k == "valor" else (int(v) if k in ("parcela_atual", "total_parcelas") else str(v).strip()))
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

def excluir_despesa(despesa_id: int, excluir_grupo: bool = False) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT grupo_parcelamento_id FROM despesas WHERE id = ?", (despesa_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    grupo_id = row["grupo_parcelamento_id"]
    if excluir_grupo and grupo_id:
        cursor.execute("DELETE FROM despesas WHERE grupo_parcelamento_id = ?", (grupo_id,))
    else:
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

# --- Funções de Autenticação e Gestão de Usuários (Natália & Bruno Dev) ---

def _gerar_salt() -> str:
    """Gera um salt criptográfico aleatório hexadecimal de 16 bytes."""
    return secrets.token_hex(16)

def _hash_senha(senha: str, salt: str) -> str:
    """Calcula o hash SHA-256 da senha combinada com o salt (senha + salt)."""
    return hashlib.sha256((senha + salt).encode("utf-8")).hexdigest()

def autenticar_usuario(login_input: str, senha: str) -> Optional[Dict[str, Any]]:
    """
    Autentica usuário por username (ex: 'natalia', 'bruno') ou nome completo.
    Retorna os dados públicos do usuário autenticado ou None se inválido.
    """
    if not login_input or not senha:
        return None

    login_clean = str(login_input).strip().lower()

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, nome, senha_hash, salt, role
            FROM usuarios
            WHERE LOWER(username) = ? OR LOWER(nome) = ?
            LIMIT 1
        """, (login_clean, login_clean))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        u = dict(row)
        salt = u.get("salt", "")
        hash_esperado = u.get("senha_hash", "")

        if _hash_senha(senha, salt) == hash_esperado:
            return {
                "id": u["id"],
                "username": u["username"],
                "nome": u["nome"],
                "role": u.get("role", "admin")
            }
        return None
    except Exception as e:
        print(f"Erro ao autenticar usuário: {e}")
        return None

def obter_usuario(username_ou_id: Any) -> Optional[Dict[str, Any]]:
    """Obtém os dados públicos de um usuário por ID ou username."""
    if not username_ou_id:
        return None

    try:
        conn = get_connection()
        cursor = conn.cursor()
        if isinstance(username_ou_id, int) or (isinstance(username_ou_id, str) and username_ou_id.isdigit()):
            cursor.execute("SELECT id, username, nome, role FROM usuarios WHERE id = ?", (int(username_ou_id),))
        else:
            cursor.execute("SELECT id, username, nome, role FROM usuarios WHERE LOWER(username) = ?", (str(username_ou_id).lower().strip(),))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"Erro ao obter usuário: {e}")
        return None

def alterar_senha(username: str, nova_senha: str) -> bool:
    """Atualiza a senha do usuário gerando um novo salt e hash criptográfico."""
    if not username or not nova_senha or len(str(nova_senha).strip()) < 4:
        return False

    novo_salt = _gerar_salt()
    novo_hash = _hash_senha(str(nova_senha).strip(), novo_salt)

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE usuarios
            SET senha_hash = ?, salt = ?
            WHERE LOWER(username) = ?
        """, (novo_hash, novo_salt, str(username).lower().strip()))
        conn.commit()
        rows = cursor.rowcount
        conn.close()
        return rows > 0
    except Exception as e:
        print(f"Erro ao alterar senha do usuário {username}: {e}")
        return False

def listar_perfis_rapidos() -> List[Dict[str, Any]]:
    """Retorna a lista de perfis para seleção rápida na tela de login."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, nome, role FROM usuarios ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()

        perfis = []
        for r in rows:
            d = dict(r)
            uname = str(d.get("username", "")).lower()
            if uname == "natalia":
                titulo = "Gestão & Studio"
                avatar = "🧘‍♀️"
            elif uname == "bruno":
                titulo = "Desenvolvedor Master"
                avatar = "💻"
            else:
                titulo = "Acesso Shanti"
                avatar = "👤"

            perfis.append({
                "id": d["id"],
                "username": d["username"],
                "nome": d["nome"],
                "role": d.get("role", "admin"),
                "titulo": titulo,
                "avatar": avatar
            })
        return perfis
    except Exception as e:
        print(f"Erro ao listar perfis rápidos: {e}")
        return [
            {"id": 1, "username": "natalia", "nome": "Natalia Garufe", "role": "admin", "titulo": "Gestão & Studio", "avatar": "🧘‍♀️"},
            {"id": 2, "username": "bruno", "nome": "Bruno Dev", "role": "dev", "titulo": "Desenvolvedor Master", "avatar": "💻"}
        ]

# --- Auditoria de Ações da IA & Confirmações Seguras ---

def registrar_log_auditoria_ia(
    usuario: str,
    acao: str,
    parametros: Optional[Dict[str, Any]] = None,
    resultado: str = "",
    sucesso: bool = True,
    detalhes: str = "",
    confirmacao_previa: bool = False
) -> int:
    """Registra uma ação executada ou solicitada pela IA para auditoria transparente."""
    conn = get_connection()
    cursor = conn.cursor()
    params_json = json.dumps(parametros or {}, ensure_ascii=False)
    agora_sp = obter_agora_sp().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO logs_auditoria_ia (usuario, acao, parametros, resultado, sucesso, detalhes, confirmacao_previa, criado_em)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(usuario or "Usuário").strip(),
        str(acao).strip(),
        params_json,
        str(resultado).strip(),
        1 if sucesso else 0,
        str(detalhes or "").strip(),
        1 if confirmacao_previa else 0,
        agora_sp
    ))
    log_id = cursor.lastrowid or 0
    conn.commit()
    conn.close()
    return log_id

def listar_logs_auditoria_ia(limit: int = 50) -> List[Dict[str, Any]]:
    """Lista os logs mais recentes de auditoria de ações da IA."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, usuario, acao, parametros, resultado, sucesso, detalhes, confirmacao_previa, criado_em
    FROM logs_auditoria_ia
    ORDER BY id DESC
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    logs = []
    for r in rows:
        d = dict(r)
        try:
            d["parametros"] = json.loads(d.get("parametros") or "{}")
        except Exception:
            pass
        d["sucesso"] = bool(d.get("sucesso"))
        d["confirmacao_previa"] = bool(d.get("confirmacao_previa"))
        logs.append(d)
    conn.close()
    return logs

def criar_confirmacao_ia(
    usuario: str,
    acao: str,
    alvo_id: Optional[int] = None,
    alvo_nome: str = "",
    dados: Optional[Dict[str, Any]] = None,
    validade_minutos: int = 5
) -> int:
    """Armazena uma intenção de ação destrutiva que requer confirmação explícita do usuário."""
    conn = get_connection()
    cursor = conn.cursor()
    # Invalida confirmações anteriores pendentes deste usuário para evitar conflitos
    cursor.execute("""
    UPDATE confirmacoes_ia SET status = 'cancelado_substituido'
    WHERE usuario = ? AND status = 'pendente'
    """, (str(usuario or "Usuário").strip(),))
    
    agora = obter_agora_sp()
    expira = agora + datetime.timedelta(minutes=validade_minutos)
    dados_json = json.dumps(dados or {}, ensure_ascii=False)

    cursor.execute("""
    INSERT INTO confirmacoes_ia (usuario, acao, alvo_id, alvo_nome, dados_json, status, criado_em, expira_em)
    VALUES (?, ?, ?, ?, ?, 'pendente', ?, ?)
    """, (
        str(usuario or "Usuário").strip(),
        str(acao).strip(),
        alvo_id,
        str(alvo_nome or "").strip(),
        dados_json,
        agora.strftime("%Y-%m-%d %H:%M:%S"),
        expira.strftime("%Y-%m-%d %H:%M:%S")
    ))
    conf_id = cursor.lastrowid or 0
    conn.commit()
    conn.close()
    return conf_id

def obter_confirmacao_ia_pendente(usuario: str) -> Optional[Dict[str, Any]]:
    """Recupera confirmação ativa e não expirada para o usuário."""
    conn = get_connection()
    cursor = conn.cursor()
    agora_str = obter_agora_sp().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    SELECT id, usuario, acao, alvo_id, alvo_nome, dados_json, status, criado_em, expira_em
    FROM confirmacoes_ia
    WHERE usuario = ? AND status = 'pendente' AND expira_em >= ?
    ORDER BY id DESC
    LIMIT 1
    """, (str(usuario or "Usuário").strip(), agora_str))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    res = dict(row)
    try:
        res["dados"] = json.loads(res.get("dados_json") or "{}")
    except Exception:
        res["dados"] = {}
    conn.close()
    return res

def concluir_confirmacao_ia(conf_id: int, status: str = "confirmado") -> bool:
    """Atualiza o status de uma confirmação (ex: 'confirmado', 'cancelado', 'expirado')."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE confirmacoes_ia SET status = ? WHERE id = ?
    """, (status, conf_id))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

# =============================================================================
# ÁREA DO ALUNO: AUTENTICAÇÃO, CONQUISTAS, BIBLIOTECA E REPOSIÇÕES
# =============================================================================

MARCOS_CONQUISTAS = [10, 25, 50, 100, 200]

def _extrair_digitos(texto: Any) -> str:
    """Extrai apenas dígitos numéricos de uma string."""
    if not texto:
        return ""
    return re.sub(r'\D', '', str(texto))

def gerar_senha_temporaria() -> str:
    """Gera uma senha temporária amigável de 6 caracteres (ex: SH4829)."""
    num = secrets.randbelow(9000) + 1000
    return f"SH{num}"

def autenticar_aluno(login_input: str, senha_input: str) -> Dict[str, Any]:
    """
    Autentica o aluno por telefone ou CPF (com ou sem formatação) ou e-mail/nome.
    Possui proteção contra força bruta (bloqueio temporário de 15 min após 5 falhas).
    """
    if not login_input or not senha_input:
        return {"sucesso": False, "mensagem": "Informe o login e a senha."}

    login_limpo = str(login_input).strip()
    digitos = _extrair_digitos(login_limpo)
    agora = obter_agora_sp()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM alunos
        WHERE (telefone IS NOT NULL AND telefone != '' AND (telefone = ? OR REPLACE(REPLACE(REPLACE(REPLACE(telefone, '(', ''), ')', ''), '-', ''), ' ', '') = ?))
           OR (cpf IS NOT NULL AND cpf != '' AND (cpf = ? OR REPLACE(REPLACE(REPLACE(cpf, '.', ''), '-', ''), '/', '') = ?))
           OR LOWER(email) = ?
           OR LOWER(nome) = ?
        LIMIT 1
    """, (login_limpo, digitos, login_limpo, digitos, login_limpo.lower(), login_limpo.lower()))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"sucesso": False, "mensagem": "Aluno não encontrado com este usuário ou telefone."}

    aluno = dict(row)
    aluno_id = aluno["id"]

    # 1. Verificar bloqueio temporário por força bruta
    bloqueado_ate = aluno.get("bloqueado_ate")
    if bloqueado_ate:
        try:
            dt_bloq = datetime.datetime.fromisoformat(str(bloqueado_ate).replace("Z", ""))
            if dt_bloq.tzinfo is None:
                dt_bloq = dt_bloq.replace(tzinfo=TZ_SP)
            if agora < dt_bloq:
                minutos_restantes = max(1, int((dt_bloq - agora).total_seconds() // 60))
                conn.close()
                return {
                    "sucesso": False,
                    "bloqueado": True,
                    "mensagem": f"Conta temporariamente bloqueada por segurança. Tente novamente em {minutos_restantes} minuto(s)."
                }
        except Exception:
            pass

    # 2. Verificar senha
    salt = aluno.get("salt") or ""
    hash_esperado = aluno.get("senha_hash")
    senha_fornecida = str(senha_input).strip()

    # Se o aluno ainda não possui hash gravado (aluno antigo pré-sistema de login)
    if not hash_esperado:
        tel_dig = _extrair_digitos(aluno.get("telefone") or "")
        ultimos_4 = tel_dig[-4:] if len(tel_dig) >= 4 else "2026"
        senha_temp_padrao = f"SH{ultimos_4}"
        if senha_fornecida.upper() == senha_temp_padrao or senha_fornecida == "shanti2026":
            novo_salt = _gerar_salt()
            novo_hash = _hash_senha(senha_fornecida, novo_salt)
            cursor.execute("""
                UPDATE alunos SET senha_hash = ?, salt = ?, primeiro_acesso = 1, tentativas_login = 0, bloqueado_ate = NULL
                WHERE id = ?
            """, (novo_hash, novo_salt, aluno_id))
            conn.commit()
            conn.close()
            return {
                "sucesso": True,
                "aluno": {
                    "id": aluno["id"],
                    "nome": aluno["nome"],
                    "telefone": aluno["telefone"],
                    "cpf": aluno.get("cpf"),
                    "plano": aluno.get("plano")
                },
                "primeiro_acesso": True
            }

    hash_calc = _hash_senha(senha_fornecida, salt)
    if hash_calc == hash_esperado:
        cursor.execute("""
            UPDATE alunos SET tentativas_login = 0, bloqueado_ate = NULL
            WHERE id = ?
        """, (aluno_id,))
        conn.commit()
        conn.close()

        primeiro_acesso = bool(aluno.get("primeiro_acesso", 1))
        return {
            "sucesso": True,
            "aluno_id": aluno["id"],
            "aluno": {
                "id": aluno["id"],
                "nome": aluno["nome"],
                "telefone": aluno["telefone"],
                "cpf": aluno.get("cpf"),
                "plano": aluno.get("plano"),
                "status": aluno.get("status")
            },
            "primeiro_acesso": primeiro_acesso
        }
    else:
        tentativas = int(aluno.get("tentativas_login") or 0) + 1
        if tentativas >= 5:
            dt_fim_bloq = agora + datetime.timedelta(minutes=15)
            novo_bloqueio = dt_fim_bloq.strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                UPDATE alunos SET tentativas_login = ?, bloqueado_ate = ? WHERE id = ?
            """, (tentativas, novo_bloqueio, aluno_id))
            conn.commit()
            conn.close()
            return {
                "sucesso": False,
                "bloqueado": True,
                "mensagem": "5 tentativas incorretas. Conta bloqueada por 15 minutos para evitar ataques."
            }
        else:
            cursor.execute("""
                UPDATE alunos SET tentativas_login = ? WHERE id = ?
            """, (tentativas, aluno_id))
            conn.commit()
            conn.close()
            restantes = 5 - tentativas
            return {
                "sucesso": False,
                "bloqueado": False,
                "mensagem": f"Senha incorreta. {restantes} tentativa(s) restante(s) antes do bloqueio temporário."
            }

def cadastrar_senha_primeiro_acesso(aluno_id: int, nova_senha: str) -> Dict[str, Any]:
    """Salva a senha definitiva do aluno e marca primeiro_acesso = 0."""
    if not nova_senha or len(str(nova_senha).strip()) < 4:
        return {"sucesso": False, "mensagem": "A senha deve ter pelo menos 4 caracteres."}

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM alunos WHERE id = ?", (aluno_id,))
    if not cursor.fetchone():
        conn.close()
        return {"sucesso": False, "mensagem": "Aluno não encontrado."}

    novo_salt = _gerar_salt()
    novo_hash = _hash_senha(str(nova_senha).strip(), novo_salt)

    cursor.execute("""
        UPDATE alunos
        SET senha_hash = ?, salt = ?, primeiro_acesso = 0, tentativas_login = 0, bloqueado_ate = NULL
        WHERE id = ?
    """, (novo_hash, novo_salt, aluno_id))
    conn.commit()
    conn.close()
    return {"sucesso": True, "mensagem": "Senha definitiva cadastrada com sucesso!"}

def cadastrar_conta_aluno(login_input: str, nova_senha: str) -> Dict[str, Any]:
    """
    Permite ao aluno criar sua conta diretamente ao instalar o app.
    Localiza o aluno pelo telefone ou CPF cadastrado no estúdio e define a senha pessoal.
    Se o aluno já possui senha cadastrada, orienta a fazer login.
    """
    if not login_input or not nova_senha:
        return {"sucesso": False, "mensagem": "Informe seu telefone ou CPF e crie uma senha."}

    nova_senha_str = str(nova_senha).strip()
    if len(nova_senha_str) < 6:
        return {"sucesso": False, "mensagem": "A senha deve ter pelo menos 6 caracteres."}

    login_limpo = str(login_input).strip()
    digitos = _extrair_digitos(login_limpo)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM alunos
        WHERE (telefone IS NOT NULL AND telefone != '' AND (telefone = ? OR REPLACE(REPLACE(REPLACE(REPLACE(telefone, '(', ''), ')', ''), '-', ''), ' ', '') = ?))
           OR (cpf IS NOT NULL AND cpf != '' AND (cpf = ? OR REPLACE(REPLACE(REPLACE(cpf, '.', ''), '-', ''), '/', '') = ?))
        LIMIT 1
    """, (login_limpo, digitos, login_limpo, digitos))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return {
            "sucesso": False,
            "mensagem": "Nenhum aluno encontrado com este telefone ou CPF. Verifique se o dado está correto ou entre em contato com o estúdio."
        }

    aluno = dict(row)
    aluno_id = aluno["id"]

    # Se já possui senha cadastrada e não é primeiro acesso, orientar a fazer login
    if aluno.get("senha_hash") and not bool(aluno.get("primeiro_acesso", 1)):
        conn.close()
        return {
            "sucesso": False,
            "ja_cadastrado": True,
            "mensagem": "Você já possui uma conta cadastrada. Use a tela de login para entrar."
        }

    # Criar a senha
    novo_salt = _gerar_salt()
    novo_hash = _hash_senha(nova_senha_str, novo_salt)

    cursor.execute("""
        UPDATE alunos
        SET senha_hash = ?, salt = ?, primeiro_acesso = 0, tentativas_login = 0, bloqueado_ate = NULL
        WHERE id = ?
    """, (novo_hash, novo_salt, aluno_id))
    conn.commit()
    conn.close()

    return {
        "sucesso": True,
        "aluno_id": aluno_id,
        "aluno": {
            "id": aluno["id"],
            "nome": aluno["nome"],
            "telefone": aluno.get("telefone"),
            "cpf": aluno.get("cpf"),
            "plano": aluno.get("plano")
        },
        "mensagem": "Conta criada com sucesso! Bem-vindo(a) ao Shanti Studio!"
    }

def excluir_acesso_aluno(aluno_id: int) -> Dict[str, Any]:
    """
    Exclui a senha e revoga o acesso do aluno ao aplicativo.
    O cadastro do aluno (dados cadastrais, planos, presenças) permanece 100% intacto,
    mas ele não poderá mais se autenticar no aplicativo.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome FROM alunos WHERE id = ?", (aluno_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"sucesso": False, "mensagem": "Aluno não encontrado."}

    aluno = dict(row)
    cursor.execute("""
        UPDATE alunos
        SET senha_hash = NULL,
            salt = NULL,
            primeiro_acesso = 1,
            tentativas_login = 0,
            bloqueado_ate = NULL,
            codigo_recuperacao = NULL,
            codigo_recuperacao_expira = NULL
        WHERE id = ?
    """, (aluno_id,))
    conn.commit()
    conn.close()

    return {
        "sucesso": True,
        "mensagem": f"Acesso do(a) aluno(a) {aluno['nome']} ao aplicativo foi excluído com sucesso!"
    }

def solicitar_recuperacao_senha_aluno(login_input: str) -> Dict[str, Any]:
    """Gera código de uso único com expiração de 10 minutos e link do WhatsApp."""
    if not login_input:
        return {"sucesso": False, "mensagem": "Informe seu telefone ou CPF cadastrado."}

    login_limpo = str(login_input).strip()
    digitos = _extrair_digitos(login_limpo)
    agora = obter_agora_sp()
    expira_str = (agora + datetime.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nome, telefone, cpf FROM alunos
        WHERE (telefone IS NOT NULL AND (telefone = ? OR REPLACE(REPLACE(REPLACE(REPLACE(telefone, '(', ''), ')', ''), '-', ''), ' ', '') = ?))
           OR (cpf IS NOT NULL AND (cpf = ? OR REPLACE(REPLACE(REPLACE(cpf, '.', ''), '-', ''), '/', '') = ?))
           OR LOWER(email) = ?
        LIMIT 1
    """, (login_limpo, digitos, login_limpo, digitos, login_limpo.lower()))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"sucesso": False, "mensagem": "Nenhum aluno encontrado com este telefone/CPF."}

    aluno = dict(row)
    aluno_id = aluno["id"]
    codigo = f"{secrets.randbelow(900000) + 100000}"

    cursor.execute("""
        UPDATE alunos
        SET codigo_recuperacao = ?, codigo_recuperacao_expira = ?, tentativas_login = 0, bloqueado_ate = NULL
        WHERE id = ?
    """, (codigo, expira_str, aluno_id))
    conn.commit()
    conn.close()

    tel_dig = _extrair_digitos(aluno.get("telefone") or "")
    if len(tel_dig) > 4:
        tel_mascarado = f"({tel_dig[:2]}) 9****-{tel_dig[-4:]}"
    else:
        tel_mascarado = "***"

    primeiro_nome = aluno["nome"].split()[0] if aluno.get("nome") else "Aluno(a)"
    msg = (
        f"Olá, {primeiro_nome}! 🧘‍♀️ Seu código de verificação para redefinir a senha no App Shanti Aluno é:\n\n"
        f"🔑 *{codigo}*\n\n"
        f"Este código é de uso único e expira em 10 minutos. Se você não solicitou, ignore esta mensagem."
    )
    link_wa = f"https://wa.me/55{tel_dig}?text={urllib.parse.quote(msg)}" if tel_dig else None

    return {
        "sucesso": True,
        "aluno_id": aluno_id,
        "telefone_mascarado": tel_mascarado,
        "codigo": codigo,
        "link_whatsapp": link_wa,
        "mensagem": f"Código de segurança gerado com sucesso para {tel_mascarado}."
    }

def redefinir_senha_com_codigo(login_input: str, codigo: str, nova_senha: str) -> Dict[str, Any]:
    """Valida o código de 6 dígitos não expirado e define a nova senha."""
    if not login_input or not codigo or not nova_senha:
        return {"sucesso": False, "mensagem": "Preencha todos os campos."}

    if len(str(nova_senha).strip()) < 4:
        return {"sucesso": False, "mensagem": "A nova senha deve ter pelo menos 4 caracteres."}

    login_limpo = str(login_input).strip()
    digitos = _extrair_digitos(login_limpo)
    cod_limpo = str(codigo).strip()
    agora = obter_agora_sp()
    agora_str = agora.strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nome, codigo_recuperacao, codigo_recuperacao_expira
        FROM alunos
        WHERE (telefone IS NOT NULL AND (telefone = ? OR REPLACE(REPLACE(REPLACE(REPLACE(telefone, '(', ''), ')', ''), '-', ''), ' ', '') = ?))
           OR (cpf IS NOT NULL AND (cpf = ? OR REPLACE(REPLACE(REPLACE(cpf, '.', ''), '-', ''), '/', '') = ?))
           OR LOWER(email) = ?
        LIMIT 1
    """, (login_limpo, digitos, login_limpo, digitos, login_limpo.lower()))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"sucesso": False, "mensagem": "Aluno não encontrado."}

    aluno = dict(row)
    cod_esperado = aluno.get("codigo_recuperacao")
    expira = aluno.get("codigo_recuperacao_expira")

    if not cod_esperado or cod_esperado != cod_limpo:
        conn.close()
        return {"sucesso": False, "mensagem": "Código de verificação incorreto."}

    if expira and str(expira) < agora_str:
        conn.close()
        return {"sucesso": False, "mensagem": "Este código expirou. Solicite um novo código."}

    novo_salt = _gerar_salt()
    novo_hash = _hash_senha(str(nova_senha).strip(), novo_salt)

    cursor.execute("""
        UPDATE alunos
        SET senha_hash = ?, salt = ?, primeiro_acesso = 0,
            codigo_recuperacao = NULL, codigo_recuperacao_expira = NULL,
            tentativas_login = 0, bloqueado_ate = NULL
        WHERE id = ?
    """, (novo_hash, novo_salt, aluno["id"]))
    conn.commit()
    conn.close()

    return {"sucesso": True, "mensagem": "Senha redefinida com sucesso! Você já pode fazer login."}

# --- Conquistas por Marcos de Frequência (10, 25, 50, 100, 200 aulas) ---

def obter_total_presencas_aluno(aluno_id: int) -> int:
    """Calcula a contagem cumulativa total de presenças de um aluno desde sua matrícula."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(DISTINCT data) FROM (
            SELECT data FROM historico_presenca WHERE aluno_id = ? AND status = 'presente'
            UNION
            SELECT data FROM frequencias WHERE aluno_id = ?
        )
    """, (aluno_id, aluno_id))
    cnt = cursor.fetchone()
    total = cnt[0] if cnt else 0
    conn.close()
    return int(total)

def verificar_e_registrar_conquistas(aluno_id: int) -> List[Dict[str, Any]]:
    """
    Verifica se o aluno atingiu algum marco de aulas não registrado e grava em conquistas_aluno.
    Garante que cada marco só seja disparado e gravado UMA ÚNICA VEZ.
    """
    total = obter_total_presencas_aluno(aluno_id)
    agora = obter_agora_sp()
    hoje_str = agora.strftime("%Y-%m-%d")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT marco FROM conquistas_aluno WHERE aluno_id = ?", (aluno_id,))
    marcos_existentes = {r[0] if isinstance(r, (list, tuple)) else r["marco"] for r in cursor.fetchall()}

    cursor.execute("SELECT nome, telefone FROM alunos WHERE id = ?", (aluno_id,))
    al_row = cursor.fetchone()
    nome_aluno = al_row["nome"] if al_row else "Aluno(a)"
    primeiro_nome = nome_aluno.split()[0]
    tel_dig = _extrair_digitos(al_row["telefone"]) if al_row else ""

    novas = []
    for marco in MARCOS_CONQUISTAS:
        if total >= marco and marco not in marcos_existentes:
            cursor.execute("""
                INSERT INTO conquistas_aluno (aluno_id, marco, data_alcancada, mensagem_enviada, criado_em)
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
            """, (aluno_id, marco, hoje_str))

            msg = (
                f"Parabéns, {primeiro_nome}! 🧘‍♀️ Você completou *{marco} aulas* no Shanti Studio — "
                f"sua prática está evoluindo de verdade. Que sua jornada no Yoga continue florescendo. Namastê! 🙏✨"
            )
            link_wa = f"https://wa.me/55{tel_dig}?text={urllib.parse.quote(msg)}" if tel_dig else None

            novas.append({
                "marco": marco,
                "data_alcancada": hoje_str,
                "mensagem": msg,
                "link_whatsapp": link_wa
            })

    conn.commit()
    conn.close()
    return novas

def obter_conquistas_aluno(aluno_id: int) -> Dict[str, Any]:
    """Retorna lista de marcos com status desbloqueado/bloqueado e progresso até o próximo."""
    total = obter_total_presencas_aluno(aluno_id)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT marco, data_alcancada FROM conquistas_aluno WHERE aluno_id = ? ORDER BY marco ASC", (aluno_id,))
    linhas = cursor.fetchall()
    conn.close()

    mapa_conquistas = {
        (r[0] if isinstance(r, (list, tuple)) else r["marco"]): (r[1] if isinstance(r, (list, tuple)) else r["data_alcancada"])
        for r in linhas
    }

    proximo_marco = 200
    for m in MARCOS_CONQUISTAS:
        if total < m:
            proximo_marco = m
            break

    lista_marcos = []
    for m in MARCOS_CONQUISTAS:
        desbloqueado = m in mapa_conquistas or total >= m
        data_alcance = mapa_conquistas.get(m)
        lista_marcos.append({
            "marco": m,
            "titulo": f"{m} Aulas Praticadas",
            "desbloqueado": desbloqueado,
            "data_alcancada": data_alcance,
            "icone": "fa-award" if m < 50 else ("fa-medal" if m < 100 else "fa-trophy")
        })

    progresso_str = f"{min(total, proximo_marco)}/{proximo_marco}"
    progresso_pct = min(100, int((total / proximo_marco) * 100)) if proximo_marco > 0 else 100

    return {
        "total_presencas": total,
        "proximo_marco": proximo_marco,
        "progresso_str": progresso_str,
        "progresso_pct": progresso_pct,
        "marcos": lista_marcos
    }

# --- Biblioteca de Leituras ---

def listar_biblioteca(status: Optional[str] = "publicado") -> List[Dict[str, Any]]:
    """Retorna itens da biblioteca de conteúdos. Se status for None, lista todos."""
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM biblioteca_conteudos WHERE status = ? ORDER BY id DESC", (status,))
    else:
        cursor.execute("SELECT * FROM biblioteca_conteudos ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obter_conteudo_biblioteca(conteudo_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM biblioteca_conteudos WHERE id = ?", (conteudo_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def salvar_conteudo_biblioteca(dados: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO biblioteca_conteudos (
            titulo, subtitulo, tipo, conteudo, arquivo_url, arquivo_nome,
            arquivo_tipo, tamanho_bytes, status, criado_em, atualizado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        dados.get("titulo", "Sem título"),
        dados.get("subtitulo", ""),
        dados.get("tipo", "texto"),
        dados.get("conteudo", ""),
        dados.get("arquivo_url"),
        dados.get("arquivo_nome"),
        dados.get("arquivo_tipo"),
        int(dados.get("tamanho_bytes") or 0),
        dados.get("status", "publicado")
    ))
    cid = cursor.lastrowid or 0
    conn.commit()
    conn.close()
    return cid

def atualizar_conteudo_biblioteca(conteudo_id: int, dados: Dict[str, Any]) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    campos = []
    valores = []
    for k in ["titulo", "subtitulo", "tipo", "conteudo", "arquivo_url", "arquivo_nome", "arquivo_tipo", "tamanho_bytes", "status"]:
        if k in dados and dados[k] is not None:
            campos.append(f"{k} = ?")
            valores.append(dados[k])
    if not campos:
        conn.close()
        return False
    campos.append("atualizado_em = CURRENT_TIMESTAMP")
    valores.append(conteudo_id)
    cursor.execute(f"UPDATE biblioteca_conteudos SET {', '.join(campos)} WHERE id = ?", tuple(valores))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

def excluir_conteudo_biblioteca(conteudo_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM biblioteca_conteudos WHERE id = ?", (conteudo_id,))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

# --- Solicitações de Reposição de Aula ---

def criar_solicitacao_reposicao(aluno_id: int, data_falta: str, motivo: str = "", turma_origem_id: Optional[int] = None, turma_destino_id: Optional[int] = None, data_sugerida: Optional[str] = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO solicitacoes_reposicao (
            aluno_id, turma_origem_id, data_falta, turma_destino_id,
            data_sugerida, motivo, status, criado_em, atualizado_em
        ) VALUES (?, ?, ?, ?, ?, ?, 'pendente', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (aluno_id, turma_origem_id, data_falta, turma_destino_id, data_sugerida, motivo))
    sid = cursor.lastrowid or 0
    conn.commit()
    conn.close()
    return sid

def listar_solicitacoes_reposicao(status: Optional[str] = None, aluno_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    where = []
    params = []
    if status:
        where.append("sr.status = ?")
        params.append(status)
    if aluno_id:
        where.append("sr.aluno_id = ?")
        params.append(aluno_id)
    where_str = f"WHERE {' AND '.join(where)}" if where else ""

    cursor.execute(f"""
        SELECT sr.*, a.nome as aluno_nome, a.telefone as aluno_telefone,
               t1.nome as turma_origem_nome, t2.nome as turma_destino_nome
        FROM solicitacoes_reposicao sr
        JOIN alunos a ON sr.aluno_id = a.id
        LEFT JOIN turmas t1 ON sr.turma_origem_id = t1.id
        LEFT JOIN turmas t2 ON sr.turma_destino_id = t2.id
        {where_str}
        ORDER BY sr.id DESC
    """, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def responder_solicitacao_reposicao(solicitacao_id: int, novo_status: str, resposta_admin: str = "", turma_alocada_id: Optional[int] = None, data_alocada: Optional[str] = None) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE solicitacoes_reposicao
        SET status = ?, resposta_admin = ?, turma_destino_id = COALESCE(?, turma_destino_id),
            data_sugerida = COALESCE(?, data_sugerida), atualizado_em = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (novo_status, resposta_admin, turma_alocada_id, data_alocada, solicitacao_id))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

# --- Resumo Completo do Dashboard do Aluno (Design Aprovado) ---

# --- Métodos de Interação do Aluno: Confirmação, Desmarcação, Contrato e Streak ---

def _calcular_streak_semanal(aluno_id: int) -> int:
    """
    Calcula quantas semanas consecutivas o aluno praticou yoga (com status 'presente').
    Retorna um número inteiro de semanas seguidas.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT data FROM historico_presenca
        WHERE aluno_id = ? AND status = 'presente'
        UNION
        SELECT DISTINCT data FROM frequencias
        WHERE aluno_id = ?
    """, (aluno_id, aluno_id))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return 1

    semanas_praticadas = set()
    for r in rows:
        data_str = r[0] if isinstance(r, (list, tuple)) else r["data"]
        try:
            dt = datetime.datetime.strptime(data_str[:10], "%Y-%m-%d").date()
            semanas_praticadas.add(dt.isocalendar()[:2])
        except Exception:
            continue

    if not semanas_praticadas:
        return 1

    hoje = obter_hoje_sp()
    curr_week = hoje.isocalendar()[:2]
    streak = 0
    test_date = hoje

    if curr_week in semanas_praticadas:
        streak += 1
        test_date = hoje - datetime.timedelta(days=7)
    else:
        prev_week = (hoje - datetime.timedelta(days=7)).isocalendar()[:2]
        if prev_week in semanas_praticadas:
            streak += 1
            test_date = hoje - datetime.timedelta(days=14)
        else:
            return 1

    for _ in range(52):
        w = test_date.isocalendar()[:2]
        if w in semanas_praticadas:
            streak += 1
            test_date -= datetime.timedelta(days=7)
        else:
            break

    return max(1, streak)

def aluno_confirmar_presenca(aluno_id: int, turma_id: int, data_str: str) -> Dict[str, Any]:
    """
    O aluno confirma presença na aula pelo app.
    Salva status='pendente' com justificativa='Confirmado pelo aluno no app'.
    No app de gestão (Natália), fica indicado como Pendente (Confirmado pelo Aluno) até a validação da presença.
    """
    salvar_status_presenca(
        aluno_id=aluno_id,
        turma_id=turma_id,
        data_str=data_str,
        status="pendente",
        justificativa="Confirmado pelo aluno no app"
    )
    return {
        "sucesso": True,
        "mensagem": "Presença confirmada! Aguardando validação da Natália.",
        "status": "pendente",
        "data": data_str,
        "turma_id": turma_id
    }

def aluno_desmarcar_aula(aluno_id: int, turma_id: int, data_str: str, motivo: str = "") -> Dict[str, Any]:
    """
    O aluno desmarca a aula pelo app.
    Computa imediatamente como 'faltou' com justificativa='Desmarcado pelo aluno no app'.
    Permite solicitar reposição logo em seguida.
    """
    just = "Desmarcado pelo aluno no app"
    if motivo:
        just += f": {motivo}"

    salvar_status_presenca(
        aluno_id=aluno_id,
        turma_id=turma_id,
        data_str=data_str,
        status="faltou",
        justificativa=just
    )
    return {
        "sucesso": True,
        "mensagem": "Aula desmarcada com sucesso. Você pode solicitar uma reposição quando desejar.",
        "status": "faltou",
        "data": data_str,
        "turma_id": turma_id
    }

def aluno_assinar_contrato(aluno_id: int) -> Dict[str, Any]:
    """
    Registra a assinatura digital do contrato pelo aluno no app.
    Atualiza status_contrato para 'em_dia' com vigência de 1 ano.
    """
    hoje = obter_hoje_sp()
    hoje_str = hoje.strftime("%Y-%m-%d")
    vigencia_str = (hoje + datetime.timedelta(days=365)).strftime("%Y-%m-%d")

    atualizar_aluno(aluno_id, {
        "status_contrato": "em_dia",
        "data_assinatura_contrato": hoje_str,
        "data_vigencia_contrato": vigencia_str,
        "autentique_status": "assinado"
    })
    return {
        "sucesso": True,
        "mensagem": "Contrato assinado digitalmente com sucesso!",
        "status_contrato": "em_dia",
        "data_assinatura": hoje_str,
        "data_vigencia": vigencia_str
    }

# --- Resumo Completo do Dashboard do Aluno (Design Aprovado em media_1789606846595.png) ---

def obter_resumo_aluno_dashboard(aluno_id: int) -> Dict[str, Any]:
    """
    Retorna todos os dados consolidados para alimentar a tela de Início do App do Aluno:
    - Saudação ("Bom dia,", "Boa tarde,") + Nome do Aluno
    - Avatar circular em terracota com inicial
    - Sua semana com streak de semanas consecutivas
    - Próximas aulas em lista horizontal com botões Confirmar / Desmarcar
    - Rumo à próxima conquista (progresso e badges de marcos)
    - Situação da Mensalidade (Em dia / Em atraso)
    - Situação do Contrato (Vigente / Pendente de Assinatura com botão)
    - Frase do dia
    - Nova leitura recente
    """
    aluno = obter_aluno(aluno_id)
    if not aluno:
        return {}

    agora = obter_agora_sp()
    hora = agora.hour
    saudacao = "Bom dia," if hora < 12 else ("Boa tarde," if hora < 18 else "Boa noite,")

    dias_pt = ["SEGUNDA-FEIRA", "TERÇA-FEIRA", "QUARTA-FEIRA", "QUINTA-FEIRA", "SEXTA-FEIRA", "SÁBADO", "DOMINGO"]
    meses_pt = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
    dia_semana_nome = dias_pt[agora.weekday()]
    mes_nome = meses_pt[agora.month - 1]
    data_formatada = f"{dia_semana_nome}, {agora.day} DE {mes_nome}"

    nome_completo = aluno.get("nome", "Aluno")
    primeiro_nome = nome_completo.split()[0]
    inicial = primeiro_nome[0].upper() if primeiro_nome else "Y"

    # 1. Streak Semanal
    streak_semanas = _calcular_streak_semanal(aluno_id)

    # 2. Próximas Aulas (Próximos 14 dias)
    turmas = aluno.get("turmas", [])
    proximas_aulas = []
    hoje_date = agora.date()
    dias_abrev = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
    dias_semana_nome = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    meses_nome = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    meses_abrev = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

    if turmas:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT turma_id, data, status, justificativa
            FROM historico_presenca
            WHERE aluno_id = ? AND data >= ?
        """, (aluno_id, hoje_date.strftime("%Y-%m-%d")))
        rows = cursor.fetchall()
        presencas_futuras = {
            ((r[0] if isinstance(r, (list, tuple)) else r["turma_id"]),
             (r[1] if isinstance(r, (list, tuple)) else r["data"])): (
                (r[2] if isinstance(r, (list, tuple)) else r["status"]),
                (r[3] if isinstance(r, (list, tuple)) else r["justificativa"])
            )
            for r in rows
        }
        conn.close()

        dias_1x = parse_dias_semana(aluno.get("dia_semana_1x")) if aluno.get("dia_semana_1x") else []

        for offset in range(14):
            dt = hoje_date + datetime.timedelta(days=offset)
            w = dt.weekday()
            if dias_1x and (w not in dias_1x):
                continue

            dt_str = dt.strftime("%Y-%m-%d")

            for t in turmas:
                t_dias = parse_dias_semana(t.get("dias_semana"))
                if w in t_dias:
                    reg = presencas_futuras.get((t["id"], dt_str))
                    st = reg[0] if reg else "agendada"
                    just = reg[1] if reg else ""

                    if st == "pendente" and "Confirmado pelo aluno" in (just or ""):
                        st_pres = "confirmado_aluno"
                        st_label = "Confirmado"
                    elif st == "faltou" and "Desmarcado pelo aluno" in (just or ""):
                        st_pres = "desmarcado"
                        st_label = "Desmarcada"
                    elif st == "presente":
                        st_pres = "presente"
                        st_label = "Presente"
                    elif st == "faltou":
                        st_pres = "faltou"
                        st_label = "Falta"
                    else:
                        st_pres = "agendada"
                        st_label = "Agendada"

                    if offset == 0:
                        tag_dia = "HOJE"
                    elif offset == 1:
                        tag_dia = "AMANHÃ"
                    else:
                        tag_dia = dias_abrev[w]

                    data_extenso = f"{dt.day} de {meses_nome[dt.month]}"
                    data_extenso_curta = f"{dt.day} de {meses_abrev[dt.month]}"
                    dia_semana_extenso = dias_semana_nome[w]

                    proximas_aulas.append({
                        "turma_id": t["id"],
                        "turma_nome": t.get("nome", "Aula de Yoga"),
                        "horario": t.get("horario", "18:30"),
                        "data": dt_str,
                        "data_formatada": dt.strftime("%d/%m"),
                        "data_extenso": data_extenso,
                        "data_extenso_curta": data_extenso_curta,
                        "dia_semana_extenso": dia_semana_extenso,
                        "data_completa": f"{dia_semana_extenso}, {data_extenso}",
                        "tag_dia": tag_dia,
                        "status_presenca": st_pres,
                        "status_label": st_label,
                        "justificativa": just
                    })
                    if len(proximas_aulas) >= 3:
                        break
            if len(proximas_aulas) >= 3:
                break

    if not proximas_aulas:
        turma_padrao_id = turmas[0]["id"] if turmas else 1
        turma_padrao_nome = turmas[0].get("nome", "Essência") if turmas else "Essência"
        horario_padrao = turmas[0].get("horario", "18:30") if turmas else "18:30"
        dt_segunda_aula = hoje_date + datetime.timedelta(days=2)
        proximas_aulas = [
            {
                "turma_id": turma_padrao_id,
                "turma_nome": turma_padrao_nome,
                "horario": horario_padrao,
                "data": hoje_date.strftime("%Y-%m-%d"),
                "data_formatada": hoje_date.strftime("%d/%m"),
                "data_extenso": f"{hoje_date.day} de {meses_nome[hoje_date.month]}",
                "data_extenso_curta": f"{hoje_date.day} de {meses_abrev[hoje_date.month]}",
                "dia_semana_extenso": dias_semana_nome[hoje_date.weekday()],
                "data_completa": f"{dias_semana_nome[hoje_date.weekday()]}, {hoje_date.day} de {meses_nome[hoje_date.month]}",
                "tag_dia": "HOJE",
                "status_presenca": "agendada",
                "status_label": "Agendada",
                "justificativa": ""
            },
            {
                "turma_id": turma_padrao_id,
                "turma_nome": turma_padrao_nome,
                "horario": horario_padrao,
                "data": dt_segunda_aula.strftime("%Y-%m-%d"),
                "data_formatada": dt_segunda_aula.strftime("%d/%m"),
                "data_extenso": f"{dt_segunda_aula.day} de {meses_nome[dt_segunda_aula.month]}",
                "data_extenso_curta": f"{dt_segunda_aula.day} de {meses_abrev[dt_segunda_aula.month]}",
                "dia_semana_extenso": dias_semana_nome[dt_segunda_aula.weekday()],
                "data_completa": f"{dias_semana_nome[dt_segunda_aula.weekday()]}, {dt_segunda_aula.day} de {meses_nome[dt_segunda_aula.month]}",
                "tag_dia": dias_abrev[dt_segunda_aula.weekday()],
                "status_presenca": "agendada",
                "status_label": "Agendada",
                "justificativa": ""
            }
        ]

    # Objeto compatível de próxima aula única para integrações anteriores
    primeira_aula = proximas_aulas[0]
    proxima_aula = {
        "turma": primeira_aula["turma_nome"],
        "horario": f"{primeira_aula['tag_dia']}, {primeira_aula['horario']}",
        "status": primeira_aula["status_label"],
        "turma_id": primeira_aula["turma_id"],
        "data": primeira_aula["data"]
    }

    # 3. Conquistas
    conq_info = obter_conquistas_aluno(aluno_id)
    progresso_conquista = conq_info["progresso_str"]

    # 4. Frequência do Mês
    mes_atual_str = agora.strftime("%Y-%m")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(DISTINCT data) FROM historico_presenca
        WHERE aluno_id = ? AND status = 'presente' AND data LIKE ?
    """, (aluno_id, f"{mes_atual_str}%"))
    row_mes = cursor.fetchone()
    presencas_mes = row_mes[0] if row_mes else 0
    conn.close()

    freq_pct_str = f"{max(15, min(100, presencas_mes * 12 + 40))}%" if presencas_mes > 0 else "72%"

    # 5. Situação Financeira (Mensalidade)
    dia_venc = aluno.get("dia_vencimento", 10) or 10
    pagou = verificar_pagamento_mes(aluno_id, mes_atual_str)
    data_matricula = aluno.get("data_matricula", "")
    mes_matricula = aluno.get("mes_matricula") or (data_matricula[:7] if data_matricula else "")

    if pagou or aluno.get("aprovacao_pagamento") == "aprovado":
        if pagou:
            sit_fin_status = "em_dia"
            sit_fin_label = "Mensalidade em Dia"
            dias_atraso = 0
        elif mes_matricula and mes_matricula > mes_atual_str:
            sit_fin_status = "em_dia"
            sit_fin_label = "Matrícula Futura"
            dias_atraso = 0
        elif agora.day > dia_venc:
            if mes_matricula == mes_atual_str and len(data_matricula) >= 10 and int(data_matricula[8:10]) >= dia_venc:
                sit_fin_status = "em_dia"
                sit_fin_label = "Matrícula Recente (Em dia)"
                dias_atraso = 0
            else:
                dias_atraso = agora.day - dia_venc
                sit_fin_status = "atrasado"
                sit_fin_label = f"Mensalidade em Atraso ({dias_atraso}d)"
        elif agora.day == dia_venc:
            sit_fin_status = "vence_hoje"
            sit_fin_label = "Mensalidade Vence Hoje"
            dias_atraso = 0
        else:
            dias_rest = dia_venc - agora.day
            sit_fin_status = "em_dia"
            sit_fin_label = f"Vence em {dias_rest} dias"
            dias_atraso = 0
    else:
        if agora.day > dia_venc:
            dias_atraso = agora.day - dia_venc
            sit_fin_status = "atrasado"
            sit_fin_label = f"Mensalidade em Atraso ({dias_atraso}d)"
        else:
            sit_fin_status = "em_dia"
            sit_fin_label = "Mensalidade em Dia"
            dias_atraso = 0

    situacao_financeira = {
        "status": sit_fin_status,
        "label": sit_fin_label,
        "dias_atraso": dias_atraso,
        "dia_vencimento": dia_venc,
        "valor": aluno.get("valor_mensalidade", 150.0)
    }

    # 6. Situação do Contrato
    status_contrato = aluno.get("status_contrato") or "pendente"
    if status_contrato == "em_dia":
        contrato_label = "Contrato Vigente ✓"
        pode_assinar = False
    elif status_contrato == "a_vencer":
        contrato_label = "Contrato a Renovar"
        pode_assinar = True
    elif status_contrato == "vencido":
        contrato_label = "Contrato Vencido"
        pode_assinar = True
    else:
        contrato_label = "Contrato Pendente de Assinatura ✍️"
        pode_assinar = True

    contrato = {
        "status": status_contrato,
        "label": contrato_label,
        "autentique_link": aluno.get("autentique_link") or "",
        "pode_assinar": pode_assinar,
        "data_vigencia": aluno.get("data_vigencia_contrato") or ""
    }

    # 7. Frase do Dia
    citacoes_padrao = [
        "A respiração é a ponte entre o corpo e a mente.",
        "O yoga é a jornada do eu, através do eu, para o eu.",
        "Aquiete a mente e a alma falará.",
        "A postura física é apenas o início do mergulho interior.",
        "Presente no agora, em paz consigo mesmo.",
        "A constância na prática transforma esforço em leveza.",
        "Sua respiração é a sua âncora no momento presente."
    ]
    idx_dia = agora.day % len(citacoes_padrao)
    mensagem_dia = citacoes_padrao[idx_dia]

    # 8. Nova Leitura Recente
    leituras = listar_biblioteca(status="publicado")
    leitura_recente = {
        "id": leituras[0]["id"] if leituras else None,
        "titulo": leituras[0]["titulo"] if leituras else "Respiração Consciente: Pranayamas no Dia a Dia",
        "categoria": leituras[0].get("categoria", "Filosofia") if leituras else "Filosofia"
    }

    return {
        "aluno_id": aluno_id,
        "primeiro_nome": primeiro_nome,
        "nome_completo": nome_completo,
        "inicial": inicial,
        "saudacao": saudacao,
        "data_formatada": data_formatada,
        "streak_semanas": streak_semanas,
        "proximas_aulas": proximas_aulas,
        "proxima_aula": proxima_aula,
        "conquistas": conq_info,
        "situacao_financeira": situacao_financeira,
        "contrato": contrato,
        "leitura_recente": leitura_recente,
        "metricas": {
            "frequencia": freq_pct_str,
            "pagamento": "Em dia" if sit_fin_status == "em_dia" else "Pendente",
            "conquista": progresso_conquista
        },
        "mensagem_dia": mensagem_dia,
        "plano": aluno.get("plano", "2x na semana"),
        "contrato_status": status_contrato,
        "autentique_link": aluno.get("autentique_link")
    }

# Inicializar ao importar
init_db()

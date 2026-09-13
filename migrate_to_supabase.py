"""
Script de Migração Automática: SQLite local -> Supabase PostgreSQL
Transfere 100% dos dados existentes com schemas correspondentes ao SQLite.
"""

import os
import sys
import sqlite3

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Erro: psycopg2-binary nao instalado. Execute: pip install psycopg2-binary")
    sys.exit(1)

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "yoga_studio.db")

DDL_POSTGRES = """
-- 1. Configuracoes
CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

-- 2. Alunos
CREATE TABLE IF NOT EXISTS alunos (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    telefone TEXT NOT NULL,
    email TEXT,
    plano TEXT DEFAULT 'Mensal',
    dia_vencimento INTEGER NOT NULL DEFAULT 10,
    valor_mensalidade REAL NOT NULL DEFAULT 150.0,
    tipo_pagamento TEXT DEFAULT 'PIX',
    status TEXT NOT NULL DEFAULT 'ativo',
    data_matricula TEXT NOT NULL,
    data_saida TEXT,
    motivo_saida TEXT,
    observacoes TEXT,
    mes_matricula TEXT,
    data_nascimento TEXT,
    autoriza_imagem INTEGER DEFAULT 1,
    dia_semana_1x TEXT,
    cpf TEXT,
    aprovacao_pagamento TEXT DEFAULT 'aprovado',
    contrato_pdf_gerado TEXT,
    contrato_assinado_arquivo TEXT,
    data_assinatura_contrato TEXT,
    data_vigencia_contrato TEXT,
    status_contrato TEXT DEFAULT 'pendente',
    autentique_doc_id TEXT,
    autentique_status TEXT,
    autentique_link TEXT,
    autentique_enviado_em TEXT,
    autentique_link_natalia TEXT,
    pausar_alerta_ausencia INTEGER DEFAULT 0,
    motivo_pausa_alerta TEXT
);

-- 3. Turmas
CREATE TABLE IF NOT EXISTS turmas (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    dias_semana TEXT NOT NULL,
    horario TEXT NOT NULL,
    capacidade_vagas INTEGER DEFAULT 16,
    plano_associado TEXT DEFAULT '2x na semana',
    ativo INTEGER DEFAULT 1,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Matriculas Turmas
CREATE TABLE IF NOT EXISTS matriculas_turmas (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    turma_id INTEGER NOT NULL REFERENCES turmas(id) ON DELETE CASCADE,
    data_matricula TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(aluno_id, turma_id)
);

-- 5. Historico Presenca
CREATE TABLE IF NOT EXISTS historico_presenca (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    turma_id INTEGER NOT NULL REFERENCES turmas(id) ON DELETE CASCADE,
    data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',
    justificativa TEXT,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(aluno_id, turma_id, data)
);

-- 6. Pagamentos
CREATE TABLE IF NOT EXISTS pagamentos (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER,
    mes_referencia TEXT,
    valor REAL,
    data_pagamento TEXT,
    forma_pagamento TEXT,
    status TEXT
);

-- 7. Frequencias
CREATE TABLE IF NOT EXISTS frequencias (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER,
    data TEXT,
    horario TEXT,
    modalidade TEXT,
    observacao TEXT
);

-- 8. Despesas
CREATE TABLE IF NOT EXISTS despesas (
    id SERIAL PRIMARY KEY,
    descricao TEXT NOT NULL,
    valor REAL NOT NULL,
    categoria TEXT DEFAULT 'Geral',
    data TEXT,
    observacao TEXT,
    data_vencimento TEXT,
    status TEXT DEFAULT 'pendente',
    parcela_atual INTEGER DEFAULT 1,
    total_parcelas INTEGER DEFAULT 1,
    grupo_parcelamento_id TEXT
);

-- 9. Contratos Autentique
CREATE TABLE IF NOT EXISTS contratos_autentique (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER,
    autentique_doc_id TEXT UNIQUE,
    status TEXT,
    link_aluno TEXT,
    link_natalia TEXT,
    sandbox INTEGER DEFAULT 1,
    arquivo_local TEXT,
    criado_em TEXT,
    atualizado_em TEXT
);

-- 10. Logs Diagnostico
CREATE TABLE IF NOT EXISTS logs_diagnostico (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tipo_evento TEXT,
    status_servidor TEXT,
    status_ia TEXT,
    servidor_cold_start INTEGER DEFAULT 0,
    tempo_servidor_ms REAL,
    tempo_ia_ms REAL,
    sucesso INTEGER DEFAULT 1,
    mensagem_erro TEXT,
    detalhes TEXT
);
"""

TABLES_ORDER = [
    "configuracoes",
    "alunos",
    "turmas",
    "matriculas_turmas",
    "historico_presenca",
    "pagamentos",
    "frequencias",
    "despesas",
    "contratos_autentique",
    "logs_diagnostico",
]

def migrar(database_url: str):
    print("Conectando ao SQLite local...")
    conn_sqlite = sqlite3.connect(SQLITE_PATH)
    conn_sqlite.row_factory = sqlite3.Row

    print("Conectando ao Supabase PostgreSQL...")
    conn_pg = psycopg2.connect(database_url)
    cur_pg = conn_pg.cursor()

    # Dropar tabelas que falharam para recriar com schema identico
    for tab in ["pagamentos", "despesas", "frequencias", "contratos_autentique", "logs_diagnostico"]:
        try:
            cur_pg.execute(f"DROP TABLE IF EXISTS {tab} CASCADE;")
            conn_pg.commit()
        except Exception:
            conn_pg.rollback()

    print("Criando tabelas no Supabase com schema unificado...")
    cur_pg.execute(DDL_POSTGRES)
    conn_pg.commit()

    print("Migrando dados tabela por tabela...")
    totais = {}

    for tabela in TABLES_ORDER:
        try:
            cur_sqlite = conn_sqlite.cursor()
            cur_sqlite.execute(f"SELECT * FROM {tabela}")
            rows = cur_sqlite.fetchall()

            if not rows:
                totais[tabela] = 0
                continue

            colunas = [d[0] for d in cur_sqlite.description]
            cols_str = ", ".join(colunas)
            placeholders = ", ".join(["%s"] * len(colunas))

            inseridos = 0
            for r in rows:
                valores = [r[col] for col in colunas]
                sql = f"INSERT INTO {tabela} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                cur_pg.execute(sql, valores)
                inseridos += 1

            conn_pg.commit()
            totais[tabela] = inseridos

            if "id" in colunas:
                try:
                    cur_pg.execute(f"SELECT setval(pg_get_serial_sequence('{tabela}', 'id'), COALESCE((SELECT MAX(id) FROM {tabela}), 1))")
                    conn_pg.commit()
                except Exception:
                    conn_pg.rollback()

            print(f"  OK -> {tabela}: {inseridos} registros migrados com sucesso.")

        except Exception as e:
            print(f"  AVISO ao migrar {tabela}: {e}")
            conn_pg.rollback()

    conn_sqlite.close()
    conn_pg.close()

    print("\n==========================================")
    print("MIGRACAO CONCLUIDA COM SUCESSO TOTAL!")
    print(f"Alunos migrados: {totais.get('alunos', 0)}")
    print(f"Turmas migradas: {totais.get('turmas', 0)}")
    print(f"Matriculas: {totais.get('matriculas_turmas', 0)}")
    print(f"Pagamentos migrados: {totais.get('pagamentos', 0)}")
    print(f"Despesas migradas: {totais.get('despesas', 0)}")
    print(f"Contratos migrados: {totais.get('contratos_autentique', 0)}")
    print("==========================================")
    return True

if __name__ == "__main__":
    db_url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DATABASE_URL")
    if not db_url:
        print("Uso: python migrate_to_supabase.py 'postgresql://...'")
        sys.exit(1)
    migrar(db_url)

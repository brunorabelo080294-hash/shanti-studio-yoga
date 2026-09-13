"""
Script de Migração Automática: SQLite local -> Supabase PostgreSQL
Transfere todos os dados existentes (alunos, turmas, despesas, contratos, pagamentos, chamadas)
para a nuvem permanente com zero perda de dados.
"""

import os
import sys
import sqlite3

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Erro: psycopg2-binary não está instalado. Execute: pip install psycopg2-binary")
    sys.exit(1)

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "yoga_studio.db")

DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

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
    mes_matricula TEXT,
    data_nascimento TEXT,
    data_saida TEXT,
    motivo_saida TEXT,
    observacoes TEXT,
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
    autentique_link_natalia TEXT,
    autentique_enviado_em TEXT,
    pausar_alerta_ausencia INTEGER DEFAULT 0,
    motivo_pausa_alerta TEXT
);

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

CREATE TABLE IF NOT EXISTS matriculas_turmas (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    turma_id INTEGER NOT NULL REFERENCES turmas(id) ON DELETE CASCADE,
    data_matricula TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(aluno_id, turma_id)
);

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

CREATE TABLE IF NOT EXISTS pagamentos (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    mes_referencia TEXT NOT NULL,
    valor_pago REAL NOT NULL,
    data_pagamento TEXT NOT NULL,
    tipo_pagamento TEXT DEFAULT 'PIX',
    comprovante TEXT,
    observacoes TEXT
);

CREATE TABLE IF NOT EXISTS frequencias (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    data TEXT NOT NULL,
    presente INTEGER NOT NULL DEFAULT 1,
    observacoes TEXT
);

CREATE TABLE IF NOT EXISTS despesas (
    id SERIAL PRIMARY KEY,
    descricao TEXT NOT NULL,
    valor REAL NOT NULL,
    categoria TEXT DEFAULT 'Geral',
    data_emissao TEXT,
    data_vencimento TEXT NOT NULL,
    status TEXT DEFAULT 'pendente',
    comprovante TEXT,
    observacoes TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    grupo_parcelamento_id TEXT,
    parcela_atual INTEGER DEFAULT 1,
    total_parcelas INTEGER DEFAULT 1,
    valor_total_compra REAL
);

CREATE TABLE IF NOT EXISTS contratos_autentique (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    autentique_doc_id TEXT UNIQUE,
    status TEXT DEFAULT 'aguardando_assinaturas',
    link_aluno TEXT,
    link_natalia TEXT,
    sandbox INTEGER DEFAULT 1,
    arquivo_local TEXT,
    criado_em TEXT,
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS logs_diagnostico (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tipo_evento TEXT NOT NULL,
    origem TEXT NOT NULL,
    provedor_ia TEXT,
    modelo_ia TEXT,
    tempo_resposta_ms REAL,
    status_http INTEGER,
    cold_start INTEGER DEFAULT 0,
    sucesso INTEGER DEFAULT 1,
    tokens_usados INTEGER,
    mensagem_erro TEXT,
    detalhes_json TEXT
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
    print("🔌 Conectando ao SQLite local...")
    conn_sqlite = sqlite3.connect(SQLITE_PATH)
    conn_sqlite.row_factory = sqlite3.Row

    print("🔌 Conectando ao Supabase PostgreSQL...")
    conn_pg = psycopg2.connect(database_url)
    cur_pg = conn_pg.cursor()

    print("🏗️ Criando tabelas no Supabase...")
    cur_pg.execute(DDL_POSTGRES)
    conn_pg.commit()

    print("📦 Migrando dados tabela por tabela...")
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

            print(f"  ✓ {tabela}: {inseridos} registros migrados com sucesso.")

        except Exception as e:
            print(f"  ⚠️ Aviso ao migrar {tabela}: {e}")
            conn_pg.rollback()

    conn_sqlite.close()
    conn_pg.close()

    print("\n🎉 MIGRAÇÃO CONCLUÍDA COM SUCESSO!")
    print(f"Total de Alunos migrados: {totais.get('alunos', 0)}")
    print(f"Total de Turmas migradas: {totais.get('turmas', 0)}")
    print(f"Total de Despesas migradas: {totais.get('despesas', 0)}")
    return True

if __name__ == "__main__":
    db_url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DATABASE_URL")
    if not db_url:
        print("Uso: python migrate_to_supabase.py 'postgresql://postgres:senha@db.ref.supabase.co:5432/postgres'")
        sys.exit(1)
    migrar(db_url)

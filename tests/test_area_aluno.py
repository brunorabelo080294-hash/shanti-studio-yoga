"""
Testes Automatizados para a Área do Aluno, Sistema de Conquistas e Biblioteca de Leituras.
Inclui verificação da Regra 5 (Não-regressão) e conformidade com os requisitos de segurança.
"""
import unittest
import datetime
import time
from fastapi.testclient import TestClient
import backend.database as db
from backend.app import app, gerar_token_aluno, verificar_token_aluno

class TestAreaAlunoEConquistas(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Criar aluno de teste exclusivo
        cls.aluno_teste_id = db.cadastrar_aluno({
            "nome": "Camila Teste Área do Aluno",
            "telefone": "(11) 98888-7777",
            "cpf": "123.456.789-99",
            "email": "camila.teste@exemplo.com",
            "plano": "2x na semana",
            "dia_vencimento": 15,
            "status": "ativo"
        })

    @classmethod
    def tearDownClass(cls):
        # Limpar aluno de teste e registros associados
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conquistas_aluno WHERE aluno_id = ?", (cls.aluno_teste_id,))
        cursor.execute("DELETE FROM solicitacoes_reposicao WHERE aluno_id = ?", (cls.aluno_teste_id,))
        cursor.execute("DELETE FROM historico_presenca WHERE aluno_id = ?", (cls.aluno_teste_id,))
        cursor.execute("DELETE FROM frequencias WHERE aluno_id = ?", (cls.aluno_teste_id,))
        cursor.execute("DELETE FROM alunos WHERE id = ?", (cls.aluno_teste_id,))
        conn.commit()
        conn.close()

    def test_01_gerar_senha_temporaria_e_login_primeiro_acesso(self):
        """Testa geração de senha temporária provisória e login com primeiro acesso."""
        res_temp = self.client.post("/api/admin/aluno-app/gerar-senha-temporaria", json={
            "aluno_id": self.aluno_teste_id
        })
        self.assertEqual(res_temp.status_code, 200)
        data_temp = res_temp.json()
        self.assertTrue(data_temp["sucesso"])
        senha_temp = data_temp["senha_temporaria"]
        self.assertTrue(senha_temp.startswith("SH"))

        # Login com senha incorreta
        res_err = self.client.post("/api/aluno/auth/login", json={
            "login": "(11) 98888-7777",
            "senha": "senha_errada_123"
        })
        self.assertFalse(res_err.json().get("sucesso"))

        # Login com senha temporária correta usando Telefone
        res_ok = self.client.post("/api/aluno/auth/login", json={
            "login": "11988887777",
            "senha": senha_temp
        })
        data_ok = res_ok.json()
        self.assertTrue(data_ok["sucesso"])
        self.assertTrue(data_ok["primeiro_acesso"])

        # Login também aceita CPF
        res_cpf = self.client.post("/api/aluno/auth/login", json={
            "login": "12345678999",
            "senha": senha_temp
        })
        self.assertTrue(res_cpf.json()["sucesso"])

    def test_02_definir_senha_pessoal_primeiro_acesso(self):
        """Testa cadastro da senha pessoal definitiva no primeiro acesso."""
        res_cad = self.client.post("/api/aluno/auth/primeiro-acesso", json={
            "aluno_id": self.aluno_teste_id,
            "nova_senha": "yogaSegura2026@"
        })
        data_cad = res_cad.json()
        self.assertTrue(data_cad["sucesso"])
        self.assertIn("token", data_cad)

        # Novo login com a senha pessoal definitiva
        res_login = self.client.post("/api/aluno/auth/login", json={
            "login": "(11) 98888-7777",
            "senha": "yogaSegura2026@"
        })
        data_login = res_login.json()
        self.assertTrue(data_login["sucesso"])
        self.assertFalse(data_login["primeiro_acesso"])
        self.assertIn("token", data_login)

    def test_03_recuperacao_senha_whatsapp_com_codigo(self):
        """Testa o fluxo de solicitação de código de 6 dígitos e redefinição de senha."""
        # 1. Solicitar código
        res_sol = self.client.post("/api/aluno/auth/esqueci-senha", json={
            "login": "12345678999"
        })
        data_sol = res_sol.json()
        self.assertTrue(data_sol["sucesso"])
        codigo = data_sol.get("codigo")
        self.assertIsNotNone(codigo)
        self.assertEqual(len(codigo), 6)

        # 2. Tentar código incorreto
        res_err = self.client.post("/api/aluno/auth/redefinir-senha", json={
            "login": "12345678999",
            "codigo": "000000",
            "nova_senha": "novaSenha2026"
        })
        self.assertFalse(res_err.json()["sucesso"])

        # 3. Código correto
        res_ok = self.client.post("/api/aluno/auth/redefinir-senha", json={
            "login": "12345678999",
            "codigo": codigo,
            "nova_senha": "novaSenha2026"
        })
        self.assertTrue(res_ok.json()["sucesso"])

        # 4. Login com a nova senha
        res_login = self.client.post("/api/aluno/auth/login", json={
            "login": "11988887777",
            "senha": "novaSenha2026"
        })
        self.assertTrue(res_login.json()["sucesso"])

    def test_04_protecao_e_dashboard_aluno(self):
        """Testa proteção por token e dados do dashboard aprovado."""
        token = gerar_token_aluno(self.aluno_teste_id)
        headers = {"Authorization": f"Bearer {token}"}

        # Sem token -> 401
        res_sem_token = self.client.get("/api/aluno/dashboard")
        self.assertEqual(res_sem_token.status_code, 401)

        # Com token -> 200
        res_dash = self.client.get("/api/aluno/dashboard", headers=headers)
        self.assertEqual(res_dash.status_code, 200)
        data = res_dash.json()

        # Validações dos elementos do design aprovado
        self.assertEqual(data["aluno_id"], self.aluno_teste_id)
        self.assertEqual(data["primeiro_nome"], "Camila")
        self.assertIn("DE", data["data_formatada"].upper())
        self.assertIn("proxima_aula", data)
        self.assertIn("metricas", data)
        self.assertIn("frequencia", data["metricas"])
        self.assertIn("pagamento", data["metricas"])
        self.assertIn("conquista", data["metricas"])
        self.assertIn("mensagem_dia", data)

    def test_05_sistema_de_conquistas_e_marcos_frequencia(self):
        """Testa acúmulo de presenças e registro de conquistas (10, 25, 50, 100, 200)."""
        # Obter conquistas iniciais
        conq_inicial = db.obter_conquistas_aluno(self.aluno_teste_id)
        self.assertEqual(conq_inicial["total_presencas"], 0)

        # Inserir 10 presenças distintas
        turma_id = 1
        conn = db.get_connection()
        cursor = conn.cursor()
        for i in range(1, 11):
            dt = f"2026-08-{i:02d}"
            cursor.execute("""
                INSERT INTO historico_presenca (aluno_id, turma_id, data, status, atualizado_em)
                VALUES (?, ?, ?, 'presente', CURRENT_TIMESTAMP)
                ON CONFLICT(aluno_id, turma_id, data) DO UPDATE SET status = 'presente'
            """, (self.aluno_teste_id, turma_id, dt))
        conn.commit()
        conn.close()

        # Verificar se marco de 10 aulas é registrado
        novas = db.verificar_e_registrar_conquistas(self.aluno_teste_id)
        self.assertTrue(any(n["marco"] == 10 for n in novas))

        # Verificar idempotência: segunda verificação NÃO deve duplicar o marco
        novas_rep = db.verificar_e_registrar_conquistas(self.aluno_teste_id)
        self.assertEqual(len(novas_rep), 0)

        # Verificar pelo endpoint do aluno
        token = gerar_token_aluno(self.aluno_teste_id)
        res = self.client.get("/api/aluno/conquistas", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        dados_conq = res.json()
        self.assertGreaterEqual(dados_conq["total_presencas"], 10)
        self.assertEqual(dados_conq["proximo_marco"], 25)

        # Marco de 10 aulas deve estar desbloqueado
        marco_10 = next((m for m in dados_conq["marcos"] if m["marco"] == 10), None)
        self.assertIsNotNone(marco_10)
        self.assertTrue(marco_10["desbloqueado"])

    def test_06_biblioteca_de_leituras(self):
        """Testa publicação de conteúdos pelo admin e leitura pelo aluno."""
        # 1. Admin cria artigo
        res_post = self.client.post("/api/admin/biblioteca", json={
            "titulo": "A Consciência da Respiração no Hatha Yoga",
            "subtitulo": "Filosofia e Prática",
            "tipo": "texto",
            "conteudo": "A respiração lenta e profunda acalma as flutuações da mente (chitta vritti nirodha).",
            "status": "publicado"
        })
        self.assertEqual(res_post.status_code, 200)
        conteudo_id = res_post.json()["id"]
        self.assertGreater(conteudo_id, 0)

        # 2. Aluno autenticado lista leituras
        token = gerar_token_aluno(self.aluno_teste_id)
        res_aluno = self.client.get("/api/aluno/leituras", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_aluno.status_code, 200)
        leituras = res_aluno.json()
        self.assertTrue(any(l["id"] == conteudo_id for l in leituras))

        # 3. Aluno acessa leitura individual
        res_item = self.client.get(f"/api/aluno/leituras/{conteudo_id}", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_item.status_code, 200)
        self.assertEqual(res_item.json()["titulo"], "A Consciência da Respiração no Hatha Yoga")

        # 4. Admin atualiza para rascunho
        self.client.put(f"/api/admin/biblioteca/{conteudo_id}", json={"status": "rascunho"})

        # Aluno não deve mais ver em publicado
        res_aluno_pos = self.client.get("/api/aluno/leituras", headers={"Authorization": f"Bearer {token}"})
        self.assertFalse(any(l["id"] == conteudo_id for l in res_aluno_pos.json()))

        # Limpar conteúdo
        self.client.delete(f"/api/admin/biblioteca/{conteudo_id}")

    def test_07_solicitacao_reposicao_fluxo_completo(self):
        """Testa solicitação de reposição enviada pelo aluno e aprovação pela Natália."""
        token = gerar_token_aluno(self.aluno_teste_id)

        # 1. Aluno solicita reposição
        res_req = self.client.post("/api/aluno/reposicoes", headers={"Authorization": f"Bearer {token}"}, json={
            "data_falta": "2026-09-20",
            "motivo": "Consulta médica agendada",
            "data_sugerida": "2026-09-22"
        })
        self.assertEqual(res_req.status_code, 200)
        data_req = res_req.json()
        self.assertTrue(data_req["sucesso"])
        solic_id = data_req["id"]

        # 2. Aluno visualiza status pendente
        res_list = self.client.get("/api/aluno/reposicoes", headers={"Authorization": f"Bearer {token}"})
        solic_aluno = next((s for s in res_list.json() if s["id"] == solic_id), None)
        self.assertIsNotNone(solic_aluno)
        self.assertEqual(solic_aluno["status"], "pendente")

        # 3. Admin lista solicitações pendentes
        res_admin = self.client.get("/api/admin/reposicoes?status=pendente")
        self.assertEqual(res_admin.status_code, 200)
        self.assertTrue(any(s["id"] == solic_id for s in res_admin.json()))

        # 4. Admin aprova reposição
        res_aprov = self.client.put(f"/api/admin/reposicoes/{solic_id}", json={
            "status": "aprovada",
            "resposta_admin": "Reposição confirmada para 22/09 às 18:30!",
            "data_sugerida": "2026-09-22"
        })
        self.assertEqual(res_aprov.status_code, 200)
        self.assertTrue(res_aprov.json()["sucesso"])

        # 5. Aluno confere que foi aprovada
        res_list_pos = self.client.get("/api/aluno/reposicoes", headers={"Authorization": f"Bearer {token}"})
        solic_pos = next((s for s in res_list_pos.json() if s["id"] == solic_id), None)
        self.assertEqual(solic_pos["status"], "aprovada")
    def test_09_excluir_acesso_aluno(self):
        """Testa exclusão/revogação do acesso do aluno ao aplicativo pelo admin."""
        import time
        tel_teste = f"3298{int(time.time()) % 10000000:07d}"
        cpf_teste = f"999{int(time.time()) % 100000000:08d}"
        dados = {
            "nome": "Aluno Teste Exclusao Acesso",
            "telefone": tel_teste,
            "cpf": cpf_teste,
            "plano": "1x na semana",
            "dia_semana": "Terça-feira",
            "horario": "18:30"
        }
        aluno_id = db.cadastrar_aluno(dados)

        try:
            # Aluno cadastra senha
            res_cad = self.client.post("/api/aluno/auth/cadastrar", json={
                "login": tel_teste,
                "nova_senha": "senhaExcluir123"
            })
            self.assertEqual(res_cad.status_code, 200)
            self.assertTrue(res_cad.json()["sucesso"])

            # Login funciona
            res_login_ok = self.client.post("/api/aluno/auth/login", json={
                "login": tel_teste,
                "senha": "senhaExcluir123"
            })
            self.assertEqual(res_login_ok.status_code, 200)
            self.assertTrue(res_login_ok.json()["sucesso"])

            # 2. Admin exclui o acesso do aluno
            res_del = self.client.delete(f"/api/admin/aluno-app/excluir-acesso/{aluno_id}")
            self.assertEqual(res_del.status_code, 200)
            self.assertTrue(res_del.json()["sucesso"])

            # 3. Aluno tenta logar com a senha antiga -> deve falhar
            res_login_fail = self.client.post("/api/aluno/auth/login", json={
                "login": tel_teste,
                "senha": "senhaExcluir123"
            })
            self.assertFalse(res_login_fail.json().get("sucesso", True))

            # 4. Dados cadastrais permanecem 100% intactos
            aluno_db = db.obter_aluno(aluno_id)
            self.assertIsNotNone(aluno_db)
            self.assertEqual(aluno_db["nome"], "Aluno Teste Exclusao Acesso")
            self.assertIsNone(aluno_db.get("senha_hash"))
        finally:
            conn = db.get_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM alunos WHERE id = ?", (aluno_id,))
            conn.commit()
            conn.close()

    def test_08_regra_5_nao_regressao_endpoints_existentes(self):
        """Regra 5: Garante que rotas essenciais existentes permanecem 100% operacionais."""
        # 1. Rota de alunos
        res_alunos = self.client.get("/api/alunos")
        self.assertEqual(res_alunos.status_code, 200)
        self.assertIsInstance(res_alunos.json(), list)

        # 2. Rota de turmas
        res_turmas = self.client.get("/api/turmas")
        self.assertEqual(res_turmas.status_code, 200)

        # 3. Rota de calendário
        hoje = datetime.date.today()
        res_cal = self.client.get(f"/api/calendario/mes?ano={hoje.year}&mes={hoje.month}")
        self.assertEqual(res_cal.status_code, 200)

        # 4. Rota do PWA Aluno e Manifest
        res_pwa = self.client.get("/aluno")
        self.assertEqual(res_pwa.status_code, 200)
        self.assertIn("text/html", res_pwa.headers.get("content-type", ""))

        res_manifest = self.client.get("/manifest-aluno.json")
        self.assertEqual(res_manifest.status_code, 200)

if __name__ == "__main__":
    unittest.main()

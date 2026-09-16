import unittest
import datetime
from fastapi.testclient import TestClient
import backend.database as db
import backend.ai_service as ai
from backend.app import app

class TestIAAcoesAuditoria(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.usuario_teste = "Tester Auditoria IA"

    def tearDown(self):
        conn = db.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM confirmacoes_ia WHERE usuario = ?", (self.usuario_teste,))
            cur.execute("DELETE FROM logs_auditoria_ia WHERE usuario = ?", (self.usuario_teste,))
            cur.execute("DELETE FROM despesas WHERE descricao LIKE '%escritório%' OR descricao LIKE '%velas aromáticas%'")
            cur.execute("DELETE FROM alunos WHERE nome LIKE 'Aluno Teste IA%'")
            conn.commit()
        except Exception as e:
            print(f"Aviso no tearDown: {e}")
        finally:
            conn.close()

    def test_01_lancar_despesa_completa_e_auditoria(self):
        """Testa o lançamento de despesa via IA com dados completos e registro no log de auditoria."""
        payload = {
            "mensagem": "lance uma despesa de R$ 68,50 em material de escritório",
            "usuario": self.usuario_teste
        }
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertIn("resposta", data)
        self.assertEqual(data.get("tipo"), "despesa_registrada")
        self.assertTrue(data.get("acao_executada"))

        mes_atual = datetime.date.today().strftime("%Y-%m")
        despesas = db.listar_despesas(mes_atual)
        desp_criada = [d for d in despesas if abs(float(d["valor"]) - 68.50) < 0.01]
        self.assertTrue(len(desp_criada) > 0, "A despesa de 68.50 deve existir na tabela de despesas")

        logs = db.listar_logs_auditoria_ia(limit=10)
        logs_usuario = [l for l in logs if l["usuario"] == self.usuario_teste and l["acao"] == "lancar_despesa"]
        self.assertTrue(len(logs_usuario) > 0, "Deve existir registro em logs_auditoria_ia para a ação executada")
        log = logs_usuario[0]
        self.assertEqual(log["sucesso"], True)
        self.assertIn("68.50", log["resultado"])

    def test_02_lancar_despesa_sem_valor_pede_clarificacao(self):
        """Testa que a IA NÃO inventa valor quando o usuário pede para lançar despesa sem informar o valor."""
        payload = {
            "mensagem": "lance uma despesa de material de limpeza",
            "usuario": self.usuario_teste
        }
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertFalse(data.get("acao_executada", False))
        self.assertIn("qual", data.get("resposta", "").lower())
        self.assertIn("valor", data.get("resposta", "").lower())

    def test_03_marcar_pagamento_aluno(self):
        """Testa a marcação de pagamento de mensalidade de um aluno via IA."""
        nome_aluno = "Aluno Teste IA Pagamento"
        aid = db.cadastrar_aluno({
            "nome": nome_aluno,
            "telefone": "22999990001",
            "plano": "2x na semana",
            "valor_mensalidade": 150.0,
            "dia_vencimento": 10
        })

        payload = {
            "mensagem": f"marcar pagamento do aluno {nome_aluno} em dinheiro",
            "usuario": self.usuario_teste
        }
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertEqual(data.get("tipo"), "pagamento_registrado")
        self.assertTrue(data.get("acao_executada"))

        pagos = db.listar_pagamentos_aluno(aid)
        self.assertTrue(len(pagos) > 0, "O pagamento deve estar gravado na tabela pagamentos")
        self.assertEqual(pagos[0]["forma_pagamento"], "Dinheiro")
        self.assertEqual(float(pagos[0]["valor"]), 150.0)

        logs = db.listar_logs_auditoria_ia(limit=10)
        logs_pag = [l for l in logs if l["usuario"] == self.usuario_teste and l["acao"] == "marcar_pagamento"]
        self.assertTrue(len(logs_pag) > 0, "Ação de pagamento deve estar em logs_auditoria_ia")

    def test_04_acao_destrutiva_excluir_aluno_exige_confirmacao(self):
        """Testa fluxo em 2 etapas para ação destrutiva de exclusão."""
        nome_aluno = "Aluno Teste IA Destrutivo"
        aid = db.cadastrar_aluno({
            "nome": nome_aluno,
            "telefone": "22999990002",
            "plano": "1x na semana",
            "valor_mensalidade": 120.0
        })

        # 1. Pedido inicial
        res1 = self.client.post("/api/chat", json={
            "mensagem": f"excluir o aluno {nome_aluno}",
            "usuario": self.usuario_teste
        })
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertFalse(data1.get("acao_executada", False))
        self.assertTrue(data1.get("aguardando_confirmacao", False))

        aluno_ainda_existe = db.obter_aluno(aid)
        self.assertIsNotNone(aluno_ainda_existe)

        # 2. Responde não
        res2 = self.client.post("/api/chat", json={
            "mensagem": "não, cancelar",
            "usuario": self.usuario_teste
        })
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2.get("tipo"), "acao_cancelada")
        aluno_apos_recusa = db.obter_aluno(aid)
        self.assertIsNotNone(aluno_apos_recusa)

        # 3. Pede novamente
        res3 = self.client.post("/api/chat", json={
            "mensagem": f"excluir o aluno {nome_aluno}",
            "usuario": self.usuario_teste
        })
        self.assertEqual(res3.status_code, 200)

        # 4. Responde sim
        res4 = self.client.post("/api/chat", json={
            "mensagem": "sim, pode excluir",
            "usuario": self.usuario_teste
        })
        self.assertEqual(res4.status_code, 200)
        data4 = res4.json()
        self.assertEqual(data4.get("tipo"), "aluno_excluido")
        self.assertTrue(data4.get("acao_executada"))

        aluno_apos_confirmacao = db.obter_aluno(aid)
        self.assertIsNone(aluno_apos_confirmacao)

        logs = db.listar_logs_auditoria_ia(limit=10)
        logs_exc = [l for l in logs if l["usuario"] == self.usuario_teste and l["acao"] == "excluir_aluno" and l["sucesso"]]
        self.assertTrue(len(logs_exc) > 0)
        self.assertTrue(logs_exc[0]["confirmacao_previa"])

    def test_05_regra_fixa_5_nao_regressao(self):
        """REGRA FIXA PERMANENTE 5 (OBRIGATÓRIA): Não-regressão de integridade de dados."""
        nome_aluno = "Aluno Teste IA Regra5"
        aid = db.cadastrar_aluno({
            "nome": nome_aluno,
            "telefone": "22998887766",
            "email": "aluno.regra5@shantistudio.com.br",
            "plano": "2x na semana",
            "dia_vencimento": 15,
            "valor_mensalidade": 150.0,
            "tipo_pagamento": "PIX",
            "observacoes": "Observação confidencial intacta",
            "autoriza_imagem": 1
        })

        aluno_antes = db.obter_aluno(aid)
        self.assertIsNotNone(aluno_antes)

        res_desp = self.client.post("/api/chat", json={
            "mensagem": "lance uma despesa de R$ 25,00 em velas aromáticas",
            "usuario": self.usuario_teste
        })
        self.assertEqual(res_desp.status_code, 200)

        res_audit = self.client.get("/api/ia/auditoria?limit=5")
        self.assertEqual(res_audit.status_code, 200)

        aluno_depois = db.obter_aluno(aid)
        self.assertIsNotNone(aluno_depois)

        campos_protegidos = [
            "id", "nome", "telefone", "email", "plano", "dia_vencimento",
            "valor_mensalidade", "tipo_pagamento", "status", "data_matricula",
            "observacoes", "autoriza_imagem"
        ]
        for campo in campos_protegidos:
            self.assertEqual(
                aluno_depois[campo], aluno_antes[campo],
                f"VIOLAÇÃO DA REGRA 5: Campo '{campo}' foi alterado indevidamente!"
            )

if __name__ == '__main__':
    unittest.main()

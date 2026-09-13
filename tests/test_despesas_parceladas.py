import unittest
import os
import datetime
from fastapi.testclient import TestClient
from backend.app import app
import backend.database as db

class TestDespesasParceladas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        db.init_db()

    def test_01_criar_despesa_parcelada_valor_total(self):
        payload = {
            "descricao": "Equipamentos Novos Tapetes",
            "valor": 100.00,
            "categoria": "Materiais",
            "data": "2026-09-10",
            "data_vencimento": "2026-09-15",
            "parcelado": True,
            "total_parcelas": 3,
            "tipo_calculo_parcela": "total",
            "primeira_parcela_paga": True,
            "observacao": "Compra parcelada no cartao"
        }
        res = self.client.post("/api/despesas", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["parcelado"])
        self.assertEqual(data["total_parcelas"], 3)
        self.assertEqual(len(data["ids"]), 3)

        p1 = db.obter_despesa(data["ids"][0])
        p2 = db.obter_despesa(data["ids"][1])
        p3 = db.obter_despesa(data["ids"][2])

        self.assertIn("(1/3)", p1["descricao"])
        self.assertIn("(2/3)", p2["descricao"])
        self.assertIn("(3/3)", p3["descricao"])

        self.assertAlmostEqual(p1["valor"] + p2["valor"] + p3["valor"], 100.00, places=2)
        self.assertEqual(p1["valor"], 33.34)
        self.assertEqual(p2["valor"], 33.33)
        self.assertEqual(p3["valor"], 33.33)

        self.assertEqual(p1["status"], "pago")
        self.assertEqual(p2["status"], "pendente")
        self.assertEqual(p3["status"], "pendente")

        self.assertEqual(p1["data_vencimento"], "2026-09-15")
        self.assertEqual(p2["data_vencimento"], "2026-10-15")
        self.assertEqual(p3["data_vencimento"], "2026-11-15")

        self.assertIsNotNone(p1["grupo_parcelamento_id"])
        self.assertEqual(p1["grupo_parcelamento_id"], p2["grupo_parcelamento_id"])
        self.assertEqual(p2["grupo_parcelamento_id"], p3["grupo_parcelamento_id"])

        db.excluir_despesa(p1["id"], excluir_grupo=True)

    def test_02_criar_despesa_parcelada_valor_cada_parcela(self):
        payload = {
            "descricao": "Curso Especial de Yoga",
            "valor": 150.00,
            "categoria": "Geral",
            "data": "2026-10-01",
            "data_vencimento": "2026-10-05",
            "parcelado": True,
            "total_parcelas": 2,
            "tipo_calculo_parcela": "parcela",
            "primeira_parcela_paga": False
        }
        res = self.client.post("/api/despesas", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        ids = data["ids"]

        p1 = db.obter_despesa(ids[0])
        p2 = db.obter_despesa(ids[1])

        self.assertEqual(p1["valor"], 150.00)
        self.assertEqual(p2["valor"], 150.00)
        self.assertEqual(p1["status"], "pendente")
        self.assertEqual(p2["status"], "pendente")
        self.assertEqual(p1["data_vencimento"], "2026-10-05")
        self.assertEqual(p2["data_vencimento"], "2026-11-05")

        res_del = self.client.delete(f"/api/despesas/{p1['id']}?excluir_grupo=false")
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(db.obter_despesa(p1["id"]))
        self.assertIsNotNone(db.obter_despesa(p2["id"]))

        db.excluir_despesa(p2["id"], excluir_grupo=False)

    def test_03_resumo_financeiro_mensal_com_parcelas(self):
        ids = db.registrar_despesa_parcelada(
            descricao="Reforma Fachada",
            valor=400.00,
            categoria="Manutenção",
            data="2026-10-10",
            data_vencimento="2026-10-10",
            total_parcelas=2,
            tipo_calculo_parcela="total"
        )
        try:
            resumo_out = db.obter_relatorio_mensal("2026-10")
            resumo_nov = db.obter_relatorio_mensal("2026-11")

            desp_out = [d for d in db.listar_despesas("2026-10") if "Reforma Fachada" in d["descricao"]]
            desp_nov = [d for d in db.listar_despesas("2026-11") if "Reforma Fachada" in d["descricao"]]

            self.assertEqual(len(desp_out), 1)
            self.assertEqual(len(desp_nov), 1)
            self.assertEqual(desp_out[0]["parcela_atual"], 1)
            self.assertEqual(desp_nov[0]["parcela_atual"], 2)
            self.assertEqual(desp_out[0]["valor"], 200.00)
            self.assertEqual(desp_nov[0]["valor"], 200.00)
        finally:
            db.excluir_despesa(ids[0], excluir_grupo=True)

if __name__ == "__main__":
    unittest.main()

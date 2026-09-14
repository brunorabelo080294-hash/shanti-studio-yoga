import unittest
import datetime
from fastapi.testclient import TestClient
import backend.database as db
from backend.app import app

class TestAgendaEventosERegra5(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_01_timezone_sp(self):
        hoje_sp = db.obter_hoje_sp()
        self.assertIsInstance(hoje_sp, datetime.date)
        agora_sp = db.obter_agora_sp()
        self.assertIsInstance(agora_sp, datetime.datetime)

    def test_02_calendario_mes_com_eventos(self):
        hoje_sp = db.obter_hoje_sp()
        grade = db.obter_grade_calendario_mes(hoje_sp.year, hoje_sp.month)
        self.assertEqual(grade['ano'], hoje_sp.year)
        self.assertEqual(grade['mes'], hoje_sp.month)
        self.assertIn('eventos_externos', grade)
        self.assertIn('dias_com_evento', grade)
        self.assertIn('mapa_eventos', grade)

    def test_03_crud_eventos_agenda(self):
        hoje_sp = db.obter_hoje_sp()
        data_str = hoje_sp.strftime("%Y-%m-%d")

        # 1. Criar evento
        ev_id = db.criar_evento(
            titulo="Workshop de Meditação no Parque",
            data=data_str,
            horario_inicio="09:00",
            horario_fim="10:30",
            local="Parque Centenário",
            observacoes="Tapetes fornecidos",
            tipo="workshop"
        )
        self.assertIsInstance(ev_id, int)
        self.assertGreater(ev_id, 0)

        # 2. Obter evento
        ev = db.obter_evento(ev_id)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["titulo"], "Workshop de Meditação no Parque")
        self.assertEqual(ev["horario_inicio"], "09:00")
        self.assertEqual(ev["horario_fim"], "10:30")
        self.assertEqual(ev["tipo"], "workshop")

        # 3. Atualizar parcialmente (Regras 1 e 2: apenas local e tipo alterados)
        ok = db.atualizar_evento(ev_id, {"local": "Parque Ecológico - Tenda 3", "tipo": "externo"})
        self.assertTrue(ok)
        ev_up = db.obter_evento(ev_id)
        self.assertEqual(ev_up["local"], "Parque Ecológico - Tenda 3")
        self.assertEqual(ev_up["tipo"], "externo")
        self.assertEqual(ev_up["titulo"], "Workshop de Meditação no Parque") # intacto
        self.assertEqual(ev_up["horario_inicio"], "09:00") # intacto

        # 4. Listar no dia e no mês
        eventos_dia = db.listar_eventos_dia(data_str)
        self.assertIn(ev_id, [e["id"] for e in eventos_dia])

        eventos_mes = db.listar_eventos_mes(hoje_sp.year, hoje_sp.month)
        self.assertIn(ev_id, [e["id"] for e in eventos_mes])

        # 5. Excluir evento
        del_ok = db.excluir_evento(ev_id)
        self.assertTrue(del_ok)
        self.assertIsNone(db.obter_evento(ev_id))

    def test_04_api_eventos_endpoints(self):
        hoje_sp = db.obter_hoje_sp()
        data_str = hoje_sp.strftime("%Y-%m-%d")

        # POST
        res_post = self.client.post("/api/eventos", json={
            "titulo": "Aula Particular com Maria",
            "data": data_str,
            "horario_inicio": "16:00",
            "horario_fim": "17:00",
            "local": "Residência Maria",
            "tipo": "particular"
        })
        self.assertEqual(res_post.status_code, 200)
        ev_id = res_post.json()["id"]

        # GET ID
        res_get = self.client.get(f"/api/eventos/{ev_id}")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()["titulo"], "Aula Particular com Maria")

        # PUT Parcial
        res_put = self.client.put(f"/api/eventos/{ev_id}", json={
            "observacoes": "Trazer blocos de yoga"
        })
        self.assertEqual(res_put.status_code, 200)
        ev_check = self.client.get(f"/api/eventos/{ev_id}").json()
        self.assertEqual(ev_check["observacoes"], "Trazer blocos de yoga")
        self.assertEqual(ev_check["titulo"], "Aula Particular com Maria")

        # DELETE
        res_del = self.client.delete(f"/api/eventos/{ev_id}")
        self.assertEqual(res_del.status_code, 200)
        res_404 = self.client.get(f"/api/eventos/{ev_id}")
        self.assertEqual(res_404.status_code, 404)

    def test_05_regra_fixa_5_nao_regressao(self):
        """
        REGRA 5: TESTE OBRIGATÓRIO DE NÃO-REGRESSÃO
        Altera um dado de aluno ou configuração; salva; verifica se todos os
        outros campos continuam intactos. Valida isolamento com nova agenda de eventos.
        """
        alunos = db.listar_alunos()
        self.assertGreater(len(alunos), 0, "Deve haver alunos cadastrados")
        aluno_id = alunos[0]["id"]
        snapshot_original = db.obter_aluno(aluno_id)

        try:
            # Alterar campo específico de observação
            obs_teste = (snapshot_original.get("observacoes") or "") + " [Regra 5 Teste]"
            res_up = self.client.put(f"/api/alunos/{aluno_id}", json={"observacoes": obs_teste})
            self.assertEqual(res_up.status_code, 200)

            # Verificar se TODOS os outros campos do aluno continuam 100% intactos
            aluno_pos = db.obter_aluno(aluno_id)
            self.assertEqual(aluno_pos["observacoes"], obs_teste)
            for campo, val_orig in snapshot_original.items():
                if campo in ("observacoes", "atualizado_em"):
                    continue
                self.assertEqual(
                    aluno_pos[campo],
                    val_orig,
                    f"Regressão no campo {campo}: original={val_orig}, pós-update={aluno_pos[campo]}"
                )
        finally:
            # Restaurar estado original incondicionalmente
            db.atualizar_aluno(aluno_id, {"observacoes": snapshot_original.get("observacoes") or ""})
            aluno_restaurado = db.obter_aluno(aluno_id)
            self.assertEqual(aluno_restaurado["observacoes"], (snapshot_original.get("observacoes") or ""))

        # Criar evento na nova agenda e garantir que NENHUM dado de aluno ou turma é afetado
        hoje_sp = db.obter_hoje_sp()
        ev_id = db.criar_evento(
            titulo="Evento Verificação Regra 5",
            data=hoje_sp.strftime("%Y-%m-%d"),
            horario_inicio="08:00",
            horario_fim="09:00"
        )
        self.assertIsInstance(ev_id, int)

        # Conferir lista de alunos
        alunos_apos_evento = db.listar_alunos()
        self.assertEqual(len(alunos_apos_evento), len(alunos))
        aluno_verif = db.obter_aluno(aluno_id)
        self.assertEqual(aluno_verif["nome"], snapshot_original["nome"])
        self.assertEqual(aluno_verif["plano"], snapshot_original["plano"])
        self.assertEqual(aluno_verif["status"], snapshot_original["status"])

        # Limpar evento
        db.excluir_evento(ev_id)


if __name__ == "__main__":
    unittest.main()

import unittest
import os
import sys
import json
import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import backend.database as db
import backend.backup_service as backup_service
from backend.app import app

class TestBackupAutomatico(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.usuario_teste = "Tester Backup Automatico"

    def tearDown(self):
        # Limpar registros temporários criados nos testes
        conn = db.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM logs_diagnostico WHERE tipo_evento = 'backup_automatico_teste'")
            cur.execute("DELETE FROM alunos WHERE nome LIKE 'Aluno Teste Backup%'")
            conn.commit()
        except Exception as e:
            print(f"Aviso no tearDown: {e}")
        finally:
            conn.close()

    def test_01_geracao_e_validacao_dump_sql(self):
        """Testa a geração do dump SQL e valida se o arquivo realmente abre e contém dados válidos."""
        caminho_sql, meta = backup_service.gerar_dump_sql()

        self.assertTrue(os.path.exists(caminho_sql), "O arquivo .sql deve existir no disco.")
        self.assertGreater(meta["tamanho_bytes"], 0, "O tamanho do backup deve ser maior que 0.")
        self.assertGreater(meta["total_tabelas"], 0, "Deve haver tabelas exportadas.")
        self.assertGreater(meta["total_registros"], 0, "Deve haver registros exportados.")

        # Validação estrutural do arquivo
        val = backup_service.validar_arquivo_dump(caminho_sql)
        self.assertTrue(val["valido"], f"Validação falhou: {val.get('erro')}")
        self.assertTrue(val["tem_begin"])
        self.assertTrue(val["tem_commit"])
        self.assertGreater(val["total_inserts"], 0)

        # Inspeção manual de conteúdo linha a linha
        with open(caminho_sql, "r", encoding="utf-8") as f:
            conteudo = f.read()

        self.assertIn("SHANTI STUDIO DE YOGA - BACKUP AUTOMATICO", conteudo)
        self.assertIn("BEGIN;", conteudo)
        self.assertIn("COMMIT;", conteudo)
        self.assertIn('INSERT INTO "configuracoes"', conteudo)

    def test_02_retencao_30_dias(self):
        """Testa política de retenção de 30 dias: arquivos antigos são expurgados e recentes mantidos."""
        dir_temp = os.path.join(backup_service.DIR_BACKUPS_LOCAL, "teste_retencao")
        os.makedirs(dir_temp, exist_ok=True)

        agora = backup_service.obter_agora_sp()
        data_recente = (agora - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
        data_antiga = (agora - datetime.timedelta(days=45)).strftime("%Y-%m-%d")

        arq_recente = os.path.join(backup_service.DIR_BACKUPS_LOCAL, f"backup-shanti-{data_recente}_03-00-00.sql")
        arq_antigo = os.path.join(backup_service.DIR_BACKUPS_LOCAL, f"backup-shanti-{data_antiga}_03-00-00.sql")

        with open(arq_recente, "w", encoding="utf-8") as f:
            f.write("-- backup recente")
        with open(arq_antigo, "w", encoding="utf-8") as f:
            f.write("-- backup antigo")

        # Ajustar timestamp de modificação no sistema de arquivos para o arquivo antigo
        ts_antigo = (agora - datetime.timedelta(days=45)).timestamp()
        os.utime(arq_antigo, (ts_antigo, ts_antigo))

        removidos = backup_service.gdrive_manager.expurgar_backups_antigos(dias_retencao=30)

        self.assertFalse(os.path.exists(arq_antigo), "Arquivo de 45 dias atrás DEVE ter sido removido.")
        self.assertTrue(os.path.exists(arq_recente), "Arquivo de 5 dias atrás DEVE ser preservado.")

        # Limpeza do arquivo de teste recente
        if os.path.exists(arq_recente):
            os.remove(arq_recente)

    def test_03_cliente_drive_mock_upload_e_listagem(self):
        """Testa o cliente Google Drive com mock HTTP da API v3 (multipart upload e listagem)."""
        manager = backup_service.GoogleDriveBackupManager()
        manager.folder_id = "mock_pasta_12345"
        manager.service_account_json_raw = '{"client_email": "mock@project.iam.gserviceaccount.com"}'
        manager._token = "mock_token_abc"
        manager._token_expiry = 9999999999

        # Mock upload
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"id": "drive_file_999", "name": "backup-shanti-teste.sql"}
            mock_post.return_value = mock_resp

            caminho_teste, _ = backup_service.gerar_dump_sql()
            res_upload = manager.fazer_upload(caminho_teste, "backup-shanti-teste.sql")

            self.assertTrue(res_upload["sucesso"])
            self.assertEqual(res_upload["file_id"], "drive_file_999")
            mock_post.assert_called_once()

        # Mock listagem
        with patch("requests.get") as mock_get:
            mock_resp_get = MagicMock()
            mock_resp_get.status_code = 200
            mock_resp_get.json.return_value = {
                "files": [
                    {"id": "f1", "name": "backup-shanti-2026-09-16.sql", "createdTime": "2026-09-16T03:00:00.000Z"},
                    {"id": "f2", "name": "backup-shanti-2026-07-01.sql", "createdTime": "2026-07-01T03:00:00.000Z"}
                ]
            }
            mock_get.return_value = mock_resp_get

            arquivos = manager.listar_backups()
            self.assertEqual(len(arquivos), 2)
            self.assertEqual(arquivos[0]["name"], "backup-shanti-2026-09-16.sql")

    def test_04_tratamento_falha_e_alerta(self):
        """Testa que falhas na rotina de backup geram logs de erro visíveis no painel de diagnóstico."""
        with patch("backend.backup_service.gerar_dump_sql", side_effect=RuntimeError("Simulação de falha de conexão")):
            res = backup_service.executar_rotina_backup(origem="teste_unitario_falha")

            self.assertFalse(res["sucesso"])
            self.assertIn("Simulação de falha de conexão", res["erro"])
            self.assertIsNotNone(res.get("alerta_whatsapp_texto"))

            # Verificar que a falha foi persistida em logs_diagnostico
            logs = db.obter_ultimos_logs_diagnostico(limite=5)
            log_erro = [l for l in logs if l["tipo_evento"] == "backup_automatico" and l["sucesso"] == 0]
            self.assertTrue(len(log_erro) > 0, "A falha DEVE ser registrada em logs_diagnostico com sucesso=0")
            self.assertIn("Simulação de falha", log_erro[0]["mensagem_erro"])

    def test_05_seguranca_credenciais_nao_expostas(self):
        """Garante que credenciais, chaves privadas e tokens NUNCA são expostos na API ou no front-end."""
        res = self.client.get("/api/backup/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        corpo_str = json.dumps(data)
        self.assertNotIn("BEGIN PRIVATE KEY", corpo_str)
        self.assertNotIn("private_key", corpo_str)
        self.assertNotIn("client_secret", corpo_str)

        # Se houver pasta ou email, devem estar mascarados
        drive_info = data.get("drive", {})
        if drive_info.get("email_servico"):
            self.assertIn("***", drive_info["email_servico"])
        if drive_info.get("pasta_id") and len(drive_info["pasta_id"]) > 8:
            self.assertIn("...", drive_info["pasta_id"])

    def test_06_regra_fixa_5_nao_regressao(self):
        """REGRA FIXA PERMANENTE 5 (OBRIGATÓRIA): A rotina de backup não pode alterar dados existentes."""
        nome_aluno = "Aluno Teste Backup Regra5"
        aid = db.cadastrar_aluno({
            "nome": nome_aluno,
            "telefone": "22997766554",
            "email": "aluno.backup.regra5@shantistudio.com.br",
            "plano": "2x na semana",
            "dia_vencimento": 20,
            "valor_mensalidade": 150.0,
            "tipo_pagamento": "PIX",
            "observacoes": "Observação de integridade antes do backup",
            "autoriza_imagem": 1
        })

        aluno_antes = db.obter_aluno(aid)
        self.assertIsNotNone(aluno_antes)

        # Executar rotina de backup e endpoints
        res_exec = self.client.post("/api/backup/executar")
        self.assertEqual(res_exec.status_code, 200)

        res_status = self.client.get("/api/backup/status")
        self.assertEqual(res_status.status_code, 200)

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
                f"VIOLAÇÃO DA REGRA 5: O campo '{campo}' foi corrompido ou alterado pelo backup!"
            )

if __name__ == '__main__':
    unittest.main()

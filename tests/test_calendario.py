import unittest
import sqlite3
import datetime
import backend.database as db

class TestCalendarioPresenca(unittest.TestCase):

    def test_parse_dias_semana(self):
        self.assertEqual(db.parse_dias_semana('Segunda e Quarta'), [0, 2])
        self.assertEqual(db.parse_dias_semana('Terça e Quinta'), [1, 3])
        self.assertEqual(db.parse_dias_semana('Terca e Quinta'), [1, 3])
        self.assertEqual(db.parse_dias_semana('Sexta'), [4])
        self.assertEqual(db.parse_dias_semana('Sábado e Domingo'), [5, 6])
        self.assertEqual(db.parse_dias_semana(''), [])
        self.assertEqual(db.parse_dias_semana(None), [])

    def test_obter_grade_calendario_mes(self):
        grade = db.obter_grade_calendario_mes(2026, 9)
        self.assertEqual(grade['ano'], 2026)
        self.assertEqual(grade['mes'], 9)
        self.assertGreater(len(grade['dias_com_aula']), 0)
        dias_com_aula_dict = {d['dia']: d for d in grade['dias_com_aula']}
        self.assertIn(1, dias_com_aula_dict)
        self.assertIn(2, dias_com_aula_dict)
        self.assertNotIn(6, dias_com_aula_dict)

    def test_obter_chamada_dia_e_status_pendente(self):
        chamada = db.obter_chamada_dia('2026-09-02')
        self.assertEqual(chamada['data'], '2026-09-02')
        self.assertEqual(chamada['dia_semana_nome'], 'Quarta-feira')
        self.assertGreater(len(chamada['turmas']), 0)
        for t in chamada['turmas']:
            for al in t['alunos']:
                self.assertIn(al['status'], ['pendente', 'presente', 'faltou'])

    def test_salvar_status_presenca_e_compatibilidade(self):
        aluno_id = 1
        turma_id = 2
        data_teste = '2026-09-02'
        res = db.salvar_status_presenca(aluno_id, turma_id, data_teste, 'presente', 'Veio pontual')
        self.assertTrue(res['sucesso'])
        self.assertEqual(res['status'], 'presente')

        chamada = db.obter_chamada_dia(data_teste)
        aluno_encontrado = None
        for t in chamada['turmas']:
            for al in t['alunos']:
                if al['aluno_id'] == aluno_id:
                    aluno_encontrado = al
                    break
        self.assertIsNotNone(aluno_encontrado)
        self.assertEqual(aluno_encontrado['status'], 'presente')

        res_falta = db.salvar_status_presenca(aluno_id, turma_id, data_teste, 'faltou', 'Avisou imprevisto')
        self.assertTrue(res_falta['sucesso'])
        self.assertEqual(res_falta['status'], 'faltou')

    def test_regra_retencao_pendente_nunca_e_falta(self):
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM historico_presenca WHERE aluno_id = 5')
        cursor.execute('DELETE FROM frequencias WHERE aluno_id = 5')
        cursor.execute('UPDATE alunos SET pausar_alerta_ausencia = 0 WHERE id = 5')
        conn.commit()
        conn.close()

        retencao_sem_faltas = db.obter_alunos_retencao_ausentes(dias_janela=14)
        alunos_retencao_ids = [r['aluno_id'] for r in retencao_sem_faltas if not r['pausado']]
        self.assertNotIn(5, alunos_retencao_ids)

        hoje = datetime.date.today()
        datas_aulas = []
        for d_delta in range(1, 14):
            dt = hoje - datetime.timedelta(days=d_delta)
            if dt.weekday() in [0, 2]:
                datas_aulas.append(dt.strftime('%Y-%m-%d'))
            if len(datas_aulas) == 2:
                break

        if len(datas_aulas) >= 2:
            db.salvar_status_presenca(5, 2, datas_aulas[0], 'faltou')
            db.salvar_status_presenca(5, 2, datas_aulas[1], 'faltou')

            retencao_com_faltas = db.obter_alunos_retencao_ausentes(dias_janela=14)
            alunos_retencao_ids = [r['aluno_id'] for r in retencao_com_faltas if not r['pausado']]
            self.assertIn(5, alunos_retencao_ids)

            db.alternar_pausa_alerta(5, pausar=True, motivo='Viagem de férias')
            retencao_pausado = db.obter_alunos_retencao_ausentes(dias_janela=14)
            aluno_5_item = next((r for r in retencao_pausado if r['aluno_id'] == 5), None)
            self.assertIsNotNone(aluno_5_item)
            self.assertTrue(aluno_5_item['pausado'])
            self.assertEqual(aluno_5_item['motivo_pausa'], 'Viagem de férias')

            db.alternar_pausa_alerta(5, pausar=False)

if __name__ == '__main__':
    unittest.main()

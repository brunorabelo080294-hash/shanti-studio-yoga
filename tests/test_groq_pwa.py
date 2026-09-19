import json
import unittest
from fastapi.testclient import TestClient
from backend.app import app
import backend.database as db
import backend.ai_service as ai

class TestGroqAndPWA(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_manifest_webapk_compliance(self):
        with open('frontend/manifest.json', encoding='utf-8') as f:
            manifest = json.load(f)
        
        self.assertEqual(manifest.get('id'), '/gestao/')
        self.assertIn('/gestao/', manifest.get('start_url'))
        self.assertEqual(manifest.get('scope'), '/gestao/')
        self.assertEqual(manifest.get('display'), 'standalone')
        self.assertFalse(manifest.get('prefer_related_applications'))
        
        purposes = [icon.get('purpose') for icon in manifest.get('icons', [])]
        sizes = [icon.get('sizes') for icon in manifest.get('icons', [])]
        
        self.assertIn('any', purposes)
        self.assertIn('maskable', purposes)
        self.assertIn('192x192', sizes)
        self.assertIn('512x512', sizes)

    def test_atalhos_rapidos_sem_llm(self):
        res = self.client.post('/api/chat', json={'mensagem': 'quem está com a mensalidade atrasada?'})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('tipo', data)
        self.assertEqual(data['tipo'], 'inadimplencia')

    def test_configuracoes_groq(self):
        res_get = self.client.get('/api/configuracoes')
        self.assertEqual(res_get.status_code, 200)
        
        res_post = self.client.post('/api/configuracoes', json={
            'configs': {
                'groq_model': 'qwen/qwen3.8-27b',
                'ai_provider': 'groq'
            }
        })
        self.assertEqual(res_post.status_code, 200)
        
        configs = db.obter_configuracoes()
        self.assertEqual(configs.get('groq_model'), 'qwen/qwen3.8-27b')
        self.assertEqual(configs.get('ai_provider'), 'groq')

    def test_status_ia_endpoint(self):
        res = self.client.get('/api/status-ia')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('status_ia', data)
        self.assertIn('latencia_ms', data)
        
        groq_key = ai.get_groq_api_key()
        if groq_key:
            res_str = json.dumps(data)
            self.assertNotIn(groq_key, res_str)

if __name__ == '__main__':
    unittest.main()

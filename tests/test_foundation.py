import json
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.main import app
from backend.contracts import MatchEvent, MatchFixture
from backend.foundry import configuration

ROOT = Path(__file__).resolve().parent.parent


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_fixture_contract_and_identity(self):
        fixture = MatchFixture.model_validate(json.loads((ROOT / 'data/live_fixture.json').read_text()))
        self.assertGreater(len(fixture.events), 900)
        self.assertEqual(len({e.event_id for e in fixture.events}), len(fixture.events))
        self.assertEqual([e.sequence for e in fixture.events], sorted(e.sequence for e in fixture.events))
        players = {p.player_id for p in fixture.players}
        teams = {t.team_id for t in fixture.teams}
        for event in fixture.events:
            self.assertEqual(event.match_id, fixture.match_id)
            self.assertIn(event.team_id, teams)
            if event.player_id is not None:
                self.assertIn(event.player_id, players)
        self.assertEqual(self.client.get('/api/fixture').status_code, 200)

    def test_invalid_pitch_coordinate_is_rejected(self):
        event = self.client.get('/api/fixture').json()['events'][0]
        event['x'] = 101
        with self.assertRaises(ValidationError):
            MatchEvent.model_validate(event)

    @patch.dict('os.environ', {}, clear=True)
    def test_missing_foundry_is_honest_and_does_not_block_fixture(self):
        self.assertFalse(self.client.get('/api/health').json()['foundry_configured'])
        self.assertEqual(self.client.post('/api/foundry/probe').status_code, 503)
        self.assertEqual(self.client.get('/api/fixture').status_code, 200)

    def test_foundry_rejects_non_azure_and_project_endpoints(self):
        for base in ['http://test.openai.azure.com/openai/v1/', 'https://example.com/openai/v1/',
                     'https://test.services.ai.azure.com/api/projects/demo']:
            with patch.dict('os.environ', {'FOUNDRY_BASE_URL': base, 'FOUNDRY_MODEL': 'deployment', 'FOUNDRY_API_KEY': 'secret'}):
                self.assertIsNone(configuration())

    def test_api_health_never_exposes_key(self):
        with patch.dict('os.environ', {'FOUNDRY_BASE_URL': 'https://demo.openai.azure.com/openai/v1/', 'FOUNDRY_MODEL': 'deployment', 'FOUNDRY_API_KEY': 'private-test-key'}):
            response = self.client.get('/api/health')
            self.assertTrue(response.json()['foundry_configured'])
            self.assertNotIn('private-test-key', response.text)


if __name__ == '__main__':
    unittest.main()

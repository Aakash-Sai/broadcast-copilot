import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from backend.main import fixture, history, historical_index, app
from backend.moments import detect_moments
from backend.editorial import EditorialService
from backend.contracts import DraftRequest, EditorialAction


class MomentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.live,self.past,self.store=fixture(),history(),historical_index()

    def test_detects_unselected_team_and_ranks_substitute_goal(self):
        pressure=detect_moments(self.live,self.past,900000,self.store)
        self.assertEqual(pressure[0].entity_id,'riverside')
        goal=detect_moments(self.live,self.past,4440000,self.store)
        self.assertEqual(goal[0].entity_id,'r-12')
        self.assertEqual(goal[0].score,100)
        self.assertEqual(detect_moments(self.live,self.past,0,self.store),[])
        self.assertEqual(detect_moments(self.live,self.past,5400000,self.store),[])

    def test_stale_events_and_players_off_pitch_are_not_suggested(self):
        truncated=self.live.model_copy(update={'events':[e for e in self.live.events if e.match_clock_ms<=2640000]})
        self.assertEqual(detect_moments(truncated,self.past,3000000,self.store),[])
        for clock in [3480000,4440000,5000000]:
            inactive={p.player_id for p in self.live.participation if p.end_match_clock_ms<=clock}
            rows=detect_moments(self.live,self.past,clock,self.store)
            self.assertFalse(any(m.mode=='player' and m.entity_id in inactive for m in rows))

    async def test_dismissal_suppresses_repeat_but_new_goal_breaks_cooldown(self):
        service=EditorialService(self.store)
        request=DraftRequest(session_id='moment-test-001',mode='player',entity_id='r-12',match_clock_ms=4439999)
        with patch('backend.editorial.generate_graphic',AsyncMock()) as provider:
            draft=(await service.generate(self.live,self.past,request)).draft
            service.act(self.live,self.past,EditorialAction(session_id=request.session_id,match_clock_ms=4439999,
                action='dismiss',draft_id=draft.draft_id))
            repeated=detect_moments(self.live,self.past,4439999,self.store,[draft])
            self.assertNotIn('r-12',[m.entity_id for m in repeated])
            goal=detect_moments(self.live,self.past,4440000,self.store,[draft])
            self.assertEqual(goal[0].entity_id,'r-12')
            provider.assert_not_awaited()
        self.assertIsNone(service.state(self.live,self.past,request.session_id,4440000).published)

    def test_api_is_bounded_and_has_no_generation_side_effect(self):
        with patch('backend.editorial.generate_graphic',AsyncMock()) as provider:
            client=TestClient(app)
            result=client.get('/api/moments?match_clock_ms=2640000&session_id=moment-api-test')
            self.assertEqual(result.status_code,200)
            self.assertLessEqual(len(result.json()),3)
            self.assertIn('n-8',[m['entity_id'] for m in result.json()])
            self.assertIsNone(client.get('/api/editorial/state?match_clock_ms=2640000&session_id=moment-api-test').json()['published'])
            provider.assert_not_awaited()

    def test_full_match_scan_is_deterministic_and_bounded(self):
        for minute in range(0,91):
            rows=detect_moments(self.live,self.past,minute*60000,self.store)
            self.assertLessEqual(len(rows),3)
            self.assertEqual(len({m.moment_id for m in rows}),len(rows))
            self.assertEqual([m.score for m in rows],sorted((m.score for m in rows),reverse=True))

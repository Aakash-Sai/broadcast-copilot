import unittest
from datetime import timedelta
from fastapi.testclient import TestClient
from backend.main import app, fixture, history
from backend.statistics import analyze, eligible_history, historical_summary, unique_events
from scripts.generate_history import generate


class StatisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = fixture()
        cls.past = history()

    def test_generation_is_repeatable_and_each_team_has_twenty_matches(self):
        self.assertEqual(generate(self.live), self.past)
        self.assertEqual(generate(self.live), generate(self.live))
        for team in self.live.teams:
            self.assertEqual(sum(team.team_id in {t.team_id for t in m.teams} for m in self.past), 20)
        self.assertEqual(len(self.live.players), 30)
        for match in self.past:
            self.assertEqual(len({e.event_id for e in match.events}), len(match.events))
            self.assertEqual(sum(p.end_match_clock_ms-p.start_match_clock_ms for p in match.participation), 22*5400000)


    def golden_fixture(self):
        from backend.contracts import MatchEvent
        live=self.live.model_copy(deep=True)
        live.events=[MatchEvent(event_id=f'e-{i+1:03d}',match_id=live.match_id,sequence=i+1,match_clock_ms=600000+i*5000,type='pass',team_id='northbridge',player_id='n-8',outcome='incomplete' if i==4 else 'completed',forward=i in [0,1,3,4]) for i in range(6)]
        past=[]
        for i,total in enumerate([1,2,3,1,3]):
            match=self.past[i].model_copy(deep=True)
            match.events=[MatchEvent(event_id=f'{match.match_id}-{j}',match_id=match.match_id,sequence=j,match_clock_ms=(j+1)*60000,type='pass',team_id='northbridge',player_id='n-8',outcome='completed',forward=True) for j in range(total)]
            past.append(match)
        return live,past

    def test_known_live_totals_and_baseline(self):
        live,past=self.golden_fixture()
        result = analyze(live, past, 6, 'n-8')
        row = next(p for p in result.players if p.entity_id == 'n-8')
        self.assertEqual((row.completed_passes, row.attempted_passes, row.completed_forward_passes), (5, 6, 3))
        self.assertEqual(row.pass_completion_pct, 83.33)
        self.assertEqual(result.comparison.historical_values, [1, 2, 3, 1, 3])
        self.assertEqual(result.comparison.baseline_value, 2)
        self.assertEqual(result.comparison.sample_size, 5)
        self.assertTrue(result.comparison.matched_baseline)
        self.assertEqual(result.comparison.current_source_event_ids, ['e-001', 'e-002', 'e-004'])
        self.assertEqual(len(result.comparison.source_event_ids), 10)

    def test_threshold_only_after_third_completed_forward_pass(self):
        live,past=self.golden_fixture()
        self.assertFalse(analyze(live, past, 3, 'n-8').comparison.matched_baseline)
        self.assertTrue(analyze(live, past, 4, 'n-8').comparison.matched_baseline)
        self.assertEqual(analyze(live, past, 5, 'n-8').comparison.current_value, 3)

    def test_unseen_events_do_not_affect_stats(self):
        changed = self.live.model_copy(deep=True)
        changed.events[-1] = changed.events[-1].model_copy(update={'player_id': 'n-8', 'type': 'pass', 'outcome': 'completed', 'forward': True})
        self.assertEqual(analyze(changed, self.past, 3, 'n-8'), analyze(self.live, self.past, 3, 'n-8'))

    def test_event_duplicates_are_idempotent_and_conflicts_rejected(self):
        live = self.live.model_copy(deep=True)
        live.events.append(live.events[0])
        self.assertEqual(analyze(live, self.past, len(live.events), 'n-8'), analyze(self.live, self.past, len(self.live.events), 'n-8'))
        live.events[-1] = live.events[0].model_copy(update={'outcome': 'incomplete'})
        with self.assertRaisesRegex(ValueError, 'Conflicting duplicate'):
            analyze(live, self.past, len(live.events), 'n-8')

    def test_future_current_and_unfinished_matches_excluded(self):
        base = self.past[0]
        future = base.model_copy(update={'match_id': 'future', 'kickoff_at': self.live.kickoff_at + timedelta(days=1), 'completed_at': self.live.kickoff_at + timedelta(days=1, hours=2)})
        unfinished = base.model_copy(update={'match_id': 'unfinished', 'completed_at': self.live.kickoff_at + timedelta(minutes=1)})
        current = base.model_copy(update={'match_id': self.live.match_id})
        self.assertEqual(eligible_history(self.past + [future, unfinished, current], self.live), self.past)
        self.assertEqual(analyze(self.live, self.past + [future, unfinished, current], 6, 'n-8'), analyze(self.live, self.past, 6, 'n-8'))

    def test_duplicate_matches_do_not_inflate_sample(self):
        self.assertEqual(analyze(self.live, self.past + [self.past[0]], 6, 'n-8').comparison.sample_size, 20)

    def test_partial_appearances_excluded_and_small_sample_falls_back(self):
        partial = self.past[0].model_copy(deep=True)
        next(p for p in partial.participation if p.player_id == 'n-8').end_match_clock_ms = 1000
        result = analyze(self.live, [partial, self.past[1], self.past[2]], 6, 'n-8')
        self.assertEqual(result.comparison.sample_size, 2)
        self.assertIsNone(result.comparison.baseline_value)
        self.assertFalse(result.comparison.matched_baseline)
        self.assertNotIn('average', result.comparison_text)
        self.assertIsNone(analyze(self.live, [], 6, 'n-8').comparison.baseline_value)

    def test_aggregates_reconcile_to_events(self):
        for match in self.past:
            summary = historical_summary(match)
            for team in summary.teams:
                rows = [row for row in summary.players if row.entity_id in {p.player_id for p in match.players if p.team_id == team.entity_id}]
                for metric in ['completed_passes', 'attempted_passes', 'completed_forward_passes', 'shots', 'pressure_events']:
                    self.assertEqual(getattr(team, metric), sum(getattr(row, metric) for row in rows))
            actual = sum(e.type == 'pass' and e.outcome == 'completed' for e in match.events)
            self.assertEqual(sum(t.completed_passes for t in summary.teams), actual)

    def test_source_events_exist_and_match_metric(self):
        result = analyze(self.live, self.past, 6, 'n-8')
        by_id = {e.event_id: e for m in self.past for e in m.events}
        for key in result.comparison.source_event_ids:
            event = by_id[key]
            self.assertEqual((event.player_id, event.type, event.outcome, event.forward), ('n-8', 'pass', 'completed', True))

    def test_api_validation_and_empty_playback(self):
        client = TestClient(app)
        result = client.get('/api/analysis?event_count=0').json()
        self.assertEqual(result['event_count'], 0)
        self.assertEqual(result['comparison']['current_value'], 0)
        self.assertFalse(result['comparison']['matched_baseline'])
        self.assertEqual(client.get('/api/analysis?event_count=100000').status_code, 422)
        self.assertEqual(client.get('/api/analysis?player_id=missing').status_code, 422)
        self.assertEqual(client.get('/api/analysis?event_count=-1').status_code, 422)
        self.assertEqual(len(client.get('/api/history').json()), 20)


if __name__ == '__main__':
    unittest.main()

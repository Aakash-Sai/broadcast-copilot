import unittest
from datetime import timedelta
from fastapi.testclient import TestClient
from backend.main import app, fixture, history
from backend.statistics import analyze, pressure_comparison


class PressureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live, cls.past = fixture(), history()

    def test_surge_uses_equivalent_windows_and_expires(self):
        peak = analyze(self.live, self.past, 0, 'n-8',match_clock_ms=900000).team_comparison
        self.assertEqual(peak.current_value, 20)
        self.assertEqual(peak.historical_values[-5:], [2, 0, 1, 3, 8])
        self.assertEqual(peak.baseline_value, 3.2)
        self.assertTrue(peak.matched_baseline)
        self.assertEqual(len(peak.current_source_event_ids), 20)
        self.assertEqual(len(peak.source_event_ids), 64)
        quiet = analyze(self.live, self.past, 0, 'n-8',match_clock_ms=1620000).team_comparison
        self.assertLess(quiet.current_value, 10)
        self.assertFalse(quiet.matched_baseline)

    def test_opponent_events_do_not_count_as_own_pressure(self):
        events=[e for e in self.live.events if e.team_id=='riverside' and e.match_clock_ms<=900000]
        result,_=pressure_comparison(self.live,self.past,events,900000,'northbridge')
        self.assertEqual(result.current_value,0)
        self.assertFalse(result.matched_baseline)

    def test_duplicates_do_not_inflate_pressure(self):
        copy = self.live.model_copy(deep=True)
        copy.events = copy.events[:18] + [copy.events[7]]
        self.assertEqual(analyze(copy, self.past, 19, 'n-8').team_comparison,
                         analyze(self.live, self.past, 18, 'n-8').team_comparison)

    def test_half_open_window_boundaries(self):
        prototype = next(e for e in self.live.events if e.type=='pressure' and e.team_id=='riverside')
        events = [prototype.model_copy(update={'event_id': str(i), 'match_clock_ms': time})
                  for i, time in enumerate([299999, 300000, 300001, 600000, 600001])]
        result, _ = pressure_comparison(self.live, self.past, events, 600000, 'riverside')
        self.assertEqual(result.current_value, 2)
        self.assertEqual(result.current_source_event_ids, ['2', '3'])

    def test_no_partial_window_or_small_sample_claim(self):
        for clock, past in [(240000, self.past), (600000, self.past[:2])]:
            result, text = pressure_comparison(self.live, past, [], clock, 'riverside')
            self.assertIsNone(result.baseline_value)
            self.assertFalse(result.matched_baseline)
            self.assertIn('insufficient context', text)

    def test_future_history_cannot_change_pressure_baseline(self):
        future = self.past[0].model_copy(update={'match_id': 'future', 'kickoff_at': self.live.kickoff_at + timedelta(days=1),
                                              'completed_at': self.live.kickoff_at + timedelta(days=1, hours=2)})
        self.assertEqual(analyze(self.live, self.past + [future], 18, 'n-8').team_comparison,
                         analyze(self.live, self.past, 18, 'n-8').team_comparison)

    def test_api_rejects_unknown_team(self):
        self.assertEqual(TestClient(app).get('/api/analysis?team_id=unknown').status_code, 422)


if __name__ == '__main__':
    unittest.main()

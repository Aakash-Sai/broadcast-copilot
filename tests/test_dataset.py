import unittest
from backend.main import fixture, history
from backend.statistics import analyze, historical_summary


class DatasetTests(unittest.TestCase):
    def test_squads_intervals_and_player_event_membership(self):
        for match in [fixture(), *history()]:
            players={p.player_id:p for p in match.players}
            parts={p.player_id:p for p in match.participation}
            self.assertEqual(match.duration_ms, 5400000)
            self.assertEqual(len(match.players),30)
            self.assertEqual(len(match.substitutions),6)
            for team in match.teams:
                roster=[p for p in match.players if p.team_id==team.team_id]
                self.assertEqual(len(roster),15)
                for clock in [0,57*60000,58*60000,70*60000,89*60000]:
                    active=[p for p in roster if p.player_id in parts and parts[p.player_id].start_match_clock_ms<=clock<parts[p.player_id].end_match_clock_ms]
                    self.assertEqual(len(active),11)
                minutes=sum((p.end_match_clock_ms-p.start_match_clock_ms)/60000 for p in match.participation if players[p.player_id].team_id==team.team_id)
                self.assertEqual(minutes,990)
            for event in match.events:
                self.assertLess(event.match_clock_ms,match.duration_ms)
                if event.player_id:
                    self.assertEqual(players[event.player_id].team_id,event.team_id)
                    interval=parts[event.player_id]
                    self.assertLessEqual(interval.start_match_clock_ms,event.match_clock_ms)
                    self.assertLess(event.match_clock_ms,interval.end_match_clock_ms)
            self.assertEqual([e.match_clock_ms for e in match.events], sorted(e.match_clock_ms for e in match.events))
            self.assertEqual(len({e.event_id for e in match.events}),len(match.events))

    def test_bench_minutes_and_no_future_events(self):
        live,past=fixture(),history()
        for clock,expected in [(57*60000,0),(59*60000,1),(5400000,32)]:
            result=analyze(live,past,0,'n-12',match_clock_ms=clock)
            row=next(p for p in result.players if p.entity_id=='n-12')
            self.assertEqual(row.minutes_played,expected)
            if expected==0:
                self.assertEqual(row.attempted_passes,0)
                self.assertEqual(row.goals,0)
        full=analyze(live,past,0,'n-15',match_clock_ms=5400000)
        self.assertEqual(next(p for p in full.players if p.entity_id=='n-15').minutes_played,0)
        self.assertIsNone(full.comparison.baseline_value)

    def test_continuous_clock_quiet_period_and_full_time(self):
        live,past=fixture(),history()
        before=analyze(live,past,0,'n-8',match_clock_ms=26*60000)
        after=analyze(live,past,0,'n-8',match_clock_ms=27*60000)
        self.assertEqual(before.event_count,after.event_count)
        self.assertEqual(after.match_clock_ms,27*60000)
        self.assertEqual(analyze(live,past,0,'n-8',match_clock_ms=5400000).match_clock_ms,5400000)
        with self.assertRaises(ValueError):
            analyze(live,past,0,'n-8',match_clock_ms=5400001)

    def test_formations_substitutions_and_score_are_as_of_clock(self):
        live,past=fixture(),history()
        early=analyze(live,past,0,'n-8',match_clock_ms=57*60000)
        later=analyze(live,past,0,'n-8',match_clock_ms=58*60000)
        self.assertEqual(early.active_formations[0].shape,'4-3-3')
        self.assertEqual(later.active_formations[0].shape,'4-2-3-1')
        self.assertEqual(len(early.completed_substitutions),0)
        self.assertEqual(len(later.completed_substitutions),1)
        before=analyze(live,past,0,'r-12',match_clock_ms=74*60000-1)
        after=analyze(live,past,0,'r-12',match_clock_ms=74*60000)
        self.assertEqual([t.goals for t in before.teams],[1,0])
        self.assertEqual([t.goals for t in after.teams],[1,1])
        self.assertEqual(next(p for p in after.players if p.entity_id=='r-12').goals,1)

    def test_event_mix_and_historical_unused_bench(self):
        self.assertEqual({e.type for e in fixture().events},{'pass','shot','pressure','tackle','possession_change','substitution','formation_change'})
        for match in history():
            stats=historical_summary(match)
            self.assertEqual(next(p for p in stats.players if p.entity_id=='n-15').minutes_played,0)

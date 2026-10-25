import sqlite3
import unittest
from datetime import timedelta
from backend.history_store import HistoryStore
from backend.main import fixture, history, historical_index
from backend.statistics import analyze, unique_events


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live,cls.past,cls.store=fixture(),history(),historical_index()

    def test_player_equal_time_counts_and_provenance(self):
        clock=2640000
        references=self.store.retrieve(self.live,'n-8',clock,'player')
        self.assertEqual(len(references),20)
        for match,reference in zip(self.past,references):
            expected=[e for e in unique_events(match.events,match.match_id) if e.player_id=='n-8'
                and e.type=='pass' and e.outcome=='completed' and e.forward and e.match_clock_ms<=clock]
            self.assertEqual(reference.match_id,match.match_id)
            self.assertEqual(reference.value,len(expected))
            self.assertEqual(set(reference.event_ids),{e.event_id for e in expected})
        self.assertEqual(analyze(self.live,self.past,0,'n-8',match_clock_ms=clock,store=self.store).comparison.baseline_value,5.25)

    def test_substitute_equal_exposure_and_small_sample(self):
        elapsed=14*60000
        references=self.store.retrieve(self.live,'r-12',elapsed,'substitute')
        for match,reference in zip(self.past,references):
            part=next(p for p in match.participation if p.player_id=='r-12')
            events=[e for e in match.events if e.player_id=='r-12' and part.start_match_clock_ms<=e.match_clock_ms<=part.start_match_clock_ms+elapsed]
            self.assertEqual(reference.value,sum(e.type=='pass' and e.outcome=='completed' for e in events))
            self.assertEqual(reference.goals,sum(e.type=='shot' and e.outcome=='goal' for e in events))
        limited=HistoryStore(self.past[:2])
        result=analyze(self.live,self.past[:2],0,'r-12',match_clock_ms=4440000,store=limited).comparison.contribution
        self.assertEqual(result.history_sample_size,2)
        self.assertIsNone(result.historical_completed_passes)

    def test_late_starts_and_short_participation_excluded(self):
        match=self.past[0].model_copy(deep=True)
        next(p for p in match.participation if p.player_id=='n-8').end_match_clock_ms=600000
        store=HistoryStore([match])
        self.assertEqual(len(store.retrieve(self.live,'n-8',600000,'player')),1)
        self.assertEqual(store.retrieve(self.live,'n-8',600001,'player'),[])
        self.assertEqual(store.retrieve(self.live,'r-12',600000,'player'),[])

    def test_future_completion_filters_parameterization_and_read_only(self):
        match=self.past[0].model_copy(deep=True)
        match.completed_at=self.live.kickoff_at+timedelta(seconds=1)
        store=HistoryStore([match])
        self.assertEqual(store.retrieve(self.live,'n-8',600000,'player'),[])
        self.assertEqual(self.store.retrieve(self.live,"n-8' OR 1=1 --",600000,'player'),[])
        with self.assertRaises(sqlite3.OperationalError):
            store.db.execute('DELETE FROM events')

    def test_pressure_half_open_window(self):
        references=self.store.retrieve(self.live,'riverside',900000,'pressure')
        self.assertEqual(sum(r.value for r in references),64)
        for match,reference in zip(self.past,references):
            self.assertEqual(reference.value,sum(e.type=='pressure' and e.team_id=='riverside'
                and 600000<e.match_clock_ms<=900000 for e in match.events))

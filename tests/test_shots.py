import unittest
from unittest.mock import AsyncMock, patch
from backend.main import fixture,history,historical_index
from backend.statistics import analyze,shot_comparison
from backend.contracts import DraftRequest,EditorialAction
from backend.editorial import EditorialService
from backend.moments import detect_moments


class ShotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.live,self.past,self.store=fixture(),history(),historical_index()

    def test_surge_counts_all_attempts_and_same_historical_window(self):
        c=analyze(self.live,self.past,0,'n-8','northbridge',2100000,store=self.store).shot_comparison
        self.assertEqual((c.current_value,c.baseline_value,c.sample_size),(5,1,20))
        self.assertTrue(c.matched_baseline)
        self.assertEqual(len(c.current_source_event_ids),5)
        for match,value in zip(self.past,c.historical_values):
            self.assertEqual(value,sum(e.team_id=='northbridge' and e.type=='shot' and 1500000<e.match_clock_ms<=2100000 for e in match.events))
        goal=next(e for e in self.live.events if e.outcome=='goal')
        c,_=shot_comparison(self.live,self.past,[goal],goal.match_clock_ms,goal.team_id,self.store)
        self.assertEqual(c.current_value,1)

    def test_boundaries_partial_windows_small_samples_and_future_events(self):
        proto=next(e for e in self.live.events if e.type=='shot' and e.team_id=='northbridge')
        events=[proto.model_copy(update={'event_id':f'boundary-{i}','match_clock_ms':clock})
                for i,clock in enumerate([599999,600000,600001,1200000,1200001])]
        c,_=shot_comparison(self.live,self.past,events,1200000,'northbridge',self.store)
        self.assertEqual(c.current_source_event_ids,['boundary-2','boundary-3'])
        for clock,past in [(599999,self.past),(2100000,self.past[:2])]:
            c,_=shot_comparison(self.live,past,[],clock,'northbridge')
            self.assertIsNone(c.baseline_value)
            self.assertFalse(c.matched_baseline)
        trimmed=self.live.model_copy(update={'events':[e for e in self.live.events if e.match_clock_ms<=2100000]})
        self.assertEqual(analyze(trimmed,self.past,0,'n-8','northbridge',2100000,store=self.store).shot_comparison,
                         analyze(self.live,self.past,0,'n-8','northbridge',2100000,store=self.store).shot_comparison)

    async def test_draft_selection_wording_approval_and_expiry(self):
        service=EditorialService(self.store)
        request=DraftRequest(session_id='shot-test-001',mode='team',entity_id='northbridge',team_metric='shots',match_clock_ms=2100000)
        c,_=service.context(self.live,self.past,request)
        raw={'title_template':'{{entity}} Shot Surge','casual_template':'{{plain_body}}','visual_type':'historical_bars',
             'analyst_template':'{{entity}}: {{current}} {{unit}} versus {{baseline}} for {{scope}}, across {{sample}} matches.',
             'reason_template':'The current shot count is above the usual count for this interval.',
             'template_id':'comparison','event_ids':c.current_source_event_ids[:2]}
        with patch('backend.editorial.generate_graphic',AsyncMock(return_value=(raw,200,100))):
            draft=(await service.generate(self.live,self.past,request)).draft
        self.assertEqual(draft.source,'foundry')
        self.assertEqual(draft.comparison.metric,'shots')
        self.assertEqual(draft.casual_text,'5 shots in 10 minutes. More than usual.')
        base=dict(session_id=request.session_id,match_clock_ms=2100000,draft_id=draft.draft_id,action='approve',title='A busy spell',body=draft.casual_text)
        for bad in ['99 shots in 10 minutes.', 'High shot quality.']:
            with self.assertRaises(ValueError):
                service.act(self.live,self.past,EditorialAction(**{**base,'body':bad}))
        state=service.act(self.live,self.past,EditorialAction(**base))
        self.assertEqual(state.published.team_id,'northbridge')
        self.assertEqual(state.published.current_value,5)
        self.assertTrue(service.relevant(self.live,self.past,draft,2100000))
        self.assertIsNone(service.state(self.live,self.past,request.session_id,2220000).published)

    def test_detected_automatically_and_opponent_is_excluded(self):
        rows=detect_moments(self.live,self.past,2100000,self.store)
        self.assertEqual((rows[0].entity_id,rows[0].metric),('northbridge','shots'))
        events=[e for e in self.live.events if e.team_id=='northbridge']
        c,_=shot_comparison(self.live,self.past,events,2100000,'riverside',self.store)
        self.assertEqual(c.current_value,0)

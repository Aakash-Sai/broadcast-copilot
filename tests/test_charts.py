import unittest
from unittest.mock import AsyncMock,patch
from backend.charts import build_visual,visual_types,model_visual_types
from backend.contracts import DraftRequest,EditorialAction
from backend.editorial import EditorialService
from backend.main import fixture,history,historical_index


class ChartTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.live,self.past=fixture(),history()
        self.service=EditorialService(historical_index())
        self.request=DraftRequest(session_id='chart-tests-001',mode='team',entity_id='riverside',match_clock_ms=900000)
        self.comparison,_=self.service.context(self.live,self.past,self.request)
        self.raw={'title_template':'{{entity}} Pressure Surge','casual_template':'{{plain_body}}',
            'analyst_template':'{{entity}}: {{current}} {{unit}} versus {{baseline}} for {{scope}}, across {{sample}} prior matches.',
            'reason_template':'The count is above the usual count for this interval.',
            'template_id':'comparison','event_ids':self.comparison.current_source_event_ids[:2],
            'visual_type':'historical_dots'}

    def test_chart_points_are_latest_verified_history_plus_current(self):
        for kind in ['historical_bars','historical_dots']:
            visual=build_visual(self.comparison,kind)
            self.assertEqual([p.value for p in visual.points],[2,0,1,3,8,20])
            self.assertEqual([p.match_id for p in visual.points[:-1]],self.comparison.source_match_ids[-5:])
            self.assertTrue(visual.points[-1].is_current)
            self.assertEqual(visual.points[-1].label,'Now')
            self.assertIn('5 of 20',visual.caption)
            self.assertIn('same period',visual.caption)

    def test_two_points_or_invalid_series_remains_numeric(self):
        for update in [dict(historical_values=[2,4],source_match_ids=['a','b']),
                       dict(source_match_ids=['only-one']),dict(historical_values=[-1]*20),
                       dict(historical_values=[float('nan')]*20)]:
            comparison=self.comparison.model_copy(update=update)
            self.assertEqual(model_visual_types(comparison),['numbers'])
            self.assertEqual(build_visual(comparison,'numbers').points,[])
            with self.assertRaises(ValueError):
                build_visual(comparison,'historical_bars')

    async def test_ai_choice_preview_options_and_producer_override(self):
        provider=AsyncMock(return_value=(self.raw,250,120))
        with patch('backend.editorial.generate_graphic',provider):
            draft=(await self.service.generate(self.live,self.past,self.request)).draft
        self.assertEqual(draft.source,'foundry')
        self.assertEqual(draft.visual.kind,'historical_dots')
        self.assertEqual([v.kind for v in draft.visual_options],['numbers','historical_bars','historical_dots'])
        evidence,schema=provider.call_args.args
        self.assertEqual([p['value'] for p in evidence['visual_data']['historical_series']],[2,0,1,3,8])
        self.assertEqual(schema['properties']['visual_type']['enum'],['historical_bars','historical_dots'])
        action=EditorialAction(session_id=self.request.session_id,match_clock_ms=900000,action='approve',
            draft_id=draft.draft_id,title=draft.title,body=draft.casual_text,visual_type='numbers')
        with self.assertRaisesRegex(ValueError,'140'):
            self.service.act(self.live,self.past,action.model_copy(update={'visual_type':'historical_bars','audience':'analyst','body':'A contextual comparison. '*7}))
        state=self.service.act(self.live,self.past,action)
        self.assertEqual(state.published.visual.kind,'numbers')
        self.assertEqual(state.published.visual.points,[])
        provider.assert_awaited_once()

    async def test_bad_chart_choice_or_model_values_cannot_change_plotted_data(self):
        for update in [{'visual_type':'line'},{'chart_values':[999]}]:
            self.service=EditorialService(historical_index())
            with patch('backend.editorial.generate_graphic',AsyncMock(return_value=({**self.raw,**update},200,100))):
                draft=(await self.service.generate(self.live,self.past,self.request)).draft
            self.assertEqual(draft.source,'factual_fallback')
            self.assertEqual([p.value for p in draft.visual.points],[2,0,1,3,8,20])

    async def test_chart_publication_and_expiry_share_the_same_snapshot(self):
        with patch('backend.editorial.generate_graphic',AsyncMock(return_value=(self.raw,200,100))):
            draft=(await self.service.generate(self.live,self.past,self.request)).draft
        state=self.service.act(self.live,self.past,EditorialAction(session_id=self.request.session_id,
            match_clock_ms=900000,action='approve',draft_id=draft.draft_id,title=draft.title,
            body=draft.casual_text,visual_type='historical_bars'))
        self.assertEqual(state.published.visual.kind,'historical_bars')
        self.assertEqual(state.published.visual.points[-1].value,20)
        self.assertIsNone(self.service.state(self.live,self.past,self.request.session_id,1020000).published)

    def test_substitute_counts_stay_numeric_without_mixing_categories(self):
        request=self.request.model_copy(update={'mode':'player','entity_id':'r-12','match_clock_ms':4440000})
        comparison,_=self.service.context(self.live,self.past,request)
        self.assertEqual(visual_types(comparison),['numbers'])

import unittest
from unittest.mock import AsyncMock, patch
import httpx
from backend.main import fixture, history
from backend.contracts import DraftRequest, EditorialAction
from backend.editorial import EditorialService


class EditorialTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service=EditorialService()
        self.live,self.past=fixture(),history()
        self.request=DraftRequest(session_id='test-session-001',match_clock_ms=2640000,mode='player',entity_id='n-8')
        comparison,_=self.service.context(self.live,self.past,self.request)
        self.raw={
            'title_template':'{{entity}} | Unusual involvement',
            'casual_template':'{{plain_body}}','visual_type':'historical_bars',
            'analyst_template':'{{entity}}: {{current}} {{unit}} versus {{baseline}} for {{scope}} across {{sample}} matches.',
            'reason_template':'The current count stands above the usual total and deserves a contextual comparison.',
            'template_id':'comparison','event_ids':comparison.current_source_event_ids[:2],
        }

    async def make_draft(self,raw=None,error=None):
        provider=AsyncMock(side_effect=error) if error else AsyncMock(return_value=(raw or self.raw,300,150))
        with patch('backend.editorial.generate_graphic',provider):
            result=await self.service.generate(self.live,self.past,self.request)
        return result,provider

    async def test_valid_draft_is_grounded_and_not_published(self):
        result,provider=await self.make_draft()
        draft=result.draft
        self.assertEqual(draft.source,'foundry')
        self.assertIn('16 forward passes completed',draft.casual_text)
        self.assertIn('usual at this point',draft.casual_text)
        self.assertLessEqual(len(draft.casual_text.split()),20)
        self.assertNotIn('{{',draft.casual_text)
        self.assertEqual(draft.input_tokens,300)
        self.assertIsNone(self.service.state(self.live,self.past,self.request.session_id,2640000).published)
        evidence=provider.call_args.args[0]
        self.assertNotIn('API_KEY',str(evidence))
        self.assertNotIn('events',evidence)

    async def test_exact_snapshot_is_cached_and_concurrent_requests_deduplicated(self):
        provider=AsyncMock(return_value=(self.raw,300,150))
        import asyncio
        with patch('backend.editorial.generate_graphic',provider):
            results=await asyncio.gather(*(self.service.generate(self.live,self.past,self.request) for _ in range(2)))
        self.assertEqual(provider.await_count,1)
        self.assertEqual(results[0].draft.draft_id,results[1].draft.draft_id)
        self.assertTrue(results[1].cached)

    async def test_bad_numbers_sources_claims_and_placeholders_fall_back(self):
        for field,value in [('casual_template','{{entity}} has 99 passes.'),
                            ('event_ids',['future-event']),('reason_template','The change caused a goal.'),
                            ('title_template','{{unknown}}'),('template_id','trend')]:
            with self.subTest(field=field):
                self.service=EditorialService()
                raw={**self.raw,field:value}
                result,_=await self.make_draft(raw)
                self.assertEqual(result.draft.source,'foundry' if field=='reason_template' else 'factual_fallback')
                if field=='reason_template':
                    self.assertEqual(result.draft.diagnostic,'explanation_replaced')
                    self.assertNotIn('caused',result.draft.rationale)
                self.assertEqual(result.draft.status,'proposed')

    async def test_schema_constrains_comparison_slots_sources_and_layouts(self):
        result,provider=await self.make_draft()
        schema=provider.call_args.args[1]
        self.assertEqual(schema['properties']['casual_template']['enum'],['{{plain_body}}'])
        self.assertTrue(all('{{scope}}' in text and '{{sample}}' in text for text in schema['properties']['analyst_template']['enum']))
        self.assertEqual(schema['properties']['template_id']['enum'],['comparison','spotlight'])
        self.assertEqual(schema['properties']['event_ids']['items']['enum'],result.draft.comparison.current_source_event_ids[:12])
        self.assertEqual(provider.call_args.args[0]['comparison']['window'],'{{window}}')
        provider.assert_awaited_once()

    async def test_provider_timeout_is_a_labeled_fallback(self):
        result,_=await self.make_draft(error=httpx.ReadTimeout('private upstream details'))
        self.assertEqual(result.draft.source,'factual_fallback')
        self.assertNotIn('private upstream',result.draft.message)

    async def test_quiet_moment_never_calls_model(self):
        request=self.request.model_copy(update={'match_clock_ms':0})
        provider=AsyncMock()
        with patch('backend.editorial.generate_graphic',provider):
            result=await self.service.generate(self.live,self.past,request)
        self.assertIsNone(result.draft)
        provider.assert_not_awaited()

    async def test_approval_edits_dismissal_expiry_and_session_isolation(self):
        result,_=await self.make_draft()
        draft=result.draft
        base=dict(session_id=self.request.session_id,match_clock_ms=2640000,draft_id=draft.draft_id,
                  title=draft.title,body=draft.casual_text,audience='casual')
        with self.assertRaisesRegex(ValueError,'unsupported'):
            self.service.act(self.live,self.past,EditorialAction(**{**base,'body':'Alex Morgan has 999 passes.'},action='approve'))
        with self.assertRaisesRegex(ValueError,'20 words'):
            self.service.act(self.live,self.past,EditorialAction(**{**base,'body':'More passes. '*25},action='approve'))
        with self.assertRaisesRegex(ValueError,'not found'):
            self.service.act(self.live,self.past,EditorialAction(**{**base,'session_id':'another-session'},action='approve'))
        state=self.service.act(self.live,self.past,EditorialAction(**base,action='approve'))
        self.assertEqual(state.published.body,draft.casual_text)
        self.assertEqual(state.published.current_value,16)
        self.assertEqual(state.published.entity_name,'Alex Morgan')
        self.assertEqual(state.published.entity_type,'player')
        self.assertEqual(state.published.team_id,'northbridge')
        self.assertIsNone(self.service.state(self.live,self.past,'another-session',2640000).published)
        self.assertIsNone(self.service.state(self.live,self.past,self.request.session_id,2760000).published)
        self.assertEqual(draft.status,'expired')

    async def test_seek_back_clears_graphic_and_cached_snapshot_can_be_reviewed_again(self):
        result,_=await self.make_draft()
        draft=result.draft
        self.service.act(self.live,self.past,EditorialAction(session_id=self.request.session_id,match_clock_ms=2640000,
            draft_id=draft.draft_id,action='approve',title=draft.title,body=draft.casual_text))
        self.assertIsNone(self.service.state(self.live,self.past,self.request.session_id,0).published)
        provider=AsyncMock()
        with patch('backend.editorial.generate_graphic',provider):
            repeated=await self.service.generate(self.live,self.past,self.request)
        self.assertTrue(repeated.cached)
        self.assertEqual(repeated.draft.status,'proposed')
        provider.assert_not_awaited()

    async def test_dismissed_snapshot_is_not_silently_reproposed(self):
        result,_=await self.make_draft()
        self.service.act(self.live,self.past,EditorialAction(session_id=self.request.session_id,match_clock_ms=2640000,
            draft_id=result.draft.draft_id,action='dismiss'))
        repeated,_=await self.make_draft()
        self.assertTrue(repeated.cached)
        self.assertEqual(repeated.draft.status,'dismissed')

    async def test_casual_headline_can_be_edited_without_repeating_entity(self):
        result,_=await self.make_draft()
        draft=result.draft
        state=self.service.act(self.live,self.past,EditorialAction(session_id=self.request.session_id,
            match_clock_ms=2640000,draft_id=draft.draft_id,action='approve',title='Busy in midfield',body=draft.casual_text))
        self.assertEqual(state.published.title,'Busy in midfield')
        self.assertTrue(state.published.show_headline)
        self.assertEqual(state.published.entity_name,'Alex Morgan')

    async def test_request_limit_caps_model_usage(self):
        import time
        self.service.calls.extend((time.monotonic(),self.request.session_id) for _ in range(10))
        with self.assertRaisesRegex(ValueError,'limit reached'):
            await self.make_draft()

    async def test_team_window_is_rendered_and_can_be_approved(self):
        self.request=self.request.model_copy(update={'mode':'team','entity_id':'riverside','match_clock_ms':900000})
        comparison,_=self.service.context(self.live,self.past,self.request)
        raw={**self.raw,'title_template':'{{entity}} Pressure Surge',
             'casual_template':'{{plain_body}}','visual_type':'historical_bars',
             'event_ids':comparison.current_source_event_ids[:2]}
        result,_=await self.make_draft(raw)
        draft=result.draft
        self.assertEqual(draft.source,'foundry')
        self.assertEqual('20 presses in 5 minutes. More than usual.',draft.casual_text)
        state=self.service.act(self.live,self.past,EditorialAction(session_id=self.request.session_id,match_clock_ms=900000,
            draft_id=draft.draft_id,action='approve',title=draft.title,body=draft.casual_text))
        self.assertEqual(state.published.current_value,20)
        self.assertEqual(state.published.baseline_value,3.2)
        self.assertEqual(state.published.entity_name,'Riverside')
        self.assertEqual(state.published.team_name,'Riverside')
        self.assertEqual(state.published.entity_type,'team')


if __name__=='__main__':
    unittest.main()

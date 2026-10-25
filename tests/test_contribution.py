import unittest
from unittest.mock import AsyncMock, patch
from backend.main import fixture, history
from backend.statistics import analyze
from backend.editorial import EditorialService
from backend.contracts import DraftRequest, EditorialAction


class ContributionTests(unittest.IsolatedAsyncioTestCase):
    def snapshot(self, clock, live=None):
        return analyze(live or fixture(), history(), 0, 'r-12', match_clock_ms=clock).comparison

    def test_entry_boundary_and_counts_match_events(self):
        self.assertIsNone(self.snapshot(3599999).contribution)
        self.assertFalse(self.snapshot(3600000).contribution.eligible)
        result=self.snapshot(4440000)
        c=result.contribution
        events=[e for e in fixture().events if e.player_id=='r-12' and 3600000<=e.match_clock_ms<=4440000]
        self.assertEqual(c.completed_passes,sum(e.type=='pass' and e.outcome=='completed' for e in events))
        self.assertEqual(c.shots,sum(e.type=='shot' for e in events))
        self.assertEqual(c.goals,1)
        self.assertEqual(c.minutes_played,14)
        self.assertIsNone(result.baseline_value)
        self.assertEqual(result.source_match_ids,[])

    def test_no_future_leakage_and_duplicate_events(self):
        live=fixture()
        prefix=live.model_copy(update={'events':[e for e in live.events if e.match_clock_ms<=4440000]})
        self.assertEqual(self.snapshot(4440000),self.snapshot(4440000,prefix))
        duplicate=live.model_copy(update={'events':live.events+live.events})
        self.assertEqual(self.snapshot(4440000),self.snapshot(4440000,duplicate))
        self.assertEqual(self.snapshot(4439999).contribution.goals,0)

    async def test_draft_publish_identity_no_model_and_expiry(self):
        service=EditorialService()
        request=DraftRequest(session_id='substitute-test-001',mode='player',entity_id='r-12',match_clock_ms=4440000)
        with patch('backend.editorial.generate_graphic',AsyncMock()) as provider:
            result=await service.generate(fixture(),history(),request)
            provider.assert_not_awaited()
        draft=result.draft
        self.assertEqual(draft.source,'calculated')
        self.assertLessEqual(len(draft.casual_text.split()),20)
        self.assertIn('1 goal',draft.casual_text)
        self.assertEqual(draft.input_tokens,0)
        self.assertIsNone(service.state(fixture(),history(),request.session_id,4440000).published)
        base=dict(session_id=request.session_id,match_clock_ms=4440000,draft_id=draft.draft_id,action='approve',title=draft.title,body=draft.casual_text)
        with self.assertRaisesRegex(ValueError,'calculated counts'):
            service.act(fixture(),history(),EditorialAction(**{**base,'body':'The substitution caused a goal.'}))
        state=service.act(fixture(),history(),EditorialAction(**base))
        self.assertEqual(state.published.team_id,'riverside')
        self.assertEqual(state.published.entity_type,'player')
        self.assertIsNone(state.published.baseline_value)
        self.assertIsNone(service.state(fixture(),history(),request.session_id,4560000).published)

    async def test_broadcaster_can_edit_headline_and_wording(self):
        service=EditorialService()
        request=DraftRequest(session_id='editable-sub-001',mode='player',entity_id='r-12',match_clock_ms=4440000)
        draft=(await service.generate(fixture(),history(),request)).draft
        base=dict(session_id=request.session_id,match_clock_ms=4440000,draft_id=draft.draft_id,action='approve',
                  title='A scoring contribution',body='Since coming on: 4 completed passes and 1 goal.')
        for bad in ['Since coming on: 4 goals.', 'Since coming on: 999 passes.', 'The change caused a goal.']:
            with self.assertRaises(ValueError):
                service.act(fixture(),history(),EditorialAction(**{**base,'body':bad}))
        state=service.act(fixture(),history(),EditorialAction(**base))
        self.assertEqual(state.published.title,base['title'])
        self.assertEqual(state.published.body,base['body'])
        self.assertTrue(state.published.show_headline)
        reviewed=service.state(fixture(),history(),request.session_id,4440000).drafts[-1]
        self.assertEqual(reviewed.casual_text,base['body'])
        self.assertEqual(reviewed.title,base['title'])

    async def test_quiet_entry_no_draft_and_changed_counts_expire(self):
        service=EditorialService()
        request=DraftRequest(session_id='substitute-test-002',mode='player',entity_id='r-12',match_clock_ms=3600000)
        with patch('backend.editorial.generate_graphic',AsyncMock()) as provider:
            self.assertIsNone((await service.generate(fixture(),history(),request)).draft)
            before=await service.generate(fixture(),history(),request.model_copy(update={'match_clock_ms':4439999}))
            provider.assert_not_awaited()
        self.assertIsNotNone(before.draft)
        self.assertEqual(service.state(fixture(),history(),request.session_id,4440000).drafts[-1].status,'expired')


if __name__=='__main__':
    unittest.main()

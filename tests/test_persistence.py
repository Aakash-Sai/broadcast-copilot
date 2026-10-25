import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from backend.main import fixture, history, historical_index
from backend.editorial import EditorialService
from backend.editorial_store import EditorialStore
from backend.contracts import DraftRequest, EditorialAction


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'editorial.sqlite3'
        self.repository=EditorialStore(self.path)
        self.service=EditorialService(historical_index(),self.repository)
        self.live,self.past=fixture(),history()
        self.request=DraftRequest(session_id='persistent-workspace',mode='player',entity_id='r-12',match_clock_ms=4440000)

    def restart(self):
        return EditorialService(historical_index(),EditorialStore(self.path))

    async def draft(self):
        return (await self.service.generate(self.live,self.past,self.request)).draft

    def action(self,draft,action='approve',**updates):
        return EditorialAction(**dict(session_id=self.request.session_id,match_clock_ms=self.request.match_clock_ms,
            draft_id=draft.draft_id,action=action,title=draft.title,body=draft.casual_text,**updates))

    async def test_saved_edits_and_publication_survive_restart_with_full_audit(self):
        draft=await self.draft()
        original_title=draft.title
        action=self.action(draft,'save').model_copy(update={'title':'A useful contribution'})
        self.service.act(self.live,self.past,action)
        restarted=self.restart()
        state=restarted.state(self.live,self.past,self.request.session_id,self.request.match_clock_ms)
        self.assertEqual(state.drafts[-1].title,'A useful contribution')
        self.assertEqual(state.drafts[-1].status,'proposed')
        self.assertIsNone(state.published)
        restarted.act(self.live,self.past,self.action(state.drafts[-1]))
        second=self.restart()
        state=second.state(self.live,self.past,self.request.session_id,self.request.match_clock_ms)
        self.assertEqual(state.published.title,'A useful contribution')
        self.assertTrue(state.published.show_headline)
        self.assertEqual(state.published.current_value,draft.comparison.current_value)
        audit=self.repository.audit(second.namespace,self.request.session_id)
        self.assertEqual(len(audit),3)
        self.assertIn('Approved',audit[0]['event'])
        self.assertEqual(audit[0]['details']['publication']['title'],'A useful contribution')
        self.assertEqual(audit[-1]['details']['draft']['title'],original_title)
        self.assertTrue(audit[0]['at'].endswith('+00:00'))
        summary=self.repository.summary(second.namespace)
        self.assertEqual(summary['drafts_by_source'],{'calculated':1})
        self.assertEqual(summary['drafts_by_status'],{'approved':1})
        self.assertEqual(summary['audit_events'],3)

    async def test_audit_insert_failure_rolls_back_the_entire_database_transaction(self):
        draft=await self.draft()
        with self.repository.connect() as db:
            db.executescript("""CREATE TRIGGER reject_approval BEFORE INSERT ON audit
                WHEN NEW.event LIKE 'Approved%' BEGIN SELECT RAISE(ABORT,'audit unavailable'); END;""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.act(self.live,self.past,self.action(draft))
        restored=self.restart().state(self.live,self.past,self.request.session_id,self.request.match_clock_ms)
        self.assertEqual(restored.drafts[-1].status,'proposed')
        self.assertIsNone(restored.published)
        self.assertEqual(self.repository.summary(self.service.namespace)['audit_events'],1)

    async def test_clear_dismiss_and_expiry_are_durable_and_polling_is_not_audited(self):
        draft=await self.draft()
        self.service.act(self.live,self.past,self.action(draft))
        self.service.act(self.live,self.past,self.action(draft,'clear'))
        service=self.restart()
        state=service.state(self.live,self.past,self.request.session_id,self.request.match_clock_ms)
        self.assertIsNone(state.published)
        self.assertEqual(state.drafts[-1].status,'superseded')
        count=len(self.repository.audit(service.namespace,self.request.session_id))
        service.state(self.live,self.past,self.request.session_id,self.request.match_clock_ms)
        self.assertEqual(len(self.repository.audit(service.namespace,self.request.session_id)),count)
        self.service=service
        draft=await self.draft()
        service.act(self.live,self.past,self.action(draft,'dismiss'))
        self.assertEqual(self.restart().state(self.live,self.past,self.request.session_id,self.request.match_clock_ms).drafts[-1].status,'dismissed')
        # A different snapshot avoids reuse of a deliberately dismissed draft.
        self.request=self.request.model_copy(update={'match_clock_ms':4440001})
        draft=await self.draft()
        service.state(self.live,self.past,self.request.session_id,draft.expires_at_match_clock_ms)
        state=self.restart().state(self.live,self.past,self.request.session_id,draft.expires_at_match_clock_ms)
        self.assertEqual(state.drafts[-1].status,'expired')
        self.assertIsNone(state.published)

    async def test_write_failure_rolls_back_memory_publication_and_audit(self):
        draft=await self.draft()
        with patch.object(self.repository,'commit',side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.act(self.live,self.past,self.action(draft))
        self.assertEqual(self.service.drafts[draft.draft_id].status,'proposed')
        self.assertNotIn(self.request.session_id,self.service.published)
        state=self.restart().state(self.live,self.past,self.request.session_id,self.request.match_clock_ms)
        self.assertIsNone(state.published)
        self.assertEqual(len(self.repository.audit(self.service.namespace,self.request.session_id)),1)

    async def test_history_is_scoped_to_workspace_and_fixture_content_and_backup_restores(self):
        draft=await self.draft()
        self.service.act(self.live,self.past,self.action(draft))
        self.assertEqual(self.repository.session_drafts(self.service.namespace,'another-workspace'),[])
        changed=self.live.model_copy(update={'label':'Changed fixture'})
        isolated=self.restart().state(changed,self.past,self.request.session_id,self.request.match_clock_ms)
        self.assertEqual(isolated.drafts,[])
        self.assertIsNone(isolated.published)
        target=Path(self.temp.name)/'backup.sqlite3'
        self.repository.backup(target)
        restored=EditorialService(historical_index(),EditorialStore(target))
        self.assertIsNotNone(restored.state(self.live,self.past,self.request.session_id,self.request.match_clock_ms).published)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        with self.assertRaises(ValueError):
            self.repository.backup(self.path)

    async def test_evicted_drafts_remain_in_durable_history(self):
        draft=await self.draft()
        with self.service.transaction():
            for index in range(105):
                copy=draft.model_copy(deep=True,update={'draft_id':f'archived-{index}'})
                self.service.save(copy)
                self.service.record(copy.session_id,'Generated test draft',copy)
        self.assertLessEqual(len(self.service.drafts),100)
        with self.repository.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0],106)
        self.assertEqual(len(self.repository.session_drafts(self.service.namespace,self.request.session_id,200)),106)

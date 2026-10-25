import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from backend import main
from backend.contracts import DraftRequest
from backend.editorial import EditorialService
from backend.editorial_store import EditorialStore, DraftLimitReached


class DurableLimitsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'demo.sqlite3'
        self.store=EditorialStore(self.path)

    def test_daily_window_and_lifetime_limit_survive_restart(self):
        self.store.reserve_model_call(daily_limit=2,total_limit=3,now=100000)
        self.store.reserve_model_call(daily_limit=2,total_limit=3,now=100001)
        restarted=EditorialStore(self.path)
        with self.assertRaises(DraftLimitReached):
            restarted.reserve_model_call(daily_limit=2,total_limit=3,now=100002)
        restarted.reserve_model_call(daily_limit=2,total_limit=3,now=200000)
        with self.assertRaises(DraftLimitReached):
            EditorialStore(self.path).reserve_model_call(daily_limit=2,total_limit=3,now=300000)

    def test_concurrent_requests_cannot_overshoot_the_limit(self):
        def reserve(_):
            try:
                self.store.reserve_model_call(daily_limit=5,total_limit=5)
                return 1
            except DraftLimitReached:
                return 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(reserve,range(12))),5)

    def test_public_diagnostics_are_disabled_and_limits_return_429(self):
        client=TestClient(main.app)
        with patch('backend.main.PUBLIC_DEMO',True),patch('backend.main.probe',AsyncMock()) as provider:
            self.assertEqual(client.get('/api/ops').status_code,404)
            self.assertEqual(client.post('/api/foundry/probe').status_code,404)
            self.assertTrue(client.get('/api/health').json()['public_demo'])
            provider.assert_not_awaited()
        with patch.object(main.editorial,'generate',AsyncMock(side_effect=DraftLimitReached('Allowance reached.'))):
            result=client.post('/api/editorial/generate',json={'session_id':'public-limit-test',
                'match_clock_ms':2640000,'mode':'player','entity_id':'n-8'})
            self.assertEqual(result.status_code,429)


class PublicGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_provider_counts_cache_does_not_and_budget_blocks_before_call(self):
        with tempfile.TemporaryDirectory() as directory:
            repository=EditorialStore(Path(directory)/'demo.sqlite3')
            service=EditorialService(main.historical_index(),repository,public_demo=True)
            request=DraftRequest(session_id='public-generation-test',mode='player',entity_id='n-8',match_clock_ms=2640000)
            with patch('backend.editorial.generate_graphic',AsyncMock(side_effect=ValueError('Offline'))) as provider:
                first=await service.generate(main.fixture(),main.history(),request)
                self.assertEqual(first.draft.source,'factual_fallback')
                self.assertTrue((await service.generate(main.fixture(),main.history(),request)).cached)
                self.assertEqual(provider.await_count,1)
                self.assertEqual(repository.summary(service.namespace)['reserved_model_calls'],1)
            with repository.connect() as db:
                db.executemany('INSERT INTO model_calls(at) VALUES(?)',[(time.time(),)]*499)
            restarted=EditorialService(main.historical_index(),EditorialStore(repository.path),public_demo=True)
            with patch('backend.editorial.generate_graphic',AsyncMock()) as provider:
                with self.assertRaises(DraftLimitReached):
                    await restarted.generate(main.fixture(),main.history(),request)
                # A calculated substitute card remains available without a model call.
                substitute=request.model_copy(update={'entity_id':'r-12','match_clock_ms':4440000})
                self.assertEqual((await restarted.generate(main.fixture(),main.history(),substitute)).draft.source,'calculated')
                provider.assert_not_awaited()

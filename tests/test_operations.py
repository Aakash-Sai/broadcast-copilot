import sqlite3
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app, ops, repository


class OperationsTests(unittest.TestCase):
    def test_health_checks_do_not_call_foundry_and_report_storage_failure(self):
        client=TestClient(app)
        with patch('backend.main.probe') as probe:
            self.assertEqual(client.get('/health/live').status_code,200)
            self.assertEqual(client.get('/health/ready').status_code,200)
            probe.assert_not_called()
        with patch.object(repository,'check',side_effect=sqlite3.OperationalError('private database path')):
            result=client.get('/health/ready')
            self.assertEqual(result.status_code,503)
            self.assertNotIn('private',result.text)

    def test_request_metrics_and_logs_do_not_expose_queries(self):
        client=TestClient(app)
        with patch.object(ops.logger,'info') as log:
            result=client.get('/api/analysis?match_clock_ms=0&private_key=do-not-log')
            self.assertEqual(result.status_code,200)
            self.assertIn('X-Request-ID',result.headers)
            self.assertNotIn('do-not-log',str(log.call_args_list))
        stats=client.get('/api/ops').json()
        self.assertTrue(any(row['route']=='/api/analysis' and row['count']>=1 for row in stats['requests']))
        self.assertIn('drafts_by_source',stats['workflow'])
        self.assertNotIn('do-not-log',str(stats))

    def test_audit_and_history_routes_are_bounded_and_do_not_leak_other_sessions(self):
        client=TestClient(app)
        self.assertEqual(client.get('/api/editorial/audit?session_id=ops-empty-workspace&limit=1001').status_code,422)
        result=client.get('/api/editorial/audit?session_id=ops-empty-workspace')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['events'],[])
        self.assertIn('attachment',result.headers['content-disposition'])
        self.assertEqual(client.get('/api/editorial/history?session_id=ops-empty-workspace').json(),[])

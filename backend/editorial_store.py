"""Single-instance SQLite persistence; workflow snapshots and audit commit together."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import time

from backend.contracts import GraphicDraft, PublishedGraphic


class DraftLimitReached(ValueError):
    pass


class EditorialStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError('Unsupported editorial database version.')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY, namespace TEXT NOT NULL, session TEXT NOT NULL,
                    payload TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS drafts_session ON drafts(namespace,session);
                CREATE TABLE IF NOT EXISTS publications (
                    namespace TEXT NOT NULL, session TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(namespace,session));
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT NOT NULL,
                    session TEXT NOT NULL, at TEXT NOT NULL, event TEXT NOT NULL,
                    draft_id TEXT, details TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS audit_session ON audit(namespace,session,id);
                CREATE TABLE IF NOT EXISTS model_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS model_calls_time ON model_calls(at);
                PRAGMA user_version=1;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def check(self):
        # Check a write transaction, not just a successful read from a stale file.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE drafts SET updated_at=updated_at WHERE id=?', ('__health__',))
            db.rollback()

    def reserve_model_call(self, daily_limit=100, total_limit=500, now=None):
        """Conservative call ceiling shared across restarts and fixture versions.

        Reserve before sending; failures also consume a slot. This is a call
        ceiling, not a dollar cap. Cache hits/calculated cards need no slot.
        """
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            total=db.execute('SELECT COUNT(*) FROM model_calls').fetchone()[0]
            daily=db.execute('SELECT COUNT(*) FROM model_calls WHERE at>?',(now-86400,)).fetchone()[0]
            if total>=total_limit or daily>=daily_limit:
                raise DraftLimitReached('The demo AI drafting allowance has been reached. Saved work remains available.')
            db.execute('INSERT INTO model_calls(at) VALUES(?)',(now,))

    def load(self, namespace):
        with self.connect() as db:
            published = {s: PublishedGraphic.model_validate_json(p) for s,p in db.execute(
                'SELECT session,payload FROM publications WHERE namespace=?', (namespace,))}
            rows = db.execute('SELECT payload FROM drafts WHERE namespace=? ORDER BY rowid DESC LIMIT 100', (namespace,)).fetchall()[::-1]
            drafts = {d.draft_id:d for d in (GraphicDraft.model_validate_json(row[0]) for row in rows)}
            for graphic in published.values():
                row = db.execute('SELECT payload FROM drafts WHERE id=? AND namespace=?', (graphic.draft_id,namespace)).fetchone()
                if row:
                    drafts[graphic.draft_id] = GraphicDraft.model_validate_json(row[0])
            actions = {}
            for session,message in db.execute('''SELECT session,event FROM
                (SELECT session,event,id,ROW_NUMBER() OVER(PARTITION BY session ORDER BY id DESC) AS n
                 FROM audit WHERE namespace=?) WHERE n<=12 ORDER BY id''', (namespace,)):
                actions.setdefault(session, []).append(message)
                actions[session] = actions[session][-12:]
            return drafts,published,actions

    def session_drafts(self, namespace, session, limit=100):
        with self.connect() as db:
            return [GraphicDraft.model_validate_json(row[0]) for row in db.execute(
                'SELECT payload FROM drafts WHERE namespace=? AND session=? ORDER BY rowid DESC LIMIT ?',
                (namespace,session,limit))][::-1]

    def commit(self, namespace, drafts, published, sessions, events):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            for draft in drafts:
                payload = draft.model_dump_json()
                db.execute('''INSERT INTO drafts VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE
                    SET payload=excluded.payload,updated_at=excluded.updated_at
                    WHERE drafts.payload<>excluded.payload''',
                    (draft.draft_id,namespace,draft.session_id,payload,now))
            for session in sessions:
                graphic = published.get(session)
                if graphic:
                    db.execute('INSERT OR REPLACE INTO publications VALUES(?,?,?)', (namespace,session,graphic.model_dump_json()))
                else:
                    db.execute('DELETE FROM publications WHERE namespace=? AND session=?', (namespace,session))
            for event in events:
                db.execute('INSERT INTO audit(namespace,session,at,event,draft_id,details) VALUES(?,?,?,?,?,?)',
                    (namespace,event['session'],now,event['event'],event['draft_id'],json.dumps(event['details'])))

    def audit(self, namespace, session, limit=100):
        with self.connect() as db:
            rows = db.execute('SELECT id,at,event,draft_id,details FROM audit WHERE namespace=? AND session=? ORDER BY id DESC LIMIT ?',
                              (namespace,session,limit)).fetchall()
            return [dict(id=i,at=at,event=event,draft_id=draft,details=json.loads(details)) for i,at,event,draft,details in rows]

    def summary(self, namespace):
        with self.connect() as db:
            return {'drafts_by_source':dict(db.execute(
                "SELECT json_extract(payload,'$.source'),COUNT(*) FROM drafts WHERE namespace=? GROUP BY 1",(namespace,))),
                'drafts_by_status':dict(db.execute(
                "SELECT json_extract(payload,'$.status'),COUNT(*) FROM drafts WHERE namespace=? GROUP BY 1",(namespace,))),
                'audit_events':db.execute('SELECT COUNT(*) FROM audit WHERE namespace=?',(namespace,)).fetchone()[0],
                'reserved_model_calls':db.execute('SELECT COUNT(*) FROM model_calls').fetchone()[0],
                'scope':'Durable totals for this fixture/history; draft counts are not model-call or billing totals.'}

    def backup(self, destination):
        destination = Path(destination)
        if destination.resolve() == self.path.resolve():
            raise ValueError('Backup destination must differ from the live database.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()

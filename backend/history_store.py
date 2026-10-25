"""Indexed, parameterized historical queries. No model-generated SQL."""
import sqlite3
import threading
from dataclasses import dataclass


@dataclass
class Reference:
    match_id: str
    value: float
    event_ids: list[str]
    shots: int = 0
    goals: int = 0


class HistoryStore:
    def __init__(self, matches):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.db.executescript('''
            CREATE TABLE matches(id TEXT PRIMARY KEY,kickoff REAL,completed REAL,duration INTEGER);
            CREATE TABLE participants(match_id TEXT,player_id TEXT,start INTEGER,end INTEGER,PRIMARY KEY(match_id,player_id));
            CREATE TABLE teams(match_id TEXT,team_id TEXT,PRIMARY KEY(match_id,team_id));
            CREATE TABLE events(id TEXT PRIMARY KEY,match_id TEXT,clock INTEGER,team_id TEXT,player_id TEXT,type TEXT,outcome TEXT,forward INTEGER);
            CREATE INDEX player_events ON events(match_id,player_id,clock);
            CREATE INDEX team_events ON events(match_id,team_id,type,clock);
            CREATE INDEX player_history ON participants(player_id,match_id);
        ''')
        seen = {}
        for match in matches:
            if match.match_id in seen:
                if seen[match.match_id] != match:
                    raise ValueError('Conflicting duplicate historical match.')
                continue
            seen[match.match_id] = match
            self.db.execute('INSERT INTO matches VALUES(?,?,?,?)',
                (match.match_id, match.kickoff_at.timestamp(), match.completed_at.timestamp(), match.duration_ms))
            self.db.executemany('INSERT INTO teams VALUES(?,?)', [(match.match_id,t.team_id) for t in match.teams])
            for part in match.participation:
                if not 0 <= part.start_match_clock_ms < part.end_match_clock_ms <= match.duration_ms:
                    raise ValueError('Invalid historical participation interval.')
                self.db.execute('INSERT INTO participants VALUES(?,?,?,?)',
                    (match.match_id,part.player_id,part.start_match_clock_ms,part.end_match_clock_ms))
            events = {}
            for e in match.events:
                if e.match_id != match.match_id or e.match_clock_ms > match.duration_ms:
                    raise ValueError('Historical event belongs to an invalid match or time.')
                if e.event_id in events and events[e.event_id] != e:
                    raise ValueError('Conflicting duplicate event ID.')
                events[e.event_id] = e
            self.db.executemany('INSERT INTO events VALUES(?,?,?,?,?,?,?,?)',
                [(e.event_id,e.match_id,e.match_clock_ms,e.team_id,e.player_id,e.type,e.outcome,int(e.forward)) for e in events.values()])
        self.db.commit()
        self.db.execute('PRAGMA query_only=ON')

    def retrieve(self, live, entity_id, clock, kind, limit=20):
        """Return latest comparable prior appearances/windows in chronological order."""
        if kind not in ['player','pressure','shots','substitute'] or not 0 <= clock <= live.duration_ms:
            raise ValueError('Unsupported historical query.')
        if not 1 <= limit <= 20:
            raise ValueError('Historical query limit must be between 1 and 20.')
        cutoff = live.kickoff_at.timestamp()
        common = 'm.id<>? AND m.kickoff<? AND m.completed<? AND m.completed>m.kickoff'
        args = [live.match_id,cutoff,cutoff]
        if kind in ['pressure','shots']:
            sql = f'''SELECT m.id,0,? FROM matches m JOIN teams t ON t.match_id=m.id
                WHERE {common} AND t.team_id=? AND m.duration>=? ORDER BY m.kickoff DESC,m.id DESC LIMIT ?'''
            args = [clock,*args,entity_id,clock,limit]
        else:
            condition = 'p.start=0 AND p.end>=?' if kind == 'player' else 'p.start>0 AND p.end-p.start>=?'
            sql = f'''SELECT m.id,p.start,MIN(p.end,p.start+?) FROM matches m JOIN participants p ON p.match_id=m.id
                WHERE {common} AND p.player_id=? AND {condition} ORDER BY m.kickoff DESC,m.id DESC LIMIT ?'''
            args = [clock,*args,entity_id,clock,limit]
        with self.lock:
            matches = self.db.execute(sql,args).fetchall()
            result = []
            for match_id,start,end in reversed(matches):
                if kind in ['pressure','shots']:
                    rows = self.db.execute('''SELECT id,type,outcome FROM events WHERE match_id=? AND team_id=?
                        AND type=? AND clock>? AND clock<=? ORDER BY clock,id''',
                        (match_id,entity_id,'shot' if kind=='shots' else 'pressure',max(0,clock-(600000 if kind=='shots' else 300000)),clock)).fetchall()
                else:
                    metric = "type='pass' AND outcome='completed' AND forward=1" if kind == 'player' else "((type='pass' AND outcome='completed') OR type='shot')"
                    rows = self.db.execute(f'''SELECT id,type,outcome FROM events WHERE match_id=? AND player_id=?
                        AND clock>=? AND clock<=? AND ({metric}) ORDER BY clock,id''',
                        (match_id,entity_id,start,end)).fetchall()
                value = len(rows) if kind != 'substitute' else sum(row[1]=='pass' for row in rows)
                result.append(Reference(match_id,float(value),[row[0] for row in rows],
                    sum(row[1]=='shot' for row in rows),sum(row[1]=='shot' and row[2]=='goal' for row in rows)))
            return result

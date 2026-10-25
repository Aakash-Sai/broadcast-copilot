"""Seeded 90-minute live/history fixtures with roster-aware action events."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random
from backend.contracts import HistoricalMatch, MatchFixture, Player, Team

ROOT=Path(__file__).resolve().parent.parent
SEED=20261012
DURATION=5400000


def roster():
    names=['Ellis Rowan','Kai Mercer','Theo Lane','Finley Hart','Casey Stone','Noah Blake','Jamie Wells','Alex Morgan','Sam Reed','Drew Hayes','Robin Cole','Taylor Quinn','Avery Moss','Charlie West','Cory Lake']
    return [Player(player_id=f'{prefix}-{i}',team_id=team,name=('Jordan Vale' if prefix=='r' and i==6 else name if prefix=='n' and i in [8,9] else name+(' North' if prefix=='n' else ' River')))
            for prefix,team in [('n','northbridge'),('r','riverside')] for i,name in enumerate(names,1)]


def make_match(match_id,kickoff,seed,*,live=False, varied=False):
    rng=Random(seed)
    teams=[Team(team_id='northbridge',name='Northbridge'),Team(team_id='riverside',name='Riverside')]
    players=roster()
    subs=[]
    for prefix,team in [('n','northbridge'),('r','riverside')]:
        for j,off in enumerate([9,7,10]):
            minute=[58,67,78][j]+(2 if prefix=='r' else 0)+(0 if live else rng.randint(-3,3))
            subs.append(dict(team_id=team,match_clock_ms=minute*60000,player_off_id=f'{prefix}-{off}',player_on_id=f'{prefix}-{12+j}'))
    formations=[dict(team_id=t.team_id,match_clock_ms=0,shape='4-3-3' if i==0 else '4-2-3-1') for i,t in enumerate(teams)]
    formations += [dict(team_id='northbridge',match_clock_ms=58*60000,shape='4-2-3-1'),dict(team_id='riverside',match_clock_ms=70*60000,shape='4-4-2')]
    participation=[]
    for player in players:
        number=int(player.player_id.split('-')[1])
        off=next((s for s in subs if s['player_off_id']==player.player_id),None)
        on=next((s for s in subs if s['player_on_id']==player.player_id),None)
        if number<=11 or on:
            participation.append(dict(player_id=player.player_id,start_match_clock_ms=on['match_clock_ms'] if on else 0,end_match_clock_ms=off['match_clock_ms'] if off else DURATION))
    intervals={p['player_id']:p for p in participation}
    def active(team,time):
        return [p for p in players if p.team_id==team and p.player_id in intervals and intervals[p.player_id]['start_match_clock_ms']<=time<intervals[p.player_id]['end_match_clock_ms']]
    events=[]
    def emit(time,kind,team,player=None,outcome='applied',**extra):
        events.append(dict(match_clock_ms=time,type=kind,team_id=team,player_id=player.player_id if player else None,outcome=outcome,**extra))
    possession='northbridge'
    # Ambient short possession sequences; no continuous tracking or causal model.
    for seconds in range(6,5400,6):
        time=seconds*1000
        if 26*60000<=time<28*60000 or 45*60000<=time<46*60000:
            continue
        actor=rng.choice(active(possession,time)[1:])
        other='riverside' if possession=='northbridge' else 'northbridge'
        roll=rng.random()
        if roll<.78:
            complete=rng.random()<.83
            emit(time,'pass',possession,actor,'completed' if complete else 'incomplete',x=rng.randint(15,85),y=rng.randint(10,90),forward=rng.random()<.38)
            if not complete:
                possession=other
                emit(time,'possession_change',other,outcome='won')
        elif roll<.9:
            emit(time,'pressure',other,rng.choice(active(other,time)[1:]),x=rng.randint(30,85),y=rng.randint(10,90))
        elif roll<.98:
            emit(time,'tackle',other,rng.choice(active(other,time)[1:]),'won',x=rng.randint(20,80),y=rng.randint(10,90))
            possession=other
            emit(time,'possession_change',other,outcome='won')
        else:
            emit(time,'shot',possession,actor,rng.choice(['saved','off_target']),x=rng.randint(78,94),y=rng.randint(35,65))
            possession=other
            emit(time,'possession_change',other,outcome='won')
    goals = [(23,'northbridge','n-9'),(74,'riverside','r-12')]
    if varied:
        goals=[]
        for _ in range(rng.randint(0,5)):
            minute=rng.randint(8,88)
            team=rng.choice(['northbridge','riverside'])
            goals.append((minute,team,rng.choice(active(team,minute*60000)[1:]).player_id))
    for minute,team,pid in goals:
        emit(minute*60000,'shot',team,next(p for p in active(team,minute*60000) if p.player_id==pid),'goal',x=88,y=50)
    if live:
        for i in range(5):
            emit((31+i)*60000,'shot','northbridge',next(p for p in players if p.player_id=='n-10'),
                 'saved' if i%2==0 else 'off_target',x=86,y=45+i)
        for i in range(20):
            emit(12*60000+i*8000,'pressure','riverside',next(p for p in players if p.player_id=='r-6'),x=65,y=40)
        for i in range(10):
            emit(40*60000+i*20000,'pass','northbridge',next(p for p in players if p.player_id=='n-8'),'completed',forward=True,x=45+i*3,y=40)
    for sub in subs:
        emit(sub['match_clock_ms'],'substitution',sub['team_id'],next(p for p in players if p.player_id==sub['player_on_id']),'changed',related_player_id=sub['player_off_id'])
    for formation in formations:
        if formation['match_clock_ms']:
            emit(formation['match_clock_ms'],'formation_change',formation['team_id'],outcome='changed',formation=formation['shape'])
    events.sort(key=lambda e:(e['match_clock_ms'],0 if e['type']=='substitution' else 1))
    for sequence,event in enumerate(events,1):
        event.update(event_id=f'{match_id}-e-{sequence:04d}',match_id=match_id,sequence=sequence)
    return MatchFixture(match_id=match_id,label='Northbridge vs Riverside',kickoff_at=kickoff,duration_ms=DURATION,
        teams=teams,players=players,events=events,participation=participation,formations=formations,substitutions=sorted(subs,key=lambda s:s['match_clock_ms']),
        scenarios=[dict(label=label,match_clock_ms=minute*60000) for label,minute in [('Pressure surge',15),('Quiet spell',27),('Shot surge',35),('Player involvement',44),('Formation and substitution',58),('Substitute scores',74),('Full time',90)]] if live else [])


def generate(fixture):
    # Retain the five recent regression fixtures; add varied, older test history.
    matches=[]
    for i in range(15):
        kickoff=fixture.kickoff_at-timedelta(days=7*(20-i))
        match=make_match(f'archive-{i+1:03d}',kickoff,SEED+200+i,varied=True)
        matches.append(HistoricalMatch(**match.model_dump(),completed_at=kickoff+timedelta(minutes=105)))
    for i in range(5):
        kickoff=fixture.kickoff_at-timedelta(days=7*(5-i))
        match=make_match(f'history-{i+1:03d}',kickoff,SEED+i)
        matches.append(HistoricalMatch(**match.model_dump(),completed_at=kickoff+timedelta(minutes=105)))
    return matches


if __name__=='__main__':
    live=make_match('demo-live-001',datetime(2026,10,12,19,tzinfo=timezone.utc),SEED+100,live=True)
    past=generate(live)
    (ROOT/'data/live_fixture.json').write_text(live.model_dump_json(indent=2)+'\n')
    (ROOT/'data/historical_matches.json').write_text(json.dumps([m.model_dump(mode='json') for m in past],separators=(',',':'))+'\n')
    print(f'Live {len(live.events)} events; history {sum(len(m.events) for m in past)} events; 30 squad players.')

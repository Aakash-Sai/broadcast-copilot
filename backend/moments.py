"""Supported moment detection and ranking, without any model calls."""
from backend.contracts import Moment
from backend.statistics import analyze


def detect_moments(live, history, clock, store, drafts=()):
    if clock >= live.duration_ms:
        return []
    candidates = []
    # All players/teams are scanned; the producer's selected entity does not gate detection.
    active={p.player_id for p in live.participation if p.start_match_clock_ms<=clock<p.end_match_clock_ms}
    targets = [('player',p.player_id,p.name,'completed_forward_passes') for p in live.players if p.player_id in active]
    targets += [('team',t.team_id,t.name,metric) for t in live.teams for metric in ['pressure_events','shots']]
    for mode,entity_id,name,metric in targets:
        result = analyze(live,history,0,entity_id if mode=='player' else live.players[0].player_id,
            entity_id if mode=='team' else live.teams[0].team_id,clock,store=store)
        comparison = result.comparison if mode=='player' else result.shot_comparison if metric=='shots' else result.team_comparison
        c = comparison.contribution
        if not (c.eligible if c else comparison.matched_baseline):
            continue
        evidence=set(comparison.current_source_event_ids)
        if not any(e.event_id in evidence and clock-120000<e.match_clock_ms<=clock for e in live.events):
            continue
        if c:
            label = 'Substitute contribution'
            detail = f'{c.completed_passes} completed passes · {c.shots} shot{"s" if c.shots!=1 else ""} · {c.goals} goal{"s" if c.goals!=1 else ""} since entry'
            # A new goal can break the repeat cooldown; old goals are not a fresh trigger.
            recent_goal = any(e.event_id in comparison.current_source_event_ids and e.outcome=='goal'
                and clock-120000 < e.match_clock_ms <= clock for e in live.events)
            score = 100 if recent_goal else 35+min(c.completed_passes,10)+c.shots*3
        else:
            label = 'Shot surge' if metric=='shots' else 'Team pressure' if mode=='team' else 'Player passing'
            detail = f'{comparison.current_value:g} vs {comparison.baseline_value:g} usual · {comparison.sample_size} prior matches'
            ratio = comparison.current_value/max(comparison.baseline_value,1)
            score = min(95,50+ratio*7) if metric=='shots' else min(90,40+ratio*5)
        repeated = False
        for old in drafts:
            if old.mode!=mode or old.entity_id!=entity_id or old.comparison.metric!=comparison.metric:
                continue
            if clock < old.snapshot_clock_ms:
                continue
            if comparison.current_source_event_ids == old.comparison.current_source_event_ids:
                repeated = True
                break
            if not clock-old.snapshot_clock_ms < 120000:
                continue
            new_goal = c and old.comparison.contribution and c.goals>old.comparison.contribution.goals
            if not new_goal:
                repeated = True
                break
        if repeated:
            continue
        candidates.append(Moment(moment_id=f'{mode}-{entity_id}-{comparison.metric}',mode=mode,
            entity_id=entity_id,entity_name=name,metric=comparison.metric,match_clock_ms=clock,
            label=label,detail=detail,score=score))
    return sorted(candidates,key=lambda m:(-m.score,m.moment_id))[:3]

"""Deterministic current snapshots and historical baselines."""
from statistics import mean
from backend.history_store import HistoryStore
from backend.contracts import (Analysis, HistoricalComparison, HistoricalMatch,
    HistoricalSummary, MatchEvent, MatchFixture, Statistics, SubstituteContribution)


def unique_events(events: list[MatchEvent], match_id: str) -> list[MatchEvent]:
    unique = {}
    for event in events:
        if event.match_id != match_id:
            raise ValueError('An event belongs to a different match.')
        if event.event_id in unique:
            if unique[event.event_id] != event:
                raise ValueError('Conflicting duplicate event ID.')
            continue
        unique[event.event_id] = event
    return sorted(unique.values(), key=lambda e: (e.match_clock_ms, e.sequence))


def aggregate(events: list[MatchEvent], entity_ids: list[str], *, player: bool) -> list[Statistics]:
    stats = {key: Statistics(entity_id=key) for key in entity_ids}
    for event in events:
        key = event.player_id if player else event.team_id
        if key not in stats:
            if player and key is None:
                continue
            raise ValueError('Event references an unknown entity.')
        row = stats[key]
        if event.type == 'pass':
            row.attempted_passes += 1
            if event.outcome == 'completed':
                row.completed_passes += 1
                row.completed_forward_passes += int(event.forward)
        elif event.type == 'shot':
            row.shots += 1
            row.goals += int(event.outcome == 'goal')
        elif event.type == 'tackle':
            row.tackles_won += int(event.outcome == 'won')
        elif event.type == 'pressure':
            row.pressure_events += 1
        elif event.type == 'possession_change':
            row.possession_changes += 1
    for row in stats.values():
        if row.attempted_passes:
            row.pass_completion_pct = round(row.completed_passes / row.attempted_passes * 100, 2)
    return list(stats.values())


def historical_summary(match: HistoricalMatch) -> HistoricalSummary:
    events = unique_events(match.events, match.match_id)
    if any(e.match_clock_ms > match.duration_ms for e in events):
        raise ValueError('Historical event occurs after match end.')
    players = aggregate(events, [p.player_id for p in match.players], player=True)
    minutes = {}
    for part in match.participation:
        if (part.player_id in minutes or part.end_match_clock_ms > match.duration_ms
                or part.end_match_clock_ms <= part.start_match_clock_ms):
            raise ValueError('Invalid or repeated player participation interval.')
        minutes[part.player_id] = (part.end_match_clock_ms - part.start_match_clock_ms) / 60000
    for row in players:
        row.minutes_played = minutes.get(row.entity_id, 0)
    return HistoricalSummary(match_id=match.match_id, kickoff_at=match.kickoff_at,
        players=players, teams=aggregate(events, [t.team_id for t in match.teams], player=False))


def eligible_history(history: list[HistoricalMatch], live: MatchFixture) -> list[HistoricalMatch]:
    unique = {}
    for match in history:
        if match.match_id == live.match_id or match.kickoff_at >= live.kickoff_at or match.completed_at >= live.kickoff_at:
            continue
        if match.completed_at <= match.kickoff_at:
            raise ValueError('Historical match completion precedes kickoff.')
        if match.match_id in unique and unique[match.match_id] != match:
            raise ValueError('Conflicting duplicate historical match.')
        unique[match.match_id] = match
    return sorted(unique.values(), key=lambda m: m.kickoff_at)


def pressure_comparison(live: MatchFixture, history: list[HistoricalMatch], current: list[MatchEvent], clock: int, team_id: str, store=None) -> tuple[HistoricalComparison, str]:
    if team_id not in {t.team_id for t in live.teams}:
        raise ValueError('Unknown team.')
    start = max(0, clock - 300000)
    def window(events):
        # Half-open boundary: (start, end]. No event is counted twice at the boundary.
        return [e for e in events if e.team_id == team_id and e.type == 'pressure' and start < e.match_clock_ms <= clock]
    current_evidence = window(current)
    store = store or HistoryStore(eligible_history(history, live))
    references = store.retrieve(live, team_id, clock, 'pressure')
    values = [r.value for r in references]
    complete_window = clock >= 300000
    baseline = mean(values) if len(values) >= 3 and complete_window else None
    # Transparent demo trigger, not statistical significance or a causal claim.
    surge = baseline is not None and len(current_evidence) >= 3 and len(current_evidence) > baseline and len(current_evidence) >= baseline * 2
    limitations = ['Pressure-event counts are a proxy; they do not measure intensity or prove tactical intent.',
                   'Synthetic data and a small historical sample; no claim of statistical significance.',
                   'Demo surge rule: at least 3 events and at least twice the historical mean, exceeding that mean.']
    if not complete_window:
        limitations.append('Waiting for a complete five-minute match window; no historical comparison yet.')
    elif len(values) < 3:
        limitations.append('At least three comparable prior match windows are required; showing current counts only.')
    team_name = next(t.name for t in live.teams if t.team_id == team_id)
    interval = f'{start // 60000}:{start // 1000 % 60:02d}–{clock // 60000}:{clock // 1000 % 60:02d}'
    comparison = HistoricalComparison(entity_id=team_id, metric='pressure_events',
        current_value=len(current_evidence), baseline_value=baseline, unit='pressure events',
        window_description=f'Five-minute match-clock window {interval}; same interval in prior matches',
        sample_size=len(references), historical_values=values,
        source_match_ids=[r.match_id for r in references],
        source_event_ids=[eid for r in references for eid in r.event_ids],
        current_source_event_ids=[e.event_id for e in current_evidence], current_minutes=clock / 60000,
        matched_baseline=surge, limitations=limitations)
    if surge:
        text = f'{team_name}: {len(current_evidence)} pressure events in the last five minutes, versus {baseline:g} on average in the same historical interval.'
    else:
        text = f'{team_name}: {len(current_evidence)} pressure events in the current window. No pressure surge detected.' if baseline is not None else f'{team_name}: {len(current_evidence)} pressure events so far in this window; insufficient context for a surge comparison.'
    return comparison, text


def shot_comparison(live, history, current, clock, team_id, store=None):
    if team_id not in {t.team_id for t in live.teams}:
        raise ValueError('Unknown team.')
    start=max(0,clock-600000)
    events=[e for e in current if e.team_id==team_id and e.type=='shot' and start<e.match_clock_ms<=clock]
    store=store or HistoryStore(eligible_history(history,live))
    references=store.retrieve(live,team_id,clock,'shots')
    values=[r.value for r in references]
    baseline=mean(values) if len(values)>=3 and clock>=600000 else None
    surge=baseline is not None and len(events)>=4 and len(events)>baseline and len(events)>=baseline*2
    comparison=HistoricalComparison(entity_id=team_id,metric='shots',current_value=len(events),baseline_value=baseline,
        unit='shots',window_description=f'Ten-minute match-clock window {start//60000}:{start//1000%60:02d} to {clock//60000}:{clock//1000%60:02d}; same interval in prior matches',
        sample_size=len(values),historical_values=values,source_match_ids=[r.match_id for r in references],
        source_event_ids=[eid for r in references for eid in r.event_ids],current_source_event_ids=[e.event_id for e in events],
        current_minutes=clock/60000,matched_baseline=surge,
        limitations=['Shot attempts only; includes goals, saved and off-target shots. No chance-quality or expected-goals estimate.',
                     'Requires a complete ten-minute window and at least three historical matches.',
                     'Demo trigger: at least four shots, above and at least twice the historical mean. Synthetic data.'])
    name=next(t.name for t in live.teams if t.team_id==team_id)
    text=(f'{name}: {len(events)} shots in the last ten minutes, versus {baseline:g} on average in the same historical interval.' if baseline is not None
          else f'{name}: {len(events)} shots so far in this window; insufficient context for a surge comparison.')
    return comparison,text


def substitute_comparison(live, current, clock, player_id, store=None):
    sub = next((s for s in live.substitutions if s.player_on_id == player_id and s.match_clock_ms <= clock), None)
    if sub is None:
        return None
    part = next(p for p in live.participation if p.player_id == player_id)
    end = min(clock, part.end_match_clock_ms)
    events = [e for e in current if e.player_id == player_id and e.team_id == sub.team_id
              and sub.match_clock_ms <= e.match_clock_ms <= end
              and (e.type == 'pass' and e.outcome == 'completed' or e.type == 'shot')]
    passes = sum(e.type == 'pass' for e in events)
    shots = sum(e.type == 'shot' for e in events)
    goals = sum(e.type == 'shot' and e.outcome == 'goal' for e in events)
    contribution = SubstituteContribution(entered_at_match_clock_ms=sub.match_clock_ms,
        minutes_played=max(0, end-sub.match_clock_ms)/60000, completed_passes=passes, shots=shots,
        goals=goals, eligible=passes >= 3 or shots >= 1)
    if store:
        references = store.retrieve(live, player_id, int(contribution.minutes_played*60000), 'substitute')
        contribution.history_sample_size = len(references)
        contribution.history_match_ids = [r.match_id for r in references]
        contribution.history_event_ids = [eid for r in references for eid in r.event_ids]
        if len(references) >= 3:
            contribution.historical_completed_passes = mean(r.value for r in references)
            contribution.historical_shots = mean(r.shots for r in references)
            contribution.historical_goals = mean(r.goals for r in references)
    return HistoricalComparison(entity_id=player_id, metric='substitute_contribution' , current_value=passes,
        unit='completed passes since coming on', window_description=f'Since coming on at {sub.match_clock_ms//60000}:{sub.match_clock_ms//1000%60:02d}',
        sample_size=0, source_match_ids=[], source_event_ids=[], current_source_event_ids=[e.event_id for e in events],
        current_minutes=contribution.minutes_played, contribution=contribution,
        limitations=['Current-match contribution only; no historical baseline or claim that the substitution caused a change.',
                     'Goals are included in shots. Demo trigger: at least three completed passes or one shot.'])


def analyze(live: MatchFixture, history: list[HistoricalMatch], event_count: int, player_id: str, team_id: str = 'riverside', match_clock_ms: int | None = None, store=None) -> Analysis:
    if player_id not in {p.player_id for p in live.players}:
        raise ValueError('Unknown player.')
    if event_count < 0 or event_count > len(live.events):
        raise ValueError('Event count is outside the fixture.')
    # Only the received prefix is used. Unseen events cannot affect current stats.
    if match_clock_ms is not None and not 0 <= match_clock_ms <= live.duration_ms:
        raise ValueError('Match clock is outside the match duration.')
    current = unique_events(live.events if match_clock_ms is not None else live.events[:event_count], live.match_id)
    clock = match_clock_ms if match_clock_ms is not None else (current[-1].match_clock_ms if current else 0)
    current = [event for event in current if event.match_clock_ms <= clock]
    players = aggregate(current, [p.player_id for p in live.players], player=True)
    teams = aggregate(current, [t.team_id for t in live.teams], player=False)
    selected = next(p for p in players if p.entity_id == player_id)
    for row in players:
        part = next((p for p in live.participation if p.player_id == row.entity_id), None)
        row.minutes_played = max(0, min(clock, part.end_match_clock_ms) - part.start_match_clock_ms) / 60000 if part else 0
    eligible = eligible_history(history, live)
    store = store or HistoryStore(eligible)
    part = next((p for p in live.participation if p.player_id == player_id), None)
    elapsed = int(selected.minutes_played*60000)
    references = store.retrieve(live, player_id, elapsed, 'player') if part and part.start_match_clock_ms == 0 else []
    values = [r.value for r in references]
    baseline = mean(values) if len(values) >= 3 else None
    limits = ['Synthetic test fixtures between two fictional teams; no league-wide or record claims.',
              'Completed forward passes compared at equal elapsed playing time in prior starts.',
              'Latest up to 20 eligible appearances; at least three are required.',
              'Demo passing trigger: at least three completed forward passes, above and at least 1.5 times the same-time historical mean.']
    if baseline is None:
        limits.append('Insufficient comparable prior starts; showing current data only.')
    comparison = HistoricalComparison(entity_id=player_id, metric='completed_forward_passes',
        current_value=selected.completed_forward_passes, baseline_value=baseline,
        unit='completed forward passes', window_description=f'Latest up to 20 prior starts through {elapsed//60000}:{elapsed//1000%60:02d}; equal elapsed playing time',
        sample_size=len(values), historical_values=values,
        source_match_ids=[r.match_id for r in references],
        current_source_event_ids=[e.event_id for e in current if e.player_id == player_id and e.type == 'pass' and e.outcome == 'completed' and e.forward],
        source_event_ids=[eid for r in references for eid in r.event_ids],
        current_minutes=selected.minutes_played,
        matched_baseline=baseline is not None and selected.completed_forward_passes >= 3 and selected.completed_forward_passes > baseline and selected.completed_forward_passes >= baseline*1.5,
        limitations=limits)
    name = next(p.name for p in live.players if p.player_id == player_id)
    if comparison.matched_baseline:
        verb = 'matched' if comparison.current_value == baseline else 'exceeded'
        text = f'{name} has already {verb} the historical average at the same playing time of {baseline:g} completed forward passes, at {clock // 60000}:{clock // 1000 % 60:02d}.'
    else:
        text = f'{name}: {selected.completed_forward_passes} completed forward passes so far.'
    substitute = substitute_comparison(live, current, clock, player_id, store)
    if substitute is not None:
        comparison = substitute
        c = substitute.contribution
        text = f'{name} since coming on: {c.completed_passes} completed passes, {c.shots} shot{"s" if c.shots != 1 else ""}, {c.goals} goal{"s" if c.goals != 1 else ""}.'
    team_comparison, team_text = pressure_comparison(live, history, current, clock, team_id, store)
    shots,shot_text=shot_comparison(live,history,current,clock,team_id,store)
    formations = [max((f for f in live.formations if f.team_id==t.team_id and f.match_clock_ms<=clock), key=lambda f:f.match_clock_ms) for t in live.teams]
    return Analysis(match_clock_ms=clock, event_count=len(current), teams=teams, players=players,
        comparison=comparison, comparison_text=text, history_match_count=len(eligible),
        team_comparison=team_comparison, team_comparison_text=team_text,shot_comparison=shots,shot_comparison_text=shot_text, active_formations=formations,
        completed_substitutions=[s for s in live.substitutions if s.match_clock_ms<=clock])

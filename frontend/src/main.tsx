import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { Analysis, Health, HistoricalSummary, MatchFixture, PublishedGraphic, Moment } from './contracts';
import './style.css';
import { MatchPitch } from './MatchPitch';
import { HistoryChart } from './HistoryChart';
import { EditorialPanel, session } from './EditorialPanel';

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path,{signal});
  if (!response.ok) throw new Error(`API returned ${response.status}. Check the backend terminal.`);
  return response.json();
}

function clock(ms: number) {
  return `${Math.floor(ms / 60000).toString().padStart(2, '0')}:${Math.floor(ms / 1000 % 60).toString().padStart(2, '0')}`;
}

function restoredWorkspace(){
  try{
    const value=JSON.parse(localStorage.getItem('broadcast-copilot-workspace') ?? '{}');
    return {clock:typeof value.clock==='number' && Number.isFinite(value.clock) ? Math.max(0,Math.min(5400000,value.clock)) : 0,
      mode:value.mode==='team' ? 'team' as const : 'player' as const,
      player:typeof value.player==='string' ? value.player : 'n-8',team:typeof value.team==='string' ? value.team : 'riverside',
      metric:value.metric==='shots' ? 'shots' as const : 'pressure_events' as const};
  }catch{return {clock:0,mode:'player' as const,player:'n-8',team:'riverside',metric:'pressure_events' as const};}
}

function App() {
  const [restored]=useState(restoredWorkspace);
  const [fixture, setFixture] = useState<MatchFixture>();
  const [health, setHealth] = useState<Health>();
  const [error, setError] = useState('');
  const [matchClock, setMatchClock] = useState(restored.clock);
  const [speed, setSpeed] = useState(60);
  const [playing, setPlaying] = useState(false);
  const [probeMessage, setProbeMessage] = useState('');
  const [probing, setProbing] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis>();
  const [history, setHistory] = useState<HistoricalSummary[]>([]);
  const [playerFocus, setPlayerFocus] = useState(restored.player);
  const [focusMode, setFocusMode] = useState<'player' | 'team'>(restored.mode);
  const [teamMetric,setTeamMetric]=useState<'pressure_events' | 'shots'>(restored.metric);
  const [teamFocus, setTeamFocus] = useState(restored.team);
  const [analysisError, setAnalysisError] = useState('');
  const [moments, setMoments] = useState<Moment[]>([]);
  const [momentsUnavailable, setMomentsUnavailable] = useState(false);
  const [sessionId] = useState(session);
  const [published, setPublished] = useState<PublishedGraphic | null>(null);
  useEffect(() => {
    Promise.all([get<MatchFixture>('/api/fixture'), get<Health>('/api/health'), get<HistoricalSummary[]>('/api/history')])
      .then(([match, status, past]) => { setFixture(match); setHealth(status); setHistory(past); })
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!playing || !fixture) return;
    let previous = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const elapsed = now - previous; previous = now;
      setMatchClock(value => Math.min(fixture.duration_ms, value + elapsed * speed));
    }, 250);
    return () => window.clearInterval(timer);
  }, [playing, speed, fixture]);
  useEffect(() => {
    if (fixture && matchClock >= fixture.duration_ms) setPlaying(false);
  }, [matchClock, fixture]);
  const snapshotClock = Math.floor(matchClock / 1000) * 1000;
  useEffect(()=>{
    localStorage.setItem('broadcast-copilot-workspace',JSON.stringify({clock:snapshotClock,mode:focusMode,player:playerFocus,team:teamFocus,metric:teamMetric}));
  },[snapshotClock,focusMode,playerFocus,teamFocus,teamMetric]);
  useEffect(() => {
    if (!fixture) return;
    const controller = new AbortController();
    if (!playing) setAnalysis(undefined);
    setAnalysisError('');
    fetch(`/api/analysis?match_clock_ms=${snapshotClock}&player_id=${encodeURIComponent(playerFocus)}&team_id=${encodeURIComponent(teamFocus)}`, {signal: controller.signal})
      .then(async response => {if (!response.ok) throw new Error('Could not calculate this comparison.'); return response.json() as Promise<Analysis>;})
      .then(value => {if (!controller.signal.aborted) setAnalysis(value);})
      .catch((e: Error) => {if (!controller.signal.aborted) setAnalysisError(e.message);});
    return () => controller.abort();
  }, [snapshotClock, playerFocus, teamFocus, fixture, playing]);

  useEffect(() => {
    if (!fixture) return;
    const controller = new AbortController();
    get<Moment[]>(`/api/moments?match_clock_ms=${snapshotClock}&session_id=${sessionId}`,controller.signal)
      .then(value => {if (!controller.signal.aborted) {setMoments(value);setMomentsUnavailable(false);}})
      .catch(() => {if (!controller.signal.aborted) {setMoments([]);setMomentsUnavailable(true);}});
    return () => controller.abort();
  },[snapshotClock,fixture,sessionId,published?.draft_id]);

  async function checkFoundry() {
    setProbing(true); setProbeMessage('Checking deployment…');
    try {
      const response = await fetch('/api/foundry/probe', { method: 'POST' });
      const result = await response.json();
      setProbeMessage(response.ok ? result.message : result.detail);
    } catch { setProbeMessage('Connection check failed. Check the backend terminal.'); }
    finally { setProbing(false); }
  }

  const events = fixture?.events.filter(event => event.match_clock_ms <= matchClock) ?? [];
  const playerName = (id?: string | null) => fixture?.players.find(p => p.player_id === id)?.name ?? 'Team';
  const count = events.length;
  const ended = !!fixture && matchClock >= fixture.duration_ms;
  // Preserve cards during refreshes, but never show a future/stale suggestion
  // after seeking or leave suggestions visible once the match has ended.
  const visibleMoments=ended ? [] : moments.filter(moment=>moment.match_clock_ms<=snapshotClock && snapshotClock-moment.match_clock_ms<=120000);
  const fresh = analysis?.match_clock_ms === snapshotClock;
  const isTeam = focusMode === 'team';
  const isShots=isTeam && teamMetric==='shots';
  const comparison = isTeam ? (isShots ? analysis?.shot_comparison : analysis?.team_comparison) : analysis?.comparison;
  const stats = isTeam ? analysis?.teams.find(t => t.entity_id === teamFocus) : analysis?.players.find(p => p.entity_id === playerFocus);
  const focusName = isTeam ? fixture?.teams.find(t => t.team_id === teamFocus)?.name : playerName(playerFocus);
  return <main>
    <header><div className="brand"><span className="brand-mark">BC</span><div><h1>Broadcast Copilot</h1><p>Producer workspace</p></div></div><span className="badge">Synthetic demo</span></header>
    {error && <div className="error" role="alert">{error}</div>}
    <section className="matchbar" aria-label="Match controls">
      <div><h2>{fixture?.label ?? 'Loading match…'}</h2><p>{matchClock < 2700000 ? 'First half' : ended ? 'Full time' : 'Second half'} · {analysis?.teams.map(team => team.goals).join(' – ') ?? '0 – 0'}</p></div>
      <div className="playback"><strong className="clock">{clock(matchClock)}</strong>
        <button className="primary" disabled={!fixture || ended} onClick={() => setPlaying(!playing)}>{playing ? 'Pause' : ended ? 'Full time' : 'Play match'}</button>
</div>
    </section>
    <section className="panel moments-panel" aria-label="Suggested moments"><div className="panel-heading"><h2>Suggested moments</h2><span className="muted">Select a moment to review</span></div><div className="moment-list">{visibleMoments.length ? visibleMoments.map(moment=><button key={`${moment.mode}-${moment.entity_id}-${moment.metric}`} onClick={()=>{setPlaying(false);setMatchClock(moment.match_clock_ms);setFocusMode(moment.mode);if(moment.mode==='team'){setTeamFocus(moment.entity_id);setTeamMetric(moment.metric==='shots' ? 'shots' : 'pressure_events');}else setPlayerFocus(moment.entity_id);}}><b>{moment.entity_name} · {moment.label}</b><span>{moment.detail}</span></button>) : <p>{momentsUnavailable ? 'Moment detection unavailable. You can still select players and teams manually.' : ended ? 'Full time. No new moments.' : 'Watching play for useful moments.'}</p>}</div></section>
    <details className="manual-focus"><summary>Choose a player or team</summary>    <div className="focusbar"><div className="focus-tabs" role="group" aria-label="Comparison mode"><button aria-pressed={!isTeam} onClick={() => setFocusMode('player')}>Player</button><button aria-pressed={isTeam} onClick={() => setFocusMode('team')}>Team</button></div>{isTeam ? <><label htmlFor="team-focus">Team focus</label><select id="team-focus" value={teamFocus} onChange={e => setTeamFocus(e.target.value)}>{fixture?.teams.map(team => <option key={team.team_id} value={team.team_id}>{team.name}</option>)}</select><label htmlFor="team-metric">Statistic</label><select id="team-metric" value={teamMetric} onChange={e=>setTeamMetric(e.target.value as 'pressure_events' | 'shots')}><option value="pressure_events">Pressure · 5 minutes</option><option value="shots">Shots · 10 minutes</option></select></> : <><label htmlFor="player-focus">Player focus</label><select id="player-focus" value={playerFocus} onChange={e => setPlayerFocus(e.target.value)}>{fixture?.players.map(player => <option key={player.player_id} value={player.player_id}>{player.name} · {fixture.teams.find(t => t.team_id === player.team_id)?.name}</option>)}</select></>}</div>
</details>
    <div className="workspace">
      <section className="panel"><div className="panel-heading"><h2>Review moment</h2><span className="muted">{!fresh ? 'Updating…' : comparison?.contribution ? (comparison.contribution.eligible ? 'Contribution ready' : 'Watching contributions') : comparison?.matched_baseline ? 'Ready to review' : 'Watching play'}</span></div>
        {snapshotClock===0 ? <div className="empty"><p>Play the match, then select a suggested moment to review.</p></div> : analysisError ? <p role="alert" className="error">{analysisError}</p> : (!comparison || comparison.entity_id !== (isTeam ? teamFocus : playerFocus)) ? <div className="empty"><p>Calculating comparison…</p></div> : comparison.contribution ? <div className="comparison-card">
          <span className="eyebrow">SUBSTITUTE CONTRIBUTION</span><h3>{focusName}</h3>
          <div className="mini-stats"><span>Completed passes <b>{comparison.contribution.completed_passes}</b></span><span>Shots <b>{comparison.contribution.shots}</b></span><span>Goals <b>{comparison.contribution.goals}</b></span></div>
          <p className="comparison-caveat">Came on at {clock(comparison.contribution.entered_at_match_clock_ms)} · {comparison.contribution.minutes_played.toFixed(1)} minutes played. Goals are included in shots.</p>
          <details className="evidence"><summary>View supporting data</summary><div><p>{comparison.window_description}</p><p>{comparison.current_source_event_ids?.join(', ') || 'No contributions yet.'}</p>          {comparison.contribution.historical_completed_passes!=null && <p className="comparison-caveat">Prior substitute appearances at equal playing time: {comparison.contribution.history_sample_size}. Average {comparison.contribution.historical_completed_passes.toFixed(1)} completed passes, {comparison.contribution.historical_shots?.toFixed(1)} shots, {comparison.contribution.historical_goals?.toFixed(1)} goals.</p>}<p>Prior matches: {comparison.contribution.history_match_ids?.join(', ') || 'None available'}</p><p>Current-match contributions; no causal impact is inferred.</p></div></details>

        </div> : <div className="comparison-card">
          <span className="eyebrow">{isTeam ? (isShots ? (comparison.matched_baseline ? 'SHOT SURGE' : 'SHOT ATTEMPTS') : (comparison.matched_baseline ? 'PRESSURE SURGE' : 'PRESSURE EVENTS')) : (comparison.matched_baseline ? 'UNUSUAL INVOLVEMENT' : 'COMPLETED FORWARD PASSES')}</span>
          <h3>{focusName}</h3>
          <div className="comparison-values"><div><strong>{comparison.current_value}</strong><span>{isTeam ? (analysis!.match_clock_ms >= (isShots ? 600000 : 300000) ? (isShots ? 'Last ten minutes' : 'Last five minutes') : 'Partial window') : 'Current'} · {clock(analysis!.match_clock_ms)}</span></div><div><strong>{comparison.baseline_value == null ? '—' : Number(comparison.baseline_value.toFixed(2))}</strong><span>{isTeam ? 'Same-window average' : 'Average at same playing time'} · {comparison.sample_size} matches</span></div></div>
          <details className="evidence" key={`${focusMode}-${comparison.entity_id}`}><summary>View supporting data</summary><div><p>{comparison.window_description}</p><ul>{(comparison.historical_values ?? []).map((value, i) => <li key={comparison.source_match_ids[i]}><code>{comparison.source_match_ids[i]}</code><b>{value} {isTeam ? (isShots ? 'shots · same window' : 'pressure events · same window') : 'forward passes · same playing time'}</b></li>)}</ul><p>Live evidence: {comparison.current_source_event_ids?.join(', ') || 'No matching events yet'}</p><p>{comparison.source_event_ids.length} historical source events. Match summaries below show calculated totals.</p>{comparison.limitations.map(limit => <p className="comparison-caveat" key={limit}>{limit}</p>)}</div></details>
        </div>}
        <EditorialPanel clock={snapshotClock} mode={focusMode} entityId={isTeam ? teamFocus : playerFocus} eligible={!!(fresh && (comparison?.contribution?.eligible ?? comparison?.matched_baseline))} contribution={!!comparison?.contribution} teamMetric={teamMetric} onPause={() => setPlaying(false)} onPublished={setPublished}/>
      </section>
      <section className="panel audience-panel"><div className="panel-heading"><h2>Audience preview</h2><span className="muted">{published ? 'Published' : 'Not published'}</span></div>
        <div className="stage" data-graphic-side={published?.team_id === fixture?.teams[1]?.team_id ? 'right' : 'left'}><MatchPitch fixture={fixture} clock={snapshotClock} playing={playing} speed={speed}/>{published && snapshotClock>=published.snapshot_clock_ms && snapshotClock<published.expires_at_match_clock_ms && <div className={`broadcast-graphic template-${published.template_id} audience-${published.audience}`} data-team={published.team_id} data-side={published.team_id === fixture?.teams[1]?.team_id ? 'right' : 'left'} aria-label={`Graphic about ${published.entity_name}`}><div className="graphic-subject"><span className="graphic-subject-type">{published.entity_type==='player' ? `PLAYER · ${published.team_name}` : 'TEAM'}</span><h3>{published.entity_name}</h3></div><div className="graphic-copy">{published.show_headline && <h4>{published.title}</h4>}<p>{published.body}</p><HistoryChart visual={published.visual}/>{published.audience==='analyst' && (!published.visual || published.visual.kind==='numbers') && published.baseline_value!=null && <div className="graphic-numbers"><strong>{published.current_value}<small>current</small></strong><strong>{published.baseline_value}<small>usual average</small></strong></div>}<span className="graphic-timestamp">{clock(published.snapshot_clock_ms)}</span></div></div>}</div>
        {!published && <p className="preview-note">Approve a draft to show it here.</p>}
      </section>
    </div>
    <details className="panel technical-tools"><summary>Demo &amp; technical tools</summary><div className="technical-tools-content">
    <div className="timeline-controls"><label htmlFor="speed">Playback speed</label><select id="speed" value={speed} onChange={e => setSpeed(Number(e.target.value))}><option value={1}>1× real time</option><option value={30}>30× · 3 minutes</option><option value={60}>60× · 90 seconds</option><option value={120}>120× · 45 seconds</option></select><label htmlFor="seek">Match timeline</label><input id="seek" aria-label="Match timeline" type="range" min={0} max={fixture?.duration_ms ?? 5400000} step={1000} value={snapshotClock} onChange={e => {setPlaying(false); setMatchClock(Number(e.target.value));}}/><span>90:00</span></div>
    <details className="panel scenario-controls"><summary>Demo moments</summary><div><div className="scenario-buttons">{fixture?.scenarios?.map(scenario => <button key={scenario.label} onClick={() => {setPlaying(false);setMatchClock(scenario.match_clock_ms); if(scenario.label==='Shot surge'){setFocusMode('team');setTeamFocus('northbridge');setTeamMetric('shots');} if(scenario.label==='Pressure surge'){setFocusMode('team');setTeamFocus('riverside');setTeamMetric('pressure_events');} if(scenario.label==='Player involvement'){setFocusMode('player');setPlayerFocus('n-8');} const scorer=fixture.events.find(e=>e.match_clock_ms===scenario.match_clock_ms && e.outcome==='goal' && fixture.substitutions.some(sub=>sub.player_on_id===e.player_id && sub.match_clock_ms<=scenario.match_clock_ms)); if(scorer?.player_id){setFocusMode('player');setPlayerFocus(scorer.player_id);}}}>{scenario.label} · {clock(scenario.match_clock_ms)}</button>)}</div><p>Formations: {analysis?.active_formations.map(formation => `${fixture?.teams.find(t=>t.team_id===formation.team_id)?.name} ${formation.shape}`).join(' · ')}</p><p>Substitutions so far: {analysis?.completed_substitutions.length ?? 0}</p>{analysis?.completed_substitutions.map(sub => <p key={`${sub.team_id}-${sub.match_clock_ms}`}><b>{clock(sub.match_clock_ms)}</b> · {fixture?.players.find(p=>p.player_id===sub.player_off_id)?.name} off → {fixture?.players.find(p=>p.player_id===sub.player_on_id)?.name} on</p>)}<p>Before/after changes are descriptive evidence, not proof of substitution impact.</p></div></details>
<div className="scenario-buttons">        <button disabled={!fixture || playing || ended} onClick={() => { const next = fixture?.events.find(event => event.match_clock_ms > matchClock); setMatchClock(next?.match_clock_ms ?? fixture?.duration_ms ?? 0); }}>Next event</button>
        <button disabled={!fixture} onClick={() => {setPlaying(false); setMatchClock(0);}}>Reset</button></div>    <details className="panel event-panel"><summary>Event log</summary><div><div className="panel-heading"><h2>Incoming events</h2><span className="muted">{count} / {fixture?.events.length ?? 0} events</span></div>
      {!events.length ? <p className="event-empty">Play the match, seek on the timeline, or step to the next event.</p> : <ol className="events">{events.slice(-12).reverse().map(event => <li key={event.event_id}><time>{clock(event.match_clock_ms)}</time><strong>{playerName(event.player_id)}</strong><span>{event.type.replace('_', ' ')} · {event.outcome.replace('_', ' ')}</span><code>{event.event_id}</code></li>)}</ol>}
    </div></details>
    <details className="panel history-panel"><summary>Historical dataset <span>{history.length} synthetic matches per team</span></summary><div><p>Twenty synthetic test fixtures per team, with starters, substitutes, and actual participation minutes. All finished before this live fixture.</p><div className="history-scroll"><table><thead><tr><th>Match</th><th>Date</th><th>{isTeam ? (isShots ? 'Shots · full match' : 'Pressure events · full match') : 'Player minutes'}</th><th>Forward passes</th><th>Completed / attempted</th></tr></thead><tbody>{history.map(match => {const row=isTeam ? match.teams.find(t => t.entity_id===teamFocus) : match.players.find(p => p.entity_id===playerFocus); return <tr key={match.match_id}><td>{match.match_id}</td><td>{match.kickoff_at.slice(0,10)}</td><td>{isTeam ? (isShots ? row?.shots : row?.pressure_events) : (row?.minutes_played ?? '—')}</td><td>{row?.completed_forward_passes ?? '—'}</td><td>{row?.completed_passes} / {row?.attempted_passes}</td></tr>;})}</tbody></table></div><p>These repeated fixtures between two fictional teams are a seeded test library, not a realistic league schedule. Eleven players are on the field per team; bench appearances and formation changes are timestamped. No tracking or causal claims.</p></div></details>
    {!health?.public_demo && <details className="panel diagnostics"><summary>Setup and connection status <span>{health?.foundry_configured ? 'Foundry configured' : 'Foundry setup needed'}</span></summary><div><p>{health?.foundry_message ?? 'Waiting for backend connection.'}</p><p>After creating a Foundry deployment, add its v1 endpoint, deployment name, and API key to your local <code>.env</code> file, then restart the backend. Keys stay on the server.</p><button disabled={!health?.foundry_configured || probing} onClick={checkFoundry}>{probing ? 'Checking…' : 'Check Foundry connection'}</button><p role="status">{probeMessage}</p></div></details>}
    </div></details>

  </main>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);

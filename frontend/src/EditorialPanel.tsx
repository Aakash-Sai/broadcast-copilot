import { useEffect, useRef, useState } from 'react';
import { HistoryChart } from './HistoryChart';
import type { DraftResult, EditorialState, PublishedGraphic, GraphicVisual, GraphicDraft } from './contracts';

type Props = {clock: number; mode: 'player' | 'team'; entityId: string; eligible: boolean; contribution: boolean; teamMetric: 'pressure_events' | 'shots';
  onPause: () => void; onPublished: (value: PublishedGraphic | null) => void;};
const emptyState: EditorialState = {drafts: [], published: null, recent_actions: []};

export function session() {
  const key = 'broadcast-copilot-session';
  let value = localStorage.getItem(key) ?? sessionStorage.getItem(key);
  if (!value) value = crypto.randomUUID();
  localStorage.setItem(key, value);
  return value;
}

export function EditorialPanel({clock, mode, entityId, eligible, contribution, teamMetric, onPause, onPublished}: Props) {
  const [sessionId] = useState(session);
  const [state, setState] = useState<EditorialState>(emptyState);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [savedWork,setSavedWork]=useState<GraphicDraft[]>([]);
  const [historyOpen,setHistoryOpen]=useState(false);
  const [historyError,setHistoryError]=useState('');
  const [audience, setAudience] = useState<'casual' | 'analyst'>('casual');
  const [title, setTitle] = useState('');
  const [casualBody,setCasualBody]=useState('');
  const [visualType,setVisualType]=useState<GraphicVisual['kind']>('numbers');
  const [analystBody,setAnalystBody]=useState('');
  const body=audience==='casual' ? casualBody : analystBody;
  const setBody=(value: string)=>audience==='casual' ? setCasualBody(value) : setAnalystBody(value);
  const latest = useRef({clock,mode,entityId,teamMetric});
  latest.current = {clock,mode,entityId,teamMetric};
  const draft = state.drafts.filter(item => item.mode === mode && item.entity_id === entityId && (mode!=='team' || item.comparison.metric===teamMetric)).at(-1);
  const selectedVisual=draft?.visual_options?.find(item=>item.kind===visualType) ?? draft?.visual;
  useEffect(() => {
    if (!draft) {setTitle('');setCasualBody('');setAnalystBody('');return;}
    setTitle(draft.title);
    setVisualType(draft.visual?.kind ?? 'numbers');
    setCasualBody(draft.casual_text);
    setAnalystBody(draft.analyst_text);
  }, [draft?.draft_id]);
  useEffect(() => {
    if (draft?.status==='expired') setMessage('The supporting facts changed. Generate a fresh draft.');
    if (draft?.status==='superseded') setMessage('This draft has been superseded.');
  }, [draft?.status, draft?.draft_id]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/editorial/state?session_id=${sessionId}&match_clock_ms=${clock}`,{signal:controller.signal})
      .then(async response => {if (!response.ok) throw new Error(); return response.json() as Promise<EditorialState>;})
      .then(value => {if (!controller.signal.aborted) {setState(value); onPublished(value.published);}})
      .catch(() => {if (!controller.signal.aborted) {onPublished(null); setMessage('Editorial state unavailable. Audience preview cleared.');}});
    return () => controller.abort();
  }, [clock, sessionId, onPublished]);

  useEffect(()=>{
    if(!historyOpen) return;
    const controller=new AbortController();
    fetch(`/api/editorial/history?session_id=${sessionId}`,{signal:controller.signal})
      .then(async response=>{if(!response.ok) throw new Error();return response.json() as Promise<GraphicDraft[]>;})
      .then(rows=>{setSavedWork(rows.reverse());setHistoryError('');})
      .catch(()=>{if(!controller.signal.aborted) setHistoryError('Saved work is unavailable.');});
    return ()=>controller.abort();
  },[historyOpen,sessionId,state]);

  async function generate() {
    onPause(); setLoading(true); setMessage('Preparing draft…');
    const requested = {session_id:sessionId,match_clock_ms:clock,mode,entity_id:entityId,team_metric:teamMetric};
    try {
      const response = await fetch('/api/editorial/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(requested)});
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not generate a draft.');
      const current = latest.current;
      if (current.clock!==clock || current.mode!==mode || current.entityId!==entityId || current.teamMetric!==teamMetric) {
        setMessage('The selection or timeline changed during generation. Return to that snapshot or generate here.'); return;
      }
      const value = result as DraftResult;
      if (value.draft) setState(old => ({...old,drafts:[...old.drafts.filter(d => d.draft_id!==value.draft!.draft_id),value.draft!].slice(-3)}));
      setMessage(value.draft ? (value.draft.source==='factual_fallback' ? 'AI wording could not be verified. A factual draft is ready to review.' : 'Draft ready to review.') : value.message);
    } catch (error) {setMessage(error instanceof Error ? error.message : 'Draft generation failed.');}
    finally {setLoading(false);}
  }

  async function act(action: 'approve' | 'dismiss' | 'clear' | 'save') {
    setBusy(true);
    try {
      const response=await fetch('/api/editorial/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        session_id:sessionId,match_clock_ms:clock,action,draft_id:draft?.draft_id ?? null,title,body,audience,visual_type:visualType,
      })});
      const value=await response.json();
      if (!response.ok) throw new Error(typeof value.detail==='string' ? value.detail : 'Editorial action failed.');
      setState(value); onPublished(value.published);
      setMessage(action==='approve' ? 'Graphic published.' : action==='dismiss' ? 'Draft dismissed.' : action==='save' ? 'Draft saved.' : 'Graphic cleared.');
    } catch(error) {setMessage(error instanceof Error ? error.message : 'Editorial action failed.');}
    finally {setBusy(false);}
  }
  const reviewable=draft?.status==='proposed' && clock>=draft.snapshot_clock_ms && clock<draft.expires_at_match_clock_ms;
  if(clock===0) return null;
  return <div className="editorial-panel">
    <div className="editorial-heading"><h3>Graphic draft</h3><button className="primary" disabled={!eligible || loading || busy || clock>=5400000} onClick={generate}>{loading ? 'Generating…' : 'Generate draft'}</button></div>
    {!eligible && <p className="editorial-hint">Choose a suggested moment, or select a player or team.</p>}
    {message && <p className="editorial-message" role="status">{message}</p>}
    {draft && <div className="draft-editor">
      <div className="draft-meta"><span>{draft.source==='factual_fallback' ? 'Factual draft' : draft.status==='approved' ? 'Published' : draft.status==='proposed' ? 'Ready to review' : draft.status}</span></div>
      <details className="draft-review" open={reviewable}><summary>{reviewable ? 'Review and edit draft' : 'View reviewed draft'}</summary>
      <label htmlFor="draft-audience">Audience wording</label><select id="draft-audience" value={audience} disabled={!reviewable || busy} onChange={e => setAudience(e.target.value as 'casual' | 'analyst')}><option value="casual">Casual</option><option value="analyst">Analyst</option></select>
      <label htmlFor="draft-title">Graphic headline</label><input id="draft-title" value={title} disabled={!reviewable || busy} maxLength={selectedVisual?.kind && selectedVisual.kind!=='numbers' ? 80 : 100} onChange={e => setTitle(e.target.value)}/>
      <label htmlFor="draft-body">Graphic wording</label><textarea id="draft-body" value={body} disabled={!reviewable || busy} maxLength={audience==='casual' ? 120 : selectedVisual?.kind && selectedVisual.kind!=='numbers' ? 140 : 500} rows={audience==='casual' ? 2 : 4} onChange={e => setBody(e.target.value)}/>
      {audience==='casual' && <p className="editorial-hint">Up to 20 words. Keep statistics tied to the supporting data.</p>}
      {(draft.visual_options?.length ?? 0)>1 && <><label htmlFor="graphic-style">Graphic style</label><select id="graphic-style" value={visualType} disabled={!reviewable || busy} onChange={e=>setVisualType(e.target.value as GraphicVisual['kind'])}>{(draft.visual_options ?? []).map(option=><option key={option.kind} value={option.kind}>{option.kind==='numbers' ? 'Numbers only' : option.kind==='historical_bars' ? 'Recent matches · bars' : 'Recent matches · dots'}</option>)}</select></>}
      {selectedVisual && selectedVisual.kind!=='numbers' && <div className="draft-chart-preview"><HistoryChart visual={selectedVisual}/></div>}
      <p className="why-now"><b>Why now</b> {draft.rationale}</p>

      <div className="editorial-actions"><button className="primary" disabled={!reviewable || busy} onClick={() => act('approve')}>Approve and publish</button><button disabled={!reviewable || busy} onClick={() => act('save')}>Save draft</button><button disabled={!reviewable || busy} onClick={() => act('dismiss')}>Dismiss</button></div>
      <details><summary>Source details</summary><p>{draft.message}</p><p>Draft source: {draft.source} · {draft.status} · {(draft.latency_ms/1000).toFixed(1)}s</p>{draft.diagnostic && <p>Validation: {draft.diagnostic}</p>}<p>Snapshot: {(draft.snapshot_clock_ms/60000).toFixed(2)} min · expires after at most two match minutes.</p><p>Cited events: {draft.cited_event_ids.join(', ')}</p><p>Input tokens: {draft.input_tokens} · Output tokens: {draft.output_tokens}</p><p>Evidence window: {draft.comparison.window_description}</p><p>Historical matches: {(draft.comparison.contribution?.history_match_ids ?? draft.comparison.source_match_ids).join(', ') || 'Insufficient history'}</p><p>Recent actions: {state.recent_actions.join(' · ') || 'None yet'}</p></details>
      </details>
    </div>}
    {state.published && <button className="clear-graphic" disabled={busy} onClick={() => act('clear')}>Clear audience graphic</button>}
    <details className="saved-work" onToggle={event=>setHistoryOpen(event.currentTarget.open)}><summary>Saved work and history</summary>
      <p>Latest 50 drafts. Saved work stays in history after its evidence expires.</p>
      {historyError && <p role="status">{historyError}</p>}
      <ul>{savedWork.map(item=><li key={item.draft_id}><b>{item.title}</b><span>{Math.floor(item.snapshot_clock_ms/60000)}:{String(item.snapshot_clock_ms/1000%60).padStart(2,'0')} · {item.status}</span></li>)}</ul>
      <a href={`/api/editorial/audit?session_id=${sessionId}&limit=1000`} download>Download recent audit history</a>
    </details>
  </div>;
}

"""Evidence-bound drafts and a local producer approval workflow.

Schema/number/source checks are not a general semantic truth verifier. Human review
is required. Model words never calculate or override the comparison values.
"""
import asyncio
import hashlib
import json
import re
import time
from copy import deepcopy
from collections import OrderedDict, deque
from contextlib import contextmanager
from uuid import uuid4
import httpx
from pydantic import BaseModel, ConfigDict
from backend.contracts import (DraftRequest, DraftResult, EditorialAction, EditorialState,
    GraphicDraft, HistoricalComparison, PublishedGraphic)
from backend.foundry import generate_graphic
from backend.statistics import analyze
from backend.charts import build_visual,visual_types,model_visual_types


class ModelDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title_template: str
    casual_template: str
    analyst_template: str
    reason_template: str
    template_id: str
    event_ids: list[str]
    visual_type: str = 'numbers'


SCHEMA = ModelDraft.model_json_schema()
SCHEMA['required'].append('visual_type')
SCHEMA['properties']['visual_type'].pop('default',None)
SCHEMA['properties']['template_id'] = {'type': 'string', 'enum': ['comparison', 'trend', 'spotlight']}
ANALYST_TEMPLATES = [
    '{{entity}}: {{current}} {{unit}} versus {{baseline}} for {{scope}}, across {{sample}} prior matches.',
    '{{entity}} has {{current}} {{unit}}; {{baseline}} is {{scope}} across {{sample}} prior matches.',
    '{{entity}}: {{current}} {{unit}} now, compared with {{baseline}} for {{scope}}. Sample: {{sample}} prior matches.',
]
SCHEMA['properties']['analyst_template']['enum'] = ANALYST_TEMPLATES
SCHEMA['properties']['casual_template']['enum'] = ['{{plain_body}}']
SAFE_REASON = 'The current count is above the historical average for this comparison.'


class DraftValidationError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)
PLACEHOLDER = re.compile(r'\{\{([a-z_]+)\}\}')
NUMBER = re.compile(r'\d+(?:\.\d+)?')
UNSUPPORTED = re.compile(r'\b(xg|chance quality|shot quality|on target|caus\w*|led to|proves?|record\w*|best|worst|dominat\w*|winning|wins?|goals?|tackles?|formation\w*|tactic\w*|speed|intensity|percent\w*|ratio\w*|rates?|per minute|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|first|second|third|double|triple|twice|he|she|his|her|him|hers)\b', re.I)


def casual_wording(comparison):
    """Short house wording keeps casual graphics readable and tied to counted events."""
    if comparison.contribution:
        c=comparison.contribution
        return f'Since coming on: {c.completed_passes} completed passes, {c.shots} shot{ "s" if c.shots!=1 else ""}, {c.goals} goal{ "s" if c.goals!=1 else ""}.'
    current=f'{comparison.current_value:g}' 
    if comparison.metric=='shots':
        return f'{current} shots in 10 minutes. More than usual.'
    if comparison.metric=='pressure_events':
        return f'{current} presses in 5 minutes. More than usual.'
    relation='above' if comparison.current_value>comparison.baseline_value else 'matches'
    return (f'{current} forward passes completed. More than usual at this point.' if relation=='above'
            else f'{current} forward passes completed. As many as usual at this point.')


def substitutions(comparison, name, clock):
    if comparison.contribution:
        return {'entity':name,'plain_body':casual_wording(comparison)}
    return {'entity': name, 'current': f'{comparison.current_value:g}',
            'plain_body':casual_wording(comparison),
            'window_minutes':'10' if comparison.metric=='shots' else '5' if comparison.metric=='pressure_events' else '',
            'baseline': f'{comparison.baseline_value:g}', 'sample': str(comparison.sample_size),
            'clock': f'{clock // 60000}:{clock // 1000 % 60:02d}', 'unit': comparison.unit,
            'window': (f'the first {comparison.current_minutes:g} minutes of playing time' if comparison.metric=='completed_forward_passes'
                       else f'{"ten" if comparison.metric=="shots" else "five"}-minute window ending at {clock // 60000}:{clock // 1000 % 60:02d}'),
            'scope': ('the historical average at the same playing time' if comparison.metric=='completed_forward_passes'
                      else f'the historical average in the same {"ten" if comparison.metric=="shots" else "five"}-minute match window')}


def validate_templates(raw, comparison, name, clock):
    draft = ModelDraft.model_validate(raw)
    if draft.visual_type not in model_visual_types(comparison):
        raise DraftValidationError('visual_type','Chart choice is not supported by the supplied data.')
    allowed = ['comparison', 'spotlight'] if comparison.metric=='completed_forward_passes' else ['comparison', 'trend']
    if draft.template_id not in allowed:
        raise DraftValidationError('template_id','Unsupported template.')
    if not 1 <= len(draft.event_ids) <= 3 or not set(draft.event_ids).issubset(set(comparison.current_source_event_ids)):
        raise DraftValidationError('event_ids','Invalid source IDs.')
    values = substitutions(comparison, name, clock)
    rendered = []
    for index, text in enumerate([draft.title_template, draft.casual_template, draft.analyst_template, draft.reason_template]):
        field=['title_template','casual_template','analyst_template','reason_template'][index]
        keys = set(PLACEHOLDER.findall(text))
        required = {'entity'} if index==0 else {'plain_body'} if index==1 else {'entity','current','baseline','scope','unit'} if index==2 else set()
        if index==1 and text.strip()!='{{plain_body}}':
            raise DraftValidationError(field,'Casual wording must use the short evidence-based phrase.')
        if index==2:
            required.add('sample')
        remaining = PLACEHOLDER.sub('', text)
        if (not required.issubset(keys) or not keys.issubset(values) or NUMBER.search(remaining)
                or UNSUPPORTED.search(remaining) or any(c in remaining for c in '{}%<>')
                or not text.strip() or len(text)>600):
            raise DraftValidationError(field,'Unsupported or incomplete claim.')
        rendered.append(PLACEHOLDER.sub(lambda m:values[m.group(1)],text))
    if len(rendered[0])>100 or any(len(text)>500 for text in rendered[1:]):
        raise ValueError('Graphic is too long.')
    return draft, rendered


def check_edit(title, body, draft):
    if not title.strip() or not body.strip():
        raise ValueError('Provide a headline and graphic wording.')
    if draft.comparison.contribution:
        c=draft.comparison.contribution
        values=[str(c.completed_passes),str(c.shots),str(c.goals),str(c.minutes_played),
                str(c.entered_at_match_clock_ms//60000),f'{c.entered_at_match_clock_ms//1000%60:02d}',
                str(c.history_sample_size)]
        for value in [c.historical_completed_passes,c.historical_shots,c.historical_goals]:
            if value is not None:
                values.extend([str(value),f'{value:.1f}'])
        allowed={float(token) for value in values for token in NUMBER.findall(value)}
        text=(title+' '+body).replace(draft.entity_name,'')
        # Goals are supported for contribution cards; causal and record claims remain unsupported.
        checked=re.sub(r'\bgoals?\b','',text,flags=re.I)
        if any(float(token) not in allowed for token in NUMBER.findall(text)) or UNSUPPORTED.search(checked) or re.search(r'\bforward\b',text,re.I) or any(ch in text for ch in '{}<>%'):
            raise ValueError('Edit must use the calculated counts without unsupported claims.')
        historical=bool(re.search(r'\b(average|averages|historical|prior)\b',text,re.I))
        metrics={'passes':(c.completed_passes,c.historical_completed_passes),
                 'shot':(c.shots,c.historical_shots),'goal':(c.goals,c.historical_goals)}
        for number,metric in re.findall(r'(\d+(?:\.\d+)?)\s+(?:completed\s+)?(passes|pass|shots?|goals?)\b',text,re.I):
            key='passes' if metric.lower().startswith('pass') else metric.lower().rstrip('s')
            current,previous=metrics[key]
            supported={float(current)}
            if historical and previous is not None:
                supported.update([float(previous),float(f'{previous:.1f}')])
            if float(number) not in supported:
                raise ValueError('Edit must keep each statistic tied to its calculated counts.')
        return
    values = substitutions(draft.comparison,draft.entity_name,draft.snapshot_clock_ms)
    allowed = {float(token) for value in values.values() for token in NUMBER.findall(value)}
    text = (title+' '+body).replace(draft.entity_name,'').replace(values['scope'],'').replace(values['window'],'')
    if any(float(token) not in allowed for token in NUMBER.findall(text)) or UNSUPPORTED.search(text) or any(c in text for c in '{}<>%'):
        raise ValueError('Edit contains an unsupported number or claim. Keep wording tied to the comparison.')


class EditorialService:
    def __init__(self, store=None, repository=None, public_demo=False):
        self.store=store
        self.repository=repository
        self.public_demo=public_demo
        if public_demo and not repository:
            raise ValueError('Public demo mode requires durable storage for AI limits.')
        self.namespace=None
        self.loaded_sessions=set()
        self.pending_events=[]
        self.evicted=[]
        self.in_transaction=False
        self.drafts = OrderedDict()
        self.published = {}
        self.actions = {}
        self.cache = OrderedDict()
        self.calls = deque()
        self.lock = asyncio.Lock()

    def prepare(self, live, history, session):
        if not self.repository:
            return
        if self.namespace is None:
            digest=hashlib.sha256(live.model_dump_json().encode())
            for match in history:
                digest.update(match.model_dump_json().encode())
            self.namespace=digest.hexdigest()
            drafts,published,actions=self.repository.load(self.namespace)
            self.drafts=OrderedDict(drafts)
            self.published=published
            self.actions={s:deque(rows,maxlen=12) for s,rows in actions.items()}
        if session not in self.loaded_sessions:
            for draft in self.repository.session_drafts(self.namespace,session):
                self.drafts[draft.draft_id]=draft
            self.loaded_sessions.add(session)

    @contextmanager
    def transaction(self):
        """No await inside: state, publication and audit either all persist or roll back."""
        if self.in_transaction or not self.repository:
            yield
            return
        before=deepcopy((self.drafts,self.published,self.actions,self.cache,self.pending_events,self.evicted))
        self.in_transaction=True
        try:
            yield
            # Polling unchanged state must not generate writes or audit spam.
            if self.pending_events:
                self.repository.commit(self.namespace,list(self.drafts.values())+self.evicted,self.published,
                    {e['session'] for e in self.pending_events},self.pending_events)
                self.pending_events=[]
                self.evicted=[]
        except Exception:
            self.drafts,self.published,self.actions,self.cache,self.pending_events,self.evicted=before
            raise
        finally:
            self.in_transaction=False

    def record(self, session, message, draft=None, details=None):
        self.actions.setdefault(session,deque(maxlen=12)).append(message)
        if self.repository:
            self.pending_events.append({'session':session,'event':message,
                'draft_id':draft.draft_id if draft else None,
                'details':details if details is not None else ({'draft':draft.model_dump(mode='json')} if draft else {})})

    def context(self, live, history, request):
        result = analyze(live,history,0,request.entity_id if request.mode=='player' else 'n-8',
                         request.entity_id if request.mode=='team' else 'riverside',request.match_clock_ms, store=self.store)
        comparison = result.comparison if request.mode=='player' else result.shot_comparison if request.team_metric=='shots' else result.team_comparison
        entities = live.players if request.mode=='player' else live.teams
        name = next(entity.name for entity in entities if (getattr(entity,'player_id',None) or getattr(entity,'team_id'))==request.entity_id)
        return comparison, name

    async def generate(self, live, history, request: DraftRequest):
        self.prepare(live,history,request.session_id)
        if request.match_clock_ms>=live.duration_ms:
            return DraftResult(draft=None,message='The match has ended; no new graphic can be published.',cached=False)
        comparison,name = self.context(live,history,request)
        contribution=comparison.contribution
        if not (contribution.eligible if contribution else comparison.matched_baseline and comparison.baseline_value is not None):
            return DraftResult(draft=None,message='No eligible unusual comparison at this moment. Try a testing moment or let play develop.',cached=False)
        key = hashlib.sha256(json.dumps([request.mode,request.entity_id,request.match_clock_ms,comparison.model_dump()],sort_keys=True).encode()).hexdigest()
        # Serializing calls deduplicates simultaneous requests and bounds cloud usage.
        async with self.lock:
            if key in self.cache:
                cached = self.cache[key]
                # Dismissed drafts stay dismissed instead of being silently regenerated.
                existing = next((d for d in self.drafts.values() if d.session_id==request.session_id and d.draft_id==cached.draft_id),None)
                if existing and existing.status in ['proposed','dismissed']:
                    return DraftResult(draft=existing,message='Reused this snapshot; no additional model call.',cached=True)
                draft = cached.model_copy(update={'draft_id':str(uuid4()),'session_id':request.session_id,'status':'proposed'})
                with self.transaction():
                    self.save(draft)
                    self.record(request.session_id,'Reused validated snapshot',draft)
                return DraftResult(draft=draft,message='Reused validated snapshot; no additional model call.',cached=True)
            now = time.monotonic()
            while self.calls and now-self.calls[0][0]>600:
                self.calls.popleft()
            if not contribution and (len(self.calls)>=30 or sum(session==request.session_id for _,session in self.calls)>=10):
                raise ValueError('Model request limit reached. Wait before generating more drafts.')
            if not contribution:
                if self.public_demo:
                    self.repository.reserve_model_call()
                self.calls.append((now,request.session_id))
            evidence = {'entity':'{{entity}}','mode':request.mode,'match_clock_ms':request.match_clock_ms,
                        'comparison':{'current':comparison.current_value,'baseline':comparison.baseline_value,
                            'sample_size':comparison.sample_size,'unit':comparison.unit,
                            'window':'{{window}}','scope':'{{scope}}'},
                        'available_current_event_ids':comparison.current_source_event_ids[:12],
                        'allowed_templates':['comparison','spotlight'] if request.mode=='player' else ['comparison','trend']}
            chart_kind=model_visual_types(comparison)[0]
            historical_series=list(zip(comparison.source_match_ids,comparison.historical_values))[-5:]
            evidence['visual_data']={'series_kind':'independent_comparable_matches',
                'historical_series':[{'match_id':mid,'value':value} for mid,value in historical_series],
                'current':comparison.current_value,'unit':comparison.unit,'history_sample_size':comparison.sample_size,
                'allowed_visual_types':model_visual_types(comparison)}
            start=time.monotonic()
            source='foundry'
            diagnostic=None
            message='Schema, numeric placeholders and source IDs checked. Producer review required.'
            input_tokens=output_tokens=0
            try:
                if contribution:
                    source='calculated'
                    message='Counts calculated from events since coming on. No model call; producer approval required.'
                    body=casual_wording(comparison)
                    texts=[f'{name} | Since coming on',body,
                           f'{body} Entered at {contribution.entered_at_match_clock_ms//60000}:{contribution.entered_at_match_clock_ms//1000%60:02d}. Goals are included in shots.',
                           ('The substitute has scored since coming on.' if contribution.goals else 'The substitute has taken a shot since coming on.' if contribution.shots else 'The substitute is getting involved in possession.')]
                    if contribution.historical_completed_passes is not None:
                        texts[2] += (f' Prior substitute appearances at equal playing time: {contribution.history_sample_size}; '
                            f'averages {contribution.historical_completed_passes:.1f} completed passes, '
                            f'{contribution.historical_shots:.1f} shots, {contribution.historical_goals:.1f} goals.')
                    template='spotlight' 
                    cited=comparison.current_source_event_ids
                else:
                    schema=deepcopy(SCHEMA)
                    schema['properties']['template_id']['enum']=evidence['allowed_templates']
                    schema['properties']['event_ids']['items']['enum']=evidence['available_current_event_ids']
                    schema['properties']['visual_type']['enum']=model_visual_types(comparison)
                    raw,input_tokens,output_tokens=await generate_graphic(evidence,schema)
                    try:
                        model,texts=validate_templates(raw,comparison,name,request.match_clock_ms)
                    except DraftValidationError as exc:
                        if exc.field!='reason_template':
                            raise
                        # Keep valid model copy; replace only the rejected explanation locally.
                        raw={**raw,'reason_template':SAFE_REASON}
                        model,texts=validate_templates(raw,comparison,name,request.match_clock_ms)
                        diagnostic='explanation_replaced'
                    template=model.template_id
                    chart_kind=model.visual_type
                    cited=model.event_ids
            except (ValueError,KeyError,TypeError,httpx.HTTPError) as exc:
                source='factual_fallback'
                diagnostic=('invalid_'+exc.field if isinstance(exc,DraftValidationError) else
                    'provider_http_error' if isinstance(exc,httpx.HTTPError) else 'provider_or_response_error')
                message='AI wording could not be verified. Review this factual draft before publishing.'
                values=substitutions(comparison,name,request.match_clock_ms)
                title=f'{name} | '+('Forward-pass involvement' if request.mode=='player' else 'Shot surge' if comparison.metric=='shots' else 'Pressure surge')
                body=f'{name}: {values["current"]} {values["unit"]}, versus {values["baseline"]} for {values["scope"]}.'
                texts=[title,body,body+f' Sample: {comparison.sample_size} matches.', 'The measured comparison crossed the configured editorial threshold.']
                template='comparison'
                cited=comparison.current_source_event_ids[:3]
            if chart_kind!='numbers' and not contribution:
                period=('10 minutes' if comparison.metric=='shots' else '5 minutes' if comparison.metric=='pressure_events'
                        else f'{comparison.current_minutes:g} minutes played')
                texts[2]=(f'{comparison.current_value:g} {comparison.unit} in {period}. '
                          f'Usual: {comparison.baseline_value:g} across {comparison.sample_size} matches.')
            draft=GraphicDraft(draft_id=str(uuid4()),session_id=request.session_id,snapshot_clock_ms=request.match_clock_ms,
                expires_at_match_clock_ms=min(live.duration_ms,request.match_clock_ms+120000),mode=request.mode,
                entity_id=request.entity_id,entity_name=name,template_id=template,title=texts[0],casual_text=casual_wording(comparison),
                analyst_text=texts[2],rationale=texts[3],source=source,status='proposed',comparison=comparison,
                cited_event_ids=cited,latency_ms=int((time.monotonic()-start)*1000),input_tokens=input_tokens,
                output_tokens=output_tokens,message=message,diagnostic=diagnostic,
                visual=build_visual(comparison,chart_kind),
                visual_options=[build_visual(comparison,kind) for kind in visual_types(comparison)])
            with self.transaction():
                self.cache[key]=draft.model_copy(deep=True)
                while len(self.cache)>32:
                    self.cache.popitem(last=False)
                self.save(draft)
                self.record(request.session_id,f'Generated {source} draft at {request.match_clock_ms//1000}s',draft)
            return DraftResult(draft=draft,message=message,cached=False)

    def save(self,draft):
        queued=[d for d in self.drafts.values() if d.session_id==draft.session_id and d.status=='proposed']
        for old in queued[:-2]:
            old.status='superseded'
            self.record(old.session_id,'Superseded queued draft',old)
        self.drafts[draft.draft_id]=draft
        while len(self.drafts)>100:
            pinned={graphic.draft_id for graphic in self.published.values()}
            removable=next((key for key in self.drafts if key not in pinned),None)
            if removable is None:
                break
            old=self.drafts.pop(removable)
            if self.repository:
                self.evicted.append(old)
                self.loaded_sessions.discard(old.session_id)

    def relevant(self,live,history,draft,clock):
        if not draft.snapshot_clock_ms<=clock<draft.expires_at_match_clock_ms:
            return False
        comparison,_=self.context(live,history,DraftRequest(session_id=draft.session_id,mode=draft.mode,entity_id=draft.entity_id,match_clock_ms=clock,team_metric='shots' if draft.comparison.metric=='shots' else 'pressure_events'))
        return ((comparison.contribution.eligible if comparison.contribution else comparison.matched_baseline) and comparison.current_value==draft.comparison.current_value
                and comparison.baseline_value==draft.comparison.baseline_value
                and comparison.current_source_event_ids==draft.comparison.current_source_event_ids)

    def state(self,live,history,session,clock):
        self.prepare(live,history,session)
        with self.transaction():
            return self._state(live,history,session,clock)

    def _state(self,live,history,session,clock):
        for draft in list(self.drafts.values()):
            if draft.session_id==session and draft.status in ['proposed','approved'] and not self.relevant(live,history,draft,clock):
                draft.status='expired'
                self.record(session,'Expired stale graphic '+draft.draft_id,draft)
        published=self.published.get(session)
        if published:
            draft=self.drafts.get(published.draft_id)
            if draft is None or draft.status!='approved':
                self.published.pop(session,None)
                published=None
        return EditorialState(drafts=[d for d in self.drafts.values() if d.session_id==session][-3:],
                              published=published,recent_actions=list(self.actions.get(session,[])))

    def act(self,live,history,action: EditorialAction):
        self.prepare(live,history,action.session_id)
        with self.transaction():
            return self._act(live,history,action)

    def _act(self,live,history,action: EditorialAction):
        self.state(live,history,action.session_id,action.match_clock_ms)
        if action.action=='clear':
            published=self.published.pop(action.session_id,None)
            if published and published.draft_id in self.drafts:
                self.drafts[published.draft_id].status='superseded'
            self.record(action.session_id,'Cleared audience graphic',details={'previous_publication':published.model_dump(mode='json') if published else None})
            return self.state(live,history,action.session_id,action.match_clock_ms)
        draft=self.drafts.get(action.draft_id)
        if draft is None or draft.session_id!=action.session_id:
            raise ValueError('Draft not found in this session.')
        if draft.status!='proposed':
            raise ValueError('This draft is no longer awaiting approval. Generate a fresh snapshot.')
        if action.action=='dismiss':
            draft.status='dismissed'
            self.record(action.session_id,'Dismissed '+draft.draft_id,draft)
        else:
            if action.audience=='casual' and (len(action.body)>120 or len(action.body.split())>20):
                raise ValueError('Keep casual wording to 20 words and 120 characters.')
            check_edit(action.title,action.body,draft)
            selected_visual=build_visual(draft.comparison,action.visual_type or (draft.visual.kind if draft.visual else 'numbers'))
            if selected_visual.kind!='numbers' and (len(action.title)>80 or len(action.body)>140):
                raise ValueError('Keep chart headlines to 80 characters and wording to 140, or choose numbers only.')
            if action.action=='save':
                draft.headline_edited=draft.headline_edited or action.title.strip()!=draft.title
                draft.title=action.title.strip()
                draft.visual=selected_visual
                if action.audience=='casual':
                    draft.casual_text=action.body.strip()
                else:
                    draft.analyst_text=action.body.strip()
                self.record(action.session_id,'Saved draft edits',draft)
                return self.state(live,history,action.session_id,action.match_clock_ms)
            previous=self.published.get(action.session_id)
            if previous and previous.draft_id in self.drafts:
                self.drafts[previous.draft_id].status='superseded'
                self.record(action.session_id,'Superseded published graphic',self.drafts[previous.draft_id])
            draft.status='approved'
            team_id=draft.entity_id if draft.mode=='team' else next(p.team_id for p in live.players if p.player_id==draft.entity_id)
            team_name=next(t.name for t in live.teams if t.team_id==team_id)
            self.published[action.session_id]=PublishedGraphic(draft_id=draft.draft_id,template_id=draft.template_id,
                entity_name=draft.entity_name,entity_type=draft.mode,team_id=team_id,team_name=team_name,
                show_headline=action.audience=='analyst' or draft.headline_edited or action.title.strip()!=draft.title,
                visual=selected_visual,
                title=action.title.strip(),body=action.body.strip(),audience=action.audience,snapshot_clock_ms=draft.snapshot_clock_ms,
                published_at_match_clock_ms=action.match_clock_ms,expires_at_match_clock_ms=draft.expires_at_match_clock_ms,
                source=draft.source,current_value=draft.comparison.current_value,baseline_value=draft.comparison.baseline_value,unit=draft.comparison.unit,
                historical_values=draft.comparison.historical_values)
            draft.title=action.title.strip()
            draft.visual=selected_visual
            if action.audience=='casual':
                draft.casual_text=action.body.strip()
            else:
                draft.analyst_text=action.body.strip()
            self.record(action.session_id,'Approved and published '+draft.draft_id,draft,
                {'draft':draft.model_dump(mode='json'),'publication':self.published[action.session_id].model_dump(mode='json')})
        return self.state(live,history,action.session_id,action.match_clock_ms)

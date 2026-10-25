import json
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from functools import lru_cache
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
from backend.contracts import (Analysis, Health, HistoricalMatch, HistoricalSummary, MatchFixture, ProbeResult,
    DraftRequest, DraftResult, EditorialAction, EditorialState)
from backend.editorial import EditorialService
from backend.editorial_store import EditorialStore, DraftLimitReached
from backend.operations import Operations
from backend.history_store import HistoryStore
from backend.moments import detect_moments
from backend.contracts import Moment
from backend.statistics import analyze, eligible_history, historical_summary
from backend.foundry import configuration, probe

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
PUBLIC_DEMO=os.getenv('PUBLIC_DEMO_MODE','0')=='1'
@asynccontextmanager
async def lifespan(app):
    editorial.prepare(fixture(),history(),'startup-check')
    repository.check()
    historical_index()
    if os.getenv('REQUIRE_FRONTEND_BUILD')=='1' and not (ROOT/'dist/index.html').is_file():
        raise RuntimeError('Build the frontend before starting the production server.')
    yield

app = FastAPI(title='Broadcast Copilot', version='0.1.0', lifespan=lifespan,
    docs_url=None if PUBLIC_DEMO else '/docs',redoc_url=None if PUBLIC_DEMO else '/redoc',
    openapi_url=None if PUBLIC_DEMO else '/openapi.json')
ops=Operations()
app.middleware('http')(ops.middleware)
@lru_cache(maxsize=1)
def historical_index():
    return HistoryStore(eligible_history(history(),fixture()))

repository=EditorialStore(os.getenv('EDITORIAL_DB_PATH',str(ROOT/'runtime/editorial.sqlite3')))
editorial=EditorialService(repository=repository,public_demo=PUBLIC_DEMO)


@app.exception_handler(sqlite3.Error)
async def storage_unavailable(request, exc):
    return JSONResponse(status_code=503,content={'detail':'Saved-work storage is unavailable. No editorial change was committed.'})


@app.get('/health/live')
async def live_check():
    return {'status':'ok'}


@app.get('/health/ready')
async def readiness():
    try:
        repository.check()
        fixture()
        historical_index()
        if os.getenv('REQUIRE_FRONTEND_BUILD')=='1' and not (ROOT/'dist/index.html').is_file():
            raise RuntimeError('Missing frontend build.')
    except (sqlite3.Error,OSError,ValueError,RuntimeError):
        return JSONResponse(status_code=503,content={'status':'unavailable'})
    return {'status':'ready','storage':'writable','foundry_configured':configuration() is not None,
        'foundry_note':'Configuration only; readiness makes no billable model call.'}


@app.get('/api/ops')
async def operations():
    if PUBLIC_DEMO:
        raise HTTPException(404,'Not found')
    editorial.prepare(fixture(),history(),'operations-check')
    return {**ops.snapshot(),'workflow':repository.summary(editorial.namespace)}


@app.get('/api/editorial/history')
async def saved_work(session_id: str=Query(min_length=8,max_length=80,pattern=r'^[a-zA-Z0-9-]+$')):
    editorial.prepare(fixture(),history(),session_id)
    return repository.session_drafts(editorial.namespace,session_id,50)


@app.get('/api/editorial/audit')
async def audit_export(session_id: str=Query(min_length=8,max_length=80,pattern=r'^[a-zA-Z0-9-]+$'),
                       limit: int=Query(100,ge=1,le=1000)):
    editorial.prepare(fixture(),history(),session_id)
    return JSONResponse(content={'scope':'Browser workspace, not an authenticated operator identity.',
        'newest_first':True,'limit':limit,'events':repository.audit(editorial.namespace,session_id,limit)},
        headers={'Content-Disposition':'attachment; filename="broadcast-history.json"'})



@app.post('/api/editorial/generate',response_model=DraftResult)
async def generate_draft(request: DraftRequest):
    try:
        editorial.store=historical_index()
        return await editorial.generate(fixture(),history(),request)
    except DraftLimitReached as exc:
        raise HTTPException(429,str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None


@app.get('/api/editorial/state',response_model=EditorialState)
async def editorial_state(session_id: str=Query(min_length=8,max_length=80,pattern=r'^[a-zA-Z0-9-]+$'),match_clock_ms: int=Query(ge=0,le=5400000)):
    return editorial.state(fixture(),history(),session_id,match_clock_ms)


@app.post('/api/editorial/action',response_model=EditorialState)
async def editorial_action(action: EditorialAction):
    try:
        return editorial.act(fixture(),history(),action)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None


@app.get('/api/health', response_model=Health)
def health():
    configured = configuration() is not None
    return Health(foundry_configured=configured, foundry_message=(
        ('AI drafting configured for this demo.' if PUBLIC_DEMO else 'Configured; run a connection check to verify.') if configured else
        'Not connected. The local fixture works without Azure credentials.'
    ),public_demo=PUBLIC_DEMO)


@app.get('/api/fixture', response_model=MatchFixture)
@lru_cache(maxsize=1)
def fixture():
    return MatchFixture.model_validate(json.loads((ROOT / 'data' / 'live_fixture.json').read_text()))


@lru_cache(maxsize=1)
def history():
    return [HistoricalMatch.model_validate(item) for item in json.loads((ROOT / 'data/historical_matches.json').read_text())]


@app.get('/api/history', response_model=list[HistoricalSummary])
def history_summaries():
    return [historical_summary(match) for match in eligible_history(history(), fixture())]


@app.get('/api/moments', response_model=list[Moment])
async def moments(match_clock_ms: int=Query(ge=0,le=5400000),
            session_id: str=Query(min_length=8,max_length=80,pattern=r'^[a-zA-Z0-9-]+$')):
    editorial.prepare(fixture(),history(),session_id)
    drafts=[d for d in editorial.drafts.values() if d.session_id==session_id]
    return detect_moments(fixture(),history(),match_clock_ms,historical_index(),drafts)


@app.get('/api/analysis', response_model=Analysis)
def analysis(event_count: int = Query(0, ge=0), player_id: str = 'n-8', team_id: str = 'riverside', match_clock_ms: int | None = Query(None, ge=0)):
    try:
        return analyze(fixture(), history(), event_count, player_id, team_id, match_clock_ms, store=historical_index())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.post('/api/foundry/probe', response_model=ProbeResult)
async def foundry_probe():
    if PUBLIC_DEMO:
        raise HTTPException(404,'Not found')
    try:
        await probe()
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from None
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f'Foundry returned HTTP {exc.response.status_code}. Check deployment and access.') from None
    except (httpx.RequestError, json.JSONDecodeError):
        raise HTTPException(502, 'Foundry could not be reached or returned an invalid response.') from None
    return ProbeResult(status='connected', message='Live Foundry response received.')


# A built deployment serves the UI and API from the same origin. API routes win.
if (ROOT/'dist').is_dir():
    app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='frontend')

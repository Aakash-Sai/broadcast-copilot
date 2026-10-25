# Broadcast Copilot

An editorial assistant for choosing evidence-backed graphics during a synthetic football match. Play a full 90-minute match or jump to a testing moment, inspect calculated evidence, generate a draft, save edits, and approve it into the audience preview. Drafts, decisions and audit history persist in SQLite. A single-server production preview adds health checks and operational logs. Spanish narration, recaps and agent orchestration remain unimplemented. See [deployment and operations](docs/DEPLOYMENT.md).

An [Azure judge-demo deployment package](docs/AZURE_HOSTING.md) is prepared for West US 3, including HTTPS, a dedicated VM template, backup/watchdog timers and durable public-demo AI request ceilings. It has not provisioned resources or a public site. Generate the source-only archive with `python -m scripts.package_hosting`.

## Run locally

Prerequisites: Python 3.12+, Node.js 20.19+ or 22.12+, and pnpm. From the project folder in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
pnpm install
.\.venv\Scripts\python.exe -m scripts.export_contracts
.\start.ps1
```

Open http://127.0.0.1:5173. The frontend proxies `/api` to FastAPI on port 8000. No Azure account or key is needed. The match clock advances continuously, independently of events. Use 1×/30×/60×/120× playback, pause, reset, the seek slider, or named testing moments. Only the latest twelve received events appear in the feed.

If using the bundled Codex Python, substitute its full path for `python` in the first command. If script execution policy blocks the launcher, run these commands in two terminals instead:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pnpm dev
```

## Data contracts

`backend/contracts.py` defines events, historical comparisons, insights, overlays, players, teams, and API responses. `frontend/src/contracts.ts` is generated from those models; regenerate it after changing a contract. The pitch coordinate range is 0–100. All teams, events, and names in the fixture are synthetic. The fixture covers 90 match-clock minutes, with 11 starters and four bench players per team, timed formation changes and substitutions. Player minutes are derived from participation intervals. Stoppage time and the wall-clock halftime break are not simulated.

## Foundry setup

1. Create an Azure subscription and a Microsoft Foundry resource.
2. Deploy a model supporting the Azure OpenAI v1 Responses API. Choose a deployment available to your resource and subscription; this app does not create billable resources automatically.
3. Copy `.env.example` to `.env`. Fill in the Azure inference base URL ending `/openai/v1/`, API key, and **deployment name** in `FOUNDRY_MODEL`. Do not use the project endpoint or put keys in frontend code.
4. Restart the backend. Expand **Setup and connection status** and select **Check Foundry connection**. This makes a small live inference request and can incur model usage charges. Configured does not mean verified; the button confirms a live response.

The adapter uses Microsoft's documented [Azure OpenAI v1 API](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle?tabs=key). [Foundry endpoints](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/endpoints) explain the distinction between project and inference URLs. The backend never returns API keys or upstream response bodies in diagnostics.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
pnpm build
```

API schema: http://127.0.0.1:8000/docs. Local development only: the connection-check endpoint has no authentication and should not be exposed publicly. Add access control and deployment configuration before hosting.

## Historical comparisons

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_history
```

The repeatable seed creates 20 historical test fixtures per team and a full live match. `/api/history` derives player/team totals from events. `/api/analysis?match_clock_ms=900000&player_id=n-8&team_id=riverside` produces an as-of snapshot, including score, formation and substitution context. Expand **Demo & technical tools → Demo moments** for scenario jumps. Team mode compares equivalent historical five-minute pressure windows; Player mode compares current completed-forward-pass totals with prior starts at equal elapsed playing time.

Player comparisons match elapsed playing time; team comparisons match the five-minute clock interval. Fewer than three eligible appearances/windows result in current-only output. Actual player minutes include substituted and unused bench players. Duplicate events are deduplicated; conflicting duplicates are rejected. Future/current/uncompleted historical matches are excluded. All numerical values are calculated in code; Foundry draft wording is available on demand. See [dataset assumptions and scenarios](data/README.md).

## Generate and publish a graphic

1. Expand **Demo & technical tools → Demo moments**. Jump to **Pressure surge at 15:00** and choose Team/Riverside, or **Player involvement at 44:00** and choose Player/Alex Morgan.
2. Select **Generate draft**. This pauses playback and makes one bounded Foundry Responses API request. It is not called by the playback clock. Ordinary model usage charges/credits apply.
3. Review casual or analyst wording, edit the headline and body in either audience mode, and inspect **Why now** and cited events. Select **Approve and publish** to display the graphic. **Dismiss** retains the decision without publishing; **Clear audience graphic** removes it.
4. Resume playback. The graphic is removed if its evidence changes, its maximum two-minute match-clock lifetime expires, or you seek before its snapshot. The graphic labels the original snapshot time.

The audience graphic sits in the bottom corner matching its team’s pitch label (including player graphics) with a separate player/team name label. Both teams are named on the pitch. Casual wording uses short, deterministic phrases derived from the evidence, limited to 20 words and 120 characters; analyst mode retains the detailed comparison and headline. Edited headlines also appear on casual cards, while the trusted player/team name remains separate. Foundry supplies the analyst wording, headline, rationale and template choice.

The backend recomputes evidence from fixture data, not client-provided numbers. Only eligible unusual comparisons are submitted. Entity names are withheld from the model and inserted locally. Structured JSON output supplies template text, an allowed graphic type and cited event IDs. Code fills numeric/time/window placeholders and checks their presence, allowed sources, text lengths and a restricted vocabulary. Unsupported drafts and provider failures produce an explicit factual fallback requiring the same approval.

These are schema, numeric-reference and source checks, **not a comprehensive semantic truth verifier**. A producer must review wording. Approved edits receive the same limited number/claim checks. Raw model output and secrets are not returned in errors. [Structured-output format](https://developers.openai.com/api/docs/guides/structured-outputs).

Exact snapshots are cached in memory (32 entries); concurrent generation is serialized and deduplicated. A browser workspace can generate up to 10 new snapshots per 10 minutes; the process permits 30. Cache reuse adds no model call. Calls have a 20-second timeout, 900 output-token maximum, and no automatic retries. Usage diagnostics show provider-reported tokens from the original draft, not a per-click billing estimate. The workflow keeps a recent draft cache and at most three proposed drafts per workspace; older drafts and audit versions remain in SQLite. A restart restores saved drafts and still-valid publications, but clears the model cache and process-local request limits/counters. These limits are not a permanent spending cap.

`POST /api/editorial/generate` takes the session, clock, mode and entity. `POST /api/editorial/action` saves/approves/dismisses/clears. `GET /api/editorial/state?session_id=...&match_clock_ms=...` supplies drafts, a machine-readable published graphic and recent actions. `/api/editorial/history` and `/api/editorial/audit` expose saved work for that workspace. Browser IDs persist locally but are not authentication. Login is excluded at the user's request; the deployment rehearsal remains localhost-only. See the deployment guide before any hosting.

## Next milestone

Player and team insights share one comparison panel, with collapsible evidence. Scores, formations and substitutions follow the selected match clock. Before/after changes do not establish causal impact.

Test the existing workflow with the expanded history before adding more insight types. Automatic ranking and indexed retrieval are implemented. See [demo and submission preparation](docs/DEMO_AND_SUBMISSION.md) for a short walkthrough and the remaining submission artifacts.

## Substitute contribution

Select **Substitute scores · 74:00** in Testing moments; this also selects Taylor Quinn River in Player mode. Select **Generate draft**, review the counts and **Approve and publish**. Other substitutes use the same Player selector after entering. A draft becomes available after three completed passes or one shot since entry. It shows completed passes, shots and goals since coming on, in the corner matching the player's team. Goals are included in shots.

Counts use only received events up to the snapshot and the player's participation interval. The casual card stays a short current-match summary. Analyst mode also shows averages from prior substitute appearances at equal elapsed playing time when at least three qualify. No causal impact is claimed. The broadcaster can edit headline and wording, with number/claim checks; no model request is made or billed. Producer approval, expiry, dismissal and clearing work as for other cards.

## Automatic moment suggestions and historical retrieval

A compact **Suggested moments** panel scans all players and both teams automatically, ranks up to three supported moments and applies repetition controls. Selecting a suggestion pauses at its evidence snapshot and selects that player/team; it does not call Foundry or publish anything. **Generate draft** / **Generate draft**, review and approval stay manual. No suggestions are produced after full time.

The backend builds an indexed, read-only SQLite database in memory at startup/first use from the synthetic history. Parameterized queries retrieve up to 20 comparable prior starts, team windows or substitute appearances, excluding matches not completed before live kickoff. The database is local and regenerated on restart; JSON fixtures remain the source of truth. No cloud database, search service or vector embeddings are provisioned. Inspect draft evidence for retrieved match IDs and source events.

## Team shot surges

Jump to **Shot surge · 35:00**. The scenario selects Team / Northbridge / Shots automatically. Alternatively select Team and **Shots · 10 minutes**, or choose a Shot surge from Suggested moments. The test window contains 5 attempts versus a 1.0 historical average across 20 matching windows. Generate, edit and approve as usual. The short casual card says “5 shots in 10 minutes. More than usual.” Source evidence, historical samples, repetition control and expiry use the selected shot metric independently of pressure.

All shot outcomes count as attempts, including goals. No expected-goals model, chance-quality estimate, on-target comparison or scoring prediction is implemented.

## Focused producer workspace

The default view shows playback, suggested moments, a selected comparison, the graphic editor and audience preview. Manual selection is under **Choose a player or team**. Playback speed, seeking, demo moments, the raw event log, historical tables and setup checks are inside **Demo & technical tools**. Evidence remains available on demand under **View supporting data** and **Source details**. Factual fallback drafts remain explicitly labelled.

Foundry's response schema constrains comparison sentences to approved placeholder templates, casual wording to its verified slot, layouts to those supported for the insight and citations to supplied event IDs. Headlines and short explanations are still generated. A rejected explanation alone is replaced locally with a factual explanation; rejected statistics, sources, titles or provider failures still use a labelled factual fallback. Validation diagnostics are available in Source details. No automatic provider retries were added. This limits structural errors; it is not a semantic guarantee and producer review is required.

## Compact historical charts

For comparisons with at least three verified historical observations, Foundry chooses a compact bar chart or dot plot from supported types. Its input includes the latest five historical counts and the current count. Application code supplies every plotted value and match ID; the model cannot emit chart values, SVG or arbitrary chart types. Independent matches are not joined by a line.

Charts show at most five prior comparable matches, oldest to newest, followed by a highlighted **Now** point. The caption states how many of the full historical sample are shown; the comparison average still uses the full eligible sample. Every chart uses a zero baseline and numeric labels. No percentages or cumulative categories are inferred.

The producer sees the same chart component before publication and can select **Graphic style**: numbers only, recent-match bars or recent-match dots. Approval revalidates the choice and builds the published points from server evidence. Two-point/insufficient series and substitute category summaries remain numeric. All visuals follow the same team corner, snapshot expiry and approval controls. Layout fallback remains labelled if AI output fails validation.

The taller audience preview reserves the same pitch height for every graphic style, so publishing or removing a chart does not resize the pitch. Chart headlines are capped at 80 characters and body copy at 140 (casual copy retains its tighter limit). Analyst chart drafts start with a short factual count/window/sample summary; numbers-only mode keeps room for longer wording.

## Illustrative match view

The audience pitch shows 22 numbered, team-coloured player markers, current formations, the last event and its active player. Lineups follow the fixture's participation intervals and substitutions. Passes and shots have illustrative paths and brief ball movement during playback; goals highlight the scoring end. Reduced-motion preferences disable animation.

The attacking team's supporting players advance with the ball: fullbacks push up, midfielders support and forwards move into the final third, with centre backs providing cover. The opposition drops into a narrower defensive shape. Pressure events treat the pressing side as the defending team. These are deterministic visual heuristics based on the latest event, not measured tactics or confirmed possession; transitions are smoothed between events.

Positions, shirt numbers and path endpoints are illustrative, not measured player tracking or verified pass destinations. The pitch carries this disclosure. Statistics still come exclusively from fixture events. Team sides remain fixed for readability, including after half time. Use **Play**, or seek through **Demo & technical tools**, to try the view; the substitute-goal moment at 74:00 is a useful example. Verify scene logic with `node --test tests/test_pitch.cjs`.

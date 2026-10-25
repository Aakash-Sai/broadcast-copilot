# MVP and official-rules review

Reviewed October 24, 2026 against the supplied OFFICIAL RULES.md and [Microsoft's published rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md). This is an implementation and submission-readiness review, not confirmation of entrant eligibility or acceptance. Category assessments below are our judgment, not organizer decisions.

## Overall assessment

Implementation update after this review: durable SQLite drafts/decisions/audit history, save-draft editing, health checks, sanitized request logs, operational counters, backups and a local production entry point have been added. The readiness limits below should now be read with that progress in mind: persistent audit storage is no longer missing. Azure hosting, external alerting and authentication remain absent; the user chose local rehearsal and excluded login. See [deployment and operations](DEPLOYMENT.md) for verified scope and the untested container package.

The MVP demonstrates the five-stage pipeline in section 4.1(i): replay synthetic events as a timed stream, calculate statistics, explain notable comparisons, render compact overlays, and offer casual/analyst experiences with player/team focus. Producer-triggered drafting and approval fit a broadcast workflow; full automatic publication is not needed to demonstrate this pipeline.

It is not ready to declare complete coverage of the challenge or submit as-is. Match recaps and multi-language output described in section 4.1 are absent, and judging access and submission artifacts remain unfinished. Some wording is aspirational ("should" and "could support"), but recaps and languages should be treated as coverage gaps rather than confidently dismissed as optional. Speed estimation, pass difficulty and video auto-eventing are explicitly introduced as features to consider; they do not justify cluttering this MVP.

## Evidence and gaps

| Area | What exists | Remaining limit |
| --- | --- | --- |
| Ingest and interpret | Seeded 90-minute replay, per-event counts, participation and substitutions | Preloaded replay, not a production external event feed |
| Explain moments | Pressure, forward passing, shots and substitute contributions; equal-period historical retrieval and evidence IDs | Statistical context is not causal tactical analysis; the data is synthetic |
| Render | Editable, approved machine-readable graphics, numbers/bars/dots, snapshot timestamps and expiry | Audience preview, not an integration with a broadcast rendering partner |
| Personalize | Casual/analyst copy, player/team selection | Producer-controlled modes, not independent viewer profiles; English only |
| Narrative and recap | Short event narratives and reasons | No automatic halftime/fulltime recap |
| Data innovation | Two fictional teams, repeatable history, full match, formations and substitutions | Synthetic locations and pass destinations are not coherent player tracking; no measured speed or distance |
| Microsoft technology | Foundry model deployment, constrained drafting and chart choices, bounded calls, factual fallback | One model-call workflow; no Foundry-managed agent orchestration, evaluation suite or cloud-native application deployment |
| Reliability and control | Approval/editing, numeric/source checks, fallback, session separation, expiry, tests; now durable audit storage and local operational checks | No authentication, cloud hosting or external alerting; session IDs are not authorization; semantic accuracy still needs editorial review |

Pitch movement is explicitly illustrative. Do not use it as evidence that the system detects real formations, tactical runs, possession or tracking metrics from live footage.

## Prize fit

| Prize | Current fit | Honest positioning |
| --- | --- | --- |
| Best Enterprise Solution Prize | Strongest product fit; readiness incomplete | Broadcaster workflow, evidence, editable drafts and approval address a clear business need. Persistent audit records and local deployment checks are now implemented; cloud deployment and an access boundary for hosting remain unfinished. |
| Best Use of Microsoft Foundry Project | Relevant, but limited differentiation | Foundry drafts grounded wording and chooses constrained visuals. Calling a deployed model alone is weaker than demonstrating Foundry's development, evaluation, orchestration and management benefits. Do not claim tools we have not used. |
| Grand Prize, First/Second Place | Thematically aligned; competitive result unknown | Clear end-to-end demonstration and practical value help. Narrow Microsoft-stack usage and limited agentic depth reduce strength under the judging rubric. |
| Best Multi-Agent System Prize | Does not currently fit | Detection, retrieval, validation and rendering are application stages, not collaborating specialized agents. Agents used to help write code would not make the product multi-agent. |
| Best Azure Cloud Native Integration | Does not currently fit well | Azure-hosted model inference exists, but the app itself runs locally. No demonstrated cloud-native service integration or resilience. |

Section 6.2 assigns 20% each to technological implementation, agentic design/innovation, real-world impact, UX/presentation and category adherence. Agentic design is our clearest scoring weakness; a clean producer experience and explicit approval are strengths, not reasons to manufacture unnecessary agents. Section 4.2 permits at most one Grand Prize and one Category Prize.

## Submission priorities

1. Close or explicitly clarify the recap and second-language coverage gaps. Keep these within the existing workflow rather than adding more analytics panels.
2. Provide a working, free-to-test demo or test build through November 10, 2026, 11:59 pm Pacific (sections 4.8 and 1). A localhost link and source requiring a judge's own paid model account do not establish unrestricted working AI access. A hosted demo is one route; a properly documented working test build is also allowed. Do not expose the current unauthenticated development server publicly.
3. Prepare the short pitch, public GitHub repository, actual working-product video under two minutes at a supported public video URL, English materials and project-page fields (sections 4.4 and 4.9). Include setup/testing instructions and dependency licenses; exclude credentials and private files.
4. Verify entrant registration and eligibility, project creation after September 29, 2026, ownership/permissions and no previous contest win (sections 3, 4.3, 4.4 and 4.6–4.12). These personal/project-history facts are not independently verified here.
5. Submit by October 27, 2026, 11:59 pm Pacific. The published registration deadline was October 20 at noon Pacific; the user says they entered, but registration status has not been inspected.

Recommendation: position this as a broadcast editorial copilot and target Enterprise Solution. Finish coverage and judging access before adding more features. Do not claim production readiness, a multi-agent architecture, measured tracking or odds of winning. No publication, deployment or entry submission was performed as part of this review.

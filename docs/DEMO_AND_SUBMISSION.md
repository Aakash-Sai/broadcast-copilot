# Demo and submission preparation

Based on the supplied `OFFICIAL RULES.md`, sections 4.1, 4.3 and 4.4. This checklist does not confirm that an entry has been submitted or accepted.

See the [October 24 rules and prize-fit review](RULES_REVIEW.md) for current coverage gaps, category assessment and judging-access requirements. Match recaps and working multi-language output remain absent; neither should be presented as implemented.

## Current implementation

- A seeded 90-minute synthetic fixture updates player and team statistics during playback.
- Passing, pressure, shot-surge and substitute moments are detected automatically across both teams, ranked and deduplicated for producer review.
- Indexed SQLite queries retrieve up to 20 comparable historical matches with time, participation and source checks.
- Microsoft Foundry generates headlines, explanations and supported wording/layout choices on request. Numerical values are inserted by code. Substitute summaries use calculated templates without a model call.
- Casual/analyst modes, editable headlines and wording, team-aligned compact graphics, approval, dismissal and expiry are available.
- This is a test library with two fictional teams and a public Azure demo; it is not a real match feed or production broadcast integration.
- SQLite now preserves saved edits, approvals, dismissals, expiry and audit versions across restarts. A local production preview serves the built UI/API with health checks and request monitoring; Azure hosting is deployed in West US 2; external alert delivery is not configured. Login is excluded by the user's choice. See [deployment and operations](DEPLOYMENT.md).

## Suggested demo (target 1 minute 45 seconds)

| Time | Show | Explain |
| --- | --- | --- |
| 0:00-0:15 | Playback and Suggested moments | Detection is automatic; drafting and publishing stay under producer control. |
| 0:15-0:45 | 15:00 Riverside pressure; Generate draft | Code checks 20 current events against a 3.2 mean across 20 matching historical windows. |
| 0:45-1:05 | Casual/analyst modes; edit wording; approve | Different detail for different audiences, with producer approval. |
| 1:05-1:25 | 44:00 Alex Morgan | 16 completed forward passes versus a 5.25 mean at equal playing time across 20 starts. |
| 1:25-1:40 | 74:00 substitute; Generate draft; approve | Taylor Quinn River has 4 completed passes, 1 shot and 1 goal since entry; analyst context uses equal-time substitute appearances. |
| 1:40-1:45 | Audience preview | Explainable evidence and accessible graphics with human editorial control. |

The additional 35:00 shot-surge example shows 5 Northbridge attempts versus a same-window historical mean of 1.0. Swap it into the walkthrough rather than extending the video.

Demo jumps are under **Demo & technical tools > Demo moments**. Keep technical panels closed when recording the main workflow. Evidence is available under **View supporting data** and **Source details**.

Before recording, run tests/build and verify actual Foundry generation. Use only material you have permission to include, keep fallback drafts labelled if shown, and keep the final video below two minutes.

## Remaining submission artifacts

- A short pitch naming the problem, product and Microsoft/Azure technologies.
- A functioning demo video shorter than two minutes, uploaded to a supported public video URL.
- Completed: public GitHub source and setup instructions at https://github.com/Aakash-Sai/broadcast-copilot. Credentials and runtime data are excluded.
- Completed project-page submission fields and an intended category.
- Deployed: https://broadcast-copilot-aakash-56875895.westus2.cloudapp.azure.com. Keep it free to judges and available through November 10, 2026 at 11:59 pm Pacific (section 4.8).
- User verification of registration, eligibility, rights and permissions, which have not been independently confirmed.

The supplied rules list registration closing October 20, 2026 at 12:00 pm Pacific and submission closing October 27, 2026 at 11:59 pm Pacific. Check current organizer notices before relying on those dates.

Public repository creation and Azure hosting are complete. Video upload and entry submission remain separate actions and have not been performed.

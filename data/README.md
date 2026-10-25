# Synthetic testing dataset

Regenerate all fixtures with `python -m scripts.generate_history`. Seed: 20261012. The live match lasts 90 match-clock minutes and has 1,112 events. Twenty historical fixtures give each team 20 prior matches, containing 21,618 events. These repeat the same two fictional teams as a test library; they do not model a realistic league schedule. Fifteen older fixtures add seeded variation in scores and substitute minutes; five recent regression fixtures are retained. No real footage or player data is used.

Each team has 11 starters and four named bench players. Three substitutes enter in each match; one bench player stays unused. Participation intervals preserve exactly 11 active players per team, with 990 team player-minutes at full time. No player action is generated outside their interval. Historical substitution minutes vary by seed. Formation metadata includes the starting shape and timestamped changes; it is supplied synthetic context, not inferred tracking data.

Event types: passes (completed/incomplete and a supplied forward flag), shots (saved/off target/goal), pressure, tackles, possession changes, substitutions, and formation changes. Goals are shot outcomes and are counted once. Short possession sequences switch after failed passes, tackles and shots. Coordinates provide a simple illustrative pitch position, not continuous ball tracking. The layered scripted cases are for repeatable editorial tests, not a physically exact simulator or evidence of causation.

Named live testing moments:

| Time | Scenario |
| --- | --- |
| 15:00 | Riverside pressure surge: 20 events versus historical same-window mean 3.2 across 20 matches |
| 27:00 | Quiet interval; match clock continues without action events |
| 35:00 | Northbridge shot surge: 5 attempts versus same-window historical mean 1.0 across 20 matches |
| 44:00 | Featured player involvement after a forward-pass burst |
| 58:00 | Northbridge changes formation and substitutes a player |
| 74:00 | A Riverside substitute scores the equalizer |
| 90:00 | Full-time score 1–1; complete minutes and statistics |

The clock is independent of event timestamps. Playback offers real time and 30×/60×/120× acceleration, pause, reset, seeking and scenario jumps. Exactly 90 minutes are modeled: stoppage time and a 15-minute wall-clock halftime break are outside this test fixture. Quiet periods include 26:00–28:00 and 45:00–46:00.

`/api/analysis?match_clock_ms=900000` includes only events up to that time. Scores, minutes, formations and substitutions use the same cutoff. Historical matches must have completed before live kickoff. Duplicate IDs are idempotent; conflicting duplicates are rejected. Historical summaries are derived from raw events. Baselines retrieve the latest up to 20 eligible appearances/windows with a minimum of three. Starter passing compares equal elapsed playing time; prior participation must cover that whole period. Substitute history compares elapsed time since entry and requires enough minutes in each previous substitute appearance. Below three eligible appearances, only current counts are shown.

Team pressure compares equivalent five-minute clock windows, with boundaries `(start, end]`. A complete window, at least three historical matches, at least three current events and at least twice the historical mean (exceeding it) are required for the demo surge rule. This is an editorial threshold, not statistical significance. Player passing requires at least three completed forward passes and a count above and at least 1.5 times the same-time historical mean. Before/after substitution patterns are descriptive, not proof of impact.

Tests cover arithmetic, aggregation, repeated generation, source IDs, duplicate handling, future-data exclusion, squad membership, on-field intervals, unused bench players, formation changes, scoring, quiet periods and full-time clock bounds.

Historical retrieval uses an indexed, read-only SQLite database built once per server process from the JSON fixture library. Queries are parameterized and return exact match and event IDs; the model never writes SQL or computes the statistics. No vector database or extra cloud resource is needed. Restart after regenerating data.

`/api/moments` scans both teams and all players at the current clock, ranks up to three supported candidates, and makes no model calls. Only active players and comparisons with supporting activity in the last two match minutes are suggested. Recent substitute goals rank highest. Repeated facts already drafted in the same session are suppressed; changed facts have a two-match-minute cooldown, with an exception for a new substitute goal. Seeking backwards ignores decisions from later snapshots. Full time offers no new candidates. These are editorial heuristics, not statistical-significance tests. The producer selects a candidate and then explicitly generates and approves a draft.

Team shots use a complete ten-minute window `(start, end]`, including goals, saved and off-target attempts exactly once. Historical retrieval uses the same match-clock interval. A suggestion requires at least four attempts, above and at least twice the historical mean, with at least three prior matches and recent supporting activity. This is an editorial count threshold, not an xG, shot-quality or statistical-significance measure. The live 35:00 burst adds five scripted non-scoring Northbridge attempts; the 1�1 final score stays the same.

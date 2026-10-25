"""Version-one contracts shared by the API and generated TypeScript client."""
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class MatchEvent(Contract):
    event_id: str
    match_id: str
    sequence: int = Field(ge=0)
    match_clock_ms: int = Field(ge=0)
    type: Literal['pass', 'shot', 'pressure', 'possession_change', 'tackle', 'substitution', 'formation_change']
    team_id: str
    player_id: str | None = None
    outcome: Literal['completed', 'incomplete', 'goal', 'saved', 'off_target', 'applied', 'won', 'lost', 'changed']
    x: float | None = Field(default=None, ge=0, le=100)
    y: float | None = Field(default=None, ge=0, le=100)
    forward: bool = False
    related_player_id: str | None = None
    formation: str | None = None


class SubstituteContribution(Contract):
    entered_at_match_clock_ms: int
    minutes_played: float
    completed_passes: int
    shots: int
    goals: int
    eligible: bool
    history_sample_size: int = 0
    historical_completed_passes: float | None = None
    historical_shots: float | None = None
    historical_goals: float | None = None
    history_match_ids: list[str] = Field(default_factory=list)
    history_event_ids: list[str] = Field(default_factory=list)


class HistoricalComparison(Contract):
    entity_id: str
    metric: str
    current_value: float
    baseline_value: float | None = None
    unit: str
    window_description: str
    sample_size: int = Field(ge=0)
    source_match_ids: list[str]
    source_event_ids: list[str]
    limitations: list[str]
    historical_values: list[float] = Field(default_factory=list)
    current_source_event_ids: list[str] = Field(default_factory=list)
    current_minutes: float = Field(ge=0)
    matched_baseline: bool = False
    contribution: SubstituteContribution | None = None


class Insight(Contract):
    insight_id: str
    trigger: Literal['pressure_shift', 'player_involvement', 'dangerous_chance']
    source_event_ids: list[str]
    statistics_snapshot_id: str
    comparison: HistoricalComparison | None = None
    rationale: str
    score: float
    casual_text: str
    analyst_text: str
    expires_at_match_clock_ms: int = Field(ge=0)


class Overlay(Contract):
    insight_id: str
    version: int = Field(ge=1)
    template_id: Literal['comparison', 'trend', 'spotlight']
    title: str
    body: str
    audience: Literal['casual', 'analyst']
    language: Literal['en', 'es']
    approval_status: Literal['proposed', 'approved', 'dismissed', 'expired', 'superseded']
    effective_match_clock_ms: int = Field(ge=0)
    expires_at_match_clock_ms: int = Field(ge=0)


class Team(Contract):
    team_id: str
    name: str


class Player(Contract):
    player_id: str
    team_id: str
    name: str


class Participation(Contract):
    player_id: str
    start_match_clock_ms: int = Field(ge=0)
    end_match_clock_ms: int = Field(gt=0)


class Formation(Contract):
    team_id: str
    match_clock_ms: int = Field(ge=0)
    shape: Literal['4-3-3', '4-2-3-1', '4-4-2']


class Substitution(Contract):
    team_id: str
    match_clock_ms: int = Field(gt=0)
    player_off_id: str
    player_on_id: str


class Scenario(Contract):
    label: str
    match_clock_ms: int = Field(ge=0)


class MatchFixture(Contract):
    match_id: str
    label: str
    synthetic: Literal[True] = True
    teams: list[Team]
    players: list[Player]
    events: list[MatchEvent]
    kickoff_at: AwareDatetime
    duration_ms: int = Field(gt=0)
    participation: list[Participation]
    formations: list[Formation]
    substitutions: list[Substitution]
    scenarios: list[Scenario] = Field(default_factory=list)


class HistoricalMatch(MatchFixture):
    completed_at: AwareDatetime


class Statistics(Contract):
    entity_id: str
    completed_passes: int = 0
    attempted_passes: int = 0
    completed_forward_passes: int = 0
    pass_completion_pct: float | None = None
    shots: int = 0
    pressure_events: int = 0
    possession_changes: int = 0
    minutes_played: float | None = None
    goals: int = 0
    tackles_won: int = 0


class HistoricalSummary(Contract):
    match_id: str
    kickoff_at: AwareDatetime
    teams: list[Statistics]
    players: list[Statistics]


class Analysis(Contract):
    match_clock_ms: int
    event_count: int
    teams: list[Statistics]
    players: list[Statistics]
    comparison: HistoricalComparison
    comparison_text: str
    history_match_count: int
    team_comparison: HistoricalComparison
    shot_comparison: HistoricalComparison
    shot_comparison_text: str
    team_comparison_text: str
    active_formations: list[Formation]
    completed_substitutions: list[Substitution]


class Health(Contract):
    public_demo: bool = False
    status: Literal['ok'] = 'ok'
    stage: str = 'Historical comparisons'
    foundry_configured: bool
    foundry_message: str


class Moment(Contract):
    moment_id: str
    mode: Literal['player', 'team']
    entity_id: str
    entity_name: str
    metric: str
    match_clock_ms: int
    label: str
    detail: str
    score: float


class ProbeResult(Contract):
    status: Literal['connected']
    message: str


class DraftRequest(Contract):
    team_metric: Literal['pressure_events', 'shots'] = 'pressure_events'
    session_id: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9-]+$')
    match_clock_ms: int = Field(ge=0, le=5400000)
    mode: Literal['player', 'team']
    entity_id: str = Field(min_length=1, max_length=80)


class ChartPoint(Contract):
    label: str
    value: float = Field(ge=0, allow_inf_nan=False)
    match_id: str | None = None
    is_current: bool = False


class GraphicVisual(Contract):
    kind: Literal['numbers', 'historical_bars', 'historical_dots']
    title: str
    caption: str
    unit: str
    points: list[ChartPoint] = Field(default_factory=list)


class GraphicDraft(Contract):
    headline_edited: bool = False
    visual: GraphicVisual | None = None
    visual_options: list[GraphicVisual] = Field(default_factory=list)
    diagnostic: str | None = None
    draft_id: str
    session_id: str
    snapshot_clock_ms: int
    expires_at_match_clock_ms: int
    mode: Literal['player', 'team']
    entity_id: str
    entity_name: str
    template_id: Literal['comparison', 'trend', 'spotlight']
    title: str
    casual_text: str
    analyst_text: str
    rationale: str
    source: Literal['foundry', 'factual_fallback', 'calculated']
    status: Literal['proposed', 'approved', 'dismissed', 'expired', 'superseded']
    comparison: HistoricalComparison
    cited_event_ids: list[str]
    latency_ms: int
    input_tokens: int
    output_tokens: int
    message: str


class DraftResult(Contract):
    draft: GraphicDraft | None
    message: str
    cached: bool


class EditorialAction(Contract):
    visual_type: Literal['numbers', 'historical_bars', 'historical_dots'] | None = None
    session_id: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9-]+$')
    match_clock_ms: int = Field(ge=0, le=5400000)
    action: Literal['approve', 'dismiss', 'clear', 'save']
    draft_id: str | None = None
    title: str = Field(default='', max_length=100)
    body: str = Field(default='', max_length=500)
    audience: Literal['casual', 'analyst'] = 'casual'


class PublishedGraphic(Contract):
    visual: GraphicVisual | None = None
    show_headline: bool = False
    draft_id: str
    entity_name: str
    entity_type: Literal['player', 'team']
    team_id: str
    team_name: str
    template_id: Literal['comparison', 'trend', 'spotlight']
    title: str
    body: str
    audience: Literal['casual', 'analyst']
    snapshot_clock_ms: int
    published_at_match_clock_ms: int
    expires_at_match_clock_ms: int
    source: Literal['foundry', 'factual_fallback', 'calculated']
    current_value: float
    baseline_value: float | None
    unit: str
    historical_values: list[float]


class EditorialState(Contract):
    drafts: list[GraphicDraft]
    published: PublishedGraphic | None
    recent_actions: list[str]

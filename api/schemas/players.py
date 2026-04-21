from pydantic import BaseModel


class PlayerEmailBody(BaseModel):
    player: str
    email: str


class PlayerAliasBody(BaseModel):
    alias: str
    canonical: str


class PlayerAnalysisEvent(BaseModel):
    """One row per deck in the player's history, sorted by date."""

    deck_id: int
    # event_id can be an int (mtgtop8) or a string like "m1" for manually-created events.
    event_id: int | str | None = None
    event_name: str = ""
    date: str = ""
    rank: str = ""
    normalized_rank: str = ""
    normalized_rank_num: float | None = None
    points: float = 0.0
    player_count: int = 0
    format_id: str = ""
    archetype: str | None = None
    color_identity: list[str] = []
    commanders: list[str] = []


class PlayerAnalysisLeaderboardPoint(BaseModel):
    date: str
    rank: int
    total_players: int


class PlayerAnalysisArchetypeRow(BaseModel):
    archetype: str
    count: int
    pct: float


class PlayerAnalysisArchetypePerf(BaseModel):
    archetype: str
    count: int
    avg_finish: float | None = None
    best_finish: str = ""
    top8_pct: float = 0.0
    win_pct: float = 0.0


class PlayerAnalysisFormatRow(BaseModel):
    format_id: str
    count: int
    pct: float


class PlayerAnalysisCommanderRow(BaseModel):
    commander: str
    count: int
    pct: float


class PlayerAnalysisCardRow(BaseModel):
    card: str
    deck_count: int
    total_copies: int


class PlayerAnalysisFieldBucket(BaseModel):
    bucket: str
    count: int
    avg_finish: float | None = None
    top8_pct: float = 0.0


class PlayerAnalysisMetagameRow(BaseModel):
    archetype: str
    player_pct: float
    global_pct: float


class PlayerAnalysisHighlights(BaseModel):
    best_finish: str = ""
    longest_top8_streak: int = 0
    biggest_field_win: int | None = None
    total_events: int = 0
    avg_days_between_events: float | None = None
    first_event_date: str | None = None
    last_event_date: str | None = None


class PlayerAnalysisResponse(BaseModel):
    player: str
    player_id: int | None = None
    per_event: list[PlayerAnalysisEvent]
    leaderboard_history: list[PlayerAnalysisLeaderboardPoint]
    archetype_distribution: list[PlayerAnalysisArchetypeRow]
    archetype_performance: list[PlayerAnalysisArchetypePerf]
    color_distribution: dict[str, float]
    color_count_distribution: dict[str, int]
    format_distribution: list[PlayerAnalysisFormatRow]
    commander_distribution: list[PlayerAnalysisCommanderRow]
    average_mana_curve: dict[str, float]
    top_cards: list[PlayerAnalysisCardRow]
    pet_cards: list[PlayerAnalysisCardRow]
    field_size_buckets: list[PlayerAnalysisFieldBucket]
    metagame_comparison: list[PlayerAnalysisMetagameRow]
    highlights: PlayerAnalysisHighlights

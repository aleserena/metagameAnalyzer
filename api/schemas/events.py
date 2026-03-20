from pydantic import BaseModel, ConfigDict, Field


class EventResponse(BaseModel):
    event_id: int | str
    event_name: str
    store: str = ""
    location: str = ""
    date: str
    format_id: str
    player_count: int = 0
    origin: str = "mtgtop8"  # 'mtgtop8' | 'manual' for merge rules and UI


class CreateEventBody(BaseModel):
    event_name: str = ""
    date: str = ""  # DD/MM/YY
    format_id: str = "EDH"
    player_count: int = 0  # number of players in the event
    event_id: int | str | None = None  # optional; manual gets m1, m2, ... if omitted
    store: str = ""
    location: str = ""


class UploadDecksBody(BaseModel):
    decks: list[dict] | None = None


class NewEventBody(BaseModel):
    event_name: str
    date: str
    format_id: str = "EDH"


class LoadBody(BaseModel):
    """Load source: optional file upload, or JSON with explicit path and/or decks (not both required).

    Priority when multiple fields are set: non-empty ``path`` is loaded from disk first; otherwise
    ``decks`` when provided (including an empty list). Omit ``decks`` to load from ``path`` only.
    """

    path: str | None = None
    decks: list[dict] | None = None
    event_id: int | str | None = None
    new_event: NewEventBody | None = None


EVENT_MERGE_FIELDS = ("event_name", "store", "location", "date", "format_id", "player_count")

# Deck fields compared when merging two decks (same player or manual pair)
DECK_MERGE_FIELDS = ("player", "name", "rank", "player_count", "commanders", "archetype", "mainboard", "sideboard")


class MergeConflictItem(BaseModel):
    field: str
    value_keep: str | int | list | None
    value_remove: str | int | list | None


class DeckPairPreview(BaseModel):
    """Two decks (keep event + remove event) that will be merged into one."""
    deck_keep: dict
    deck_remove: dict
    conflicts: list[MergeConflictItem] = []


class MergePreviewResponse(BaseModel):
    can_merge: bool
    error: str | None = None
    event_a: dict
    event_b: dict
    conflicts: list[MergeConflictItem] = []
    merged_preview: dict  # proposed merged event (prefer mtgtop8, fill missing from other)
    keep_event_id: str  # which event will be kept (mtgtop8 if one is manual)
    remove_event_id: str  # which event will be deleted
    # Player/deck merge: auto-paired by canonical player name
    deck_pairs: list[DeckPairPreview] = []  # same player in both events -> merge with conflict resolution
    decks_keep_only: list[dict] = []  # decks in keep event with no pair in remove (by player)
    decks_remove_only: list[dict] = []  # decks in remove event with no pair in keep (will move as-is or manual pair)


class PlayerMergePair(BaseModel):
    """Admin-selected pair: merge this deck from remove event into this deck in keep event."""
    deck_id_keep: int
    deck_id_remove: int


class MergeEventsBody(BaseModel):
    event_id_keep: str
    event_id_remove: str
    resolutions: dict[str, str] = {}  # event field -> "keep" | "remove"
    # Manual player merges: merge remove deck into keep deck (same as auto-pair flow)
    player_merges: list[PlayerMergePair] = []  # admin-selected pairs (from decks_remove_only + decks_keep_only)
    # Per deck-pair conflict resolution. Key: "deck_id_keep-deck_id_remove", value: { field: "keep"|"remove" }
    deck_resolutions: dict[str, dict[str, str]] = {}


class ScrapeBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Accepts JSON key "format" (frontend) while exposing field name "format_id" in Python.
    format_id: str = Field(alias="format")
    period: str | None = None
    meta: int | None = None
    store: str | None = None
    event_ids: str | list[int] | None = None  # comma-separated string from frontend or list of ints
    ignore_existing_events: bool = False
    force_replace: bool = False


class EventExportPlayer(BaseModel):
    """Player reference in event export (id, display_name)."""

    id: int
    display_name: str


class EventExportData(BaseModel):
    """Payload for exporting/importing a single event and all related data."""

    schema_version: int = 1
    event: EventResponse
    decks: list[dict] = Field(default_factory=list)
    matchups: list[dict] = Field(default_factory=list)
    player_emails: dict[str, str] = Field(default_factory=dict)
    players: list[EventExportPlayer] = Field(default_factory=list)


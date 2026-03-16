from pydantic import BaseModel, Field

from .matchups import MatchupItem


class CreateUploadLinksBody(BaseModel):
    type: str = "deck"  # deck | event_edit | feedback
    count: int = 1
    deck_id: int | None = None
    expires_in_days: int | None = None


class EventFeedbackBody(BaseModel):
    archetype: str
    deck_name: str | None = None
    rank: str | None = None
    matchups: list[MatchupItem] = Field(default_factory=list)

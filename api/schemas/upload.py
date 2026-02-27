from pydantic import BaseModel

from .decks import SubmitDeckBody


class CreateUploadLinksBody(BaseModel):
    type: str = "deck"  # deck | event_edit | feedback
    count: int = 1
    deck_id: int | None = None
    expires_in_days: int | None = None


class EventFeedbackMatchupItem(BaseModel):
    opponent_player: str
    result: str  # win | loss | draw | intentional_draw
    result_note: str | None = None
    round: int | None = None


class EventFeedbackBody(BaseModel):
    archetype: str
    deck_name: str | None = None
    rank: str | None = None
    matchups: list[EventFeedbackMatchupItem] = []


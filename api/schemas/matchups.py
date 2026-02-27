from pydantic import BaseModel, Field


class MatchupItem(BaseModel):
    opponent_player: str
    result: str  # win | loss | draw | intentional_draw
    result_note: str | None = None
    round: int | None = None


class AdminMatchupsBody(BaseModel):
    matchups: list[MatchupItem] = Field(default_factory=list)


class PatchMatchupBody(BaseModel):
    result: str | None = None
    result_note: str | None = None
    round: int | None = None


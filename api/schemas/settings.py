from pydantic import BaseModel, Field


class IgnoreLandsCardsBody(BaseModel):
    cards: list[str] = Field(default_factory=list)


class RankWeightsBody(BaseModel):
    weights: dict[str, float] = Field(default_factory=dict)


class MatchupsMinMatchesBody(BaseModel):
    value: int = 0


class SendFeedbackLinkToPlayerBody(BaseModel):
    """Body for sending a single feedback link email to a player for a given event."""

    player: str = ""

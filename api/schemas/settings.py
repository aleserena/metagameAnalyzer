from pydantic import BaseModel


class IgnoreLandsCardsBody(BaseModel):
    cards: list[str] = []


class RankWeightsBody(BaseModel):
    weights: dict[str, float] = {}


class MatchupsMinMatchesBody(BaseModel):
    value: int = 0


class SendFeedbackLinkToPlayerBody(BaseModel):
    """Body for sending a single feedback link email to a player for a given event."""

    player: str = ""

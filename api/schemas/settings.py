from pydantic import BaseModel


class IgnoreLandsCardsBody(BaseModel):
    cards: list[str] = []


class RankWeightsBody(BaseModel):
    weights: dict[str, float] = {}


class MatchupsMinMatchesBody(BaseModel):
    value: int = 0


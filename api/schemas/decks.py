from pydantic import BaseModel, Field


class SubmitDeckBody(BaseModel):
    event_name: str = ""
    player: str = ""
    name: str = ""
    rank: str = ""
    mainboard: list[dict] = Field(default_factory=list)  # [{"qty": int, "card": str}, ...]
    sideboard: list[dict] = Field(default_factory=list)
    commanders: list[str] | None = None


class DeckCardUpdate(BaseModel):
    qty: int = 1
    card: str = ""


class DeckListBody(BaseModel):
    """Deck list update via feedback link (mainboard, sideboard, commanders)."""

    mainboard: list[DeckCardUpdate]
    sideboard: list[DeckCardUpdate] = Field(default_factory=list)
    commanders: list[str] = Field(default_factory=list)


class UpdateDeckBody(BaseModel):
    """Optional fields for updating a deck (admin-only)."""

    name: str | None = None
    player: str | None = None
    rank: str | None = None
    archetype: str | None = None
    event_id: int | str | None = None  # move deck to another event (must exist)
    commanders: list[str] | None = None
    mainboard: list[DeckCardUpdate] | None = None
    sideboard: list[DeckCardUpdate] | None = None


class ImportMoxfieldBody(BaseModel):
    url: str


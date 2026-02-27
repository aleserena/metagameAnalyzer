from pydantic import BaseModel, Field


class EventResponse(BaseModel):
    event_id: int | str
    event_name: str
    store: str = ""
    location: str = ""
    date: str
    format_id: str
    player_count: int = 0


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
    decks: list[dict] = Field(default_factory=list)
    new_event: NewEventBody | None = None


class ScrapeBody(BaseModel):
    # Accepts JSON key "format" (frontend) while exposing field name "format_id" in Python.
    format_id: str = Field(alias="format")
    period: str | None = None
    meta: int | None = None
    store: str | None = None
    event_ids: list[int] | None = None
    ignore_existing_events: bool = False
    force_replace: bool = False

    class Config:
        allow_population_by_field_name = True


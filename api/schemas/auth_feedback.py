from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class LoginBody(BaseModel):
    password: str = ""


class SiteFeedbackBody(BaseModel):
    type: str = "bug"  # bug | enhancement | question
    title: str = ""
    description: str = ""
    email: str | None = Field(default=None, max_length=254)
    website: str | None = None  # honeypot: bots often fill this; humans leave empty
    captcha_token: str | None = None
    captcha_answer: int | None = None


# Largest card-name batch POST /cards/lookup accepts; the frontend splits bigger requests.
MAX_LOOKUP_NAMES = 200


class CardLookupBody(BaseModel):
    names: list[Annotated[str, StringConstraints(max_length=200)]] = Field(default_factory=list, max_length=MAX_LOOKUP_NAMES)


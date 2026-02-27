from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    password: str = ""


class SiteFeedbackBody(BaseModel):
    type: str = "bug"  # bug | enhancement | question
    title: str = ""
    description: str = ""
    email: str | None = None
    website: str | None = None  # honeypot: bots often fill this; humans leave empty
    captcha_a: int | None = None
    captcha_b: int | None = None
    captcha_answer: int | None = None


class CardLookupBody(BaseModel):
    names: list[str] = Field(default_factory=list)


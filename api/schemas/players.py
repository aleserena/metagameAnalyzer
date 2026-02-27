from pydantic import BaseModel


class PlayerEmailBody(BaseModel):
    player: str
    email: str


class PlayerAliasBody(BaseModel):
    alias: str
    canonical: str


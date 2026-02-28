from pydantic import BaseModel, Field, model_validator

MATCHUP_RESULT_VALUES = frozenset({
    "win", "loss", "draw",
    "intentional_draw", "intentional_draw_win", "intentional_draw_loss",
    "bye", "drop",
})


class MatchupItem(BaseModel):
    opponent_player: str
    result: str  # win | loss | draw | intentional_draw | bye | drop
    result_note: str | None = None
    round: int | None = None

    @model_validator(mode="after")
    def reject_null_or_invalid_registry(self):
        """Prevent matchup items that would become NULL or invalid in the DB."""
        result = (self.result or "").strip()
        if not result:
            raise ValueError("result is required and cannot be empty")
        if result.lower() not in MATCHUP_RESULT_VALUES:
            raise ValueError(
                f"result must be one of: {sorted(MATCHUP_RESULT_VALUES)}"
            )
        # For non-bye/drop, opponent must be present
        if result.lower() not in ("bye", "drop"):
            opp = (self.opponent_player or "").strip()
            if not opp or opp == "(unknown)":
                raise ValueError(
                    "opponent_player is required when result is not bye or drop"
                )
        return self


class AdminMatchupsBody(BaseModel):
    matchups: list[MatchupItem] = Field(default_factory=list)


class PatchMatchupBody(BaseModel):
    result: str | None = None
    result_note: str | None = None
    round: int | None = None


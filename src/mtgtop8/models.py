"""Data models for MTGTop8 scraper."""

from dataclasses import dataclass
from typing import Any


@dataclass
class Event:
    """Event metadata from format page."""

    event_id: int
    format_id: str
    name: str
    date: str  # DD/MM/YY


@dataclass
class Deck:
    """Deck with full card list and metadata."""

    deck_id: int
    event_id: int
    format_id: str
    name: str
    player: str
    event_name: str
    date: str  # DD/MM/YY
    rank: str  # "1", "2", "3-4", "5-8", etc.
    player_count: int
    mainboard: list[tuple[int, str]]  # [(qty, card_name), ...]
    sideboard: list[tuple[int, str]]
    commanders: list[str]  # for EDH
    archetype: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "deck_id": self.deck_id,
            "event_id": self.event_id,
            "format_id": self.format_id,
            "name": self.name,
            "player": self.player,
            "event_name": self.event_name,
            "date": self.date,
            "rank": self.rank,
            "player_count": self.player_count,
            "mainboard": [{"qty": q, "card": c} for q, c in self.mainboard],
            "sideboard": [{"qty": q, "card": c} for q, c in self.sideboard],
            "commanders": self.commanders,
            "archetype": self.archetype,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Deck":
        """Deserialize from JSON."""
        mainboard = [
            (item["qty"], item["card"])
            for item in data.get("mainboard", [])
        ]
        sideboard = [
            (item["qty"], item["card"])
            for item in data.get("sideboard", [])
        ]
        return cls(
            deck_id=data["deck_id"],
            event_id=data["event_id"],
            format_id=data["format_id"],
            name=data["name"],
            player=data["player"],
            event_name=data["event_name"],
            date=data["date"],
            rank=data["rank"],
            player_count=data["player_count"],
            mainboard=mainboard,
            sideboard=sideboard,
            commanders=data.get("commanders", []),
            archetype=data.get("archetype"),
        )

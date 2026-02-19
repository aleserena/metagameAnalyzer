"""FastAPI backend for MTG Metagame web app."""

import json
import os
import threading
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote

import jwt

def _normalize_search(s: str) -> str:
    """Lowercase and strip accents for relaxed substring matching."""
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from pydantic import BaseModel

# Import from project - run from project root
import sys
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

DATA_DIR = Path(os.getenv("DATA_DIR", str(_project_root)))
if not DATA_DIR.is_absolute():
    DATA_DIR = _project_root / DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

from src.mtgtop8.analyzer import (
    DEFAULT_IGNORE_LANDS_SET,
    analyze,
    deck_analysis,
    find_duplicate_decks,
    player_leaderboard,
    similar_decks,
)
from src.mtgtop8.card_lookup import lookup_cards
from src.mtgtop8.models import Deck
from src.mtgtop8.scraper import scrape

app = FastAPI(title="MTG Metagame API", version="1.0.0")

_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Admin auth: single user, password from env, JWT for session
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
JWT_SECRET = os.getenv("JWT_SECRET", ADMIN_PASSWORD or "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXP_SECONDS = 7 * 24 * 3600  # 7 days


def _create_admin_token() -> str:
    return jwt.encode(
        {"sub": "admin", "exp": int(time.time()) + JWT_EXP_SECONDS},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def _verify_admin_token(token: str) -> bool:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub") == "admin"
    except jwt.PyJWTError:
        return False


def require_admin(authorization: str | None = Header(None, alias="Authorization")):
    """Dependency: require valid admin Bearer token or raise 401."""
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Admin login disabled (ADMIN_PASSWORD not set)")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if not _verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return "admin"


# In-memory storage
_decks: list[dict] = []
_metagame_cache: dict | None = None
_player_aliases: dict[str, str] = {}  # alias -> canonical


def _aliases_path() -> Path:
    return DATA_DIR / "player_aliases.json"


def _ignore_lands_cards_path() -> Path:
    return DATA_DIR / "ignore_lands_cards.json"


def _get_ignore_lands_cards() -> list[str]:
    """Load ignore-lands card list from file, or return default sorted list."""
    p = _ignore_lands_cards_path()
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            cards = data.get("cards")
            if isinstance(cards, list) and all(isinstance(c, str) for c in cards):
                return sorted(set(c.strip() for c in cards if c.strip()))
        except (json.JSONDecodeError, OSError):
            pass
    return sorted(DEFAULT_IGNORE_LANDS_SET)


def _load_player_aliases() -> None:
    global _player_aliases
    p = _aliases_path()
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                _player_aliases = json.load(f)
        except (json.JSONDecodeError, OSError):
            _player_aliases = {}
    else:
        _player_aliases = {}


def _save_player_aliases() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_aliases_path(), "w", encoding="utf-8") as f:
        json.dump(_player_aliases, f, indent=2, ensure_ascii=False)


def _normalize_player(name: str) -> str:
    """Return canonical player name (alias -> canonical mapping)."""
    if not name or not name.strip():
        return "(unknown)"
    n = name.strip()
    return _player_aliases.get(n, n)


_load_player_aliases()


def _get_decks() -> list[Deck]:
    return [Deck.from_dict(d) for d in _decks]


def _invalidate_metagame() -> None:
    global _metagame_cache
    _metagame_cache = None


def _normalize_split_cards(decks: list[dict]) -> list[dict]:
    """Fix split card names: 'Fire / Ice' -> 'Fire // Ice'."""
    import re
    for d in decks:
        for section in ("mainboard", "sideboard"):
            cards = d.get(section, [])
            for card in cards:
                if isinstance(card, dict) and "card" in card:
                    name = card["card"]
                    if " // " not in name and re.search(r"\s/\s", name):
                        card["card"] = re.sub(r"\s+/\s+", " // ", name)
    return decks


def _load_from_file(path: str) -> None:
    global _decks
    with open(path, encoding="utf-8") as f:
        _decks = _normalize_split_cards(json.load(f))
    _invalidate_metagame()


# Load decks.json on startup if present
_startup_path = DATA_DIR / "decks.json"
if _startup_path.exists():
    try:
        _load_from_file(str(_startup_path))
    except Exception:
        pass


_RANK_ORDER = {"1": 0, "2": 1, "3-4": 2, "5-8": 3, "9-16": 4, "17-32": 5}


def _parse_date_sortkey(date_str: str) -> str:
    """Convert DD/MM/YY to YYMMDD for sorting."""
    parts = date_str.split("/")
    if len(parts) == 3:
        return parts[2] + parts[1] + parts[0]
    return date_str


def _deck_sort_key(d: dict) -> tuple:
    """Sort by date descending, then rank ascending."""
    date_key = _parse_date_sortkey(d.get("date", ""))
    rank_key = _RANK_ORDER.get(d.get("rank", ""), 99)
    return (-int(date_key) if date_key.isdigit() else 0, rank_key)


def _date_in_range(date_str: str, date_from: str | None, date_to: str | None) -> bool:
    """Check if DD/MM/YY date_str is within [date_from, date_to] (inclusive)."""
    key = _parse_date_sortkey(date_str)
    if not key.isdigit():
        return True
    key_int = int(key)
    if date_from:
        from_key = _parse_date_sortkey(date_from)
        if from_key.isdigit() and key_int < int(from_key):
            return False
    if date_to:
        to_key = _parse_date_sortkey(date_to)
        if to_key.isdigit() and key_int > int(to_key):
            return False
    return True


def _filter_decks_by_date(decks: list[dict], date_from: str | None, date_to: str | None) -> list[dict]:
    """Filter decks by date range."""
    if not date_from and not date_to:
        return decks
    return [d for d in decks if _date_in_range(d.get("date", ""), date_from, date_to)]


@app.get("/api/health")
def health():
    """Health check for load balancers and monitoring."""
    return {"status": "ok"}


class LoginBody(BaseModel):
    password: str = ""


@app.post("/api/auth/login")
def auth_login(body: LoginBody):
    """Login as admin. Returns JWT if password matches ADMIN_PASSWORD."""
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Admin login disabled (ADMIN_PASSWORD not set)")
    if body.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"token": _create_admin_token(), "user": "admin"}


@app.get("/api/auth/me")
def auth_me(authorization: str | None = Header(None, alias="Authorization")):
    """Return current user if valid Bearer token, else 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if not _verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"user": "admin"}


class CardLookupBody(BaseModel):
    names: list[str] = []


@app.post("/api/cards/lookup")
def cards_lookup(body: CardLookupBody):
    """Look up card metadata and images from Scryfall."""
    if not body.names:
        return {}
    return lookup_cards(body.names)


def _deck_sort_key_by(sort: str, order: str):
    """Return (key_fn, reverse) for sorting decks."""
    reverse = order == "desc"

    def key(d: dict):
        if sort == "date":
            date_key = _parse_date_sortkey(d.get("date", ""))
            val = int(date_key) if date_key.isdigit() else 0
            return (-val if reverse else val, _RANK_ORDER.get(d.get("rank", ""), 99))
        if sort == "rank":
            rk = _RANK_ORDER.get(d.get("rank", ""), 99)
            date_key = _parse_date_sortkey(d.get("date", ""))
            return (-rk if reverse else rk, -(int(date_key) if date_key.isdigit() else 0))
        if sort == "player":
            return ((d.get("player") or "").lower(),)
        if sort == "name":
            return ((d.get("name") or "").lower(),)
        return _deck_sort_key(d)

    return key, reverse if sort in ("player", "name") else False


@app.get("/api/decks")
def list_decks(
    event_id: int | None = Query(None, description="Filter by event ID (single, for backward compatibility)"),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    commander: str | None = Query(None, description="Filter by commander name (substring)"),
    deck_name: str | None = Query(None, description="Filter by deck name (substring)"),
    archetype: str | None = Query(None, description="Filter by archetype (substring)"),
    player: str | None = Query(None, description="Filter by player name (substring)"),
    card: str | None = Query(None, description="Filter by card name (substring, commander, mainboard or sideboard)"),
    sort: str = Query("date", description="Sort by: date, rank, player, name"),
    order: str = Query("desc", description="Sort order: asc, desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List decks with optional filters and pagination."""
    filtered = _decks
    if event_ids:
        ids = [int(x.strip()) for x in event_ids.split(",") if x.strip()]
        if ids:
            filtered = [d for d in filtered if d.get("event_id") in ids]
    elif event_id is not None:
        filtered = [d for d in filtered if d.get("event_id") == event_id]
    if commander:
        c_norm = _normalize_search(commander)
        filtered = [
            d for d in filtered
            if any(c_norm in _normalize_search(c or "") for c in d.get("commanders", []))
        ]
    if deck_name:
        dn_norm = _normalize_search(deck_name)
        filtered = [d for d in filtered if dn_norm in _normalize_search(d.get("name") or "")]
    if archetype:
        arch_norm = _normalize_search(archetype)
        filtered = [
            d for d in filtered
            if arch_norm in _normalize_search(d.get("archetype") or "")
        ]
    if player:
        p_norm = _normalize_search(player)
        filtered = [
            d for d in filtered
            if p_norm in _normalize_search(d.get("player") or "")
            or p_norm in _normalize_search(_normalize_player(d.get("player") or ""))
        ]
    if card:
        card_norm = _normalize_search(card)
        filtered = [
            d for d in filtered
            if any(card_norm in _normalize_search(c or "") for c in d.get("commanders", []))
            or any(
                card_norm in _normalize_search((e.get("card") if isinstance(e, dict) else "") or "")
                for section in (d.get("mainboard", []), d.get("sideboard", []))
                for e in section
            )
        ]
    sort_val = sort if sort in ("date", "rank", "player", "name") else "date"
    order_val = order if order in ("asc", "desc") else "desc"
    key_fn, reverse = _deck_sort_key_by(sort_val, order_val)
    filtered = sorted(filtered, key=key_fn, reverse=reverse)
    total = len(filtered)
    page = filtered[skip : skip + limit]
    # Normalize player names for display (merge aliases)
    page = [{**d, "player": _normalize_player(d.get("player") or "")} for d in page]
    return {"decks": page, "total": total, "skip": skip, "limit": limit}


@app.get("/api/decks/compare")
def compare_decks(ids: str = Query(..., description="Comma-separated deck IDs")):
    """Get multiple decks by ID for comparison."""
    try:
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deck IDs")
    if len(id_list) < 2 or len(id_list) > 4:
        raise HTTPException(status_code=400, detail="Provide 2 to 4 deck IDs")
    deck_map = {d.get("deck_id"): d for d in _decks}
    result = []
    for did in id_list:
        if did not in deck_map:
            raise HTTPException(status_code=404, detail=f"Deck {did} not found")
        d = dict(deck_map[did])
        d["player"] = _normalize_player(d.get("player") or "")
        result.append(d)
    return {"decks": result}


def _deck_duplicate_info(deck_id: int) -> dict | None:
    """Return duplicate info for a deck: {is_duplicate, duplicate_of, same_mainboard_ids}."""
    decks = [Deck.from_dict(d) for d in _decks]
    dup_map = find_duplicate_decks(decks)
    for primary, others in dup_map.items():
        if deck_id == primary:
            return {"is_duplicate": False, "duplicate_of": None, "same_mainboard_ids": others}
        if deck_id in others:
            return {"is_duplicate": True, "duplicate_of": primary, "same_mainboard_ids": [x for x in others if x != deck_id]}
    return None


@app.get("/api/decks/duplicates")
def list_duplicate_decks(
    event_ids: str | None = Query(None, description="Limit to events (comma-separated)"),
):
    """Decks with identical mainboard (duplicates across events)."""
    candidate = _decks
    if event_ids:
        ids = [int(x.strip()) for x in event_ids.split(",") if x.strip()]
        if ids:
            candidate = [d for d in _decks if d.get("event_id") in ids]
    decks = [Deck.from_dict(d) for d in candidate]
    dup_map = find_duplicate_decks(decks)
    deck_map = {d.get("deck_id"): d for d in _decks}
    result = []
    for primary_id, duplicate_ids in dup_map.items():
        primary = deck_map.get(primary_id, {})
        result.append({
            "primary_deck_id": primary_id,
            "primary_name": primary.get("name"),
            "primary_player": primary.get("player"),
            "primary_event": primary.get("event_name"),
            "primary_date": primary.get("date"),
            "duplicate_deck_ids": duplicate_ids,
            "duplicates": [
                {
                    "deck_id": did,
                    "name": deck_map.get(did, {}).get("name"),
                    "player": deck_map.get(did, {}).get("player"),
                    "event_name": deck_map.get(did, {}).get("event_name"),
                    "date": deck_map.get(did, {}).get("date"),
                }
                for did in duplicate_ids
            ],
        })
    return {"duplicates": result}


@app.get("/api/decks/{deck_id}")
def get_deck(deck_id: int):
    """Get single deck by ID."""
    for d in _decks:
        if d.get("deck_id") == deck_id:
            out = dict(d)
            out["player"] = _normalize_player(out.get("player") or "")
            dup = _deck_duplicate_info(deck_id)
            if dup:
                out["duplicate_info"] = dup
            return out
    raise HTTPException(status_code=404, detail="Deck not found")


@app.get("/api/decks/{deck_id}/similar")
def get_similar_decks(
    deck_id: int,
    limit: int = Query(10, ge=1, le=20),
    event_ids: str | None = Query(None, description="Limit to events (comma-separated)"),
):
    """Decks with high card overlap (same metagame)."""
    deck_dict = None
    for d in _decks:
        if d.get("deck_id") == deck_id:
            deck_dict = d
            break
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    deck = Deck.from_dict(deck_dict)
    candidate_decks = _decks
    if event_ids:
        ids = [int(x.strip()) for x in event_ids.split(",") if x.strip()]
        if ids:
            candidate_decks = [d for d in _decks if d.get("event_id") in ids]
    all_decks = [Deck.from_dict(d) for d in candidate_decks]
    return {"similar": similar_decks(deck, all_decks, limit=limit)}


@app.get("/api/decks/{deck_id}/analysis")
def get_deck_analysis(deck_id: int):
    """Deck analysis: mana curve, color distribution, lands distribution."""
    deck_dict = None
    for d in _decks:
        if d.get("deck_id") == deck_id:
            deck_dict = d
            break
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    deck = Deck.from_dict(deck_dict)
    card_names = list({c for _, c in deck.mainboard} | {c for _, c in deck.sideboard})
    metadata = lookup_cards(card_names)
    return deck_analysis(deck, metadata)


@app.get("/api/date-range")
def get_date_range():
    """Return min/max dates and the latest event date from loaded decks."""
    if not _decks:
        return {"min_date": None, "max_date": None, "last_event_date": None}
    dates = [d.get("date", "") for d in _decks if d.get("date")]
    valid = [d for d in dates if _parse_date_sortkey(d).isdigit()]
    if not valid:
        return {"min_date": None, "max_date": None, "last_event_date": None}
    sorted_keys = sorted(valid, key=_parse_date_sortkey)
    max_date = sorted_keys[-1]
    return {"min_date": sorted_keys[0], "max_date": max_date, "last_event_date": max_date}


@app.get("/api/format-info")
def get_format_info():
    """Return the format(s) detected from loaded decks."""
    FORMAT_NAMES = {
        "ST": "Standard", "PI": "Pioneer", "MO": "Modern", "LE": "Legacy",
        "VI": "Vintage", "PAU": "Pauper", "cEDH": "cEDH", "EDH": "Duel Commander",
        "PREM": "Premodern", "EXP": "Explorer", "HI": "Historic", "ALCH": "Alchemy",
        "PEA": "Peasant", "BL": "Block", "EX": "Extended", "HIGH": "Highlander",
        "CHL": "Canadian Highlander",
    }
    if not _decks:
        return {"format_id": None, "format_name": None}
    format_ids = {d.get("format_id", "") for d in _decks if d.get("format_id")}
    if len(format_ids) == 1:
        fid = next(iter(format_ids))
        return {"format_id": fid, "format_name": FORMAT_NAMES.get(fid, fid)}
    return {"format_id": None, "format_name": "Multiple Formats"}


@app.get("/api/events")
def list_events():
    """List unique events from current data."""
    seen: dict[tuple[int, str], dict] = {}
    for d in _decks:
        key = (d.get("event_id"), d.get("event_name", ""))
        if key not in seen:
            seen[key] = {
                "event_id": d.get("event_id"),
                "event_name": d.get("event_name"),
                "date": d.get("date"),
                "format_id": d.get("format_id"),
            }
    return {"events": list(seen.values())}


@app.get("/api/metagame")
def get_metagame(
    placement_weighted: bool = Query(False),
    ignore_lands: bool = Query(False),
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    event_id: int | None = Query(None, description="Filter by event ID (single, backward compat)"),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
):
    """Full metagame report."""
    if not _decks:
        return {
            "summary": {"total_decks": 0, "unique_commanders": 0, "unique_archetypes": 0},
            "commander_distribution": [],
            "archetype_distribution": [],
            "top_cards_main": [],
            "placement_weighted": placement_weighted,
            "ignore_lands": ignore_lands,
        }
    filtered = _decks
    if event_ids:
        ids = [int(x.strip()) for x in event_ids.split(",") if x.strip()]
        if ids:
            filtered = [d for d in filtered if d.get("event_id") in ids]
    elif event_id is not None:
        filtered = [d for d in filtered if d.get("event_id") == event_id]
    else:
        filtered = _filter_decks_by_date(filtered, date_from, date_to)
    decks = [Deck.from_dict(d) for d in filtered]
    ignore_lands_cards = set(_get_ignore_lands_cards()) if ignore_lands else None
    return analyze(
        decks,
        placement_weighted=placement_weighted,
        ignore_lands=ignore_lands,
        ignore_lands_cards=ignore_lands_cards,
    )


@app.get("/api/settings/ignore-lands-cards")
def get_ignore_lands_cards(_: str = Depends(require_admin)):
    """Return list of card names excluded when 'Ignore lands' is checked (admin-only)."""
    return {"cards": _get_ignore_lands_cards()}


class IgnoreLandsCardsBody(BaseModel):
    cards: list[str] = []


@app.put("/api/settings/ignore-lands-cards")
def put_ignore_lands_cards(body: IgnoreLandsCardsBody, _: str = Depends(require_admin)):
    """Update list of cards excluded when 'Ignore lands' is checked (admin-only)."""
    cards = [c.strip() for c in body.cards if isinstance(c, str) and c.strip()]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_ignore_lands_cards_path(), "w", encoding="utf-8") as f:
        json.dump({"cards": sorted(set(cards))}, f, indent=2, ensure_ascii=False)
    return {"cards": _get_ignore_lands_cards()}


@app.get("/api/player-aliases")
def get_player_aliases():
    """List player alias mappings (alias -> canonical)."""
    return {"aliases": _player_aliases}


class PlayerAliasBody(BaseModel):
    alias: str
    canonical: str


@app.post("/api/player-aliases")
def add_player_alias(body: PlayerAliasBody, _: str = Depends(require_admin)):
    """Merge player: map alias to canonical name. E.g. {'alias': 'Pablo Tomas Pesci', 'canonical': 'Tomas Pesci'}."""
    alias = body.alias.strip()
    canonical = body.canonical.strip()
    if not alias or not canonical:
        raise HTTPException(status_code=400, detail="alias and canonical required")
    _player_aliases[alias] = canonical
    _save_player_aliases()
    return {"aliases": _player_aliases}


@app.delete("/api/player-aliases/{alias:path}")
def remove_player_alias(alias: str, _: str = Depends(require_admin)):
    """Remove a player alias."""
    a = unquote(alias).strip()
    if a in _player_aliases:
        del _player_aliases[a]
        _save_player_aliases()
    return {"aliases": _player_aliases}


@app.get("/api/players/similar")
def get_similar_players(
    name: str = Query(..., description="Player name to find similar"),
    limit: int = Query(10, ge=1, le=50),
):
    """Suggest players with similar names (for merging)."""
    name_norm = _normalize_search(name)
    names = set((d.get("player") or "").strip() for d in _decks if (d.get("player") or "").strip())
    names.discard("")
    names.discard("(unknown)")
    # Simple similarity: same last word, or one contains the other (accent-insensitive)
    def score(n: str) -> int:
        nn = _normalize_search(n)
        if nn == name_norm:
            return 0
        if name_norm in nn or nn in name_norm:
            return 1
        name_words = set(name_norm.split())
        n_words = set(nn.split())
        overlap = len(name_words & n_words)
        return 10 - overlap if overlap > 0 else 99
    sorted_names = sorted(names, key=score)
    return {"similar": [n for n in sorted_names if score(n) < 99][:limit]}


@app.get("/api/players")
def get_players(
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Player leaderboard (wins, top-2, top-4, points). Merges aliased players."""
    if not _decks:
        return {"players": []}
    filtered = _filter_decks_by_date(_decks, date_from, date_to)
    decks = [Deck.from_dict(d) for d in filtered]
    return {"players": player_leaderboard(decks, normalize_player=_normalize_player)}


@app.get("/api/players/{player_name:path}")
def get_player_detail(player_name: str):
    """Player stats and their decks. Merges aliased players (e.g. Pablo Tomas Pesci = Tomas Pesci)."""
    name = unquote(player_name).strip()
    canonical = _normalize_player(name)
    player_decks = [d for d in _decks if _normalize_player(d.get("player") or "") == canonical]
    if not player_decks:
        raise HTTPException(status_code=404, detail="Player not found")
    decks = [Deck.from_dict(d) for d in player_decks]
    stats_list = player_leaderboard(decks)
    if not stats_list:
        raise HTTPException(status_code=404, detail="Player not found")
    stat = stats_list[0]
    deck_summaries = [
        {"deck_id": d.get("deck_id"), "name": d.get("name"), "event_name": d.get("event_name"), "date": d.get("date"), "rank": d.get("rank")}
        for d in player_decks
    ]
    deck_summaries.sort(key=lambda x: _deck_sort_key(x))
    return {
        "player": canonical,
        "wins": stat["wins"],
        "top2": stat["top2"],
        "top4": stat["top4"],
        "top8": stat["top8"],
        "points": stat["points"],
        "deck_count": stat["deck_count"],
        "decks": deck_summaries,
    }


class LoadBody(BaseModel):
    decks: list[dict] | None = None
    path: str | None = None


@app.post("/api/load")
async def load_decks(
    body: LoadBody | None = None,
    file: UploadFile | None = File(None),
    _: str = Depends(require_admin),
):
    """Load decks from JSON. Body: { "decks": [...] } or { "path": "decks.json" }, or upload file."""
    global _decks
    if file:
        content = await file.read()
        try:
            _decks = _normalize_split_cards(json.loads(content.decode("utf-8")))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    elif body:
        if body.decks is not None:
            _decks = _normalize_split_cards(body.decks)
        elif body.path:
            path = Path(body.path)
            if not path.is_absolute():
                path = DATA_DIR / path
            if not path.exists():
                raise HTTPException(status_code=404, detail=f"File not found: {path}")
            _load_from_file(str(path))
        else:
            raise HTTPException(status_code=400, detail="Provide 'decks' array or 'path'")
    else:
        raise HTTPException(status_code=400, detail="Provide JSON body or file upload")
    _invalidate_metagame()
    return {"loaded": len(_decks), "message": f"Loaded {len(_decks)} decks"}


@app.get("/api/export")
def export_decks(_: str = Depends(require_admin)):
    """Download current scraped/loaded data as JSON (same format as load accepts)."""
    if not _decks:
        raise HTTPException(status_code=404, detail="No data to export. Scrape or load data first.")
    body = json.dumps(_decks, indent=2, ensure_ascii=False).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="decks.json"'},
    )


@app.post("/api/analyze")
def run_analyze():
    """Re-run analysis (no-op, metagame is computed on demand)."""
    _invalidate_metagame()
    return {"message": "Analysis will be recomputed on next /api/metagame request"}


class ScrapeBody(BaseModel):
    format: str = "EDH"
    period: str | None = None
    store: str | None = None
    event_ids: str | list[int] | None = None


@app.post("/api/scrape")
async def run_scrape(body: ScrapeBody, _: str = Depends(require_admin)):
    """Trigger scrape with SSE progress streaming."""
    import queue
    import re

    format_id = body.format
    period = body.period
    store = body.store
    event_ids = body.event_ids
    if isinstance(event_ids, str):
        event_ids = [int(x.strip()) for x in event_ids.split(",") if x.strip()] or None

    q: queue.Queue[str | None] = queue.Queue()
    result_holder: list = []
    error_holder: list = []

    def on_progress(msg: str) -> None:
        q.put(msg)

    def run_scraper() -> None:
        try:
            decks = scrape(
                format_id=format_id,
                period=period,
                store=store,
                event_ids=event_ids,
                on_progress=on_progress,
            )
            result_holder.append(decks)
        except Exception as e:
            error_holder.append(str(e))
        finally:
            q.put(None)

    thread = threading.Thread(target=run_scraper, daemon=True)
    thread.start()

    def event_stream():
        global _decks
        total_events = 0
        current_event = 0
        total_decks_in_event = 0
        current_deck_in_event = 0
        while True:
            try:
                msg = q.get(timeout=300)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Timeout'})}\n\n"
                return
            if msg is None:
                break

            pct = 0
            events_match = re.search(r"Found (\d+) events", msg)
            if events_match:
                total_events = int(events_match.group(1))

            event_match = re.match(r"\[(\d+)/(\d+)\]", msg)
            if event_match:
                current_event = int(event_match.group(1))
                total_events = int(event_match.group(2))

            deck_found = re.search(r"Found (\d+) decks", msg)
            if deck_found:
                total_decks_in_event = int(deck_found.group(1))
                current_deck_in_event = 0

            deck_parse = re.search(r"Parsing deck (\d+)/(\d+)", msg)
            if deck_parse:
                current_deck_in_event = int(deck_parse.group(1))
                total_decks_in_event = int(deck_parse.group(2))

            if total_events > 0:
                event_pct = ((current_event - 1) / total_events) * 100 if current_event > 0 else 0
                if total_decks_in_event > 0 and current_event > 0:
                    deck_pct = (current_deck_in_event / total_decks_in_event) * (100 / total_events)
                    pct = event_pct + deck_pct
                else:
                    pct = event_pct
                pct = min(pct, 99)

            yield f"data: {json.dumps({'type': 'progress', 'message': msg, 'pct': round(pct, 1)})}\n\n"

        if error_holder:
            yield f"data: {json.dumps({'type': 'error', 'message': error_holder[0]})}\n\n"
        elif result_holder:
            decks = result_holder[0]
            _decks = [d.to_dict() for d in decks]
            _invalidate_metagame()
            yield f"data: {json.dumps({'type': 'done', 'message': f'Scraped {len(decks)} decks', 'loaded': len(decks), 'pct': 100})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Unknown error'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# Serve built frontend (production); static dir is populated by Dockerfile
STATIC_DIR = _project_root / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
    _index_path = STATIC_DIR / "index.html"

    @app.get("/", include_in_schema=False)
    def serve_index():
        if _index_path.exists():
            return FileResponse(_index_path)
        raise StarletteHTTPException(status_code=404)

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            raise StarletteHTTPException(status_code=404)
        if _index_path.exists():
            return FileResponse(_index_path)
        raise StarletteHTTPException(status_code=404)

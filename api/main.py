"""FastAPI backend for MTG Metagame web app."""

import json
import threading
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Import from project - run from project root
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mtgtop8.analyzer import analyze, deck_analysis, player_leaderboard
from src.mtgtop8.card_lookup import lookup_cards
from src.mtgtop8.models import Deck
from src.mtgtop8.scraper import scrape

app = FastAPI(title="MTG Metagame API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage
_decks: list[dict] = []
_metagame_cache: dict | None = None


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
_startup_path = Path(__file__).resolve().parent.parent / "decks.json"
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


class CardLookupBody(BaseModel):
    names: list[str] = []


@app.post("/api/cards/lookup")
def cards_lookup(body: CardLookupBody):
    """Look up card metadata and images from Scryfall."""
    if not body.names:
        return {}
    return lookup_cards(body.names)


@app.get("/api/decks")
def list_decks(
    event_id: int | None = Query(None, description="Filter by event ID"),
    commander: str | None = Query(None, description="Filter by commander name (substring)"),
    deck_name: str | None = Query(None, description="Filter by deck name (substring)"),
    player: str | None = Query(None, description="Filter by player name (substring)"),
    card: str | None = Query(None, description="Filter by card name (substring, commander, mainboard or sideboard)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List decks with optional filters and pagination."""
    filtered = _decks
    if event_id is not None:
        filtered = [d for d in filtered if d.get("event_id") == event_id]
    if commander:
        c_lower = commander.lower()
        filtered = [
            d for d in filtered
            if any(c_lower in (c or "").lower() for c in d.get("commanders", []))
        ]
    if deck_name:
        dn_lower = deck_name.lower()
        filtered = [d for d in filtered if dn_lower in (d.get("name") or "").lower()]
    if player:
        p_lower = player.lower()
        filtered = [d for d in filtered if p_lower in (d.get("player") or "").lower()]
    if card:
        card_lower = card.lower().strip()
        filtered = [
            d for d in filtered
            if any(card_lower in (c or "").lower() for c in d.get("commanders", []))
            or any(
                card_lower in ((e.get("card") if isinstance(e, dict) else "") or "").lower()
                for section in (d.get("mainboard", []), d.get("sideboard", []))
                for e in section
            )
        ]
    filtered = sorted(filtered, key=_deck_sort_key)
    total = len(filtered)
    page = filtered[skip : skip + limit]
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
        result.append(deck_map[did])
    return {"decks": result}


@app.get("/api/decks/{deck_id}")
def get_deck(deck_id: int):
    """Get single deck by ID."""
    for d in _decks:
        if d.get("deck_id") == deck_id:
            return d
    raise HTTPException(status_code=404, detail="Deck not found")


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
    event_id: int | None = Query(None, description="Filter by event ID"),
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
    if event_id is not None:
        filtered = [d for d in filtered if d.get("event_id") == event_id]
    filtered = _filter_decks_by_date(filtered, date_from, date_to)
    decks = [Deck.from_dict(d) for d in filtered]
    return analyze(decks, placement_weighted=placement_weighted, ignore_lands=ignore_lands)


@app.get("/api/players")
def get_players(
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Player leaderboard (wins, top-2, top-4, points)."""
    if not _decks:
        return {"players": []}
    filtered = _filter_decks_by_date(_decks, date_from, date_to)
    decks = [Deck.from_dict(d) for d in filtered]
    return {"players": player_leaderboard(decks)}


@app.get("/api/players/{player_name:path}")
def get_player_detail(player_name: str):
    """Player stats and their decks."""
    name = unquote(player_name)
    player_decks = [d for d in _decks if (d.get("player") or "").strip() == name]
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
        "player": stat["player"],
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
async def load_decks(body: LoadBody | None = None, file: UploadFile | None = File(None)):
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
                path = Path(__file__).resolve().parent.parent / path
            if not path.exists():
                raise HTTPException(status_code=404, detail=f"File not found: {path}")
            _load_from_file(str(path))
        else:
            raise HTTPException(status_code=400, detail="Provide 'decks' array or 'path'")
    else:
        raise HTTPException(status_code=400, detail="Provide JSON body or file upload")
    _invalidate_metagame()
    return {"loaded": len(_decks), "message": f"Loaded {len(_decks)} decks"}


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
async def run_scrape(body: ScrapeBody):
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

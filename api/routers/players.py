import logging
import math
import secrets
from datetime import datetime
from urllib.parse import unquote

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import case, func
from src.mtgtop8.analyzer import (
    archetype_aggregate_analysis,
    archetype_distribution,
    effective_commanders,
    effective_mainboard,
    is_top8,
    normalize_rank,
    player_leaderboard,
)
from src.mtgtop8.card_lookup import lookup_cards
from src.mtgtop8.models import Deck
from src.mtgtop8.scraper import event_display_name

from api.dependencies import (
    require_admin,
    require_database,
)
from api.helpers import (
    _deck_sort_key,
    _filter_decks_by_date,
    _normalize_search,
    _parse_date_sortkey,
)
from api.schemas.players import (
    PlayerAliasBody,
    PlayerAnalysisResponse,
    PlayerEmailBody,
)
from api.services import settings as settings_service
from api.state import (
    _load_decks_from_db,
    _load_player_aliases,
    _normalize_player,
    _save_player_aliases,
    state,
)

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

from api.route_helpers import (
    _upload_link_base_url,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.put("/api/v1/player-emails", dependencies=[Depends(require_admin), Depends(require_database)])
def put_player_email(body: PlayerEmailBody):
    """Set or replace the email for a player (admin-only). Empty email deletes. Response never contains email."""
    player = (body.player or "").strip()
    if not player:
        raise HTTPException(status_code=400, detail="player is required")
    canonical = _normalize_player(player)
    with _db.session_scope() as session:
        _db.set_player_email(session, canonical, body.email or "")
    return {"ok": True}


@router.post("/api/v1/players/{player_name:path}/send-missing-deck-links", dependencies=[Depends(require_admin), Depends(require_database)])
def send_player_missing_deck_links(player_name: str, request: Request):
    """Email one-time deck upload links for all of this player's missing (empty) decks. Uses DB-stored email. 503 if email not configured."""
    try:
        from api import email as _email
    except ImportError:
        raise HTTPException(status_code=503, detail="Email not configured")
    if not _email.is_email_configured():
        raise HTTPException(
            status_code=503,
            detail="Email not configured: set Brevo SMTP (SMTP_HOST, SMTP_USER, SMTP_PASSWORD) or Brevo API (BREVO_API_KEY + SMTP_FROM). See .env.example.",
        )
    name = (player_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Player name required")
    canonical = _resolve_player_name_to_canonical(name)
    players_to_match = [canonical] + [k for k, v in state.player_aliases.items() if v == canonical]
    base_url = _upload_link_base_url(request)
    with _db.session_scope() as session:
        addr = _db.get_player_email(session, canonical)
        if not addr or not addr.strip():
            raise HTTPException(status_code=400, detail="No email set for this player. Set email on this page first.")
        decks = session.query(_db.DeckRow).filter(_db.DeckRow.player.in_(players_to_match)).all()
        missing = []
        for d in decks:
            main = getattr(d, "mainboard", None) or []
            if not (isinstance(main, list) and len(main) > 0):
                missing.append(d)
        if not missing:
            return {"sent": 0, "message": "No missing decks for this player"}
        links_by_event = {}
        for deck_row in missing:
            eid = deck_row.event_id
            _db.invalidate_upload_links_for_slot(session, eid, _db.LINK_TYPE_DECK_UPDATE, deck_id=deck_row.deck_id)
            token = secrets.token_urlsafe(32)
            _db.create_upload_link(
                session, token, eid, deck_id=deck_row.deck_id, link_type=_db.LINK_TYPE_DECK_UPDATE
            )
            url = f"{base_url}/upload/{token}"
            if eid not in links_by_event:
                ev = _db.get_event(session, eid)
                event_name = event_display_name(
                    ev.name or "", getattr(ev, "store", "") or "", getattr(ev, "location", "") or ""
                ) if ev else eid
                links_by_event[eid] = {"event_name": event_name, "links": []}
            links_by_event[eid]["links"].append(url)
        body_parts = ["You have missing deck lists. Use the link(s) below (each is one-time):", ""]
        for eid, info in links_by_event.items():
            body_parts.append(f"{info['event_name']}:")
            for url in info["links"]:
                body_parts.append(url)
            body_parts.append("")
        subject = "Deck upload links (missing decks)"
        body = "\n".join(body_parts).strip()
        try:
            _email.send_email(addr, subject, body)
        except Exception as e:
            logger.exception("Send player missing-deck email failed for %s", canonical)
            raise HTTPException(status_code=500, detail="Failed to send email") from e
        return {"sent": 1}


@router.get("/api/v1/player-aliases")
def get_player_aliases():
    """List player alias mappings (alias -> canonical)."""
    return {"aliases": state.player_aliases}


@router.post("/api/v1/player-aliases")
def add_player_alias(body: PlayerAliasBody, _: str = Depends(require_admin)):
    """Merge player: map alias to canonical name. E.g. {'alias': 'Pablo Tomas Pesci', 'canonical': 'Tomas Pesci'}."""
    alias = body.alias.strip()
    canonical = body.canonical.strip()
    if not alias or not canonical:
        raise HTTPException(status_code=400, detail="alias and canonical required")
    state.player_aliases[alias] = canonical
    _save_player_aliases()
    # If DB is available, also persist alias + merge historical data there
    if state.database_available():
        try:
            with _db.session_scope() as session:
                _db.set_player_alias(session, alias, canonical)
                _db.merge_players_by_names(session, alias, canonical)
        except Exception as e:
            logger.exception("Failed to save/merge player alias to DB: %s", e)
        else:
            _load_player_aliases()
            _load_decks_from_db()
    return {"aliases": state.player_aliases}


@router.delete("/api/v1/player-aliases/{alias:path}")
def remove_player_alias(alias: str, _: str = Depends(require_admin)):
    """Remove a player alias."""
    a = unquote(alias).strip()
    if a in state.player_aliases:
        del state.player_aliases[a]
        if state.database_available():
            try:
                with _db.session_scope() as session:
                    _db.remove_player_alias(session, a)
            except Exception as e:
                logger.exception("Failed to remove player alias from DB: %s", e)
            else:
                _load_player_aliases()
                _load_decks_from_db()
        _save_player_aliases()
    return {"aliases": state.player_aliases}


@router.get("/api/v1/players/similar")
def get_similar_players(
    name: str = Query(..., description="Player name to find similar"),
    limit: int = Query(10, ge=1, le=50),
):
    """Suggest players with similar names (for merging)."""
    name_norm = _normalize_search(name)
    names = set((d.get("player") or "").strip() for d in state.decks if (d.get("player") or "").strip())
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


@router.get("/api/v1/players")
def get_players(
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    player_id: int | None = Query(None, description="Filter to a single player by ID (exact)"),
):
    """Player leaderboard (wins, top-2, top-4, points). Merges aliased players. Includes player_id for stable links."""
    if not state.decks:
        return {"players": []}
    filtered = _filter_decks_by_date(state.decks, date_from, date_to)
    if player_id is not None:
        filtered = [d for d in filtered if d.get("player_id") == player_id]
    decks = [Deck.from_dict(d) for d in filtered]
    rank_weights = settings_service.get_rank_weights()
    players = player_leaderboard(decks, normalize_player=_normalize_player, rank_weights=rank_weights)
    for p in players:
        canonical = p.get("player") or ""
        p["player_id"] = next((d.get("player_id") for d in filtered if _normalize_player(d.get("player") or "") == canonical), None)
    if player_id is not None:
        players = [p for p in players if p.get("player_id") == player_id]
    # Attach recorded-match win% (date-filtered when a range is active).
    date_filtered = date_from is not None or date_to is not None or player_id is not None
    deck_ids = (
        [d.get("deck_id") for d in filtered if d.get("deck_id") is not None] if date_filtered else None
    )
    winrate_by_player = _match_winrate_by_player(deck_ids)
    for p in players:
        ms = winrate_by_player.get(p.get("player_id")) if p.get("player_id") is not None else None
        p["recorded_matches"] = ms["recorded_matches"] if ms else 0
        p["match_win_pct"] = ms["match_win_pct"] if ms else None
    return {"players": players}


def _empty_player_stats() -> dict:
    return {"wins": 0, "top2": 0, "top4": 0, "top8": 0, "points": 0.0, "deck_count": 0}


def _player_match_stats(deck_ids: list[int]) -> dict:
    """Aggregate recorded per-match results (W/L/D) across the given decks.

    Reads `MatchupRow` from the DB; the deck_ids should already be date-filtered
    so the win% stays consistent with the rest of the (date-ranged) payload.
    """
    empty = {"recorded_matches": 0, "match_wins": 0, "match_losses": 0, "match_draws": 0, "match_win_pct": 0.0}
    if not deck_ids or not state.database_available():
        return empty
    with _db.session_scope() as session:
        rows = (
            session.query(_db.MatchupRow.result)
            .filter(_db.MatchupRow.deck_id.in_(deck_ids))
            .filter(_db.MatchupRow.result.in_(["win", "loss", "draw", "intentional_draw"]))
            .all()
        )
    total = len(rows)
    if not total:
        return empty
    wins = sum(1 for (r,) in rows if (r or "").lower() == "win")
    losses = sum(1 for (r,) in rows if (r or "").lower() == "loss")
    return {
        "recorded_matches": total,
        "match_wins": wins,
        "match_losses": losses,
        "match_draws": total - wins - losses,
        "match_win_pct": round(wins / total * 100, 1),
    }


def _match_winrate_by_player(deck_ids: list[int] | None) -> dict[int, dict]:
    """Map player_id -> {recorded_matches, match_win_pct} from MatchupRow.

    Aggregated in SQL grouped by player_id. If deck_ids is given (date-filtered
    view), restrict to those decks so the win% matches the filtered leaderboard;
    pass None to aggregate across all decks.
    """
    if not state.database_available():
        return {}
    if deck_ids is not None and not deck_ids:
        return {}
    wins_expr = func.sum(case((func.lower(_db.MatchupRow.result) == "win", 1), else_=0))
    with _db.session_scope() as session:
        q = (
            session.query(_db.DeckRow.player_id, func.count().label("total"), wins_expr.label("wins"))
            .join(_db.MatchupRow, _db.MatchupRow.deck_id == _db.DeckRow.deck_id)
            .filter(_db.MatchupRow.result.in_(["win", "loss", "draw", "intentional_draw"]))
            .filter(_db.DeckRow.player_id.isnot(None))
        )
        if deck_ids is not None:
            q = q.filter(_db.DeckRow.deck_id.in_(deck_ids))
        rows = q.group_by(_db.DeckRow.player_id).all()
    out: dict[int, dict] = {}
    for pid, total, wins in rows:
        total = int(total or 0)
        if not total:
            continue
        out[pid] = {
            "recorded_matches": total,
            "match_win_pct": round(int(wins or 0) / total * 100, 1),
        }
    return out


def _player_detail_payload(
    all_player_decks: list[dict],
    display: str,
    player_id: int | None,
    date_from: str | None,
    date_to: str | None,
) -> dict:
    """Build the shared payload for both /players/id/{id} and /players/{name} endpoints.

    When date filters are provided, stats are computed on the filtered subset. If
    the player exists but has no decks in range, returns zero-valued stats with
    an empty decks list (instead of 404).
    """
    player_decks = _filter_decks_by_date(all_player_decks, date_from, date_to)
    rank_weights = settings_service.get_rank_weights()
    decks = [Deck.from_dict(d) for d in player_decks]
    stats_list = player_leaderboard(decks, rank_weights=rank_weights) if decks else []
    stat = stats_list[0] if stats_list else _empty_player_stats()
    deck_summaries = [
        {"deck_id": d.get("deck_id"), "name": d.get("name"), "event_name": d.get("event_name"), "date": d.get("date"), "rank": d.get("rank")}
        for d in player_decks
    ]
    deck_summaries.sort(key=lambda x: _deck_sort_key(x))
    match_stats = _player_match_stats([d.get("deck_id") for d in player_decks if d.get("deck_id") is not None])
    return {
        "player": display,
        "player_id": player_id,
        "wins": stat["wins"],
        "top2": stat["top2"],
        "top4": stat["top4"],
        "top8": stat["top8"],
        "points": stat["points"],
        "deck_count": stat["deck_count"],
        "decks": deck_summaries,
        **match_stats,
    }


@router.get("/api/v1/players/id/{player_id:int}")
def get_player_detail_by_id(
    player_id: int,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Player stats and their decks by stable player_id. Optional date range."""
    all_player_decks = [d for d in state.decks if d.get("player_id") == player_id]
    if not all_player_decks:
        raise HTTPException(status_code=404, detail="Player not found")
    display = _normalize_player((all_player_decks[0].get("player") or "").strip())
    out = _player_detail_payload(all_player_decks, display, player_id, date_from, date_to)
    if state.database_available():
        with _db.session_scope() as session:
            prow = _db.get_player_by_id(session, player_id)
            if prow and (prow.display_name or "").strip():
                display = (prow.display_name or "").strip()
                out["player"] = display
            email = _db.get_player_email(session, display)
            out["has_email"] = bool(email and email.strip())
    return out


def _resolve_player_name_to_canonical(name: str) -> str:
    """Resolve a requested player name (e.g. from URL) to the canonical display name, accent-insensitive.
    So 'matias' finds the player whose canonical name is 'Matías'."""
    if not name or not name.strip():
        return name or ""
    name = name.strip()
    canonicals = {_normalize_player(d.get("player") or "") for d in state.decks if (d.get("player") or "").strip()}
    canonical = _normalize_player(name)
    if canonical in canonicals:
        return canonical
    name_norm = _normalize_search(name)
    for c in canonicals:
        if _normalize_search(c) == name_norm:
            return c
    return canonical


@router.get("/api/v1/players/id/{player_id:int}/analysis", response_model=PlayerAnalysisResponse)
def get_player_analysis_by_id(
    player_id: int,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Aggregated analytics for the player dashboard by stable player_id. Optional date range."""
    player_decks = [d for d in state.decks if d.get("player_id") == player_id]
    if not player_decks:
        raise HTTPException(status_code=404, detail="Player not found")
    display = _normalize_player((player_decks[0].get("player") or "").strip())
    if state.database_available():
        try:
            with _db.session_scope() as session:
                prow = _db.get_player_by_id(session, player_id)
                if prow and (prow.display_name or "").strip():
                    display = (prow.display_name or "").strip()
        except Exception:
            logger.exception("DB lookup failed for player analysis display name")
    return _player_analysis_cached(player_decks, display, player_id, date_from, date_to)


@router.get("/api/v1/players/{player_name:path}/analysis", response_model=PlayerAnalysisResponse)
def get_player_analysis_by_name(
    player_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Aggregated analytics for the player dashboard by name (alias-resolved). Optional date range."""
    name = unquote(player_name).strip()
    # If the name ends with "/analysis" because of path matching quirks, strip it.
    if name.endswith("/analysis"):
        name = name[: -len("/analysis")].strip()
    canonical = _resolve_player_name_to_canonical(name)
    player_decks = [d for d in state.decks if _normalize_player(d.get("player") or "") == canonical]
    if not player_decks:
        raise HTTPException(status_code=404, detail="Player not found")
    pid = player_decks[0].get("player_id")
    display = _normalize_player(canonical)
    if state.database_available() and pid is not None:
        try:
            with _db.session_scope() as session:
                prow = _db.get_player_by_id(session, pid)
                if prow and (prow.display_name or "").strip():
                    display = (prow.display_name or "").strip()
        except Exception:
            logger.exception("DB lookup failed for player analysis display name")
    return _player_analysis_cached(player_decks, display, pid, date_from, date_to)


@router.get("/api/v1/players/id/{player_id}/head-to-head", dependencies=[Depends(require_database)])
def get_player_head_to_head(player_id: int):
    """All opponents with aggregated W/L/D record for a given player."""
    with _db.session_scope() as session:
        rows = (
            session.query(_db.MatchupRow, _db.DeckRow)
            .join(_db.DeckRow, _db.MatchupRow.deck_id == _db.DeckRow.deck_id)
            .filter(_db.DeckRow.player_id == player_id)
            .filter(_db.MatchupRow.opponent_player_id.isnot(None))
            .filter(_db.MatchupRow.result.in_(["win", "loss", "draw", "intentional_draw"]))
            .all()
        )

    if not rows:
        return {"player_id": player_id, "opponents": []}

    # Aggregate per opponent
    opp_stats: dict[int, dict] = {}
    for matchup, deck in rows:
        oid = matchup.opponent_player_id
        if oid not in opp_stats:
            opp_stats[oid] = {
                "opponent_player_id": oid,
                "opponent_player": matchup.opponent_player or "",
                "wins": 0, "losses": 0, "draws": 0,
                "matches": 0,
                "formats": {},
            }
        s = opp_stats[oid]
        s["matches"] += 1
        result = (matchup.result or "").lower()
        if result == "win":
            s["wins"] += 1
        elif result == "loss":
            s["losses"] += 1
        else:
            s["draws"] += 1
        fmt = deck.format_id or "Unknown"
        if fmt not in s["formats"]:
            s["formats"][fmt] = {"wins": 0, "losses": 0, "draws": 0}
        if result == "win":
            s["formats"][fmt]["wins"] += 1
        elif result == "loss":
            s["formats"][fmt]["losses"] += 1
        else:
            s["formats"][fmt]["draws"] += 1

    # Build response list, sorted by matches desc
    opponents = []
    for s in opp_stats.values():
        total = s["matches"]
        win_pct = round(s["wins"] / total * 100, 1) if total else 0.0
        opponents.append({
            "opponent_player_id": s["opponent_player_id"],
            "opponent_player": s["opponent_player"],
            "wins": s["wins"],
            "losses": s["losses"],
            "draws": s["draws"],
            "matches": total,
            "win_pct": win_pct,
            "formats": [
                {"format_id": fmt, **counts}
                for fmt, counts in sorted(s["formats"].items())
            ],
        })

    opponents.sort(key=lambda x: x["matches"], reverse=True)
    return {"player_id": player_id, "opponents": opponents}


@router.get("/api/v1/players/id/{player_id}/head-to-head/{opponent_id}", dependencies=[Depends(require_database)])
def get_player_head_to_head_detail(player_id: int, opponent_id: int):
    """Full per-match encounter history between two players."""
    with _db.session_scope() as session:
        rows = (
            session.query(_db.MatchupRow, _db.DeckRow)
            .join(_db.DeckRow, _db.MatchupRow.deck_id == _db.DeckRow.deck_id)
            .filter(_db.DeckRow.player_id == player_id)
            .filter(_db.MatchupRow.opponent_player_id == opponent_id)
            .filter(_db.MatchupRow.result.in_(["win", "loss", "draw", "intentional_draw"]))
            .all()
        )

    if not rows:
        return {"player_id": player_id, "opponent_id": opponent_id, "matches": []}

    # Look up display names from state.decks
    def _display_name(pid: int) -> str:
        for d in state.decks:
            if d.get("player_id") == pid:
                return d.get("player") or ""
        return ""

    opponent_name = _display_name(opponent_id)

    encounters = []
    for matchup, deck in rows:
        # Look up opponent deck archetype from state.decks
        opp_archetype = matchup.opponent_archetype
        if opp_archetype is None and matchup.opponent_deck_id is not None:
            opp_d = next((d for d in state.decks if d.get("deck_id") == matchup.opponent_deck_id), None)
            if opp_d:
                opp_archetype = opp_d.get("archetype")

        encounters.append({
            "deck_id": deck.deck_id,
            "event_id": deck.event_id,
            "event_name": deck.event_name or "",
            "date": deck.date or "",
            "format_id": deck.format_id or "",
            "round": matchup.round,
            "result": matchup.result,
            "player_archetype": deck.archetype,
            "opponent_deck_id": matchup.opponent_deck_id,
            "opponent_archetype": opp_archetype,
        })

    # Sort by date descending
    encounters.sort(key=lambda x: _parse_date_sortkey(x["date"] or ""), reverse=True)

    wins = sum(1 for e in encounters if e["result"] == "win")
    losses = sum(1 for e in encounters if e["result"] == "loss")
    draws = sum(1 for e in encounters if e["result"] in ("draw", "intentional_draw"))

    return {
        "player_id": player_id,
        "opponent_id": opponent_id,
        "opponent_player": opponent_name,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "matches": encounters,
    }


@router.get("/api/v1/players/{player_name:path}")
def get_player_detail(
    player_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Player stats and their decks. Merges aliased players (e.g. Pablo Tomas Pesci = Tomas Pesci). Accent-insensitive: matias finds Matías."""
    name = unquote(player_name).strip()
    canonical = _resolve_player_name_to_canonical(name)
    all_player_decks = [d for d in state.decks if _normalize_player(d.get("player") or "") == canonical]
    if not all_player_decks:
        raise HTTPException(status_code=404, detail="Player not found")
    pid = all_player_decks[0].get("player_id")
    display = _normalize_player(canonical)
    out = _player_detail_payload(all_player_decks, display, pid, date_from, date_to)
    if state.database_available():
        with _db.session_scope() as session:
            if pid is not None:
                prow = _db.get_player_by_id(session, pid)
                if prow and (prow.display_name or "").strip():
                    display = (prow.display_name or "").strip()
                    out["player"] = display
            email = _db.get_player_email(session, display)
            out["has_email"] = bool(email and email.strip())
    return out


_NORMALIZED_RANK_MID = {
    "1": 1.0,
    "2": 2.0,
    "3-4": 3.5,
    "5-8": 6.5,
    "9-16": 12.5,
    "17-32": 24.5,
    "33-64": 48.5,
    "65-128": 96.5,
}


_COLOR_KEYS_FULL = ("W", "U", "B", "R", "G", "C")


_BASIC_LAND_NAMES = {
    "Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
    "Snow-Covered Mountain", "Snow-Covered Forest",
}


def _rank_numeric(rank: str) -> float | None:
    """Midpoint of the normalized rank band (e.g. '3-4' -> 3.5), or None."""
    nr = normalize_rank(rank or "")
    return _NORMALIZED_RANK_MID.get(nr)


def _best_rank(ranks: list[str]) -> str:
    """Return the best (lowest-numbered) rank string from a list."""
    best = None
    best_val = None
    for r in ranks:
        v = _rank_numeric(r)
        if v is None:
            continue
        if best_val is None or v < best_val:
            best = normalize_rank(r)
            best_val = v
    return best or ""


def _deck_color_identity(deck_obj: Deck, card_metadata: dict[str, dict]) -> list[str]:
    """Color identity for a deck, ordered WUBRG+C.

    EDH: derived from commander color identity (colorless EDH -> ['C']).
    Non-EDH: derived from mainboard cards' color identities.
    """
    is_edh = (deck_obj.format_id or "").upper() in {"EDH", "CEDH", "COMMANDER"}
    ci: set[str] = set()
    if is_edh:
        for name in effective_commanders(deck_obj):
            entry = card_metadata.get(name)
            if entry and "error" not in entry:
                for c in entry.get("color_identity") or entry.get("colors") or []:
                    if c in {"W", "U", "B", "R", "G"}:
                        ci.add(c)
        if not ci:
            ci.add("C")
    else:
        for _qty, card in effective_mainboard(deck_obj):
            entry = card_metadata.get(card)
            if not entry or "error" in entry:
                continue
            for c in entry.get("color_identity") or entry.get("colors") or []:
                if c in {"W", "U", "B", "R", "G"}:
                    ci.add(c)
        if not ci:
            ci.add("C")
    order = ["W", "U", "B", "R", "G", "C"]
    return [c for c in order if c in ci]


def _lookup_player_card_metadata(player_deck_objs: list[Deck]) -> dict[str, dict]:
    """Single Scryfall lookup for every unique card (commander + mainboard) across a player's decks."""
    names: set[str] = set()
    for d in player_deck_objs:
        for c in effective_commanders(d):
            if c:
                names.add(c)
        for _qty, card in effective_mainboard(d):
            if card:
                names.add(card)
    if not names:
        return {}
    try:
        return lookup_cards(list(names))
    except Exception:
        logger.exception("Card metadata lookup failed for player analysis")
        return {}


def _archetype_performance(player_deck_dicts: list[dict]) -> list[dict]:
    """Per-archetype: count, avg finish, best finish, top-8 %, win %."""
    buckets: dict[str, dict] = {}
    display_name: dict[str, str] = {}
    for d in player_deck_dicts:
        arch_raw = (d.get("archetype") or "").strip()
        if not arch_raw or arch_raw.lower() == "(unknown)":
            continue
        key = arch_raw.lower()
        display_name.setdefault(key, arch_raw)
        b = buckets.setdefault(key, {"ranks": [], "top8": 0, "wins": 0})
        b["ranks"].append(d.get("rank") or "")
        if is_top8(d.get("rank") or ""):
            b["top8"] += 1
        if normalize_rank(d.get("rank") or "") == "1":
            b["wins"] += 1
    rows: list[dict] = []
    for key, b in buckets.items():
        count = len(b["ranks"])
        nums = [v for v in (_rank_numeric(r) for r in b["ranks"]) if v is not None]
        avg_finish = round(sum(nums) / len(nums), 1) if nums else None
        rows.append({
            "archetype": display_name[key],
            "count": count,
            "avg_finish": avg_finish,
            "best_finish": _best_rank(b["ranks"]),
            "top8_pct": round(100 * b["top8"] / count, 1) if count else 0.0,
            "win_pct": round(100 * b["wins"] / count, 1) if count else 0.0,
        })
    rows.sort(key=lambda r: (-r["count"], r["archetype"].lower()))
    return rows


def _color_count_distribution(color_identities: list[list[str]]) -> dict[str, int]:
    """Bucket decks by number of distinct non-colorless colors. Colorless decks bucket to 0."""
    out: dict[str, int] = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    for ci in color_identities:
        non_c = [c for c in ci if c != "C"]
        n = len(non_c)
        if n > 5:
            n = 5
        out[str(n)] += 1
    return out


def _format_distribution(player_deck_dicts: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for d in player_deck_dicts:
        fid = (d.get("format_id") or "").strip() or "?"
        counts[fid] = counts.get(fid, 0) + 1
    total = sum(counts.values()) or 1
    rows = [
        {"format_id": fid, "count": c, "pct": round(100 * c / total, 1)}
        for fid, c in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
    return rows


def _commander_distribution_edh(player_deck_objs: list[Deck]) -> list[dict]:
    """Top commanders, EDH-only. Empty for non-EDH players."""
    counts: dict[str, int] = {}
    for d in player_deck_objs:
        if (d.format_id or "").upper() not in {"EDH", "CEDH", "COMMANDER"}:
            continue
        ec = effective_commanders(d)
        key = " / ".join(sorted(ec)) if ec else "(no commander)"
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values()) or 1
    return [
        {"commander": c, "count": n, "pct": round(100 * n / total, 1)}
        for c, n in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


def _top_cards_for_player(
    player_deck_objs: list[Deck],
    ignore_cards: set[str],
    limit: int = 20,
) -> tuple[list[dict], list[dict]]:
    """Returns (top_cards, pet_cards) across the player's mainboards (excluding basic lands & ignore list)."""
    deck_count = len(player_deck_objs)
    card_decks: dict[str, set[int]] = {}
    card_copies: dict[str, int] = {}
    for d in player_deck_objs:
        seen_in_deck: set[str] = set()
        for qty, card in effective_mainboard(d):
            if card in _BASIC_LAND_NAMES:
                continue
            if card in ignore_cards:
                continue
            card_copies[card] = card_copies.get(card, 0) + int(qty)
            seen_in_deck.add(card)
        for card in seen_in_deck:
            card_decks.setdefault(card, set()).add(d.deck_id)
    rows = [
        {"card": c, "deck_count": len(card_decks[c]), "total_copies": card_copies[c]}
        for c in card_decks
    ]
    rows.sort(key=lambda r: (-r["deck_count"], -r["total_copies"], r["card"].lower()))
    top_cards = rows[:limit]
    pet_threshold = max(3, math.ceil(deck_count * 0.3)) if deck_count else 3
    pet_cards = [r for r in rows if r["deck_count"] >= pet_threshold][:30]
    return top_cards, pet_cards


def _field_size_buckets(player_deck_dicts: list[dict]) -> list[dict]:
    bucket_defs = [("<32", 0, 31), ("32-100", 32, 100), ("100+", 101, 10**9)]
    buckets: dict[str, dict] = {b[0]: {"ranks": [], "top8": 0} for b in bucket_defs}
    for d in player_deck_dicts:
        pc = int(d.get("player_count") or 0)
        rank = d.get("rank") or ""
        for label, lo, hi in bucket_defs:
            if lo <= pc <= hi:
                buckets[label]["ranks"].append(rank)
                if is_top8(rank):
                    buckets[label]["top8"] += 1
                break
    rows: list[dict] = []
    for label, _lo, _hi in bucket_defs:
        b = buckets[label]
        count = len(b["ranks"])
        nums = [v for v in (_rank_numeric(r) for r in b["ranks"]) if v is not None]
        rows.append({
            "bucket": label,
            "count": count,
            "avg_finish": round(sum(nums) / len(nums), 1) if nums else None,
            "top8_pct": round(100 * b["top8"] / count, 1) if count else 0.0,
        })
    return rows


def _metagame_comparison(
    player_dist: list[dict],
    global_dist: list[dict],
    limit: int = 10,
) -> list[dict]:
    """For the player's top archetypes, return side-by-side player vs global pct."""
    global_by_key: dict[str, float] = {
        (row.get("archetype") or "").lower(): float(row.get("pct") or 0)
        for row in global_dist
    }
    out: list[dict] = []
    for row in player_dist[:limit]:
        name = row.get("archetype") or ""
        out.append({
            "archetype": name,
            "player_pct": float(row.get("pct") or 0),
            "global_pct": global_by_key.get(name.lower(), 0.0),
        })
    return out


def _highlights(per_event: list[dict]) -> dict:
    """Best finish, longest top-8 streak, biggest-field win, total events, cadence."""
    if not per_event:
        return {
            "best_finish": "",
            "longest_top8_streak": 0,
            "biggest_field_win": None,
            "total_events": 0,
            "avg_days_between_events": None,
            "first_event_date": None,
            "last_event_date": None,
        }
    ranks = [e.get("rank") or "" for e in per_event]
    best = _best_rank(ranks)
    # Longest top-8 streak across chronologically ordered events
    longest = current = 0
    for e in per_event:
        if is_top8(e.get("rank") or ""):
            current += 1
            if current > longest:
                longest = current
        else:
            current = 0
    # Biggest-field win: largest player_count where rank normalizes to "1"
    biggest_field_win: int | None = None
    for e in per_event:
        if normalize_rank(e.get("rank") or "") == "1":
            pc = int(e.get("player_count") or 0)
            if biggest_field_win is None or pc > biggest_field_win:
                biggest_field_win = pc
    # Cadence: avg days between distinct event dates
    date_strs = sorted({e.get("date") or "" for e in per_event if e.get("date")}, key=_parse_date_sortkey)
    avg_days: float | None = None
    if len(date_strs) >= 2:
        def _to_dt(ds: str) -> datetime | None:
            try:
                parts = ds.split("/")
                if len(parts) != 3:
                    return None
                dd, mm, yy = int(parts[0]), int(parts[1]), int(parts[2])
                year = 2000 + yy if yy < 100 else yy
                return datetime(year, mm, dd)
            except Exception:
                return None
        dts = [dt for dt in (_to_dt(s) for s in date_strs) if dt is not None]
        if len(dts) >= 2:
            gaps = [(dts[i] - dts[i - 1]).days for i in range(1, len(dts))]
            avg_days = round(sum(gaps) / len(gaps), 1) if gaps else None
    return {
        "best_finish": best,
        "longest_top8_streak": longest,
        "biggest_field_win": biggest_field_win,
        "total_events": len({e.get("event_id") for e in per_event if e.get("event_id") is not None}) or len(per_event),
        "avg_days_between_events": avg_days,
        "first_event_date": date_strs[0] if date_strs else None,
        "last_event_date": date_strs[-1] if date_strs else None,
    }


def _leaderboard_history_for_player(
    canonical: str,
    all_decks: list[dict],
    rank_weights: dict[str, float],
) -> list[dict]:
    """Snapshot the player's leaderboard rank at each date they had an event.

    Streaming algorithm: walk all decks in date order, accumulating per-player
    stats; after processing each date we snapshot the rank at target dates.
    O(D log D + E * P log P).
    """
    # Group decks by date in chronological order
    date_order = sorted(
        {d.get("date") or "" for d in all_decks if d.get("date")},
        key=_parse_date_sortkey,
    )
    target_dates = {
        d.get("date") or ""
        for d in all_decks
        if _normalize_player(d.get("player") or "") == canonical and d.get("date")
    }
    if not target_dates:
        return []
    by_date: dict[str, list[dict]] = {}
    for d in all_decks:
        ds = d.get("date") or ""
        if not ds:
            continue
        by_date.setdefault(ds, []).append(d)
    stats: dict[str, dict[str, float]] = {}
    snapshots: list[dict] = []
    for ds in date_order:
        for d in by_date.get(ds, []):
            raw = (d.get("player") or "").strip()
            if not raw or raw.lower() == "(unknown)":
                continue
            player = _normalize_player(raw)
            s = stats.setdefault(player, {"wins": 0.0, "points": 0.0})
            nr = normalize_rank(d.get("rank") or "")
            s["points"] += rank_weights.get(nr, 1.0)
            if nr == "1":
                s["wins"] += 1
        if ds in target_dates:
            sorted_players = sorted(
                stats.items(),
                key=lambda kv: (-kv[1]["wins"], -kv[1]["points"]),
            )
            rank = next(
                (i + 1 for i, (p, _s) in enumerate(sorted_players) if p == canonical),
                0,
            )
            snapshots.append({
                "date": ds,
                "rank": rank,
                "total_players": len(sorted_players),
            })
    return snapshots


def _build_player_analysis(
    player_deck_dicts: list[dict],
    all_decks: list[dict],
    canonical_display: str,
    player_id: int | None,
) -> dict:
    """Aggregate everything required by the Player Detail analytics dashboard."""
    deck_objs = [Deck.from_dict(d) for d in player_deck_dicts]
    rank_weights = settings_service.get_rank_weights()

    card_metadata = _lookup_player_card_metadata(deck_objs)

    # Per-event (deck) rows, sorted chronologically (ascending for time-series charts)
    per_event_rows: list[dict] = []
    color_identities: list[list[str]] = []
    for d, deck_obj in zip(player_deck_dicts, deck_objs):
        ci = _deck_color_identity(deck_obj, card_metadata)
        color_identities.append(ci)
        nr = normalize_rank(d.get("rank") or "")
        per_event_rows.append({
            "deck_id": d.get("deck_id"),
            "event_id": d.get("event_id"),
            "event_name": d.get("event_name") or "",
            "date": d.get("date") or "",
            "rank": d.get("rank") or "",
            "normalized_rank": nr,
            "normalized_rank_num": _rank_numeric(d.get("rank") or ""),
            "points": rank_weights.get(nr, 1.0),
            "player_count": int(d.get("player_count") or 0),
            "format_id": d.get("format_id") or "",
            "archetype": d.get("archetype"),
            "color_identity": ci,
            "commanders": list(d.get("commanders") or []),
        })
    per_event_rows.sort(key=lambda r: _parse_date_sortkey(r.get("date") or ""))

    # Distributions
    arch_dist = archetype_distribution(deck_objs)
    arch_perf = _archetype_performance(player_deck_dicts)

    color_count_dist = _color_count_distribution(color_identities)

    fmt_dist = _format_distribution(player_deck_dicts)
    cmd_dist = _commander_distribution_edh(deck_objs)

    # Average mana curve and color distribution across decks (reuse analyzer helper)
    aggregate = archetype_aggregate_analysis(deck_objs, card_metadata) if deck_objs else {}
    avg_mana_curve_raw = aggregate.get("mana_curve") or {}
    average_mana_curve = {str(k): float(v) for k, v in avg_mana_curve_raw.items()}
    color_distribution = {k: float(v) for k, v in (aggregate.get("color_distribution") or {}).items()}
    for k in _COLOR_KEYS_FULL:
        color_distribution.setdefault(k, 0.0)

    # Top cards / pet cards (exclude basics and configured ignore list)
    ignore_cards = set(settings_service.get_ignore_lands_cards() or [])
    top_cards, pet_cards = _top_cards_for_player(deck_objs, ignore_cards)

    field_buckets = _field_size_buckets(player_deck_dicts)

    # Global archetype distribution for comparison (full dataset)
    try:
        global_arch_dist = archetype_distribution([Deck.from_dict(d) for d in all_decks])
    except Exception:
        logger.exception("Global archetype distribution failed for player analysis")
        global_arch_dist = []
    meta_comparison = _metagame_comparison(arch_dist, global_arch_dist)

    highlights = _highlights(per_event_rows)

    # Leaderboard rank history (streaming)
    try:
        leaderboard_history = _leaderboard_history_for_player(
            canonical_display, all_decks, rank_weights,
        )
    except Exception:
        logger.exception("Leaderboard history failed for player %s", canonical_display)
        leaderboard_history = []

    return {
        "player": canonical_display,
        "player_id": player_id,
        "per_event": per_event_rows,
        "leaderboard_history": leaderboard_history,
        "archetype_distribution": [
            {"archetype": r["archetype"], "count": int(round(float(r["count"]))), "pct": float(r["pct"])}
            for r in arch_dist
        ],
        "archetype_performance": arch_perf,
        "color_distribution": color_distribution,
        "color_count_distribution": color_count_dist,
        "format_distribution": fmt_dist,
        "commander_distribution": cmd_dist,
        "average_mana_curve": average_mana_curve,
        "top_cards": top_cards,
        "pet_cards": pet_cards,
        "field_size_buckets": field_buckets,
        "metagame_comparison": meta_comparison,
        "highlights": highlights,
    }


_player_analysis_cache: dict[tuple, dict] = {}


def _player_analysis_cache_signature() -> tuple:
    weights = settings_service.get_rank_weights()
    weights_sig = tuple(sorted((str(k), float(v)) for k, v in (weights or {}).items()))
    # id(state.decks) plus len gives cheap invalidation on reload (new list) or append.
    return (id(state.decks), len(state.decks), weights_sig)


def _player_analysis_cached(
    player_deck_dicts: list[dict],
    canonical_display: str,
    player_id: int | None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    key = (
        _player_analysis_cache_signature(),
        player_id if player_id is not None else canonical_display,
        date_from or "",
        date_to or "",
    )
    cached = _player_analysis_cache.get(key)
    if cached is not None:
        return cached
    # Apply date filter consistently: the per_event rows, distributions, metagame
    # comparison and leaderboard-rank history are all computed relative to the
    # selected window so the dashboard stays internally consistent.
    filtered_player = _filter_decks_by_date(player_deck_dicts, date_from, date_to)
    filtered_all = _filter_decks_by_date(state.decks, date_from, date_to)
    result = _build_player_analysis(
        filtered_player, filtered_all, canonical_display, player_id,
    )
    # Bound cache size to avoid unbounded memory growth.
    if len(_player_analysis_cache) > 128:
        _player_analysis_cache.clear()
    _player_analysis_cache[key] = result
    return result

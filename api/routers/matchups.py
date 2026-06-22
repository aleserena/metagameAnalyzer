import logging

from fastapi import Depends, HTTPException, Query

from api.dependencies import (
    require_admin,
    require_database,
)
from api.schemas.matchups import PatchMatchupBody

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

from api.route_helpers import (
    _date_in_range,
    _is_intentional_draw_result,
    _matchup_result_to_canonical,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_effective_wld(result: str) -> tuple[int, int, int]:
    raw = (result or "loss").strip().lower()
    if raw == "intentional_draw":
        return (0, 0, 1)
    if raw == "intentional_draw_win":
        return (1, 0, 0)
    if raw == "intentional_draw_loss":
        return (0, 1, 0)
    canonical = _matchup_result_to_canonical(result or "loss")
    if canonical == "win":
        return (1, 0, 0)
    if canonical == "loss":
        return (0, 1, 0)
    return (0, 0, 1)


def _front_face_name(name: str) -> str:
    """Dual-faced style 'Front // Back' -> 'Front'. Unifies e.g. Norman Osborn and Norman Osborn // Green Goblin."""
    s = (name or "").strip()
    if not s or s in ("Bye", "(drop)"):
        return s or "(unknown)"
    if " // " in s:
        return s.split(" // ", 1)[0].strip() or s
    return s


@router.get("/api/v1/matchups/summary", dependencies=[Depends(require_database)], tags=["Matchups"])
def get_matchups_summary(
    format_id: str | None = Query(None),
    event_ids: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    archetype: list[str] | None = Query(None, description="Filter by archetype(s); repeated param per name; include matchups where both deck and opponent archetype are in this list"),
    min_matches: int = Query(0, ge=0, le=1_000_000, description="Minimum aggregated matches per archetype pair to include in list and matrix"),
    include_opponents_below_min: bool = Query(
        False,
        description="When min_matches > 0, still include pairs with at least one match but fewer than min_matches (matrix + list)",
    ),
):
    """Aggregated matchup summary by archetype. Optional filters.

    Query parameters:
    - format_id: filter by format (e.g. EDH)
    - event_ids: comma-separated event IDs
    - date_from/date_to: DD/MM/YY range filter
    - min_matches: hide pairs with fewer than this many aggregated matches (default 0)
    - include_opponents_below_min: if true and min_matches > 0, also show pairs with 1 .. min_matches-1 games
    """
    with _db.session_scope() as session:
        rows = _db.list_matchups_with_deck_info(session)

    event_id_set = None
    if event_ids:
        event_id_set = {x.strip() for x in event_ids.split(",") if x.strip()}

    archetype_set = None
    if archetype:
        archetype_set = {x.strip().lower() for x in archetype if (x or "").strip()}

    filtered = []
    for r in rows:
        if format_id and (r.get("format_id") or "").strip().upper() != format_id.strip().upper():
            continue
        if event_id_set is not None and (r.get("event_id") or "").strip() not in event_id_set:
            continue
        if not _date_in_range(r.get("date") or "", date_from, date_to):
            continue
        if archetype_set is not None:
            arch = (r.get("archetype") or "").strip()
            opp = (r.get("opponent_archetype") or "").strip()
            if arch.lower() not in archetype_set:
                continue
            # When multiple archetypes selected: only matchups between those archetypes. When single: show that archetype vs all.
            if len(archetype_set) > 1 and opp.lower() not in archetype_set:
                continue
        # Bye and drop count as rounds for validation but are not used in matchup calculations
        if (r.get("result") or "").strip().lower() in ("bye", "drop"):
            continue
        filtered.append(r)

    # One canonical display name per case-insensitive archetype to avoid duplicate matrix rows
    canonical_archetype: dict[str, str] = {}
    for r in filtered:
        for raw in [(r.get("archetype") or "").strip(), (r.get("opponent_archetype") or "").strip()]:
            if raw and raw.lower() not in ("bye", "drop"):
                canonical_archetype.setdefault(raw.lower(), raw)

    def to_effective_wld(row):
        return _to_effective_wld(row.get("result") or "loss")

    def norm_arch(name: str) -> str:
        return canonical_archetype.get((name or "").lower(), name or "(unknown)")

    def add_to_agg(arch: str, opp: str, wins: int, losses: int, draws: int, is_intentional_draw: bool, matches: int):
        arch, opp = norm_arch(arch), norm_arch(opp)
        for (a, o), (aw, al, ad) in [((arch, opp), (wins, losses, draws)), ((opp, arch), (losses, wins, draws))]:
            key = (a.lower(), o.lower())
            if key not in agg:
                agg[key] = {"wins": 0, "losses": 0, "draws": 0, "intentional_draws": 0, "matches": 0, "archetype": a, "opponent_archetype": o}
            agg[key]["wins"] += aw
            agg[key]["losses"] += al
            agg[key]["draws"] += ad
            if is_intentional_draw:
                agg[key]["intentional_draws"] += 1
            agg[key]["matches"] += matches

    agg = {}
    # Rows we can pair by (deck_id, opponent_deck_id) for consistent A vs B / B vs A
    paired_rows = [r for r in filtered if r.get("opponent_deck_id") is not None]
    unpaired_rows = [r for r in filtered if r.get("opponent_deck_id") is None]

    by_match: dict[tuple[int, int, int | None], list[dict]] = {}
    for r in paired_rows:
        d_a, d_b = sorted([r["deck_id"], r["opponent_deck_id"]])
        rnd = r.get("round")
        key = (d_a, d_b, rnd)
        by_match.setdefault(key, []).append(r)

    for match_key, match_rows in by_match.items():
        d_a, d_b, _rnd = match_key
        from_ab = [r for r in match_rows if (r["deck_id"], r["opponent_deck_id"]) == (d_a, d_b)]
        from_ba = [r for r in match_rows if (r["deck_id"], r["opponent_deck_id"]) == (d_b, d_a)]
        from_ab.sort(key=lambda x: (x.get("round") or 0, x.get("deck_id")))
        from_ba.sort(key=lambda x: (x.get("round") or 0, x.get("deck_id")))
        n_paired = min(len(from_ab), len(from_ba))
        for i in range(n_paired):
            ra, rb = from_ab[i], from_ba[i]
            c1 = _matchup_result_to_canonical((ra.get("result") or "").strip())
            c2 = _matchup_result_to_canonical((rb.get("result") or "").strip())
            if (c1 == "win" and c2 == "loss") or (c1 == "loss" and c2 == "win") or (c1 in ("draw", "intentional_draw") and c2 in ("draw", "intentional_draw")):
                row = ra
            else:
                row = ra
            arch = (row.get("archetype") or "(unknown)").strip()
            opp = (row.get("opponent_archetype") or "(unknown)").strip()
            wins, losses, draws = to_effective_wld(row)
            is_id = _is_intentional_draw_result(row.get("result") or "")
            add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)
        for i in range(n_paired, len(from_ab)):
            row = from_ab[i]
            arch = (row.get("archetype") or "(unknown)").strip()
            opp = (row.get("opponent_archetype") or "(unknown)").strip()
            wins, losses, draws = to_effective_wld(row)
            is_id = _is_intentional_draw_result(row.get("result") or "")
            add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)
        for i in range(n_paired, len(from_ba)):
            row = from_ba[i]
            arch = (row.get("archetype") or "(unknown)").strip()
            opp = (row.get("opponent_archetype") or "(unknown)").strip()
            wins, losses, draws = to_effective_wld(row)
            is_id = _is_intentional_draw_result(row.get("result") or "")
            add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)

    for r in unpaired_rows:
        arch = (r.get("archetype") or "(unknown)").strip()
        opp = (r.get("opponent_archetype") or "(unknown)").strip()
        wins, losses, draws = to_effective_wld(r)
        is_id = _is_intentional_draw_result(r.get("result") or "")
        add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)

    def _pair_included_in_summary(mcount: int) -> bool:
        if mcount <= 0:
            return False
        if min_matches <= 0:
            return True
        if mcount >= min_matches:
            return True
        return include_opponents_below_min

    list_out = []
    for (_arch_lower, _opp_lower), v in agg.items():
        if not _pair_included_in_summary(v["matches"]):
            continue
        wr = (v["wins"] + 0.5 * v["draws"]) / v["matches"] if v["matches"] else 0
        list_out.append({
            "archetype": v["archetype"],
            "opponent_archetype": v["opponent_archetype"],
            "wins": v["wins"],
            "losses": v["losses"],
            "draws": v["draws"],
            "intentional_draws": v["intentional_draws"],
            "matches": v["matches"],
            "win_rate": round(wr, 4),
        })

    archetypes_sorted = sorted({r["archetype"] for r in list_out} | {r["opponent_archetype"] for r in list_out})
    matrix = []
    for i, a in enumerate(archetypes_sorted):
        row = []
        for j, b in enumerate(archetypes_sorted):
            if i == j:
                row.append(None)
                continue
            key = (a.lower(), b.lower())
            v = agg.get(key, {"matches": 0, "wins": 0, "draws": 0})
            if not _pair_included_in_summary(v["matches"]):
                row.append(None)
                continue
            wr = (v["wins"] + 0.5 * v["draws"]) / v["matches"] if v["matches"] else None
            row.append(round(wr, 4) if wr is not None else None)
        matrix.append(row)

    return {
        "list": list_out,
        "archetypes": archetypes_sorted,
        "matrix": matrix,
        "min_matches": min_matches,
        "include_opponents_below_min": include_opponents_below_min,
    }



@router.get("/api/v1/matchups/players-summary", dependencies=[Depends(require_database)], tags=["Matchups"])
def get_matchups_players_summary(
    format_id: str | None = Query(None),
    event_ids: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    player: list[str] | None = Query(None),
    min_matches: int = Query(0, ge=0, le=1_000_000, description="Minimum aggregated matches per player pair to include in list and matrix"),
    include_opponents_below_min: bool = Query(
        False,
        description="When min_matches > 0, still include pairs with at least one match but fewer than min_matches (matrix + list)",
    ),
):
    """Aggregated matchup summary by player. Optional filters."""
    with _db.session_scope() as session:
        rows = _db.list_matchups_with_deck_and_players(session)

    event_id_set = None
    if event_ids:
        event_id_set = {x.strip() for x in event_ids.split(",") if x.strip()}

    filtered = []
    for r in rows:
        if format_id and (r.get("format_id") or "").strip().upper() != format_id.strip().upper():
            continue
        if event_id_set is not None and (r.get("event_id") or "").strip() not in event_id_set:
            continue
        if not _date_in_range(r.get("date") or "", date_from, date_to):
            continue
        if (r.get("result") or "").strip().lower() in ("bye", "drop"):
            continue
        filtered.append(r)

    def to_effective_wld(row):
        raw = (row.get("result") or "loss").strip().lower()
        if raw == "intentional_draw":
            return (0, 0, 1)
        if raw == "intentional_draw_win":
            return (1, 0, 0)
        if raw == "intentional_draw_loss":
            return (0, 1, 0)
        canonical = _matchup_result_to_canonical(row.get("result") or "loss")
        if canonical == "win":
            return (1, 0, 0)
        if canonical == "loss":
            return (0, 1, 0)
        return (0, 0, 1)

    # Aggregate by (player, opponent_player). Use front-face name so "Norman Osborn" and
    # "Norman Osborn // Green Goblin" are one row (dual-faced names unified across the app).
    agg: dict[tuple[str, str], dict] = {}
    for r in filtered:
        if r.get("opponent_player_id") is None:
            continue
        pname = (r.get("player") or "(unknown)").strip()
        opp = (r.get("opponent_player") or "(unknown)").strip()
        player_canonical = _front_face_name(pname)
        opp_canonical = _front_face_name(opp)
        key = (player_canonical.lower(), opp_canonical.lower())
        if key not in agg:
            agg[key] = {
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "intentional_draws": 0,
                "matches": 0,
                "player": player_canonical,
                "opponent_player": opp_canonical,
            }
        wins, losses, draws = to_effective_wld(r)
        agg[key]["wins"] += wins
        agg[key]["losses"] += losses
        agg[key]["draws"] += draws
        if _is_intentional_draw_result(r.get("result") or ""):
            agg[key]["intentional_draws"] += 1
        agg[key]["matches"] += 1

    # Canonical display names (first occurrence)
    canonical_player: dict[str, str] = {}
    for (pl, op), v in agg.items():
        for raw in [v["player"], v["opponent_player"]]:
            if raw and raw.lower() not in ("bye", "drop"):
                canonical_player.setdefault(raw.lower(), raw)

    # Map canonical player name -> player_id (first non-None occurrence)
    player_id_map: dict[str, int] = {}
    for r in filtered:
        for name_key, id_key in (("player", "player_id"), ("opponent_player", "opponent_player_id")):
            name = _front_face_name((r.get(name_key) or "").strip())
            pid = r.get(id_key)
            if name and pid is not None and name not in player_id_map:
                player_id_map[name] = pid

    def norm_player(name: str) -> str:
        return canonical_player.get((name or "").lower(), name or "(unknown)")

    def _player_pair_included(mcount: int) -> bool:
        if mcount <= 0:
            return False
        if min_matches <= 0:
            return True
        if mcount >= min_matches:
            return True
        return include_opponents_below_min

    players_list_out = []
    for (_pl_lower, _op_lower), v in agg.items():
        if not _player_pair_included(v["matches"]):
            continue
        wr = (v["wins"] + 0.5 * v["draws"]) / v["matches"] if v["matches"] else 0
        players_list_out.append({
            "player": norm_player(v["player"]),
            "opponent_player": norm_player(v["opponent_player"]),
            "wins": v["wins"],
            "losses": v["losses"],
            "draws": v["draws"],
            "intentional_draws": v["intentional_draws"],
            "matches": v["matches"],
            "win_rate": round(wr, 4),
        })

    all_players_sorted = sorted(
        {r["player"] for r in players_list_out} | {r["opponent_player"] for r in players_list_out}
    )
    players_matrix = []
    for i, pa in enumerate(all_players_sorted):
        row = []
        for j, pb in enumerate(all_players_sorted):
            if i == j:
                row.append(None)
                continue
            key = (pa.lower(), pb.lower())
            v = agg.get(key, {"matches": 0, "wins": 0, "draws": 0})
            if not _player_pair_included(v["matches"]):
                row.append(None)
                continue
            wr = (v["wins"] + 0.5 * v["draws"]) / v["matches"] if v["matches"] else None
            row.append(round(wr, 4) if wr is not None else None)
        players_matrix.append(row)

    matchups_list_out = [
        {
            "player_a": _front_face_name(r.get("player") or "(unknown)"),
            "player_b": _front_face_name(r.get("opponent_player") or "(unknown)"),
            "result": r.get("result") or "",
            "event_id": r.get("event_id") or "",
            "date": r.get("date") or "",
            "round": r.get("round"),
            "archetype_a": r.get("archetype") or "",
            "archetype_b": r.get("opponent_archetype") or "",
        }
        for r in filtered
    ]

    # Optional filter by player name(s): keep only pairs where at least one side is in the selection
    if player and len(player) > 0:
        selected_lower = {p.strip().lower() for p in player if p and p.strip()}
        if selected_lower:
            players_list_out = [
                r for r in players_list_out
                if (r["player"] or "").lower() in selected_lower or (r["opponent_player"] or "").lower() in selected_lower
            ]
            all_players_sorted = sorted(
                {r["player"] for r in players_list_out} | {r["opponent_player"] for r in players_list_out}
            )
            players_matrix = []
            for i, pa in enumerate(all_players_sorted):
                row = []
                for j, pb in enumerate(all_players_sorted):
                    if i == j:
                        row.append(None)
                        continue
                    key = (pa.lower(), pb.lower())
                    v = agg.get(key, {"matches": 0, "wins": 0, "draws": 0})
                    if not _player_pair_included(v["matches"]):
                        row.append(None)
                        continue
                    wr = (v["wins"] + 0.5 * v["draws"]) / v["matches"] if v["matches"] else None
                    row.append(round(wr, 4) if wr is not None else None)
                players_matrix.append(row)
            filtered_pairs_lower = {
                ((r["player"] or "").lower(), (r["opponent_player"] or "").lower()) for r in players_list_out
            }
            matchups_list_out = [
                m for m in matchups_list_out
                if (
                    ((m["player_a"] or "").strip().lower(), (m["player_b"] or "").strip().lower()) in filtered_pairs_lower
                    or ((m["player_b"] or "").strip().lower(), (m["player_a"] or "").strip().lower()) in filtered_pairs_lower
                )
            ]

    return {
        "players_list": players_list_out,
        "players": all_players_sorted,
        "players_matrix": players_matrix,
        "matchups_list": matchups_list_out,
        "min_matches": min_matches,
        "include_opponents_below_min": include_opponents_below_min,
        "player_ids": player_id_map,
    }


@router.patch("/api/v1/matchups/{matchup_id}", dependencies=[Depends(require_admin), Depends(require_database)])
def patch_matchup(matchup_id: int, body: PatchMatchupBody):
    """Update a matchup result (admin fix for discrepancies or one-sided reports)."""
    with _db.session_scope() as session:
        ok = _db.update_matchup(
            session,
            matchup_id,
            result=body.result,
            result_note=body.result_note,
            round=body.round,
        )
    if not ok:
        raise HTTPException(status_code=404, detail="Matchup not found")
    return {"ok": True}

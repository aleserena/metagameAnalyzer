import logging
import math
from datetime import date
from urllib.parse import unquote

from fastapi import HTTPException, Query
from src.mtgtop8.analyzer import (
    analyze,
    archetype_aggregate_analysis,
    card_stat_buckets,
    effective_commanders,
    is_top8,
    normalize_rank,
    player_leaderboard,
    top_cards_main,
)
from src.mtgtop8.card_lookup import lookup_cards
from src.mtgtop8.config import FORMATS
from src.mtgtop8.models import Deck

from api.helpers import (
    _date_yymmdd_to_parts,
    _filter_decks_for_query,
    _parse_date_sortkey,
    _parse_event_id_filter,
    _window_summary_from_dicts,
    _yymmdd_to_ordinal,
)
from api.services import settings as settings_service
from api.state import (
    _normalize_player,
    state,
)

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

from api.route_helpers import (
    _date_in_range,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/v1/date-range")
def get_date_range():
    """Return min/max dates and the latest event date from loaded decks."""
    if not state.decks:
        return {"min_date": None, "max_date": None, "last_event_date": None}
    dates = [d.get("date", "") for d in state.decks if d.get("date")]
    valid = [d for d in dates if _parse_date_sortkey(d).isdigit()]
    if not valid:
        return {"min_date": None, "max_date": None, "last_event_date": None}
    sorted_keys = sorted(valid, key=_parse_date_sortkey)
    max_date = sorted_keys[-1]
    return {"min_date": sorted_keys[0], "max_date": max_date, "last_event_date": max_date}


@router.get("/api/v1/format-info")
def get_format_info():
    """Return the format(s) detected from loaded decks."""
    if not state.decks:
        return {"format_id": None, "format_name": None}
    format_ids = {d.get("format_id", "") for d in state.decks if d.get("format_id")}
    if len(format_ids) == 1:
        fid = next(iter(format_ids))
        return {"format_id": fid, "format_name": FORMATS.get(fid, fid)}
    return {"format_id": None, "format_name": "Multiple Formats"}


@router.get("/api/v1/metagame/health")
def get_metagame_health(
    format_id: str | None = Query(None, alias="format", description="Format ID (e.g. EDH, Modern)"),
    event_id: str | None = Query(None, description="Filter by single event ID"),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Metagame health score (0–100) for a format.

    Five equally-weighted factors:
    1. Archetype diversity    — Shannon entropy effective archetype count (e^H)
    2. Top-card concentration — avg inclusion rate of the top-5 most-played cards
    3. Win-rate parity        — weighted std-dev of win rates (weighted by sqrt(matches))
    4. Meta shift rate        — stability index × diversity penalty (stable-but-stagnant penalized)
    5. Dominant archetype     — top archetype share (boogeyman detector)
    """
    source = _filter_decks_for_query(state.decks, event_id, event_ids, date_from, date_to)
    if format_id:
        fmt_upper = format_id.strip().upper()
        source = [d for d in source if (d.get("format_id") or "").upper() == fmt_upper]

    empty = {
        "health_score": None,
        "factors": {
            "archetype_diversity": None,
            "top_card_concentration": None,
            "win_rate_parity": None,
            "meta_shift_rate": None,
            "dominant_archetype": None,
        },
        "details": {},
    }

    if not source:
        return empty

    total = len(source)

    # ── Factor 1: Archetype diversity (Shannon entropy) ──────────────────────
    # Effective number of archetypes = e^H (Shannon entropy). Rewards both breadth
    # and even distribution; a format where one deck has 80% naturally scores low
    # even if 10 archetypes technically exist.
    # Score: 1 effective archetype = 0, 15+ = 100.
    arch_counts: dict[str, int] = {}
    for d in source:
        arch = (d.get("archetype") or "").strip()
        if arch and arch.lower() != "(unknown)":
            arch_counts[arch] = arch_counts.get(arch, 0) + 1
    arch_total = sum(arch_counts.values())
    if arch_total > 0:
        probs = [c / arch_total for c in arch_counts.values()]
        entropy = -sum(p * math.log(p) for p in probs if p > 0)
        effective_archetypes = math.exp(entropy)
        diversity_score = round(min(100.0, (effective_archetypes - 1) / 14 * 100))
    else:
        effective_archetypes = 0.0
        diversity_score = 0
    n_viable = sum(1 for c in arch_counts.values() if arch_total > 0 and c / arch_total >= 0.02)

    # ── Factor 2: Top-card concentration ────────────────────────────────────
    # Avg inclusion rate of the top-5 most-played cards. High concentration → unhealthy.
    # Score: 0% avg → 100 (healthy), 100% avg → 0 (solved).
    card_counts: dict[str, int] = {}
    for d in source:
        seen: set[str] = set()
        for entry in d.get("mainboard") or []:
            name = (entry.get("name") or entry.get("card") or "").strip()
            if name and name not in seen:
                card_counts[name] = card_counts.get(name, 0) + 1
                seen.add(name)
    top5_rates = sorted((c / total for c in card_counts.values()), reverse=True)[:5]
    avg_top5 = sum(top5_rates) / len(top5_rates) if top5_rates else 0.0
    concentration_score = round(max(0.0, 100.0 - avg_top5 * 100))

    # ── Factor 3: Win-rate parity ────────────────────────────────────────────
    # Weighted std-dev of win rates; each archetype weighted by sqrt(match_count)
    # so archetypes with more recorded matches carry proportionally more signal.
    # Score: stddev 0 → 100, stddev ≥ 0.20 → 0.
    parity_score: int | None = None
    arch_win_rates: list[float] = []
    weighted_stddev: float | None = None
    if state.database_available():
        try:
            with _db.session_scope() as session:
                rows = _db.list_matchups_with_deck_info(session)
            # Filter to the same scope
            ev_set = _parse_event_id_filter(event_id, event_ids)
            filtered_rows = []
            for r in rows:
                if format_id and (r.get("format_id") or "").upper() != format_id.strip().upper():
                    continue
                if ev_set and str(r.get("event_id")) not in ev_set:
                    continue
                if not _date_in_range(r.get("date") or "", date_from, date_to):
                    continue
                if (r.get("result") or "").lower() in ("bye", "drop"):
                    continue
                filtered_rows.append(r)
            # Aggregate wins + matches per archetype
            arch_agg: dict[str, dict] = {}
            for r in filtered_rows:
                arch = (r.get("archetype") or "(unknown)").strip()
                if arch == "(unknown)":
                    continue
                result = (r.get("result") or "").lower()
                if result not in ("win", "loss", "draw", "intentional_draw"):
                    continue
                if arch not in arch_agg:
                    arch_agg[arch] = {"wins": 0.0, "matches": 0}
                arch_agg[arch]["matches"] += 1
                if result == "win":
                    arch_agg[arch]["wins"] += 1.0
                elif result in ("draw", "intentional_draw"):
                    arch_agg[arch]["wins"] += 0.5
            # Only archetypes with ≥ 5 matches; weight each by sqrt(match_count)
            arch_wr_data: list[tuple[float, int]] = [
                (v["wins"] / v["matches"], v["matches"])
                for v in arch_agg.values()
                if v["matches"] >= 5
            ]
            arch_win_rates = [wr for wr, _ in arch_wr_data]
            if len(arch_wr_data) >= 2:
                wr_weights = [math.sqrt(m) for _, m in arch_wr_data]
                total_wr_weight = sum(wr_weights)
                weighted_mean = sum(w * wr for w, wr in zip(wr_weights, arch_win_rates)) / total_wr_weight
                weighted_variance = sum(
                    w * (wr - weighted_mean) ** 2
                    for w, wr in zip(wr_weights, arch_win_rates)
                ) / total_wr_weight
                weighted_stddev = math.sqrt(weighted_variance)
                parity_score = round(max(0.0, min(100.0, (1 - weighted_stddev / 0.20) * 100)))
            elif arch_wr_data:
                parity_score = 100
                weighted_stddev = 0.0
        except Exception:
            logger.exception("Failed to compute win-rate parity for health score")

    # ── Factor 4: Meta shift rate (stability) ────────────────────────────────
    # Reuse the churn stability index (last 4 weeks) as the shift-rate factor.
    shift_score: int | None = None
    try:
        churn_result = get_metagame_churn(
            format_id=format_id,
            weeks=4,
            top_n=8,
            event_id=event_id,
            event_ids=event_ids,
            date_from=date_from,
            date_to=date_to,
        )
        if isinstance(churn_result, dict):
            shift_score = churn_result.get("stability_index")
    except Exception:
        logger.exception("Failed to compute meta shift rate for health score")

    # Apply combined penalty: high stability + low diversity = stagnant, not healthy.
    # Multiply stability by min(1, diversity / 50) so a dominant-deck stable format
    # cannot mask its lack of diversity with a high stability score.
    shift_score_adjusted: int | None = None
    if shift_score is not None:
        penalty = min(1.0, diversity_score / 50.0) if diversity_score is not None else 1.0
        shift_score_adjusted = round(shift_score * penalty)

    # ── Factor 5: Dominant archetype (boogeyman) ─────────────────────────────
    # Top archetype share < 15% → 100 (healthy), ≥ 40% → 0 (one deck dominates).
    if arch_counts and arch_total > 0:
        top_arch_name, top_arch_count = max(arch_counts.items(), key=lambda x: x[1])
        top_arch_share = top_arch_count / arch_total
    else:
        top_arch_name = None
        top_arch_share = 0.0
    boogeyman_score = round(max(0.0, min(100.0, (1 - max(0.0, top_arch_share - 0.15) / 0.25) * 100)))

    # ── Aggregate ────────────────────────────────────────────────────────────
    available_factors = [
        s for s in [diversity_score, concentration_score, parity_score, shift_score_adjusted, boogeyman_score]
        if s is not None
    ]
    health_score = round(sum(available_factors) / len(available_factors)) if available_factors else None

    return {
        "health_score": health_score,
        "factors": {
            "archetype_diversity": diversity_score,
            "top_card_concentration": concentration_score,
            "win_rate_parity": parity_score,
            "meta_shift_rate": shift_score_adjusted,
            "dominant_archetype": boogeyman_score,
        },
        "details": {
            "viable_archetype_count": n_viable,
            "effective_archetype_count": round(effective_archetypes, 1),
            "avg_top5_card_inclusion_pct": round(avg_top5 * 100, 1),
            "archetype_win_rate_stddev": round(weighted_stddev, 4) if weighted_stddev is not None and arch_win_rates else None,
            "stability_index": shift_score,
            "top_archetype": top_arch_name,
            "top_archetype_share_pct": round(top_arch_share * 100, 1),
        },
    }


@router.get("/api/v1/metagame/churn")
def get_metagame_churn(
    format_id: str | None = Query(None, alias="format", description="Format ID (e.g. EDH, Modern)"),
    weeks: int = Query(4, ge=1, le=52, description="Length of each window in weeks"),
    top_n: int = Query(8, ge=0, le=200, description="Top N archetypes to track for rank deltas (0 = all)"),
    event_id: str | None = Query(None, description="Filter by single event ID"),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Format volatility / churn metric.

    Two modes:
    - No filter (no event_ids / date range): splits all data into two consecutive
      `weeks`-wide windows anchored to the most recent event.
    - With filter (event_ids or date_from/date_to selected): treats the filtered
      decks as the CURRENT window and automatically looks back an equal calendar
      span into the full dataset to build the PREVIOUS window.

    Returns:
    - stability_index (0–100, higher = more stable)
    - archetype_changes: rank delta, entry/exit for top-N archetypes
    - most_volatile_cards: cards whose play-rate changed most between windows
    - window metadata (date ranges, deck counts)
    """
    has_filter = bool(event_id or event_ids or date_from or date_to)

    # Format filter applied to the full corpus for previous-window lookups
    fmt_upper = format_id.strip().upper() if format_id else None
    def _fmt_ok(d: dict) -> bool:
        return not fmt_upper or (d.get("format_id") or "").upper() == fmt_upper

    current_decks = _filter_decks_for_query(state.decks, event_id, event_ids, date_from, date_to)
    current_decks = [d for d in current_decks if _fmt_ok(d)]

    if not current_decks:
        return {
            "stability_index": None,
            "current_window": {"deck_count": 0, "event_count": 0, "date_from": None, "date_to": None},
            "previous_window": {"deck_count": 0, "event_count": 0, "date_from": None, "date_to": None},
            "archetype_changes": [],
            "most_volatile_cards": [],
            "message": "No data available for the requested format/window.",
        }

    def deck_ordinal(d: dict) -> int | None:
        key = _parse_date_sortkey(d.get("date", "") or "")
        return _yymmdd_to_ordinal(key) if key.isdigit() and len(key) == 6 else None

    cur_ordinals = [o for o in (deck_ordinal(d) for d in current_decks) if o is not None]
    if not cur_ordinals:
        return {
            "stability_index": None,
            "current_window": {"deck_count": 0, "event_count": 0, "date_from": None, "date_to": None},
            "previous_window": {"deck_count": 0, "event_count": 0, "date_from": None, "date_to": None},
            "archetype_changes": [],
            "most_volatile_cards": [],
            "message": "No dated decks found.",
        }

    if has_filter:
        # Current window = the filtered selection.
        # Previous window = same calendar span shifted back by the span length,
        # drawn from the full corpus (format-filtered only, no event/date filter).
        cur_min = min(cur_ordinals)
        cur_max = max(cur_ordinals)
        span = max(cur_max - cur_min, 0)  # days covered by the selection
        prev_end = cur_min - 1
        prev_start = prev_end - span
        full_corpus = [d for d in state.decks if _fmt_ok(d)]
        previous_decks = [
            d for d in full_corpus
            if (o := deck_ordinal(d)) is not None and prev_start <= o <= prev_end
        ]
    else:
        # No filter: split all data into two consecutive weeks-wide windows.
        week_days = weeks * 7
        anchor = max(cur_ordinals)
        cur_start = anchor - week_days + 1
        prev_start_wk = cur_start - week_days
        current_decks = [d for d in current_decks if (o := deck_ordinal(d)) is not None and cur_start <= o <= anchor]
        full_corpus = [d for d in state.decks if _fmt_ok(d)]
        previous_decks = [
            d for d in full_corpus
            if (o := deck_ordinal(d)) is not None and prev_start_wk <= o < cur_start
        ]

    def archetype_playrates(decks: list[dict]) -> dict[str, float]:
        """Return {archetype: play_rate (0–1)} for non-null archetypes."""
        total = len(decks)
        if not total:
            return {}
        counts: dict[str, int] = {}
        for d in decks:
            arch = (d.get("archetype") or "").strip()
            if arch and arch.lower() != "(unknown)":
                counts[arch] = counts.get(arch, 0) + 1
        return {a: c / total for a, c in counts.items()}

    cur_rates = archetype_playrates(current_decks)
    prev_rates = archetype_playrates(previous_decks)

    # Rank archetypes in each window by play rate (rank 1 = most played)
    def ranked(rates: dict[str, float]) -> dict[str, int]:
        sorted_archs = sorted(rates, key=lambda a: rates[a], reverse=True)
        return {a: i + 1 for i, a in enumerate(sorted_archs)}

    cur_rank = ranked(cur_rates)
    prev_rank = ranked(prev_rates)

    # Build archetype_changes for the union of top-N from both windows (0 = all)
    effective_n = top_n if top_n > 0 else max(len(cur_rank), len(prev_rank))
    all_archs_cur = set(list(cur_rank.keys())[:effective_n])
    all_archs_prev = set(list(prev_rank.keys())[:effective_n])
    tracked = all_archs_cur | all_archs_prev

    archetype_changes = []
    for arch in tracked:
        in_cur = arch in cur_rank
        in_prev = arch in prev_rank
        c_rank = cur_rank.get(arch)
        p_rank = prev_rank.get(arch)
        c_rate = cur_rates.get(arch, 0.0)
        p_rate = prev_rates.get(arch, 0.0)

        if in_cur and in_prev:
            status = "stable"
            rank_delta = p_rank - c_rank  # positive = moved up
        elif in_cur and not in_prev:
            status = "entered"
            rank_delta = None
        else:
            status = "exited"
            rank_delta = None

        archetype_changes.append({
            "archetype": arch,
            "status": status,
            "current_rank": c_rank,
            "previous_rank": p_rank,
            "rank_delta": rank_delta,
            "current_play_rate_pct": round(c_rate * 100, 1),
            "previous_play_rate_pct": round(p_rate * 100, 1),
            "play_rate_delta_pct": round((c_rate - p_rate) * 100, 1),
        })

    # Sort: entered first, then exited, then stable sorted by |rank_delta| desc
    def _change_sort_key(x):
        order = {"entered": 0, "exited": 1, "stable": 2}
        delta_abs = abs(x["rank_delta"]) if x["rank_delta"] is not None else 0
        return (order.get(x["status"], 3), -delta_abs)

    archetype_changes.sort(key=_change_sort_key)

    # Most volatile cards: compare inclusion rate per card across all decks in each window
    def card_inclusion_rates(decks: list[dict]) -> dict[str, float]:
        """Return {card_name: inclusion_rate (0–1)} across all decks (mainboard)."""
        total = len(decks)
        if not total:
            return {}
        counts: dict[str, int] = {}
        for d in decks:
            seen = set()
            for entry in d.get("mainboard") or []:
                name = (entry.get("name") or entry.get("card") or "").strip()
                if name and name not in seen:
                    counts[name] = counts.get(name, 0) + 1
                    seen.add(name)
        return {c: n / total for c, n in counts.items()}

    cur_card_rates = card_inclusion_rates(current_decks)
    prev_card_rates = card_inclusion_rates(previous_decks)

    # Only consider cards that appear in at least one window with ≥1% inclusion
    all_cards = {c for c, r in cur_card_rates.items() if r >= 0.01} | \
                {c for c, r in prev_card_rates.items() if r >= 0.01}

    card_volatility = []
    for card in all_cards:
        c_rate = cur_card_rates.get(card, 0.0)
        p_rate = prev_card_rates.get(card, 0.0)
        delta = c_rate - p_rate
        card_volatility.append({
            "card": card,
            "current_inclusion_pct": round(c_rate * 100, 1),
            "previous_inclusion_pct": round(p_rate * 100, 1),
            "delta_pct": round(delta * 100, 1),
        })

    card_volatility.sort(key=lambda x: abs(x["delta_pct"]), reverse=True)
    most_volatile_cards = card_volatility[:20]

    # Stability index (0–100)
    # Components:
    #   1. Entry/exit rate: (entered + exited) / top_n  — penalizes archetype turnover
    #   2. Average rank delta (normalised): mean(|rank_delta|) / top_n for stable archetypes
    # stability = 100 - clamp(churn_score * 100, 0, 100)
    entered_count = sum(1 for x in archetype_changes if x["status"] == "entered")
    exited_count = sum(1 for x in archetype_changes if x["status"] == "exited")
    stable_changes = [x for x in archetype_changes if x["status"] == "stable" and x["rank_delta"] is not None]

    entry_exit_rate = (entered_count + exited_count) / max(effective_n, 1)
    avg_rank_delta_norm = (
        sum(abs(x["rank_delta"]) for x in stable_changes) / (len(stable_changes) * max(effective_n, 1))
        if stable_changes else 0.0
    )
    # Weight entry/exit (60%) more than rank movement (40%)
    churn_score = 0.6 * entry_exit_rate + 0.4 * avg_rank_delta_norm
    stability_index = round(max(0.0, min(100.0, 100.0 - churn_score * 100.0)))

    return {
        "stability_index": stability_index,
        "current_window": _window_summary_from_dicts(current_decks),
        "previous_window": _window_summary_from_dicts(previous_decks),
        "archetype_changes": archetype_changes,
        "most_volatile_cards": most_volatile_cards,
        "params": {"format": format_id, "weeks": weeks, "top_n": top_n},
    }


@router.get("/api/v1/metagame")
def get_metagame(
    placement_weighted: bool = Query(False),
    ignore_lands: bool = Query(False),
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    event_id: str | None = Query(None, description="Filter by event ID (single, backward compat)"),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    top8_only: bool = Query(False, description="Only include decks that made top 8"),
    include_top8_breakdown: bool = Query(False, description="Also return summary_top8 and archetype_distribution_top8"),
):
    """Full metagame report."""
    if not state.decks:
        out = {
            "summary": {"total_decks": 0, "unique_players": 0, "unique_archetypes": 0},
            "commander_distribution": [],
            "archetype_distribution": [],
            "color_distribution": [],
            "color_count_distribution": [],
            "top_cards_main": [],
            "top_players": [],
            "placement_weighted": placement_weighted,
            "ignore_lands": ignore_lands,
        }
        if include_top8_breakdown:
            out["summary_top8"] = {"total_decks": 0, "unique_players": 0, "unique_archetypes": 0}
            out["archetype_distribution_top8"] = []
        return out
    filtered = _filter_decks_for_query(state.decks, event_id, event_ids, date_from, date_to)
    decks_all = [Deck.from_dict(d) for d in filtered]
    if top8_only:
        decks = [d for d in decks_all if is_top8(d.rank)]
    else:
        decks = decks_all
    ignore_lands_cards = set(settings_service.get_ignore_lands_cards()) if ignore_lands else None
    rank_weights = settings_service.get_rank_weights()
    result = analyze(
        decks,
        placement_weighted=placement_weighted,
        ignore_lands=ignore_lands,
        ignore_lands_cards=ignore_lands_cards,
        rank_weights=rank_weights,
    )
    if include_top8_breakdown:
        decks_top8 = [d for d in decks_all if is_top8(d.rank)]
        report_top8 = analyze(
            decks_top8,
            placement_weighted=placement_weighted,
            ignore_lands=ignore_lands,
            ignore_lands_cards=ignore_lands_cards,
            rank_weights=rank_weights,
        )
        result["summary_top8"] = report_top8["summary"]
        result["archetype_distribution_top8"] = report_top8["archetype_distribution"]
    # Most played colors: each deck counts for each of its colors (multicolor = counted in each)
    _COLOR_LABEL = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
    _COLOR_ORDER = ["W", "U", "B", "R", "G", "Colorless"]
    commander_names = list({c for d in decks for c in effective_commanders(d) if c})
    lookup = lookup_cards(commander_names) if commander_names else {}
    color_counts: dict[str, int] = {k: 0 for k in _COLOR_ORDER}
    # Per-color commander counts (or weighted score) for tooltip "top decks in this color"
    color_deck_scores: dict[str, dict[str, float]] = {k: {} for k in _COLOR_ORDER}
    # Decks by number of colors (0=colorless, 1=mono, 2=2-color, ...)
    color_count_buckets: dict[int, float] = {n: 0.0 for n in range(6)}
    # Per color-count commander scores for tooltip "top decks in this bucket"
    color_count_deck_scores: dict[int, dict[str, float]] = {n: {} for n in range(6)}
    # Per-archetype color identity derived from commanders (for UI mana symbols).
    archetype_color_sets: dict[str, set[str]] = {}

    for d in decks:
        ec = effective_commanders(d)
        if not ec:
            continue
        ci: set[str] = set()
        for name in ec:
            entry = lookup.get(name)
            if entry and "error" not in entry:
                for c in entry.get("color_identity") or entry.get("colors") or []:
                    if c in _COLOR_LABEL:
                        ci.add(c)
        is_colorless = len(ci) == 0
        if is_colorless:
            color_counts["Colorless"] += 1
            colors_for_deck = ["Colorless"]
        else:
            for c in ci:
                color_counts[c] += 1
            colors_for_deck = list(ci)

        # Track colors per archetype for archetype list UI.
        arch = (d.archetype or "").strip()
        if arch:
            s = archetype_color_sets.setdefault(arch, set())
            if is_colorless:
                s.add("C")
            else:
                for c in ci:
                    s.add(c)
        w = rank_weights.get(normalize_rank(d.rank or ""), 1.0) if placement_weighted else 1.0
        commander_key = " / ".join(sorted(ec))
        for c in colors_for_deck:
            color_deck_scores[c][commander_key] = color_deck_scores[c].get(commander_key, 0.0) + w
        n_colors = 0 if len(ci) == 0 else len(ci)
        color_count_buckets[n_colors] += w
        color_count_deck_scores[n_colors][commander_key] = color_count_deck_scores[n_colors].get(commander_key, 0.0) + w
    total = sum(color_counts.values())
    _COLOR_COUNT_LABELS = {0: "Colorless", 1: "Monocolor", 2: "2-color", 3: "3-color", 4: "4-color", 5: "5-color"}
    color_count_total = sum(color_count_buckets.values()) or 1
    _MAX_TOP_DECKS_PER_COLOR = 5
    result["color_count_distribution"] = [
        {
            "label": _COLOR_COUNT_LABELS[n],
            "count": round(color_count_buckets[n], 1),
            "pct": round(100 * color_count_buckets[n] / color_count_total, 1),
            "top_decks": [
                {"name": name, "count": round(cnt, 1)}
                for name, cnt in sorted(color_count_deck_scores[n].items(), key=lambda x: -x[1])[
                    :_MAX_TOP_DECKS_PER_COLOR
                ]
            ],
        }
        for n in range(6)
        if color_count_buckets[n] > 0
    ]
    result["color_distribution"] = [
        {
            "color": _COLOR_LABEL.get(k, k),
            "count": color_counts[k],
            "pct": round(100 * color_counts[k] / total, 1) if total else 0,
            "top_decks": [
                {"name": name, "count": round(cnt, 1)}
                for name, cnt in sorted(
                    color_deck_scores[k].items(), key=lambda x: -x[1]
                )[: _MAX_TOP_DECKS_PER_COLOR]
            ],
        }
        for k in _COLOR_ORDER
        if color_counts[k] > 0
    ]

    # Attach commander-based color identity to archetype_distribution entries so the
    # frontend can render mana symbols and filter by color without extra calls.
    if "archetype_distribution" in result and archetype_color_sets:
        color_code_order = ["W", "U", "B", "R", "G", "C"]
        for row in result["archetype_distribution"]:
            arch = (row.get("archetype") or "").strip()
            colors = archetype_color_sets.get(arch)
            if not colors:
                continue
            ordered = [c for c in color_code_order if c in colors]
            if ordered:
                row["colors"] = ordered
    full_leaderboard = player_leaderboard(
        decks, normalize_player=_normalize_player, rank_weights=rank_weights
    )
    result["top_players"] = full_leaderboard[:5]
    # Unique players must match leaderboard (alias-aware): count distinct canonical players
    result["summary"]["unique_players"] = len(full_leaderboard)
    return result


@router.get("/api/v1/archetypes/{archetype_name:path}/weekly-stats")
def get_archetype_weekly_stats(
    archetype_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    event_id: str | None = Query(None),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
):
    """Week-over-week popularity and top-8 conversion for this archetype.

    Returns one row per ISO week in which the archetype has at least one deck,
    plus the total deck count across all archetypes that week (for share %).
    """
    if not state.decks:
        raise HTTPException(status_code=404, detail="No data loaded")
    decoded = unquote(archetype_name)
    if (decoded or "").strip().lower() == "(unknown)":
        raise HTTPException(status_code=404, detail="Archetype not found")
    want_key = _db.archetype_canonical_key(decoded)
    scoped = _filter_decks_for_query(state.decks, event_id, event_ids, date_from, date_to)

    def _week_key(d: dict) -> str | None:
        key = _parse_date_sortkey(d.get("date", "") or "")
        parts = _date_yymmdd_to_parts(key)
        if not parts:
            return None
        yy, mm, dd = parts
        try:
            dt = date(2000 + yy, mm, dd)
        except ValueError:
            return None
        iso = dt.isocalendar()
        return f"{iso[0]:04d}-W{iso[1]:02d}"

    def _week_monday(week_label: str) -> str | None:
        try:
            yr, wk = week_label.split("-W")
            dt = date.fromisocalendar(int(yr), int(wk), 1)
            return f"{dt.day:02d}/{dt.month:02d}/{dt.year % 100:02d}"
        except Exception:
            return None

    total_per_week: dict[str, int] = {}
    archetype_per_week: dict[str, int] = {}
    top8_per_week: dict[str, int] = {}
    matched_any = False
    for d in scoped:
        wk = _week_key(d)
        if wk is None:
            continue
        total_per_week[wk] = total_per_week.get(wk, 0) + 1
        if _db.archetype_canonical_key(d.get("archetype")) == want_key:
            matched_any = True
            archetype_per_week[wk] = archetype_per_week.get(wk, 0) + 1
            if is_top8(d.get("rank") or ""):
                top8_per_week[wk] = top8_per_week.get(wk, 0) + 1
    if not matched_any:
        raise HTTPException(status_code=404, detail="Archetype not found or no decks in range")

    weeks = sorted(archetype_per_week.keys())
    out = []
    for wk in weeks:
        a = archetype_per_week.get(wk, 0)
        t = total_per_week.get(wk, 0)
        t8 = top8_per_week.get(wk, 0)
        share = round(100 * a / t, 1) if t else 0.0
        top8_rate = round(100 * t8 / a, 1) if a else 0.0
        out.append({
            "week": wk,
            "week_start": _week_monday(wk),
            "archetype_decks": a,
            "archetype_top8": t8,
            "total_decks": t,
            "share_pct": share,
            "top8_rate_pct": top8_rate,
        })

    display_arch = _db.normalize_archetype_display(decoded.strip()) or decoded.strip()
    return {
        "archetype": display_arch,
        "weeks": out,
    }


@router.get("/api/v1/archetypes/{archetype_name:path}/card-trends")
def get_archetype_card_trends(
    archetype_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    event_id: str | None = Query(None),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    ignore_lands: bool = Query(False),
    recency_mode: str = Query("events", pattern="^(events|days|ratio|custom)$"),
    recency_value: int = Query(3, ge=1, le=365),
    recent_from: str | None = Query(None, description="DD/MM/YY; used when recency_mode=custom"),
    recent_to: str | None = Query(None, description="DD/MM/YY; used when recency_mode=custom"),
    min_recent_play_rate: float = Query(20.0, ge=0.0, le=100.0),
    max_older_play_rate: float = Query(5.0, ge=0.0, le=100.0),
    limit: int = Query(20, ge=1, le=200),
):
    """Return cards newly appearing and cards falling out of this archetype.

    Splits the archetype's scoped decks into a "recent" window and an "older"
    window (per `recency_mode`) and compares per-card play rates.
    """
    import math

    if not state.decks:
        raise HTTPException(status_code=404, detail="No data loaded")
    decoded = unquote(archetype_name)
    if (decoded or "").strip().lower() == "(unknown)":
        raise HTTPException(status_code=404, detail="Archetype not found")
    want_key = _db.archetype_canonical_key(decoded)
    filtered = _filter_decks_for_query(state.decks, event_id, event_ids, date_from, date_to)
    filtered = [
        d for d in filtered
        if _db.archetype_canonical_key(d.get("archetype")) == want_key
    ]
    if not filtered:
        raise HTTPException(status_code=404, detail="Archetype not found or no decks in range")

    sorted_dicts = sorted(
        filtered,
        key=lambda d: _parse_date_sortkey(d.get("date", "") or "") or "",
    )
    total = len(sorted_dicts)

    warning: str | None = None
    recent_dicts: list[dict] = []
    older_dicts: list[dict] = []

    if recency_mode == "events":
        event_latest: dict[str, str] = {}
        for d in sorted_dicts:
            eid = str(d.get("event_id"))
            k = _parse_date_sortkey(d.get("date", "") or "")
            if not k.isdigit():
                continue
            if eid not in event_latest or k > event_latest[eid]:
                event_latest[eid] = k
        ordered_events = sorted(event_latest.items(), key=lambda kv: kv[1])
        n = max(1, min(recency_value, len(ordered_events)))
        recent_event_ids = {eid for eid, _ in ordered_events[-n:]}
        recent_dicts = [d for d in sorted_dicts if str(d.get("event_id")) in recent_event_ids]
        older_dicts = [d for d in sorted_dicts if str(d.get("event_id")) not in recent_event_ids]
        if ordered_events and n >= len(ordered_events):
            warning = "No older events to compare against."
    elif recency_mode == "days":
        max_ord = None
        for d in sorted_dicts:
            o = _yymmdd_to_ordinal(_parse_date_sortkey(d.get("date", "") or ""))
            if o is not None and (max_ord is None or o > max_ord):
                max_ord = o
        if max_ord is None:
            warning = "Deck dates could not be parsed."
            recent_dicts = list(sorted_dicts)
        else:
            cutoff = max_ord - recency_value
            for d in sorted_dicts:
                o = _yymmdd_to_ordinal(_parse_date_sortkey(d.get("date", "") or ""))
                if o is None:
                    older_dicts.append(d)
                elif o >= cutoff:
                    recent_dicts.append(d)
                else:
                    older_dicts.append(d)
    elif recency_mode == "ratio":
        pct = max(1, min(recency_value, 99))
        take = max(1, math.ceil(total * pct / 100))
        take = min(take, total)
        older_dicts = sorted_dicts[: total - take]
        recent_dicts = sorted_dicts[total - take:]
    else:  # custom
        if not recent_from and not recent_to:
            raise HTTPException(
                status_code=400,
                detail="recency_mode=custom requires recent_from or recent_to",
            )
        for d in sorted_dicts:
            if _date_in_range(d.get("date", "") or "", recent_from, recent_to):
                recent_dicts.append(d)
            else:
                older_dicts.append(d)

    if not recent_dicts:
        warning = warning or "No decks in the recent window."
    if not older_dicts:
        warning = warning or "No decks in the older window; nothing to compare against."

    ignore_lands_cards = (
        set(settings_service.get_ignore_lands_cards()) if ignore_lands else None
    )
    rank_weights = settings_service.get_rank_weights()

    def _rates_for(dicts: list[dict]) -> dict[str, dict]:
        if not dicts:
            return {}
        decks_objs = [Deck.from_dict(d) for d in dicts]
        top = top_cards_main(
            decks_objs,
            placement_weighted=False,
            ignore_lands=ignore_lands,
            ignore_lands_cards=ignore_lands_cards,
            rank_weights=rank_weights,
            include_basic_lands=True,
        )
        return {row["card"]: row for row in top}

    recent_map = _rates_for(recent_dicts)
    older_map = _rates_for(older_dicts)

    all_cards = set(recent_map.keys()) | set(older_map.keys())

    new_cards: list[dict] = []
    legacy_cards: list[dict] = []
    for card in all_cards:
        r = recent_map.get(card) or {}
        o = older_map.get(card) or {}
        r_rate = float(r.get("play_rate_pct") or 0.0)
        o_rate = float(o.get("play_rate_pct") or 0.0)
        r_decks = int(r.get("decks") or 0)
        o_decks = int(o.get("decks") or 0)
        if r_rate >= min_recent_play_rate and o_rate <= max_older_play_rate:
            new_cards.append({
                "card": card,
                "recent_play_rate_pct": round(r_rate, 1),
                "older_play_rate_pct": round(o_rate, 1),
                "delta_pct": round(r_rate - o_rate, 1),
                "recent_decks": r_decks,
                "older_decks": o_decks,
            })
        if o_rate >= min_recent_play_rate and r_rate <= max_older_play_rate:
            legacy_cards.append({
                "card": card,
                "recent_play_rate_pct": round(r_rate, 1),
                "older_play_rate_pct": round(o_rate, 1),
                "delta_pct": round(o_rate - r_rate, 1),
                "recent_decks": r_decks,
                "older_decks": o_decks,
            })

    new_cards.sort(key=lambda x: (-x["delta_pct"], -x["recent_play_rate_pct"], x["card"]))
    legacy_cards.sort(key=lambda x: (-x["delta_pct"], -x["older_play_rate_pct"], x["card"]))
    new_cards = new_cards[:limit]
    legacy_cards = legacy_cards[:limit]

    display_arch = _db.normalize_archetype_display(decoded.strip()) or decoded.strip()
    return {
        "archetype": display_arch,
        "recent": _window_summary_from_dicts(recent_dicts),
        "older": _window_summary_from_dicts(older_dicts),
        "new_cards": new_cards,
        "legacy_cards": legacy_cards,
        "warning": warning,
    }


@router.get("/api/v1/commanders/{commander_name:path}/synergies")
def get_commander_synergies(
    commander_name: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    event_id: str | None = Query(None),
    event_ids: str | None = Query(None),
):
    """Commander synergy view: co-commanders, shell composition, core/flex/tech cards."""
    if not state.decks:
        raise HTTPException(status_code=404, detail="No data loaded")
    decoded = unquote(commander_name).strip()
    if not decoded:
        raise HTTPException(status_code=404, detail="Commander name required")

    want_key = _db.archetype_canonical_key(decoded)
    filtered = _filter_decks_for_query(state.decks, event_id, event_ids, date_from, date_to)
    filtered = [
        d for d in filtered
        if (d.get("format_id") or "").upper() in {"EDH", "CEDH", "COMMANDER"}
        and any(
            _db.archetype_canonical_key(c) == want_key
            for c in (d.get("commanders") or [])
        )
    ]
    if not filtered:
        raise HTTPException(status_code=404, detail="No EDH decks found for this commander")

    decks_objs = [Deck.from_dict(d) for d in filtered]
    total = len(decks_objs)

    # Co-commanders: count other commanders across all filtered decks
    co_cmd_count: dict[str, int] = {}
    for d in filtered:
        for c in (d.get("commanders") or []):
            if _db.archetype_canonical_key(c) != want_key:
                co_cmd_count[c] = co_cmd_count.get(c, 0) + 1
    co_commanders = sorted(
        [{"name": name, "count": cnt, "pct": round(100 * cnt / total, 1)} for name, cnt in co_cmd_count.items()],
        key=lambda x: -x["count"],
    )

    # Collect all mainboard cards
    all_card_names: set[str] = set()
    for d in decks_objs:
        for _, c in d.mainboard:
            all_card_names.add(c)

    # Fetch metadata for category classification
    metadata = lookup_cards(list(all_card_names)) if all_card_names else {}

    def _classify_category(card_name: str) -> str:
        meta = metadata.get(card_name) or {}
        type_line = (meta.get("type_line") or "").lower()
        if "land" in type_line:
            return "Land"
        if "creature" in type_line:
            return "Creature"
        if "planeswalker" in type_line:
            return "Planeswalker"
        if "instant" in type_line or "sorcery" in type_line:
            return "Spell"
        if "artifact" in type_line:
            return "Artifact"
        if "enchantment" in type_line:
            return "Enchantment"
        return "Other"

    # Shell composition: average category % across all decks
    category_totals: dict[str, float] = {}
    for d in decks_objs:
        if not d.mainboard:
            continue
        deck_total = sum(q for q, _ in d.mainboard)
        if deck_total == 0:
            continue
        cat_counts: dict[str, int] = {}
        for qty, card in d.mainboard:
            cat = _classify_category(card)
            cat_counts[cat] = cat_counts.get(cat, 0) + qty
        for cat, cnt in cat_counts.items():
            category_totals[cat] = category_totals.get(cat, 0) + (cnt / deck_total * 100)
    decks_with_mainboard = sum(1 for d in decks_objs if d.mainboard)
    shell_composition = {
        cat: round(total_pct / decks_with_mainboard, 1)
        for cat, total_pct in category_totals.items()
    } if decks_with_mainboard > 0 else {}

    # Inclusion rates per card (main only)
    main_count: dict[str, int] = {}
    for d in decks_objs:
        seen = set()
        for _, c in d.mainboard:
            if c not in seen:
                main_count[c] = main_count.get(c, 0) + 1
                seen.add(c)

    # Top-placing decks (rank 1–4)
    top_decks = [d for d in filtered if (d.get("rank") or "").strip() in {"1", "2", "3", "4"}]
    top_total = len(top_decks)
    top_count: dict[str, int] = {}
    if top_total > 0:
        for d in top_decks:
            d_obj = Deck.from_dict(d)
            seen = set()
            for _, c in d_obj.mainboard:
                if c not in seen:
                    top_count[c] = top_count.get(c, 0) + 1
                    seen.add(c)

    core_cards = []
    flex_cards = []
    tech_cards = []
    for card, cnt in main_count.items():
        overall_rate = round(100 * cnt / total, 1)
        if overall_rate >= 75:
            core_cards.append({"card": card, "inclusion_rate_pct": overall_rate})
        elif overall_rate >= 20:
            flex_cards.append({"card": card, "inclusion_rate_pct": overall_rate})

        if top_total >= 3:
            top_rate = round(100 * top_count.get(card, 0) / top_total, 1)
            delta = round(top_rate - overall_rate, 1)
            if delta >= 15:
                tech_cards.append({
                    "card": card,
                    "top_rate_pct": top_rate,
                    "overall_rate_pct": overall_rate,
                    "delta_pct": delta,
                })

    core_cards.sort(key=lambda x: -x["inclusion_rate_pct"])
    flex_cards.sort(key=lambda x: -x["inclusion_rate_pct"])
    tech_cards.sort(key=lambda x: -x["delta_pct"])

    display_name = decoded
    return {
        "commander": display_name,
        "deck_count": total,
        "co_commanders": co_commanders,
        "shell_composition": shell_composition,
        "core_cards": core_cards,
        "flex_cards": flex_cards,
        "tech_cards": tech_cards,
    }


@router.get("/api/v1/archetypes/{archetype_name:path}/card-heatmap")
def get_archetype_card_heatmap(
    archetype_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    event_id: str | None = Query(None),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    ignore_lands: bool = Query(False),
):
    """Card usage heatmap for an archetype.

    Returns each card with inclusion rate (main/side split) and an auto-detected
    category derived from the Scryfall type_line / oracle_text.
    """
    if not state.decks:
        raise HTTPException(status_code=404, detail="No data loaded")
    decoded = unquote(archetype_name)
    if (decoded or "").strip().lower() == "(unknown)":
        raise HTTPException(status_code=404, detail="Archetype not found")
    want_key = _db.archetype_canonical_key(decoded)
    filtered = _filter_decks_for_query(state.decks, event_id, event_ids, date_from, date_to)
    filtered = [
        d for d in filtered
        if _db.archetype_canonical_key(d.get("archetype")) == want_key
    ]
    if not filtered:
        raise HTTPException(status_code=404, detail="Archetype not found or no decks in range")

    decks = [Deck.from_dict(d) for d in filtered]
    total = len(decks)

    ignore_lands_cards = set(settings_service.get_ignore_lands_cards()) if ignore_lands else None

    # Count main/side appearances per card
    main_count: dict[str, int] = {}
    side_count: dict[str, int] = {}
    for d in decks:
        seen_main = set()
        for _, c in d.mainboard:
            if ignore_lands_cards and c in ignore_lands_cards:
                continue
            if c not in seen_main:
                main_count[c] = main_count.get(c, 0) + 1
                seen_main.add(c)
        seen_side = set()
        for _, c in d.sideboard:
            if ignore_lands_cards and c in ignore_lands_cards:
                continue
            if c not in seen_side:
                side_count[c] = side_count.get(c, 0) + 1
                seen_side.add(c)

    all_cards = set(main_count) | set(side_count)
    # Fetch Scryfall metadata for category classification
    metadata = lookup_cards(list(all_cards))

    def _classify_category(card_name: str) -> str:
        """Best-effort card category from type_line."""
        meta = metadata.get(card_name) or {}
        type_line = (meta.get("type_line") or "").lower()
        if "land" in type_line:
            return "Land"
        if "creature" in type_line:
            return "Creature"
        if "planeswalker" in type_line:
            return "Planeswalker"
        if "instant" in type_line or "sorcery" in type_line:
            return "Spell"
        if "artifact" in type_line:
            return "Artifact"
        if "enchantment" in type_line:
            return "Enchantment"
        return "Other"

    CATEGORY_ORDER = ["Creature", "Spell", "Artifact", "Enchantment", "Planeswalker", "Land", "Other"]

    entries = []
    for card in all_cards:
        m = main_count.get(card, 0)
        s = side_count.get(card, 0)
        inclusion = m + s  # any deck that has it in either zone
        # Only include if it appears in at least 1 deck
        if inclusion == 0:
            continue
        # Inclusion rate: fraction of decks with card in main
        main_rate = round(100 * m / total, 1)
        side_rate = round(100 * s / total, 1)
        total_rate = round(100 * inclusion / total, 1)
        entries.append({
            "card": card,
            "category": _classify_category(card),
            "main_decks": m,
            "side_decks": s,
            "main_rate_pct": main_rate,
            "side_rate_pct": side_rate,
            "inclusion_rate_pct": total_rate,
        })

    # Sort by category order then by inclusion rate descending
    cat_idx = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    entries.sort(key=lambda e: (cat_idx.get(e["category"], 99), -e["inclusion_rate_pct"], e["card"]))

    display_arch = _db.normalize_archetype_display(decoded.strip()) or decoded.strip()
    return {
        "archetype": display_arch,
        "deck_count": total,
        "cards": entries,
    }


@router.get("/api/v1/archetypes/{archetype_name:path}")
def get_archetype_detail(
    archetype_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    event_id: str | None = Query(None, description="Filter by event ID (single)"),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    ignore_lands: bool = Query(False),
):
    """Archetype detail: average analysis and top cards for decks with this archetype."""
    if not state.decks:
        raise HTTPException(status_code=404, detail="No data loaded")
    decoded = unquote(archetype_name)
    if (decoded or "").strip().lower() == "(unknown)":
        raise HTTPException(status_code=404, detail="Archetype not found")
    want_key = _db.archetype_canonical_key(decoded)
    filtered = _filter_decks_for_query(state.decks, event_id, event_ids, date_from, date_to)
    filtered = [
        d for d in filtered
        if _db.archetype_canonical_key(d.get("archetype")) == want_key
    ]
    if not filtered:
        raise HTTPException(status_code=404, detail="Archetype not found or no decks in range")
    decks = [Deck.from_dict(d) for d in filtered]
    card_names = set()
    for d in decks:
        for _, c in d.mainboard:
            card_names.add(c)
        for _, c in d.sideboard:
            card_names.add(c)
        # Include archetype (commander) for empty EDH decks so we fetch metadata
        if not d.mainboard and (d.format_id or "").upper() in ("EDH", "COMMANDER", "CEDH") and (d.archetype or "").strip():
            card_names.add((d.archetype or "").strip())
    metadata = lookup_cards(list(card_names))
    merged: dict = {}
    for name in card_names:
        if name in metadata and "error" not in metadata.get(name, {}):
            merged[name] = metadata[name]
        else:
            for k, v in metadata.items():
                if "error" not in v and k.lower() == name.lower():
                    merged[name] = v
                    break
    ignore_lands_cards = set(settings_service.get_ignore_lands_cards()) if ignore_lands else None
    rank_weights = settings_service.get_rank_weights()
    average_analysis = archetype_aggregate_analysis(decks, merged)
    top_main = top_cards_main(
        decks,
        placement_weighted=False,
        ignore_lands=ignore_lands,
        ignore_lands_cards=ignore_lands_cards,
        rank_weights=rank_weights,
        include_basic_lands=True,
    )
    top_players = player_leaderboard(
        decks, normalize_player=_normalize_player, rank_weights=rank_weights
    )[:10]
    typical_list = card_stat_buckets(
        decks,
        ignore_lands=ignore_lands,
        ignore_lands_cards=ignore_lands_cards,
        include_basic_lands=True,
    )
    deck_count_top8 = sum(1 for d in decks if is_top8(d.rank))
    display_arch = _db.normalize_archetype_display(decoded.strip()) or decoded.strip()
    return {
        "archetype": display_arch,
        "deck_count": len(decks),
        "deck_count_top8": deck_count_top8,
        "average_analysis": average_analysis,
        "top_cards_main": top_main,
        "top_players": top_players,
        "typical_list": typical_list,
    }

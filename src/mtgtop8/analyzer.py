"""Metagame analysis for scraped decks."""

import json
from typing import Any

from .models import Deck

# Rank to weight for placement-weighted stats (higher = better)
RANK_WEIGHTS: dict[str, float] = {
    "1": 8.0,
    "2": 6.0,
    "3-4": 4.0,
    "5-8": 2.0,
    "9-16": 1.0,
    "17-32": 0.5,
}


def _get_weight(rank: str) -> float:
    return RANK_WEIGHTS.get(rank, 1.0)


def commander_distribution(
    decks: list[Deck], placement_weighted: bool = False
) -> list[dict[str, Any]]:
    """Count (or weighted score) and % of decks per commander."""
    scores: dict[str, float] = {}
    for d in decks:
        key = " / ".join(sorted(d.commanders)) if d.commanders else "(no commander)"
        w = _get_weight(d.rank) if placement_weighted else 1.0
        scores[key] = scores.get(key, 0.0) + w
    total = sum(scores.values()) or 1
    return [
        {"commander": c, "count": round(n, 1), "pct": round(100 * n / total, 1)}
        for c, n in sorted(scores.items(), key=lambda x: -x[1])
    ]


def archetype_distribution(
    decks: list[Deck], placement_weighted: bool = False
) -> list[dict[str, Any]]:
    """Count (or weighted score) and % per archetype."""
    scores: dict[str, float] = {}
    for d in decks:
        key = d.archetype or "(unknown)"
        w = _get_weight(d.rank) if placement_weighted else 1.0
        scores[key] = scores.get(key, 0.0) + w
    total = sum(scores.values()) or 1
    return [
        {"archetype": a, "count": round(n, 1), "pct": round(100 * n / total, 1)}
        for a, n in sorted(scores.items(), key=lambda x: -x[1])
    ]


BASIC_LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest",
               "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
               "Snow-Covered Mountain", "Snow-Covered Forest", "Wastes"}

# Exact full names only (no suffix matching).
LAND_KEYWORDS = {
    "Land", "Lands", "Command Tower",
    "Tundra", "Underground Sea", "Badlands", "Taiga", "Savannah",
    "Scrubland", "Volcanic Island", "Bayou", "Plateau", "Tropical Island",
    # Fetchlands
    "Arid Mesa", "Marsh Flats", "Misty Rainforest", "Scalding Tarn", "Verdant Catacombs",
    "Flooded Strand", "Polluted Delta", "Windswept Heath", "Wooded Foothills", "Bloodstained Mire",
    # Shocklands
    "Hallowed Fountain", "Temple Garden", "Sacred Foundry", "Stomping Ground", "Breeding Pool",
    "Godless Shrine", "Steam Vents", "Overgrown Tomb", "Blood Crypt", "Watery Grave",
    # Pathways (MDFC lands)
    "Barkchannel Pathway", "Blightstep Pathway", "Boulderloft Pathway", "Branchloft Pathway",
    "Brightclimb Pathway", "Clearwater Pathway", "Cragcrown Pathway", "Darkbore Pathway",
    "Grimclimb Pathway", "Hengegate Pathway", "Ice Tunnel Pathway", "Lavaglide Pathway",
    "Mistgate Pathway", "Murkwater Pathway", "Needleverge Pathway", "Pillarverge Pathway",
    "Riverglide Pathway", "Searstep Pathway", "Shadowgrange Pathway", "Silvergill Pathway",
    "Skyclave Pathway", "Slitherbore Pathway", "Sundown Pass", "Tidechannel Pathway",
    "Timbercrown Pathway", "Vineglimmer Pathway",
    # Verges / Fast lands
    "Razorverge Thicket", "Copperline Gorge", "Blackcleave Cliffs", "Seachrome Coast",
    "Darkslick Shores", "Concealed Courtyard", "Inspiring Vantage", "Spirebluff Canal",
    "Botanical Sanctum", "Blooming Marsh",
}

def _is_land_card(card: str) -> bool:
    """True for cards that are lands. Uses exact full name matching only."""
    if card in BASIC_LANDS:
        return True
    return card in LAND_KEYWORDS


def top_cards_main(
    decks: list[Deck],
    placement_weighted: bool = False,
    ignore_lands: bool = False,
) -> list[dict[str, Any]]:
    """Top cards in mainboard: play rate %, total copies."""
    deck_count = len(decks)
    card_decks: dict[str, set[int]] = {}
    card_copies: dict[str, float] = {}

    for d in decks:
        w = _get_weight(d.rank) if placement_weighted else 1.0
        for qty, card in d.mainboard:
            if card in BASIC_LANDS:
                continue
            if ignore_lands and _is_land_card(card):
                continue
            if card not in card_decks:
                card_decks[card] = set()
                card_copies[card] = 0.0
            card_decks[card].add(d.deck_id)
            card_copies[card] += qty * w

    return [
        {
            "card": c,
            "decks": len(card_decks[c]),
            "play_rate_pct": round(100 * len(card_decks[c]) / deck_count, 1),
            "total_copies": round(card_copies[c], 1),
        }
        for c in sorted(card_decks.keys(), key=lambda x: -card_copies[x])
    ][:100]


def top_cards_sideboard(decks: list[Deck], placement_weighted: bool = False) -> list[dict[str, Any]]:
    """Top cards in sideboard."""
    deck_count = len(decks)
    card_decks: dict[str, set[int]] = {}
    card_copies: dict[str, float] = {}

    for d in decks:
        w = _get_weight(d.rank) if placement_weighted else 1.0
        for qty, card in d.sideboard:
            if card not in card_decks:
                card_decks[card] = set()
                card_copies[card] = 0.0
            card_decks[card].add(d.deck_id)
            card_copies[card] += qty * w

    return [
        {
            "card": c,
            "decks": len(card_decks[c]),
            "play_rate_pct": round(100 * len(card_decks[c]) / deck_count, 1),
            "total_copies": round(card_copies[c], 1),
        }
        for c in sorted(card_decks.keys(), key=lambda x: -card_copies[x])
    ][:100]


def player_leaderboard(
    decks: list[Deck],
    normalize_player: "typing.Callable[[str], str] | None" = None,
) -> list[dict[str, Any]]:
    """Player stats: wins, top-2, top-4, points. Sorted by wins desc, then points.
    normalize_player: optional fn to merge aliases (e.g. 'Pablo Tomas Pesci' -> 'Tomas Pesci').
    """
    norm = normalize_player if normalize_player is not None else (lambda x: x)
    stats: dict[str, dict[str, int | float]] = {}
    for d in decks:
        player = norm(d.player or "(unknown)")
        if player not in stats:
            stats[player] = {"player": player, "wins": 0, "top2": 0, "top4": 0, "top8": 0, "points": 0.0, "deck_count": 0}
        s = stats[player]
        s["deck_count"] += 1
        s["points"] += _get_weight(d.rank)
        if d.rank == "1":
            s["wins"] += 1
        if d.rank in ("1", "2"):
            s["top2"] += 1
        if d.rank in ("1", "2", "3-4"):
            s["top4"] += 1
        if d.rank in ("1", "2", "3-4", "5-8"):
            s["top8"] += 1

    return sorted(
        stats.values(),
        key=lambda x: (-x["wins"], -x["points"]),
    )


_TYPE_ORDER = ("Land", "Creature", "Instant", "Sorcery", "Enchantment", "Artifact", "Planeswalker")


def _primary_type(type_line: str) -> str:
    """Extract primary card type from Scryfall type_line (e.g. 'Creature — Human' -> 'Creature')."""
    upper = type_line.upper()
    for t in _TYPE_ORDER:
        if t.upper() in upper:
            return t
    return "Other"


_COLOR_ORDER = ("W", "U", "B", "R", "G", "C", "M")
_COLOR_LABELS = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "C": "Colorless",
    "M": "Multicolor",
}


def _card_color_group(meta: dict) -> str:
    """Return a single-letter color group for grouping: W, U, B, R, G, C, or M (multicolor)."""
    colors = meta.get("colors") or meta.get("color_identity") or []
    if len(colors) == 0:
        return "C"
    if len(colors) > 1:
        return "M"
    return colors[0] if colors[0] in _COLOR_LABELS else "C"


def deck_analysis(deck: Deck, card_metadata: dict[str, dict]) -> dict[str, Any]:
    """Per-deck analysis: mana curve, color distribution, lands distribution, type distribution."""
    mana_curve: dict[int, int] = {}
    color_counts: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0, "C": 0}
    lands = 0
    nonlands = 0
    type_distribution: dict[str, int] = {}
    grouped_by_type: dict[str, list[tuple[int, str]]] = {}
    grouped_by_cmc: dict[int, list[tuple[int, str]]] = {}
    grouped_by_color: dict[str, list[tuple[int, str]]] = {}
    card_meta_out: dict[str, dict] = {}

    for qty, card in deck.mainboard:
        meta = card_metadata.get(card, {})
        type_line = (meta.get("type_line") or "").upper()
        is_land = "LAND" in type_line if meta else _is_land_card(card)
        primary = _primary_type(meta.get("type_line") or "") if meta else ("Land" if is_land else "Other")

        type_distribution[primary] = type_distribution.get(primary, 0) + qty
        grouped_by_type.setdefault(primary, []).append((qty, card))

        cmc_val = int(meta.get("cmc", 0)) if meta else 0
        grouped_by_cmc.setdefault(cmc_val, []).append((qty, card))

        color_group = _card_color_group(meta) if meta else "C"
        if is_land:
            color_group = "Land"
        grouped_by_color.setdefault(color_group, []).append((qty, card))

        if card not in card_meta_out and meta:
            card_meta_out[card] = {
                "mana_cost": meta.get("mana_cost", ""),
                "cmc": meta.get("cmc", 0),
                "type_line": meta.get("type_line", ""),
                "colors": meta.get("colors", []),
            }

        if is_land:
            lands += qty
        else:
            nonlands += qty
            cmc = meta.get("cmc")
            if cmc is not None:
                cmc_int = int(cmc) if isinstance(cmc, (int, float)) else 0
                mana_curve[cmc_int] = mana_curve.get(cmc_int, 0) + qty

        colors = meta.get("color_identity") or meta.get("colors") or []
        for c in colors:
            if c in color_counts:
                color_counts[c] += qty
        if not colors and meta:
            color_counts["C"] += qty

    total_color_slots = sum(color_counts.values())
    color_pct = {k: round(100 * v / total_color_slots, 1) if total_color_slots else 0 for k, v in color_counts.items()}

    grouped_by_type_sideboard: dict[str, list[tuple[int, str]]] = {}
    grouped_by_cmc_sideboard: dict[int, list[tuple[int, str]]] = {}
    grouped_by_color_sideboard: dict[str, list[tuple[int, str]]] = {}
    for qty, card in deck.sideboard:
        meta = card_metadata.get(card, {})
        type_line = (meta.get("type_line") or "").upper()
        is_land = "LAND" in type_line if meta else _is_land_card(card)
        primary = _primary_type(meta.get("type_line") or "") if meta else ("Land" if is_land else "Other")
        grouped_by_type_sideboard.setdefault(primary, []).append((qty, card))

        cmc_val = int(meta.get("cmc", 0)) if meta else 0
        grouped_by_cmc_sideboard.setdefault(cmc_val, []).append((qty, card))

        color_group = _card_color_group(meta) if meta else "C"
        if is_land:
            color_group = "Land"
        grouped_by_color_sideboard.setdefault(color_group, []).append((qty, card))

        if card not in card_meta_out and meta:
            card_meta_out[card] = {
                "mana_cost": meta.get("mana_cost", ""),
                "cmc": meta.get("cmc", 0),
                "type_line": meta.get("type_line", ""),
                "colors": meta.get("colors", []),
            }

    sorted_types = sorted(
        grouped_by_type.keys(),
        key=lambda t: (_TYPE_ORDER.index(t) if t in _TYPE_ORDER else 99, t),
    )
    sorted_types_sb = sorted(
        grouped_by_type_sideboard.keys(),
        key=lambda t: (_TYPE_ORDER.index(t) if t in _TYPE_ORDER else 99, t),
    )
    color_key_order = list(_COLOR_ORDER) + ["Land"]
    sorted_colors = sorted(
        grouped_by_color.keys(),
        key=lambda c: (color_key_order.index(c) if c in color_key_order else 99, c),
    )
    sorted_colors_sb = sorted(
        grouped_by_color_sideboard.keys(),
        key=lambda c: (color_key_order.index(c) if c in color_key_order else 99, c),
    )

    return {
        "mana_curve": dict(sorted(mana_curve.items())),
        "color_distribution": color_pct,
        "lands_distribution": {"lands": lands, "nonlands": nonlands},
        "type_distribution": type_distribution,
        "grouped_by_type": {t: grouped_by_type[t] for t in sorted_types},
        "grouped_by_type_sideboard": {t: grouped_by_type_sideboard[t] for t in sorted_types_sb},
        "grouped_by_cmc": {str(k): grouped_by_cmc[k] for k in sorted(grouped_by_cmc.keys())},
        "grouped_by_cmc_sideboard": {str(k): grouped_by_cmc_sideboard[k] for k in sorted(grouped_by_cmc_sideboard.keys())},
        "grouped_by_color": {c: grouped_by_color[c] for c in sorted_colors},
        "grouped_by_color_sideboard": {c: grouped_by_color_sideboard[c] for c in sorted_colors_sb},
        "card_meta": card_meta_out,
    }


def deck_diversity(decks: list[Deck]) -> dict[str, Any]:
    """Unique commanders/archetypes, simple diversity metrics."""
    commanders = set()
    archetypes = set()
    for d in decks:
        if d.commanders:
            commanders.add(" / ".join(sorted(d.commanders)))
        archetypes.add(d.archetype or "(unknown)")
    return {
        "total_decks": len(decks),
        "unique_commanders": len(commanders),
        "unique_archetypes": len(archetypes),
    }


def analyze(
    decks: list[Deck],
    placement_weighted: bool = False,
    ignore_lands: bool = False,
    include_card_synergy: bool = True,
) -> dict[str, Any]:
    """Full metagame analysis."""
    result: dict[str, Any] = {
        "summary": deck_diversity(decks),
        "commander_distribution": commander_distribution(decks, placement_weighted),
        "archetype_distribution": archetype_distribution(decks, placement_weighted),
        "top_cards_main": top_cards_main(decks, placement_weighted, ignore_lands),
        "placement_weighted": placement_weighted,
        "ignore_lands": ignore_lands,
    }
    if include_card_synergy and len(decks) >= 3:
        result["card_synergy"] = card_synergy(decks, min_decks=2, top_n=30, ignore_lands=ignore_lands)
    else:
        result["card_synergy"] = []
    return result


def card_synergy(
    decks: list[Deck],
    min_decks: int = 3,
    top_n: int = 50,
    ignore_lands: bool = False,
) -> list[dict[str, Any]]:
    """Cards often played together: pairs that co-occur in many decks."""
    from collections import defaultdict

    pair_counts: dict[tuple[str, str], int] = defaultdict(int)

    for d in decks:
        cards = set()
        for qty, card in d.mainboard:
            if card in BASIC_LANDS:
                continue
            if ignore_lands and _is_land_card(card):
                continue
            cards.add(card)
        cards_list = sorted(cards)
        for i in range(len(cards_list)):
            for j in range(i + 1, len(cards_list)):
                a, b = cards_list[i], cards_list[j]
                pair_counts[(a, b)] += 1

    return [
        {
            "card_a": a,
            "card_b": b,
            "decks": count,
        }
        for (a, b), count in sorted(pair_counts.items(), key=lambda x: -x[1])
        if count >= min_decks
    ][:top_n]


def similar_decks(
    deck: Deck,
    all_decks: list[Deck],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return decks with highest card overlap (Jaccard similarity on mainboard)."""
    deck_cards = set(c for _, c in deck.mainboard)
    if not deck_cards:
        return []

    results: list[tuple[float, Deck]] = []
    for d in all_decks:
        if d.deck_id == deck.deck_id:
            continue
        other_cards = set(c for _, c in d.mainboard)
        if not other_cards:
            continue
        intersection = len(deck_cards & other_cards)
        union = len(deck_cards | other_cards)
        sim = intersection / union if union else 0
        results.append((sim, d))

    results.sort(key=lambda x: -x[0])
    return [
        {
            "deck_id": d.deck_id,
            "name": d.name,
            "player": d.player,
            "event_name": d.event_name,
            "date": d.date,
            "rank": d.rank,
            "similarity": round(sim * 100, 1),
        }
        for sim, d in results[:limit]
    ]


def find_duplicate_decks(decks: list[Deck]) -> dict[int, list[int]]:
    """Deck IDs that are duplicates (identical mainboard). Returns {deck_id: [other_duplicate_ids]}."""
    def mainboard_key(d: Deck) -> tuple:
        return tuple(sorted((qty, c) for qty, c in d.mainboard))

    by_key: dict[tuple, list[int]] = {}
    for d in decks:
        k = mainboard_key(d)
        by_key.setdefault(k, []).append(d.deck_id)

    return {ids[0]: ids[1:] for ids in by_key.values() if len(ids) > 1}


def write_report(report: dict[str, Any], path: str) -> None:
    """Write analysis report as JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

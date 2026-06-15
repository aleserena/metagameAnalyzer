"""Card metadata and images.

Card metadata, oracle text and prices come from MTGJSON, stored in the ``cards``
Postgres table (populated by ``api/services/mtgjson.py``). Images are built from
each card's ``scryfall_id`` and served from Scryfall's CDN — no per-card Scryfall
API call on the hot path. The legacy Scryfall API client remains as a thin fallback
(``_scryfall_lookup_cards``) for names missing from the table (e.g. fresh spoilers).

The oracle-tag functional-category system (``refresh_otag_index`` /
``get_card_categories``) still uses the Scryfall search API — MTGJSON has no
equivalent and it is a periodic admin refresh, not on the per-request path.
"""

import json
import os
import time
from pathlib import Path

import requests

from .storage import load_json, save_json

SCRYFALL_COLLECTION = "https://api.scryfall.com/cards/collection"
SCRYFALL_NAMED = "https://api.scryfall.com/cards/named"
SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search"
SCRYFALL_AUTOCOMPLETE = "https://api.scryfall.com/cards/autocomplete"
SCRYFALL_IMAGE_BASE = "https://cards.scryfall.io"
CACHE_FILE = Path(__file__).resolve().parent.parent.parent / ".scryfall_cache.json"
OTAG_CACHE_FILE = Path(__file__).resolve().parent.parent.parent / ".scryfall_otag_cache.json"
REQUEST_DELAY = 0.1  # ~10 req/s rate limit
AUTOCOMPLETE_MIN_LEN = 2
SCRYFALL_HEADERS = {"User-Agent": "MTGMetagameAnalyzer/1.0 (metagame-analyzer)"}

# Fall back to the Scryfall API for names not found in the MTGJSON-backed `cards`
# table. Disable via MTGJSON_SCRYFALL_FALLBACK=0 to guarantee zero Scryfall calls.
SCRYFALL_FALLBACK_ENABLED = os.getenv("MTGJSON_SCRYFALL_FALLBACK", "1").lower() not in ("0", "false", "no")

IMAGE_SIZES = ("small", "normal", "large")
# Layouts with a distinct back image (built from the same scryfall_id via /back/).
TWO_FACED_LAYOUTS = frozenset({"transform", "modal_dfc", "reversible_card", "double_faced_token"})


def scryfall_image_urls(scryfall_id: str, face: str = "front") -> dict[str, str] | None:
    """Build Scryfall CDN image URLs for a printing UUID.

    Path scheme: ``/<size>/<face>/<a>/<b>/<scryfall_id>.jpg`` where a/b are the first
    two characters of the UUID. Returns None when ``scryfall_id`` is missing/too short.
    """
    if not scryfall_id or len(scryfall_id) < 2:
        return None
    a, b = scryfall_id[0], scryfall_id[1]
    return {
        size: f"{SCRYFALL_IMAGE_BASE}/{size}/{face}/{a}/{b}/{scryfall_id}.jpg"
        for size in IMAGE_SIZES
    }

# Maps our internal category keys → Scryfall oracle tag names to query.
# Categories not listed here (land, manaless, ward) are heuristic-only.
CATEGORY_TO_OTAGS: dict[str, list[str]] = {
    "ramp": ["ramp"],
    "removal": ["removal"],
    "wipe": ["wrath"],
    "disenchant": ["enchantment-removal", "artifact-removal"],
    "counter": ["counterspell"],
    "card-draw": ["card-draw"],
    "tutor": ["tutor"],
    "graveyard": ["reanimation"],
    "token": ["token-generator"],
    "protection": ["protection"],
    "evasion": ["evasion"],
    "lifegain": ["lifegain"],
    "combat-trick": ["combat-trick"],
    "uncounterable": ["uncounterable"],
    "hatebear": ["stax"],
    "discard": ["discard"],
}


_card_cache: dict[str, dict] = {}

# card_name → sorted list of our internal category keys, built from Scryfall otag searches.
_otag_index: dict[str, list[str]] = {}
_otag_index_loaded = False


def _load_otag_index() -> None:
    global _otag_index, _otag_index_loaded
    if _otag_index_loaded:
        return
    data = load_json(OTAG_CACHE_FILE, default={}, suppress_errors=True)
    _otag_index = data or {}
    _otag_index_loaded = True


def _save_otag_index() -> None:
    save_json(OTAG_CACHE_FILE, _otag_index, ensure_ascii=False, suppress_errors=True)


def _fetch_cards_for_otag(otag: str) -> set[str]:
    """Fetch all card names from Scryfall with the given oracle tag (paginated)."""
    names: set[str] = set()
    url: str | None = SCRYFALL_SEARCH
    params: dict[str, str] = {"q": f"otag:{otag}", "unique": "cards", "order": "name"}
    while url:
        time.sleep(REQUEST_DELAY)
        try:
            r = requests.get(url, params=params, headers=SCRYFALL_HEADERS, timeout=30)
            if r.status_code == 404:
                break
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, json.JSONDecodeError):
            break
        for card in data.get("data", []):
            name = card.get("name", "")
            if name:
                names.add(name)
        url = data.get("next_page")
        params = {}
    return names


def refresh_otag_index(categories: list[str] | None = None) -> dict[str, int]:
    """Build or refresh the oracle tag index for the given category keys (all if None).

    Queries the Scryfall search API for each associated oracle tag and persists
    a card_name → [category_keys] mapping to OTAG_CACHE_FILE.

    Returns {category_key: card_count} for each refreshed category.
    """
    global _otag_index, _otag_index_loaded
    _load_otag_index()
    _otag_index_loaded = True  # prevent stale-load mid-refresh

    target_cats = categories or list(CATEGORY_TO_OTAGS.keys())

    # Collect unique otag names needed and which categories they feed
    otag_to_cats: dict[str, set[str]] = {}
    for cat in target_cats:
        for otag in CATEGORY_TO_OTAGS.get(cat, []):
            otag_to_cats.setdefault(otag, set()).add(cat)

    # Fetch cards per otag and update index
    otag_to_names: dict[str, set[str]] = {}
    for otag, cats in otag_to_cats.items():
        names = _fetch_cards_for_otag(otag)
        otag_to_names[otag] = names
        for name in names:
            existing = set(_otag_index.get(name, []))
            existing.update(cats)
            _otag_index[name] = sorted(existing)

    _save_otag_index()

    result: dict[str, int] = {}
    for cat in target_cats:
        combined: set[str] = set()
        for otag in CATEGORY_TO_OTAGS.get(cat, []):
            combined.update(otag_to_names.get(otag, set()))
        result[cat] = len(combined)
    return result


def get_card_categories(card_name: str) -> list[str] | None:
    """Return functional category keys for a card from the oracle tag index.

    Returns None when the index is empty (not yet built) — callers should fall
    back to text heuristics. Returns [] when the card is known but has no tags.
    """
    _load_otag_index()
    if not _otag_index:
        return None
    return _otag_index.get(card_name, [])


def _load_cache() -> None:
    global _card_cache
    if _card_cache:
        return
    data = load_json(CACHE_FILE, default={}, suppress_errors=True)
    _card_cache = data or {}


def _save_cache() -> None:
    save_json(CACHE_FILE, _card_cache, ensure_ascii=False, suppress_errors=True)


def clear_cache() -> None:
    """Clear in-memory card cache and delete the cache file."""
    global _card_cache
    _card_cache = {}
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
    except OSError:
        pass


def _scryfall_lookup_name(name: str) -> str:
    """For split cards like 'Fire // Ice', Scryfall collection API needs just the first half."""
    if " // " in name:
        return name.split(" // ")[0]
    return name


def _name_for_scryfall(name: str) -> str:
    """Normalize name for Scryfall collection API without rewriting punctuation/casing."""
    return _scryfall_lookup_name(name).strip()


def _fetch_named(card_name: str) -> dict | None:
    """Fetch a card by exact name via /cards/named. Returns card object or None."""
    if not card_name:
        return None
    time.sleep(REQUEST_DELAY)
    try:
        r = requests.get(
            SCRYFALL_NAMED,
            params={"fuzzy": card_name},
            headers=SCRYFALL_HEADERS,
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
    except (requests.RequestException, json.JSONDecodeError):
        pass
    return None


def _fetch_paper_printing(card_name: str) -> dict | None:
    """Fetch a paper printing of the card via search API. Returns card object or None."""
    if not card_name:
        return None
    time.sleep(REQUEST_DELAY)
    try:
        q = f'!"{card_name}" game:paper'
        r = requests.get(
            SCRYFALL_SEARCH,
            params={"q": q, "unique": "cards"},
            headers=SCRYFALL_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        cards = data.get("data", [])
        if cards:
            return cards[0]
    except (requests.RequestException, json.JSONDecodeError):
        pass
    return None


def _search_by_flavor_name(typed_name: str) -> dict | None:
    """Search Scryfall for a card whose flavor_name matches typed_name. Returns card object or None."""
    if not typed_name or not typed_name.strip():
        return None
    time.sleep(REQUEST_DELAY)
    try:
        # Search cards that have a flavor name and match the typed string (fulltext may match flavor_name)
        q = f'has:flavorname "{typed_name}" game:paper'
        r = requests.get(
            SCRYFALL_SEARCH,
            params={"q": q, "unique": "cards"},
            headers=SCRYFALL_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        cards = data.get("data", []) or []
        normalized = typed_name.strip()
        for card in cards:
            fn = card.get("flavor_name") or ""
            if fn.strip().lower() == normalized.lower():
                return card
    except (requests.RequestException, json.JSONDecodeError):
        pass
    return None


def _card_is_paper(card: dict) -> bool:
    """True if this printing is available in paper."""
    games = card.get("games") or []
    return "paper" in games


def _build_entry(card: dict) -> dict:
    """Build the standard lookup entry from a Scryfall card object."""
    image_uris = card.get("image_uris")
    faces = card.get("card_faces") or []
    first_face = faces[0] if faces else {}
    if not image_uris and faces:
        image_uris = first_face.get("image_uris")
    mana_cost = card.get("mana_cost") or first_face.get("mana_cost", "")
    type_line = card.get("type_line") or first_face.get("type_line", "")
    cmc = card.get("cmc")
    if cmc is None and first_face:
        cmc = first_face.get("cmc", 0)
    cmc = cmc if cmc is not None else 0
    colors = card.get("colors")
    if not colors and first_face:
        colors = first_face.get("colors", [])
    colors = colors or []
    oracle_text = card.get("oracle_text") or ""
    if not oracle_text and faces:
        oracle_text = " // ".join(f.get("oracle_text", "") for f in faces if f.get("oracle_text"))
    entry = {
        "name": card.get("name"),
        "image_uris": image_uris,
        "mana_cost": mana_cost,
        "cmc": cmc,
        "type_line": type_line,
        "oracle_text": oracle_text,
        "colors": colors,
        "color_identity": card.get("color_identity", []),
        "prices": card.get("prices"),
    }
    if len(faces) >= 2:
        entry["card_faces"] = [
            {"name": f.get("name", ""), "image_uris": f.get("image_uris")}
            for f in faces
        ]
    else:
        entry["card_faces"] = [
            {"name": card.get("name", ""), "image_uris": image_uris}
        ]
    return entry


def _row_to_entry(row) -> dict:
    """Map a ``cards`` DB row to the standard lookup entry (same shape as Scryfall path).

    Images are built from ``scryfall_id``; two-faced layouts get front/back faces.
    """
    faces = row.card_faces or []
    two_faced = row.layout in TWO_FACED_LAYOUTS and len(faces) >= 2
    if two_faced:
        front = scryfall_image_urls(row.scryfall_id, "front")
        back = scryfall_image_urls(row.scryfall_id, "back")
        card_faces = [
            {"name": faces[0].get("name", "") or row.name, "image_uris": front},
            {"name": faces[1].get("name", "") or row.name, "image_uris": back},
        ]
        top_image = None
    else:
        image = scryfall_image_urls(row.scryfall_id, "front")
        card_faces = [{"name": row.name, "image_uris": image}]
        top_image = image
    return {
        "name": row.name,
        "image_uris": top_image,
        "mana_cost": row.mana_cost or "",
        "cmc": row.cmc if row.cmc is not None else 0,
        "type_line": row.type_line or "",
        "oracle_text": row.oracle_text or "",
        "colors": row.colors or [],
        "color_identity": row.color_identity or [],
        "prices": {
            "usd": row.price_usd,
            "usd_foil": row.price_usd_foil,
            "eur": row.price_eur,
            "eur_foil": row.price_eur_foil,
            "tix": None,
        },
        "card_faces": card_faces,
    }


def lookup_cards(card_names: list[str]) -> dict[str, dict]:
    """Look up cards by name. Returns {card_name: {image_uris, mana_cost, cmc, type_line, ...}}.

    Reads from the MTGJSON-backed ``cards`` table; names not found there fall back to
    the Scryfall API (unless disabled). Returns the same entry shape from both paths.
    """
    names = list(dict.fromkeys(card_names))
    result: dict[str, dict] = {}
    missing: list[str] = []

    try:
        from api import db as _db

        if _db.is_database_available():
            with _db.session_scope() as session:
                rows = _db.get_cards_by_name(session, names)
                for name in names:
                    row = rows.get(name)
                    if row is not None:
                        result[name] = _row_to_entry(row)
                    else:
                        missing.append(name)
        else:
            missing = list(names)
    except Exception:
        missing = list(names)

    if missing and SCRYFALL_FALLBACK_ENABLED:
        result.update(_scryfall_lookup_cards(missing))
    return result


def _scryfall_lookup_cards(card_names: list[str]) -> dict[str, dict]:
    """Legacy Scryfall API lookup, used as a fallback for cards missing from the DB."""
    _load_cache()
    names = list(dict.fromkeys(card_names))
    result: dict[str, dict] = {}
    to_fetch: list[str] = []

    for name in names:
        cached = _card_cache.get(name)
        if cached and "error" not in cached and "card_faces" in cached and "oracle_text" in cached:
            result[name] = cached
        else:
            to_fetch.append(name)

    if not to_fetch:
        return result

    for i in range(0, len(to_fetch), 75):
        chunk = to_fetch[i : i + 75]
        identifiers = [{"name": _name_for_scryfall(n)} for n in chunk]
        lookup_to_original: dict[str, str] = {}
        for n in chunk:
            lookup_to_original[_name_for_scryfall(n)] = n

        time.sleep(REQUEST_DELAY)
        try:
            r = requests.post(
                SCRYFALL_COLLECTION,
                json={"identifiers": identifiers},
                headers=SCRYFALL_HEADERS,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, json.JSONDecodeError):
            continue

        not_found_lookup_names = set()
        for nf in data.get("not_found", []):
            nf_name = nf.get("name", "") if isinstance(nf, dict) else str(nf)
            not_found_lookup_names.add(nf_name)

        data_list = data.get("data", [])
        data_idx = 0
        for idx in range(len(chunk)):
            lookup_name = _name_for_scryfall(chunk[idx])
            if lookup_name in not_found_lookup_names:
                _card_cache[chunk[idx]] = {"error": "not_found"}
                continue
            if data_idx >= len(data_list):
                break
            card = data_list[data_idx]
            data_idx += 1
            orig_name = chunk[idx]

            if not _card_is_paper(card):
                paper_card = _fetch_paper_printing(card.get("name", ""))
                if paper_card:
                    card = paper_card

            # If prices are still null, fall back to /cards/named which picks a priced printing
            if not (card.get("prices") or {}).get("usd"):
                named_card = _fetch_named(card.get("name", "") or orig_name)
                if named_card and (named_card.get("prices") or {}).get("usd"):
                    card = named_card

            entry = _build_entry(card)
            result[orig_name] = entry
            _card_cache[orig_name] = entry
            _card_cache[card.get("name", "")] = entry

    # Second pass: for names still not found, search by flavor_name (e.g. Universes Within names)
    still_missing = [n for n in names if n not in result or result.get(n, {}).get("error")]
    for orig_name in still_missing:
        card = _search_by_flavor_name(orig_name)
        if not card:
            continue
        if not _card_is_paper(card):
            paper_card = _fetch_paper_printing(card.get("name", ""))
            if paper_card:
                card = paper_card
        if not (card.get("prices") or {}).get("usd"):
            named_card = _fetch_named(card.get("name", "") or orig_name)
            if named_card and (named_card.get("prices") or {}).get("usd"):
                card = named_card
        entry = _build_entry(card)
        result[orig_name] = entry
        _card_cache[orig_name] = entry
        _card_cache[card.get("name", "")] = entry

    _save_cache()
    return result


def autocomplete_cards(prefix: str, role: str | None = None) -> list[str]:
    """Return card names matching the given prefix (for typeahead).

    Queries the local MTGJSON-backed ``cards`` table when a database is available;
    otherwise falls back to the Scryfall autocomplete API. When ``role`` is given,
    the DB query restricts results to cards matching that commander/partner
    mechanic (the Scryfall autocomplete fallback does not support role filtering).
    """
    q = (prefix or "").strip()
    if len(q) < AUTOCOMPLETE_MIN_LEN:
        return []

    try:
        from api import db as _db

        if _db.is_database_available():
            with _db.session_scope() as session:
                return _db.search_card_names(session, q, limit=20, role=role)
    except Exception:
        pass

    if not SCRYFALL_FALLBACK_ENABLED:
        return []
    time.sleep(REQUEST_DELAY)
    try:
        r = requests.get(
            SCRYFALL_AUTOCOMPLETE,
            params={"q": q},
            headers=SCRYFALL_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("data") or []
    except (requests.RequestException, json.JSONDecodeError):
        return []

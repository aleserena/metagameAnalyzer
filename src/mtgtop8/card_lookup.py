"""Scryfall API client for card metadata and images."""

import json
import time
from pathlib import Path

import requests

SCRYFALL_COLLECTION = "https://api.scryfall.com/cards/collection"
SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search"
CACHE_FILE = Path(__file__).resolve().parent.parent.parent / ".scryfall_cache.json"
REQUEST_DELAY = 0.1  # ~10 req/s rate limit


_card_cache: dict[str, dict] = {}


def _load_cache() -> None:
    global _card_cache
    if _card_cache:
        return
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                _card_cache = json.load(f)
        except Exception:
            pass


def _save_cache() -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_card_cache, f, ensure_ascii=False)
    except Exception:
        pass


def clear_cache() -> None:
    """Clear in-memory card cache and delete the cache file."""
    global _card_cache
    _card_cache = {}
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
    except Exception:
        pass


def _scryfall_lookup_name(name: str) -> str:
    """For split cards like 'Fire // Ice', Scryfall collection API needs just the first half."""
    if " // " in name:
        return name.split(" // ")[0]
    return name


def _name_for_scryfall(name: str) -> str:
    """Normalize name for Scryfall collection API (exact match). Title-case so 'Lunarch veteran' matches 'Lunarch Veteran'."""
    return _scryfall_lookup_name(name).title()


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
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        cards = data.get("data", [])
        if cards:
            return cards[0]
    except Exception:
        pass
    return None


def _card_is_paper(card: dict) -> bool:
    """True if this printing is available in paper."""
    games = card.get("games") or []
    return "paper" in games


def lookup_cards(card_names: list[str]) -> dict[str, dict]:
    """Look up cards by name. Returns {card_name: {image_uris, mana_cost, cmc, type_line, ...}}."""
    _load_cache()
    names = list(dict.fromkeys(card_names))
    result: dict[str, dict] = {}
    to_fetch: list[str] = []

    for name in names:
        cached = _card_cache.get(name)
        if cached and "error" not in cached and "card_faces" in cached:
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
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception:
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

            image_uris = card.get("image_uris")
            faces = card.get("card_faces") or []
            first_face = faces[0] if faces else {}
            if not image_uris and faces:
                image_uris = first_face.get("image_uris")
            # Multi-faced cards report mana_cost and type_line on card_faces, not at root
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
            entry = {
                "name": card.get("name"),
                "image_uris": image_uris,
                "mana_cost": mana_cost,
                "cmc": cmc,
                "type_line": type_line,
                "colors": colors,
                "color_identity": card.get("color_identity", []),
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
            result[orig_name] = entry
            _card_cache[orig_name] = entry
            _card_cache[card.get("name", "")] = entry

    _save_cache()
    return result

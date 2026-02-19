"""Scryfall API client for card metadata and images."""

import json
import time
from pathlib import Path

import requests

SCRYFALL_COLLECTION = "https://api.scryfall.com/cards/collection"
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


def _scryfall_lookup_name(name: str) -> str:
    """For split cards like 'Fire // Ice', Scryfall collection API needs just the first half."""
    if " // " in name:
        return name.split(" // ")[0]
    return name


def lookup_cards(card_names: list[str]) -> dict[str, dict]:
    """Look up cards by name. Returns {card_name: {image_uris, mana_cost, cmc, type_line, ...}}."""
    _load_cache()
    names = list(dict.fromkeys(card_names))
    result: dict[str, dict] = {}
    to_fetch: list[str] = []

    for name in names:
        cached = _card_cache.get(name)
        if cached and "error" not in cached:
            result[name] = cached
        else:
            to_fetch.append(name)

    if not to_fetch:
        return result

    for i in range(0, len(to_fetch), 75):
        chunk = to_fetch[i : i + 75]
        identifiers = [{"name": _scryfall_lookup_name(n)} for n in chunk]
        lookup_to_original: dict[str, str] = {}
        for n in chunk:
            lookup_to_original[_scryfall_lookup_name(n)] = n

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

        found_lookup_names = [_scryfall_lookup_name(c) for c in chunk if _scryfall_lookup_name(c) not in not_found_lookup_names]
        for idx, card in enumerate(data.get("data", [])):
            if idx < len(found_lookup_names):
                orig_name = lookup_to_original.get(found_lookup_names[idx], card.get("name", ""))
            else:
                orig_name = card.get("name", "")

            image_uris = card.get("image_uris")
            if not image_uris and card.get("card_faces"):
                image_uris = card["card_faces"][0].get("image_uris")
            entry = {
                "name": card.get("name"),
                "image_uris": image_uris,
                "mana_cost": card.get("mana_cost", ""),
                "cmc": card.get("cmc", 0),
                "type_line": card.get("type_line", ""),
                "colors": card.get("colors", []),
                "color_identity": card.get("color_identity", []),
            }
            if entry["image_uris"]:
                result[orig_name] = entry
                _card_cache[orig_name] = entry
                _card_cache[card.get("name", "")] = entry

        for nf in data.get("not_found", []):
            nf_name = nf.get("name", "") if isinstance(nf, dict) else str(nf)
            orig = lookup_to_original.get(nf_name, nf_name)
            if orig in chunk:
                _card_cache[orig] = {"error": "not_found"}

    _save_cache()
    return result

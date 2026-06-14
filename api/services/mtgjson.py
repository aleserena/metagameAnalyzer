"""MTGJSON sync: download bulk card data and populate the ``cards`` table.

MTGJSON is distributed as static, daily-rebuilt JSON files (no live REST API).
We source card metadata from ``AtomicCards.json`` (name-keyed) and a representative
printing's ``scryfallId`` + UUID from ``AllIdentifiers.json`` (UUID-keyed), using
``SetList.json`` release dates to pick the newest paper printing. Prices come from
``AllPricesToday.json`` (UUID-keyed) in a separate step.

Large files are streamed with ``ijson`` so we never hold a whole file in memory.
Downloads are on demand only (admin button / CLI) — there is no auto-sync.

Pure helpers (``atomic_card_to_row``, ``extract_prices``, ``pick_representative_printing``)
are unit-tested in ``tests/test_mtgjson_sync.py``; the network/DB orchestration
(``sync_metadata`` / ``sync_prices``) is exercised manually via the sync script.
"""

from __future__ import annotations

import gzip
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Iterable

import ijson
import requests

logger = logging.getLogger(__name__)

MTGJSON_BASE = "https://mtgjson.com/api/v5"
ATOMIC_CARDS_URL = f"{MTGJSON_BASE}/AtomicCards.json.gz"
ALL_IDENTIFIERS_URL = f"{MTGJSON_BASE}/AllIdentifiers.json.gz"
ALL_PRICES_TODAY_URL = f"{MTGJSON_BASE}/AllPricesToday.json.gz"
SET_LIST_URL = f"{MTGJSON_BASE}/SetList.json"

_DOWNLOAD_TIMEOUT = 300  # seconds; large files
_WUBRG = "WUBRG"
_UPSERT_BATCH = 1000

# Layouts that have a distinct front and back image (built from the same scryfallId).
# Meld is intentionally excluded: its back face is a different card entirely.
TWO_FACED_LAYOUTS = frozenset({"transform", "modal_dfc", "reversible_card", "double_faced_token"})


# --- Pure helpers -----------------------------------------------------------


def _sort_colors(colors: Iterable[str]) -> list[str]:
    """Sort a color set into WUBRG order (unknown symbols last)."""
    uniq = {c for c in colors if c}
    return sorted(uniq, key=lambda c: _WUBRG.index(c) if c in _WUBRG else 99)


def atomic_card_to_row(name: str, faces: list[dict]) -> dict:
    """Convert an AtomicCards entry (name + list of face objects) into card-row fields.

    Returns the metadata columns only (no ``scryfall_id`` / ``mtgjson_uuid`` / prices).
    For multi-face cards (split/DFC/adventure) mana cost, type line and oracle text are
    joined with `` // ``; ``cmc`` uses the first face; colors/identity are unioned.
    """
    faces = faces or []
    first = faces[0] if faces else {}

    mana_costs = [f.get("manaCost", "") for f in faces if f.get("manaCost")]
    if len(mana_costs) > 1:
        mana_cost = " // ".join(mana_costs)
    else:
        mana_cost = mana_costs[0] if mana_costs else ""

    cmc = first.get("manaValue", first.get("convertedManaCost", 0)) or 0

    types = [f.get("type", "") for f in faces if f.get("type")]
    if len(types) > 1:
        type_line = " // ".join(types)
    else:
        type_line = types[0] if types else ""

    colors = _sort_colors(c for f in faces for c in (f.get("colors") or []))
    color_identity = _sort_colors(c for f in faces for c in (f.get("colorIdentity") or []))

    texts = [f.get("text", "") for f in faces if f.get("text")]
    oracle_text = " // ".join(texts)

    layout = first.get("layout") or "normal"

    card_faces = [
        {"name": f.get("faceName") or f.get("name") or name, "side": f.get("side")}
        for f in faces
    ] or [{"name": name, "side": None}]

    return {
        "name": name,
        "mana_cost": mana_cost,
        "cmc": float(cmc),
        "type_line": type_line,
        "oracle_text": oracle_text,
        "colors": colors,
        "color_identity": color_identity,
        "layout": layout,
        "card_faces": card_faces,
    }


def _latest_price(node: dict | None) -> str | None:
    """Return the most-recent dated price in a ``{date: price}`` map as a string."""
    if not node:
        return None
    latest_date = max(node.keys())
    value = node.get(latest_date)
    return None if value is None else str(value)


def extract_prices(price_entry: dict | None) -> dict:
    """Extract {usd, usd_foil, eur, eur_foil} from an AllPricesToday entry for one UUID.

    USD comes from ``paper.tcgplayer.retail``; EUR from ``paper.cardmarket.retail``.
    """
    paper = (price_entry or {}).get("paper") or {}

    def retail(provider: str, finish: str) -> str | None:
        node = (((paper.get(provider) or {}).get("retail") or {}).get(finish)) or {}
        return _latest_price(node)

    return {
        "usd": retail("tcgplayer", "normal"),
        "usd_foil": retail("tcgplayer", "foil"),
        "eur": retail("cardmarket", "normal"),
        "eur_foil": retail("cardmarket", "foil"),
    }


def pick_representative_printing(entries: list[tuple[str, dict]], set_release: dict[str, str]) -> dict | None:
    """Pick the representative printing for a card from its AllIdentifiers entries.

    ``entries`` is a list of (uuid, entry). Prefers paper printings, then the newest
    set release date. Entries without a ``scryfallId`` are skipped. Returns
    ``{"scryfall_id", "uuid"}`` or ``None`` when no entry has a ``scryfallId``.
    """
    best = None
    best_key = None
    for uuid, entry in entries:
        sid = (entry.get("identifiers") or {}).get("scryfallId")
        if not sid:
            continue
        paper = "paper" in (entry.get("availability") or [])
        rel = set_release.get(entry.get("setCode") or "", "")
        key = (paper, rel)
        if best_key is None or key > best_key:
            best_key = key
            best = {"scryfall_id": sid, "uuid": uuid}
    return best


# --- Download / streaming ---------------------------------------------------


def _stream_kvitems(url: str, prefix: str = "data"):
    """Yield (key, value) pairs from the object at ``prefix`` in a (gzipped) JSON file.

    Streams the HTTP response through gzip + ijson so the full file is never loaded.
    """
    resp = requests.get(url, stream=True, timeout=_DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    resp.raw.decode_content = False  # we decompress gzip ourselves
    if url.endswith(".gz"):
        stream = gzip.GzipFile(fileobj=resp.raw)
    else:
        stream = resp.raw
    try:
        yield from ijson.kvitems(stream, prefix)
    finally:
        resp.close()


def _load_set_release_dates() -> dict[str, str]:
    """Return {set_code: releaseDate} from SetList.json (small file)."""
    resp = requests.get(SET_LIST_URL, timeout=_DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    data = resp.json().get("data") or []
    return {s.get("code"): (s.get("releaseDate") or "") for s in data if s.get("code")}


def _build_identifier_map(set_release: dict[str, str]) -> dict[str, dict]:
    """Stream AllIdentifiers and return {name: {scryfall_id, uuid}} for the best printing.

    Tracks the best printing per name incrementally to avoid holding all printings.
    """
    best_by_name: dict[str, dict] = {}
    best_key_by_name: dict[str, tuple] = {}
    for uuid, entry in _stream_kvitems(ALL_IDENTIFIERS_URL):
        name = entry.get("name")
        sid = (entry.get("identifiers") or {}).get("scryfallId")
        if not name or not sid:
            continue
        paper = "paper" in (entry.get("availability") or [])
        rel = set_release.get(entry.get("setCode") or "", "")
        key = (paper, rel)
        if name not in best_key_by_name or key > best_key_by_name[name]:
            best_key_by_name[name] = key
            best_by_name[name] = {"scryfall_id": sid, "uuid": uuid}
    return best_by_name


# --- Orchestration ----------------------------------------------------------


def sync_metadata() -> dict:
    """Download MTGJSON metadata and upsert the ``cards`` table. Returns {cards_synced}."""
    from api import db as _db

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset)")

    logger.info("MTGJSON sync: loading set release dates")
    set_release = _load_set_release_dates()
    logger.info("MTGJSON sync: building identifier map from AllIdentifiers")
    identifier_map = _build_identifier_map(set_release)

    logger.info("MTGJSON sync: streaming AtomicCards and building rows")
    rows: list[dict] = []
    for name, faces in _stream_kvitems(ATOMIC_CARDS_URL):
        row = atomic_card_to_row(name, faces)
        ident = identifier_map.get(name)
        row["scryfall_id"] = ident["scryfall_id"] if ident else None
        row["mtgjson_uuid"] = ident["uuid"] if ident else None
        rows.append(row)

    logger.info("MTGJSON sync: upserting %d cards", len(rows))
    with _db.session_scope() as session:
        count = _db.upsert_cards(session, rows, batch_size=_UPSERT_BATCH)
    logger.info("MTGJSON sync: upserted %d cards", count)
    return {"cards_synced": count}


def sync_prices() -> dict:
    """Download AllPricesToday and update price columns by UUID. Returns {prices_updated}."""
    from api import db as _db

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset)")

    with _db.session_scope() as session:
        wanted = _db.get_card_uuids(session)
    logger.info("MTGJSON price sync: %d card UUIDs to price", len(wanted))
    if not wanted:
        return {"prices_updated": 0}

    updates: dict[str, dict] = {}
    for uuid, entry in _stream_kvitems(ALL_PRICES_TODAY_URL):
        if uuid in wanted:
            updates[uuid] = extract_prices(entry)

    with _db.session_scope() as session:
        count = _db.update_card_prices(session, updates, batch_size=_UPSERT_BATCH)
    logger.info("MTGJSON price sync: updated prices for %d cards", count)
    return {"prices_updated": count}


# --- Background job runner --------------------------------------------------
#
# The syncs download hundreds of MB and can run for minutes, which would exceed
# an HTTP request timeout. The admin endpoints start a background thread and the
# UI polls ``get_sync_status``. Status is process-local (in-memory): a server
# restart resets it to idle, which is fine since the DB upserts are idempotent.
# Only one sync runs at a time (they touch the same table).

_JOB_NAMES = ("metadata", "prices")
_JOB_FNS: dict[str, Callable[[], dict]] = {"metadata": sync_metadata, "prices": sync_prices}

_JOB_LOCK = threading.Lock()
_RUNNING: dict[str, str | None] = {"name": None}
_JOBS: dict[str, dict] = {
    name: {"status": "idle", "started_at": None, "finished_at": None, "result": None, "error": None}
    for name in _JOB_NAMES
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_sync_status() -> dict:
    """Return the current sync job status (which job is running, and per-job state)."""
    with _JOB_LOCK:
        return {"running": _RUNNING["name"], "jobs": {k: dict(v) for k, v in _JOBS.items()}}


def _run_job(name: str, fn: Callable[[], dict]) -> None:
    try:
        result = fn()
        with _JOB_LOCK:
            _JOBS[name].update(status="success", finished_at=_now_iso(), result=result, error=None)
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI via status
        logger.exception("MTGJSON sync job %r failed", name)
        with _JOB_LOCK:
            _JOBS[name].update(status="error", finished_at=_now_iso(), error=str(exc))
    finally:
        with _JOB_LOCK:
            _RUNNING["name"] = None


def start_sync_job(name: str) -> dict:
    """Start a sync job in a background thread.

    Returns ``{started, running, message}``. Refuses (``started=False``) if any
    sync is already running, so the UI can show a friendly message.
    """
    fn = _JOB_FNS.get(name)
    if fn is None:
        raise ValueError(f"Unknown sync job: {name!r}")
    with _JOB_LOCK:
        if _RUNNING["name"] is not None:
            running = _RUNNING["name"]
            return {"started": False, "running": running, "message": f"A sync ({running}) is already running."}
        _RUNNING["name"] = name
        _JOBS[name].update(status="running", started_at=_now_iso(), finished_at=None, result=None, error=None)
    thread = threading.Thread(target=_run_job, args=(name, fn), name=f"mtgjson-sync-{name}", daemon=True)
    thread.start()
    return {"started": True, "running": name, "message": f"{name} sync started."}

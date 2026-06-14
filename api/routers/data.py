import json
import logging
import re
import threading
import time

from fastapi import Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from src.mtgtop8.scraper import parse_event_display, scrape

from api.dependencies import (
    require_admin,
    require_database,
)
from api.helpers import (
    _normalize_split_cards,
    _read_upload_json_bytes_async,
    _resolve_load_path_under_data_dir,
)
from api.schemas.events import (
    LoadBody,
    ScrapeBody,
)
from api.state import (
    _invalidate_metagame,
    _load_decks_from_db,
    _load_from_file,
    _persist_decks_to_db,
    _resolve_deck_player,
    state,
)

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/v1/load", dependencies=[Depends(require_database)])
async def load_decks(
    request: Request,
    file: UploadFile | None = File(None),
    _: str = Depends(require_admin),
):
    """Load decks from JSON into the database. Body: { "decks": [...] } or { "path": "decks.json" }, or upload file. Requires PostgreSQL.

    JSON body cannot be declared alongside ``File()`` in the same handler (OpenAPI limitation); we read ``application/json`` from the request when no file part is sent.
    """
    body: LoadBody | None = None
    has_upload = file is not None and bool(getattr(file, "filename", None))

    if has_upload:
        try:
            content = await _read_upload_json_bytes_async(file)
            state.decks = _normalize_split_cards(json.loads(content.decode("utf-8")))
        except json.JSONDecodeError as e:
            logger.warning("Load decks: invalid JSON from upload: %s", e)
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    else:
        ct = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ct != "application/json":
            raise HTTPException(status_code=400, detail="Provide JSON body or file upload")
        try:
            raw = await request.json()
        except json.JSONDecodeError as e:
            logger.warning("Load decks: invalid JSON body: %s", e)
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        try:
            body = LoadBody.model_validate(raw)
        except Exception as e:
            logger.warning("Load decks: invalid load payload: %s", e)
            raise HTTPException(status_code=422, detail=str(e)) from e
        path_str = (body.path or "").strip()
        if path_str:
            path = _resolve_load_path_under_data_dir(path_str)
            if not path.exists():
                raise HTTPException(status_code=404, detail=f"File not found: {path}")
            try:
                _load_from_file(str(path))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Load decks from path %s failed: %s", path, e)
                raise HTTPException(status_code=400, detail=f"Failed to load file: {e}") from e
        elif body.decks is not None:
            state.decks = _normalize_split_cards(body.decks)
        else:
            raise HTTPException(status_code=400, detail="Provide 'decks' array, 'path', or file upload")
    _invalidate_metagame()
    if state.database_available():
        if body and (body.event_id is not None or body.new_event is not None):
            event_id = body.event_id
            event_name = date = format_id = None
            if body.new_event:
                with _db.session_scope() as session:
                    row = _db.create_event(
                        session,
                        event_name=body.new_event.event_name.strip() or "Unnamed",
                        date=body.new_event.date.strip() or "",
                        format_id=body.new_event.format_id.strip() or "EDH",
                        origin=_db.ORIGIN_MANUAL,
                        event_id=None,
                    )
                    event_id, event_name, date, format_id = row.event_id, row.name, row.date, row.format_id
            elif body.event_id is not None:
                with _db.session_scope() as session:
                    ev = _db.get_event(session, body.event_id)
                    if not ev:
                        raise HTTPException(status_code=404, detail="Event not found")
                    event_id, event_name, date, format_id = ev.event_id, ev.name, ev.date, ev.format_id
            if event_id is not None and event_name is not None:
                next_id = None
                with _db.session_scope() as session:
                    next_id = _db.next_manual_deck_id(session)
                for i, d in enumerate(state.decks):
                    d = dict(d)
                    d["event_id"] = event_id
                    d["event_name"] = event_name or d.get("event_name", "")
                    d["date"] = date or d.get("date", "")
                    d["format_id"] = format_id or d.get("format_id", "")
                    if d.get("deck_id") is None or (isinstance(d.get("deck_id"), int) and d["deck_id"] < _db.MANUAL_DECK_ID_START):
                        d["deck_id"] = next_id + i
                    state.decks[i] = d
        _persist_decks_to_db(state.decks, origin=_db.ORIGIN_MANUAL if (body and (body.event_id is not None or body.new_event)) else _db.ORIGIN_MTGTOP8)
    return {"loaded": len(state.decks), "message": f"Loaded {len(state.decks)} decks"}


@router.get("/api/v1/export")
def export_decks(_: str = Depends(require_admin)):
    """Download current scraped/loaded data as JSON (same format as load accepts)."""
    if not state.decks:
        raise HTTPException(status_code=404, detail="No data to export. Scrape or load data first.")
    body = json.dumps(state.decks, indent=2, ensure_ascii=False).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="decks.json"'},
    )


@router.post("/api/v1/analyze")
def run_analyze():
    """Re-run analysis (no-op, metagame is computed on demand)."""
    _invalidate_metagame()
    return {"message": "Analysis will be recomputed on next /api/metagame request"}


@router.post("/api/v1/scrape")
async def run_scrape(body: ScrapeBody, _: str = Depends(require_admin)):
    """Trigger scrape with SSE progress streaming."""
    import queue

    format_id = body.format_id
    period = body.period
    store = body.store
    event_ids = body.event_ids
    if isinstance(event_ids, str):
        event_ids = [x.strip() for x in event_ids.split(",") if x.strip()] or None
    # Scraper expects list[int]; ignore non-numeric IDs (e.g. manual "m1")
    scrape_event_ids: list[int] | None = None
    if event_ids:
        scrape_event_ids = [int(x) for x in event_ids if str(x).isdigit()]
        if not scrape_event_ids:
            scrape_event_ids = None

    # When not forcing, skip events already in DB (or in state.decks when no DB)
    skip_event_ids: set[int] | None = None
    if not body.force_replace and body.ignore_existing_events:
        if state.database_available():
            try:
                with _db.session_scope() as session:
                    skip_event_ids = _db.get_mtgtop8_event_ids(session)
            except Exception as e:
                logger.warning("Could not load existing event IDs for skip list: %s", e)
        elif state.decks:
            skip_event_ids = {
                int(eid)
                for eid in {d.get("event_id") for d in state.decks}
                if eid is not None and str(eid).isdigit()
            }

    state.scrape_cancel_event = threading.Event()
    start_time = time.time()
    logger.info(
        "Scrape started: format=%s period=%s store=%s event_ids=%s ignore_existing=%s force_replace=%s db_available=%s skip_count=%s",
        format_id, period, store, scrape_event_ids, body.ignore_existing_events, body.force_replace,
        state.database_available(), len(skip_event_ids) if skip_event_ids else 0,
    )

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
                event_ids=scrape_event_ids,
                on_progress=on_progress,
                skip_event_ids=None if body.force_replace or scrape_event_ids else skip_event_ids,
                should_stop=lambda: state.scrape_cancel_event.is_set() if state.scrape_cancel_event else False,
            )
            result_holder.append(decks)
        except Exception as e:
            logger.exception(
                "Scrape failed: format=%s period=%s event_ids=%s error=%s",
                format_id, period, scrape_event_ids, e,
            )
            error_holder.append(str(e))
        finally:
            q.put(None)

    thread = threading.Thread(target=run_scraper, daemon=True)
    thread.start()

    def event_stream():
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
            duration = time.time() - start_time
            logger.warning("Scrape failed after %.1fs: %s", duration, error_holder[0])
            yield f"data: {json.dumps({'type': 'error', 'message': error_holder[0]})}\n\n"
        elif result_holder:
            decks = result_holder[0]
            deck_dicts = [d.to_dict() for d in decks]
            events_in_run = {str(d.get("event_id")) for d in deck_dicts if d.get("event_id") is not None}
            if state.database_available():
                try:
                    with _db.session_scope() as session:
                        if body.force_replace:
                            # Hybrid forced replace: update event metadata, delete MTGTop8 decks per event, then upsert fresh decks
                            for eid in events_in_run:
                                sample = next((d for d in deck_dicts if str(d.get("event_id")) == eid), None)
                                if not sample:
                                    continue
                                ev_name_raw = sample.get("event_name", "")
                                ev_name, ev_store, ev_location = parse_event_display(ev_name_raw)
                                existing = _db.get_event(session, eid)
                                if existing is None:
                                    _db.create_event(
                                        session,
                                        event_name=ev_name or ev_name_raw or "Unnamed",
                                        date=sample.get("date", ""),
                                        format_id=sample.get("format_id", ""),
                                        origin=_db.ORIGIN_MTGTOP8,
                                        event_id=eid,
                                        player_count=int(sample.get("player_count", 0)),
                                        store=ev_store,
                                        location=ev_location,
                                    )
                                else:
                                    _db.update_event(
                                        session,
                                        eid,
                                        event_name=ev_name or ev_name_raw or existing.name,
                                        date=sample.get("date", existing.date),
                                        format_id=sample.get("format_id", existing.format_id),
                                        player_count=int(sample.get("player_count", 0) or existing.player_count or 0),
                                        store=ev_store or existing.store,
                                        location=ev_location or existing.location,
                                    )
                                session.query(_db.DeckRow).filter(
                                    _db.DeckRow.event_id == eid,
                                    _db.DeckRow.origin == _db.ORIGIN_MTGTOP8,
                                ).delete(synchronize_session=False)
                            for d in deck_dicts:
                                _resolve_deck_player(session, d)
                                _db.upsert_deck(session, d, origin=_db.ORIGIN_MTGTOP8)
                        else:
                            # Default: create events only if missing, upsert decks by deck_id
                            seen_event_ids = set()
                            for d in deck_dicts:
                                ev_id = d.get("event_id")
                                if ev_id is not None and ev_id not in seen_event_ids:
                                    seen_event_ids.add(ev_id)
                                    if _db.get_event(session, ev_id) is None:
                                        ev_name_raw = d.get("event_name", "")
                                        ev_name, ev_store, ev_location = parse_event_display(ev_name_raw)
                                        _db.create_event(
                                            session,
                                            event_name=ev_name or ev_name_raw or "Unnamed",
                                            date=d.get("date", ""),
                                            format_id=d.get("format_id", ""),
                                            origin=_db.ORIGIN_MTGTOP8,
                                            event_id=ev_id,
                                            player_count=int(d.get("player_count", 0)),
                                            store=ev_store,
                                            location=ev_location,
                                        )
                            for d in deck_dicts:
                                _resolve_deck_player(session, d)
                                _db.upsert_deck(session, d, origin=_db.ORIGIN_MTGTOP8)
                    _load_decks_from_db()
                    duration = time.time() - start_time
                    logger.info(
                        "Scrape completed: decks=%s events=%s duration_sec=%.1f force_replace=%s",
                        len(decks), len(events_in_run), duration, body.force_replace,
                    )
                except Exception as e:
                    logger.exception("Failed to persist scraped decks to DB: %s", e)
                    state.decks = deck_dicts
                    _invalidate_metagame()
            else:
                state.decks = deck_dicts
                _invalidate_metagame()
                duration = time.time() - start_time
                logger.info(
                    "Scrape completed: decks=%s events=%s duration_sec=%.1f (no DB)",
                    len(decks), len(events_in_run), duration,
                )
            loaded = len(state.decks)
            num_events = len(events_in_run)
            cancelled = state.scrape_cancel_event is not None and state.scrape_cancel_event.is_set()
            message = f"Scraped {len(decks)} decks from {num_events} event{'s' if num_events != 1 else ''}"
            if cancelled:
                message = f"Stopped. {message}"
            yield f"data: {json.dumps({'type': 'cancelled' if cancelled else 'done', 'message': message, 'loaded': loaded, 'pct': 100})}\n\n"
        else:
            duration = time.time() - start_time
            logger.warning("Scrape ended with unknown error after %.1fs", duration)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Unknown error'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/api/v1/scrape/stop")
def stop_scrape(_: str = Depends(require_admin)):
    """Request the current scrape to stop. Takes effect after the next progress check."""
    if state.scrape_cancel_event is not None:
        state.scrape_cancel_event.set()
    return {"message": "Stop requested"}

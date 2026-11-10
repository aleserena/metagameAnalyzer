import json
import logging

from fastapi import Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response

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
from api.services.scrape_job import (
    ScrapeAlreadyRunning,
    current_job,
    request_stop,
    snapshot,
    start_job,
)
from api.state import (
    _invalidate_metagame,
    _load_from_file,
    _persist_decks_to_db,
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
def run_scrape(body: ScrapeBody, _: str = Depends(require_admin)):
    """Start a scrape as a server-side job (poll GET /api/v1/scrape/status)."""
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

    logger.info(
        "Scrape requested: format=%s period=%s store=%s event_ids=%s ignore_existing=%s force_replace=%s db_available=%s skip_count=%s",
        format_id, period, store, scrape_event_ids, body.ignore_existing_events, body.force_replace,
        state.database_available(), len(skip_event_ids) if skip_event_ids else 0,
    )
    params = {
        "format_id": format_id,
        "period": period,
        "store": store,
        "event_ids": scrape_event_ids,
        "skip_event_ids": None if body.force_replace or scrape_event_ids else skip_event_ids,
        "force_replace": body.force_replace,
    }
    try:
        job = start_job(params)
    except ScrapeAlreadyRunning:
        raise HTTPException(status_code=409, detail="A scrape is already running")
    return JSONResponse(status_code=202, content={"job": snapshot(job)})


@router.get("/api/v1/scrape/status")
def get_scrape_status(after: int = Query(0, ge=0), _: str = Depends(require_admin)):
    """Status of the current (or most recent) scrape job; ``job`` is null when the server has none."""
    job = current_job()
    return {"job": snapshot(job, after) if job else None}


@router.post("/api/v1/scrape/stop")
def stop_scrape(_: str = Depends(require_admin)):
    """Request the current scrape to stop. Takes effect after the next progress check."""
    request_stop()
    return {"message": "Stop requested"}

"""Server-side scrape job: the scrape runs and saves its own results in a worker thread.

The browser only starts the job and polls its status, so closing the tab never loses data.
At most one job runs at a time. All mutable job state is guarded by ``_LOCK``.
"""

import logging
import re
import threading
import uuid
from datetime import datetime, timezone

from api import db as _db
from api.services.scrape_store import persist_scraped_decks
from api.state import _load_decks_from_db
from src.mtgtop8.scraper import scrape

logger = logging.getLogger(__name__)

MAX_MESSAGES = 5000

_LOCK = threading.Lock()
_JOB: "ScrapeJob | None" = None


class ScrapeAlreadyRunning(RuntimeError):
    pass


class ScrapeJob:
    def __init__(self) -> None:
        self.id = uuid.uuid4().hex
        self.status = "running"
        self.pct = 0.0
        self.messages: list[str] = []
        self.dropped = 0  # messages trimmed from the front; keeps indexes monotonic
        self.message = ""
        self.decks_saved = 0
        self.failed_decks: list[dict] = []
        self.started_at = _now()
        self.finished_at: str | None = None
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        # progress-parsing state
        self._total_events = 0
        self._current_event = 0
        self._total_decks = 0
        self._current_deck = 0


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _progress_pct(job: ScrapeJob, msg: str) -> float:
    pct = job.pct
    events_match = re.search(r"Found (\d+) events", msg)
    if events_match:
        job._total_events = int(events_match.group(1))

    event_match = re.match(r"\[(\d+)/(\d+)\]", msg)
    if event_match:
        job._current_event = int(event_match.group(1))
        job._total_events = int(event_match.group(2))

    deck_found = re.search(r"Found (\d+) decks", msg)
    if deck_found:
        job._total_decks = int(deck_found.group(1))
        job._current_deck = 0

    deck_parse = re.search(r"Parsing deck (\d+)/(\d+)", msg)
    if deck_parse:
        job._current_deck = int(deck_parse.group(1))
        job._total_decks = int(deck_parse.group(2))

    if job._total_events > 0:
        event_pct = ((job._current_event - 1) / job._total_events) * 100 if job._current_event > 0 else 0
        if job._total_decks > 0 and job._current_event > 0:
            deck_pct = (job._current_deck / job._total_decks) * (100 / job._total_events)
            pct = event_pct + deck_pct
        else:
            pct = event_pct
        pct = min(pct, 99)
    return pct


def _default_persist(deck_dicts: list[dict], force_replace: bool) -> dict:
    with _db.session_scope() as session:
        return persist_scraped_decks(session, deck_dicts, refresh_events=force_replace)


def _default_reload() -> None:
    _load_decks_from_db(strict=True)


def start_job(params: dict, *, scrape_fn=scrape, persist_fn=None, reload_fn=None) -> ScrapeJob:
    """Start a scrape in a worker thread. Raises ScrapeAlreadyRunning if one is running."""
    global _JOB
    persist_fn = persist_fn or _default_persist
    reload_fn = reload_fn or _default_reload
    with _LOCK:
        if _JOB is not None and _JOB.status == "running":
            raise ScrapeAlreadyRunning("A scrape is already running")
        job = ScrapeJob()
        _JOB = job
        job.thread = threading.Thread(
            target=_run, args=(job, params, scrape_fn, persist_fn, reload_fn), daemon=True
        )
        job.thread.start()
    return job


def _run(job: ScrapeJob, params: dict, scrape_fn, persist_fn, reload_fn) -> None:
    force_replace = bool(params.get("force_replace"))

    def on_progress(msg: str) -> None:
        with _LOCK:
            job.pct = _progress_pct(job, msg)
            job.messages.append(msg)
            if len(job.messages) > MAX_MESSAGES:
                overflow = len(job.messages) - MAX_MESSAGES
                del job.messages[:overflow]
                job.dropped += overflow

    def on_deck_error(event_id: int, deck_id: int, error: str) -> None:
        with _LOCK:
            job.failed_decks.append({"deck_id": deck_id, "event_id": event_id, "error": error})

    status = "done"
    message = ""
    try:
        decks = scrape_fn(
            format_id=params.get("format_id"),
            period=params.get("period"),
            store=params.get("store"),
            event_ids=params.get("event_ids"),
            skip_event_ids=params.get("skip_event_ids"),
            on_progress=on_progress,
            on_deck_error=on_deck_error,
            should_stop=job.stop_event.is_set,
        )
        deck_dicts = [d.to_dict() for d in decks]
        events_in_run = {d.get("event_id") for d in deck_dicts if d.get("event_id") is not None}
        result = persist_fn(deck_dicts, force_replace)
        persist_failed = list(result.get("failed") or [])
        for f in persist_failed:
            logger.warning(
                "Scrape: failed to save deck %s (event %s): %s",
                f.get("deck_id"), f.get("event_id"), f.get("error"),
            )
        # Record what was saved before reloading, so a reload failure cannot hide it.
        with _LOCK:
            job.failed_decks.extend(persist_failed)
            job.decks_saved = int(result.get("decks_saved", 0))
        try:
            reload_fn()
        except Exception as exc:
            raise RuntimeError(
                f"Decks were saved but reloading them failed: {exc}"
            ) from exc
        with _LOCK:
            failed_events = sorted({str(f["event_id"]) for f in job.failed_decks if f.get("event_id") is not None})
            n_failed = len(job.failed_decks)
        n = len(deck_dicts)
        m = len(events_in_run)
        message = f"Scraped {n} decks from {m} events"
        if n_failed:
            message += f"; {n_failed} decks failed — re-run with Event IDs: {', '.join(failed_events)}"
        if job.stop_event.is_set():
            status = "cancelled"
            message = f"Stopped. {message}"
    except Exception as exc:
        logger.exception("Scrape job failed: %s", exc)
        status = "error"
        message = str(exc) or exc.__class__.__name__
    finally:
        with _LOCK:
            job.status = status
            job.message = message
            if status in ("done", "cancelled"):
                job.pct = 100
            job.finished_at = _now()


def current_job() -> ScrapeJob | None:
    with _LOCK:
        return _JOB


def request_stop() -> bool:
    """Ask the running job to stop. Returns whether a job was running."""
    with _LOCK:
        if _JOB is not None and _JOB.status == "running":
            _JOB.stop_event.set()
            return True
    return False


def snapshot(job: ScrapeJob, after: int = 0) -> dict:
    with _LOCK:
        start = max(after - job.dropped, 0)
        return {
            "id": job.id,
            "status": job.status,
            "pct": round(job.pct, 1),
            "messages": job.messages[start:],
            "next": job.dropped + len(job.messages),
            "message": job.message,
            "decks_saved": job.decks_saved,
            "failed_decks": list(job.failed_decks),
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }


def _reset_for_tests() -> None:
    global _JOB
    with _LOCK:
        _JOB = None

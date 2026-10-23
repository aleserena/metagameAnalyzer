"""Structured logging for production (e.g. Railway). JSON lines to stdout for easy parsing.

Every record carries ``request_id`` (inside an HTTP request), ``env`` and ``build`` so a
log line can be traced to a request and a deployment. Secrets (DB URL passwords, bearer
tokens, ``password=…``) are redacted from messages and tracebacks before output.
Uncaught exceptions — main thread or background threads — are logged instead of only
printed to stderr. ERROR records can additionally be emailed via :class:`ErrorEmailHandler`.
"""

import contextvars
import hashlib
import json
import logging
import os
import queue
import re
import sys
import threading
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

# Keys we don't put into the JSON "extra" payload (standard LogRecord attrs)
_STANDARD_ATTRS = frozenset({
    "name", "msg", "args", "created", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs",
    "pathname", "process", "processName", "relativeCreated",
    "stack_info", "exc_info", "exc_text", "thread", "threadName",
    "message", "taskName",
    "color_message",  # uvicorn's ANSI-coloured duplicate of the message
})

# Set by the request middleware; read by the record factory so every log line in a request has it.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_SECRET_PATTERNS = (
    # scheme://user:password@host -> scheme://user:***@host
    (re.compile(r"(://[^:/@\s]*:)[^@\s]*@"), r"\1***@"),
    # Authorization: Bearer <token>
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1***"),
    # password=..., api_key: ..., token="..."
    (re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)(['\"]?\s*[=:]\s*['\"]?)[^\s'\",&]+"), r"\1\2***"),
)


def redact_secrets(text: Any) -> str:
    """Mask credentials in free text (log messages, tracebacks, alert bodies)."""
    s = str(text)
    for pattern, repl in _SECRET_PATTERNS:
        s = pattern.sub(repl, s)
    return s


def environment_name() -> str:
    return (os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("DB_ENV") or "local").strip() or "local"


def build_id() -> str:
    sha = os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT_SHA", "")
    return sha[:7] if sha else "dev"


_base_record_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs) -> logging.LogRecord:
    record = _base_record_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    record.env = environment_name()
    record.build = build_id()
    return record


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _safe_message(record: logging.LogRecord) -> str:
    try:
        return record.getMessage()
    except Exception:  # bad %-args must not lose the record
        return f"{record.msg!r} (args={record.args!r})"


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON for log aggregators (Railway, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            log = {
                "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": redact_secrets(_safe_message(record)),
                "source": f"{record.module}:{record.lineno}",
            }
            if record.exc_info:
                log["exception"] = redact_secrets(self.formatException(record.exc_info))
            if record.stack_info:
                log["stack"] = redact_secrets(record.stack_info)
            for key, value in record.__dict__.items():
                if key not in _STANDARD_ATTRS and value is not None:
                    try:
                        json.dumps(value, default=_json_default)
                        log[key] = value
                    except (TypeError, ValueError):
                        log[key] = str(value)
            return json.dumps(log, default=_json_default, ensure_ascii=False)
        except Exception as e:  # never let formatting kill a log line
            return json.dumps({
                "level": record.levelname,
                "logger": record.name,
                "message": redact_secrets(_safe_message(record)),
                "formatter_error": str(e),
            })


class TextFormatter(logging.Formatter):
    """Human-readable local format; also redacts and shows the request id when present."""

    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "request_id", None)
        record.rid = f" [{rid}]" if rid else ""
        return redact_secrets(super().format(record))


def _log_uncaught(exc_type, exc_value, exc_tb, where: str) -> None:
    logging.getLogger("uncaught").critical(
        "Uncaught exception in %s: %s", where, exc_value,
        exc_info=(exc_type, exc_value, exc_tb), extra={"event": "uncaught_exception"},
    )


def _install_excepthooks() -> None:
    def sys_hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        _log_uncaught(exc_type, exc_value, exc_tb, "main thread")

    def thread_hook(args: threading.ExceptHookArgs):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread else "unknown"
        _log_uncaught(args.exc_type, args.exc_value, args.exc_traceback, f"thread {name!r}")

    sys.excepthook = sys_hook
    threading.excepthook = thread_hook


def configure_logging() -> None:
    """Configure root logger: level from LOG_LEVEL, JSON when LOG_FORMAT=json or on Railway."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)
    log_format_env = os.getenv("LOG_FORMAT", "").strip().lower()
    use_json = (
        log_format_env == "json"
        or os.getenv("RAILWAY_ENVIRONMENT") is not None
        or os.getenv("RAILWAY_SERVICE_NAME") is not None
    )

    logging.setLogRecordFactory(_record_factory)
    root = logging.getLogger()
    root.setLevel(level)
    for h in root.handlers[:]:
        if not isinstance(h, ErrorEmailHandler):  # keep the email handler across re-configuration
            root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    if use_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            TextFormatter(
                "%(asctime)s | %(levelname)-8s | %(name)s%(rid)s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    root.addHandler(handler)

    # Route uvicorn's own startup/error lines through our handler (JSON on Railway) instead of
    # its plain-text handlers, so every line in the deploy logs is parseable.
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    # Reduce noise from third-party libs (we log requests ourselves)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _install_excepthooks()


class ErrorEmailHandler(logging.Handler):
    """Email ERROR+ records to the operator — batched, deduplicated and rate-limited.

    ``emit`` only enqueues (never blocks a request or raises); a daemon thread collects
    records for ``batch_seconds`` and sends one digest via ``send(subject, body)``.
    The same error (logger + message template + exception type) is emailed at most once
    per ``cooldown_seconds``; repeats are counted and reported in the next email. At most
    ``max_per_hour`` emails are sent. Records with ``extra={"email": False}`` and records
    from the email path itself (``skip_loggers``) are ignored, so a failing mail server
    cannot cause an email loop.
    """

    def __init__(
        self,
        send: Callable[[str, str], None],
        *,
        batch_seconds: float = 30.0,
        cooldown_seconds: float = 900.0,
        max_per_hour: int = 20,
        skip_loggers: tuple[str, ...] = (),
        level: int = logging.ERROR,
    ) -> None:
        super().__init__(level)
        self._send = send
        self._batch_seconds = batch_seconds
        self._cooldown = cooldown_seconds
        self._max_per_hour = max_per_hour
        self._skip = skip_loggers
        self._queue: queue.Queue = queue.Queue(maxsize=500)
        self._last_sent: dict[str, float] = {}
        self._suppressed: dict[str, int] = {}
        self._sent_times: list[float] = []
        self._dropped = 0
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, name="error-email", daemon=True)
        self._worker.start()

    @staticmethod
    def fingerprint(record: logging.LogRecord) -> str:
        exc = record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else ""
        raw = f"{record.name}|{record.msg}|{exc}"
        return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:12]

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if getattr(record, "email", True) is False or record.name.startswith(self._skip):
                return
            # Render now: exc_info/args may not survive until the worker runs.
            entry = {
                "fingerprint": self.fingerprint(record),
                "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="seconds"),
                "level": record.levelname,
                "logger": record.name,
                "source": f"{record.module}:{record.lineno}",
                "message": redact_secrets(_safe_message(record)),
                "request_id": getattr(record, "request_id", None),
                "path": getattr(record, "path", None),
                "event": getattr(record, "event", None),
                "traceback": (
                    redact_secrets("".join(traceback.format_exception(*record.exc_info)))[-8000:]
                    if record.exc_info else None
                ),
            }
            self._queue.put_nowait(entry)
        except queue.Full:
            with self._lock:
                self._dropped += 1
        except Exception:
            self.handleError(record)

    def _admit(self, entry: dict, now: float) -> bool:
        """Apply the per-error cooldown; returns False (and counts it) for a recent repeat."""
        fp = entry["fingerprint"]
        last = self._last_sent.get(fp)
        if last is not None and now - last < self._cooldown:
            self._suppressed[fp] = self._suppressed.get(fp, 0) + 1
            return False
        entry["suppressed_before"] = self._suppressed.pop(fp, 0)
        self._last_sent[fp] = now
        return True

    def _run(self) -> None:
        while True:
            first = self._queue.get()
            if first is None:
                return
            batch = [first]
            deadline = time.monotonic() + self._batch_seconds
            stop = False
            while (remaining := deadline - time.monotonic()) > 0:
                try:
                    item = self._queue.get(timeout=remaining)
                except queue.Empty:
                    break
                if item is None:
                    stop = True
                    break
                batch.append(item)
            self._send_batch(batch)
            if stop:
                return

    def _send_batch(self, batch: list[dict]) -> None:
        now = time.monotonic()
        with self._lock:
            entries = [e for e in batch if self._admit(e, now)]
            dropped, self._dropped = self._dropped, 0
            self._sent_times = [t for t in self._sent_times if now - t < 3600]
            if not entries:
                return
            if len(self._sent_times) >= self._max_per_hour:
                return  # hourly cap reached; errors remain in the logs
            self._sent_times.append(now)
        try:
            subject, body = self.render(entries, dropped)
            self._send(subject, body)
        except Exception as e:  # logged below ERROR with email=False: no loop
            logging.getLogger("api.alerts.email").warning(
                "Failed to send error email: %s", e, extra={"email": False, "event": "alert_failed"}
            )

    @staticmethod
    def render(entries: list[dict], dropped: int = 0) -> tuple[str, str]:
        env, build = environment_name(), build_id()
        first = entries[0]
        more = f" (+{len(entries) - 1} more)" if len(entries) > 1 else ""
        subject = f"[{env}] {first['level']}: {first['message'][:120]}{more}"
        parts = [f"Environment: {env}\nBuild: {build}\nErrors in this email: {len(entries)}\n"]
        if dropped:
            parts.append(f"WARNING: {dropped} error(s) were dropped because the email queue was full.\n")
        for i, e in enumerate(entries, 1):
            lines = [
                f"--- #{i} {e['level']} at {e['time']} ---",
                f"Message: {e['message']}",
                f"Logger: {e['logger']} ({e['source']})",
            ]
            if e.get("request_id") or e.get("path"):
                lines.append(f"Request: {e.get('path') or '-'} (request_id={e.get('request_id') or '-'})")
            if e.get("event"):
                lines.append(f"Event: {e['event']}")
            if e.get("suppressed_before"):
                lines.append(f"Repeated {e['suppressed_before']} more time(s) since the last email for this error.")
            if e.get("traceback"):
                lines.append("\n" + e["traceback"])
            parts.append("\n".join(lines) + "\n")
        parts.append("Search the deploy logs by request_id or message for full context.")
        return subject, "\n".join(parts)

    def flush_and_stop(self, timeout: float = 10.0) -> None:
        """Send whatever is queued now (used on shutdown) and stop the worker."""
        self._batch_seconds = 0
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._worker.join(timeout)

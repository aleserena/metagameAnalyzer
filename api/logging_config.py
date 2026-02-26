"""Structured logging for production (e.g. Railway). JSON lines to stdout for easy parsing."""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

# Keys we don't put into the JSON "extra" payload (standard LogRecord attrs)
_STANDARD_ATTRS = frozenset({
    "name", "msg", "args", "created", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs",
    "pathname", "process", "processName", "relativeCreated",
    "stack_info", "exc_info", "exc_text", "thread", "threadName",
    "message", "taskName",
})


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON for log aggregators (Railway, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and value is not None:
                try:
                    json.dumps(value, default=_json_default)
                    log[key] = value
                except TypeError:
                    log[key] = str(value)
        return json.dumps(log, default=_json_default, ensure_ascii=False)


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

    root = logging.getLogger()
    root.setLevel(level)
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    if use_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    root.addHandler(handler)

    # Reduce noise from third-party libs (we log requests ourselves)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

"""Shared helpers for reading and writing JSON config/data files.

These helpers centralize JSON I/O semantics so that the API and core
mtgtop8 modules handle errors and encoding consistently.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


def load_json(path: str | Path, default: T | None = None, *, suppress_errors: bool = True) -> T | None:
    """Load JSON from ``path`` and return the parsed object.

    - If the file does not exist, return ``default``.
    - If parsing or I/O fails:
      - When ``suppress_errors`` is True (default), return ``default``.
      - When ``suppress_errors`` is False, re-raise the exception.
    """
    p = Path(path)
    if not p.exists():
        return default
    try:
        with p.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        if suppress_errors:
            return default
        raise


def save_json(
    path: str | Path,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    suppress_errors: bool = False,
) -> None:
    """Write ``data`` as JSON to ``path``.

    - Parent directories are created automatically.
    - When ``suppress_errors`` is True, any I/O or serialization error is
      swallowed to match legacy behavior of some callers.
    """
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
    except Exception:
        if not suppress_errors:
            raise


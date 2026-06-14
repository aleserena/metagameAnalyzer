#!/usr/bin/env python3
"""Generate (or check) docs/API_ROUTES.md from the FastAPI route definitions.

Parses the route source with `ast` (no import, so no DB connection or app
startup side effects), extracts each endpoint's method, path, handler function
name, and auth dependencies, and renders a grouped markdown table.

Usage:
    python3 scripts/gen_api_routes.py          # rewrite docs/API_ROUTES.md
    python3 scripts/gen_api_routes.py --check   # exit 1 if the file is stale
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_OUTPUT = _ROOT / "docs" / "API_ROUTES.md"

# Source files that define routes (via @app.* or @router.*).
_SOURCES = [
    _ROOT / "api" / "main.py",
    *sorted((_ROOT / "api" / "routers").glob("*.py")),
]

_HTTP_METHODS = {"get", "post", "put", "delete", "patch"}

# Dependency callable name -> short auth label shown in the table.
_AUTH_LABELS = {
    "require_admin": "admin",
    "require_database": "DB",
    "require_admin_or_event_edit": "event-edit",
    "require_admin_or_event_edit_deck": "event-edit",
}

# Resource grouping: first path segment after /api/v1/ -> section heading.
# Order here is the order sections appear in the output.
_SECTIONS: list[tuple[str, str]] = [
    ("health", "Health / Info / Auth / Feedback"),
    ("info", "Health / Info / Auth / Feedback"),
    ("auth", "Health / Info / Auth / Feedback"),
    ("feedback", "Health / Info / Auth / Feedback"),
    ("cards", "Cards"),
    ("decks", "Decks"),
    ("events", "Events"),
    ("upload", "Upload / event-edit links"),
    ("event-edit", "Upload / event-edit links"),
    ("metagame", "Metagame / Archetypes / Commanders"),
    ("archetypes", "Metagame / Archetypes / Commanders"),
    ("commanders", "Metagame / Archetypes / Commanders"),
    ("date-range", "Metagame / Archetypes / Commanders"),
    ("format-info", "Metagame / Archetypes / Commanders"),
    ("matchups", "Matchups"),
    ("players", "Players"),
    ("player-aliases", "Players"),
    ("player-emails", "Players"),
    ("settings", "Settings (admin)"),
    ("load", "Data operations"),
    ("export", "Data operations"),
    ("analyze", "Data operations"),
    ("scrape", "Data operations"),
]
_OTHER_SECTION = "Other"


def _depends_names(node: ast.AST) -> list[str]:
    """Return the callable names inside Depends(...) calls found anywhere in node."""
    names: list[str] = []
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "Depends"
            and child.args
            and isinstance(child.args[0], ast.Name)
        ):
            names.append(child.args[0].id)
    return names


def _auth_label(dep_names: list[str]) -> str:
    seen: list[str] = []
    for name in dep_names:
        label = _AUTH_LABELS.get(name)
        if label and label not in seen:
            seen.append(label)
    # Show event-edit/admin before DB for readability.
    order = {"admin": 0, "event-edit": 0, "DB": 1}
    seen.sort(key=lambda lbl: order.get(lbl, 2))
    return ", ".join(seen)


def _collect_routes() -> list[dict[str, str]]:
    routes: list[dict[str, str]] = []
    for src in _SOURCES:
        if not src.exists():
            continue
        tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in _HTTP_METHODS
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)
                ):
                    continue
                method = dec.func.attr.upper()
                path = dec.args[0].value
                # Auth from decorator dependencies + handler signature Depends().
                dep_names = _depends_names(dec) + _depends_names(node.args)
                routes.append(
                    {
                        "method": method,
                        "path": path,
                        "handler": node.name,
                        "auth": _auth_label(dep_names),
                        "source": src.name,
                    }
                )
    return routes


def _section_for(path: str) -> str:
    # Strip leading /api/v1/ if present, take first segment.
    trimmed = path
    for prefix in ("/api/v1/", "/api/"):
        if trimmed.startswith(prefix):
            trimmed = trimmed[len(prefix):]
            break
    else:
        trimmed = trimmed.lstrip("/")
    segment = trimmed.split("/", 1)[0].split("{", 1)[0].strip("/")
    for key, heading in _SECTIONS:
        if segment == key:
            return heading
    return _OTHER_SECTION


def _sort_key(route: dict[str, str]) -> tuple:
    # Stable sort: by path then method, so output is deterministic.
    method_order = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}
    return (route["path"], method_order.get(route["method"], 9))


def render() -> str:
    routes = _collect_routes()

    # Group into sections, preserving the section order in _SECTIONS.
    section_order: list[str] = []
    for _, heading in _SECTIONS:
        if heading not in section_order:
            section_order.append(heading)
    section_order.append(_OTHER_SECTION)

    grouped: dict[str, list[dict[str, str]]] = {h: [] for h in section_order}
    for route in routes:
        grouped[_section_for(route["path"])].append(route)

    lines: list[str] = []
    lines.append("# API Route Index")
    lines.append("")
    lines.append(
        "**Auto-generated by `scripts/gen_api_routes.py` — do not edit by hand.** "
        "Regenerate with `python3 scripts/gen_api_routes.py` (or `npm run gen:routes`)."
    )
    lines.append("")
    lines.append(
        "Route -> handler-function map for the FastAPI app. **Grep for the handler "
        "name** to jump to an endpoint instead of scanning the source."
    )
    lines.append("")
    lines.append(
        "Auth column: `admin` = admin token required, `event-edit` = admin **or** a "
        "valid event-edit token, `DB` = database required. Blank = public."
    )
    lines.append("")
    lines.append(f"Total endpoints: **{len(routes)}**.")
    lines.append("")

    for heading in section_order:
        section_routes = grouped[heading]
        if not section_routes:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        lines.append("| Method | Path | Handler | Auth |")
        lines.append("|---|---|---|---|")
        for route in sorted(section_routes, key=_sort_key):
            handler_cell = f"`{route['handler']}`"
            if route["source"] != "main.py":
                handler_cell += f" (in `api/routers/{route['source']}`)"
            lines.append(
                f"| {route['method']} | `{route['path']}` | {handler_cell} | {route['auth']} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if docs/API_ROUTES.md is out of date instead of rewriting it.",
    )
    args = parser.parse_args()

    content = render()

    if args.check:
        current = _OUTPUT.read_text(encoding="utf-8") if _OUTPUT.exists() else ""
        if current != content:
            print(
                "docs/API_ROUTES.md is out of date. Run: python3 scripts/gen_api_routes.py",
                file=sys.stderr,
            )
            return 1
        print("docs/API_ROUTES.md is up to date.")
        return 0

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(content, encoding="utf-8")
    print(f"Wrote {_OUTPUT.relative_to(_ROOT)} ({content.count(chr(10))} lines).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

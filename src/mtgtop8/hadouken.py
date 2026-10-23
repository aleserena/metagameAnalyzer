"""Parser for tournament pages of the Hadouken league site (hadoleague.vercel.app).

Hadouken publishes full standings and every round's pairings (with game scores) but no decklists,
so it is used to complete events that were first scraped from MTGTop8 (which has the top decks only).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag

from .config import FORMATS

HADOUKEN_HOST = "hadoleague.vercel.app"

_SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Pairing side text: "NAME (2)" on the left, "(2) NAME" on the right.
_LEFT_RE = re.compile(r"^(?P<name>.+?)\s*\(\s*(?P<games>\d+)\s*\)$")
_RIGHT_RE = re.compile(r"^\(\s*(?P<games>\d+)\s*\)\s*(?P<name>.+)$")


@dataclass
class HadoukenStanding:
    rank: int
    player: str
    points: int
    wins: int
    losses: int
    draws: int


@dataclass
class HadoukenPairing:
    round: int
    player1: str
    player2: str
    games1: int
    games2: int


@dataclass
class HadoukenEvent:
    url: str
    name: str
    date: str  # DD/MM/YY, like MTGTop8 events
    format_id: str
    store: str
    player_count: int
    standings: list[HadoukenStanding] = field(default_factory=list)
    pairings: list[HadoukenPairing] = field(default_factory=list)


def is_hadouken_url(url: str) -> bool:
    """True for https://hadoleague.vercel.app/torneos/<slug> URLs (the only URLs we fetch)."""
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == HADOUKEN_HOST
        and parsed.path.startswith("/torneos/")
        and len(parsed.path) > len("/torneos/")
    )


def parse_spanish_date(text: str) -> str:
    """'viernes, 9 de octubre de 2026, 10:00 p. m.' -> '09/10/26'. Returns '' if not parseable."""
    s = unicodedata.normalize("NFD", (text or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    m = re.search(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", s)
    if not m or m.group(2) not in _SPANISH_MONTHS:
        return ""
    return f"{int(m.group(1)):02d}/{_SPANISH_MONTHS[m.group(2)]:02d}/{m.group(3)[2:]}"


def pairing_results(p: HadoukenPairing) -> tuple[str, str]:
    """Match results (player1, player2) from game wins. 0-0 is treated as an intentional draw."""
    if p.games1 > p.games2:
        return "win", "loss"
    if p.games1 < p.games2:
        return "loss", "win"
    if p.games1 == 0:
        return "intentional_draw", "intentional_draw"
    return "draw", "draw"


def _clean_name(name: str) -> str:
    """Hadouken shows names in upper case; store them title-cased ('MASINO JULIAN' -> 'Masino Julian')."""
    return " ".join((name or "").split()).title()


def _text(el: Tag | None) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _int(text: str) -> int:
    m = re.search(r"-?\d+", text or "")
    return int(m.group()) if m else 0


def _format_id(label: str) -> str:
    """'Magic: The Gathering Duel Commander' -> 'EDH' (longest matching FORMATS name wins)."""
    low = (label or "").lower()
    matches = [(len(name), fid) for fid, name in FORMATS.items() if name.lower() in low]
    return max(matches)[1] if matches else ""


def _info_value(main: Tag, label: str) -> str:
    """Value shown under a small caps label like 'Ubicacion' / 'Participantes'."""
    for p in main.find_all("p"):
        if _text(p).lower() == label.lower():
            return _text(p.find_next("p"))
    return ""


def _parse_standings(main: Tag) -> list[HadoukenStanding]:
    table = main.find("table")
    if not table:
        return []
    out = []
    for tr in table.find_all("tr"):
        cells = [_text(td) for td in tr.find_all("td")]
        # #, Jugador, Mazo, Pts torneo, Pts liga, V, D, E
        if len(cells) < 8:
            continue
        out.append(
            HadoukenStanding(
                rank=_int(cells[0]),
                player=_clean_name(cells[1]),
                points=_int(cells[3]),
                wins=_int(cells[5]),
                losses=_int(cells[6]),
                draws=_int(cells[7]),
            )
        )
    return out


def _parse_pairings(main: Tag) -> list[HadoukenPairing]:
    out = []
    for h3 in main.find_all("h3"):
        title = _text(h3)
        if not title.lower().startswith("ronda"):
            continue
        round_no = _int(title)
        ul = h3.find_next_sibling("ul")
        if not ul:
            continue
        for li in ul.find_all("li"):
            spans = [s for s in li.find_all("span", recursive=False) if _text(s).lower() != "vs"]
            if len(spans) != 2:
                continue  # bye or unexpected layout
            left = _LEFT_RE.match(_text(spans[0]))
            right = _RIGHT_RE.match(_text(spans[1]))
            if not left or not right:
                continue
            p1, p2 = _clean_name(left.group("name")), _clean_name(right.group("name"))
            if "bye" in (p1.lower(), p2.lower()):
                continue
            out.append(HadoukenPairing(round_no, p1, p2, int(left.group("games")), int(right.group("games"))))
    return out


def parse_hadouken_event(html: str, url: str = "") -> HadoukenEvent:
    """Parse a Hadouken tournament page. Raises ValueError if it does not look like one."""
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main")
    h1 = main.find("h1") if main else None
    if not main or not h1:
        raise ValueError("Not a Hadouken tournament page (no event title found)")

    label = h1.find_previous_sibling("p")
    date_p = h1.find_next_sibling("p")
    location = _info_value(main, "Ubicacion")
    store = location.split("/", 1)[1].strip() if "/" in location else location

    standings = _parse_standings(main)
    return HadoukenEvent(
        url=url,
        name=_text(h1),
        date=parse_spanish_date(_text(date_p)),
        format_id=_format_id(_text(label)),
        store=store,
        player_count=_int(_info_value(main, "Participantes")) or len(standings),
        standings=standings,
        pairings=_parse_pairings(main),
    )


def fetch_hadouken_event(url: str, session: requests.Session | None = None) -> HadoukenEvent:
    """Download and parse a Hadouken tournament page. Only hadoleague.vercel.app/torneos/ URLs are allowed."""
    if not is_hadouken_url(url):
        raise ValueError(f"Not a Hadouken tournament URL: {url!r}")
    http = session or requests.Session()
    r = http.get(url.strip(), timeout=30, headers={"User-Agent": "MTGTop8Scraper/1.0"})
    r.raise_for_status()
    r.encoding = "utf-8"
    return parse_hadouken_event(r.text, url=url.strip())

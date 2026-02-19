"""MTGTop8 scraper: fetch events and deck lists."""

import re
import time
from typing import Callable

import requests
from bs4 import BeautifulSoup

from .config import BASE_URL, DEFAULT_META, REQUEST_DELAY_SECONDS, get_meta_value
from .models import Deck, Event


def _fetch(url: str, session: requests.Session) -> str:
    """Fetch URL with retries and exponential backoff."""
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            r.encoding = "windows-1252"
            return r.text
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    return ""


def _parse_card_line(line: str) -> tuple[int, str] | None:
    """Parse 'N Card Name' into (qty, card_name)."""
    m = re.match(r"^(\d+)\s+(.+)$", line.strip())
    if m:
        card_name = m.group(2).strip()
        # MTGTop8 uses single '/' for split cards; Scryfall expects '//'
        card_name = re.sub(r"\s+/\s+", " // ", card_name)
        return int(m.group(1)), card_name
    return None


def _is_section_header(card_name: str) -> bool:
    """True if parsed 'card' is actually a section header like 'LANDS (39)'."""
    upper = card_name.upper()
    return (
        "LANDS" in upper
        or "CREATURES" in upper
        or ("INSTANTS" in upper and "SORC" in upper)
        or "OTHER SPELLS" in upper
    ) and ("(" in card_name or len(card_name) < 25)


def scrape_events_from_format(
    format_id: str,
    meta: int,
    store_filter: str | None,
    session: requests.Session,
) -> list[Event]:
    """Scrape format page(s) and return matching events."""
    events: list[Event] = []
    page = 1
    seen_ids: set[int] = set()

    while True:
        url = f"{BASE_URL}/format?f={format_id}&meta={meta}"
        if page > 1:
            url += f"&cp={page}"
        html = _fetch(url, session)
        time.sleep(REQUEST_DELAY_SECONDS)

        soup = BeautifulSoup(html, "lxml")
        tables = soup.find_all("table")

        page_has_events = False
        for table in tables:
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                link = row.find("a", href=re.compile(r"event\?e=\d+"))
                if not link:
                    continue
                href = link.get("href", "")
                m = re.search(r"e=(\d+)", href)
                if not m:
                    continue
                event_id = int(m.group(1))
                if event_id in seen_ids:
                    continue
                seen_ids.add(event_id)

                link_cell = link.find_parent("td")
                event_name = link_cell.get_text(separator=" ", strip=True) if link_cell else link.get_text(strip=True)
                event_name = re.sub(r"\s*NEW\s*$", "", event_name)

                date_text = ""
                for cell in reversed(cells):
                    candidate = cell.get_text(strip=True)
                    if re.match(r"\d{2}/\d{2}/\d{2}$", candidate):
                        date_text = candidate
                        break
                if not date_text:
                    continue

                page_has_events = True

                if store_filter and store_filter.lower() not in event_name.lower():
                    continue

                events.append(
                    Event(
                        event_id=event_id,
                        format_id=format_id,
                        name=event_name,
                        date=date_text,
                    )
                )

        next_link = soup.find("a", href=re.compile(r"cp=" + str(page + 1)))
        if not page_has_events or not next_link:
            break
        page += 1

    return events


def scrape_deck_ids_from_event(
    event_id: int,
    format_id: str,
    session: requests.Session,
) -> list[int]:
    """Scrape event page and return deck IDs."""
    url = f"{BASE_URL}/event?e={event_id}&f={format_id}"
    html = _fetch(url, session)
    time.sleep(REQUEST_DELAY_SECONDS)

    soup = BeautifulSoup(html, "lxml")
    deck_ids: list[int] = []
    for link in soup.find_all("a", href=re.compile(r"e=" + str(event_id) + r"&d=\d+")):
        href = link.get("href", "")
        m = re.search(r"d=(\d+)", href)
        if m:
            did = int(m.group(1))
            if did not in deck_ids:
                deck_ids.append(did)
    return deck_ids


_SECTION_RE = re.compile(
    r"^(\d+\s+)?"
    r"(COMMANDER|COMPANION|LANDS|CREATURES|INSTANTS\s+and\s+SORC\.|OTHER\s+SPELLS|SIDEBOARD)"
    r"(\s*\(\d+\))?$",
    re.IGNORECASE,
)


def _detect_section(text: str) -> str | None:
    """Return section name if text is a section header, else None."""
    m = _SECTION_RE.match(text.strip())
    if m:
        return m.group(2).upper().strip()
    return None


def scrape_deck_robust(
    event_id: int,
    deck_id: int,
    format_id: str,
    session: requests.Session,
) -> Deck | None:
    """Scrape deck page using the actual DOM structure."""
    url = f"{BASE_URL}/event?e={event_id}&d={deck_id}&f={format_id}"
    html = _fetch(url, session)
    time.sleep(REQUEST_DELAY_SECONDS)

    soup = BeautifulSoup(html, "lxml")

    event_name = ""
    player_count = 0
    date = ""
    deck_name = ""
    player = ""
    rank = ""
    archetype: str | None = None

    player_link = soup.find("a", class_="player_big")
    if player_link:
        player = player_link.get_text(strip=True)

    title = soup.find("title")
    if title:
        title_text = title.get_text()
        m = re.match(r"^(.+)\s+-\s+(.+?)\s*@\s*mtgtop8\.com", title_text)
        if m:
            deck_name = m.group(1).strip()
            if not player:
                player = m.group(2).strip()
        elif " - " in title_text:
            parts = title_text.rsplit(" - ", 1)
            deck_name = parts[0].strip()
            if not player:
                player = parts[1].replace("@ mtgtop8.com", "").strip()

    meta_text = soup.get_text()
    pc_match = re.search(r"(\d+)\s*players\s*-\s*(\d{2}/\d{2}/\d{2})", meta_text)
    if pc_match:
        player_count = int(pc_match.group(1))
        date = pc_match.group(2)

    chosen = soup.find("div", class_="chosen_tr")
    if chosen:
        for div in chosen.find_all("div", class_="S14"):
            text = div.get_text(strip=True)
            if text in ("1", "2", "3-4", "5-8", "9-16", "17-32"):
                rank = text
                break

    archetype_link = soup.find("a", href=re.compile(r"archetype\?a="))
    if archetype_link:
        archetype_text = archetype_link.get_text(strip=True)
        archetype_text = re.sub(r"\s+decks$", "", archetype_text)
        archetype = archetype_text or None

    event_title_div = soup.find("div", class_="event_title")
    if event_title_div:
        event_name = event_title_div.get_text(strip=True)

    mainboard: list[tuple[int, str]] = []
    sideboard: list[tuple[int, str]] = []
    commanders: list[str] = []

    # The deck is rendered as a sequence of <div> elements:
    #   <div class="O14">SECTION_NAME</div>  (section header)
    #   <div class="deck_line hover_tr" id="md...">1 <span>Card</span></div>
    # Card div IDs: md* = mainboard, sb* = sideboard
    # We iterate all divs in DOM order so sections and cards stay interleaved.
    section = ""
    for div in soup.find_all("div"):
        classes = div.get("class", [])
        if not classes:
            continue
        cls_str = " ".join(classes)

        if "O14" in classes:
            text = div.get_text(strip=True)
            text = re.sub(r"^\s*\ue001\s*", "", text)
            detected = _detect_section(text)
            if detected:
                section = detected
            continue

        if "deck_line" in cls_str:
            text = div.get_text(separator=" ", strip=True)
            parsed = _parse_card_line(text)
            if not parsed:
                continue
            qty, card = parsed
            div_id = div.get("id", "")
            if section == "COMMANDER":
                commanders.append(card)
            elif section in ("COMPANION", "SIDEBOARD") or div_id.startswith("sb"):
                sideboard.append((qty, card))
            else:
                mainboard.append((qty, card))

    return Deck(
        deck_id=deck_id,
        event_id=event_id,
        format_id=format_id,
        name=deck_name or "Unknown",
        player=player or "Unknown",
        event_name=event_name or "Unknown",
        date=date or "",
        rank=rank or "",
        player_count=player_count or 0,
        mainboard=mainboard,
        sideboard=sideboard,
        commanders=commanders,
        archetype=archetype,
    )


def scrape(
    format_id: str,
    period: str | None = None,
    meta: int | None = None,
    store: str | None = None,
    event_ids: list[int] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> list[Deck]:
    """
    Scrape decks from MTGTop8.

    Args:
        format_id: Format (EDH, ST, PI, etc.)
        period: Time period label (e.g. "Last 2 Weeks")
        meta: Override meta value if period not used
        store: Substring to filter events by name
        event_ids: If set, scrape only these event IDs (skip format page)
        on_progress: Optional callback for progress messages
    """
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "MTGTop8Scraper/1.0"})

    meta_val = meta
    if meta_val is None and period:
        meta_val = get_meta_value(format_id, period)
    if meta_val is None:
        meta_val = DEFAULT_META.get("Last 2 Weeks", 115)

    events: list[Event] = []
    if event_ids:
        events = [Event(event_id=eid, format_id=format_id, name="", date="") for eid in event_ids]
    else:
        if on_progress:
            on_progress("Fetching events from format page...")
        events = scrape_events_from_format(format_id, meta_val, store, session)
        if on_progress:
            on_progress(f"Found {len(events)} events")

    decks: list[Deck] = []
    for i, ev in enumerate(events, 1):
        label = ev.name or f"event {ev.event_id}"
        if on_progress:
            on_progress(f"[{i}/{len(events)}] Fetching decks from {label}...")
        deck_ids = scrape_deck_ids_from_event(ev.event_id, format_id, session)
        if on_progress:
            on_progress(f"  Found {len(deck_ids)} decks")
        for j, did in enumerate(deck_ids, 1):
            if on_progress:
                on_progress(f"  Parsing deck {j}/{len(deck_ids)} (id={did})...")
            deck = scrape_deck_robust(ev.event_id, did, format_id, session)
            if deck:
                if ev.name and (not deck.event_name or deck.event_name == "Unknown"):
                    deck = Deck(
                        deck_id=deck.deck_id,
                        event_id=deck.event_id,
                        format_id=deck.format_id,
                        name=deck.name,
                        player=deck.player,
                        event_name=ev.name,
                        date=deck.date or ev.date,
                        rank=deck.rank,
                        player_count=deck.player_count,
                        mainboard=deck.mainboard,
                        sideboard=deck.sideboard,
                        commanders=deck.commanders,
                        archetype=deck.archetype,
                    )
                decks.append(deck)

    if on_progress:
        on_progress(f"Done. Total: {len(decks)} decks from {len(events)} events.")
    return decks

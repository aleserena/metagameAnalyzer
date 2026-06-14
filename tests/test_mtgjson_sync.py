"""Tests for MTGJSON sync pure functions (parsing, price extraction, printing selection)."""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.services import mtgjson


def test_atomic_card_to_row_single_face():
    faces = [
        {
            "name": "Lightning Bolt",
            "manaCost": "{R}",
            "manaValue": 1,
            "type": "Instant",
            "colors": ["R"],
            "colorIdentity": ["R"],
            "text": "Lightning Bolt deals 3 damage to any target.",
            "layout": "normal",
        }
    ]
    row = mtgjson.atomic_card_to_row("Lightning Bolt", faces)
    assert row["name"] == "Lightning Bolt"
    assert row["mana_cost"] == "{R}"
    assert row["cmc"] == 1.0
    assert row["type_line"] == "Instant"
    assert row["oracle_text"] == "Lightning Bolt deals 3 damage to any target."
    assert row["colors"] == ["R"]
    assert row["color_identity"] == ["R"]
    assert row["layout"] == "normal"
    assert row["card_faces"] == [{"name": "Lightning Bolt", "side": None}]


def test_atomic_card_to_row_split_card_combines_faces():
    faces = [
        {
            "name": "Fire // Ice",
            "faceName": "Fire",
            "side": "a",
            "manaCost": "{1}{R}",
            "manaValue": 2,
            "type": "Instant",
            "colors": ["R"],
            "colorIdentity": ["R", "U"],
            "text": "Fire deals 2 damage divided as you choose.",
            "layout": "split",
        },
        {
            "name": "Fire // Ice",
            "faceName": "Ice",
            "side": "b",
            "manaCost": "{1}{U}",
            "manaValue": 2,
            "type": "Instant",
            "colors": ["U"],
            "colorIdentity": ["R", "U"],
            "text": "Tap target permanent. Draw a card.",
            "layout": "split",
        },
    ]
    row = mtgjson.atomic_card_to_row("Fire // Ice", faces)
    assert row["mana_cost"] == "{1}{R} // {1}{U}"
    assert row["cmc"] == 2.0  # first face's manaValue
    assert row["type_line"] == "Instant // Instant"
    assert row["colors"] == ["U", "R"]  # WUBRG order
    assert row["color_identity"] == ["U", "R"]
    assert row["oracle_text"] == (
        "Fire deals 2 damage divided as you choose. // Tap target permanent. Draw a card."
    )
    assert row["layout"] == "split"
    assert row["card_faces"] == [
        {"name": "Fire", "side": "a"},
        {"name": "Ice", "side": "b"},
    ]


def test_atomic_card_to_row_handles_missing_fields():
    row = mtgjson.atomic_card_to_row("Memnite", [{"name": "Memnite", "type": "Artifact Creature — Construct"}])
    assert row["mana_cost"] == ""
    assert row["cmc"] == 0.0
    assert row["colors"] == []
    assert row["color_identity"] == []
    assert row["layout"] == "normal"


def test_extract_prices_picks_latest_date_per_finish():
    entry = {
        "paper": {
            "tcgplayer": {
                "retail": {
                    "normal": {"2026-06-12": 1.0, "2026-06-13": 1.5},
                    "foil": {"2026-06-13": 9.0},
                }
            },
            "cardmarket": {"retail": {"normal": {"2026-06-13": 2.0}}},
        }
    }
    prices = mtgjson.extract_prices(entry)
    assert prices == {"usd": "1.5", "usd_foil": "9.0", "eur": "2.0", "eur_foil": None}


def test_extract_prices_empty():
    assert mtgjson.extract_prices({}) == {"usd": None, "usd_foil": None, "eur": None, "eur_foil": None}
    assert mtgjson.extract_prices(None) == {"usd": None, "usd_foil": None, "eur": None, "eur_foil": None}


def test_pick_representative_prefers_newest_paper_printing():
    entries = [
        ("u1", {"identifiers": {"scryfallId": "sA"}, "availability": ["paper"], "setCode": "OLD"}),
        ("u2", {"identifiers": {"scryfallId": "sB"}, "availability": ["paper"], "setCode": "NEW"}),
        ("u3", {"identifiers": {"scryfallId": "sC"}, "availability": ["mtgo"], "setCode": "NEWEST"}),
    ]
    set_release = {"OLD": "2010-01-01", "NEW": "2020-01-01", "NEWEST": "2025-01-01"}
    rep = mtgjson.pick_representative_printing(entries, set_release)
    assert rep == {"scryfall_id": "sB", "uuid": "u2"}


def test_pick_representative_falls_back_to_nonpaper():
    entries = [
        ("u1", {"identifiers": {"scryfallId": "sA"}, "availability": ["mtgo"], "setCode": "A"}),
        ("u2", {"identifiers": {"scryfallId": "sB"}, "availability": ["mtgo"], "setCode": "B"}),
    ]
    set_release = {"A": "2010-01-01", "B": "2020-01-01"}
    rep = mtgjson.pick_representative_printing(entries, set_release)
    assert rep == {"scryfall_id": "sB", "uuid": "u2"}


def test_pick_representative_skips_entries_without_scryfall_id():
    entries = [
        ("u1", {"identifiers": {}, "availability": ["paper"], "setCode": "A"}),
        ("u2", {"identifiers": {"scryfallId": "sB"}, "availability": ["paper"], "setCode": "B"}),
    ]
    set_release = {"A": "2025-01-01", "B": "2000-01-01"}
    rep = mtgjson.pick_representative_printing(entries, set_release)
    assert rep == {"scryfall_id": "sB", "uuid": "u2"}


def test_pick_representative_none_when_no_scryfall_id():
    entries = [("u1", {"identifiers": {}, "availability": ["paper"], "setCode": "A"})]
    assert mtgjson.pick_representative_printing(entries, {}) is None


def _wait_until(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_sync_job_runs_in_background_and_reports_status(monkeypatch):
    release = threading.Event()
    started = threading.Event()

    def fake_metadata():
        started.set()
        release.wait(timeout=5)
        return {"cards_synced": 7}

    monkeypatch.setitem(mtgjson._JOB_FNS, "metadata", fake_metadata)
    # Reset registry to a clean state for this test.
    with mtgjson._JOB_LOCK:
        mtgjson._RUNNING["name"] = None
        mtgjson._JOBS["metadata"].update(status="idle", started_at=None, finished_at=None, result=None, error=None)

    try:
        resp = mtgjson.start_sync_job("metadata")
        assert resp["started"] is True
        assert started.wait(timeout=5)

        # While running, a second start is refused and status reflects the running job.
        status = mtgjson.get_sync_status()
        assert status["running"] == "metadata"
        assert status["jobs"]["metadata"]["status"] == "running"
        busy = mtgjson.start_sync_job("metadata")
        assert busy["started"] is False
        assert busy["running"] == "metadata"

        release.set()
        assert _wait_until(lambda: mtgjson.get_sync_status()["running"] is None)
        final = mtgjson.get_sync_status()["jobs"]["metadata"]
        assert final["status"] == "success"
        assert final["result"] == {"cards_synced": 7}
        assert final["finished_at"] is not None
    finally:
        release.set()


def test_sync_job_captures_error(monkeypatch):
    def boom():
        raise RuntimeError("download failed")

    monkeypatch.setitem(mtgjson._JOB_FNS, "metadata", boom)
    with mtgjson._JOB_LOCK:
        mtgjson._RUNNING["name"] = None
        mtgjson._JOBS["metadata"].update(status="idle", started_at=None, finished_at=None, result=None, error=None)

    mtgjson.start_sync_job("metadata")
    assert _wait_until(lambda: mtgjson.get_sync_status()["jobs"]["metadata"]["status"] == "error")
    job = mtgjson.get_sync_status()["jobs"]["metadata"]
    assert "download failed" in (job["error"] or "")
    assert mtgjson.get_sync_status()["running"] is None

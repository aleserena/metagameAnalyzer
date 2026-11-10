import threading

import pytest
from api.services import scrape_job

PARAMS = {
    "format_id": "EDH",
    "period": None,
    "store": None,
    "event_ids": [1],
    "skip_event_ids": None,
    "force_replace": False,
}
EMPTY = {"decks_saved": 0, "events": 0, "failed": []}
ONE = {"decks_saved": 1, "events": 1, "failed": []}


class FakeDeck:
    def to_dict(self):
        return {"deck_id": 1, "event_id": 1}


@pytest.fixture(autouse=True)
def _reset():
    scrape_job._reset_for_tests()
    yield
    scrape_job._reset_for_tests()


def _scrape_ok(**kw):
    kw["on_progress"]("Found 1 events")
    return [FakeDeck()]


def test_job_saves_without_a_listener():
    saved = []

    def persist(decks, force):
        saved.append(decks)
        return ONE

    job = scrape_job.start_job(PARAMS, scrape_fn=_scrape_ok, persist_fn=persist, reload_fn=lambda: None)
    job.thread.join(5)
    snap = scrape_job.snapshot(job)
    assert snap["status"] == "done"
    assert snap["decks_saved"] == 1
    assert len(saved) == 1
    assert "Found 1 events" in snap["messages"]
    assert snap["message"] == "Scraped 1 decks from 1 events"


def test_persist_failure_ends_in_error_and_does_not_reload():
    reloaded = []

    def boom(decks, force):
        raise RuntimeError("db down")

    job = scrape_job.start_job(
        PARAMS, scrape_fn=_scrape_ok, persist_fn=boom, reload_fn=lambda: reloaded.append(1)
    )
    job.thread.join(5)
    snap = scrape_job.snapshot(job)
    assert snap["status"] == "error"
    assert "db down" in snap["message"]
    assert reloaded == []


def test_reload_failure_ends_in_error_and_frees_the_slot():
    def bad_reload():
        raise RuntimeError("reload failed")

    job = scrape_job.start_job(PARAMS, scrape_fn=_scrape_ok, persist_fn=lambda d, f: ONE, reload_fn=bad_reload)
    job.thread.join(5)
    assert scrape_job.snapshot(job)["status"] == "error"
    again = scrape_job.start_job(
        PARAMS, scrape_fn=_scrape_ok, persist_fn=lambda d, f: EMPTY, reload_fn=lambda: None
    )
    again.thread.join(5)
    assert scrape_job.snapshot(again)["status"] == "done"


def test_second_start_is_rejected_while_running():
    gate = threading.Event()

    def slow(**kw):
        gate.wait(5)
        return []

    job = scrape_job.start_job(PARAMS, scrape_fn=slow, persist_fn=lambda d, f: EMPTY, reload_fn=lambda: None)
    with pytest.raises(scrape_job.ScrapeAlreadyRunning):
        scrape_job.start_job(PARAMS, scrape_fn=slow)
    gate.set()
    job.thread.join(5)


def test_snapshot_after_returns_only_new_messages():
    job = scrape_job.start_job(PARAMS, scrape_fn=_scrape_ok, persist_fn=lambda d, f: ONE, reload_fn=lambda: None)
    job.thread.join(5)
    full = scrape_job.snapshot(job)
    assert scrape_job.snapshot(job, after=full["next"])["messages"] == []


def test_scraper_and_persist_failures_are_reported_to_the_user():
    def scrape_with_error(**kw):
        kw["on_deck_error"](10, 2, "boom")
        return [FakeDeck()]

    result = {"decks_saved": 0, "events": 1, "failed": [{"deck_id": 5, "event_id": 11, "error": "bad"}]}
    job = scrape_job.start_job(
        PARAMS, scrape_fn=scrape_with_error, persist_fn=lambda d, f: result, reload_fn=lambda: None
    )
    job.thread.join(5)
    snap = scrape_job.snapshot(job)
    assert len(snap["failed_decks"]) == 2
    assert "2 decks failed" in snap["message"]
    assert "10" in snap["message"]
    assert "11" in snap["message"]


def test_stop_marks_job_cancelled():
    started = threading.Event()

    def stoppable(**kw):
        started.set()
        while not kw["should_stop"]():
            pass
        return []

    job = scrape_job.start_job(PARAMS, scrape_fn=stoppable, persist_fn=lambda d, f: EMPTY, reload_fn=lambda: None)
    started.wait(5)
    assert scrape_job.request_stop() is True
    job.thread.join(5)
    assert scrape_job.snapshot(job)["status"] == "cancelled"

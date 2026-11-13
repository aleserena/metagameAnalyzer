"""Browser protection headers (api/security_headers.py) and their middleware in api/main.py."""

from fastapi.testclient import TestClient

from api.main import app
from api.security_headers import security_headers


def test_headers_when_deployed():
    h = security_headers(deployed=True)
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer"
    assert h["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    csp = h["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    img_src = next(d.split()[1:] for d in csp.split(";") if d.split()[:1] == ["img-src"])
    assert img_src.count("https://cards.scryfall.io") == 1


def test_csp_does_not_allow_inline_or_eval_scripts():
    script_src = next(
        part for part in security_headers(deployed=True)["Content-Security-Policy"].split(";")
        if part.strip().startswith("script-src")
    )
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src
    assert "*" not in script_src


def test_no_hsts_when_not_deployed():
    assert "Strict-Transport-Security" not in security_headers(deployed=False)


def test_report_only_switches_header_name():
    h = security_headers(deployed=True, report_only=True)
    assert "Content-Security-Policy-Report-Only" in h
    assert "Content-Security-Policy" not in h


def test_every_response_carries_the_headers():
    r = TestClient(app).get("/api/v1/info")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_error_responses_carry_the_headers_too():
    r = TestClient(app).get("/api/v1/decks/not-a-number")
    assert r.status_code == 422
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_local_api_docs_are_not_broken_by_the_policy():
    r = TestClient(app).get("/docs")
    assert r.status_code == 200  # docs are on when not deployed
    assert "Content-Security-Policy" not in r.headers
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_unhandled_error_responses_carry_the_headers():
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/api/v1/__test_headers_boom")
    def _boom():
        raise RuntimeError("kaboom")

    app.include_router(router)
    r = TestClient(app, raise_server_exceptions=False).get("/api/v1/__test_headers_boom")
    assert r.status_code == 500
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"

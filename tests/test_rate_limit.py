from types import SimpleNamespace

import pytest

from api.services.rate_limit import RateLimiter, client_ip


def test_blocks_after_max_events_and_recovers():
    now = [0.0]
    rl = RateLimiter(2, 60, clock=lambda: now[0])
    rl.record("a")
    assert rl.allow("a")
    rl.record("a")
    assert not rl.allow("a")
    assert rl.retry_after("a") == 60
    assert rl.allow("b")
    now[0] = 61
    assert rl.allow("a")
    assert rl.retry_after("a") == 0


def test_expired_keys_are_dropped():
    now = [0.0]
    rl = RateLimiter(5, 10, clock=lambda: now[0])
    for i in range(1000):
        rl.record(f"ip-{i}")
    now[0] = 11
    rl.allow("fresh")
    assert len(rl) == 0


def test_client_ip_prefers_x_real_ip():
    req = SimpleNamespace(
        headers={"x-real-ip": "203.0.113.9", "x-forwarded-for": "1.1.1.1"},
        client=SimpleNamespace(host="10.0.0.1"),
    )
    assert client_ip(req) == "203.0.113.9"
    assert client_ip(SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.1"))) == "10.0.0.1"
    assert client_ip(SimpleNamespace(headers={}, client=None)) == "unknown"


def _request(ip: str = "198.51.100.7"):
    return SimpleNamespace(headers={"x-real-ip": ip}, client=SimpleNamespace(host="10.0.0.1"))


def test_rate_limited_dependency_blocks_and_sets_retry_after():
    from fastapi import HTTPException

    from api.services.rate_limit import rate_limited

    dep = rate_limited(RateLimiter(2, 60))
    dep(_request())
    dep(_request())
    with pytest.raises(HTTPException) as exc:
        dep(_request())
    assert exc.value.status_code == 429
    assert exc.value.detail == "Too many requests. Try again later."
    assert int(exc.value.headers["Retry-After"]) >= 1


def test_rate_limited_dependency_counts_each_address_separately():
    from api.services.rate_limit import rate_limited

    dep = rate_limited(RateLimiter(1, 60))
    dep(_request("198.51.100.7"))
    dep(_request("198.51.100.8"))  # a different visitor is not affected

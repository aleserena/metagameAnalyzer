from types import SimpleNamespace

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

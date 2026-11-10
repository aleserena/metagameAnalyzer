import base64
import json
import re

import pytest

from api.services import captcha


@pytest.fixture(autouse=True)
def _reset():
    captcha._reset_for_tests()
    yield
    captcha._reset_for_tests()


def solve(question: str) -> int:
    a, b = map(int, re.fullmatch(r"What is (\d+) \+ (\d+)\?", question).groups())
    return a + b


def test_right_answer_passes_once():
    c = captcha.issue_captcha()
    assert captcha.verify_captcha(c["token"], solve(c["question"])) is True
    assert captcha.verify_captcha(c["token"], solve(c["question"])) is False


def test_wrong_answer_burns_the_token():
    c = captcha.issue_captcha()
    assert captcha.verify_captcha(c["token"], solve(c["question"]) + 1) is False
    assert captcha.verify_captcha(c["token"], solve(c["question"])) is False


def test_expired_and_garbage_tokens_fail(monkeypatch):
    monkeypatch.setattr(captcha, "CAPTCHA_TTL_SECONDS", -5)  # issued already expired
    c = captcha.issue_captcha()
    assert captcha.verify_captcha(c["token"], solve(c["question"])) is False
    assert captcha.verify_captcha("not-a-token", 3) is False


def test_token_does_not_reveal_the_answer():
    c = captcha.issue_captcha()
    payload = json.loads(base64.urlsafe_b64decode(c["token"].split(".")[1] + "=="))
    assert set(payload) == {"typ", "jti", "exp", "h"}


def test_seen_set_is_pruned_of_expired_entries():
    c = captcha.issue_captcha()
    captcha.verify_captcha(c["token"], solve(c["question"]))
    assert len(captcha._seen) == 1
    captcha._seen["old"] = 0.0  # long expired
    c2 = captcha.issue_captcha()
    captcha.verify_captcha(c2["token"], solve(c2["question"]))
    assert "old" not in captcha._seen

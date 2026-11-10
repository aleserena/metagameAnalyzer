"""Server-issued, signed, single-use math captcha for the public feedback form.

The token is an HS256 JWT carrying ``typ``, ``jti``, ``exp`` and ``h`` where
``h = HMAC-SHA256(key, f"{jti}:{answer}")``. The operands and the answer are
never in the token, so a client cannot read the answer out of it.
"""

import hashlib
import hmac
import secrets
import threading
import time

import jwt
from api.dependencies import _JWT_KEY

CAPTCHA_TTL_SECONDS = 600
_ALGORITHM = "HS256"
_TYP = "captcha"

# jti -> exp (epoch seconds) of tokens already used; pruned on use so it stays bounded.
_seen: dict[str, float] = {}
_lock = threading.Lock()


def _answer_hash(jti: str, answer: int) -> str:
    return hmac.new(_JWT_KEY, f"{jti}:{answer}".encode(), hashlib.sha256).hexdigest()


def issue_captcha() -> dict:
    a = secrets.randbelow(20) + 1
    b = secrets.randbelow(20) + 1
    jti = secrets.token_urlsafe(16)
    claims = {
        "typ": _TYP,
        "jti": jti,
        "exp": int(time.time()) + CAPTCHA_TTL_SECONDS,
        "h": _answer_hash(jti, a + b),
    }
    return {
        "question": f"What is {a} + {b}?",
        "token": jwt.encode(claims, _JWT_KEY, algorithm=_ALGORITHM),
    }


def verify_captcha(token: str, answer: int) -> bool:
    try:
        claims = jwt.decode(token, _JWT_KEY, algorithms=[_ALGORITHM], options={"require": ["exp"]})
        jti = claims["jti"]
        expected = claims["h"]
        exp = float(claims["exp"])
    except Exception:
        return False
    if claims.get("typ") != _TYP or not isinstance(jti, str) or not isinstance(expected, str):
        return False
    now = time.time()
    with _lock:
        for k in [k for k, e in _seen.items() if e < now]:
            del _seen[k]
        if jti in _seen:
            return False
        _seen[jti] = exp  # burn the token whether or not the answer is right
    return hmac.compare_digest(expected, _answer_hash(jti, answer))


def _reset_for_tests() -> None:
    with _lock:
        _seen.clear()

import hashlib
from unittest.mock import patch

import pytest

from api import dependencies as deps


def test_refuses_to_start_on_railway_without_jwt_secret():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        deps.validate_auth_config({"RAILWAY_ENVIRONMENT_NAME": "production", "ADMIN_PASSWORD": "pw"})


def test_refuses_to_start_on_railway_without_admin_password():
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        deps.validate_auth_config({"RAILWAY_ENVIRONMENT_NAME": "staging", "JWT_SECRET": "s" * 40})


def test_railway_with_both_secrets_is_allowed():
    deps.validate_auth_config({"RAILWAY_ENVIRONMENT_NAME": "staging", "JWT_SECRET": "s" * 40, "ADMIN_PASSWORD": "pw"})


def test_local_start_without_secrets_is_allowed():
    deps.validate_auth_config({})


def test_is_deployed_detects_railway():
    assert deps.is_deployed({"RAILWAY_ENVIRONMENT_NAME": "production"}) is True
    assert deps.is_deployed({"RAILWAY_ENVIRONMENT_NAME": ""}) is False
    assert deps.is_deployed({}) is False


def test_key_is_never_the_old_hardcoded_default():
    old = hashlib.sha256(b"dev-secret-change-in-production").digest()
    assert deps.derive_jwt_key("", "") != old
    assert deps.derive_jwt_key("", "") != deps.derive_jwt_key("", "")


def test_short_secret_keeps_sha256_derivation():
    assert deps.derive_jwt_key("short", "pw") == hashlib.sha256(b"short").digest()
    long_secret = "s" * 40
    assert deps.derive_jwt_key(long_secret, "pw") == long_secret.encode()
    assert deps.derive_jwt_key("", "pw") == hashlib.sha256(b"pw").digest()


def test_tokens_are_rejected_while_admin_login_is_disabled():
    token = deps._create_admin_token()
    with patch.object(deps, "ADMIN_PASSWORD", ""):
        assert deps._verify_admin_token(token) is False
    with patch.object(deps, "ADMIN_PASSWORD", "pw"):
        assert deps._verify_admin_token(token) is True

import hashlib
import os
import subprocess
import sys
from pathlib import Path
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


def test_whitespace_only_values_are_treated_as_unset():
    assert deps.is_deployed({"RAILWAY_ENVIRONMENT_NAME": "  "}) is False
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        deps.validate_auth_config({"RAILWAY_ENVIRONMENT_NAME": "production", "JWT_SECRET": "   ", "ADMIN_PASSWORD": "pw"})
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        deps.validate_auth_config({"RAILWAY_ENVIRONMENT_NAME": "production", "JWT_SECRET": "s" * 40, "ADMIN_PASSWORD": " "})


def test_validator_lives_in_config_without_importing_state():
    root = Path(__file__).resolve().parent.parent
    code = "import api.config, sys; assert 'api.state' not in sys.modules; assert 'api.dependencies' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], cwd=root, check=True)


def test_invalid_auth_config_alert_email_is_flushed_before_the_import_aborts(tmp_path):
    marker = tmp_path / "sent.txt"
    code = (
        "import api.services.alerts as a\n"
        "def fake(subject, body):\n"
        f"    open({str(marker)!r}, 'a').write(subject + ' ' + body)\n"
        "a.send_alert_email = fake\n"
        "import api.main\n"
    )
    root = Path(__file__).resolve().parent.parent
    env = {
        **os.environ,
        "RAILWAY_ENVIRONMENT_NAME": "test",
        "JWT_SECRET": "",
        "ADMIN_PASSWORD": "pw",
        "ALERTS_ENABLED": "1",
        "ALERT_EMAIL": "ops@example.com",
        "BREVO_API_KEY": "dummy",
        "SMTP_FROM": "from@example.com",
        "DATABASE_URL": os.environ.get("DATABASE_URL", ""),
        "DATABASE_URL_LOCKED": "1",
    }
    result = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert "JWT_SECRET" in result.stderr + result.stdout
    assert marker.exists(), "auth_config_invalid alert was never sent"
    assert "JWT_SECRET" in marker.read_text()


def test_api_docs_disabled_when_deployed():
    from api.config import docs_kwargs

    assert docs_kwargs({"RAILWAY_ENVIRONMENT_NAME": "production"}) == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


def test_api_docs_enabled_locally():
    from api.config import docs_kwargs

    assert docs_kwargs({}) == {}

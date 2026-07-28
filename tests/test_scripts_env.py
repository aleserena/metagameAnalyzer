"""The maintenance scripts must announce which database they are about to touch."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._env import describe_target

_URL = "postgresql://admin:sup3rs3cret@trolley.proxy.rlwy.net:50358/railway"


def test_describe_target_names_the_environment_and_host():
    out = describe_target(_URL, "prod")
    assert "prod" in out
    assert "trolley.proxy.rlwy.net:50358" in out


def test_describe_target_never_leaks_credentials():
    out = describe_target(_URL, "prod")
    assert "sup3rs3cret" not in out
    assert "admin" not in out
    assert "@" not in out


def test_describe_target_handles_missing_url():
    out = describe_target("", "staging")
    assert "staging" in out
    assert "unset" in out.lower()


def test_describe_target_handles_url_without_credentials():
    out = describe_target("postgresql://localhost:5432/mtg", "dev")
    assert "localhost:5432" in out
    assert "dev" in out

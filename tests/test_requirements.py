from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _packages(name):
    lines = [line.strip() for line in (ROOT / name).read_text().splitlines()]
    return [line for line in lines if line and not line.startswith(("#", "-"))]


def test_runtime_requirements_are_pinned_and_have_no_dev_tools():
    pkgs = _packages("requirements.txt")
    assert pkgs
    assert all("==" in p for p in pkgs)
    names = {p.split("==")[0].lower() for p in pkgs}
    assert not names & {"pytest", "pytest-cov", "ruff", "httpx", "pip-tools"}
    assert {"fastapi", "sqlalchemy", "psycopg2-binary", "alembic", "ijson"} <= names


def test_dev_requirements_are_pinned_and_include_the_tools():
    pkgs = _packages("requirements-dev.txt")
    names = {p.split("==")[0].lower() for p in pkgs}
    assert all("==" in p for p in pkgs)
    assert {"pytest", "ruff", "httpx", "fastapi"} <= names

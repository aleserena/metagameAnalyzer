import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_railway_runs_migrations_before_deploy():
    cfg = json.loads((ROOT / "railway.json").read_text())
    assert cfg["deploy"]["preDeployCommand"] == ["alembic upgrade head"]
    assert cfg["deploy"]["healthcheckPath"] == "/api/v1/health"


def test_image_contains_alembic():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "COPY alembic/ ./alembic/" in dockerfile
    assert "COPY alembic.ini ./" in dockerfile

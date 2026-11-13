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


def test_ci_audits_dependencies():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pip-audit -r requirements.txt" in ci
    assert "npm audit --omit=dev --audit-level=high" in ci


def test_dependabot_covers_all_ecosystems():
    import yaml

    config = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())
    updates = {u["package-ecosystem"]: u["directory"] for u in config["updates"]}
    assert updates == {"pip": "/", "npm": "/web", "github-actions": "/", "docker": "/"}

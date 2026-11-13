"""Serving the built frontend (api/main.py mount_spa).

index.html must never be reused from the browser cache without revalidating:
it names the hashed chunk files of the current build, and those of the previous
build are gone after a deploy ("Failed to fetch dynamically imported module").
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import mount_spa


def _client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<html>app</html>")
    app = FastAPI()
    mount_spa(app, tmp_path)
    return TestClient(app)


def test_index_html_is_revalidated_on_every_load(tmp_path):
    client = _client(tmp_path)
    for path in ("/", "/events", "/events/12"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.text == "<html>app</html>"
        assert r.headers["cache-control"] == "no-cache"


def test_hashed_assets_served_and_missing_ones_404(tmp_path):
    client = _client(tmp_path)
    assert client.get("/assets/index-abc123.js").status_code == 200
    # An old build's chunk must 404, not fall back to index.html (which would
    # be parsed as JavaScript and fail with a confusing MIME error).
    assert client.get("/assets/Events-CmWtiSYD.js").status_code == 404


def test_api_paths_do_not_fall_back_to_index(tmp_path):
    assert _client(tmp_path).get("/api/unknown").status_code == 404

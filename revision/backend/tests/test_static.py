"""L'interface compilée est servie par FastAPI, sans jamais sortir de son dossier."""
from __future__ import annotations

import pytest

from app.config import FRONTEND_DIST

pytestmark = pytest.mark.skipif(not (FRONTEND_DIST / "index.html").exists(), reason="interface non compilée")


def test_spa_routes_serve_the_app(client):
    for path in ("/", "/lecons", "/lecon/3/quiz"):
        resp = client.get(path)
        assert resp.status_code == 200 and "<div id=\"root\">" in resp.text, path
    assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg")
    assert client.get("/api/inconnu").status_code == 404


def test_no_file_outside_the_app_folder_is_served(client):
    for path in ("/..%2f..%2f.env.example", "/%2e%2e/%2e%2e/README.md", "/..%2f..%2fbackend/requirements.txt"):
        resp = client.get(path)
        assert "<div id=\"root\">" in resp.text or resp.status_code == 404, path

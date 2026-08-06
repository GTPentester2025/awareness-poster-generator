import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import canva
from tests.test_content import SETTINGS, VALID


@pytest.fixture()
def client(tmp_path, monkeypatch):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path, "token_path": tmp_path / "token.json"})
    monkeypatch.setattr(main, "settings", s)
    return TestClient(main.app)


def test_status_disconnected(client):
    assert client.get("/api/status").json() == {"canva_connected": False}


def test_auth_redirects(client):
    r = client.get("/auth/canva", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://www.canva.com/api/oauth/authorize?")


def test_poster_happy_path(client, monkeypatch, tmp_path):
    fake_pptx = tmp_path / "poster_x.pptx"
    fake_pptx.write_bytes(b"pptx")
    monkeypatch.setattr(main.content, "generate", lambda topic, s, client=None: dict(VALID))
    monkeypatch.setattr(main.artwork, "generate", lambda p, o, s, client=None: None)
    monkeypatch.setattr(main.builder, "build", lambda c, i, o, d: fake_pptx)
    monkeypatch.setattr(main.canva, "import_design", lambda s, p, t, **kw: "https://canva.com/edit/d1")
    r = client.post("/api/posters", json={"topic": "road safety", "orientation": "portrait"})
    body = r.json()
    assert r.status_code == 200
    assert body["edit_url"] == "https://canva.com/edit/d1"
    assert body["content"]["headline"] == VALID["headline"]
    assert any("background" in w.lower() for w in body["warnings"])


def test_poster_import_failure_offers_download(client, monkeypatch, tmp_path):
    fake_pptx = tmp_path / "poster_y.pptx"
    fake_pptx.write_bytes(b"pptx")
    monkeypatch.setattr(main.content, "generate", lambda topic, s, client=None: dict(VALID))
    monkeypatch.setattr(main.artwork, "generate", lambda p, o, s, client=None: None)
    monkeypatch.setattr(main.builder, "build", lambda c, i, o, d: fake_pptx)

    def boom(*a, **kw):
        raise canva.ImportFailed("bad")

    monkeypatch.setattr(main.canva, "import_design", boom)
    body = client.post("/api/posters", json={"topic": "x", "orientation": "portrait"}).json()
    assert body["edit_url"] is None
    assert body["pptx_download"] == "/api/download/poster_y.pptx"
    dl = client.get(body["pptx_download"])
    assert dl.status_code == 200


def test_poster_not_authenticated(client, monkeypatch):
    monkeypatch.setattr(main.content, "generate", lambda topic, s, client=None: dict(VALID))
    monkeypatch.setattr(main.artwork, "generate", lambda p, o, s, client=None: None)

    def build(c, i, o, d):
        p = main.settings.out_dir / "poster_z.pptx"
        p.write_bytes(b"pptx")
        return p

    monkeypatch.setattr(main.builder, "build", build)

    def nope(*a, **kw):
        raise canva.NotAuthenticated("no token")

    monkeypatch.setattr(main.canva, "import_design", nope)
    r = client.post("/api/posters", json={"topic": "x", "orientation": "portrait"})
    assert r.status_code == 401


def test_bad_orientation_rejected(client):
    r = client.post("/api/posters", json={"topic": "x", "orientation": "square"})
    assert r.status_code == 422


def test_download_traversal_blocked(client):
    assert client.get("/api/download/..%5Ctoken.json").status_code in (404, 422)


def test_download_drive_relative_blocked(client):
    assert client.get("/api/download/C%3A.env").status_code == 404

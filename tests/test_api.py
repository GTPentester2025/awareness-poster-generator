import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import canva
from tests.test_content import SETTINGS, VARIANTS


@pytest.fixture()
def client(tmp_path, monkeypatch):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path, "token_path": tmp_path / "token.json"})
    monkeypatch.setattr(main, "settings", s)
    monkeypatch.setattr(main.knowledge, "retrieve", lambda topic: [])
    monkeypatch.setattr(main.research, "web_research", lambda topic, s, client=None: None)
    monkeypatch.setattr(main.critique, "critique_pptx", lambda p, s, client=None: None)
    monkeypatch.setattr(main.history, "avoid_block", lambda path=None: "")
    monkeypatch.setattr(main.history, "remember", lambda specs, path=None: None)
    monkeypatch.setattr(main.brand, "DEFAULT_PATH", tmp_path / "brand.json")
    monkeypatch.setattr(main.curation, "synthesize_brief",
                        lambda topic, docs, s, n_angles=5, client=None: {
                            "synthesis": "brief", "grounded": bool(docs),
                            "angles": [{"title": f"angle {i}", "rationale": "", "key_facts": []}
                                       for i in range(max(4, n_angles))]})
    monkeypatch.setattr(main.recipes, "shortlist", lambda moods, k=15, seed=0: [{"archetype": "hero_top"}])
    monkeypatch.setattr(main.director, "select_recipes",
                        lambda variants, pool, s, client=None: [{"recipe": {}, "image_subject": ""} for _ in variants])
    return TestClient(main.app)


def _connect(tmp_path):
    (tmp_path / "token.json").write_text(json.dumps({
        "access_token": "t", "refresh_token": "r", "expires_at": 9999999999,
    }))


_BASE_SPEC = {
    "archetype": "hero_top",
    "palette": {"bg": "#0E3A5D", "surface": "#FFFFFF", "accent": "#3EC1D3", "text": "#FFFFFF", "muted": "#9AA5B1"},
    "fonts": {"heading": "Anton", "body": "Open Sans"},
    "card_style": "filled", "header_style": "block", "accent_shapes": True,
    "image_prompt": "x", "fact_stats": [],
}
SPECS = [
    {**_BASE_SPEC, "archetype": "hero_top", "background_style": "solid"},
    {**_BASE_SPEC, "archetype": "steps_path", "background_style": "solid"},
    {**_BASE_SPEC, "archetype": "big_number", "background_style": "image"},
]


def _happy_mocks(monkeypatch, tmp_path):
    fake_pptx = tmp_path / "poster_x.pptx"
    fake_pptx.write_bytes(b"pptx")
    monkeypatch.setattr(main.content, "generate_reviewed",
                        lambda topic, s, knowledge_docs=None, angles=None, brand_block="", brief="", count=3, client=None: ([dict(v) for v in VARIANTS][:count], {"score": 92, "feedback": []}))
    specs_iter = iter([dict(x) for x in SPECS])
    monkeypatch.setattr(main.recipes, "recipe_to_spec", lambda recipe, subject="": next(specs_iter))
    monkeypatch.setattr(main.artwork, "generate", lambda p, o, s, client=None: None)
    monkeypatch.setattr(main.builder, "render", lambda spec, variant, i, o, d: fake_pptx)
    monkeypatch.setattr(main.canva, "import_design", lambda s, p, t, **kw: "https://canva.com/edit/d1")
    return fake_pptx


def test_status_disconnected(client):
    assert client.get("/api/status").json() == {"canva_connected": False}


def test_auth_redirects(client):
    r = client.get("/auth/canva", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://www.canva.com/api/oauth/authorize?")


def test_poster_returns_three_options(client, monkeypatch, tmp_path):
    _connect(tmp_path)
    _happy_mocks(monkeypatch, tmp_path)
    r = client.post("/api/posters", json={"topic": "road safety", "orientation": "portrait"})
    body = r.json()
    assert r.status_code == 200
    assert len(body["options"]) == 3
    archetypes = [o["archetype"] for o in body["options"]]
    assert len(set(archetypes)) == 3  # distinct layouts (shape-matched)
    assert body["options"][0]["edit_url"] == "https://canva.com/edit/d1"
    assert body["options"][1]["content"]["angle"] == "impact"
    assert all(isinstance(o["lint_score"], int) for o in body["options"])
    # third spec wanted an image; artwork mock returned None → warning on that option only
    assert any("image" in w.lower() for w in body["options"][2]["warnings"])
    assert body["options"][0]["warnings"] == []


def test_poster_not_connected_401_before_generation(client, monkeypatch):
    called = {"content": False}

    def content_gen(*a, **kw):
        called["content"] = True
        return [dict(v) for v in VARIANTS], {"score": 90, "feedback": []}

    monkeypatch.setattr(main.content, "generate_reviewed", content_gen)
    r = client.post("/api/posters", json={"topic": "x", "orientation": "portrait"})
    assert r.status_code == 401
    assert called["content"] is False  # no OpenAI spend without Canva connection


def test_poster_import_failure_isolated_to_option(client, monkeypatch, tmp_path):
    _connect(tmp_path)
    fake_pptx = _happy_mocks(monkeypatch, tmp_path)

    calls = {"n": 0}

    def import_flaky(s, p, t, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise canva.ImportFailed("bad")
        return "https://canva.com/edit/ok"

    monkeypatch.setattr(main.canva, "import_design", import_flaky)
    body = client.post("/api/posters", json={"topic": "x", "orientation": "portrait"}).json()
    oks = [o for o in body["options"] if o["edit_url"]]
    failed = [o for o in body["options"] if not o["edit_url"]]
    assert len(oks) == 2 and len(failed) == 1
    assert failed[0]["pptx_download"] == f"/api/download/{fake_pptx.name}"


def test_poster_direction_failure_falls_back_to_single(client, monkeypatch, tmp_path):
    _connect(tmp_path)
    fake_pptx = tmp_path / "poster_fb.pptx"
    fake_pptx.write_bytes(b"pptx")
    monkeypatch.setattr(main.content, "generate_reviewed",
                        lambda topic, s, knowledge_docs=None, angles=None, brand_block="", brief="", count=3, client=None: ([dict(v) for v in VARIANTS][:count], {"score": 90, "feedback": []}))

    def boom(*a, **kw):
        raise ValueError("recipe selection failed")

    monkeypatch.setattr(main.recipes, "shortlist", boom)
    monkeypatch.setattr(main.artwork, "generate", lambda p, o, s, client=None: None)
    monkeypatch.setattr(main.builder, "fallback_build", lambda c, i, o, d: fake_pptx)
    monkeypatch.setattr(main.canva, "import_design", lambda s, p, t, **kw: "https://canva.com/edit/fb")
    body = client.post("/api/posters", json={"topic": "x", "orientation": "portrait"}).json()
    assert len(body["options"]) == 1
    assert body["options"][0]["edit_url"] == "https://canva.com/edit/fb"
    assert any("art direction" in w.lower() for w in body["options"][0]["warnings"])


def test_num_options_controls_count(client, monkeypatch, tmp_path):
    _connect(tmp_path)
    fake_pptx = tmp_path / "poster_n.pptx"
    fake_pptx.write_bytes(b"pptx")
    monkeypatch.setattr(main.content, "generate_reviewed",
                        lambda topic, s, knowledge_docs=None, angles=None, brand_block="", brief="", count=3, client=None: ([dict(v) for v in VARIANTS][:count], {"score": 90, "feedback": []}))
    specs_iter = iter([dict(x) for x in SPECS])
    monkeypatch.setattr(main.recipes, "recipe_to_spec", lambda recipe, subject="": next(specs_iter))
    monkeypatch.setattr(main.artwork, "generate", lambda p, o, s, client=None: None)
    monkeypatch.setattr(main.builder, "render", lambda spec, variant, i, o, d: fake_pptx)
    monkeypatch.setattr(main.canva, "import_design", lambda s, p, t, **kw: "https://canva.com/edit/n")
    body = client.post("/api/posters", json={"topic": "x", "num_options": 2}).json()
    assert len(body["options"]) == 2


def test_num_options_out_of_range_rejected(client):
    r = client.post("/api/posters", json={"topic": "x", "num_options": 99})
    assert r.status_code == 422


def test_suggest_angles(client, monkeypatch):
    body = client.post("/api/angles", json={"topic": "phishing", "n": 6}).json()
    assert "angles" in body and len(body["angles"]) >= 4
    assert all("title" in a for a in body["angles"])


def test_knowledge_titles_reported(client, monkeypatch, tmp_path):
    _connect(tmp_path)
    _happy_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr(main.knowledge, "retrieve",
                        lambda topic: [{"title": "GDPR (EU)", "keywords": set(), "body": "x"}])
    body = client.post("/api/posters", json={"topic": "gdpr", "orientation": "portrait"}).json()
    assert body["knowledge_used"] == ["GDPR (EU)"]


def test_both_orientations_doubles_options(client, monkeypatch, tmp_path):
    _connect(tmp_path)
    _happy_mocks(monkeypatch, tmp_path)
    body = client.post("/api/posters", json={"topic": "x", "orientation": "both"}).json()
    assert len(body["options"]) == 6
    orientations = [o["orientation"] for o in body["options"]]
    assert orientations.count("portrait") == 3
    assert orientations.count("landscape") == 3


def test_brand_roundtrip(client, monkeypatch, tmp_path):
    r = client.post("/api/brand", json={
        "org_name": "Acme", "about": "Safety non-profit",
        "colors": ["#112233", "notahex", "#AABBCC"],
    })
    assert r.status_code == 200
    saved = r.json()
    assert saved["org_name"] == "Acme"
    assert saved["colors"] == ["#112233", "#AABBCC"]
    got = client.get("/api/brand").json()
    assert got["about"] == "Safety non-profit"


def test_bad_orientation_rejected(client):
    r = client.post("/api/posters", json={"topic": "x", "orientation": "square"})
    assert r.status_code == 422


def test_download_traversal_blocked(client):
    assert client.get("/api/download/..%5Ctoken.json").status_code in (404, 422)


def test_download_drive_relative_blocked(client):
    assert client.get("/api/download/C%3A.env").status_code == 404

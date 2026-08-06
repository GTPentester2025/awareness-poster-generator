import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.envfile import read_env


@pytest.fixture()
def client(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "OPENAI_API_KEY=sk-dummy-key-for-testing\n"
        "CANVA_CLIENT_ID=dummy_client_id\n"
        "CANVA_CLIENT_SECRET=dummy_client_secret\n"
        "BASE_URL=http://127.0.0.1:8010\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "ENV_PATH", env)
    main.reload_settings()
    return TestClient(main.app), env


def test_get_config_masks_secrets(client):
    c, _ = client
    body = c.get("/api/config").json()
    assert body["openai_api_key"]["set"] is True
    # full secret never present in the masked hint
    assert "sk-dummy-key-for-testing" not in body["openai_api_key"]["hint"]
    assert body["openai_api_key"]["hint"].endswith("ting")
    assert body["base_url"] == "http://127.0.0.1:8010"


def test_post_config_writes_and_reloads(client):
    c, env = client
    resp = c.post("/api/config", json={
        "openai_api_key": "sk-real-openai-key-999",
        "canva_client_id": "real_id_123",
        "canva_client_secret": "real_secret_456",
    })
    assert resp.status_code == 200
    saved = read_env(env)
    assert saved["OPENAI_API_KEY"] == "sk-real-openai-key-999"
    assert saved["CANVA_CLIENT_ID"] == "real_id_123"
    assert saved["CANVA_CLIENT_SECRET"] == "real_secret_456"
    # hot reload took effect on the live settings object
    assert main.settings.canva_client_id == "real_id_123"
    # BASE_URL preserved
    assert saved["BASE_URL"] == "http://127.0.0.1:8010"


def test_post_config_never_returns_full_secret(client):
    c, _ = client
    resp = c.post("/api/config", json={"canva_client_secret": "super_secret_value_xyz"})
    assert "super_secret_value_xyz" not in resp.text


def test_post_empty_field_keeps_existing(client):
    c, env = client
    c.post("/api/config", json={"openai_api_key": "sk-new-key-abcd"})
    # omitting canva fields must not wipe them
    saved = read_env(env)
    assert saved["CANVA_CLIENT_ID"] == "dummy_client_id"
    assert saved["OPENAI_API_KEY"] == "sk-new-key-abcd"

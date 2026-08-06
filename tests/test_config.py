from pathlib import Path

from app.config import load_settings


def _env(**overrides):
    base = {
        "OPENAI_API_KEY": "sk-test",
        "CANVA_CLIENT_ID": "cid",
        "CANVA_CLIENT_SECRET": "csecret",
    }
    base.update(overrides)
    return base


def test_loads_required_keys():
    s = load_settings(_env())
    assert s.openai_api_key == "sk-test"
    assert s.canva_client_id == "cid"
    assert s.canva_client_secret == "csecret"


def test_defaults():
    s = load_settings(_env())
    assert s.openai_text_model == "gpt-4o-mini"
    assert s.base_url == "http://127.0.0.1:8000"
    assert s.out_dir == Path("out")
    assert s.token_path == Path("token.json")


def test_text_model_override():
    s = load_settings(_env(OPENAI_TEXT_MODEL="gpt-4o"))
    assert s.openai_text_model == "gpt-4o"


def test_missing_key_raises():
    import pytest
    with pytest.raises(KeyError):
        load_settings({"OPENAI_API_KEY": "sk-test"})

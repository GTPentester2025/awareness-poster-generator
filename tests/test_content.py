import json

import pytest

from app.config import Settings
from app.content import generate, validate_content
from pathlib import Path

SETTINGS = Settings(
    openai_api_key="sk-test", openai_text_model="gpt-4o-mini",
    canva_client_id="c", canva_client_secret="s",
    base_url="http://127.0.0.1:8000", out_dir=Path("out"), token_path=Path("token.json"),
)

VALID = {
    "headline": "Save Water, Save Life",
    "subheadline": "Every drop counts more than you think",
    "facts": ["A dripping tap wastes 5,500 L/year", "Only 3% of Earth's water is fresh", "Showers beat baths by 50 L"],
    "cta": "Turn it off. Today.",
    "palette": {"bg": "#0E3A5D", "accent": "#3EC1D3", "text": "#FFFFFF"},
    "image_prompt": "minimal water drop illustration, deep blue background, space at top for text",
}


def test_valid_passes():
    assert validate_content(VALID) == VALID


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("headline"),
    lambda d: d.update(headline="x" * 61),
    lambda d: d.update(facts=["only one"]),
    lambda d: d.update(facts=["a"] * 6),
    lambda d: d.update(facts=["ok", "", "ok2"]),
    lambda d: d["palette"].update(bg="blue"),
    lambda d: d["palette"].pop("accent"),
    lambda d: d.update(image_prompt=""),
])
def test_invalid_rejected(mutate):
    bad = json.loads(json.dumps(VALID))
    mutate(bad)
    with pytest.raises(ValueError):
        validate_content(bad)


class FakeCompletions:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        text = self.payloads.pop(0)
        msg = type("M", (), {"content": text})
        choice = type("C", (), {"message": msg})
        return type("R", (), {"choices": [choice]})


class FakeClient:
    def __init__(self, payloads):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(payloads)


def test_generate_returns_valid_dict():
    client = FakeClient([json.dumps(VALID)])
    out = generate("water conservation", SETTINGS, client=client)
    assert out["headline"] == VALID["headline"]


def test_generate_retries_once_then_succeeds():
    client = FakeClient(["not json", json.dumps(VALID)])
    out = generate("water conservation", SETTINGS, client=client)
    assert out["facts"] == VALID["facts"]
    assert client.chat.completions.calls == 2


def test_generate_fails_after_two_bad():
    client = FakeClient(["not json", "{}"])
    with pytest.raises(ValueError):
        generate("water conservation", SETTINGS, client=client)

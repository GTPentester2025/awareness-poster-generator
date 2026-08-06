import json

import pytest

from app import design
from app.config import Settings
from pathlib import Path

SETTINGS = Settings(
    openai_api_key="sk-test", openai_text_model="gpt-4o-mini",
    canva_client_id="c", canva_client_secret="s",
    base_url="http://127.0.0.1:8000", out_dir=Path("out"), token_path=Path("token.json"),
)

VALID_PLAN = {
    "palette": {"bg": "#0E3A5D", "accent": "#3EC1D3", "text": "#FFFFFF"},
    "font_heading": "Anton",
    "font_body": "Open Sans",
    "background": {"mode": "solid"},
    "elements": [
        {"type": "shape", "shape": "rect", "x": 0, "y": 0, "w": 1, "h": 0.2,
         "color": "#3EC1D3", "opacity": 0.5},
        {"type": "text", "text": "Save Water", "x": 0.1, "y": 0.05, "w": 0.8, "h": 0.15,
         "font": "Anton", "size_pt": 54, "weight": "bold", "align": "center", "color": "#FFFFFF"},
        {"type": "text", "text": "Every drop counts", "x": 0.1, "y": 0.3, "w": 0.8, "h": 0.1,
         "font": "Open Sans", "size_pt": 20, "weight": "normal", "align": "left", "color": "#FFFFFF"},
    ],
}


def test_valid_plan_passes():
    plan = design.validate_plan(json.loads(json.dumps(VALID_PLAN)))
    assert plan["font_heading"] == "Anton"
    assert len(plan["elements"]) == 3


def test_unknown_font_coerced_to_default():
    bad = json.loads(json.dumps(VALID_PLAN))
    bad["font_heading"] = "Comic Monstrosity"
    bad["elements"][1]["font"] = "Nonexistent Font"
    plan = design.validate_plan(bad)
    assert plan["font_heading"] == design.DEFAULT_HEADING
    assert plan["elements"][1]["font"] == design.DEFAULT_BODY


def test_out_of_range_coords_clamped():
    bad = json.loads(json.dumps(VALID_PLAN))
    bad["elements"][1]["x"] = 5.0
    bad["elements"][1]["size_pt"] = 9999
    plan = design.validate_plan(bad)
    assert 0.0 <= plan["elements"][1]["x"] <= 1.0
    assert plan["elements"][1]["size_pt"] <= 160


def test_bad_background_mode_defaults_solid():
    bad = json.loads(json.dumps(VALID_PLAN))
    bad["background"] = {"mode": "hologram"}
    plan = design.validate_plan(bad)
    assert plan["background"]["mode"] == "solid"


def test_empty_text_element_dropped():
    bad = json.loads(json.dumps(VALID_PLAN))
    bad["elements"].append({"type": "text", "text": "   ", "x": 0.1, "y": 0.5, "w": 0.5, "h": 0.1})
    plan = design.validate_plan(bad)
    texts = [e for e in plan["elements"] if e["type"] == "text"]
    assert len(texts) == 2  # blank one dropped


def test_no_text_raises():
    bad = {"palette": VALID_PLAN["palette"], "background": {"mode": "solid"},
           "elements": [{"type": "shape", "shape": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "color": "#3EC1D3"}]}
    with pytest.raises(ValueError):
        design.validate_plan(bad)


def test_bad_palette_raises():
    bad = json.loads(json.dumps(VALID_PLAN))
    bad["palette"]["bg"] = "navy"
    with pytest.raises(ValueError):
        design.validate_plan(bad)


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


CONTENT = {
    "headline": "Save Water", "subheadline": "Every drop counts",
    "facts": ["a", "b", "c"], "cta": "Act now",
    "palette": VALID_PLAN["palette"],
}


def test_generate_returns_plan():
    client = FakeClient([json.dumps(VALID_PLAN)])
    plan = design.generate(CONTENT, "portrait", SETTINGS, client=client)
    assert plan["elements"][1]["text"] == "Save Water"


def test_generate_retries_then_succeeds():
    client = FakeClient(["not json", json.dumps(VALID_PLAN)])
    plan = design.generate(CONTENT, "portrait", SETTINGS, client=client)
    assert client.chat.completions.calls == 2
    assert plan["palette"]["bg"] == "#0E3A5D"


def test_generate_fails_after_two_bad():
    client = FakeClient(["not json", "{}"])
    with pytest.raises(ValueError):
        design.generate(CONTENT, "portrait", SETTINGS, client=client)

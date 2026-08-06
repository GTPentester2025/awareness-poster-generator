import json
from pathlib import Path

import pytest

from app import design
from app.config import Settings

SETTINGS = Settings(
    openai_api_key="sk-test", openai_text_model="gpt-4o-mini",
    canva_client_id="c", canva_client_secret="s",
    base_url="http://127.0.0.1:8000", out_dir=Path("out"), token_path=Path("token.json"),
)

VALID_SPEC = {
    "archetype": "hero_top",
    "palette": {"bg": "#0E3A5D", "surface": "#FFFFFF", "accent": "#3EC1D3",
                "text": "#FFFFFF", "muted": "#9AA5B1"},
    "fonts": {"heading": "Anton", "body": "Open Sans"},
    "background_style": "image",
    "card_style": "filled",
    "header_style": "block",
    "accent_shapes": True,
    "image_prompt": "water drops, deep blue, minimal, no text",
    "fact_stats": ["5,500L", "3%", "50L"],
}


def test_valid_spec_passes():
    s = design.validate_spec(json.loads(json.dumps(VALID_SPEC)))
    assert s["archetype"] == "hero_top"
    assert s["fonts"]["heading"] == "Anton"
    assert s["fact_stats"] == ["5,500L", "3%", "50L"]


def test_bad_archetype_defaults():
    bad = {**VALID_SPEC, "archetype": "spiral"}
    assert design.validate_spec(json.loads(json.dumps(bad)))["archetype"] == "hero_top"


def test_unknown_fonts_coerced():
    bad = json.loads(json.dumps(VALID_SPEC))
    bad["fonts"] = {"heading": "Wingdings3000", "body": "MadeUp"}
    s = design.validate_spec(bad)
    assert s["fonts"]["heading"] == design.DEFAULT_HEADING
    assert s["fonts"]["body"] == design.DEFAULT_BODY


def test_missing_surface_and_muted_defaulted():
    bad = json.loads(json.dumps(VALID_SPEC))
    del bad["palette"]["surface"]
    del bad["palette"]["muted"]
    s = design.validate_spec(bad)
    assert s["palette"]["surface"] == design.PALETTE_DEFAULTS["surface"]
    assert s["palette"]["muted"] == design.PALETTE_DEFAULTS["muted"]


@pytest.mark.parametrize("field,default", [
    ("background_style", "image"), ("card_style", "filled"), ("header_style", "block"),
])
def test_bad_enum_fields_default(field, default):
    bad = json.loads(json.dumps(VALID_SPEC))
    bad[field] = "nonsense"
    assert design.validate_spec(bad)[field] == default


def test_bad_core_palette_raises():
    bad = json.loads(json.dumps(VALID_SPEC))
    bad["palette"]["bg"] = "navy"
    with pytest.raises(ValueError):
        design.validate_spec(bad)


def test_fact_stats_non_list_becomes_empty():
    bad = json.loads(json.dumps(VALID_SPEC))
    bad["fact_stats"] = "oops"
    assert design.validate_spec(bad)["fact_stats"] == []


def test_missing_image_prompt_gets_fallback():
    bad = json.loads(json.dumps(VALID_SPEC))
    del bad["image_prompt"]
    assert design.validate_spec(bad)["image_prompt"]


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


VARIANTS = [
    {"angle": "precautions", "headline": "A", "subheadline": "a",
     "points": [{"stat": "1", "text": "t1"}], "cta": "go", "sources": []},
    {"angle": "stats", "headline": "B", "subheadline": "b",
     "points": [{"stat": "2", "text": "t2"}], "cta": "go", "sources": []},
    {"angle": "impact", "headline": "C", "subheadline": "c",
     "points": [{"stat": "3", "text": "t3"}], "cta": "go", "sources": []},
]


def _directions_payload(archetypes):
    return json.dumps({"directions": [
        {**json.loads(json.dumps(VALID_SPEC)), "archetype": a} for a in archetypes
    ]})


def test_validate_directions_distinct_kept():
    data = json.loads(_directions_payload(["hero_top", "sidebar", "big_number"]))
    specs = design.validate_directions(data)
    assert [s["archetype"] for s in specs] == ["hero_top", "sidebar", "big_number"]


def test_validate_directions_duplicates_reassigned():
    data = json.loads(_directions_payload(["hero_top", "hero_top", "hero_top"]))
    specs = design.validate_directions(data)
    archs = [s["archetype"] for s in specs]
    assert len(set(archs)) == 3
    assert archs[0] == "hero_top"


def test_validate_directions_wrong_count_raises():
    data = json.loads(_directions_payload(["hero_top", "sidebar"]))
    with pytest.raises(ValueError):
        design.validate_directions(data)


def test_generate_directions_returns_three():
    client = FakeClient([_directions_payload(["hero_top", "steps_path", "split_band"])])
    specs = design.generate_directions(VARIANTS, "portrait", SETTINGS, client=client)
    assert len(specs) == 3
    assert specs[1]["archetype"] == "steps_path"


def test_generate_directions_retries_then_succeeds():
    client = FakeClient(["not json", _directions_payload(["hero_top", "sidebar", "banner_header"])])
    specs = design.generate_directions(VARIANTS, "portrait", SETTINGS, client=client)
    assert client.chat.completions.calls == 2
    assert len(specs) == 3


def test_generate_directions_fails_after_two_bad():
    client = FakeClient(["not json", "{}"])
    with pytest.raises(ValueError):
        design.generate_directions(VARIANTS, "portrait", SETTINGS, client=client)

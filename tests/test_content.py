import json
from pathlib import Path

import pytest

from app.config import Settings
from app.content import generate, to_legacy, validate_content, validate_variant

SETTINGS = Settings(
    openai_api_key="sk-test", openai_text_model="gpt-4o-mini",
    canva_client_id="c", canva_client_secret="s",
    base_url="http://127.0.0.1:8000", out_dir=Path("out"), token_path=Path("token.json"),
)

# Legacy content dict — still used by builder.fallback_build and its tests.
VALID = {
    "headline": "Save Water, Save Life",
    "subheadline": "Every drop counts more than you think",
    "facts": ["A dripping tap wastes 5,500 L/year", "Only 3% of Earth's water is fresh", "Showers beat baths by 50 L"],
    "cta": "Turn it off. Today.",
    "palette": {"bg": "#0E3A5D", "accent": "#3EC1D3", "text": "#FFFFFF"},
    "image_prompt": "minimal water drop illustration, deep blue background, space at top for text",
}

VARIANT = {
    "angle": "precautions",
    "headline": "Save Water, Save Life",
    "subheadline": "Every drop counts more than you think",
    "points": [
        {"stat": "5,500L", "text": "A dripping tap wastes 5,500 litres a year"},
        {"stat": "3%", "text": "Only 3% of Earth's water is fresh"},
        {"stat": "50L", "text": "Showers beat baths by 50 litres"},
    ],
    "cta": "Turn it off. Today.",
    "sources": ["WHO"],
}

VARIANTS = [
    VARIANT,
    {**VARIANT, "angle": "impact", "points": VARIANT["points"] + [
        {"stat": "2025", "text": "Water stress already affects billions"},
    ]},
    {**VARIANT, "angle": "stats"},
]


def _payload():
    return json.loads(json.dumps({"variants": VARIANTS}))


def test_valid_variants_pass():
    out = validate_content(_payload())
    assert len(out["variants"]) == 3
    assert out["variants"][1]["angle"] == "impact"
    assert len(out["variants"][1]["points"]) == 4


def test_unknown_angle_coerced():
    v = json.loads(json.dumps(VARIANT))
    v["angle"] = "interpretive_dance"
    assert validate_variant(v)["angle"] == "precautions"


def test_missing_stat_gets_number():
    v = json.loads(json.dumps(VARIANT))
    del v["points"][1]["stat"]
    out = validate_variant(v)
    assert out["points"][1]["stat"] == "2"


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("headline"),
    lambda d: d.update(headline="x" * 61),
    lambda d: d.update(points=[]),
    lambda d: d.update(points=[{"stat": "x", "text": "ok"}] * 7),
    lambda d: d["points"].__setitem__(0, {"stat": "x", "text": ""}),
    lambda d: d.pop("cta"),
])
def test_invalid_variant_rejected(mutate):
    bad = json.loads(json.dumps(VARIANT))
    mutate(bad)
    with pytest.raises(ValueError):
        validate_variant(bad)


def test_wrong_variant_count_rejected():
    with pytest.raises(ValueError):
        validate_content({"variants": [json.loads(json.dumps(VARIANT))]})


def test_same_angles_rejected():
    same = json.loads(json.dumps({"variants": [VARIANT, VARIANT, VARIANT]}))
    with pytest.raises(ValueError):
        validate_content(same)


def test_sources_capped_and_cleaned():
    v = json.loads(json.dumps(VARIANT))
    v["sources"] = ["A", "", "B", 42, "C", "D"]
    assert validate_variant(v)["sources"] == ["A", "B", "C"]


def test_to_legacy_adapter():
    legacy = to_legacy(VARIANT)
    assert legacy["headline"] == VARIANT["headline"]
    assert legacy["facts"][0] == VARIANT["points"][0]["text"]
    assert "palette" in legacy


class FakeCompletions:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        text = self.payloads.pop(0)
        msg = type("M", (), {"content": text})
        choice = type("C", (), {"message": msg})
        return type("R", (), {"choices": [choice]})


class FakeClient:
    def __init__(self, payloads):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(payloads)


def test_generate_returns_variants():
    client = FakeClient([json.dumps({"variants": VARIANTS})])
    out = generate("water conservation", SETTINGS, client=client)
    assert len(out) == 3


def test_generate_includes_knowledge_in_prompt():
    client = FakeClient([json.dumps({"variants": VARIANTS})])
    docs = [{"title": "GDPR", "keywords": {"gdpr"}, "body": "Fines up to 4% of turnover."}]
    generate("gdpr basics", SETTINGS, knowledge_docs=docs, client=client)
    user_msg = client.chat.completions.last_kwargs["messages"][1]["content"]
    assert "REFERENCE MATERIAL" in user_msg
    assert "4% of turnover" in user_msg


def test_generate_retries_then_fails():
    client = FakeClient(["not json", "{}"])
    with pytest.raises(ValueError):
        generate("x", SETTINGS, client=client)
    assert client.chat.completions.calls == 2

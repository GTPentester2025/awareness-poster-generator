import json
from pathlib import Path

from app import content, curation
from app.config import Settings
from tests.test_content import VARIANTS

SETTINGS = Settings(
    openai_api_key="sk-test", openai_text_model="gpt-4o-mini",
    canva_client_id="c", canva_client_secret="s",
    base_url="http://127.0.0.1:8000", out_dir=Path("out"), token_path=Path("token.json"),
)


class FakeCompletions:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        text = self.payloads.pop(0)
        return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": text})})]})


class FakeClient:
    def __init__(self, payloads):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(payloads)


def test_synthesize_returns_grounded_angles():
    payload = json.dumps({"synthesis": "s" * 60, "grounded": True, "angles": [
        {"title": "the hover test", "rationale": "teaches url check", "key_facts": ["hover reveals url"]},
        {"title": "bank never asks", "rationale": "corrects myth", "key_facts": []},
        {"title": "friday 5pm attack", "rationale": "timing", "key_facts": []},
        {"title": "cost to a family", "rationale": "impact", "key_facts": []},
    ]})
    out = curation.synthesize_brief("phishing", [{"title": "CISA", "body": "facts"}], SETTINGS,
                                    client=FakeClient([payload]))
    assert out["grounded"] is True
    assert len(out["angles"]) == 4
    assert out["angles"][0]["title"] == "the hover test"


def test_synthesize_falls_back_on_garbage():
    out = curation.synthesize_brief("phishing", [], SETTINGS, client=FakeClient(["not json"]))
    assert out["grounded"] is False
    assert len(out["angles"]) >= 3


def test_synthesize_falls_back_on_too_few_angles():
    payload = json.dumps({"synthesis": "s", "grounded": True, "angles": [{"title": "only one"}]})
    out = curation.synthesize_brief("x", [], SETTINGS, client=FakeClient([payload]))
    assert len(out["angles"]) >= 3  # fallback kicked in


def test_review_scores_and_feedback():
    payload = json.dumps({"score": 91, "feedback": ["tighten concept 2"]})
    v = content.review(VARIANTS, "water", SETTINGS, client=FakeClient([payload]))
    assert v["score"] == 91
    assert v["feedback"] == ["tighten concept 2"]


def test_review_none_on_failure():
    assert content.review(VARIANTS, "water", SETTINGS, client=FakeClient(["nope"])) is None


def test_generate_reviewed_accepts_high_score():
    good = json.dumps({"variants": VARIANTS})
    review = json.dumps({"score": 95, "feedback": []})
    client = FakeClient([good, review])
    variants, verdict = content.generate_reviewed("water", SETTINGS, client=client)
    assert verdict["score"] == 95
    assert client.chat.completions.calls == 2  # one generate, one review, no rework


def test_generate_reviewed_reworks_then_returns_best():
    good = json.dumps({"variants": VARIANTS})
    low = json.dumps({"score": 70, "feedback": ["too generic"]})
    high = json.dumps({"score": 90, "feedback": []})
    # gen, review(70) -> rework gen, review(90)
    client = FakeClient([good, low, good, high])
    variants, verdict = content.generate_reviewed("water", SETTINGS, max_rounds=2, client=client)
    assert verdict["score"] == 90
    assert client.chat.completions.calls == 4

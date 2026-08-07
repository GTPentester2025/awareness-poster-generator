import json

from app import director, recipes
from app.config import Settings
from pathlib import Path

SETTINGS = Settings(
    openai_api_key="sk-test", openai_text_model="gpt-4o-mini",
    canva_client_id="c", canva_client_secret="s",
    base_url="http://127.0.0.1:8000", out_dir=Path("out"), token_path=Path("token.json"),
)


class FakeCompletions:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    def create(self, **kwargs):
        text = self.payloads.pop(0)
        msg = type("M", (), {"content": text})
        return type("R", (), {"choices": [type("C", (), {"message": msg})]})


class FakeClient:
    def __init__(self, payloads):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(payloads)


VARIANTS = [
    {"angle": "the 3-second hover test", "headline": "Hover Before You Click", "subheadline": "s"},
    {"angle": "what a real bank never does", "headline": "Banks Don't Ask That", "subheadline": "s"},
    {"angle": "the Friday 5pm attack", "headline": "Beware the Friday Rush", "subheadline": "s"},
]


def test_brainstorm_returns_three_distinct():
    payload = json.dumps({"candidates": ["a", "b", "c", "d"],
                          "chosen": ["the hover test", "bank check", "friday rush"]})
    angles = director.brainstorm_angles("phishing", SETTINGS, client=FakeClient([payload]))
    assert len(angles) == 3
    assert len(set(a.lower() for a in angles)) == 3


def test_brainstorm_falls_back_on_garbage():
    angles = director.brainstorm_angles("phishing", SETTINGS, client=FakeClient(["not json"]))
    assert len(angles) == 3  # generic fallback


def test_select_recipes_distinct_archetypes():
    pool = recipes.shortlist([], k=12, seed=1)
    # choose three real ids with distinct archetypes to instruct the fake agent
    chosen, used = [], set()
    for r in pool:
        if r["archetype"] not in used:
            used.add(r["archetype"])
            chosen.append(r["id"])
        if len(chosen) == 3:
            break
    payload = json.dumps({"selections": [
        {"concept_index": 0, "recipe_id": chosen[0], "image_subject": "a lock"},
        {"concept_index": 1, "recipe_id": chosen[1], "image_subject": "an inbox"},
        {"concept_index": 2, "recipe_id": chosen[2], "image_subject": "a clock"},
    ]})
    picks = director.select_recipes(VARIANTS, pool, SETTINGS, client=FakeClient([payload]))
    assert len(picks) == 3
    archs = [p["recipe"]["archetype"] for p in picks]
    assert len(set(archs)) == 3
    assert picks[0]["image_subject"] == "a lock"


def test_select_recipes_fallback_on_bad_json():
    pool = recipes.shortlist([], k=12, seed=2)
    picks = director.select_recipes(VARIANTS, pool, SETTINGS, client=FakeClient(["nope"]))
    assert len(picks) == 3
    archs = [p["recipe"]["archetype"] for p in picks]
    assert len(set(archs)) == 3  # fallback still spreads archetypes

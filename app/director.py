"""Creative + art direction agents.

creative_director: brainstorms fresh, TOPIC-SPECIFIC angles (human-like — not a
fixed enum) and picks the three most distinct, so every run explores different
framings.

art_director: given the three written concepts and a diverse shortlist from the
recipe library, picks the best-fit recipe per concept (distinct archetypes) and
writes a topic-specific image subject for each. This is the "choose the best
template" step."""
import json

from app.config import Settings

ANGLE_PROMPT = """You are a creative director brainstorming poster angles for an awareness
campaign on this topic:
"{topic}"

Invent {n} genuinely different ANGLES a great designer might take — specific and
human, not generic buckets. Examples of the *kind* of specificity wanted (do not
reuse these): "the 3-second hover test", "what a real bank email never does",
"the myth your uncle still believes", "one habit that halves the risk",
"what it costs a family", "spot it before you click".

Then choose the THREE most distinct from your list.

Return ONLY JSON: {{"candidates": ["..."], "chosen": ["angle 1", "angle 2", "angle 3"]}}
Each chosen angle is a short phrase (max 60 chars) describing the framing."""

ART_PROMPT = """You are an art director choosing a visual template for each of three poster
concepts. You are given the concepts and a SHORTLIST of design recipes (each with
an id, layout, mood, palette, fonts, treatment, image medium).

Pick the single best recipe id for EACH concept so that:
- the visual mood fits that concept's angle and emotional tone,
- the three chosen recipes use THREE DIFFERENT layouts (no repeats),
- together they feel like a varied, expert set — not three of the same look.

Also write a short, vivid IMAGE SUBJECT for each concept: what the background
artwork should depict (topic-relevant, concrete, NO text in the image).

Return ONLY JSON:
{{"selections": [
  {{"concept_index": 0, "recipe_id": <id from shortlist>, "image_subject": "..."}},
  {{"concept_index": 1, "recipe_id": <id>, "image_subject": "..."}},
  {{"concept_index": 2, "recipe_id": <id>, "image_subject": "..."}}
]}}"""


def _chat_json(settings: Settings, prompt: str, client) -> dict:
    resp = client.chat.completions.create(
        model=settings.openai_text_model,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(resp.choices[0].message.content)


def brainstorm_angles(topic: str, settings: Settings, n: int = 7, client=None) -> list[str]:
    """Fresh topic-specific angles. Falls back to a generic spread on failure."""
    fallback = ["what most people get wrong", "how to protect yourself",
                "the real-world impact", "warning signs to watch",
                "the numbers that matter", "simple steps that help"]
    try:
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
        data = _chat_json(settings, ANGLE_PROMPT.format(topic=topic, n=max(n, 5)), client)
        chosen = data.get("chosen")
        angles = [a.strip()[:60] for a in chosen if isinstance(a, str) and a.strip()] \
            if isinstance(chosen, list) else []
        # dedupe, need 3 distinct
        seen, out = set(), []
        for a in angles:
            key = a.lower()
            if key not in seen:
                seen.add(key)
                out.append(a)
        if len(out) >= 3:
            return out[:3]
    except Exception:
        pass
    import random
    return random.sample(fallback, 3)


def select_recipes(variants: list[dict], shortlist_recipes: list[dict],
                   settings: Settings, client=None) -> list[dict]:
    """Return one selection dict per concept: {recipe, image_subject}. Falls
    back to spreading distinct shortlist recipes if the agent misbehaves."""
    from app import recipes as recipe_lib
    by_id = {r["id"]: r for r in shortlist_recipes}

    def _fallback():
        picks, used_arch = [], set()
        pool = list(shortlist_recipes)
        for v in variants:
            choice = next((r for r in pool if r["archetype"] not in used_arch), pool[0] if pool else None)
            if choice is None:
                choice = shortlist_recipes[0]
            used_arch.add(choice["archetype"])
            if choice in pool:
                pool.remove(choice)
            picks.append({"recipe": choice, "image_subject": ""})
        return picks

    try:
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
        shortlist_view = [recipe_lib.summarize(r) for r in shortlist_recipes]
        payload = {
            "concepts": [{"index": i, "angle": v.get("angle"), "headline": v.get("headline"),
                          "subheadline": v.get("subheadline")} for i, v in enumerate(variants)],
            "shortlist": shortlist_view,
        }
        prompt = ART_PROMPT + "\n\nDATA:\n" + json.dumps(payload)
        data = _chat_json(settings, prompt, client)
        sels = data.get("selections")
        if not isinstance(sels, list):
            return _fallback()
        out: dict[int, dict] = {}
        used_arch: set[str] = set()
        for sel in sels:
            idx = sel.get("concept_index")
            rid = sel.get("recipe_id")
            recipe = by_id.get(rid) or recipe_lib.get(rid) if isinstance(rid, int) else None
            if not isinstance(idx, int) or not 0 <= idx < len(variants) or recipe is None:
                continue
            subject = sel.get("image_subject")
            subject = subject.strip()[:200] if isinstance(subject, str) else ""
            out[idx] = {"recipe": recipe, "image_subject": subject, "_arch": recipe["archetype"]}
        # ensure every concept has a distinct-archetype pick
        picks = []
        for i, v in enumerate(variants):
            chosen = out.get(i)
            if chosen is None or chosen["_arch"] in used_arch:
                alt = next((r for r in shortlist_recipes if r["archetype"] not in used_arch), None)
                if alt is not None:
                    chosen = {"recipe": alt, "image_subject": (chosen or {}).get("image_subject", "")}
            if chosen is None:
                chosen = {"recipe": shortlist_recipes[i % len(shortlist_recipes)], "image_subject": ""}
            used_arch.add(chosen["recipe"]["archetype"])
            picks.append({"recipe": chosen["recipe"], "image_subject": chosen.get("image_subject", "")})
        return picks
    except Exception:
        return _fallback()

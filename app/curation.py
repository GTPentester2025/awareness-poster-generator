"""Agentic content curation (ported approach from the reference app).

synthesize_brief: turns retrieved knowledge + live web research into a compact
research brief and 3-5 GROUNDED angles (each with a rationale tied to the
material) — so poster copy stays on-topic and non-generic, instead of being
brainstormed from thin air.

The topic is authoritative and never substituted. Degrades gracefully: with
little/no grounding it still returns angles but marks grounded=False."""
import json

from app.config import Settings

BRIEF_PROMPT = """You are a research editor preparing an awareness-poster brief.
TOPIC (authoritative — never change it): "{topic}"

{material}

Produce a tight brief and distinct angles GROUNDED in the material above (or, if
material is thin, in well-established facts — mark grounded=false then).

Return ONLY JSON:
{
  "synthesis": "4-6 sentence factual synthesis of what matters about this topic",
  "grounded": true|false,
  "angles": [
    {"title": "<short distinct framing, max 60 chars>",
      "rationale": "<one line: why this angle matters / what it teaches>",
      "key_facts": ["<1-3 concrete facts this angle would use>"]}
  ]
}
Give {n} angles, each genuinely different in framing (not rewordings). Angles
should be specific and human, e.g. 'what a real bank email never does', not
generic buckets like 'precautions'."""


def _fallback(topic: str) -> dict:
    return {
        "synthesis": f"General awareness guidance about {topic}.",
        "grounded": False,
        "angles": [
            {"title": "what most people get wrong", "rationale": "corrects a common misconception", "key_facts": []},
            {"title": "the warning signs", "rationale": "helps people spot the risk early", "key_facts": []},
            {"title": "simple steps that help", "rationale": "gives concrete protective actions", "key_facts": []},
            {"title": "why it matters to you", "rationale": "makes the impact personal", "key_facts": []},
        ],
    }


def synthesize_brief(topic: str, docs: list[dict], settings: Settings, n_angles: int = 5,
                     client=None) -> dict:
    """Return {synthesis, grounded, angles:[{title,rationale,key_facts}]}.
    n_angles: how many distinct angles to brainstorm (for the "more angles" UI)."""
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)

    if docs:
        material = "MATERIAL (cite these facts, prefer them over guesses):\n" + "\n\n".join(
            f"### {d.get('title','source')}\n{d.get('body','')}" for d in docs)
    else:
        material = "MATERIAL: none retrieved — use only well-established facts and set grounded=false."

    prompt = BRIEF_PROMPT.replace("{topic}", topic).replace("{material}", material).replace("{n}", str(max(3, n_angles)))
    try:
        resp = client.chat.completions.create(
            model=settings.openai_text_model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(resp.choices[0].message.content)
        angles = data.get("angles")
        if not isinstance(angles, list) or len(angles) < 3:
            return _fallback(topic)
        clean = []
        for a in angles:
            if isinstance(a, dict) and isinstance(a.get("title"), str) and a["title"].strip():
                clean.append({
                    "title": a["title"].strip()[:60],
                    "rationale": (a.get("rationale") or "").strip()[:160],
                    "key_facts": [f.strip()[:160] for f in a.get("key_facts", [])
                                  if isinstance(f, str) and f.strip()][:3],
                })
        if len(clean) < 3:
            return _fallback(topic)
        synthesis = data.get("synthesis")
        return {
            "synthesis": synthesis.strip()[:1200] if isinstance(synthesis, str) else "",
            "grounded": bool(data.get("grounded", bool(docs))),
            "angles": clean[:5],
        }
    except Exception:
        return _fallback(topic)

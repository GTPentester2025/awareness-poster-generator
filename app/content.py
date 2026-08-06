"""Poster copywriting: one call produces three DISTINCT content variants for a
topic — different angles (precautions, red flags, impact, myths vs facts,
stats, checklist, steps) and varied point counts (3-6). When knowledge-base
snippets are supplied the facts must come from them and cite the source."""
import json

from app.config import Settings

ANGLES = {"precautions", "red_flags", "impact", "myths_vs_facts", "stats", "checklist", "steps"}
MIN_POINTS, MAX_POINTS = 3, 6

SYSTEM_PROMPT = """You are an expert public-awareness copywriter. For the given topic,
write THREE clearly different poster concepts. Each takes a different ANGLE:
choose from: precautions, red_flags, impact, myths_vs_facts, stats, checklist, steps.
Vary the number of points between concepts (3 to 6 points each) — do NOT give
every concept the same count.

Return ONLY JSON:
{
  "variants": [
    {
      "angle": "<one of the angles>",
      "headline": "punchy title, max 60 chars",
      "subheadline": "supporting line, max 120 chars",
      "points": [
        {"stat": "<very short label: a number, %, or 1-3 word hook, max 12 chars>",
         "text": "<the point itself, one sentence, max 140 chars>"}
      ],
      "cta": "call to action, max 80 chars",
      "sources": ["<short source names you actually used, e.g. 'NIST CSF 2.0', 'GDPR Art. 33'>"]
    },
    ... exactly 3 variants ...
  ]
}

Rules:
- The three variants must differ in angle, structure, and tone — not rewordings.
- Facts must be accurate. If REFERENCE MATERIAL is provided below, prefer its
  facts verbatim-ish and cite those sources in "sources". Never invent statistics:
  without reference material use only well-established facts and leave "sources" empty
  rather than fabricating citations.
- "stat" labels must be punchy: "72h", "1 in 4", "€20M", "Step 1", "Myth".
- For myths_vs_facts, alternate points between a myth and the correcting fact."""


def _txt(value, max_len, name):
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise ValueError(f"bad {name}")
    return value


def validate_variant(v: dict) -> dict:
    if not isinstance(v, dict):
        raise ValueError("variant must be an object")
    if v.get("angle") not in ANGLES:
        v["angle"] = "precautions"
    _txt(v.get("headline"), 60, "headline")
    _txt(v.get("subheadline"), 120, "subheadline")
    _txt(v.get("cta"), 80, "cta")
    points = v.get("points")
    if not isinstance(points, list) or not MIN_POINTS <= len(points) <= MAX_POINTS:
        raise ValueError(f"points must be a list of {MIN_POINTS}-{MAX_POINTS}")
    clean_points = []
    for p in points:
        if not isinstance(p, dict):
            raise ValueError("point must be an object")
        text = _txt(p.get("text"), 140, "point.text")
        stat = p.get("stat")
        stat = stat.strip()[:12] if isinstance(stat, str) and stat.strip() else str(len(clean_points) + 1)
        clean_points.append({"stat": stat, "text": text})
    v["points"] = clean_points
    sources = v.get("sources")
    v["sources"] = [s.strip()[:60] for s in sources if isinstance(s, str) and s.strip()][:3] \
        if isinstance(sources, list) else []
    return v


def validate_content(data: dict) -> dict:
    variants = data.get("variants") if isinstance(data, dict) else None
    if not isinstance(variants, list) or len(variants) != 3:
        raise ValueError("need exactly 3 variants")
    data["variants"] = [validate_variant(v) for v in variants]
    angles = [v["angle"] for v in data["variants"]]
    if len(set(angles)) < 2:
        raise ValueError("variants must use different angles")
    return data


def generate(topic: str, settings: Settings, knowledge_docs: list[dict] | None = None,
             client=None) -> list[dict]:
    """Returns 3 validated content variants. Retries once, then raises ValueError."""
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)

    user = f"Awareness poster topic: {topic}"
    if knowledge_docs:
        ref = "\n\n".join(f"### {d['title']}\n{d['body']}" for d in knowledge_docs)
        user += f"\n\nREFERENCE MATERIAL (use these facts, cite these sources):\n{ref}"

    last_err = None
    for _ in range(2):
        resp = client.chat.completions.create(
            model=settings.openai_text_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
        )
        try:
            return validate_content(json.loads(resp.choices[0].message.content))["variants"]
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    raise ValueError(f"content generation failed: {last_err}")


def to_legacy(variant: dict) -> dict:
    """Adapter for builder.fallback_build, which expects the original schema."""
    return {
        "headline": variant["headline"],
        "subheadline": variant["subheadline"],
        "facts": [p["text"] for p in variant["points"]][:5],
        "cta": variant["cta"],
        "palette": {"bg": "#12314A", "accent": "#3EC1D3", "text": "#FFFFFF"},
    }

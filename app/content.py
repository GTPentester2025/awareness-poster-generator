"""Poster copywriting: one call produces three DISTINCT content variants for a
topic — different angles (precautions, red flags, impact, myths vs facts,
stats, checklist, steps) and varied point counts (3-6). When knowledge-base
snippets are supplied the facts must come from them and cite the source."""
import json

from app.config import Settings

# Legacy angle vocabulary — kept only as a fallback. The creative director
# (app.director) now brainstorms fresh, topic-specific angles per run, so the
# angle field is free-form text and no longer constrained to this set.
ANGLES = {"precautions", "red_flags", "impact", "myths_vs_facts", "stats", "checklist", "steps"}
MIN_POINTS, MAX_POINTS = 3, 6

SYSTEM_PROMPT = """You are an expert public-awareness copywriter. For the given topic,
write {count} clearly different poster concepts. Use EXACTLY the assigned angles
(one per concept, in order). Vary the number of points between concepts (3 to 6
points each) — do NOT give every concept the same count.

PRECISION RULES (critical — vague copy is rejected):
- Every point must be CONCRETE and specific. Prefer a real number, percentage,
  timeframe, or a named concrete action. No filler adjectives ("very", "important",
  "crucial"), no empty motivation ("stay safe", "be aware") as a point.
- Facts must be accurate and, when reference material is given, taken from it.
  Never invent statistics. If you have no number for a point, make it a specific
  ACTION ("Turn on MFA in Settings > Security"), not a platitude.
- Headlines are punchy and specific (name the risk or the number), max 8 words.
- Each point's text is one tight sentence, no throat-clearing.

Return ONLY JSON:
{
  "variants": [
    {
      "angle": "<one of the angles>",
      "headline": "punchy title, max 60 chars",
      "subheadline": "supporting line, max 120 chars",
      "points": [
        {"stat": "<a PUNCHY badge, max 8 chars: prefer a number/percent/figure like '61%', '16,500', '$932M', '72h', '1 in 3'. If the point has no number, use a 1-word tag like 'Myth', 'Fact', 'Tip'. NEVER a phrase.>",
         "text": "<the point itself, one sentence, max 140 chars>"}
      ],
      "cta": "call to action, max 80 chars",
      "sources": ["<short source names you actually used, e.g. 'NIST CSF 2.0', 'GDPR Art. 33'>"]
    },
    ... exactly {count} variants ...
  ]
}

Rules:
- The variants must differ in angle, structure, and tone — not rewordings.
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
    angle = v.get("angle")
    v["angle"] = angle.strip()[:60] if isinstance(angle, str) and angle.strip() else "awareness"
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
        stat = stat.strip()[:10] if isinstance(stat, str) and stat.strip() else str(len(clean_points) + 1)
        clean_points.append({"stat": stat, "text": text})
    v["points"] = clean_points
    sources = v.get("sources")
    v["sources"] = [s.strip()[:60] for s in sources if isinstance(s, str) and s.strip()][:3] \
        if isinstance(sources, list) else []
    return v


def validate_content(data: dict, count: int = 3) -> dict:
    variants = data.get("variants") if isinstance(data, dict) else None
    if not isinstance(variants, list) or len(variants) != count:
        raise ValueError(f"need exactly {count} variants")
    data["variants"] = [validate_variant(v) for v in variants]
    angles = [v["angle"].lower() for v in data["variants"]]
    if count >= 2 and len(set(angles)) < 2:
        raise ValueError("variants must use different angles")
    return data


def generate(topic: str, settings: Settings, knowledge_docs: list[dict] | None = None,
             angles: list[str] | None = None, brand_block: str = "", brief: str = "",
             feedback: list[str] | None = None, count: int = 3, client=None) -> list[dict]:
    """Returns `count` validated content variants. Retries once, then raises.
    `angles`: assigned angles (grounded, from curation.synthesize_brief).
    `brand_block`: serialized brand kit steering tone. `brief`: research
    synthesis to ground copy. `feedback`: reviewer notes from a prior draft."""
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)

    system = SYSTEM_PROMPT.replace("{count}", str(count))
    user = _build_user_prompt(topic, angles, brand_block, knowledge_docs, brief, feedback, count)

    last_err = None
    for _ in range(2):
        resp = client.chat.completions.create(
            model=settings.openai_text_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        try:
            return validate_content(json.loads(resp.choices[0].message.content), count)["variants"]
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    raise ValueError(f"content generation failed: {last_err}")


def _build_user_prompt(topic, angles, brand_block, knowledge_docs, brief, feedback, count=3) -> str:
    user = f"Awareness poster topic: {topic}"
    if brief:
        user += f"\n\nRESEARCH BRIEF (ground the copy in this):\n{brief}"
    if angles:
        user += (f"\n\nUse EXACTLY these {count} angles, one per concept in order — keep each "
                 "concept's framing true to its angle:\n"
                 + "\n".join(f"{i+1}. {a}" for i, a in enumerate(angles[:count])))
    if brand_block:
        user += f"\n\nBRAND (match this voice; mention the org naturally in the CTA if it fits):\n{brand_block}"
    if knowledge_docs:
        ref = "\n\n".join(f"### {d['title']}\n{d['body']}" for d in knowledge_docs)
        user += f"\n\nREFERENCE MATERIAL (use these facts, cite these sources):\n{ref}"
    if feedback:
        user += ("\n\nA reviewer rejected the previous draft. Fix ALL of these, keeping what worked:\n- "
                 + "\n- ".join(feedback))
    return user


REVIEW_PROMPT = """You are a strict awareness-poster copy reviewer. Score the three concepts
for a poster on topic "{topic}".

Judge: on-topic relevance, factual soundness, distinctness of the three angles,
punchiness, and whether each point is concrete (not vague filler). Be harsh.

Return ONLY JSON:
{{"score": <0-100 overall>,
  "feedback": ["<each specific, actionable fix — name the concept and what is wrong>"]}}
An accepted draft (score >= 88) may still list minor feedback."""

PASS_SCORE = 88


def review(variants: list[dict], topic: str, settings: Settings, client=None) -> dict:
    """Independent reviewer: score 0-100 + specific feedback. None on failure."""
    try:
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
        payload = json.dumps([{"angle": v["angle"], "headline": v["headline"],
                               "subheadline": v["subheadline"],
                               "points": [p["text"] for p in v["points"]], "cta": v["cta"]}
                              for v in variants])
        resp = client.chat.completions.create(
            model=settings.openai_text_model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": REVIEW_PROMPT.format(topic=topic) + "\n\nDRAFT:\n" + payload}],
        )
        data = json.loads(resp.choices[0].message.content)
        score = data.get("score")
        if not isinstance(score, (int, float)):
            return None
        return {"score": max(0, min(100, int(score))),
                "feedback": [f for f in data.get("feedback", []) if isinstance(f, str)][:6]}
    except Exception:
        return None


def generate_reviewed(topic: str, settings: Settings, knowledge_docs=None, angles=None,
                      brand_block="", brief="", count: int = 3, max_rounds: int = 3, client=None):
    """Generate → review → rework with full feedback history until score >=
    PASS_SCORE or rounds exhausted. Returns (variants, review_dict|None)."""
    history: list[str] = []
    best = None
    best_review = None
    for _ in range(max_rounds):
        variants = generate(topic, settings, knowledge_docs=knowledge_docs, angles=angles,
                            brand_block=brand_block, brief=brief, count=count,
                            feedback=history or None, client=client)
        verdict = review(variants, topic, settings, client=client)
        if verdict is None:
            return variants, None
        if best_review is None or verdict["score"] > best_review["score"]:
            best, best_review = variants, verdict
        if verdict["score"] >= PASS_SCORE or not verdict["feedback"]:
            return variants, verdict
        history = verdict["feedback"]  # full feedback re-enters the next draft
    return best, best_review


def to_legacy(variant: dict) -> dict:
    """Adapter for builder.fallback_build, which expects the original schema."""
    return {
        "headline": variant["headline"],
        "subheadline": variant["subheadline"],
        "facts": [p["text"] for p in variant["points"]][:5],
        "cta": variant["cta"],
        "palette": {"bg": "#12314A", "accent": "#3EC1D3", "text": "#FFFFFF"},
    }

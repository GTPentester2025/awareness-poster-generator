import json
import re

from app.config import Settings

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

SYSTEM_PROMPT = """You design awareness posters. Given a topic, return ONLY a JSON object:
{
  "headline": "punchy title, max 60 chars",
  "subheadline": "supporting line, max 120 chars",
  "facts": ["3 to 5 short, true, striking facts or tips"],
  "cta": "call to action, max 80 chars",
  "palette": {"bg": "#RRGGBB", "accent": "#RRGGBB", "text": "#RRGGBB"},
  "image_prompt": "prompt for a background illustration; flat/minimal style, muted, leaves clear space for overlaid text, no words or letters in the image"
}
Palette must have strong contrast between text and bg. Facts must be accurate and non-graphic."""


def validate_content(data: dict) -> dict:
    def txt(key, max_len):
        v = data.get(key)
        if not isinstance(v, str) or not v.strip() or len(v) > max_len:
            raise ValueError(f"bad {key}")
        return v

    txt("headline", 60)
    txt("subheadline", 120)
    txt("cta", 80)
    txt("image_prompt", 1000)
    facts = data.get("facts")
    if not isinstance(facts, list) or not 3 <= len(facts) <= 5:
        raise ValueError("facts must be a list of 3-5 items")
    if any(not isinstance(f, str) or not f.strip() for f in facts):
        raise ValueError("facts must be non-empty strings")
    palette = data.get("palette")
    if not isinstance(palette, dict):
        raise ValueError("palette missing")
    for key in ("bg", "accent", "text"):
        if not isinstance(palette.get(key), str) or not HEX.match(palette[key]):
            raise ValueError(f"palette.{key} must be #RRGGBB")
    return data


def generate(topic: str, settings: Settings, client=None) -> dict:
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
    last_err = None
    for _ in range(2):
        resp = client.chat.completions.create(
            model=settings.openai_text_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Awareness poster topic: {topic}"},
            ],
        )
        try:
            return validate_content(json.loads(resp.choices[0].message.content))
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    raise ValueError(f"content generation failed: {last_err}")

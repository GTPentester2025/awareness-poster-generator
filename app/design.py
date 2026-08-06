"""AI-as-art-director: the LLM chooses a composition archetype and style
tokens (palette, fonts, background/card treatment, a stat per fact). It does
NOT place pixels — the renderer in builder.py owns all geometry, so layouts
are always clean, filled, and contain real card containers. A lenient
validator coerces bad values; it raises ValueError only when unusable, so the
caller can fall back to builder.fallback_build."""
import json
import re

from app.config import Settings

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

ARCHETYPES = {"hero_top", "sidebar", "banner_header", "centered_feature",
              "big_number", "steps_path", "split_band"}
BACKGROUND_STYLES = {"image", "gradient", "solid"}
CARD_STYLES = {"filled", "outline", "soft_shadow"}
HEADER_STYLES = {"block", "underline", "badge"}

ALLOWED_FONTS = {
    "Open Sans", "Montserrat", "Poppins", "Lato", "Roboto", "Playfair Display",
    "Merriweather", "Oswald", "Raleway", "Anton", "Bebas Neue", "Archivo",
    "Nunito", "Work Sans", "Georgia", "Arial", "League Spartan", "Abril Fatface",
    "Lora", "PT Sans", "Quicksand",
}
DEFAULT_HEADING = "Montserrat"
DEFAULT_BODY = "Open Sans"

PALETTE_KEYS = ("bg", "surface", "accent", "text", "muted")
PALETTE_DEFAULTS = {"surface": "#FFFFFF", "muted": "#9AA5B1"}


def _coerce_font(name, default) -> str:
    return name if name in ALLOWED_FONTS else default


def validate_spec(spec: dict) -> dict:
    """Coerce a raw StyleSpec into a safe, renderable one. Raises ValueError
    only when unrecoverable (bad core palette, or no facts to show)."""
    if not isinstance(spec, dict):
        raise ValueError("spec must be an object")

    spec["archetype"] = spec.get("archetype") if spec.get("archetype") in ARCHETYPES else "hero_top"

    palette = spec.get("palette")
    if not isinstance(palette, dict):
        raise ValueError("palette missing")
    for key in ("bg", "accent", "text"):
        if not isinstance(palette.get(key), str) or not HEX.match(str(palette.get(key))):
            raise ValueError(f"palette.{key} must be #RRGGBB")
    for key, default in PALETTE_DEFAULTS.items():
        if not isinstance(palette.get(key), str) or not HEX.match(str(palette.get(key))):
            palette[key] = default
    spec["palette"] = {k: palette[k] for k in PALETTE_KEYS}

    fonts = spec.get("fonts") if isinstance(spec.get("fonts"), dict) else {}
    spec["fonts"] = {
        "heading": _coerce_font(fonts.get("heading"), DEFAULT_HEADING),
        "body": _coerce_font(fonts.get("body"), DEFAULT_BODY),
    }

    spec["background_style"] = spec.get("background_style") if spec.get("background_style") in BACKGROUND_STYLES else "image"
    spec["card_style"] = spec.get("card_style") if spec.get("card_style") in CARD_STYLES else "filled"
    spec["header_style"] = spec.get("header_style") if spec.get("header_style") in HEADER_STYLES else "block"
    spec["accent_shapes"] = bool(spec.get("accent_shapes", True))

    ip = spec.get("image_prompt")
    spec["image_prompt"] = ip if isinstance(ip, str) and ip.strip() else "abstract minimal background, soft shapes, muted tones, ample negative space, no text"

    stats = spec.get("fact_stats")
    if not isinstance(stats, list):
        stats = []
    spec["fact_stats"] = [s if isinstance(s, str) else "" for s in stats]
    return spec


def validate_directions(data: dict) -> list[dict]:
    """Validate a 3-direction response and force archetype diversity: any
    duplicate archetype is reassigned from the unused pool so the three
    options never look alike."""
    directions = data.get("directions") if isinstance(data, dict) else None
    if not isinstance(directions, list) or len(directions) != 3:
        raise ValueError("need exactly 3 directions")
    specs = [validate_spec(d) for d in directions]
    used: list[str] = []
    unused = [a for a in sorted(ARCHETYPES)]
    for spec in specs:
        if spec["archetype"] in unused:
            unused.remove(spec["archetype"])
    for spec in specs:
        if spec["archetype"] in used:
            spec["archetype"] = unused.pop(0)
        used.append(spec["archetype"])
    return specs


SYSTEM_PROMPT = """You are an award-winning art director. You receive THREE poster
concepts for one awareness topic. Give each concept its own DISTINCT visual
direction — like three different human designers would. You do NOT position
elements — a layout engine owns geometry. Your job: composition choice + rich style.

Return ONLY JSON:
{
  "directions": [
    {
      "archetype": "hero_top" | "sidebar" | "banner_header" | "centered_feature" | "big_number" | "steps_path" | "split_band",
      "palette": {"bg":"#RRGGBB","surface":"#RRGGBB","accent":"#RRGGBB","text":"#RRGGBB","muted":"#RRGGBB"},
      "fonts": {"heading":"<allowed font>","body":"<allowed font>"},
      "background_style": "image" | "gradient" | "solid",
      "card_style": "filled" | "outline" | "soft_shadow",
      "header_style": "block" | "underline" | "badge",
      "accent_shapes": true | false,
      "image_prompt": "<vivid prompt for background/hero art matching THIS concept's mood; flat illustration or photographic; NO text or letters in the image; calm areas for overlaid text>"
    },
    ... exactly 3, one per concept, in order ...
  ]
}

Hard rules:
- The three directions MUST use three different archetypes, different palettes
  (not shades of the same hue), and different heading fonts.
- At least TWO of the three directions must use background_style "image" —
  posters without imagery look flat. Use "solid"/"gradient" for at most one
  deliberately minimal concept.
- Match archetype to angle: steps/checklist → steps_path; stats-led → big_number;
  emotional/impact → hero_top or split_band with image; informational → banner_header/sidebar.
- 'surface' is the card color — must contrast with the body text drawn on it.
- Expressive heading fonts: Anton, Bebas Neue, Playfair Display, Abril Fatface, Oswald,
  League Spartan. Readable body: Open Sans, Lato, Roboto, Work Sans, Nunito.
- Allowed fonts ONLY: Open Sans, Montserrat, Poppins, Lato, Roboto, Playfair Display,
  Merriweather, Oswald, Raleway, Anton, Bebas Neue, Archivo, Nunito, Work Sans, Georgia,
  Arial, League Spartan, Abril Fatface, Lora, PT Sans, Quicksand."""


def generate_directions(variants: list[dict], orientation: str, settings: Settings,
                        client=None) -> list[dict]:
    """Art-direct all three content variants together → three validated,
    archetype-distinct StyleSpecs (same order as variants). Retries once."""
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)

    user = json.dumps({
        "orientation": orientation,
        "concepts": [
            {
                "angle": v.get("angle"),
                "headline": v.get("headline"),
                "subheadline": v.get("subheadline"),
                "points": v.get("points"),
                "cta": v.get("cta"),
            } for v in variants
        ],
    })

    last_err = None
    for _ in range(2):
        resp = client.chat.completions.create(
            model=settings.openai_text_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Art-direct these 3 {orientation} poster concepts:\n{user}"},
            ],
        )
        try:
            return validate_directions(json.loads(resp.choices[0].message.content))
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    raise ValueError(f"style direction failed: {last_err}")

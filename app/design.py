"""AI-as-designer: turn poster copy into a free-form LayoutPlan the renderer
can draw. No fixed templates — the LLM composes each layout. A lenient
validator coerces out-of-range values so a plan almost always renders; it
raises ValueError only when the plan is unusable (then the caller falls back
to the safe auto-layout in builder.fallback_build)."""
import json
import re

from app.config import Settings

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Fonts Canva recognizes by name, so imported text keeps its typeface instead
# of being substituted. Unknown fonts are coerced to the defaults below.
ALLOWED_FONTS = {
    "Open Sans", "Montserrat", "Poppins", "Lato", "Roboto", "Playfair Display",
    "Merriweather", "Oswald", "Raleway", "Anton", "Bebas Neue", "Archivo",
    "Nunito", "Work Sans", "Georgia", "Arial", "League Spartan", "Abril Fatface",
    "Dancing Script", "Lora", "PT Sans", "Source Sans Pro", "Quicksand",
}
DEFAULT_HEADING = "Montserrat"
DEFAULT_BODY = "Open Sans"
BG_MODES = {"solid", "gradient", "image_full", "image_panel"}
SHAPES = {"rect", "ellipse", "line"}
ALIGNS = {"left", "center", "right"}


def _clamp(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _coerce_font(name) -> str:
    return name if name in ALLOWED_FONTS else DEFAULT_BODY


def validate_plan(plan: dict) -> dict:
    """Coerce a raw plan into a safe, renderable one. Raises ValueError only
    when unrecoverable (bad palette, or no usable text element)."""
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")

    palette = plan.get("palette")
    if not isinstance(palette, dict):
        raise ValueError("palette missing")
    for key in ("bg", "accent", "text"):
        if not isinstance(palette.get(key), str) or not HEX.match(palette[key]):
            raise ValueError(f"palette.{key} must be #RRGGBB")

    plan["font_heading"] = plan.get("font_heading") if plan.get("font_heading") in ALLOWED_FONTS else DEFAULT_HEADING
    plan["font_body"] = _coerce_font(plan.get("font_body"))

    bg = plan.get("background")
    if not isinstance(bg, dict) or bg.get("mode") not in BG_MODES:
        plan["background"] = {"mode": "solid"}

    raw_elements = plan.get("elements")
    if not isinstance(raw_elements, list):
        raise ValueError("elements must be a list")

    clean: list[dict] = []
    has_text = False
    for el in raw_elements:
        if not isinstance(el, dict):
            continue
        etype = el.get("type")
        x = _clamp(el.get("x"), 0.0, 1.0, 0.0)
        y = _clamp(el.get("y"), 0.0, 1.0, 0.0)
        w = _clamp(el.get("w"), 0.01, 1.0, 0.3)
        h = _clamp(el.get("h"), 0.01, 1.0, 0.1)
        if etype == "text":
            text = el.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            color = el.get("color") if isinstance(el.get("color"), str) and HEX.match(str(el.get("color"))) else palette["text"]
            clean.append({
                "type": "text", "text": text, "x": x, "y": y, "w": w, "h": h,
                "font": _coerce_font(el.get("font")),
                "size_pt": _clamp(el.get("size_pt"), 6, 160, 18),
                "weight": "bold" if el.get("weight") == "bold" else "normal",
                "align": el.get("align") if el.get("align") in ALIGNS else "left",
                "color": color,
            })
            has_text = True
        elif etype == "shape":
            color = el.get("color") if isinstance(el.get("color"), str) and HEX.match(str(el.get("color"))) else palette["accent"]
            clean.append({
                "type": "shape",
                "shape": el.get("shape") if el.get("shape") in SHAPES else "rect",
                "x": x, "y": y, "w": w, "h": h, "color": color,
                "opacity": _clamp(el.get("opacity"), 0.0, 1.0, 1.0),
            })
        elif etype == "image":
            clean.append({"type": "image", "x": x, "y": y, "w": w, "h": h,
                          "fit": "cover"})
        # unknown element types are dropped

    if not has_text:
        raise ValueError("plan has no usable text element")
    plan["elements"] = clean
    return plan


SYSTEM_PROMPT = """You are an award-winning graphic designer laying out an awareness poster.
Given the poster copy, the color palette, and the canvas orientation, invent a
distinctive composition. Do NOT reuse a generic template — vary the layout,
typography, and use of color each time as a real designer would.

Return ONLY a JSON object of this shape:
{
  "palette": {"bg": "#RRGGBB", "accent": "#RRGGBB", "text": "#RRGGBB"},
  "font_heading": "<one of the allowed fonts>",
  "font_body": "<one of the allowed fonts>",
  "background": {"mode": "solid" | "gradient" | "image_full" | "image_panel",
                 "panel": {"x":0-1,"y":0-1,"w":0-1,"h":0-1}   // only for image_panel
  },
  "elements": [
    {"type":"text","text":"<verbatim copy>","x":0-1,"y":0-1,"w":0-1,"h":0-1,
     "font":"<allowed font>","size_pt":<6-160>,"weight":"bold"|"normal",
     "align":"left"|"center"|"right","color":"#RRGGBB"},
    {"type":"shape","shape":"rect"|"ellipse"|"line","x":0-1,"y":0-1,"w":0-1,"h":0-1,
     "color":"#RRGGBB","opacity":0-1},
    {"type":"image","x":0-1,"y":0-1,"w":0-1,"h":0-1}
  ]
}

Rules:
- x,y,w,h are fractions of the canvas (0 = left/top, 1 = right/bottom).
- Include EVERY piece of copy: the headline, subheadline, every fact, and the CTA.
  Use the text VERBATIM — do not invent, paraphrase, or drop any fact.
- Keep text blocks from overlapping each other. Leave margins.
- Ensure strong contrast between each text color and whatever is behind it.
- Allowed fonts ONLY: Open Sans, Montserrat, Poppins, Lato, Roboto, Playfair Display,
  Merriweather, Oswald, Raleway, Anton, Bebas Neue, Archivo, Nunito, Work Sans,
  Georgia, Arial, League Spartan, Abril Fatface, Lora, PT Sans, Quicksand.
- If you place an "image" element or use an image background, it will hold the
  provided background artwork; keep important text off the busiest image areas.
- Draw order = array order (later elements sit on top)."""


def generate(content: dict, orientation: str, settings: Settings, client=None) -> dict:
    """Ask the LLM to design a layout for this copy. Returns a validated plan.
    Retries once on invalid output, then raises ValueError."""
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)

    user = json.dumps({
        "orientation": orientation,
        "palette": content.get("palette"),
        "copy": {
            "headline": content.get("headline"),
            "subheadline": content.get("subheadline"),
            "facts": content.get("facts"),
            "cta": content.get("cta"),
        },
    })

    last_err = None
    for _ in range(2):
        resp = client.chat.completions.create(
            model=settings.openai_text_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Design a {orientation} poster for this copy and palette:\n{user}"},
            ],
        )
        try:
            return validate_plan(json.loads(resp.choices[0].message.content))
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    raise ValueError(f"layout design failed: {last_err}")

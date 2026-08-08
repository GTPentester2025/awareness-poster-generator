"""Premium browser-render track. The LLM authors a full standalone HTML/CSS
poster from the concept copy + the recipe's design tokens; Chromium renders it
to a crisp PNG and a TEXT-LAYER PDF. The PDF imports into Canva with the text
still editable (verified). CSS-only visuals (gradients/shapes/type) so pages
render deterministically with no external image loads to stall on."""
import re
from pathlib import Path

from app.config import Settings

PAGE = {"portrait": ("210mm", "297mm"), "landscape": ("297mm", "210mm")}
# A4 at 96dpi, in CSS pixels — used to size the PNG preview viewport
PAGE_PX = {"portrait": (794, 1123), "landscape": (1123, 794)}

SYSTEM_PROMPT = """You are an elite poster designer who writes production HTML/CSS.
Produce ONE complete, standalone HTML document for a print poster.

HARD REQUIREMENTS:
- Page is EXACTLY {w} x {h}. Use `@page{{size:{size};margin:0}}` and set body to that
  size with `margin:0`.
- body MUST be `display:flex; flex-direction:column` and DISTRIBUTE content down the
  full page height (e.g. `justify-content:space-between` or generous flex gaps) so the
  poster fills the whole page — never leave a large empty band at the top or bottom.
- Load the two fonts from Google Fonts with a <link> to fonts.googleapis.com.
- ALL text must be real HTML text elements (h1/p/div) so it stays editable after
  import — NEVER render text inside SVG, canvas, or a background image.
- Use ONLY CSS for visuals: gradients, colors, borders, border-radius, box-shadow,
  blur, pseudo-element shapes. Do NOT reference any external image URL (no <img>,
  no url() images) — the page must render fully offline.
- Include EVERY piece of copy provided (headline, subheadline, each point with its
  stat, and the CTA). Strong hierarchy; the headline dominates; points read as cards
  or a list; the CTA is a clear button-like block.
- Fill the page tastefully — no huge empty gaps, no overflow, high contrast.
- Return ONLY the HTML document, starting with <!doctype html>. No markdown fences."""


def _tokens(spec: dict) -> str:
    p = spec["palette"]
    return (f"Palette: bg {p['bg']}, surface {p['surface']}, accent {p['accent']}, "
            f"text {p['text']}, muted {p['muted']}. "
            f"Heading font '{spec['fonts']['heading']}', body font '{spec['fonts']['body']}'. "
            f"Design vibe: {spec.get('layout', spec.get('archetype', 'modern'))}, "
            f"treatment {spec.get('treatment', 'clean')}.")


def build_html(variant: dict, spec: dict, orientation: str, settings: Settings, client=None) -> str:
    if orientation not in PAGE:
        raise ValueError("orientation must be portrait or landscape")
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
    w, h = PAGE[orientation]
    system = SYSTEM_PROMPT.format(w=w, h=h, size=("A4" if orientation == "portrait" else "A4 landscape"))
    copy = {
        "headline": variant["headline"], "subheadline": variant["subheadline"],
        "points": [{"stat": p["stat"], "text": p["text"]} for p in variant["points"]],
        "cta": variant["cta"], "sources": variant.get("sources", []),
    }
    import json
    user = f"Design tokens: {_tokens(spec)}\n\nCopy (use verbatim, include all):\n{json.dumps(copy, indent=2)}"
    resp = client.chat.completions.create(
        model=settings.openai_text_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    html = resp.choices[0].message.content.strip()
    m = re.search(r"<!doctype html>.*</html>", html, re.IGNORECASE | re.DOTALL)
    if m:
        html = m.group(0)
    if "<html" not in html.lower() or variant["headline"][:12].lower() not in html.lower():
        raise ValueError("HTML generation did not include the headline")
    return html


def render(html: str, orientation: str, out_dir: Path) -> tuple[Path, Path]:
    """Render HTML → (pdf_path, png_path). PDF keeps a real text layer."""
    import uuid
    from playwright.sync_api import sync_playwright
    w, h = PAGE[orientation]
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"web_{uuid.uuid4().hex[:8]}"
    pdf_path = out_dir / f"{stem}.pdf"
    png_path = out_dir / f"{stem}.png"
    vw, vh = PAGE_PX[orientation]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=2)
        page.set_content(html, wait_until="networkidle")
        page.pdf(path=str(pdf_path), width=w, height=h, print_background=True)
        page.screenshot(path=str(png_path))  # viewport-sized (A4), 2x for crisp preview
        browser.close()
    return pdf_path, png_path

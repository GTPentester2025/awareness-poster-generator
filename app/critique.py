"""Poster critique loop — the pipeline's eyes. Rasterizes the PPTX with
LibreOffice (if installed) and has a vision model score the poster like a
senior designer: legibility, overflow, contrast, composition, clutter.
Everything fails soft: no LibreOffice / no vision → None (no critique)."""
import base64
import json
import subprocess
from pathlib import Path

from app.config import Settings

SOFFICE_CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "soffice",
]
PASS_SCORE = 7

CRITIQUE_PROMPT = """You are a ruthless senior poster designer reviewing a rendered awareness poster.
Score it and list concrete defects. Judge ONLY what you see.

Return ONLY JSON:
{"score": <1-10 overall quality>,
 "defects": ["<each concrete visual problem: text cut off / overlapping elements /
   poor contrast with background / awkward empty space / cluttered area / misaligned items>"],
 "fix_hints": ["<short, actionable style instruction for the art director to fix the worst defects,
   e.g. 'use a darker scrim behind the headline', 'fewer points, larger cards'>"]}"""


def soffice_path() -> str | None:
    for cand in SOFFICE_CANDIDATES:
        if cand.endswith(".exe"):
            if Path(cand).exists():
                return cand
            continue
        try:
            result = subprocess.run([cand, "--version"], capture_output=True, timeout=20)
            if result.returncode == 0:
                return cand
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def rasterize(pptx: Path, out_dir: Path, soffice: str | None = None) -> Path | None:
    """PPTX → PNG via headless LibreOffice. None when unavailable/failed."""
    soffice = soffice or soffice_path()
    if soffice is None:
        return None
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "png", "--outdir", str(out_dir), str(pptx)],
            capture_output=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    png = out_dir / (pptx.stem + ".png")
    return png if png.exists() else None


def review(png: Path, settings: Settings, client=None) -> dict | None:
    """Vision critique of a rendered poster. None on any failure."""
    try:
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
        b64 = base64.b64encode(png.read_bytes()).decode()
        resp = client.chat.completions.create(
            model=settings.openai_text_model,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": CRITIQUE_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
                ],
            }],
        )
        data = json.loads(resp.choices[0].message.content)
        score = data.get("score")
        if not isinstance(score, (int, float)):
            return None
        return {
            "score": max(1, min(10, int(score))),
            "defects": [d for d in data.get("defects", []) if isinstance(d, str)][:6],
            "fix_hints": [h for h in data.get("fix_hints", []) if isinstance(h, str)][:4],
        }
    except Exception:
        return None


def critique_pptx(pptx: Path, settings: Settings, client=None) -> dict | None:
    png = rasterize(pptx, settings.out_dir)
    if png is None:
        return None
    return review(png, settings, client=client)

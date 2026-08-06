# Awareness Poster Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local web app: awareness-topic prompt → AI-generated A4 poster (PPTX) → imported into Canva via Connect API → user gets Canva edit URL.

**Architecture:** FastAPI backend with four isolated modules (content generation, background artwork, PPTX building, Canva import) chained by one `/api/posters` route; static single-page frontend; one-time Canva OAuth (PKCE) with tokens in local `token.json`.

**Tech Stack:** Python 3.14, FastAPI, uvicorn, python-pptx, openai (official SDK), httpx, python-dotenv, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-07-awareness-poster-design.md`. Read it before starting.
- OpenAI text model default `gpt-4o-mini`, overridable via `OPENAI_TEXT_MODEL` env var. Image model `gpt-image-1`.
- Poster sizes: A4 portrait (210×297 mm) and A4 landscape (297×210 mm) only. 1 mm = 36000 EMU → portrait slide 7,560,000 × 10,692,000 EMU.
- Canva endpoints (verified against live docs 2026-08-07):
  - Authorize: `https://www.canva.com/api/oauth/authorize` (query: `code_challenge`, `code_challenge_method=s256`, `scope`, `response_type=code`, `client_id`, `state`, `redirect_uri`)
  - Token: `POST https://api.canva.com/rest/v1/oauth/token`, `Content-Type: application/x-www-form-urlencoded`, `Authorization: Basic base64(client_id:client_secret)`
  - Import: `POST https://api.canva.com/rest/v1/imports`, `Content-Type: application/octet-stream`, header `Import-Metadata` = JSON `{"title_base64": ..., "mime_type": ...}`, body = raw PPTX bytes. Poll `GET https://api.canva.com/rest/v1/imports/{jobId}`.
- OAuth scope: exactly `design:content:write`.
- Canva design title max 50 characters (unencoded) — truncate before base64.
- Secrets only in `.env` / `token.json` (both gitignored). Never commit keys. Never print keys.
- Redirect URI everywhere: `http://127.0.0.1:8000/auth/canva/callback`.
- All network-touching unit tests use mocks/fakes. Only `scripts/smoke.py` hits real APIs.
- Windows host: run commands via PowerShell; paths must work with `pathlib.Path`.

## File Structure

```
poster_try/
├─ app/
│  ├─ __init__.py
│  ├─ config.py        # env settings (Task 1)
│  ├─ content.py       # OpenAI chat → validated poster content (Task 2)
│  ├─ artwork.py       # gpt-image-1 background (Task 3)
│  ├─ builder.py       # python-pptx A4 poster (Task 4)
│  ├─ canva.py         # PKCE OAuth + import job (Task 5)
│  └─ main.py          # FastAPI routes (Task 6)
├─ static/index.html   # UI (Task 6)
├─ scripts/smoke.py    # real-API smoke test (Task 7)
├─ tests/
│  ├─ test_config.py
│  ├─ test_content.py
│  ├─ test_artwork.py
│  ├─ test_builder.py
│  ├─ test_canva.py
│  └─ test_api.py
├─ requirements.txt
├─ .env.example
└─ README.md
```

---

### Task 1: Scaffold + config

**Files:**
- Create: `requirements.txt`, `.env.example`, `app/__init__.py`, `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.Settings` dataclass with fields `openai_api_key: str`, `openai_text_model: str`, `canva_client_id: str`, `canva_client_secret: str`, `base_url: str`, `out_dir: Path`, `token_path: Path`; function `config.load_settings(env: Mapping[str, str] | None = None) -> Settings` (reads `os.environ` when `env is None`, after loading `.env` via python-dotenv).

- [ ] **Step 1: Create venv and install deps**

`requirements.txt`:

```
fastapi
uvicorn[standard]
python-pptx
openai
httpx
python-dotenv
pytest
```

Run (PowerShell, from project root):

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Expected: installs succeed. (If `python-pptx` fails on Python 3.14, install `lxml` prerelease wheel first, or fall back to `py -3.12 -m venv .venv` if present — record which python was used in README later.)

- [ ] **Step 2: Write failing test**

`tests/test_config.py`:

```python
from pathlib import Path

from app.config import load_settings


def _env(**overrides):
    base = {
        "OPENAI_API_KEY": "sk-test",
        "CANVA_CLIENT_ID": "cid",
        "CANVA_CLIENT_SECRET": "csecret",
    }
    base.update(overrides)
    return base


def test_loads_required_keys():
    s = load_settings(_env())
    assert s.openai_api_key == "sk-test"
    assert s.canva_client_id == "cid"
    assert s.canva_client_secret == "csecret"


def test_defaults():
    s = load_settings(_env())
    assert s.openai_text_model == "gpt-4o-mini"
    assert s.base_url == "http://127.0.0.1:8000"
    assert s.out_dir == Path("out")
    assert s.token_path == Path("token.json")


def test_text_model_override():
    s = load_settings(_env(OPENAI_TEXT_MODEL="gpt-4o"))
    assert s.openai_text_model == "gpt-4o"


def test_missing_key_raises():
    import pytest
    with pytest.raises(KeyError):
        load_settings({"OPENAI_API_KEY": "sk-test"})
```

- [ ] **Step 3: Run test, verify fails**

Run: `.\.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'` (add empty `app/__init__.py` and `tests/__init__.py` if needed) then `ImportError` for `load_settings`.

- [ ] **Step 4: Implement**

`app/config.py`:

```python
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_text_model: str
    canva_client_id: str
    canva_client_secret: str
    base_url: str
    out_dir: Path
    token_path: Path


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv()
        env = os.environ
    return Settings(
        openai_api_key=env["OPENAI_API_KEY"],
        openai_text_model=env.get("OPENAI_TEXT_MODEL", "gpt-4o-mini"),
        canva_client_id=env["CANVA_CLIENT_ID"],
        canva_client_secret=env["CANVA_CLIENT_SECRET"],
        base_url=env.get("BASE_URL", "http://127.0.0.1:8000"),
        out_dir=Path(env.get("OUT_DIR", "out")),
        token_path=Path(env.get("TOKEN_PATH", "token.json")),
    )
```

`.env.example`:

```
OPENAI_API_KEY=sk-...
# OPENAI_TEXT_MODEL=gpt-4o-mini
CANVA_CLIENT_ID=...
CANVA_CLIENT_SECRET=...
```

- [ ] **Step 5: Run tests, verify pass**

Run: `.\.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```powershell
git add requirements.txt .env.example app tests
git commit -m "feat: project scaffold and settings loader"
```

---

### Task 2: Poster content generation (`content.py`)

**Files:**
- Create: `app/content.py`
- Test: `tests/test_content.py`

**Interfaces:**
- Consumes: `config.Settings` (for api key + model name).
- Produces:
  - `content.validate_content(data: dict) -> dict` — returns the dict unchanged if valid, else raises `ValueError` with reason.
  - `content.generate(topic: str, settings: Settings, client=None) -> dict` — `client` is an injected OpenAI-compatible client (tests pass a fake); returns validated dict with keys: `headline` (str ≤60 chars), `subheadline` (str ≤120), `facts` (list of 3–5 non-empty str), `cta` (str ≤80), `palette` (dict with `bg`, `accent`, `text` as `#RRGGBB`), `image_prompt` (str). Retries once on invalid JSON/schema, then raises `ValueError`.

- [ ] **Step 1: Write failing tests**

`tests/test_content.py`:

```python
import json

import pytest

from app.config import Settings
from app.content import generate, validate_content
from pathlib import Path

SETTINGS = Settings(
    openai_api_key="sk-test", openai_text_model="gpt-4o-mini",
    canva_client_id="c", canva_client_secret="s",
    base_url="http://127.0.0.1:8000", out_dir=Path("out"), token_path=Path("token.json"),
)

VALID = {
    "headline": "Save Water, Save Life",
    "subheadline": "Every drop counts more than you think",
    "facts": ["A dripping tap wastes 5,500 L/year", "Only 3% of Earth's water is fresh", "Showers beat baths by 50 L"],
    "cta": "Turn it off. Today.",
    "palette": {"bg": "#0E3A5D", "accent": "#3EC1D3", "text": "#FFFFFF"},
    "image_prompt": "minimal water drop illustration, deep blue background, space at top for text",
}


def test_valid_passes():
    assert validate_content(VALID) == VALID


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("headline"),
    lambda d: d.update(headline="x" * 61),
    lambda d: d.update(facts=["only one"]),
    lambda d: d.update(facts=["a"] * 6),
    lambda d: d.update(facts=["ok", "", "ok2"]),
    lambda d: d["palette"].update(bg="blue"),
    lambda d: d["palette"].pop("accent"),
    lambda d: d.update(image_prompt=""),
])
def test_invalid_rejected(mutate):
    bad = json.loads(json.dumps(VALID))
    mutate(bad)
    with pytest.raises(ValueError):
        validate_content(bad)


class FakeCompletions:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        text = self.payloads.pop(0)
        msg = type("M", (), {"content": text})
        choice = type("C", (), {"message": msg})
        return type("R", (), {"choices": [choice]})


class FakeClient:
    def __init__(self, payloads):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(payloads)


def test_generate_returns_valid_dict():
    client = FakeClient([json.dumps(VALID)])
    out = generate("water conservation", SETTINGS, client=client)
    assert out["headline"] == VALID["headline"]


def test_generate_retries_once_then_succeeds():
    client = FakeClient(["not json", json.dumps(VALID)])
    out = generate("water conservation", SETTINGS, client=client)
    assert out["facts"] == VALID["facts"]
    assert client.chat.completions.calls == 2


def test_generate_fails_after_two_bad():
    client = FakeClient(["not json", "{}"])
    with pytest.raises(ValueError):
        generate("water conservation", SETTINGS, client=client)
```

- [ ] **Step 2: Run tests, verify fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_content.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

`app/content.py`:

```python
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.\.venv\Scripts\python -m pytest tests/test_content.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/content.py tests/test_content.py
git commit -m "feat: AI poster content generation with schema validation"
```

---

### Task 3: Background artwork (`artwork.py`)

**Files:**
- Create: `app/artwork.py`
- Test: `tests/test_artwork.py`

**Interfaces:**
- Consumes: `Settings`.
- Produces: `artwork.generate(image_prompt: str, orientation: str, settings: Settings, client=None) -> Path | None` — writes PNG into `settings.out_dir`, returns its path; returns `None` on any API failure (callers treat `None` as "use fallback background"). `orientation` is `"portrait"` or `"landscape"`; any other value raises `ValueError` immediately.

- [ ] **Step 1: Write failing tests**

`tests/test_artwork.py`:

```python
import base64
from pathlib import Path

import pytest

from app.artwork import generate
from tests.test_content import SETTINGS

PNG_1PX = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c626001000000ffff03000006000557bfabd4000000"
        "0049454e44ae426082"
    )
).decode()


class FakeImages:
    def __init__(self, fail=False):
        self.fail = fail
        self.kwargs = None

    def generate(self, **kwargs):
        if self.fail:
            raise RuntimeError("api down")
        self.kwargs = kwargs
        item = type("I", (), {"b64_json": PNG_1PX})
        return type("R", (), {"data": [item]})


class FakeClient:
    def __init__(self, fail=False):
        self.images = FakeImages(fail)


def test_writes_png(tmp_path):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path})
    client = FakeClient()
    p = generate("water drop art", "portrait", s, client=client)
    assert p is not None and p.exists() and p.suffix == ".png"
    assert client.images.kwargs["size"] == "1024x1536"
    assert client.images.kwargs["model"] == "gpt-image-1"


def test_landscape_size(tmp_path):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path})
    client = FakeClient()
    generate("art", "landscape", s, client=client)
    assert client.images.kwargs["size"] == "1536x1024"


def test_api_failure_returns_none(tmp_path):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path})
    assert generate("art", "portrait", s, client=FakeClient(fail=True)) is None


def test_bad_orientation_raises(tmp_path):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path})
    with pytest.raises(ValueError):
        generate("art", "square", s, client=FakeClient())
```

- [ ] **Step 2: Run tests, verify fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_artwork.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

`app/artwork.py`:

```python
import base64
import uuid
from pathlib import Path

from app.config import Settings

SIZES = {"portrait": "1024x1536", "landscape": "1536x1024"}


def generate(image_prompt: str, orientation: str, settings: Settings, client=None) -> Path | None:
    if orientation not in SIZES:
        raise ValueError(f"orientation must be one of {sorted(SIZES)}")
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
    try:
        resp = client.images.generate(
            model="gpt-image-1",
            prompt=image_prompt,
            size=SIZES[orientation],
            n=1,
        )
        raw = base64.b64decode(resp.data[0].b64_json)
    except Exception:
        return None
    settings.out_dir.mkdir(parents=True, exist_ok=True)
    path = settings.out_dir / f"bg_{uuid.uuid4().hex[:8]}.png"
    path.write_bytes(raw)
    return path
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.\.venv\Scripts\python -m pytest tests/test_artwork.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/artwork.py tests/test_artwork.py
git commit -m "feat: gpt-image-1 background generation with graceful failure"
```

---

### Task 4: PPTX poster builder (`builder.py`)

**Files:**
- Create: `app/builder.py`
- Test: `tests/test_builder.py`

**Interfaces:**
- Consumes: content dict from Task 2, optional PNG path from Task 3.
- Produces: `builder.build(content: dict, image: Path | None, orientation: str, out_dir: Path) -> Path` — writes `poster_<hex>.pptx` sized A4, one slide, with real text boxes; `image=None` → solid palette background with accent shapes. Raises `ValueError` on bad orientation.
- Layout contract (tests check): slide contains ≥4 text-bearing shapes; headline text present; every fact string present; CTA present.

- [ ] **Step 1: Write failing tests**

`tests/test_builder.py`:

```python
from pathlib import Path

import pytest
from pptx import Presentation

from app.builder import A4_EMU, build
from tests.test_content import VALID

PORTRAIT = (7_560_000, 10_692_000)


def _texts(pptx_path):
    prs = Presentation(str(pptx_path))
    out = []
    for shape in prs.slides[0].shapes:
        if shape.has_text_frame:
            out.append(shape.text_frame.text)
    return prs, out


def test_a4_constants():
    assert A4_EMU["portrait"] == PORTRAIT
    assert A4_EMU["landscape"] == (PORTRAIT[1], PORTRAIT[0])


@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_build_no_image(tmp_path, orientation):
    p = build(VALID, None, orientation, tmp_path)
    prs, texts = _texts(p)
    w, h = A4_EMU[orientation]
    assert (prs.slide_width, prs.slide_height) == (w, h)
    joined = "\n".join(texts)
    assert VALID["headline"] in joined
    assert VALID["cta"] in joined
    for fact in VALID["facts"]:
        assert fact in joined


def test_build_with_image(tmp_path):
    import base64
    from tests.test_artwork import PNG_1PX
    img = tmp_path / "bg.png"
    img.write_bytes(base64.b64decode(PNG_1PX))
    p = build(VALID, img, "portrait", tmp_path)
    prs, _ = _texts(p)
    pics = [s for s in prs.slides[0].shapes if s.shape_type == 13]  # PICTURE
    assert len(pics) == 1
    assert (pics[0].width, pics[0].height) == A4_EMU["portrait"]


def test_bad_orientation(tmp_path):
    with pytest.raises(ValueError):
        build(VALID, None, "square", tmp_path)
```

- [ ] **Step 2: Run tests, verify fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_builder.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

`app/builder.py`:

```python
import uuid
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

A4_EMU = {
    "portrait": (7_560_000, 10_692_000),
    "landscape": (10_692_000, 7_560_000),
}


def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str.lstrip("#"))


def _set_fill_alpha(shape, transparency_pct: int) -> None:
    """Add alpha to a solid fill. transparency_pct=40 → 60% opaque."""
    srgb = shape.fill.fore_color._xFill.find(qn("a:srgbClr"))
    alpha = srgb.makeelement(qn("a:alpha"), {"val": str((100 - transparency_pct) * 1000)})
    srgb.append(alpha)


def _add_rect(slide, x, y, w, h, hex_color, transparency_pct=0):
    from pptx.enum.shapes import MSO_SHAPE
    rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x), Emu(y), Emu(w), Emu(h))
    rect.fill.solid()
    rect.fill.fore_color.rgb = _rgb(hex_color)
    rect.line.fill.background()
    if transparency_pct:
        _set_fill_alpha(rect, transparency_pct)
    return rect


def _add_text(slide, x, y, w, h, text, size_pt, hex_color, bold=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    para = tf.paragraphs[0]
    para.alignment = align
    run = para.add_run()
    run.text = text
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = _rgb(hex_color)
    return box


def build(content: dict, image: Path | None, orientation: str, out_dir: Path) -> Path:
    if orientation not in A4_EMU:
        raise ValueError(f"orientation must be one of {sorted(A4_EMU)}")
    w, h = A4_EMU[orientation]
    pal = content["palette"]

    prs = Presentation()
    prs.slide_width = Emu(w)
    prs.slide_height = Emu(h)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    if image is not None:
        slide.shapes.add_picture(str(image), 0, 0, Emu(w), Emu(h))
        _add_rect(slide, 0, 0, w, h, pal["bg"], transparency_pct=55)
    else:
        _add_rect(slide, 0, 0, w, h, pal["bg"])
        _add_rect(slide, 0, int(h * 0.92), w, int(h * 0.08), pal["accent"])
        _add_rect(slide, int(w * 0.82), 0, int(w * 0.18), int(h * 0.25), pal["accent"], transparency_pct=30)

    margin = int(w * 0.08)
    cw = w - 2 * margin
    headline_size = 44 if orientation == "portrait" else 40

    _add_text(slide, margin, int(h * 0.07), cw, int(h * 0.14),
              content["headline"], headline_size, pal["text"], bold=True, align=PP_ALIGN.CENTER)
    _add_text(slide, margin, int(h * 0.21), cw, int(h * 0.08),
              content["subheadline"], 20, pal["text"], align=PP_ALIGN.CENTER)

    facts_top = int(h * 0.34)
    row_h = int(h * 0.40 / len(content["facts"]))
    for i, fact in enumerate(content["facts"]):
        _add_rect(slide, margin, facts_top + i * row_h, int(w * 0.012), int(row_h * 0.72), pal["accent"])
        _add_text(slide, margin + int(w * 0.03), facts_top + i * row_h, cw - int(w * 0.03), int(row_h * 0.8),
                  fact, 16, pal["text"])

    cta_top = int(h * 0.80)
    _add_rect(slide, margin, cta_top, cw, int(h * 0.10), pal["accent"])
    _add_text(slide, margin, cta_top + int(h * 0.025), cw, int(h * 0.05),
              content["cta"], 24, pal["bg"], bold=True, align=PP_ALIGN.CENTER)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"poster_{uuid.uuid4().hex[:8]}.pptx"
    prs.save(str(path))
    return path
```

Note: if `shape.fill.fore_color._xFill` fails (python-pptx internals differ), the fallback is `shape.fill._xPr.find(qn('a:solidFill')).find(qn('a:srgbClr'))` — same alpha-append afterward. Verify against installed python-pptx version and keep whichever works; the test `test_build_with_image` exercises the code path.

- [ ] **Step 4: Run tests, verify pass**

Run: `.\.venv\Scripts\python -m pytest tests/test_builder.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Eyeball check (manual, no commit gate)**

```powershell
.\.venv\Scripts\python -c "from app.builder import build; from tests.test_content import VALID; from pathlib import Path; print(build(VALID, None, 'portrait', Path('out')))"
```

Open the produced PPTX in PowerPoint/LibreOffice if available; confirm layout sane (headline top, facts middle, CTA band bottom). Adjust size constants only if text overflows.

- [ ] **Step 6: Commit**

```powershell
git add app/builder.py tests/test_builder.py
git commit -m "feat: A4 PPTX poster builder with image and fallback backgrounds"
```

---

### Task 5: Canva OAuth + import (`canva.py`)

**Files:**
- Create: `app/canva.py`
- Test: `tests/test_canva.py`

**Interfaces:**
- Consumes: `Settings` (client id/secret, token_path, base_url).
- Produces:
  - Exceptions: `NotAuthenticated`, `ImportFailed`, `ImportTimeout` (all subclass `CanvaError(Exception)`).
  - `canva.make_pkce() -> tuple[str, str]` — `(verifier, challenge)`; verifier 43–128 chars urlsafe, challenge = urlsafe-b64(SHA256(verifier)) without `=` padding.
  - `canva.build_auth_url(settings: Settings, challenge: str, state: str) -> str`.
  - `canva.exchange_code(settings, code: str, verifier: str) -> dict` — POSTs token endpoint, saves token file, returns token dict.
  - `canva.get_access_token(settings, http=None) -> str` — loads token file; refreshes via refresh_token grant if `expires_at` within 60 s; raises `NotAuthenticated` if file missing/refresh fails.
  - `canva.import_design(settings, pptx: Path, title: str, http=None, poll_interval: float = 2.0, timeout: float = 60.0) -> str` — returns `edit_url`.
  - `http` is an injected `httpx.Client`-compatible object (tests pass fakes); production code creates `httpx.Client()` when `None`.
- Token file JSON: `{"access_token": str, "refresh_token": str, "expires_at": float}` (`expires_at` = epoch seconds computed from `expires_in`).

- [ ] **Step 1: Write failing tests**

`tests/test_canva.py`:

```python
import base64
import hashlib
import json
import time
from pathlib import Path

import pytest

from app import canva
from tests.test_content import SETTINGS


def _settings(tmp_path):
    return SETTINGS.__class__(**{**SETTINGS.__dict__, "token_path": tmp_path / "token.json"})


def test_pkce_pair():
    verifier, challenge = canva.make_pkce()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected


def test_auth_url(tmp_path):
    url = canva.build_auth_url(_settings(tmp_path), "chal", "st4te")
    assert url.startswith("https://www.canva.com/api/oauth/authorize?")
    assert "code_challenge=chal" in url
    assert "code_challenge_method=s256" in url
    assert "response_type=code" in url
    assert "client_id=c" in url
    assert "state=st4te" in url
    assert "design%3Acontent%3Awrite" in url or "design:content:write" in url


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttp:
    def __init__(self, post_responses=None, get_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.post_responses.pop(0)

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self.get_responses.pop(0)


def _write_token(settings, expires_in=3600):
    settings.token_path.write_text(json.dumps({
        "access_token": "tok", "refresh_token": "ref",
        "expires_at": time.time() + expires_in,
    }))


def test_get_access_token_valid(tmp_path):
    s = _settings(tmp_path)
    _write_token(s)
    assert canva.get_access_token(s, http=FakeHttp()) == "tok"


def test_get_access_token_missing_raises(tmp_path):
    with pytest.raises(canva.NotAuthenticated):
        canva.get_access_token(_settings(tmp_path), http=FakeHttp())


def test_get_access_token_refreshes_expired(tmp_path):
    s = _settings(tmp_path)
    _write_token(s, expires_in=10)
    http = FakeHttp(post_responses=[FakeResponse(200, {
        "access_token": "tok2", "refresh_token": "ref2", "expires_in": 3600, "token_type": "Bearer",
    })])
    assert canva.get_access_token(s, http=http) == "tok2"
    url, kwargs = http.posts[0]
    assert url == "https://api.canva.com/rest/v1/oauth/token"
    assert kwargs["data"]["grant_type"] == "refresh_token"
    saved = json.loads(s.token_path.read_text())
    assert saved["refresh_token"] == "ref2"


def test_import_metadata_title_truncated():
    header = canva._import_metadata("x" * 80)
    meta = json.loads(header)
    assert len(base64.b64decode(meta["title_base64"]).decode()) == 50
    assert meta["mime_type"] == "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def test_import_design_success(tmp_path):
    s = _settings(tmp_path)
    _write_token(s)
    pptx = tmp_path / "p.pptx"
    pptx.write_bytes(b"fake")
    http = FakeHttp(
        post_responses=[FakeResponse(200, {"job": {"id": "j1", "status": "in_progress"}})],
        get_responses=[
            FakeResponse(200, {"job": {"id": "j1", "status": "in_progress"}}),
            FakeResponse(200, {"job": {"id": "j1", "status": "success", "result": {"designs": [
                {"id": "d1", "urls": {"edit_url": "https://canva.com/edit/d1", "view_url": "v"}},
            ]}}}),
        ],
    )
    url = canva.import_design(s, pptx, "My Poster", http=http, poll_interval=0, timeout=5)
    assert url == "https://canva.com/edit/d1"
    post_url, kwargs = http.posts[0]
    assert post_url == "https://api.canva.com/rest/v1/imports"
    assert kwargs["headers"]["Content-Type"] == "application/octet-stream"
    assert "Import-Metadata" in kwargs["headers"]
    assert http.gets[0][0] == "https://api.canva.com/rest/v1/imports/j1"


def test_import_design_failed_job(tmp_path):
    s = _settings(tmp_path)
    _write_token(s)
    pptx = tmp_path / "p.pptx"
    pptx.write_bytes(b"fake")
    http = FakeHttp(post_responses=[FakeResponse(200, {"job": {
        "id": "j1", "status": "failed", "error": {"code": "bad", "message": "nope"},
    }})])
    with pytest.raises(canva.ImportFailed):
        canva.import_design(s, pptx, "t", http=http, poll_interval=0, timeout=5)


def test_import_design_timeout(tmp_path):
    s = _settings(tmp_path)
    _write_token(s)
    pptx = tmp_path / "p.pptx"
    pptx.write_bytes(b"fake")
    stuck = FakeResponse(200, {"job": {"id": "j1", "status": "in_progress"}})
    http = FakeHttp(post_responses=[stuck], get_responses=[stuck] * 50)
    with pytest.raises(canva.ImportTimeout):
        canva.import_design(s, pptx, "t", http=http, poll_interval=0, timeout=0.1)
```

- [ ] **Step 2: Run tests, verify fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_canva.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

`app/canva.py`:

```python
import base64
import hashlib
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

from app.config import Settings

AUTH_URL = "https://www.canva.com/api/oauth/authorize"
TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
IMPORT_URL = "https://api.canva.com/rest/v1/imports"
SCOPE = "design:content:write"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class CanvaError(Exception):
    pass


class NotAuthenticated(CanvaError):
    pass


class ImportFailed(CanvaError):
    pass


class ImportTimeout(CanvaError):
    pass


def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(settings: Settings, challenge: str, state: str) -> str:
    query = urlencode({
        "code_challenge": challenge,
        "code_challenge_method": "s256",
        "scope": SCOPE,
        "response_type": "code",
        "client_id": settings.canva_client_id,
        "state": state,
        "redirect_uri": f"{settings.base_url}/auth/canva/callback",
    })
    return f"{AUTH_URL}?{query}"


def _basic_auth(settings: Settings) -> str:
    raw = f"{settings.canva_client_id}:{settings.canva_client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _save_token(settings: Settings, payload: dict) -> dict:
    token = {
        "access_token": payload["access_token"],
        "refresh_token": payload["refresh_token"],
        "expires_at": time.time() + float(payload["expires_in"]),
    }
    settings.token_path.write_text(json.dumps(token))
    return token


def _token_request(settings: Settings, data: dict, http=None) -> dict:
    if http is None:
        import httpx
        http = httpx.Client()
    resp = http.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth(settings),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=data,
    )
    resp.raise_for_status()
    return _save_token(settings, resp.json())


def exchange_code(settings: Settings, code: str, verifier: str, http=None) -> dict:
    return _token_request(settings, {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": f"{settings.base_url}/auth/canva/callback",
    }, http=http)


def get_access_token(settings: Settings, http=None) -> str:
    if not settings.token_path.exists():
        raise NotAuthenticated("no token file — connect Canva first")
    token = json.loads(settings.token_path.read_text())
    if token["expires_at"] - time.time() > 60:
        return token["access_token"]
    try:
        refreshed = _token_request(settings, {
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        }, http=http)
    except Exception as e:
        raise NotAuthenticated(f"token refresh failed: {e}") from e
    return refreshed["access_token"]


def _import_metadata(title: str) -> str:
    title_b64 = base64.b64encode(title[:50].encode()).decode()
    return json.dumps({"title_base64": title_b64, "mime_type": PPTX_MIME})


def import_design(settings: Settings, pptx: Path, title: str, http=None,
                  poll_interval: float = 2.0, timeout: float = 60.0) -> str:
    if http is None:
        import httpx
        http = httpx.Client(timeout=30)
    access = get_access_token(settings, http=http)
    headers = {
        "Authorization": f"Bearer {access}",
        "Content-Type": "application/octet-stream",
        "Import-Metadata": _import_metadata(title),
    }
    resp = http.post(IMPORT_URL, headers=headers, content=pptx.read_bytes())
    resp.raise_for_status()
    job = resp.json()["job"]
    deadline = time.time() + timeout
    while True:
        if job["status"] == "success":
            return job["result"]["designs"][0]["urls"]["edit_url"]
        if job["status"] == "failed":
            err = job.get("error", {})
            raise ImportFailed(f"{err.get('code')}: {err.get('message')}")
        if time.time() >= deadline:
            raise ImportTimeout(f"import job {job['id']} still in progress after {timeout}s")
        time.sleep(poll_interval)
        poll = http.get(f"{IMPORT_URL}/{job['id']}",
                        headers={"Authorization": f"Bearer {access}"})
        poll.raise_for_status()
        job = poll.json()["job"]
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.\.venv\Scripts\python -m pytest tests/test_canva.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/canva.py tests/test_canva.py
git commit -m "feat: Canva Connect OAuth (PKCE) and PPTX design import"
```

---

### Task 6: FastAPI app + UI (`main.py`, `static/index.html`)

**Files:**
- Create: `app/main.py`, `static/index.html`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: everything above — `content.generate`, `artwork.generate`, `builder.build`, `canva.import_design`, `canva.build_auth_url`, `canva.exchange_code`, `canva.make_pkce`, `canva.NotAuthenticated`.
- Produces routes:
  - `GET /` → `static/index.html`
  - `GET /api/status` → `{"canva_connected": bool}` (token file exists)
  - `GET /auth/canva` → 307 redirect to Canva authorize URL; stores `{state: verifier}` in module-level dict `_pending`
  - `GET /auth/canva/callback?code&state` → exchanges code, saves token, redirects `/`
  - `POST /api/posters` body `{"topic": str, "orientation": "portrait"|"landscape"}` → `{"edit_url": str|null, "content": {...}, "warnings": [str], "pptx_download": str|null}`; `pptx_download` set (path under `/api/download/`) when Canva import failed; `warnings` notes image-fallback or import failure.
  - `GET /api/download/{filename}` → serves file from `out_dir` (reject names with path separators — 404).

- [ ] **Step 1: Write failing tests**

`tests/test_api.py`:

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import canva
from tests.test_content import SETTINGS, VALID


@pytest.fixture()
def client(tmp_path, monkeypatch):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path, "token_path": tmp_path / "token.json"})
    monkeypatch.setattr(main, "settings", s)
    return TestClient(main.app)


def test_status_disconnected(client):
    assert client.get("/api/status").json() == {"canva_connected": False}


def test_auth_redirects(client):
    r = client.get("/auth/canva", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://www.canva.com/api/oauth/authorize?")


def test_poster_happy_path(client, monkeypatch, tmp_path):
    fake_pptx = tmp_path / "poster_x.pptx"
    fake_pptx.write_bytes(b"pptx")
    monkeypatch.setattr(main.content, "generate", lambda topic, s, client=None: dict(VALID))
    monkeypatch.setattr(main.artwork, "generate", lambda p, o, s, client=None: None)
    monkeypatch.setattr(main.builder, "build", lambda c, i, o, d: fake_pptx)
    monkeypatch.setattr(main.canva, "import_design", lambda s, p, t, **kw: "https://canva.com/edit/d1")
    r = client.post("/api/posters", json={"topic": "road safety", "orientation": "portrait"})
    body = r.json()
    assert r.status_code == 200
    assert body["edit_url"] == "https://canva.com/edit/d1"
    assert body["content"]["headline"] == VALID["headline"]
    assert any("background" in w.lower() for w in body["warnings"])


def test_poster_import_failure_offers_download(client, monkeypatch, tmp_path):
    fake_pptx = tmp_path / "poster_y.pptx"
    fake_pptx.write_bytes(b"pptx")
    monkeypatch.setattr(main.content, "generate", lambda topic, s, client=None: dict(VALID))
    monkeypatch.setattr(main.artwork, "generate", lambda p, o, s, client=None: None)
    monkeypatch.setattr(main.builder, "build", lambda c, i, o, d: fake_pptx)

    def boom(*a, **kw):
        raise canva.ImportFailed("bad")

    monkeypatch.setattr(main.canva, "import_design", boom)
    body = client.post("/api/posters", json={"topic": "x", "orientation": "portrait"}).json()
    assert body["edit_url"] is None
    assert body["pptx_download"] == "/api/download/poster_y.pptx"
    dl = client.get(body["pptx_download"])
    assert dl.status_code == 200


def test_poster_not_authenticated(client, monkeypatch):
    monkeypatch.setattr(main.content, "generate", lambda topic, s, client=None: dict(VALID))
    monkeypatch.setattr(main.artwork, "generate", lambda p, o, s, client=None: None)

    def build(c, i, o, d):
        p = main.settings.out_dir / "poster_z.pptx"
        p.write_bytes(b"pptx")
        return p

    monkeypatch.setattr(main.builder, "build", build)

    def nope(*a, **kw):
        raise canva.NotAuthenticated("no token")

    monkeypatch.setattr(main.canva, "import_design", nope)
    r = client.post("/api/posters", json={"topic": "x", "orientation": "portrait"})
    assert r.status_code == 401


def test_bad_orientation_rejected(client):
    r = client.post("/api/posters", json={"topic": "x", "orientation": "square"})
    assert r.status_code == 422


def test_download_traversal_blocked(client):
    assert client.get("/api/download/..%5Ctoken.json").status_code in (404, 422)
```

- [ ] **Step 2: Run tests, verify fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_api.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement backend**

`app/main.py`:

```python
import secrets
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from app import artwork, builder, canva, content
from app.config import load_settings

app = FastAPI(title="Awareness Poster Generator")
settings = load_settings()
_pending: dict[str, str] = {}  # state -> PKCE verifier

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class PosterRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    orientation: Literal["portrait", "landscape"] = "portrait"


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def status():
    return {"canva_connected": settings.token_path.exists()}


@app.get("/auth/canva")
def auth_start():
    verifier, challenge = canva.make_pkce()
    state = secrets.token_urlsafe(16)
    _pending[state] = verifier
    return RedirectResponse(canva.build_auth_url(settings, challenge, state))


@app.get("/auth/canva/callback")
def auth_callback(code: str, state: str):
    verifier = _pending.pop(state, None)
    if verifier is None:
        raise HTTPException(400, "unknown state — restart auth from /auth/canva")
    canva.exchange_code(settings, code, verifier)
    return RedirectResponse("/")


@app.post("/api/posters")
def create_poster(req: PosterRequest):
    warnings: list[str] = []
    data = content.generate(req.topic, settings)
    image = artwork.generate(data["image_prompt"], req.orientation, settings)
    if image is None:
        warnings.append("Background image generation failed — used palette background instead.")
    pptx = builder.build(data, image, req.orientation, settings.out_dir)

    edit_url = None
    pptx_download = None
    try:
        edit_url = canva.import_design(settings, pptx, data["headline"])
    except canva.NotAuthenticated:
        raise HTTPException(401, "Canva not connected — click Connect Canva first")
    except canva.CanvaError as e:
        warnings.append(f"Canva import failed ({e}) — download the PPTX and import manually.")
        pptx_download = f"/api/download/{pptx.name}"

    return {"edit_url": edit_url, "content": data, "warnings": warnings, "pptx_download": pptx_download}


@app.get("/api/download/{filename}")
def download(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(404)
    path = settings.out_dir / filename
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=filename)
```

- [ ] **Step 4: Implement frontend**

`static/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Awareness Poster Generator</title>
<style>
  :root { --ink: #1b2733; --accent: #2f7d6d; --paper: #f4f1ea; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: Georgia, 'Times New Roman', serif; background: var(--paper); color: var(--ink); }
  main { max-width: 640px; margin: 4rem auto; padding: 0 1.5rem; }
  h1 { font-size: 2rem; letter-spacing: -0.02em; }
  form { display: grid; gap: 0.9rem; margin-top: 1.5rem; }
  textarea { font: inherit; padding: 0.8rem; border: 2px solid var(--ink); background: #fff; min-height: 5rem; }
  .row { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
  button { font: inherit; font-weight: bold; padding: 0.7rem 1.4rem; border: 2px solid var(--ink);
           background: var(--accent); color: #fff; cursor: pointer; }
  button:disabled { opacity: 0.5; cursor: wait; }
  #connect { background: #fff; color: var(--ink); }
  #result { margin-top: 2rem; border-top: 2px solid var(--ink); padding-top: 1rem; }
  .warn { color: #8a5a00; }
  a.edit { display: inline-block; margin-top: 0.6rem; font-weight: bold; color: var(--accent); }
  ul { padding-left: 1.2rem; }
</style>
</head>
<body>
<main>
  <h1>Awareness Poster Generator</h1>
  <p id="canva-state">Checking Canva connection…</p>
  <form id="form">
    <textarea id="topic" placeholder="e.g. Road safety for teenagers" required minlength="3"></textarea>
    <div class="row">
      <label><input type="radio" name="orientation" value="portrait" checked> A4 portrait</label>
      <label><input type="radio" name="orientation" value="landscape"> A4 landscape</label>
      <button id="go" type="submit">Generate poster</button>
      <button id="connect" type="button" hidden>Connect Canva</button>
    </div>
  </form>
  <div id="result"></div>
</main>
<script>
const state = document.getElementById('canva-state');
const connect = document.getElementById('connect');
const go = document.getElementById('go');
const result = document.getElementById('result');

async function refreshStatus() {
  const s = await (await fetch('/api/status')).json();
  state.textContent = s.canva_connected ? 'Canva: connected ✓' : 'Canva: not connected';
  connect.hidden = s.canva_connected;
}
connect.onclick = () => { location.href = '/auth/canva'; };
refreshStatus();

document.getElementById('form').onsubmit = async (e) => {
  e.preventDefault();
  go.disabled = true;
  result.textContent = 'Generating… (30–90 s: writing copy, drawing background, importing to Canva)';
  try {
    const resp = await fetch('/api/posters', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic: document.getElementById('topic').value,
        orientation: document.querySelector('input[name=orientation]:checked').value,
      }),
    });
    const body = await resp.json();
    if (resp.status === 401) {
      result.textContent = 'Connect Canva first.';
      connect.hidden = false;
      return;
    }
    if (!resp.ok) { result.textContent = 'Error: ' + (body.detail ?? resp.status); return; }
    const c = body.content;
    result.innerHTML = `
      <h2>${c.headline}</h2>
      <p>${c.subheadline}</p>
      <ul>${c.facts.map(f => `<li>${f}</li>`).join('')}</ul>
      <p><strong>${c.cta}</strong></p>
      ${body.warnings.map(w => `<p class="warn">⚠ ${w}</p>`).join('')}
      ${body.edit_url ? `<a class="edit" href="${body.edit_url}" target="_blank">Edit in Canva →</a>` : ''}
      ${body.pptx_download ? `<a class="edit" href="${body.pptx_download}">Download PPTX</a>` : ''}
    `;
  } catch (err) {
    result.textContent = 'Request failed: ' + err;
  } finally {
    go.disabled = false;
  }
};
</script>
</body>
</html>
```

- [ ] **Step 5: Run tests, verify pass**

Run: `.\.venv\Scripts\python -m pytest tests/test_api.py -v`
Expected: 7 PASS. Note: `load_settings()` at import time requires a `.env` with the three keys or the env vars set — for the test run, create `.env` from `.env.example` with dummy values first if not present.

- [ ] **Step 6: Full suite**

Run: `.\.venv\Scripts\python -m pytest -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```powershell
git add app/main.py static tests/test_api.py
git commit -m "feat: FastAPI routes and single-page UI"
```

---

### Task 7: Smoke script + README

**Files:**
- Create: `scripts/smoke.py`, `README.md`

**Interfaces:**
- Consumes: full pipeline.
- Produces: `scripts/smoke.py` — run manually with real keys; prints edit URL or failure per stage.

- [ ] **Step 1: Write smoke script**

`scripts/smoke.py`:

```python
"""Manual end-to-end smoke test. Needs real .env and a connected Canva token.

Run:  .venv\\Scripts\\python scripts\\smoke.py "topic here" [portrait|landscape]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import artwork, builder, canva, content
from app.config import load_settings


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "hand washing and hygiene"
    orientation = sys.argv[2] if len(sys.argv) > 2 else "portrait"
    settings = load_settings()

    print(f"[1/4] content for: {topic!r}")
    data = content.generate(topic, settings)
    print(f"      headline: {data['headline']}")

    print("[2/4] background image")
    image = artwork.generate(data["image_prompt"], orientation, settings)
    print(f"      {'ok: ' + str(image) if image else 'FAILED — using fallback'}")

    print("[3/4] building pptx")
    pptx = builder.build(data, image, orientation, settings.out_dir)
    print(f"      {pptx}")

    print("[4/4] importing to Canva")
    url = canva.import_design(settings, pptx, data["headline"])
    print(f"\nEDIT URL: {url}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write README**

`README.md` must contain, in this order (write real prose, not stubs):

1. **What it does** — one paragraph: topic → AI poster → Canva edit URL.
2. **Setup**
   - `py -m venv .venv` then `.\.venv\Scripts\python -m pip install -r requirements.txt` (note actual Python version used in Task 1).
   - Copy `.env.example` → `.env`; fill `OPENAI_API_KEY` from platform.openai.com.
   - **Canva integration (exact clicks):** go to `https://www.canva.com/developers/integrations` → *Create an integration* → type **Public** not required; a private/dev integration works for the creator's own account → name it → under **Scopes** enable `design:content:write` → under **Authentication** add redirect URL `http://127.0.0.1:8000/auth/canva/callback` → copy **Client ID** and generate **Client secret** → paste both into `.env`.
3. **Run** — `.\.venv\Scripts\python -m uvicorn app.main:app --port 8000`, open `http://127.0.0.1:8000`, click *Connect Canva* once, then generate posters.
4. **Tests** — `.\.venv\Scripts\python -m pytest`; smoke: `.\.venv\Scripts\python scripts\smoke.py "road safety"`.
5. **Troubleshooting** — 401 → reconnect Canva; import failed → download PPTX and drag into Canva manually; image warnings → poster still generated with palette background.

- [ ] **Step 3: Run smoke test with real keys (requires user's .env + one-time OAuth in browser)**

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
# browser: http://127.0.0.1:8000 → Connect Canva → generate a poster
```

Expected: UI returns an `Edit in Canva` link that opens an editable design (text selectable/editable in Canva editor). If blocked on missing keys, stop and ask the user to fill `.env` and complete OAuth — do not fake this step.

- [ ] **Step 4: Commit**

```powershell
git add scripts/smoke.py README.md
git commit -m "docs: README setup guide and end-to-end smoke script"
```

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from app import (artwork, brand, builder, canva, content, critique, design, director,
                 envfile, history, knowledge, recipes, research)
from app.config import load_settings

app = FastAPI(title="Awareness Poster Generator")
settings = load_settings()
_pending: dict[str, str] = {}  # state -> PKCE verifier

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
ENV_PATH = Path(os.environ.get("ENV_FILE", ".env"))


def reload_settings() -> None:
    """Rebuild the module-level settings from the current .env file, layered
    over os.environ so shell-provided extras (OUT_DIR, etc.) still apply.
    Lets a config save take effect without restarting the server."""
    global settings
    merged = {**os.environ, **envfile.read_env(ENV_PATH)}
    settings = load_settings(env=merged)


class PosterRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    orientation: Literal["portrait", "landscape", "both"] = "portrait"


class ConfigRequest(BaseModel):
    openai_api_key: str | None = None
    canva_client_id: str | None = None
    canva_client_secret: str | None = None


class BrandRequest(BaseModel):
    org_name: str | None = None
    about: str | None = None
    colors: list[str] | None = None


def _plan_uses_image(spec: dict) -> bool:
    """True when the chosen style uses background artwork, so we only pay for
    image generation when the design actually places one."""
    return spec.get("background_style") == "image"


def _brand_moods(kit: dict) -> list[str]:
    """Map a brand's ideology text to recipe moods so selection leans on-brand.
    Empty list = no preference (full library in play)."""
    about = (kit.get("about") or "").lower()
    hits = []
    cues = {
        "corporate": ["enterprise", "b2b", "corporate", "compliance", "finance", "bank"],
        "playful": ["fun", "playful", "kids", "youth", "vibrant", "community"],
        "activist": ["activist", "campaign", "rights", "justice", "advocacy", "non-profit", "nonprofit"],
        "calm": ["wellness", "health", "mindful", "calm", "care", "support"],
        "urgent": ["emergency", "urgent", "alert", "safety", "crisis", "threat"],
        "editorial": ["magazine", "editorial", "story", "journal", "research"],
        "modern": ["tech", "startup", "saas", "digital", "innovation"],
    }
    for mood, words in cues.items():
        if any(w in about for w in words):
            hits.append(mood)
    return hits


def _config_status() -> dict:
    """Masked view of current credentials — never returns full secrets."""
    return {
        "openai_api_key": {"set": bool(settings.openai_api_key), "hint": envfile.mask(settings.openai_api_key)},
        "canva_client_id": {"set": bool(settings.canva_client_id), "hint": envfile.mask(settings.canva_client_id)},
        "canva_client_secret": {"set": bool(settings.canva_client_secret), "hint": envfile.mask(settings.canva_client_secret)},
        "base_url": settings.base_url,
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def status():
    return {"canva_connected": settings.token_path.exists()}


@app.get("/api/config")
def get_config():
    return _config_status()


@app.get("/api/brand")
def get_brand():
    return brand.load()


@app.post("/api/brand")
def set_brand(req: BrandRequest):
    current = brand.load()
    merged = {
        "org_name": req.org_name if req.org_name is not None else current["org_name"],
        "about": req.about if req.about is not None else current["about"],
        "colors": req.colors if req.colors is not None else current["colors"],
    }
    return brand.save(merged)


@app.post("/api/config")
def set_config(req: ConfigRequest):
    envfile.update_env(ENV_PATH, {
        "OPENAI_API_KEY": req.openai_api_key or "",
        "CANVA_CLIENT_ID": req.canva_client_id or "",
        "CANVA_CLIENT_SECRET": req.canva_client_secret or "",
    })
    reload_settings()
    return _config_status()


@app.get("/auth/canva")
def auth_start():
    verifier, challenge = canva.make_pkce()
    state = secrets.token_urlsafe(16)
    _pending[state] = verifier
    return RedirectResponse(canva.build_auth_url(settings, challenge, state))


@app.get("/auth/canva/callback")
def auth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    if error:
        raise HTTPException(400, f"Canva returned an error: {error} — {error_description or ''}")
    if not code or not state:
        raise HTTPException(400, "Missing authorization code — start from Connect Canva, don't open this URL directly.")
    verifier = _pending.pop(state, None)
    if verifier is None:
        raise HTTPException(400, "unknown state — restart auth from Connect Canva")
    try:
        canva.exchange_code(settings, code, verifier)
    except Exception as e:
        raise HTTPException(400, f"Token exchange failed: {e}")
    return RedirectResponse("/")


def _render_and_check(variant: dict, spec: dict, image, orientation: str,
                      warnings: list[str], brand_block: str):
    """Render, then let the vision critic look at the poster. One retry with
    the critic's fix hints when the score is poor. Returns (pptx, score)."""
    pptx = builder.render(spec, variant, image, orientation, settings.out_dir)
    verdict = critique.critique_pptx(pptx, settings)
    if verdict is None:
        return pptx, None
    if verdict["score"] >= critique.PASS_SCORE or not verdict.get("fix_hints"):
        return pptx, verdict["score"]
    try:
        new_spec = design.generate_single(variant, orientation, settings,
                                          brand_block=brand_block,
                                          fix_hints=verdict["fix_hints"],
                                          keep_archetype=spec.get("archetype"))
        new_image = image
        if _plan_uses_image(new_spec) and image is None:
            new_image = artwork.generate(new_spec["image_prompt"], orientation, settings)
        pptx2 = builder.render(new_spec, variant, new_image, orientation, settings.out_dir)
        verdict2 = critique.critique_pptx(pptx2, settings)
        if verdict2 is None or verdict2["score"] >= verdict["score"]:
            spec.update(new_spec)
            return pptx2, (verdict2 or {}).get("score")
    except Exception:
        pass
    warnings.append(f"Design critic scored this option {verdict['score']}/10; retry did not improve it.")
    return pptx, verdict["score"]


def _make_option(variant: dict, spec: dict, orientation: str, brand_block: str) -> dict:
    """Build one poster option end-to-end: image (if styled, with no-text QA)
    → render → vision critique (retry once on poor score) → import. Never
    raises — failures degrade into warnings/downloads so siblings still ship."""
    warnings: list[str] = []
    image = None
    if _plan_uses_image(spec):
        image = artwork.generate(spec["image_prompt"], orientation, settings)
        if image is None:
            warnings.append("Background image failed — solid background used.")
    score = None
    try:
        pptx, score = _render_and_check(variant, spec, image, orientation, warnings, brand_block)
    except Exception as e:
        warnings.append(f"Layout render failed ({e}) — standard layout used.")
        pptx = builder.fallback_build(content.to_legacy(variant), image, orientation, settings.out_dir)

    edit_url = None
    pptx_download = None
    try:
        edit_url = canva.import_design(settings, pptx, variant["headline"])
    except Exception as e:  # CanvaError or any transport/parse failure
        warnings.append(f"Canva import failed ({e}) — download the PPTX instead.")
        pptx_download = f"/api/download/{pptx.name}"

    return {
        "content": variant,
        "archetype": spec.get("archetype"),
        "orientation": orientation,
        "quality_score": score,
        "edit_url": edit_url,
        "warnings": warnings,
        "pptx_download": pptx_download,
    }


@app.post("/api/posters")
def create_poster(req: PosterRequest):
    if not settings.token_path.exists():
        raise HTTPException(401, "Canva not connected — click Connect Canva first")
    try:
        return _generate_posters(req)
    except HTTPException:
        raise
    except Exception as e:
        # never leak a plain-text 500 — the UI expects JSON
        raise HTTPException(502, f"Poster generation failed: {e}")


def _generate_posters(req: PosterRequest) -> dict:
    kit = brand.load()
    brand_block = brand.prompt_block(kit)
    docs = knowledge.retrieve(req.topic)
    fresh = research.web_research(req.topic, settings)
    if fresh:
        docs = docs + [fresh]

    # Creative director brainstorms fresh, topic-specific angles each run.
    angles = director.brainstorm_angles(req.topic, settings)
    try:
        variants = content.generate(req.topic, settings, knowledge_docs=docs,
                                    angles=angles, brand_block=brand_block)
    except ValueError as e:
        raise HTTPException(502, f"Could not write poster copy for this topic ({e}). Try rephrasing the topic.")

    base_orientation = "portrait" if req.orientation == "both" else req.orientation
    # Art director selects the best template recipe per concept from a diverse
    # shortlist of the 1,900+ recipe library (biased by brand colors if set).
    try:
        seed = abs(hash(req.topic)) % 997
        pool = recipes.shortlist(_brand_moods(kit), k=15, seed=seed)
        selections = director.select_recipes(variants, pool, settings)
        specs = []
        for sel in selections:
            spec = recipes.recipe_to_spec(sel["recipe"], sel.get("image_subject", ""))
            if kit.get("colors"):
                spec["palette"]["accent"] = kit["colors"][0]
                if len(kit["colors"]) > 1:
                    spec["palette"]["bg"] = kit["colors"][1]
            specs.append(spec)
    except Exception:
        specs = None

    if specs is None:
        # art direction failed entirely — ship one safe poster rather than nothing
        image = artwork.generate("awareness poster background, abstract, no text",
                                 base_orientation, settings)
        pptx = builder.fallback_build(content.to_legacy(variants[0]), image,
                                      base_orientation, settings.out_dir)
        option = {"content": variants[0], "archetype": "standard",
                  "orientation": base_orientation, "quality_score": None,
                  "edit_url": None,
                  "warnings": ["AI art direction failed — standard layout used."],
                  "pptx_download": None}
        try:
            option["edit_url"] = canva.import_design(settings, pptx, variants[0]["headline"])
        except canva.CanvaError as e:
            option["warnings"].append(f"Canva import failed ({e}).")
            option["pptx_download"] = f"/api/download/{pptx.name}"
        return {"options": [option], "knowledge_used": [d["title"] for d in docs]}

    orientations = ["portrait", "landscape"] if req.orientation == "both" else [req.orientation]
    jobs = [(variant, dict(spec), o)
            for variant, spec in zip(variants, specs) for o in orientations]
    with ThreadPoolExecutor(max_workers=4) as pool:
        options = list(pool.map(
            lambda job: _make_option(job[0], job[1], job[2], brand_block),
            jobs,
        ))

    history.remember(specs)
    return {"options": options, "knowledge_used": [d["title"] for d in docs]}


@app.get("/api/download/{filename}")
def download(filename: str):
    base = settings.out_dir.resolve()
    try:
        path = (settings.out_dir / filename).resolve()
    except (OSError, ValueError):
        raise HTTPException(404)
    if not path.is_relative_to(base) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=path.name)

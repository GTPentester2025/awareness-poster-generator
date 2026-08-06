import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from app import artwork, builder, canva, content, design, envfile, knowledge
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
    orientation: Literal["portrait", "landscape"] = "portrait"


class ConfigRequest(BaseModel):
    openai_api_key: str | None = None
    canva_client_id: str | None = None
    canva_client_secret: str | None = None


def _plan_uses_image(spec: dict) -> bool:
    """True when the chosen style uses background artwork, so we only pay for
    image generation when the design actually places one."""
    return spec.get("background_style") == "image"


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


def _make_option(variant: dict, spec: dict, orientation: str) -> dict:
    """Build one poster option end-to-end: image (if styled) → render → import.
    Never raises — failures degrade into warnings/downloads so sibling options
    still ship."""
    warnings: list[str] = []
    image = None
    if _plan_uses_image(spec):
        image = artwork.generate(spec["image_prompt"], orientation, settings)
        if image is None:
            warnings.append("Background image failed — solid background used.")
    try:
        pptx = builder.render(spec, variant, image, orientation, settings.out_dir)
    except Exception as e:
        warnings.append(f"Layout render failed ({e}) — standard layout used.")
        pptx = builder.fallback_build(content.to_legacy(variant), image, orientation, settings.out_dir)

    edit_url = None
    pptx_download = None
    try:
        edit_url = canva.import_design(settings, pptx, variant["headline"])
    except canva.CanvaError as e:
        warnings.append(f"Canva import failed ({e}) — download the PPTX instead.")
        pptx_download = f"/api/download/{pptx.name}"

    return {
        "content": variant,
        "archetype": spec.get("archetype"),
        "edit_url": edit_url,
        "warnings": warnings,
        "pptx_download": pptx_download,
    }


@app.post("/api/posters")
def create_poster(req: PosterRequest):
    if not settings.token_path.exists():
        raise HTTPException(401, "Canva not connected — click Connect Canva first")

    docs = knowledge.retrieve(req.topic)
    variants = content.generate(req.topic, settings, knowledge_docs=docs)

    try:
        specs = design.generate_directions(variants, req.orientation, settings)
    except Exception:
        specs = None

    if specs is None:
        # art direction failed entirely — ship one safe poster rather than nothing
        image = artwork.generate("awareness poster background, abstract, no text",
                                 req.orientation, settings)
        pptx = builder.fallback_build(content.to_legacy(variants[0]), image,
                                      req.orientation, settings.out_dir)
        option = {"content": variants[0], "archetype": "standard", "edit_url": None,
                  "warnings": ["AI art direction failed — standard layout used."],
                  "pptx_download": None}
        try:
            option["edit_url"] = canva.import_design(settings, pptx, variants[0]["headline"])
        except canva.CanvaError as e:
            option["warnings"].append(f"Canva import failed ({e}).")
            option["pptx_download"] = f"/api/download/{pptx.name}"
        return {"options": [option], "knowledge_used": [d["title"] for d in docs]}

    with ThreadPoolExecutor(max_workers=3) as pool:
        options = list(pool.map(
            lambda pair: _make_option(pair[0], pair[1], req.orientation),
            zip(variants, specs),
        ))

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

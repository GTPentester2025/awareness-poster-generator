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
    topic: str = Field(min_length=1, max_length=300)
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

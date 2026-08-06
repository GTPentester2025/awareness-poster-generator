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

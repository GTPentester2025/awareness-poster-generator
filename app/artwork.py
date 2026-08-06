"""Background artwork via gpt-image-1, with two defenses against the model
rendering text inside the image (which clashes with the poster's real
typography): a hardened prompt suffix, and a vision QA pass that inspects the
result and regenerates once if any readable text is detected."""
import base64
import uuid
from pathlib import Path

from app.config import Settings

SIZES = {"portrait": "1024x1536", "landscape": "1536x1024"}

NO_TEXT_SUFFIX = (
    " STRICT RULES: absolutely no text, no letters, no words, no numbers, no typography, "
    "no logos, no watermarks, no signage, no labels anywhere in the image. "
    "Purely visual imagery with calm low-detail areas suitable for overlaying text later."
)


def _generate_once(image_prompt: str, orientation: str, settings: Settings, client) -> Path | None:
    try:
        resp = client.images.generate(
            model="gpt-image-1",
            prompt=image_prompt + NO_TEXT_SUFFIX,
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


def has_text(image_path: Path, settings: Settings, client=None) -> bool | None:
    """Vision QA: does the image contain readable text? None = check failed."""
    try:
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        resp = client.chat.completions.create(
            model=settings.openai_text_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text",
                     "text": "Does this image contain ANY readable text, letters, numbers or words? Answer with exactly YES or NO."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"}},
                ],
            }],
        )
        answer = (resp.choices[0].message.content or "").strip().upper()
        return answer.startswith("YES")
    except Exception:
        return None


def generate(image_prompt: str, orientation: str, settings: Settings, client=None) -> Path | None:
    """Generate background art; QA it for stray text and retry once. Returns
    None on total failure (caller falls back to a non-image background)."""
    if orientation not in SIZES:
        raise ValueError(f"orientation must be one of {sorted(SIZES)}")
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)

    path = _generate_once(image_prompt, orientation, settings, client)
    if path is None:
        return None
    if has_text(path, settings, client=client) is True:
        retry = _generate_once(
            image_prompt + " Zero text of any kind — this is mandatory.",
            orientation, settings, client)
        if retry is not None:
            checked = has_text(retry, settings, client=client)
            if checked is not True:
                return retry
        # both attempts texty or retry failed — return first; scrim + panel keep it usable
    return path

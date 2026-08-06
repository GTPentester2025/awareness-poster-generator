"""Brand kit: optional org identity that steers every poster — brand colors,
what the organization is about (ideology/voice), and org name. Stored in a
local brand.json; absent file means no branding constraints."""
import json
import re
from pathlib import Path

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
DEFAULT_PATH = Path("brand.json")


def load(path: Path | None = None) -> dict:
    path = path or DEFAULT_PATH
    if not path.exists():
        return {"org_name": "", "about": "", "colors": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"org_name": "", "about": "", "colors": []}
    return validate(data)


def validate(data: dict) -> dict:
    if not isinstance(data, dict):
        data = {}
    org = data.get("org_name")
    about = data.get("about")
    colors = data.get("colors")
    return {
        "org_name": org.strip()[:80] if isinstance(org, str) else "",
        "about": about.strip()[:1200] if isinstance(about, str) else "",
        "colors": [c for c in colors if isinstance(c, str) and HEX.match(c)][:6]
        if isinstance(colors, list) else [],
    }


def save(data: dict, path: Path | None = None) -> dict:
    path = path or DEFAULT_PATH
    clean = validate(data)
    path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return clean


def prompt_block(kit: dict) -> str:
    """Serialize the brand kit for LLM prompts. Empty string when unbranded."""
    parts = []
    if kit.get("org_name"):
        parts.append(f"Organization: {kit['org_name']}")
    if kit.get("about"):
        parts.append(f"About the organization / brand voice: {kit['about']}")
    if kit.get("colors"):
        parts.append("Brand colors (build palettes around these, they must appear): "
                     + ", ".join(kit["colors"]))
    return "\n".join(parts)

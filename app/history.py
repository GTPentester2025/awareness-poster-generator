"""Design recency memory: remembers the last runs' archetype/palette/font
combos so the art director can be told to avoid repeating them. Local JSON,
best-effort — any IO failure degrades to no memory."""
import json
from pathlib import Path

DEFAULT_PATH = Path("design_history.json")
KEEP = 12  # remembered combos (~4 runs of 3 options)


def recent(path: Path | None = None) -> list[dict]:
    path = path or DEFAULT_PATH
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def remember(specs: list[dict], path: Path | None = None) -> None:
    path = path or DEFAULT_PATH
    entries = recent(path)
    for s in specs:
        entries.append({
            "archetype": s.get("archetype"),
            "bg": s.get("palette", {}).get("bg"),
            "accent": s.get("palette", {}).get("accent"),
            "heading_font": s.get("fonts", {}).get("heading"),
            "background_style": s.get("background_style"),
        })
    try:
        path.write_text(json.dumps(entries[-KEEP:], indent=1), encoding="utf-8")
    except OSError:
        pass


def avoid_block(path: Path | None = None) -> str:
    """Prompt fragment describing recently used combos to steer away from."""
    entries = recent(path)
    if not entries:
        return ""
    lines = [f"- {e.get('archetype')} / bg {e.get('bg')} / accent {e.get('accent')} / {e.get('heading_font')}"
             for e in entries[-9:]]
    return ("RECENTLY USED COMBINATIONS — do NOT repeat these archetype+palette+font pairings; "
            "pick visibly different directions:\n" + "\n".join(lines))

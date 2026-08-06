"""Read and update a .env file in place, preserving unrelated keys and order."""
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Ignores blanks and # comments. Missing file → {}."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def update_env(path: Path, updates: dict[str, str]) -> None:
    """Apply updates to the .env file. Only keys whose value is a non-empty
    string are written; empty/None values are skipped so a blank UI field
    never wipes an existing secret. Existing keys are updated in place;
    new keys are appended. Comments and unrelated lines are preserved."""
    to_apply = {k: v for k, v in updates.items() if isinstance(v, str) and v.strip()}
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in to_apply:
                out.append(f"{key}={to_apply[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, value in to_apply.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def mask(value: str) -> str:
    """Masked preview: reveal only the last 4 chars so the user can tell a
    real key from a dummy without exposing the secret. Empty → ''."""
    if not value:
        return ""
    if len(value) <= 4:
        return "•" * len(value)
    return "•" * (len(value) - 4) + value[-4:]

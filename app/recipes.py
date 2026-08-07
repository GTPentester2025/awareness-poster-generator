"""Style-recipe library. Crosses the researched 2026 design axes (layouts ×
palettes × font pairings × treatments × image media) into a large catalog of
concrete, mood-coherent recipes. Each recipe maps cleanly onto the renderer's
StyleSpec so any of them can be produced as an editable poster.

The art director (app.director) selects the best recipe per concept from a
diverse shortlist; recipe_to_spec() converts the winner into a StyleSpec."""
import json
from pathlib import Path

LIBRARY_PATH = Path(__file__).resolve().parent.parent / "data" / "design_library.json"

CARD_STYLES = ["filled", "soft_shadow", "outline"]
HEADER_STYLES = ["block", "underline", "badge"]
MOTIFS = ["dots", "rings", "stripes", "none"]

_LIBRARY: dict | None = None
_RECIPES: list[dict] | None = None


def load_library(path: Path | None = None) -> dict:
    global _LIBRARY
    if _LIBRARY is None or path is not None:
        data = json.loads((path or LIBRARY_PATH).read_text(encoding="utf-8"))
        _LIBRARY = data
    return _LIBRARY


def _pick_by_mood(items: list[dict], mood: str, index: int) -> dict:
    """Prefer items matching the mood; deterministically rotate for variety."""
    matches = [it for it in items if it.get("mood") == mood]
    pool = matches if matches else items
    return pool[index % len(pool)]


def build_recipes(path: Path | None = None) -> list[dict]:
    """Materialize the recipe catalog. Deterministic so recipe ids are stable
    across runs (needed for the art director to reference them)."""
    global _RECIPES
    if _RECIPES is not None and path is None:
        return _RECIPES
    lib = load_library(path)
    layouts = lib["layouts"]
    palettes = lib["palettes"]
    fonts = lib["font_pairings"]
    treatments = lib["visual_treatments"]
    media = lib["image_media"]

    recipes: list[dict] = []
    rid = 0
    # Cross every layout with every palette; derive coherent font/treatment/
    # media from the palette's mood. ~33 layouts x 60 palettes = ~1980 recipes.
    for li, layout in enumerate(layouts):
        for pi, palette in enumerate(palettes):
            mood = palette["mood"]
            font = _pick_by_mood(fonts, mood, li + pi)
            treatment = _pick_by_mood(treatments, mood, li * 2 + pi)
            medium = _pick_by_mood(media, mood, li + pi * 2)
            recipes.append({
                "id": rid,
                "layout": layout["name"],
                "archetype": layout["archetype"],
                "background_style": layout["bg"],
                "mood": mood,
                "palette": {"bg": palette["bg"], "surface": palette["surface"],
                            "accent": palette["accent"], "text": palette["text"],
                            "muted": palette.get("muted", "#9AA5B1")},
                "palette_name": palette["name"],
                "fonts": {"heading": font["heading"], "body": font["body"]},
                "card_style": CARD_STYLES[(li + pi) % len(CARD_STYLES)],
                "header_style": HEADER_STYLES[(li + pi) % len(HEADER_STYLES)],
                "motif": MOTIFS[(li * 3 + pi) % len(MOTIFS)],
                "treatment": treatment["name"],
                "image_medium": medium["name"],
            })
            rid += 1
    if path is None:
        _RECIPES = recipes
    return recipes


def all_moods(path: Path | None = None) -> list[str]:
    return sorted({r["mood"] for r in build_recipes(path)})


def shortlist(preferred_moods: list[str], k: int = 15, seed: int = 0,
              path: Path | None = None) -> list[dict]:
    """A diverse shortlist for the art director: spread across moods and
    archetypes so the three chosen options can differ sharply. `seed` (e.g. a
    hash of the topic) rotates the selection run-to-run."""
    recipes = build_recipes(path)
    pref = [r for r in recipes if not preferred_moods or r["mood"] in preferred_moods]
    pool = pref if len(pref) >= k else recipes
    # stride sampling for spread, offset by seed
    step = max(1, len(pool) // k)
    picked, seen_arch = [], {}
    i = seed % len(pool)
    guard = 0
    while len(picked) < k and guard < len(pool) * 2:
        r = pool[i % len(pool)]
        arch = r["archetype"]
        if seen_arch.get(arch, 0) < 2:  # cap repeats of one archetype in the shortlist
            picked.append(r)
            seen_arch[arch] = seen_arch.get(arch, 0) + 1
        i += step
        guard += 1
    if len(picked) < k:  # fallback: fill without the cap
        for r in pool:
            if r not in picked:
                picked.append(r)
            if len(picked) >= k:
                break
    return picked[:k]


def get(recipe_id: int, path: Path | None = None) -> dict | None:
    recipes = build_recipes(path)
    if 0 <= recipe_id < len(recipes) and recipes[recipe_id]["id"] == recipe_id:
        return recipes[recipe_id]
    for r in recipes:
        if r["id"] == recipe_id:
            return r
    return None


def summarize(recipe: dict) -> dict:
    """Compact view handed to the art director for selection."""
    return {
        "id": recipe["id"],
        "layout": recipe["layout"],
        "mood": recipe["mood"],
        "palette": recipe["palette_name"],
        "colors": [recipe["palette"]["bg"], recipe["palette"]["accent"]],
        "fonts": f"{recipe['fonts']['heading']} / {recipe['fonts']['body']}",
        "treatment": recipe["treatment"],
        "image_medium": recipe["image_medium"],
        "background_style": recipe["background_style"],
    }


def recipe_to_spec(recipe: dict, image_subject: str = "") -> dict:
    """Convert a recipe (+ optional topic-specific image subject) into a
    renderer StyleSpec. The image prompt fuses the subject with the recipe's
    media + treatment for on-trend, on-topic artwork."""
    subject = image_subject.strip() or "evocative abstract background related to the topic"
    image_prompt = (f"{subject}; {recipe['image_medium']} style; {recipe['treatment']}; "
                    f"editorial poster background, tasteful negative space")
    return {
        "archetype": recipe["archetype"],
        "palette": dict(recipe["palette"]),
        "fonts": dict(recipe["fonts"]),
        "background_style": recipe["background_style"],
        "card_style": recipe["card_style"],
        "header_style": recipe["header_style"],
        "accent_shapes": True,
        "motif": recipe["motif"],
        "image_prompt": image_prompt,
        "recipe_id": recipe["id"],
        "layout": recipe["layout"],
        "palette_name": recipe["palette_name"],
    }

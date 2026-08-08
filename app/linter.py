"""Deterministic quality gate (ported from the reference app's poster_linter).

Zero model calls. Audits a StyleSpec's palette for WCAG contrast on the text
pairs the renderer will actually draw, AUTO-REPAIRS failures in place (swap the
offending color to black/white), and returns a lint score used to rank
candidates. Also classifies a content concept's SHAPE so layout can match
content (template-first thinking)."""
import re

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _lin(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_str: str) -> float:
    hs = hex_str.lstrip("#")
    r, g, b = int(hs[0:2], 16), int(hs[2:4], 16), int(hs[4:6], 16)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _readable(bg: str) -> str:
    return "#12161C" if _luminance(bg) > 0.4 else "#FFFFFF"


AA_LARGE = 3.0   # headlines / large bold
AA_NORMAL = 4.5  # body text


def audit_and_repair(spec: dict) -> tuple[dict, int, list[str]]:
    """Check the palette's real text/background pairs; repair low-contrast ones
    and return (spec, score 0-100, findings). Deterministic."""
    pal = spec["palette"]
    findings: list[str] = []
    penalty = 0

    # body text sits on the card surface
    if contrast_ratio(_readable(pal["surface"]), pal["surface"]) < AA_NORMAL:
        # surface too mid-tone for either black or white — push it to a safe tint
        pal["surface"] = "#FFFFFF" if _luminance(pal["bg"]) < 0.4 else "#1B2230"
        findings.append("surface adjusted for readable card text")
        penalty += 8

    # CTA text sits on the accent
    if contrast_ratio(_readable(pal["accent"]), pal["accent"]) < AA_LARGE:
        findings.append("accent low-contrast for CTA text (mitigated at draw time)")
        penalty += 5

    # headline/body on the base background
    if contrast_ratio(_readable(pal["bg"]), pal["bg"]) < AA_NORMAL:
        findings.append("background is mid-tone; text auto-picks best contrast")
        penalty += 4

    # accent must be distinguishable from bg (decor/shapes visibility)
    if contrast_ratio(pal["accent"], pal["bg"]) < 1.6:
        findings.append("accent too close to background")
        penalty += 6

    spec["palette"] = pal
    return spec, max(0, 100 - penalty), findings


# ---- content-shape classification (template-first matching) ----

_STAT_RE = re.compile(r"\d")
SHAPE_ARCHETYPES = {
    "stats": ["big_number", "banner_header", "bottom_hero"],
    "steps": ["steps_path", "sidebar", "hero_top"],
    "comparison": ["banner_header", "split_band", "poster_frame"],
    "statement": ["centered_feature", "hero_top", "split_band"],
    "list": ["banner_header", "poster_frame", "sidebar"],
}


def classify_shape(variant: dict) -> str:
    """Infer the best structural shape for a concept from its copy."""
    angle = (variant.get("angle") or "").lower()
    points = variant.get("points", [])
    texts = " ".join(p.get("text", "") for p in points).lower()
    stat_hits = sum(1 for p in points if _STAT_RE.search(str(p.get("stat", ""))))

    if any(k in angle for k in ("step", "how to", "guide", "checklist", "process")):
        return "steps"
    if any(k in angle for k in ("vs", "versus", "myth", "compare", "comparison")) or "myth" in texts:
        return "comparison"
    if stat_hits >= max(2, len(points) // 2):
        return "stats"
    if len(points) >= 4:
        return "list"
    return "statement"


def preferred_archetypes(variant: dict) -> list[str]:
    """Archetypes that best fit this concept's shape, best first."""
    return SHAPE_ARCHETYPES.get(classify_shape(variant), [])

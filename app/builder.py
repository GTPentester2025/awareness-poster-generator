import uuid
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

A4_EMU = {
    "portrait": (7_560_000, 10_692_000),
    "landscape": (10_692_000, 7_560_000),
}


def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str.lstrip("#"))


def _set_fill_alpha(shape, transparency_pct: int) -> None:
    """Add alpha to a solid fill. transparency_pct=40 → 60% opaque.

    Primary variant: shape.fill.fore_color._xFill is the <a:solidFill> element
    in python-pptx 1.0.2. If it fails, falls back to traversing _xPr.
    """
    try:
        srgb = shape.fill.fore_color._xFill.find(qn("a:srgbClr"))
        if srgb is None:
            raise AttributeError("srgbClr not found via _xFill")
    except AttributeError:
        # Fallback for python-pptx versions where _xFill differs
        srgb = shape.fill._xPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
    alpha = srgb.makeelement(qn("a:alpha"), {"val": str((100 - transparency_pct) * 1000)})
    srgb.append(alpha)


def _add_rect(slide, x, y, w, h, hex_color, transparency_pct=0):
    from pptx.enum.shapes import MSO_SHAPE
    rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x), Emu(y), Emu(w), Emu(h))
    rect.fill.solid()
    rect.fill.fore_color.rgb = _rgb(hex_color)
    rect.line.fill.background()
    if transparency_pct:
        _set_fill_alpha(rect, transparency_pct)
    return rect


def _add_text(slide, x, y, w, h, text, size_pt, hex_color, bold=False, align=PP_ALIGN.LEFT, font=None):
    box = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    para = tf.paragraphs[0]
    para.alignment = align
    run = para.add_run()
    run.text = text
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = _rgb(hex_color)
    if font:
        run.font.name = font
    return box


_ALIGN_MAP = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}


def _add_auto_shape(slide, shape_name, x, y, w, h, hex_color, opacity=1.0):
    from pptx.enum.shapes import MSO_SHAPE
    enum = {"rect": MSO_SHAPE.RECTANGLE, "line": MSO_SHAPE.RECTANGLE,
            "ellipse": MSO_SHAPE.OVAL}.get(shape_name, MSO_SHAPE.RECTANGLE)
    shp = slide.shapes.add_shape(enum, Emu(x), Emu(y), Emu(max(w, 1)), Emu(max(h, 1)))
    shp.fill.solid()
    shp.fill.fore_color.rgb = _rgb(hex_color)
    shp.line.fill.background()
    transparency_pct = int(round((1.0 - opacity) * 100))
    if transparency_pct:
        _set_fill_alpha(shp, transparency_pct)
    return shp


def render(plan: dict, image: Path | None, orientation: str, out_dir: Path) -> Path:
    """Render a free-form LayoutPlan (from app.design) into an editable PPTX.
    Draws background per plan, then each element in array order (later on top)."""
    if orientation not in A4_EMU:
        raise ValueError(f"orientation must be one of {sorted(A4_EMU)}")
    w, h = A4_EMU[orientation]
    pal = plan["palette"]
    bg = plan.get("background", {"mode": "solid"})
    mode = bg.get("mode", "solid")

    prs = Presentation()
    prs.slide_width = Emu(w)
    prs.slide_height = Emu(h)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    def rect(el):
        return (int(el["x"] * w), int(el["y"] * h), int(el["w"] * w), int(el["h"] * h))

    # ---- background ----
    if mode == "image_full" and image is not None:
        slide.shapes.add_picture(str(image), 0, 0, Emu(w), Emu(h))
    elif mode == "image_panel" and image is not None:
        _add_rect(slide, 0, 0, w, h, pal["bg"])
        panel = bg.get("panel") if isinstance(bg.get("panel"), dict) else {"x": 0.5, "y": 0, "w": 0.5, "h": 1}
        px, py, pw, ph = rect({"x": panel.get("x", 0.5), "y": panel.get("y", 0),
                               "w": panel.get("w", 0.5), "h": panel.get("h", 1)})
        slide.shapes.add_picture(str(image), Emu(px), Emu(py), Emu(pw), Emu(ph))
    else:
        # solid (also the fallback for gradient and for image modes with no image)
        _add_rect(slide, 0, 0, w, h, pal["bg"])

    # ---- elements ----
    for el in plan["elements"]:
        ex, ey, ew, eh = rect(el)
        if el["type"] == "text":
            _add_text(slide, ex, ey, ew, eh, el["text"], el["size_pt"], el["color"],
                      bold=(el["weight"] == "bold"),
                      align=_ALIGN_MAP.get(el["align"], PP_ALIGN.LEFT),
                      font=el["font"])
        elif el["type"] == "shape":
            _add_auto_shape(slide, el["shape"], ex, ey, ew, eh, el["color"], el.get("opacity", 1.0))
        elif el["type"] == "image" and image is not None:
            slide.shapes.add_picture(str(image), Emu(ex), Emu(ey), Emu(ew), Emu(eh))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"poster_{uuid.uuid4().hex[:8]}.pptx"
    prs.save(str(path))
    return path


def build(content: dict, image: Path | None, orientation: str, out_dir: Path) -> Path:
    if orientation not in A4_EMU:
        raise ValueError(f"orientation must be one of {sorted(A4_EMU)}")
    w, h = A4_EMU[orientation]
    pal = content["palette"]

    prs = Presentation()
    prs.slide_width = Emu(w)
    prs.slide_height = Emu(h)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    if image is not None:
        slide.shapes.add_picture(str(image), 0, 0, Emu(w), Emu(h))
        _add_rect(slide, 0, 0, w, h, pal["bg"], transparency_pct=55)
    else:
        _add_rect(slide, 0, 0, w, h, pal["bg"])
        _add_rect(slide, 0, int(h * 0.92), w, int(h * 0.08), pal["accent"])
        _add_rect(slide, int(w * 0.82), 0, int(w * 0.18), int(h * 0.25), pal["accent"], transparency_pct=30)

    margin = int(w * 0.08)
    cw = w - 2 * margin
    headline_size = 44 if orientation == "portrait" else 40

    _add_text(slide, margin, int(h * 0.07), cw, int(h * 0.14),
              content["headline"], headline_size, pal["text"], bold=True, align=PP_ALIGN.CENTER)
    _add_text(slide, margin, int(h * 0.21), cw, int(h * 0.08),
              content["subheadline"], 20, pal["text"], align=PP_ALIGN.CENTER)

    facts_top = int(h * 0.34)
    row_h = int(h * 0.40 / len(content["facts"]))
    for i, fact in enumerate(content["facts"]):
        _add_rect(slide, margin, facts_top + i * row_h, int(w * 0.012), int(row_h * 0.72), pal["accent"])
        _add_text(slide, margin + int(w * 0.03), facts_top + i * row_h, cw - int(w * 0.03), int(row_h * 0.8),
                  fact, 16, pal["text"])

    cta_top = int(h * 0.80)
    _add_rect(slide, margin, cta_top, cw, int(h * 0.10), pal["accent"])
    _add_text(slide, margin, cta_top + int(h * 0.025), cw, int(h * 0.05),
              content["cta"], 24, pal["bg"], bold=True, align=PP_ALIGN.CENTER)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"poster_{uuid.uuid4().hex[:8]}.pptx"
    prs.save(str(path))
    return path


# Kept as the safety net when AI layout generation or validation fails.
fallback_build = build

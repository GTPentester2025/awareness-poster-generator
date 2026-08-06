import base64

import pytest
from pptx import Presentation

from app.builder import A4_EMU, render
from tests.test_design import VALID_PLAN
from tests.test_artwork import PNG_1PX


def _load(path):
    prs = Presentation(str(path))
    slide = prs.slides[0]
    texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
    return prs, slide, texts


@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_render_solid_has_text(tmp_path, orientation):
    p = render(VALID_PLAN, None, orientation, tmp_path)
    prs, slide, texts = _load(p)
    assert (prs.slide_width, prs.slide_height) == A4_EMU[orientation]
    joined = "\n".join(texts)
    assert "Save Water" in joined
    assert "Every drop counts" in joined


def test_render_bad_orientation(tmp_path):
    with pytest.raises(ValueError):
        render(VALID_PLAN, None, "square", tmp_path)


def test_render_image_full(tmp_path):
    img = tmp_path / "bg.png"
    img.write_bytes(base64.b64decode(PNG_1PX))
    plan = dict(VALID_PLAN)
    plan = {**VALID_PLAN, "background": {"mode": "image_full"}}
    p = render(plan, img, "portrait", tmp_path)
    prs, slide, _ = _load(p)
    pics = [s for s in slide.shapes if s.shape_type == 13]  # PICTURE
    assert len(pics) == 1
    assert (pics[0].width, pics[0].height) == A4_EMU["portrait"]


def test_render_image_mode_without_image_falls_back(tmp_path):
    plan = {**VALID_PLAN, "background": {"mode": "image_full"}}
    p = render(plan, None, "portrait", tmp_path)
    prs, slide, texts = _load(p)
    # no picture, but still renders text on a solid background
    pics = [s for s in slide.shapes if s.shape_type == 13]
    assert len(pics) == 0
    assert "Save Water" in "\n".join(texts)


def test_render_font_applied(tmp_path):
    p = render(VALID_PLAN, None, "portrait", tmp_path)
    prs, slide, _ = _load(p)
    fonts = set()
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if run.font.name:
                        fonts.add(run.font.name)
    assert "Anton" in fonts  # heading font from the plan

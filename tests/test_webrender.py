import pytest

from app import webrender
from app.config import Settings
from pathlib import Path

SETTINGS = Settings(
    openai_api_key="sk-test", openai_text_model="gpt-4o-mini",
    canva_client_id="c", canva_client_secret="s",
    base_url="http://127.0.0.1:8000", out_dir=Path("out"), token_path=Path("token.json"),
)

VARIANT = {
    "headline": "Every Minute Without Fire Safety Costs Lives",
    "subheadline": "Ignoring fire safety puts lives at risk.",
    "points": [{"stat": "$932M", "text": "Workplace fires caused $932 million in damage."},
               {"stat": "81", "text": "81 firefighters lost their lives in 2025."}],
    "cta": "Enhance your fire safety today", "sources": ["FEMA"],
}
SPEC = {"palette": {"bg": "#0D0E12", "surface": "#1A1C22", "accent": "#A6FF00", "text": "#F5F7FA", "muted": "#9AA5B1"},
        "fonts": {"heading": "Oswald", "body": "Merriweather"}, "layout": "Vertical Timeline", "treatment": "clean"}

GOOD_HTML = ("<!doctype html><html><head></head><body>"
             "<h1>Every Minute Without Fire Safety Costs Lives</h1>"
             "<p>Ignoring fire safety puts lives at risk.</p></body></html>")


class FakeResp:
    def __init__(self, text):
        self.choices = [type("C", (), {"message": type("M", (), {"content": text})})]


class FakeClient:
    def __init__(self, text):
        self.text = text
        self.chat = type("Chat", (), {"completions": type("X", (), {"create": self._create})()})()

    def _create(self, **kw):
        return FakeResp(self.text)


def test_build_html_returns_document():
    html = webrender.build_html(VARIANT, SPEC, "portrait", SETTINGS, client=FakeClient(GOOD_HTML))
    assert html.lower().startswith("<!doctype html>")
    assert "Every Minute" in html


def test_build_html_strips_markdown_fence():
    fenced = "```html\n" + GOOD_HTML + "\n```"
    html = webrender.build_html(VARIANT, SPEC, "portrait", SETTINGS, client=FakeClient(fenced))
    assert html.lower().startswith("<!doctype html>")
    assert "```" not in html


def test_build_html_rejects_missing_headline():
    with pytest.raises(ValueError):
        webrender.build_html(VARIANT, SPEC, "portrait", SETTINGS,
                             client=FakeClient("<!doctype html><html><body>nope</body></html>"))


def test_build_html_bad_orientation():
    with pytest.raises(ValueError):
        webrender.build_html(VARIANT, SPEC, "square", SETTINGS, client=FakeClient(GOOD_HTML))

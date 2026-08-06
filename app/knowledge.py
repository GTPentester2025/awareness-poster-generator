"""Curated knowledge base: markdown fact sheets in knowledge/ with YAML-ish
front matter (title, keywords). retrieve() scores files by keyword overlap
with the topic and returns the best matches to ground poster content."""
import re
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
MAX_CHARS_PER_DOC = 2400


def _parse(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return None
    header, body = m.group(1), m.group(2)
    fields = {}
    for line in header.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip().lower()] = value.strip()
    keywords = {k.strip().lower() for k in fields.get("keywords", "").split(",") if k.strip()}
    if not keywords:
        return None
    return {
        "title": fields.get("title", path.stem),
        "keywords": keywords,
        "body": body.strip()[:MAX_CHARS_PER_DOC],
    }


def load_all(base: Path | None = None) -> list[dict]:
    base = base or KNOWLEDGE_DIR
    if not base.is_dir():
        return []
    docs = []
    for path in sorted(base.glob("*.md")):
        doc = _parse(path)
        if doc:
            docs.append(doc)
    return docs


MIN_SCORE = 3  # a full-keyword hit; stray single-word overlaps stay below this


def _score(topic_words: set[str], doc: dict) -> int:
    score = 0
    for kw in doc["keywords"]:
        kw_words = set(kw.split())
        if kw in topic_words or kw_words <= topic_words:
            score += 3  # whole keyword (or every word of a phrase) present
        elif any(w in topic_words for w in kw_words):
            score += 1  # weak partial: one word of a multi-word phrase
    return score


def retrieve(topic: str, base: Path | None = None, top_n: int = 2) -> list[dict]:
    """Top matching docs for a topic, or [] when nothing is clearly relevant."""
    topic_words = set(re.findall(r"[a-z0-9]+", topic.lower()))
    scored = [(_score(topic_words, d), d) for d in load_all(base)]
    scored = [(s, d) for s, d in scored if s >= MIN_SCORE]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [d for _, d in scored[:top_n]]

from app.knowledge import load_all, retrieve

GDPR = """---
title: GDPR (EU)
keywords: gdpr, europe, eu, privacy, data protection, personal data, consent
---

# GDPR

## Key facts
- Fines up to 4% of global turnover (Art. 83)
"""

PHISHING = """---
title: Phishing (CISA)
keywords: phishing, email, scam, cyber, social engineering
---

# Phishing

## Key facts
- Check sender addresses carefully
"""


def _kb(tmp_path):
    (tmp_path / "gdpr.md").write_text(GDPR, encoding="utf-8")
    (tmp_path / "phishing.md").write_text(PHISHING, encoding="utf-8")
    return tmp_path


def test_load_all_parses_front_matter(tmp_path):
    docs = load_all(_kb(tmp_path))
    assert len(docs) == 2
    titles = {d["title"] for d in docs}
    assert titles == {"GDPR (EU)", "Phishing (CISA)"}
    gdpr = next(d for d in docs if d["title"] == "GDPR (EU)")
    assert "gdpr" in gdpr["keywords"]
    assert "4% of global turnover" in gdpr["body"]


def test_retrieve_matches_topic(tmp_path):
    kb = _kb(tmp_path)
    docs = retrieve("gdpr awareness for employees", base=kb)
    assert docs and docs[0]["title"] == "GDPR (EU)"


def test_retrieve_multiword_keyword(tmp_path):
    kb = _kb(tmp_path)
    docs = retrieve("protecting personal data in the EU", base=kb)
    assert any(d["title"] == "GDPR (EU)" for d in docs)


def test_retrieve_unrelated_topic_empty(tmp_path):
    kb = _kb(tmp_path)
    assert retrieve("road safety for teenagers", base=kb) == []


def test_retrieve_missing_dir():
    from pathlib import Path
    assert retrieve("anything", base=Path("does/not/exist")) == []


def test_file_without_front_matter_skipped(tmp_path):
    (tmp_path / "junk.md").write_text("# no front matter here", encoding="utf-8")
    assert load_all(tmp_path) == []

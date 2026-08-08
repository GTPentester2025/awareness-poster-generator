from app import linter


def test_contrast_ratio_extremes():
    assert round(linter.contrast_ratio("#000000", "#FFFFFF"), 1) == 21.0
    assert round(linter.contrast_ratio("#FFFFFF", "#FFFFFF"), 1) == 1.0


def _spec(bg, surface, accent):
    return {"palette": {"bg": bg, "surface": surface, "accent": accent,
                        "text": "#FFFFFF", "muted": "#9AA5B1"}}


def test_audit_passes_good_palette():
    spec, score, findings = linter.audit_and_repair(_spec("#0F172A", "#1B2438", "#4FE0B0"))
    assert score >= 90
    assert not any("card text" in f for f in findings)


def test_audit_repairs_bad_surface():
    # mid-tone surface where neither black nor white reads well
    spec, score, findings = linter.audit_and_repair(_spec("#0F172A", "#808080", "#4FE0B0"))
    assert spec["palette"]["surface"] != "#808080"  # repaired
    assert score < 100


def test_audit_flags_accent_close_to_bg():
    spec, score, findings = linter.audit_and_repair(_spec("#101010", "#FFFFFF", "#151515"))
    assert any("accent" in f.lower() for f in findings)


def test_classify_stats():
    v = {"angle": "the numbers", "points": [{"stat": "61%", "text": "x"}, {"stat": "16,500", "text": "y"},
                                            {"stat": "$932M", "text": "z"}]}
    assert linter.classify_shape(v) == "stats"


def test_classify_steps():
    v = {"angle": "how to turn on MFA", "points": [{"stat": "1", "text": "a"}, {"stat": "2", "text": "b"}]}
    assert linter.classify_shape(v) == "steps"


def test_classify_comparison():
    v = {"angle": "myth vs fact", "points": [{"stat": "Myth", "text": "phishing is rare"},
                                             {"stat": "Fact", "text": "it is common"}]}
    assert linter.classify_shape(v) == "comparison"


def test_preferred_archetypes_nonempty():
    v = {"angle": "the numbers", "points": [{"stat": "61%", "text": "x"}, {"stat": "9%", "text": "y"}]}
    prefs = linter.preferred_archetypes(v)
    assert "big_number" in prefs

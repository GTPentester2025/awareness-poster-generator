from app import brand, history


def test_brand_load_missing(tmp_path):
    assert brand.load(tmp_path / "nope.json") == {"org_name": "", "about": "", "colors": []}


def test_brand_save_validates(tmp_path):
    p = tmp_path / "brand.json"
    out = brand.save({"org_name": " Acme ", "about": "x" * 2000,
                      "colors": ["#123456", "red", "#ABCDEF", 5]}, p)
    assert out["org_name"] == "Acme"
    assert len(out["about"]) == 1200
    assert out["colors"] == ["#123456", "#ABCDEF"]
    assert brand.load(p) == out


def test_brand_prompt_block():
    assert brand.prompt_block({"org_name": "", "about": "", "colors": []}) == ""
    block = brand.prompt_block({"org_name": "Acme", "about": "Safety first", "colors": ["#112233"]})
    assert "Acme" in block and "#112233" in block and "Safety first" in block


def test_history_roundtrip(tmp_path):
    p = tmp_path / "hist.json"
    assert history.recent(p) == []
    assert history.avoid_block(p) == ""
    specs = [{"archetype": "hero_top",
              "palette": {"bg": "#111111", "accent": "#222222"},
              "fonts": {"heading": "Anton"}, "background_style": "image"}]
    history.remember(specs, p)
    entries = history.recent(p)
    assert entries[0]["archetype"] == "hero_top"
    block = history.avoid_block(p)
    assert "hero_top" in block and "#111111" in block


def test_history_caps_entries(tmp_path):
    p = tmp_path / "hist.json"
    spec = {"archetype": "sidebar", "palette": {"bg": "#000000", "accent": "#FFFFFF"},
            "fonts": {"heading": "Lato"}, "background_style": "solid"}
    for _ in range(10):
        history.remember([spec, spec], p)
    assert len(history.recent(p)) == history.KEEP


def test_history_corrupt_file(tmp_path):
    p = tmp_path / "hist.json"
    p.write_text("{not json", encoding="utf-8")
    assert history.recent(p) == []

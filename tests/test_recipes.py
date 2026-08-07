from app import recipes
from app.design import ARCHETYPES, validate_spec


def test_library_builds_large_catalog():
    r = recipes.build_recipes()
    assert len(r) >= 600  # user asked for a big library
    ids = [x["id"] for x in r]
    assert ids == list(range(len(r)))  # stable, contiguous ids


def test_every_recipe_maps_to_a_real_archetype():
    for r in recipes.build_recipes():
        assert r["archetype"] in ARCHETYPES


def test_recipe_to_spec_is_valid_stylespec():
    r = recipes.get(0)
    spec = recipes.recipe_to_spec(r, "a padlock over a phishing hook")
    validated = validate_spec(dict(spec))  # must survive the renderer's validator
    assert validated["archetype"] in ARCHETYPES
    assert "padlock" in spec["image_prompt"]
    assert r["image_medium"] in spec["image_prompt"]


def test_shortlist_is_diverse_and_sized():
    sl = recipes.shortlist(["urgent", "activist"], k=12, seed=5)
    assert len(sl) == 12
    archs = [r["archetype"] for r in sl]
    # no archetype dominates the shortlist
    assert max(archs.count(a) for a in set(archs)) <= 2


def test_shortlist_seed_varies_selection():
    a = [r["id"] for r in recipes.shortlist([], k=10, seed=1)]
    b = [r["id"] for r in recipes.shortlist([], k=10, seed=500)]
    assert a != b


def test_get_returns_none_for_bad_id():
    assert recipes.get(10_000_000) is None

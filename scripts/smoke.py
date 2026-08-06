"""Manual end-to-end smoke test. Needs real .env and a connected Canva token.

Run:  .venv\\Scripts\\python scripts\\smoke.py "topic here" [portrait|landscape]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import artwork, builder, canva, content, design, knowledge
from app.config import load_settings


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "hand washing and hygiene"
    orientation = sys.argv[2] if len(sys.argv) > 2 else "portrait"
    settings = load_settings()

    print(f"[1/5] knowledge for: {topic!r}")
    docs = knowledge.retrieve(topic)
    print(f"      matched: {[d['title'] for d in docs] or 'none'}")

    print("[2/5] content — 3 variants")
    variants = content.generate(topic, settings, knowledge_docs=docs)
    for v in variants:
        print(f"      [{v['angle']}] {v['headline']} ({len(v['points'])} points)")

    print("[3/5] art direction — 3 distinct specs")
    specs = design.generate_directions(variants, orientation, settings)
    for s in specs:
        print(f"      {s['archetype']} | bg={s['background_style']} | {s['fonts']['heading']}")

    print("[4/5] render + [5/5] import per option")
    for i, (variant, spec) in enumerate(zip(variants, specs), 1):
        image = None
        if spec["background_style"] == "image":
            image = artwork.generate(spec["image_prompt"], orientation, settings)
        pptx = builder.render(spec, variant, image, orientation, settings.out_dir)
        url = canva.import_design(settings, pptx, variant["headline"])
        print(f"      option {i}: {url}")


if __name__ == "__main__":
    main()

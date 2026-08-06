"""Manual end-to-end smoke test. Needs real .env and a connected Canva token.

Run:  .venv\\Scripts\\python scripts\\smoke.py "topic here" [portrait|landscape]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import artwork, builder, canva, content
from app.config import load_settings


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "hand washing and hygiene"
    orientation = sys.argv[2] if len(sys.argv) > 2 else "portrait"
    settings = load_settings()

    print(f"[1/4] content for: {topic!r}")
    data = content.generate(topic, settings)
    print(f"      headline: {data['headline']}")

    print("[2/4] background image")
    image = artwork.generate(data["image_prompt"], orientation, settings)
    print(f"      {'ok: ' + str(image) if image else 'FAILED — using fallback'}")

    print("[3/4] building pptx")
    pptx = builder.build(data, image, orientation, settings.out_dir)
    print(f"      {pptx}")

    print("[4/4] importing to Canva")
    url = canva.import_design(settings, pptx, data["headline"])
    print(f"\nEDIT URL: {url}")


if __name__ == "__main__":
    main()

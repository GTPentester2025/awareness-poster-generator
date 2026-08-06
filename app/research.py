"""Live web research at generation time via OpenAI's hosted web_search tool.
Pulls current statistics/facts about the topic from credible sources
(government, international bodies, established institutions). Returns a
knowledge-doc-shaped dict so it merges with the local knowledge base.
Fails soft: any error returns None and the pipeline continues without it."""
import json

from app.config import Settings

RESEARCH_PROMPT = """Search the web for the LATEST verifiable facts and statistics about:
"{topic}"

Rules:
- Prefer primary/credible sources ONLY: government sites (.gov, .gov.in, europa.eu),
  international bodies (WHO, UN, ENISA), standards bodies (NIST, ISO), CISA/FBI/IC3,
  or major peer-reviewed/official reports. Ignore blogs, vendors, and content farms.
- Collect 5-8 short poster-usable facts, each with a specific number/date where possible.
- Note the source name for each fact.

Return ONLY JSON:
{{"facts": [{{"text": "<one-line fact>", "source": "<short source name, e.g. 'WHO 2026'>"}}],
  "as_of": "<month year of the most recent data found>"}}"""


def web_research(topic: str, settings: Settings, client=None) -> dict | None:
    try:
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
        resp = client.responses.create(
            model=settings.openai_text_model,
            tools=[{"type": "web_search_preview"}],
            input=RESEARCH_PROMPT.format(topic=topic),
        )
        text = resp.output_text
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        data = json.loads(text[start:end + 1])
        facts = data.get("facts")
        if not isinstance(facts, list) or not facts:
            return None
        lines = []
        for f in facts[:8]:
            if isinstance(f, dict) and isinstance(f.get("text"), str) and f["text"].strip():
                src = f.get("source") if isinstance(f.get("source"), str) else ""
                lines.append(f"- {f['text'].strip()}" + (f" (Source: {src.strip()})" if src.strip() else ""))
        if not lines:
            return None
        as_of = data.get("as_of") if isinstance(data.get("as_of"), str) else ""
        title = f"Live web research{f' (as of {as_of})' if as_of else ''}"
        return {"title": title, "keywords": set(), "body": "\n".join(lines)}
    except Exception:
        return None

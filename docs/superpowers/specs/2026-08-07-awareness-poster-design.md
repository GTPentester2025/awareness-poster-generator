# Awareness Poster Generator — Design

**Date:** 2026-08-07
**Status:** Approved by user (sections reviewed in conversation)

## Purpose

A local web app that turns a user's prompt about an awareness topic (e.g. "road safety for teens", "World Diabetes Day") into a finished A4 awareness poster, imports it into Canva via the Canva Connect API, and returns the Canva edit URL so the user can make final tweaks in the Canva editor.

Workflow modeled on the Canva Connect API demo shown in the reference video (Meredith Hassett, Canva developer advocate): a third-party app pushes design data into Canva; the user finishes editing inside Canva.

## Constraints

- **No Canva Enterprise.** Brand-template autofill APIs are unavailable. Instead we use the Connect **design import** endpoint (available to free accounts): upload a PPTX, Canva converts it into an editable design.
- **PPTX is the import format** because Canva converts PPTX text boxes into native, editable Canva text. A flat PNG import would not be editable — rejected.
- **OpenAI APIs** for generation: a chat model for poster copy and design spec (default `gpt-4o-mini`, overridable via `OPENAI_TEXT_MODEL` env var), `gpt-image-1` for the background image (used only when needed; fallback exists).
- Single user, localhost only. No database.
- Poster sizes: A4 portrait and A4 landscape (user picks per poster in the UI).

## Architecture & Flow

```
Browser (static single page)
   │  POST /api/posters {topic, orientation}
   ▼
FastAPI backend
   1. content.py  — OpenAI chat → poster content JSON
      {headline, subheadline, facts[3–5], cta,
       palette {bg, accent, text}, image_prompt}
      (schema-validated; retry once on invalid JSON)
   2. artwork.py  — gpt-image-1 background
      portrait 1024×1536 / landscape 1536×1024;
      prompt requests clear space for text overlay
   3. builder.py  — python-pptx builds one A4 slide:
      full-bleed background image, translucent overlay
      shape for readability, real text boxes for
      headline / subheadline / facts / CTA
   4. canva.py    — Connect API design import:
      create import job (upload PPTX) → poll job
      (~60 s max) → design id + edit URL
   ▼
Browser shows content summary, background preview, "Edit in Canva" link
```

### Canva auth

- OAuth 2.0 with PKCE against a Connect integration the user creates at canva.com/developers (free).
- One-time flow: `/auth/canva` → Canva consent → `/auth/canva/callback` stores access + refresh token in local `token.json`.
- Tokens auto-refresh; if no valid token, the UI shows a "Connect Canva" button instead of failing.

### Config

`.env` (gitignored): `OPENAI_API_KEY`, `CANVA_CLIENT_ID`, `CANVA_CLIENT_SECRET`.
Redirect URI: `http://127.0.0.1:8000/auth/canva/callback` (must match the integration settings in the Canva developer portal).

## Components

```
poster_try/
├─ app/
│  ├─ main.py          # FastAPI app, routes, static file serving
│  ├─ content.py       # OpenAI chat → validated poster content dict
│  ├─ artwork.py       # gpt-image-1 background generation
│  ├─ builder.py       # python-pptx A4 poster construction
│  ├─ canva.py         # OAuth PKCE, import job, poll, edit URL
│  └─ config.py        # env loading
├─ static/index.html   # UI: topic input, orientation toggle, result panel
├─ out/                # generated pptx/png artifacts (gitignored)
├─ .env                # secrets (gitignored)
└─ tests/
```

Module contracts (each testable in isolation):

- `content.generate(topic) -> dict` — validated against a fixed JSON schema.
- `artwork.generate(image_prompt, orientation) -> Path | None` — `None` on failure triggers fallback.
- `builder.build(content: dict, image: Path | None, orientation) -> Path` — returns PPTX path; when `image is None`, renders palette-colored background with simple shapes instead.
- `canva.import_design(pptx: Path, title: str) -> str` — returns Canva edit URL; raises typed errors (`NotAuthenticated`, `ImportFailed`, `ImportTimeout`).

## Error handling

| Failure | Behavior |
|---|---|
| OpenAI content call fails / invalid JSON twice | Error surfaced in UI with retry button |
| Image generation fails | Fallback: palette-colored background + shapes; poster still produced |
| No/expired Canva token | UI shows "Connect Canva" button → OAuth flow; refresh token used automatically when possible |
| Import job fails or exceeds ~60 s poll | UI offers the generated PPTX as a download so work isn't lost |

## Testing

- **Unit (no network):** content JSON schema validation (accept/reject cases); builder output is a valid PPTX with A4 dimensions and expected text boxes, both orientations.
- **Integration (manual, needs keys):** full pipeline smoke test producing a real Canva edit URL.

## Out of scope (YAGNI)

- Multi-user auth, hosting, HTTPS.
- Poster history/gallery, database.
- Social-media auto-posting (Connect API cannot post to socials; noted in video Q&A).
- Non-A4 sizes (can be added later as new orientation presets).

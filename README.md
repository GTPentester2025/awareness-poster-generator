# Awareness Poster Generator

## What it does

This tool generates custom health and safety awareness posters on demand. You provide a topic (e.g., "road safety" or "hand hygiene"), and the pipeline orchestrates the full creation flow: OpenAI generates engaging poster copy (headline, three facts, and a call-to-action) along with a color palette, optionally generates a background image using DALL-E, renders a high-quality A4 poster in Python (portrait or landscape), and finally imports the finished design into Canva for editing—returning an instant edit URL where you can refine text, colors, and layout in the Canva editor.

## Setup

### 1. Create and activate a virtual environment

Python 3.14.5 is required. Create a virtual environment in the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

### 2. Configure API keys

Copy the environment template and fill in your credentials:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and add your OpenAI API key from [platform.openai.com](https://platform.openai.com):

```
OPENAI_API_KEY=sk-...your-key-here...
```

The text model defaults to `gpt-4o-mini` but can be overridden by setting `OPENAI_TEXT_MODEL` in `.env`.

### 3. Connect Canva for design import

Set up OAuth integration with Canva to enable one-click design import:

1. Go to [Canva Developers](https://www.canva.com/developers/integrations)
2. Click **Create an integration**
3. Leave **Public** unchecked (a private/dev integration works fine for testing)
4. Name your integration (e.g., "Awareness Poster Generator")
5. Under **Scopes**, enable: `design:content:write`
6. Under **Authentication**, add redirect URL: `http://127.0.0.1:8000/auth/canva/callback`
7. Copy the **Client ID** and generate a **Client secret**
8. Add both to `.env`:

```
CANVA_CLIENT_ID=your-client-id-here
CANVA_CLIENT_SECRET=your-client-secret-here
```

## Run

Start the development server:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. On first visit, click **Connect Canva** to authenticate. Then use the form to generate a poster: enter a topic, select orientation (portrait/landscape), and click Generate. The app will return an **Edit in Canva** link that opens your design in the Canva editor, where all text remains fully editable.

## Tests

Run the full test suite:

```powershell
.\.venv\Scripts\python -m pytest
```

Run the end-to-end smoke test (requires real OpenAI and Canva credentials in `.env`):

```powershell
.\.venv\Scripts\python scripts\smoke.py "road safety"
```

The smoke script tests the full pipeline: content generation, optional image generation, PPTX building, and Canva import. It prints stage-by-stage progress and returns the final edit URL.

## Troubleshooting

- **401 Unauthorized from Canva**: Canva token has expired. Revisit [http://127.0.0.1:8000](http://127.0.0.1:8000), click **Connect Canva** again, and retry generation.
- **Canva import failed**: The PPTX may be incompatible with the Canva API. Use the Download PPTX link shown in the app (files are saved in the `out/` directory) and manually drag it into a Canva design—all content will import correctly.
- **Image generation warnings or fallback to palette background**: The DALL-E request failed (rate limit, API issue, or model unavailability). The poster is still generated with a solid color background derived from the color palette. Regenerate or manually add an image in Canva.

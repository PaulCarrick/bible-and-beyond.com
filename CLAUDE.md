# Bible and Beyond

A web app that answers Bible questions using AI/ML.

## Architecture
- `drupal/` — Drupal 11 (PHP), run with DDEV. Content management and admin. Exposes content via JSON:API.
- `ml-service/` — Python 3.12 + FastAPI. AI/ML logic and the question-answering API.
- `frontend/` — React + TypeScript + Vite. The public web UI; calls ml-service and Drupal.

## Local URLs
- Drupal: https://bible-and-beyond.ddev.site
- ML service: http://localhost:8000 (API docs at /docs)
- Frontend: http://localhost:5173

## Running locally
- Drupal: `cd drupal && ddev start` (use `ddev composer` and `ddev drush`, never local php/composer)
- ML service: `cd ml-service && source .venv/bin/activate && uvicorn main:app --reload --port 8000`
- Frontend: `cd frontend && npm run dev`

## Conventions
- No abbreviations in variable, function, or method names.
- 2-space indentation in PHP, TypeScript, JSON, YAML; follow the formatter's default for Python.
- Keep solutions simple and direct; avoid unnecessary abstractions.
- Show complete files/functions when making changes.
- Never commit secrets; use `.env` files (gitignored) and keep a `.env.example`.

## Testing
- Python: pytest — `cd ml-service && source .venv/bin/activate && python -m pytest`
- Frontend: Vitest (to be added)
- Drupal: PHPUnit via `ddev exec vendor/bin/phpunit` (to be added)
## Bible database
- Postgres 17 + pgvector in Docker (`docker compose up -d` from the repo root), container `bible-and-beyond-database`, host port 5434.
- Connection string lives in `ml-service/.env` as `DATABASE_URL` (never commit `.env`).
- Schema: `ml-service/database/schema.sql` — tables `translations`, `books` (canonical 1–66 with USFM codes and name aliases), `verses`, `verse_embeddings`. Applying it drops and recreates these tables.
- Import a translation (BSB tab format or eBible `*_vpl.txt` format): `.venv/bin/python scripts/import_bible.py data/<file>.txt --code BSB --name "Berean Standard Bible" --license "Public domain"`. KJV also needs `--strip-brackets`.
- Search in public-domain text (BSB); copyrighted translations like ESV are only fetched for display, never stored.

## Licensed Bibles (API.Bible)
- NIV, NASB 2020 and The Message come from API.Bible (free Starter plan: non-commercial only, 5,000 requests a month). Code is in `ml-service/api_bible.py`; the key and endpoint are `API_BIBLE_KEY` and `API_BIBLE_ENDPOINT` in `ml-service/.env`.
- Their text is never stored in our database; it is fetched on demand and cached in memory (search results 10 minutes, copyright metadata 24 hours; the terms require refreshing within 30 days).
- Terms to keep: show each Bible's copyright notice with its text, keep the visible API.Bible link and "Bible copyright notices" page, and report every view to FUMS (`frontend/src/fums.ts`). Never alter the text, never use it commercially, and never put it in AI prompts or training data. Use only the public-domain local Bibles (ASV, BSB, KJV, WEB) for `/ask`.
- These Bibles are searched one at a time, matching all words, in Bible order. Match any, exact phrase, whole words, per-book counts and sorting by contents are not available for them.
- Backend tests fake the API so they do not use the monthly allowance. Live calls count against it, so keep them few.

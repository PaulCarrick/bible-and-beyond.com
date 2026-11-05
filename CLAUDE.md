# BibleAnswers

A web app that answers Bible questions using AI/ML.

## Architecture
- `drupal/` — Drupal 11 (PHP), run with DDEV. Content management and admin. Exposes content via JSON:API.
- `ml-service/` — Python 3.12 + FastAPI. AI/ML logic and the question-answering API.
- `frontend/` — React + TypeScript + Vite. The public web UI; calls ml-service and Drupal.

## Local URLs
- Drupal: https://bibleanswers.ddev.site
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
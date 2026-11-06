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
- Live site: https://bible-and-beyond.com (app) and https://cms.bible-and-beyond.com (Drupal); see "Production server" below

## Running locally
- Drupal: `cd drupal && ddev start` (use `ddev composer` and `ddev drush`, never local php/composer)
- ML service: `cd ml-service && source .venv/bin/activate && uvicorn main:app --reload --port 8000`
- Frontend: `cd frontend && npm run dev`
- If something else already uses port 8000 (Docker sometimes does), run uvicorn on 8001 and put `VITE_ML_SERVICE_URL=http://localhost:8001` in `frontend/.env.local` (git-ignored).

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
- Each translation has an `is_published` flag. Search and the Bible picker only see published ones. Database changes live in `ml-service/database/migrations/` as files that are safe to run twice; `deploy/deploy.sh` applies them. `schema.sql` is kept in step for fresh databases.
- The importer lives in `ml-service/bible_import/`; `scripts/import_bible.py` (command line, publishes at once unless `--unpublished`) and `scripts/manage_bibles.py` (JSON output, used by Drupal) both call it.

## Licensed Bibles (API.Bible)
- NIV, NASB 2020 and The Message come from API.Bible (free Starter plan: non-commercial only, 5,000 requests a month). Code is in `ml-service/api_bible.py`; the key and endpoint are `API_BIBLE_KEY` and `API_BIBLE_ENDPOINT` in `ml-service/.env`.
- Their text is never stored in our database; it is fetched on demand and cached in memory (search results 10 minutes, copyright metadata 24 hours; the terms require refreshing within 30 days).
- Terms to keep: show each Bible's copyright notice with its text, keep the visible API.Bible link and "Bible copyright notices" page, and report every view to FUMS (`frontend/src/fums.ts`). Never alter the text, never use it commercially, and never put it in AI prompts or training data. Use only the public-domain local Bibles (ASV, BSB, KJV, WEB) for `/ask`.
- These Bibles are searched one at a time, matching all words, in Bible order. Match any, exact phrase, whole words, per-book counts and sorting by contents are not available for them.
- Backend tests fake the API so they do not use the monthly allowance. Live calls count against it, so keep them few.

## Production server
- One AWS Lightsail instance (Debian 13, 2 vCPU, about 2 GB RAM plus a 2 GB swap file), static IP `54.200.249.10`. Firewall: ufw and the Lightsail firewall allow only ports 22, 80 and 443.
- Access: `ssh bible-and-beyond` (an entry in `~/.ssh/config`; user `paul`, key login only, password login is off). The repository lives at `/home/paul/bible-and-beyond.com` and everything runs as `paul`. `paul`'s sudo asks for a password; system-level setup was done through the Lightsail default `admin` account, whose key is kept outside the repository.
- Layout: nginx serves `frontend/dist` and proxies `/api/` to the ML service (systemd user service `bible-and-beyond-ml`, 127.0.0.1:8000, Python 3.13). PostgreSQL 17 + pgvector runs natively (database `bibleandbeyond`, socket login as `paul`, no password). Drupal runs through a PHP-FPM pool as `paul` with MariaDB 11.8 (database `bibleandbeyond_drupal`, socket login).
- Secrets exist only on the server and are never committed (this repository is public): `ml-service/.env` (mode 600), `drupal/web/sites/default/settings.local.php` (git-ignored; template in `deploy/drupal/settings.local.php.example`), and the TLS private keys in `/etc/ssl/private` (root only).
- Rate limits live in nginx (`deploy/nginx/bible-and-beyond-limits.conf`): the API allows about 5 requests a second per visitor, searches in the licensed Bibles 20 a minute, and Drupal's login page 10 a minute. The ML service also stops calling API.Bible at 4,500 requests a month (`API_BIBLE_MONTHLY_LIMIT`; the count is kept in `ml-service/data/api_bible_usage.json`).
- Drupal: it was installed fresh, not imported from DDEV. Nothing in the app calls it yet. For a one-time admin login link: `ssh bible-and-beyond 'cd ~/bible-and-beyond.com/drupal && vendor/bin/drush user:login --name=admin --uri=https://cms.bible-and-beyond.com'`. Drupal keeps `sites/default` read-only on purpose.

## Managing Bibles from Drupal
- Drupal is the admin screen for the main site; the Bible text goes into the main PostgreSQL database, never into Drupal's. Page: https://cms.bible-and-beyond.com/admin/bibles (Drupal module `drupal/web/modules/custom/bible_admin`).
- Flow: upload a `.txt` file with a code, name, language and license; see a preview (format, verse and book counts, sample verses, warnings); confirm to import. A new Bible is **hidden until published** (Publish / Hide / Delete on the list page). Re-importing an existing code replaces its text and keeps its published state. The last published Bible cannot be hidden or deleted. The codes NIV, NASB and MSG are refused (they belong to API.Bible).
- Drupal runs `ml-service/scripts/manage_bibles.py` with a fixed argument list (no shell). The uploaded file is kept in `/home/paul/drupal-private/bible-uploads/` only until the import is confirmed or cancelled, and stale ones are removed by cron after a day. Check the Drupal log (type `bible_admin`) to see who imported, published or deleted what.
- Roles: `administrator` (everything, including adding users) and `Bible administrator` (only the Bibles page). Add people at People > Add user. The server cannot send email, so set each new user's first password yourself and tell them privately.
- Adding a file format (USFM, XML, ...): write a reader class in `ml-service/bible_import/formats.py` (same members as `TabSeparatedReader`: `id`, `name`, `description`, `score`, `read`) and add it to `READERS`. Detection, the preview, the import and the Drupal format list pick it up automatically. Add tests in `ml-service/tests/test_bible_import.py`.
- The Drupal module has no automated tests yet (PHPUnit is not set up); the Python side does.

## Deploying
- Push to `main`, then run `deploy/deploy.sh` from your Mac (`--all` rebuilds and restarts everything). It pulls on the server, then only redoes what changed: Python dependencies and an ML service restart, the frontend build (`VITE_ML_SERVICE_URL=/api`), Composer, Drupal database updates and a cache rebuild. It then checks health, including from outside. The server deploys what is on GitHub, not your working copy.
- It unlocks Drupal's read-only settings folder only while git updates files, and locks it again afterwards (`555`, not `444`, because git tracks `settings.php` as executable).
- nginx and PHP-FPM config files need sudo, so the deploy script only reports when the installed copies differ from `deploy/`. Install them with `ssh -t bible-and-beyond sudo ~/bible-and-beyond.com/deploy/install-system-config.sh`. It replaces only changed files, tests the configuration, and puts the old files back if the test fails.
- Make changes in the repository and deploy them. Do not edit files on the server; that blocks `git pull`.

## HTTPS certificates (bought from Namecheap, renewed by hand)
- Two single-name certificates issued by SSL.com: Standard SSL (Namecheap id 36657834) for `bible-and-beyond.com` and `www`, and PositiveSSL (id 29419701) for `cms.bible-and-beyond.com` and `www.cms`. **Both expire 2027-05-23. Renew around 2027-05-01.** They do not renew by themselves.
- Files on the server: private keys `/etc/ssl/private/bible-and-beyond.com.key` and `cms.bible-and-beyond.com.key` (root only); certificate plus CA bundle in `/etc/ssl/bible-and-beyond/<name>.fullchain.crt`; nginx settings in `deploy/nginx/*-ssl.conf`.
- To renew: (1) on the server, make a new key and CSR with `openssl req -new -newkey rsa:2048 -nodes` including the same names as subjectAltName; (2) in Namecheap, reissue or activate the certificate with "Manage SSL manually", paste the CSR, and choose HTTP file validation (email validation cannot work because the domain has no mailboxes); (3) put the validation file in `/var/www/pki-validation/` (served at `/.well-known/pki-validation/` on both names), then click Verify; (4) download the zip and join the certificate and the CA bundle, certificate first, into the `.fullchain.crt`; confirm it matches the key (compare `openssl ... -modulus` of both) and that `openssl verify` accepts the chain; install it, run `sudo nginx -t`, then `sudo systemctl reload nginx`; (5) check with `openssl s_client -connect <host>:443 -servername <name>`.

## DNS
- DNS for `bible-and-beyond.com` is at Network Solutions (nameservers `ns83.worldnic.com` and `ns84.worldnic.com`). A records `@`, `www`, `cms` and `www.cms` point to `54.200.249.10` with a 15 minute TTL. The domain has no mail records.

## Backups
- Manual only. Both databases live only on the server, so keep a copy off it. The first backup is in `~/Documents/bible-and-beyond-backups/2026-11-06/` on the maintainer's Mac, with restore commands in its `RESTORE.txt`.
- To take one, on the server as `paul`: `pg_dump --no-owner --no-privileges bibleandbeyond | gzip -9 > postgres.sql.gz` and `mariadb-dump --single-transaction --routines --triggers --no-tablespaces bibleandbeyond_drupal | gzip -9 > drupal.sql.gz`. Copy the files to your Mac with `scp`, check them against a `sha256sum` list, and delete the server copies.
- Test a backup by restoring it into a scratch database and comparing row counts (verses: 124,372 at the last backup) before trusting it, then drop the scratch database.
- Not in the database backups, on purpose: `ml-service/.env`, `settings.local.php` and the TLS private keys (secrets), and the code (it is in GitHub). Without the `.env` and `settings.local.php`, a rebuilt server needs new keys and a new Drupal hash salt.
- A Lightsail snapshot of the whole instance is the one thing that also captures those files; take one from the Lightsail console before big changes if you want that safety net.

## Open items
- Backups are manual only, by choice (no scheduled jobs, to keep the server light). Take one before risky changes; see "Backups". The last one was 2026-11-06.
- The old Network Solutions hosting service on this domain is no longer used and expires 2026-12-06; cancel it if it is not needed.

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

## Show in Context
- Each verse in a result from a Bible stored on this site has four links, "Show in Context", "Full Chapter", "Other Translations" and "Related Verses". Each replaces the result list with a window and an X (or Escape) that goes back to the same results. The first two highlight the chosen verse (search words in bold only there). Show in Context shows some verses before and after it in reading order, with chapter headings when it crosses a chapter. Full Chapter shows the whole chapter that contains the verse and ignores the numbers below. Other Translations lists the same verse in every published Bible stored on this site (the one searched comes first, marked "This result"); a Bible that lacks that verse is left out. Results from the licensed Bibles (NIV, NASB, The Message) have no link: it would cost API.Bible requests and the text would have to be split into verses.
- The window stops at the start and end of the book. How many verses come before and after is set in Drupal at https://cms.bible-and-beyond.com/admin/bibles/settings (defaults 5 before and 10 after, each 0 to 50), together with how many related verses to list (default 10, 1 to 50). They live in the `site_settings` table (migration 002), so changes apply to the public site at once. Same permission as the Bibles page.
- Code: `GET /context`, `GET /chapter`, `GET /parallel` and `GET /related` in `ml-service/main.py` and `ml-service/context.py`; settings in `ml-service/site_settings.py` and `scripts/manage_settings.py` (JSON, used by Drupal); frontend `ContextWindow.tsx` and `SearchResults.tsx`.

## Related Verses (cross references)
- Data: OpenBible.info's cross references (https://www.openbible.info/labs/cross-references/), **licensed CC BY 4.0**, based mainly on the Treasury of Scripture Knowledge (public domain). The license requires credit, which the Related Verses window and the "Bible copyright notices" page give (`frontend/src/CrossReferenceCredit.tsx`). It says the data was reformatted and that links with no positive votes were left out; keep that true if the import changes.
- It lives in the `cross_references` table (migration 003; about 341,000 rows, 42 MB), numbered like the KJV and not tied to one translation. A reference points at a verse or a range. Votes are OpenBible.info users' ranking of how useful a link is; rows with zero or negative votes are not loaded.
- Load or refresh it by hand (the deploy script only warns when the table is empty): download `cross-references.zip` from the page above, unzip it, then run `ml-service/.venv/bin/python ml-service/scripts/import_cross_references.py cross_references.txt` (`--dry-run` first). It replaces every row in one transaction. Its first line carries the release date; the one loaded on 2026-11-06 was dated 2026-11-02.
- `GET /related?translation=&book=&chapter=&verse=` lists the best-voted references first, with their text in the Bible searched, a range expanded to at most 15 verses, and a reference to a verse that Bible lacks shown without text. Only Bibles stored on this site get the link; the licensed Bibles do not.
- The window has two tabs: "Points to" (where the verse points) and "Pointed to by" (`direction=to`: the verses that have a reference beginning at it, or a range inside its chapter that contains it; a range that starts in an earlier chapter and runs through it is not matched). The data is one-way, only 25% of pairs also appear in reverse, so "Pointed to by" is a real second list (John 3:16 points to 23 verses and is pointed to by 104). Migration 004 adds the index for it.
- Each related verse has its own "Show in Context" and "Related Verses" links. They open another window on top, so you can follow a chain of references; Back goes up one level and the X or Escape closes them all and returns to the results (`WindowView` stack in `SearchResults.tsx`, `RelatedPanel.tsx`).

## Original Words (Hebrew and Greek, Strong's lexicon)
- Data: STEPBible-Data (https://github.com/STEPBible/STEPBible-Data) from STEP Bible and Tyndale House, Cambridge, **licensed CC BY 4.0**. Its README and file headers allow including the data in software without asking permission and require credit to "STEP Bible" with a link; they ask people not to post copies of the data files elsewhere. So: the files are never committed (the repository is public; `ml-service/data/stepbible/` is git-ignored), the site offers no download of them, and the API only returns the entries for one verse or one word at a time. Credit is in `frontend/src/StepBibleCredit.tsx`, shown in the Original Words and lexicon windows and on the "Bible copyright notices" page. It says the data was reformatted and that only the Greek words of the modern critical text (NA27/28) are loaded; keep that true if the import changes.
- Tables (migration 005): `original_words` (about 441,000 rows: book, chapter, verse, position, original text, transliteration, English, Strong's number, grammar) and `lexicon_entries` (about 22,700 rows). Verses are numbered like the KJV (TAHOT gives that first, with the Hebrew numbering in brackets), not tied to one translation.
- Load or refresh it by hand (the deploy script only warns when `original_words` is empty): download these into one folder, for example `ml-service/data/stepbible/`: the four TAHOT files and the two TAGNT files from "Translators Amalgamated OT+NT", and TBESH and TBESG from "Lexicons" (names may be shortened but must start with tahot, tagnt, tbesh or tbesg). Then run `ml-service/.venv/bin/python ml-service/scripts/import_original_words.py <folder>` (`--dry-run` first). It replaces every row in one transaction. Loaded on 2026-11-06 from the files on GitHub that day (441,490 words, 22,717 lexicon entries).
- Hebrew words come from the Leningrad reading only (type `L`); a joined word such as `H9003/{H7225G}` keeps the number in braces. Greek words are those whose type starts with N (NA27/28); words found only in the Textus Receptus (such as John 7:53 to 8:11) have none. A few tags carry a sense letter the lexicon lacks (H0430J, G2453); they fall back to the "G" entry of the same number (`resolve_strong_code`).
- `GET /original-words?book=&chapter=&verse=` (the words of a verse, each with its lexicon gloss, 404 when none) and `GET /lexicon?translation=&strong_code=` (an entry, the number of verses that use the word, and the first 30 in Bible order with their text in the Bible searched; licensed Bibles get 422). Code: `ml-service/original_words.py`; frontend `WordsPanel.tsx`, `LexiconPanel.tsx`, and the "Original Words" link in `SearchResults.tsx`. Each lexicon verse has "Show in Context" and "Original Words" links, so the windows chain like Related Verses. Only Bibles stored on this site get the link.
- Search by Strong's number: a search box query that is only a number (`G25`, `g0025`, `H7225`, `H7225G`; letters and spaces forgiven, parsed by `parse_strong_query` in `ml-service/search.py`) lists the verses that contain that Hebrew or Greek word, in the Bibles chosen, with the usual book filter, sorting and paging (the match options do not apply and nothing is bolded). A number without a sense letter also matches its senses (H7225 covers H7225G and the others); a letter narrows it (H7225G only). The response adds `strong` (the lexicon entry chosen: the number itself, else its "G" sense, else the first) and the page shows a note under the heading with an "Open the lexicon entry" link (`openLexicon` in `SearchResults.tsx`; it opens the same lexicon window as a Strong's number in Original Words, with the first Bible searched for the verse text). A number that is not in the lexicon gives a 422 message; the licensed Bibles refuse it (422). A real English search that happens to look like a number (for example "H1") is treated as a Strong's search.
- Not built yet: clicking an English word to find its Strong's number (the words are shown as a list per verse, not aligned to each Bible's own wording).

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
- Manual only. Both databases live only on the server, so keep a copy off it. Backups are in `~/Documents/bible-and-beyond-backups/` on the maintainer's Mac, one folder per backup, each with restore commands in its `RESTORE.txt`. The latest, `2026-11-06-2019`, was taken just before Original Words was added (so it has no original words or lexicon; reload them from the STEPBible files) and was checked by checksum only, not restored; `2026-11-06-1949` includes YLT and the cross references and had both restores tested; the first (`2026-11-06`) predates them.
- To take one, on the server as `paul`: `pg_dump --no-owner --no-privileges bibleandbeyond | gzip -9 > postgres.sql.gz` and `mariadb-dump --single-transaction --routines --triggers --no-tablespaces bibleandbeyond_drupal | gzip -9 > drupal.sql.gz`. Copy the files to your Mac with `scp`, check them against a `sha256sum` list, and delete the server copies.
- Test a backup by restoring it into a scratch database and comparing row counts (at the last backup: 155,474 verses, 5 translations, 341,355 cross references; 59 Drupal tables) before trusting it, then drop the scratch database.
- Not in the database backups, on purpose: `ml-service/.env`, `settings.local.php` and the TLS private keys (secrets), and the code (it is in GitHub). Without the `.env` and `settings.local.php`, a rebuilt server needs new keys and a new Drupal hash salt.
- A Lightsail snapshot of the whole instance is the one thing that also captures those files; take one from the Lightsail console before big changes if you want that safety net.

## Open items
- Backups are manual only, by choice (no scheduled jobs, to keep the server light). Take one before risky changes; see "Backups". The last one was 2026-11-06 (20:19 UTC).
- The old Network Solutions hosting service on this domain is no longer used and expires 2026-12-06; cancel it if it is not needed.

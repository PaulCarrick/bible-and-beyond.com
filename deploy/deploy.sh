#!/usr/bin/env bash
# Update the live site from GitHub. Run from your Mac, from anywhere in the repository:
#
#   deploy/deploy.sh          update only what changed since the last deploy
#   deploy/deploy.sh --all    rebuild and restart everything
#
# The server deploys what is on GitHub, so push your commits first. Everything here runs as
# the paul account and needs no sudo. Changes to the nginx or PHP-FPM config files do need
# sudo; this script tells you when that is the case (see deploy/install-system-config.sh).

set -euo pipefail

HOST="${DEPLOY_HOST:-bible-and-beyond}"   # an entry in ~/.ssh/config
FORCE=0
[ "${1:-}" = "--all" ] && FORCE=1

cd "$(git rev-parse --show-toplevel)"

if [ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]; then
  echo "Switch to the main branch first." >&2
  exit 1
fi
git fetch -q origin
if [ "$(git rev-list --count origin/main..HEAD)" != "0" ]; then
  echo "You have commits that are not on GitHub. Push them first; the server deploys from GitHub." >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "Note: you have uncommitted changes. They are not deployed."
fi

echo "Deploying to $HOST ..."
ssh "$HOST" bash -s -- "$FORCE" <<'REMOTE'
set -euo pipefail
FORCE="$1"
cd ~/bible-and-beyond.com
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
SETTINGS_DIR=drupal/web/sites/default

# Drupal locks its settings folder to read-only. Open it just long enough for git to update
# files there, and lock it again afterwards, even if something fails.
lock_settings() {
  chmod 555 "$SETTINGS_DIR" 2>/dev/null || true
  # 555, not 444: Drupal uses 555, and git tracks this file as executable.
  chmod 555 "$SETTINGS_DIR/settings.php" 2>/dev/null || true
}
trap lock_settings EXIT
chmod u+w "$SETTINGS_DIR" "$SETTINGS_DIR/settings.php"

before="$(git rev-parse HEAD)"
git pull -q --ff-only
after="$(git rev-parse HEAD)"
changed="$(git diff --name-only "$before" "$after")"

# touched PATTERN: did the update change a file matching PATTERN (or is this a full deploy)?
touched() { [ "$FORCE" = 1 ] || echo "$changed" | grep -qE "$1"; }

if [ "$before" = "$after" ]; then
  echo "Server already at $(git log --oneline -1)"
else
  echo "Updated $(git log --oneline -1 "$before") -> $(git log --oneline -1)"
  echo "$changed" | sed 's/^/    /'
fi

echo "== Database changes"
# Every file in ml-service/database/migrations is written to be safe to run again.
if touched '^ml-service/database/migrations/'; then
  for migration in ml-service/database/migrations/*.sql; do
    psql -d bibleandbeyond -v ON_ERROR_STOP=1 -q -f "$migration"
    echo "  applied $(basename "$migration")"
  done
else
  echo "  no changes"
fi

# The data itself is loaded by hand (see "Related Verses" in CLAUDE.md); say so if it is missing.
if [ "$(psql -d bibleandbeyond -tAc 'SELECT COUNT(*) FROM cross_references' 2>/dev/null || echo 0)" = "0" ]; then
  echo "  note: the cross_references table is empty, so Related Verses has nothing to show."
  echo "        Load it with: ml-service/.venv/bin/python ml-service/scripts/import_cross_references.py <file>"
fi

if [ "$(psql -d bibleandbeyond -tAc 'SELECT COUNT(*) FROM original_words' 2>/dev/null || echo 0)" = "0" ]; then
  echo "  note: the original_words table is empty, so Original Words has nothing to show."
  echo "        Load it with: ml-service/.venv/bin/python ml-service/scripts/import_original_words.py <folder>"
fi

if [ "$(psql -d bibleandbeyond -tAc 'SELECT COUNT(*) FROM verse_word_links' 2>/dev/null || echo 0)" = "0" ]; then
  echo "  note: the verse_word_links table is empty, so BSB words are not clickable."
  echo "        Load it with: ml-service/.venv/bin/python ml-service/scripts/import_word_links.py <bsb_tables.tsv>"
fi

if [ "$(psql -d bibleandbeyond -tAc 'SELECT COUNT(*) FROM commentary_entries' 2>/dev/null || echo 0)" = "0" ]; then
  echo "  note: the commentary_entries table is empty, so Commentaries has nothing to show."
  echo "        Load it with: ml-service/.venv/bin/python ml-service/scripts/import_commentaries.py <folder>"
fi

if [ "$(psql -d bibleandbeyond -tAc 'SELECT COUNT(*) FROM devotional_entries' 2>/dev/null || echo 0)" = "0" ]; then
  echo "  note: the devotional_entries table is empty, so the Devotionals tab is hidden."
  echo "        Load it with: ml-service/.venv/bin/python ml-service/scripts/import_devotionals.py <folder>"
fi

echo "== ML service"
if touched '^ml-service/requirements.txt$'; then
  ml-service/.venv/bin/pip install -q -r ml-service/requirements.txt
  echo "  dependencies installed"
fi
if touched '^deploy/systemd/'; then
  cp deploy/systemd/bible-and-beyond-ml.service ~/.config/systemd/user/
  systemctl --user daemon-reload
  echo "  service file updated"
fi
if touched '^ml-service/(requirements\.txt|[^/]+\.py|bible_import/|scripts/)|^deploy/systemd/'; then
  systemctl --user restart bible-and-beyond-ml.service
  echo "  service restarted"
else
  echo "  no changes"
fi

echo "== Frontend"
if touched '^frontend/' || [ ! -d frontend/dist ]; then
  (
    cd frontend
    if touched '^frontend/package(-lock)?\.json$' || [ ! -d node_modules ]; then
      npm ci --no-audit --no-fund --loglevel=error
    fi
    VITE_ML_SERVICE_URL=/api npm run build 2>&1 | grep -E "built in|error" || true
  )
else
  echo "  no changes"
fi

echo "== Drupal"
if touched '^drupal/composer\.(json|lock)$'; then
  (cd drupal && COMPOSER_MEMORY_LIMIT=-1 composer install --no-dev --optimize-autoloader --no-interaction --no-progress 2>&1 | tail -2)
fi
if touched '^drupal/'; then
  (
    cd drupal
    # Our own module: switch it on the first time it is deployed.
    if ! vendor/bin/drush pm:list --status=enabled --field=name | grep -qx bible_admin; then
      vendor/bin/drush pm:install bible_admin -y 2>&1 | tail -2
    fi
    vendor/bin/drush updatedb -y 2>&1 | tail -2
    vendor/bin/drush cache:rebuild 2>&1 | tail -1
  )
else
  echo "  no changes"
fi

echo "== Config files that need sudo"
drift=0
check() { # repo file, installed file
  if ! diff -q "$1" "$2" >/dev/null 2>&1; then echo "  differs: $1"; drift=1; fi
}
check deploy/nginx/bible-and-beyond-limits.conf /etc/nginx/conf.d/bible-and-beyond-limits.conf
check deploy/nginx/bible-and-beyond-ssl.conf /etc/nginx/snippets/bible-and-beyond-ssl.conf
check deploy/nginx/cms-ssl.conf /etc/nginx/snippets/cms-ssl.conf
check deploy/nginx/bible-and-beyond.conf /etc/nginx/sites-available/bible-and-beyond
check deploy/nginx/cms.bible-and-beyond.com.conf /etc/nginx/sites-available/cms.bible-and-beyond.com
check deploy/php-fpm/bible-and-beyond.conf /etc/php/8.4/fpm/pool.d/bible-and-beyond.conf
if [ "$drift" = 0 ]; then
  echo "  all installed config files match the repository"
else
  echo "  Install them from your Mac with:"
  echo "    ssh -t bible-and-beyond sudo ~/bible-and-beyond.com/deploy/install-system-config.sh"
fi

echo "== Health"
for attempt in 1 2 3 4 5; do
  curl -fsS -m 5 http://127.0.0.1:8000/health >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS -m 5 http://127.0.0.1:8000/health | sed 's/^/  ML service: /'; echo
echo "  Drupal: $(cd drupal && vendor/bin/drush status --field=bootstrap 2>&1 | tail -1)"
REMOTE

echo "== From outside"
check_url() {
  code="$(curl -s -m 15 -o /dev/null -w '%{http_code}' "$1" || true)"
  printf '  %-50s %s\n' "$1" "$code"
}
check_url https://bible-and-beyond.com/
check_url https://bible-and-beyond.com/api/health
check_url https://cms.bible-and-beyond.com/user/login
echo "Done."

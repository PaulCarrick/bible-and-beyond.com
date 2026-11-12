#!/usr/bin/env bash
# Install the system packages, and the nginx and PHP-FPM config files, from this repository. Run ON the server with sudo:
#
#   ssh -t bible-and-beyond sudo ~/bible-and-beyond.com/deploy/install-system-config.sh
#
# Only files that differ are replaced. The new configuration is tested before it goes live, and
# the old files are put back if the test fails. Certificates and keys are never touched.

set -euo pipefail

if [ "$(id -u)" != "0" ]; then
  echo "Run this with sudo." >&2
  exit 1
fi

REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKUP="$(mktemp -d)"
trap 'rm -rf "$BACKUP"' EXIT

# System packages the site needs: Tesseract reads scanned PDFs uploaded as commentaries, devotionals, books
# or song words (ml-service/document_import.py). Installed only when missing.
PACKAGES=(tesseract-ocr tesseract-ocr-eng)
missing=()
for package in "${PACKAGES[@]}"; do
  dpkg -s "$package" >/dev/null 2>&1 || missing+=("$package")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "installing: ${missing[*]}"
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends "${missing[@]}"
fi

# repo file : installed file
FILES=(
  "deploy/nginx/bible-and-beyond-limits.conf:/etc/nginx/conf.d/bible-and-beyond-limits.conf"
  "deploy/nginx/bible-and-beyond-ssl.conf:/etc/nginx/snippets/bible-and-beyond-ssl.conf"
  "deploy/nginx/cms-ssl.conf:/etc/nginx/snippets/cms-ssl.conf"
  "deploy/nginx/bible-and-beyond.conf:/etc/nginx/sites-available/bible-and-beyond"
  "deploy/nginx/cms.bible-and-beyond.com.conf:/etc/nginx/sites-available/cms.bible-and-beyond.com"
  "deploy/php-fpm/bible-and-beyond.conf:/etc/php/8.4/fpm/pool.d/bible-and-beyond.conf"
)

changed=()
for entry in "${FILES[@]}"; do
  source_file="$REPO/${entry%%:*}"
  target_file="${entry#*:}"
  if ! cmp -s "$source_file" "$target_file"; then
    [ -f "$target_file" ] && cp "$target_file" "$BACKUP/$(echo "$target_file" | tr / _)"
    install -m 644 "$source_file" "$target_file"
    changed+=("$target_file")
    echo "installed: $target_file"
  fi
done

if [ "${#changed[@]}" = 0 ]; then
  echo "Nothing to do: every installed file already matches the repository."
  exit 0
fi

rollback() {
  echo "Test failed, putting the old files back." >&2
  for target_file in "${changed[@]}"; do
    saved="$BACKUP/$(echo "$target_file" | tr / _)"
    [ -f "$saved" ] && cp "$saved" "$target_file"
  done
  nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
  exit 1
}

nginx -t || rollback
php-fpm8.4 -t || rollback
systemctl reload nginx
systemctl reload php8.4-fpm
echo "Reloaded nginx and PHP-FPM with the new configuration."

#!/bin/bash
# Starts the web container. The first time (Drupal not installed yet) it sets the site up from the
# settings file (docker/.env): installs Drupal with the Bible admin module, makes the first administrator,
# saves the email server settings and the site's title and copyright line. Then it runs nginx, PHP-FPM,
# the Python service and the daily devotional emails (supervisord).
set -euo pipefail

files=/app/drupal/web/sites/default/files
chown site:site "$files" /app/drupal-private /app/drupal-config /app/ml-service/data

# A hash salt for Drupal, made once and kept, unless DRUPAL_HASH_SALT is given.
if [ -z "${DRUPAL_HASH_SALT:-}" ] && [ ! -s /app/drupal-private/hash_salt ]; then
  head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > /app/drupal-private/hash_salt
  chown site:site /app/drupal-private/hash_salt
  chmod 600 /app/drupal-private/hash_salt
fi

as_site() {
  runuser -u site -- "$@"
}
drush() {
  as_site /app/drupal/vendor/bin/drush --root=/app/drupal/web "$@"
}

if ! drush status --field=bootstrap 2>/dev/null | grep -q Successful; then
  echo "First start: setting up Drupal and the site ..."
  admin_username="${ADMIN_USERNAME:-admin}"
  admin_email="${ADMIN_EMAIL:?Set ADMIN_EMAIL in docker/.env}"
  admin_password="${ADMIN_PASSWORD:-}"
  generated_password=no
  if [ -z "$admin_password" ]; then
    admin_password=$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 20)
    generated_password=yes
  fi

  # The installer gets a throwaway password; the real one is set from the environment just after, so it
  # never appears in a command line.
  drush site:install standard --yes \
    --site-name="${SITE_TITLE:-Bible and Beyond}" \
    --site-mail="$admin_email" \
    --account-name="$admin_username" \
    --account-mail="$admin_email" \
    --account-pass="$(head -c 24 /dev/urandom | base64 | tr -d '/+=')"
  STACK_ADMIN_PASSWORD="$admin_password" drush php:script /app/docker-setup/set-admin-password.php
  drush pm:install bible_admin --yes

  if [ -n "${SMTP_HOST:-}" ]; then
    drush php:script /app/docker-setup/save-mail-settings.php
  fi

  # The title and copyright line the public site shows (they can be changed on the Site settings screen).
  (cd /app/ml-service && as_site .venv/bin/python scripts/manage_settings.py set \
    --site-title="${SITE_TITLE:-Bible and Beyond}" --copyright-text="${SITE_COPYRIGHT:-}" > /dev/null)

  echo "----------------------------------------------------------------------"
  echo " The site is set up. Log in to the admin as \"$admin_username\"."
  if [ "$generated_password" = yes ]; then
    echo " No ADMIN_PASSWORD was given, so this one was made (shown only now):"
    echo "   $admin_password"
    echo " Change it after logging in (the admin's My account > Edit)."
  fi
  echo "----------------------------------------------------------------------"
else
  # An existing site started with a newer image: apply Drupal's database updates (as deploy.sh does on
  # the live server) and rebuild its caches, so new pages, permissions and roles appear.
  drush updatedb --yes
  drush cache:rebuild
fi

exec /usr/bin/supervisord -c /etc/supervisor/stack.conf

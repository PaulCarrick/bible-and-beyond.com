#!/bin/bash
# Starts MariaDB (Drupal's database) and then PostgreSQL (the Bible database) in one container.
# The first time (empty volumes) MariaDB gets an empty database and user for Drupal, and PostgreSQL loads
# the built-in Bible data (load-bible-data.sh).
set -euo pipefail

socket=/run/mysqld/mysqld.sock
drupal_database=bibleandbeyond_drupal
drupal_user="${DRUPAL_DATABASE_USER:-drupal}"
drupal_password="${DRUPAL_DATABASE_PASSWORD:?Set DRUPAL_DATABASE_PASSWORD (see docker/.env.example)}"
if [[ ! "$drupal_user$drupal_password" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "DRUPAL_DATABASE_USER and DRUPAL_DATABASE_PASSWORD may use only letters, digits, - and _." >&2
  exit 1
fi

mkdir -p /run/mysqld
chown mysql:mysql /run/mysqld /var/lib/mysql

wait_for_mariadb() {
  for _ in $(seq 1 60); do
    if mariadb-admin --socket="$socket" ping --silent 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "MariaDB did not start." >&2
  exit 1
}

if [ ! -d /var/lib/mysql/mysql ]; then
  echo "Setting up MariaDB with an empty database for Drupal ..."
  mariadb-install-db --user=mysql --datadir=/var/lib/mysql --skip-test-db > /dev/null
  mariadbd --user=mysql --skip-networking --socket="$socket" &
  setup_process=$!
  wait_for_mariadb
  mariadb --socket="$socket" <<SQL
CREATE DATABASE $drupal_database CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
CREATE USER '$drupal_user'@'%' IDENTIFIED BY '$drupal_password';
GRANT ALL PRIVILEGES ON $drupal_database.* TO '$drupal_user'@'%';
SQL
  mariadb-admin --socket="$socket" shutdown
  wait "$setup_process" || true
fi

# MariaDB runs in the background; PostgreSQL (below) keeps the container running.
mariadbd --user=mysql --bind-address=0.0.0.0 --port=3306 --socket="$socket" &

exec docker-entrypoint.sh "$@"

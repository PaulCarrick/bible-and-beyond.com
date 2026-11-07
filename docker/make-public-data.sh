#!/usr/bin/env bash
# Makes the public data for the containers from the live Bible database: the Bibles, commentaries,
# devotionals, cross references, original words and lexicon, as loaded in the database.
#
#   docker/make-public-data.sh
#
# Writes docker/public-data/bible-data.sql.gz (git-ignored; built into the database image). The tables
# of the visitors (accounts, sessions, links, notes, email subscriptions) are dumped without a single row,
# on the server itself, so no personal data leaves it. Drupal's database is not used: the containers
# install Drupal fresh. No source file (the downloaded texts and data files) is copied.

set -euo pipefail

server="bible-and-beyond"
output_directory="$(cd "$(dirname "$0")" && pwd)/public-data"
mkdir -p "$output_directory"

# The tables that hold anything about a visitor: their structure is kept, their rows never.
personal_tables=(users user_sessions account_tokens notes devotional_subscriptions)
exclude=""
for table in "${personal_tables[@]}"; do
  exclude+=" --exclude-table-data=public.$table"
done

echo "Dumping the public data on $server ..."
ssh "$server" "pg_dump --no-owner --no-privileges$exclude bibleandbeyond | gzip -9" > "$output_directory/bible-data.sql.gz.new"

echo "Checking that no personal rows are in it ..."
for table in "${personal_tables[@]}"; do
  if gunzip -c "$output_directory/bible-data.sql.gz.new" | grep -q "^COPY public\.$table "; then
    echo "The dump has rows of $table; stopping." >&2
    rm -f "$output_directory/bible-data.sql.gz.new"
    exit 1
  fi
done

mv "$output_directory/bible-data.sql.gz.new" "$output_directory/bible-data.sql.gz"
(cd "$output_directory" && shasum -a 256 bible-data.sql.gz > bible-data.sql.gz.sha256)
ls -l "$output_directory"

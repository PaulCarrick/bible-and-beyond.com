#!/bin/bash
# Run once by the PostgreSQL image, when its data volume is new: loads the built-in Bible data.
set -euo pipefail

echo "Loading the Bible data (about a minute) ..."
gunzip -c /bible-data/bible-data.sql.gz | psql -v ON_ERROR_STOP=1 --quiet --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" > /dev/null
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc \
  "SELECT 'Loaded: ' || (SELECT count(*) FROM verses) || ' verses, ' || (SELECT count(*) FROM commentary_entries) || ' commentary notes, ' || (SELECT count(*) FROM cross_references) || ' cross references.'"

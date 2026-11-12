#!/usr/bin/env bash
# Makes the public data for the containers from the live Bible database: the Bibles, the commentaries,
# the cross references and the Berean word links, as loaded in the database.
#
#   docker/make-public-data.sh
#
# Writes docker/public-data/bible-data.sql.gz (git-ignored; built into the database image). The tables
# of the visitors (accounts, sessions, links, notes, email subscriptions) are dumped without a single row,
# on the server itself, so no personal data leaves it. So are the tables of the sources whose owners ask
# not to be redistributed (STEPBible's original words and lexicon; the devotionals, two of them from
# CCEL), and the rows of Wesley's Notes (a CCEL commentary): each container fetches those from their owners. Drupal's database is not
# used: the containers install Drupal fresh. No source file (the downloaded texts and data files) is copied.

set -euo pipefail

server="bible-and-beyond"
output_directory="$(cd "$(dirname "$0")" && pwd)/public-data"
mkdir -p "$output_directory"

# The tables that hold anything about a visitor: their structure is kept, their rows never.
personal_tables=(users user_sessions account_tokens notes devotional_subscriptions playlists playlist_songs conversation_posts conversation_replies)
# Fetched by each site from the owners (docker/web/fetch-owner-data.sh), never shipped.
owner_tables=(original_words lexicon_entries devotionals devotional_sections devotional_entries)
# This site's own stored FAQ answers from Gemini (each site makes its own with its own key), and its songs:
# their files are in the music folder, not the database, and the recordings may not be ours to pass on. And the
# embeddings of the AI search (hundreds of megabytes, made with this site's Google key; a site makes its own with
# ml-service/scripts/embed_passages.py).
site_tables=(faq_answers music_tracks passage_embeddings ai_search_cache)
# Commentaries whose owner (CCEL) asks not to be redistributed: their rows are taken out of the commentary
# tables below, and each site fetches them itself.
owner_commentaries=(wesley-notes)
exclude=""
for table in "${personal_tables[@]}" "${owner_tables[@]}" "${site_tables[@]}"; do
  exclude+=" --exclude-table-data=public.$table"
done

echo "Dumping the public data on $server ..."
ssh "$server" "pg_dump --no-owner --no-privileges$exclude bibleandbeyond" \
  | awk -v owned="$(IFS=,; echo "${owner_commentaries[*]}")" '
      # Inside the COPY of a commentary table, leave out the rows of an owner-fetched commentary: the column
      # that names the commentary is "commentary_id" (or "id" in the commentaries table itself).
      BEGIN { split(owned, list, ","); for (i in list) skip[list[i]] = 1 }
      /^COPY public\.(commentaries|commentary_entries|commentary_introductions) / {
        header = $0; sub(/^[^(]*\(/, "", header); sub(/\).*$/, "", header)
        count = split(header, columns, ", "); column = 0
        for (i = 1; i <= count; i++) if (columns[i] == "commentary_id" || (columns[i] == "id" && $2 == "public.commentaries")) column = i
        print; inside = 1; next
      }
      inside && /^\\\.$/ { inside = 0; print; next }
      inside { split($0, fields, "\t"); if (fields[column] in skip) next }
      { print }
    ' \
  | gzip -9 > "$output_directory/bible-data.sql.gz.new"

echo "Checking that no personal or owner-fetched rows are in it ..."
for table in "${personal_tables[@]}" "${owner_tables[@]}" "${site_tables[@]}"; do
  if gunzip -c "$output_directory/bible-data.sql.gz.new" | grep -q "^COPY public\.$table "; then
    echo "The dump has rows of $table; stopping." >&2
    rm -f "$output_directory/bible-data.sql.gz.new"
    exit 1
  fi
done
for commentary in "${owner_commentaries[@]}"; do
  if gunzip -c "$output_directory/bible-data.sql.gz.new" | grep -q "	$commentary	\|^$commentary	"; then
    echo "The dump has rows of the commentary $commentary; stopping." >&2
    rm -f "$output_directory/bible-data.sql.gz.new"
    exit 1
  fi
done

mv "$output_directory/bible-data.sql.gz.new" "$output_directory/bible-data.sql.gz"
(cd "$output_directory" && shasum -a 256 bible-data.sql.gz > bible-data.sql.gz.sha256)
ls -l "$output_directory"

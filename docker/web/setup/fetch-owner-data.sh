#!/bin/bash
# Run once each time the web container starts (supervisord), as the user "site": fetches from their owners
# the data that is not shipped in the images, when the database does not have it yet:
#
# - STEPBible's original-language words and lexicons (the Original Words and lexicon windows), from
#   https://github.com/STEPBible/STEPBible-Data (CC BY 4.0), which asks that its files not be posted
#   elsewhere;
# - the four devotionals, from the Christian Classics Ethereal Library (Morning and Evening, Daily Light on
#   the Daily Path; CCEL asks to be contacted before its editions are republished) and Project Gutenberg;
# - the Other books, from Project Gutenberg.
#
# The site works while this runs; those parts appear when they are loaded. The downloaded files are
# deleted once imported. If a download fails, the next start tries again.
set -uo pipefail
cd /app/ml-service

python=.venv/bin/python

row_count() {
  "$python" -c "
import sys
from search import connect
with connect() as connection:
    print(connection.execute('SELECT count(*) FROM ' + sys.argv[1]).fetchone()[0])
" "$1"
}

if [ "$(row_count original_words)" = "0" ]; then
  echo "Fetching the STEPBible data from STEPBible (about 110 MB) ..."
  folder=data/stepbible-download
  if "$python" scripts/download_stepbible.py "$folder" && "$python" scripts/import_original_words.py "$folder"; then
    echo "Loaded the STEPBible data."
  else
    echo "Could not fetch or load the STEPBible data; it will be tried again at the next start." >&2
  fi
  rm -rf "$folder"
fi

# The Other books (Project Gutenberg), when none is loaded yet: also for a site that had its devotionals
# before the books were added.
book_count=$("$python" -c "
from search import connect
with connect() as connection:
    print(connection.execute(\"SELECT count(*) FROM devotionals WHERE collection = 'books'\").fetchone()[0])
")
if [ "$book_count" = "0" ] && [ "$(row_count devotional_entries)" != "0" ]; then
  echo "Fetching the Other books from Project Gutenberg ..."
  folder=data/books-download
  books=$("$python" -c "from devotionals import BOOKS; print(' '.join(BOOKS))")
  if "$python" scripts/download_devotionals.py "$folder" $books && "$python" scripts/import_devotionals.py "$folder" $books; then
    echo "Loaded the Other books."
  else
    echo "Could not fetch or load the Other books; they will be tried again at the next start." >&2
  fi
  rm -rf "$folder"
fi

if [ "$(row_count devotional_entries)" = "0" ]; then
  echo "Fetching the devotionals (CCEL, Project Gutenberg) and the Other books (Project Gutenberg) ..."
  folder=data/devotionals-download
  if "$python" scripts/download_devotionals.py "$folder" && "$python" scripts/import_devotionals.py "$folder"; then
    echo "Loaded the devotionals."
  else
    echo "Could not fetch or load the devotionals; they will be tried again at the next start." >&2
  fi
  rm -rf "$folder"
fi

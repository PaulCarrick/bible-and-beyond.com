-- Keywords for a song (music_tracks) and for a devotional or Other book (devotionals): words the administrator
-- types on the Drupal forms, found by the searches (Search the media, Search other books, Search everything)
-- as well as the text. Comma-separated, any words; empty for none.
--
-- Only new columns, empty for every row already there: adding a column with a constant default changes no
-- existing row and rebuilds no table or index, so the songs, books and devotionals already loaded are untouched.
-- Like the tables, they are not in schema.sql. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/032_add_keywords.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/032_add_keywords.sql)

ALTER TABLE music_tracks ADD COLUMN IF NOT EXISTS keywords TEXT NOT NULL DEFAULT '';
ALTER TABLE devotionals ADD COLUMN IF NOT EXISTS keywords TEXT NOT NULL DEFAULT '';

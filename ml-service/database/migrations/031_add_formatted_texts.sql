-- Formatted texts from PDF and Word uploads (document_import.py): commentary notes and introductions,
-- devotional and Other book readings, and song words can keep their formatting (headings, bold, italic, lists,
-- quotations, tables, pictures, footnotes) as cleaned HTML. The plain text stays in `text` (`lyrics` for songs):
-- the search index, the excerpts and the daily emails read it. NULL means the text has no formatting (the
-- texts loaded from their sources, tab-separated and plain-text uploads). Pictures are files in
-- data/library-images/, served at /library-image/<name>. Adding a column with no default is instant, even on
-- the large tables. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/031_add_formatted_texts.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/031_add_formatted_texts.sql)

ALTER TABLE commentary_entries ADD COLUMN IF NOT EXISTS html TEXT;
ALTER TABLE commentary_introductions ADD COLUMN IF NOT EXISTS html TEXT;
ALTER TABLE devotional_entries ADD COLUMN IF NOT EXISTS html TEXT;
ALTER TABLE music_tracks ADD COLUMN IF NOT EXISTS lyrics_html TEXT;

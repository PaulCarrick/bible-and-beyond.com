-- Which English words of a verse stand for which Hebrew or Greek word (Strong's number), so a
-- word can be clicked. Only for Bibles where such a table exists (the Berean Standard Bible).
-- "links" is a list of [start, end, "H7225"] over the verse text, in characters. text_hash is the
-- md5 of the verse text the offsets were made for; the lookup ignores a row if the text has changed.
-- Safe to run more than once. Load the data with scripts/import_word_links.py.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/006_add_verse_word_links.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/006_add_verse_word_links.sql)

CREATE TABLE IF NOT EXISTS verse_word_links (
    verse_id INTEGER PRIMARY KEY REFERENCES verses (id) ON DELETE CASCADE,
    text_hash TEXT NOT NULL,
    links JSONB NOT NULL
);

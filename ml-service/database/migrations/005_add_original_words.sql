-- Hebrew and Greek words of each verse, and a lexicon of their Strong's numbers (STEPBible.org,
-- Tyndale House Cambridge, CC BY 4.0). Verses are numbered like the KJV and are not tied to one
-- translation. Safe to run more than once. Load the data with scripts/import_original_words.py.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/005_add_original_words.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/005_add_original_words.sql)

CREATE TABLE IF NOT EXISTS lexicon_entries (
    strong_code TEXT PRIMARY KEY,
    language TEXT NOT NULL,
    original TEXT NOT NULL,
    transliteration TEXT NOT NULL,
    morphology TEXT NOT NULL,
    gloss TEXT NOT NULL,
    definition TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS original_words (
    id BIGSERIAL PRIMARY KEY,
    book_number SMALLINT NOT NULL REFERENCES books (number),
    chapter INTEGER NOT NULL,
    verse INTEGER NOT NULL,
    position INTEGER NOT NULL,
    original TEXT NOT NULL,
    transliteration TEXT NOT NULL,
    english TEXT NOT NULL,
    strong_code TEXT,
    grammar TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS original_words_by_verse
    ON original_words (book_number, chapter, verse, position);

CREATE INDEX IF NOT EXISTS original_words_by_strong
    ON original_words (strong_code, book_number, chapter, verse);

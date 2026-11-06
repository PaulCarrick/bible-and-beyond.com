-- Public-domain Bible commentaries (Matthew Henry, John Gill, Adam Clarke, Jamieson-Fausset-Brown,
-- John Calvin, Keil and Delitzsch), from the Free Use Bible API (bible.helloao.org), each marked
-- Public Domain. Verses are numbered like the KJV and are not tied to one translation.
-- An entry covers verse to end_verse (an open end, NULL, means to the end of its chapter).
-- Chapter 0 of commentary_introductions is the introduction to the whole book.
-- Safe to run more than once. Load the data with scripts/import_commentaries.py.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/007_add_commentaries.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/007_add_commentaries.sql)

CREATE TABLE IF NOT EXISTS commentaries (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    position INTEGER NOT NULL,
    license_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commentary_entries (
    id BIGSERIAL PRIMARY KEY,
    commentary_id TEXT NOT NULL REFERENCES commentaries (id) ON DELETE CASCADE,
    book_number SMALLINT NOT NULL REFERENCES books (number),
    chapter INTEGER NOT NULL,
    verse INTEGER NOT NULL,
    end_verse INTEGER,
    text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS commentary_entries_by_verse
    ON commentary_entries (commentary_id, book_number, chapter, verse);

CREATE TABLE IF NOT EXISTS commentary_introductions (
    commentary_id TEXT NOT NULL REFERENCES commentaries (id) ON DELETE CASCADE,
    book_number SMALLINT NOT NULL REFERENCES books (number),
    chapter INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (commentary_id, book_number, chapter)
);

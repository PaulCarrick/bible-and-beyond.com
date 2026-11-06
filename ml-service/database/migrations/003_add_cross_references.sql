-- Cross references between verses (OpenBible.info, CC BY 4.0, based mainly on the Treasury of
-- Scripture Knowledge). Verses are numbered like the KJV, and are not tied to one translation.
-- A reference points at one verse, or at a range of verses when the "to end" columns are filled in.
-- Safe to run more than once. Load the data with scripts/import_cross_references.py.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/003_add_cross_references.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/003_add_cross_references.sql)

CREATE TABLE IF NOT EXISTS cross_references (
    from_book SMALLINT NOT NULL REFERENCES books (number),
    from_chapter INTEGER NOT NULL,
    from_verse INTEGER NOT NULL,
    to_book SMALLINT NOT NULL REFERENCES books (number),
    to_chapter INTEGER NOT NULL,
    to_verse INTEGER NOT NULL,
    to_end_book SMALLINT REFERENCES books (number),
    to_end_chapter INTEGER,
    to_end_verse INTEGER,
    votes INTEGER NOT NULL,
    PRIMARY KEY (from_book, from_chapter, from_verse, to_book, to_chapter, to_verse)
);

CREATE INDEX IF NOT EXISTS cross_references_by_votes
    ON cross_references (from_book, from_chapter, from_verse, votes DESC);

-- Full-text search inside the Other books (and, should it be wanted later, the devotionals): a stored
-- search vector over each entry's chapter title and text, and an index on it. It uses the commentaries'
-- text search configuration, commentary_english (migration 008): English word forms, no ignored common words.
--
-- Adding the column computes it for every existing row (about 18 MB of text: seconds). Safe to run more
-- than once.

ALTER TABLE devotional_entries
    ADD COLUMN IF NOT EXISTS search_vector TSVECTOR
    GENERATED ALWAYS AS (to_tsvector('commentary_english', unit_title || ' ' || text)) STORED;

CREATE INDEX IF NOT EXISTS devotional_entries_by_search_vector
    ON devotional_entries USING GIN (search_vector);

-- Full-text search inside the commentaries: a stored search vector and an index on it.
--
-- It uses its own text search configuration, commentary_english: English word forms ("love" finds
-- "loved") like Postgres's "english", but without its list of ignored common words, so a phrase
-- such as "born again" or "so loved the world" matches exactly.
--
-- Adding the column computes it for every existing row, which takes a minute or so on the server
-- and blocks reads of this table meanwhile. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/008_add_commentary_search.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/008_add_commentary_search.sql)

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_dict WHERE dictname = 'english_stem_with_common_words') THEN
        CREATE TEXT SEARCH DICTIONARY english_stem_with_common_words (TEMPLATE = snowball, Language = english);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'commentary_english') THEN
        CREATE TEXT SEARCH CONFIGURATION commentary_english (COPY = pg_catalog.english);
        ALTER TEXT SEARCH CONFIGURATION commentary_english
            ALTER MAPPING FOR asciiword, word, hword_asciipart, hword_part, asciihword, hword
            WITH english_stem_with_common_words;
    END IF;
END
$$;

ALTER TABLE commentary_entries
    ADD COLUMN IF NOT EXISTS search_vector TSVECTOR
    GENERATED ALWAYS AS (to_tsvector('commentary_english', text)) STORED;

CREATE INDEX IF NOT EXISTS commentary_entries_by_search_vector
    ON commentary_entries USING GIN (search_vector);

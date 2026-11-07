-- Bible and Beyond database schema: multiple translations, canonical books, embeddings.
--
-- WARNING: this drops and recreates all Bible tables. Re-run the importer afterwards.
--
-- Apply with:
--   docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/schema.sql

CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS devotional_entries CASCADE;
DROP TABLE IF EXISTS devotional_sections CASCADE;
DROP TABLE IF EXISTS devotionals CASCADE;
DROP TABLE IF EXISTS commentary_introductions CASCADE;
DROP TABLE IF EXISTS commentary_entries CASCADE;
DROP TABLE IF EXISTS commentaries CASCADE;
DROP TEXT SEARCH CONFIGURATION IF EXISTS commentary_english;
DROP TEXT SEARCH DICTIONARY IF EXISTS english_stem_with_common_words;
DROP TABLE IF EXISTS verse_word_links CASCADE;
DROP TABLE IF EXISTS original_words CASCADE;
DROP TABLE IF EXISTS lexicon_entries CASCADE;
DROP TABLE IF EXISTS cross_references CASCADE;
DROP TABLE IF EXISTS verse_embeddings CASCADE;
DROP TABLE IF EXISTS verses CASCADE;
DROP TABLE IF EXISTS books CASCADE;
DROP TABLE IF EXISTS translations CASCADE;

CREATE TABLE translations (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    license TEXT NOT NULL,
    source_url TEXT,
    is_published BOOLEAN NOT NULL DEFAULT TRUE  -- hidden from search until an administrator publishes it
);

CREATE TABLE books (
    number INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    testament TEXT NOT NULL CHECK (testament IN ('OT', 'NT')),
    aliases TEXT[] NOT NULL DEFAULT '{}'  -- other names and codes used by source files (e.g. BibleWorks/eBible VPL codes)
);

CREATE TABLE verses (
    id SERIAL PRIMARY KEY,
    translation_id INTEGER NOT NULL REFERENCES translations (id) ON DELETE CASCADE,
    book_number INTEGER NOT NULL REFERENCES books (number),
    chapter INTEGER NOT NULL,
    verse INTEGER NOT NULL,
    text TEXT NOT NULL,
    UNIQUE (translation_id, book_number, chapter, verse)
);

CREATE INDEX verses_reference_index ON verses (book_number, chapter, verse);

CREATE TABLE verse_embeddings (
    verse_id INTEGER NOT NULL REFERENCES verses (id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL,
    PRIMARY KEY (verse_id, model)
);

-- Not dropped above: these settings are not Bible data and should survive a schema reset.
CREATE TABLE IF NOT EXISTS site_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cross references (OpenBible.info). Reload them after a schema reset: scripts/import_cross_references.py.
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

CREATE INDEX IF NOT EXISTS cross_references_by_target
    ON cross_references (to_book, to_chapter, to_verse);

INSERT INTO books (number, code, name, testament, aliases) VALUES
    (1, 'GEN', 'Genesis', 'OT', '{"Gen"}'),
    (2, 'EXO', 'Exodus', 'OT', '{"Exod"}'),
    (3, 'LEV', 'Leviticus', 'OT', '{"Lev"}'),
    (4, 'NUM', 'Numbers', 'OT', '{"Num"}'),
    (5, 'DEU', 'Deuteronomy', 'OT', '{"Deut"}'),
    (6, 'JOS', 'Joshua', 'OT', '{"Josh"}'),
    (7, 'JDG', 'Judges', 'OT', '{"Judg"}'),
    (8, 'RUT', 'Ruth', 'OT', '{}'),
    (9, '1SA', '1 Samuel', 'OT', '{"I Samuel","First Samuel","1 Kingdoms"}'),
    (10, '2SA', '2 Samuel', 'OT', '{"II Samuel","Second Samuel","2 Kingdoms"}'),
    (11, '1KI', '1 Kings', 'OT', '{"I Kings","First Kings","3 Kingdoms"}'),
    (12, '2KI', '2 Kings', 'OT', '{"II Kings","Second Kings","4 Kingdoms"}'),
    (13, '1CH', '1 Chronicles', 'OT', '{"I Chronicles","First Chronicles"}'),
    (14, '2CH', '2 Chronicles', 'OT', '{"II Chronicles","Second Chronicles"}'),
    (15, 'EZR', 'Ezra', 'OT', '{}'),
    (16, 'NEH', 'Nehemiah', 'OT', '{}'),
    (17, 'EST', 'Esther', 'OT', '{}'),
    (18, 'JOB', 'Job', 'OT', '{}'),
    (19, 'PSA', 'Psalms', 'OT', '{"Psalm","Ps"}'),
    (20, 'PRO', 'Proverbs', 'OT', '{"Prov"}'),
    (21, 'ECC', 'Ecclesiastes', 'OT', '{"Qoheleth","Eccl"}'),
    (22, 'SNG', 'Song of Solomon', 'OT', '{"Song of Songs","Song","Canticles","Canticle of Canticles","SOL"}'),
    (23, 'ISA', 'Isaiah', 'OT', '{"Isa"}'),
    (24, 'JER', 'Jeremiah', 'OT', '{"Jer"}'),
    (25, 'LAM', 'Lamentations', 'OT', '{"Lam"}'),
    (26, 'EZK', 'Ezekiel', 'OT', '{"Ezek","EZE"}'),
    (27, 'DAN', 'Daniel', 'OT', '{"Dan"}'),
    (28, 'HOS', 'Hosea', 'OT', '{}'),
    (29, 'JOL', 'Joel', 'OT', '{"JOE"}'),
    (30, 'AMO', 'Amos', 'OT', '{}'),
    (31, 'OBA', 'Obadiah', 'OT', '{}'),
    (32, 'JON', 'Jonah', 'OT', '{}'),
    (33, 'MIC', 'Micah', 'OT', '{}'),
    (34, 'NAM', 'Nahum', 'OT', '{"NAH"}'),
    (35, 'HAB', 'Habakkuk', 'OT', '{}'),
    (36, 'ZEP', 'Zephaniah', 'OT', '{}'),
    (37, 'HAG', 'Haggai', 'OT', '{}'),
    (38, 'ZEC', 'Zechariah', 'OT', '{}'),
    (39, 'MAL', 'Malachi', 'OT', '{}'),
    (40, 'MAT', 'Matthew', 'NT', '{"Matt"}'),
    (41, 'MRK', 'Mark', 'NT', '{"MAR"}'),
    (42, 'LUK', 'Luke', 'NT', '{}'),
    (43, 'JHN', 'John', 'NT', '{"JOH"}'),
    (44, 'ACT', 'Acts', 'NT', '{"Acts of the Apostles","The Acts"}'),
    (45, 'ROM', 'Romans', 'NT', '{"Rom"}'),
    (46, '1CO', '1 Corinthians', 'NT', '{"I Corinthians","First Corinthians"}'),
    (47, '2CO', '2 Corinthians', 'NT', '{"II Corinthians","Second Corinthians"}'),
    (48, 'GAL', 'Galatians', 'NT', '{"Gal"}'),
    (49, 'EPH', 'Ephesians', 'NT', '{"Eph"}'),
    (50, 'PHP', 'Philippians', 'NT', '{"Phil","PHI"}'),
    (51, 'COL', 'Colossians', 'NT', '{"Col"}'),
    (52, '1TH', '1 Thessalonians', 'NT', '{"I Thessalonians","First Thessalonians"}'),
    (53, '2TH', '2 Thessalonians', 'NT', '{"II Thessalonians","Second Thessalonians"}'),
    (54, '1TI', '1 Timothy', 'NT', '{"I Timothy","First Timothy"}'),
    (55, '2TI', '2 Timothy', 'NT', '{"II Timothy","Second Timothy"}'),
    (56, 'TIT', 'Titus', 'NT', '{}'),
    (57, 'PHM', 'Philemon', 'NT', '{"Philem"}'),
    (58, 'HEB', 'Hebrews', 'NT', '{"Heb"}'),
    (59, 'JAS', 'James', 'NT', '{"Jas","JAM"}'),
    (60, '1PE', '1 Peter', 'NT', '{"I Peter","First Peter"}'),
    (61, '2PE', '2 Peter', 'NT', '{"II Peter","Second Peter"}'),
    (62, '1JN', '1 John', 'NT', '{"I John","First John","1JO"}'),
    (63, '2JN', '2 John', 'NT', '{"II John","Second John","2JO"}'),
    (64, '3JN', '3 John', 'NT', '{"III John","Third John","3JO"}'),
    (65, 'JUD', 'Jude', 'NT', '{}'),
    (66, 'REV', 'Revelation', 'NT', '{"Revelations","The Revelation","Revelation of John","Apocalypse"}');

-- Hebrew and Greek words and their lexicon (STEPBible.org). Reload them after a schema reset: scripts/import_original_words.py.
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

-- Clickable English words (Strong's numbers). Reload them after a schema reset: scripts/import_word_links.py.
CREATE TABLE IF NOT EXISTS verse_word_links (
    verse_id INTEGER PRIMARY KEY REFERENCES verses (id) ON DELETE CASCADE,
    text_hash TEXT NOT NULL,
    links JSONB NOT NULL
);

-- Search configuration for the commentaries: English word forms, without the list of ignored common words.
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

-- Public-domain commentaries. Reload them after a schema reset: scripts/import_commentaries.py.
CREATE TABLE IF NOT EXISTS commentaries (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    position INTEGER NOT NULL,
    license_url TEXT NOT NULL,
    -- Hidden ones are not shown on the site (migration 016).
    is_published BOOLEAN NOT NULL DEFAULT true,
    -- Where the text came from, for the credit (migration 016).
    source_name TEXT NOT NULL DEFAULT 'Free Use Bible API',
    source_url TEXT NOT NULL DEFAULT 'https://bible.helloao.org'
);

CREATE TABLE IF NOT EXISTS commentary_entries (
    id BIGSERIAL PRIMARY KEY,
    commentary_id TEXT NOT NULL REFERENCES commentaries (id) ON DELETE CASCADE,
    book_number SMALLINT NOT NULL REFERENCES books (number),
    chapter INTEGER NOT NULL,
    verse INTEGER NOT NULL,
    end_verse INTEGER,
    text TEXT NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('commentary_english', text)) STORED
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

CREATE INDEX IF NOT EXISTS commentary_entries_by_search_vector
    ON commentary_entries USING GIN (search_vector);

-- Public-domain devotionals. Reload them after a schema reset: scripts/import_devotionals.py.
CREATE TABLE IF NOT EXISTS devotionals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    author TEXT NOT NULL,
    -- "daily": sections are months and units are days (section = month, unit = day of the month).
    -- "chapters": sections are books or parts and units are chapters.
    kind TEXT NOT NULL CHECK (kind IN ('daily', 'chapters')),
    position INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    translator TEXT,
    -- Hidden ones are not shown on the site and send no emails (migration 016).
    is_published BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS devotional_sections (
    devotional_id TEXT NOT NULL REFERENCES devotionals (id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    PRIMARY KEY (devotional_id, number)
);

CREATE TABLE IF NOT EXISTS devotional_entries (
    devotional_id TEXT NOT NULL REFERENCES devotionals (id) ON DELETE CASCADE,
    section INTEGER NOT NULL,
    unit INTEGER NOT NULL,
    part INTEGER NOT NULL,
    unit_title TEXT NOT NULL,
    heading TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (devotional_id, section, unit, part)
);

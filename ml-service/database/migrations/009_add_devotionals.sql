-- Public-domain devotionals (Spurgeon's Morning and Evening, Daily Light on the Daily Path, The
-- Imitation of Christ, The Practice of the Presence of God).
--
-- A devotional is a list of sections (the months of a daily devotional, or the books and parts of
-- one that has chapters) and, in each section, units (a day, or a chapter). A unit has one or more
-- entries: a day has a morning and an evening entry, a chapter has one. Everything is in reading
-- order by (section, unit, part).
-- Safe to run more than once. Load the data with scripts/import_devotionals.py.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/009_add_devotionals.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/009_add_devotionals.sql)

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
    translator TEXT
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

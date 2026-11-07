-- Notes that a logged-in visitor writes about a Bible verse, a commentary note or a devotional reading.
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/012_add_notes.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/012_add_notes.sql)

CREATE TABLE IF NOT EXISTS notes (
    id BIGSERIAL PRIMARY KEY,
    -- A user has many notes; deleting the user deletes them.
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK (item_type IN ('bible_verse', 'commentary', 'devotional')),
    -- The translation read (bible_verse), the commentary (commentary) or the devotional (devotional), by id.
    source_code TEXT NOT NULL,
    -- bible_verse and commentary: the verse, numbered like the KJV (as everywhere on this site).
    book_number INTEGER,
    chapter INTEGER,
    verse INTEGER,
    -- devotional: the section (month or book) and unit (day or chapter), as the reader numbers them.
    section INTEGER,
    unit INTEGER,
    -- What the visitor wrote: a little HTML from the editor (Quill), cleaned by the server before it is saved.
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT notes_item_fields CHECK (
        (item_type IN ('bible_verse', 'commentary')
            AND book_number BETWEEN 1 AND 66 AND chapter >= 1 AND verse >= 1
            AND section IS NULL AND unit IS NULL)
        OR
        (item_type = 'devotional'
            AND section >= 0 AND unit >= 1
            AND book_number IS NULL AND chapter IS NULL AND verse IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS notes_user_recent_index ON notes (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS notes_user_verse_index ON notes (user_id, book_number, chapter, verse);

-- The plain text of each note, for searching (the body is HTML from the editor, whose tags and
-- attributes must not match a search). Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/013_add_note_search_text.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/013_add_note_search_text.sql)

ALTER TABLE notes ADD COLUMN IF NOT EXISTS body_text TEXT NOT NULL DEFAULT '';

-- Notes written before this column existed: take the tags out of the body and undo the five escapes the
-- server makes. New and edited notes get exactly this text from the server (notes.py).
UPDATE notes
SET body_text = replace(replace(replace(replace(replace(
        regexp_replace(body, '<[^>]*>', ' ', 'g'),
        '&lt;', '<'), '&gt;', '>'), '&quot;', '"'), '&#x27;', ''''), '&amp;', '&')
WHERE body_text = '';

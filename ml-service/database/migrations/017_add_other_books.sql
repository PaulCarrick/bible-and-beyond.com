-- "Other books": books read a chapter at a time (Orthodoxy, the Confessions, ...), shown on their own page.
-- They are kept in the devotionals tables, which already hold books by chapter, marked by collection, so
-- the reader, the notes and the admin work the same; books get no daily emails. Everything loaded so far
-- is a devotional. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/017_add_other_books.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/017_add_other_books.sql)

ALTER TABLE devotionals ADD COLUMN IF NOT EXISTS collection TEXT NOT NULL DEFAULT 'devotionals';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'devotionals_collection_check') THEN
    ALTER TABLE devotionals ADD CONSTRAINT devotionals_collection_check CHECK (collection IN ('devotionals', 'books'));
  END IF;
END $$;

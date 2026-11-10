-- A devotional's or Other book's own credit line, shown instead of the usual "... is in the public domain"
-- when the text is not an old public-domain edition (the modern wording of the Apostles' Creed). NULL for all
-- the others. Set with: scripts/manage_library.py set-credit --kind=book --id=... --credit="..."
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/022_add_devotional_credit.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/022_add_devotional_credit.sql)

ALTER TABLE devotionals ADD COLUMN IF NOT EXISTS credit TEXT;

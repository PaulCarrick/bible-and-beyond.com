-- A translation is hidden from search until an administrator publishes it.
-- Safe to run more than once. Existing translations stay published.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/001_add_is_published.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/001_add_is_published.sql)

ALTER TABLE translations ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT TRUE;

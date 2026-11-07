-- A yes/no setting on each account of the main site, set by an administrator on the Drupal "Site users"
-- page: open_ai_queries (false unless turned on). Nothing on the public site uses it yet.
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/015_add_open_ai_queries.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/015_add_open_ai_queries.sql)

ALTER TABLE users ADD COLUMN IF NOT EXISTS open_ai_queries BOOLEAN NOT NULL DEFAULT false;

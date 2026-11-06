-- Lets "Related Verses" find which verses point AT a verse, not only where a verse points.
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/004_add_cross_reference_target_index.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/004_add_cross_reference_target_index.sql)

CREATE INDEX IF NOT EXISTS cross_references_by_target
    ON cross_references (to_book, to_chapter, to_verse);

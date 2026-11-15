-- A member can share one of their notes, pins or routes on a map with chosen members (map_marks.py): each row says
-- one member may see one mark, read-only, with its author's name. Only accounts an administrator allowed the maps
-- (users.use_maps) can be chosen, by their email address, and only while both still have it do they see it.
-- Deleting the mark or either account deletes the row. Not in schema.sql, like the other account tables. Safe to
-- run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/040_add_map_mark_shares.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/040_add_map_mark_shares.sql)

CREATE TABLE IF NOT EXISTS map_mark_shares (
  mark_id BIGINT NOT NULL REFERENCES map_marks (id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  PRIMARY KEY (mark_id, user_id)
);

CREATE INDEX IF NOT EXISTS map_mark_shares_by_user ON map_mark_shares (user_id);

-- My lists (added 2026-11-17 at the owner's request: members tick results in any search and save them as a named
-- list; saved_lists.py). A list belongs to one account; its entries are kept as the search showed them (kind, a
-- title such as "John 3:16", a source such as "BSB" or a commentary's name, the text, and where to open it), so the
-- list never runs a search again. One entry per item per list (item_key).
--
-- Not in schema.sql, like the other account tables; make-public-data.sh leaves their rows out. Safe to run more
-- than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/047_add_saved_lists.sql

CREATE TABLE IF NOT EXISTS saved_lists (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS saved_lists_one_name ON saved_lists (user_id, lower(name));

CREATE TABLE IF NOT EXISTS saved_list_items (
  id SERIAL PRIMARY KEY,
  list_id INTEGER NOT NULL REFERENCES saved_lists (id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('bible', 'commentary', 'devotional', 'book', 'music', 'map', 'faq')),
  item_key TEXT NOT NULL,
  title TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL DEFAULT '',
  target JSONB NOT NULL,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (list_id, item_key)
);

CREATE INDEX IF NOT EXISTS saved_list_items_by_list ON saved_list_items (list_id, position);

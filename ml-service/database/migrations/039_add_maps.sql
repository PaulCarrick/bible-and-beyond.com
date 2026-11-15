-- Maps (maps.py): pictures of maps, each with a title, a description, where it came from, keywords and the
-- Bible verses it goes with, managed on the Drupal "Maps" page (scripts/manage_maps.py). The files (the original
-- upload, a WebP copy for showing and a small picture for the list) are kept in the maps folder
-- (ml-service/data/maps, or MAPS_FOLDER), never in the database. A new map is hidden until published.
--
-- Members an administrator allowed (users.use_maps, set on the Drupal "Site users" page, false unless turned
-- on) can add their own notes, pins and routes to a map (map_marks). Each member sees only their own. A mark
-- is a few numbers over the shared picture (x and y from 0 to 1 across and down it), so the map itself is never
-- copied. Deleting the user or the map deletes their marks.
--
-- Like the other account tables and the songs, none of this is in schema.sql, so re-applying that file cannot
-- wipe it. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/039_add_maps.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/039_add_maps.sql)

ALTER TABLE users ADD COLUMN IF NOT EXISTS use_maps BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS maps (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  -- Where the map came from and its credit or licence line, shown under it.
  source TEXT NOT NULL DEFAULT '',
  keywords TEXT NOT NULL DEFAULT '',
  -- The verses as they are shown, joined by "; " ("Acts 13:4–14; Acts 16:11"); map_verses holds them one by one.
  verses TEXT NOT NULL DEFAULT '',
  -- The file as uploaded: "<id>.<extension>" in the maps folder.
  file_name TEXT NOT NULL,
  media_type TEXT NOT NULL,
  file_size BIGINT NOT NULL,
  -- For a PDF, the page drawn as the map (from 1); NULL for a picture.
  pdf_page INTEGER,
  -- The size of the copy shown on the site ("<id>-display.webp"), in pixels.
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  is_published BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- The search page's matching, as for the songs (migration 023): the title and keywords count most.
  search_vector tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('commentary_english', title || ' ' || keywords), 'A')
    || setweight(to_tsvector('commentary_english', description || ' ' || verses || ' ' || source), 'B')
  ) STORED
);

CREATE INDEX IF NOT EXISTS maps_by_search_vector ON maps USING gin (search_vector);

CREATE TABLE IF NOT EXISTS map_verses (
  map_id TEXT NOT NULL REFERENCES maps (id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  book_number INTEGER NOT NULL,
  chapter INTEGER NOT NULL,
  verse INTEGER NOT NULL,
  -- The last verse of a range in the same chapter; NULL for one verse.
  end_verse INTEGER,
  label TEXT NOT NULL,
  PRIMARY KEY (map_id, position)
);

CREATE INDEX IF NOT EXISTS map_verses_by_verse ON map_verses (book_number, chapter, verse);

CREATE TABLE IF NOT EXISTS map_marks (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  map_id TEXT NOT NULL REFERENCES maps (id) ON DELETE CASCADE,
  -- note: a note on the whole map; pin: a point (x, y) with a note; route: a line through points, with a name
  -- and a colour (and a note if wished).
  kind TEXT NOT NULL CHECK (kind IN ('note', 'pin', 'route')),
  x DOUBLE PRECISION CHECK (x BETWEEN 0 AND 1),
  y DOUBLE PRECISION CHECK (y BETWEEN 0 AND 1),
  -- A route's points: [[x, y], ...], each from 0 to 1.
  points JSONB,
  name TEXT NOT NULL DEFAULT '',
  colour TEXT CHECK (colour ~ '^#[0-9a-f]{6}$'),
  -- Plain text written by the member; the verses named in it are linked when it is shown.
  body TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (kind = 'note' AND x IS NULL AND y IS NULL AND points IS NULL AND colour IS NULL)
    OR (kind = 'pin' AND x IS NOT NULL AND y IS NOT NULL AND points IS NULL AND colour IS NULL)
    OR (kind = 'route' AND x IS NULL AND y IS NULL AND points IS NOT NULL AND colour IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS map_marks_by_user_and_map ON map_marks (user_id, map_id, created_at);
CREATE INDEX IF NOT EXISTS map_marks_by_map ON map_marks (map_id);

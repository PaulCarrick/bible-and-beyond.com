-- The Christian music section: one row per song, its MP3 or MP4 file kept in the music folder set on the
-- Drupal Site settings screen (service_settings.music_folder), never in the database. Managed on the Drupal
-- "Christian music" page (scripts/manage_music.py, music.py). A new song is hidden until published.
-- Like faq_notes it is not in schema.sql, so re-applying that file cannot wipe it. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/023_add_music.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/023_add_music.sql)

CREATE TABLE IF NOT EXISTS music_tracks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT NOT NULL DEFAULT '',
  -- The words, as plain text: a line per line, a blank line between verses.
  lyrics TEXT NOT NULL DEFAULT '',
  -- The file's name in the music folder: the id and .mp3 or .mp4.
  file_name TEXT NOT NULL,
  media_type TEXT NOT NULL CHECK (media_type IN ('audio/mpeg', 'video/mp4')),
  file_size BIGINT NOT NULL,
  is_published BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- The search page's matching, as for the commentaries and the Other books (migration 008).
  search_vector tsvector GENERATED ALWAYS AS (
    to_tsvector('commentary_english', title || ' ' || author || ' ' || lyrics)
  ) STORED
);

CREATE INDEX IF NOT EXISTS music_tracks_by_search_vector ON music_tracks USING gin (search_vector);

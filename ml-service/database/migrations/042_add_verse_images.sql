-- Pictures for the verse a day (added 2026-11-16 at the owner's request; verse_images.py). An administrator
-- uploads them on the Drupal "Verse a day pictures" page. They are not shown on the site: a later "Send
-- Multimedia Messages" choice will send the verse a day as a picture message, the verse written over one of
-- these chosen at random (only those in_use).
--
-- The files are kept in the verse images folder (ml-service/data/verse-images), never in the database: the
-- picture as uploaded ("<id><extension>") and a small copy for the admin list ("<id>-thumbnail.webp").
--
-- Not in schema.sql, like the maps. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/042_add_verse_images.sql

CREATE TABLE IF NOT EXISTS verse_images (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  file_name TEXT NOT NULL,
  media_type TEXT NOT NULL,
  file_size BIGINT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  in_use BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Spotify items in the Christian media (added 2026-11-19 at the owner's request: "an interface to spotify to play
-- music under Christian media"). A music_tracks row of media type 'spotify' has no file (file_name '' and
-- file_size 0) and a spotify_link instead: the kind and id of a Spotify track, album, playlist, episode, show or artist
-- ("playlist/37i9dQZF1DX..."), shown with Spotify's own embedded player (full tracks for a visitor signed in to Spotify
-- in that browser, 30-second previews otherwise). Spotify's playback API for Premium accounts was ruled out: since
-- May 2025 Spotify grants it only to large registered businesses.
--
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/060_add_music_spotify.sql

ALTER TABLE music_tracks ADD COLUMN IF NOT EXISTS spotify_link TEXT;

ALTER TABLE music_tracks DROP CONSTRAINT IF EXISTS music_tracks_media_type_check;
ALTER TABLE music_tracks ADD CONSTRAINT music_tracks_media_type_check
  CHECK (media_type IN ('audio/mpeg', 'video/mp4', 'spotify'));

ALTER TABLE music_tracks DROP CONSTRAINT IF EXISTS music_tracks_spotify_link;
ALTER TABLE music_tracks ADD CONSTRAINT music_tracks_spotify_link
  CHECK ((media_type = 'spotify') = (spotify_link IS NOT NULL));

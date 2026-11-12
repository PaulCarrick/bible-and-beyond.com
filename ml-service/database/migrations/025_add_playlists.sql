-- Playlists: a logged-in visitor's own lists of songs from the Christian music section, played one after
-- another on the music page (playlists.py). A user has many playlists (deleting the user deletes them); a
-- playlist has its songs in order (deleting a song takes it out of every playlist). Like the other account
-- tables it is not in schema.sql, so re-applying that file cannot wipe it. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/025_add_playlists.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/025_add_playlists.sql)

CREATE TABLE IF NOT EXISTS playlists (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One playlist of a name per visitor, whatever the case: saving under a name already used replaces it.
CREATE UNIQUE INDEX IF NOT EXISTS playlists_user_name_index ON playlists (user_id, lower(name));

CREATE TABLE IF NOT EXISTS playlist_songs (
  playlist_id BIGINT NOT NULL REFERENCES playlists (id) ON DELETE CASCADE,
  -- The order the songs play in, from 1.
  position INTEGER NOT NULL,
  song_id TEXT NOT NULL REFERENCES music_tracks (id) ON DELETE CASCADE,
  PRIMARY KEY (playlist_id, position)
);

CREATE INDEX IF NOT EXISTS playlist_songs_song_index ON playlist_songs (song_id);

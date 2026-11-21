-- Sharing playlists (added 2026-11-21 at the owner's request: "I can't share a play list"): like My lists
-- (migration 061), a member an administrator allowed (users.share_lists, "Can share lists" on Site users) may share
-- any of their playlists, and every shared playlist is shown on the Public lists page under Members, to everyone who
-- can use the site (playlists.py). Turning share_lists off hides that account's shared playlists without unsharing.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/064_add_playlist_sharing.sql

ALTER TABLE playlists ADD COLUMN IF NOT EXISTS shared_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS playlists_shared ON playlists (shared_at DESC) WHERE shared_at IS NOT NULL;

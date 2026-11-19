-- Sharing My lists (added 2026-11-19 at the owner's request): a member an administrator allowed
-- (users.share_lists, set on the Drupal "Site users" page, false unless turned on) may share any of their lists,
-- and every shared list is shown on the Public lists page under Members, to everyone who can use the site
-- (saved_lists.py). Turning share_lists off hides that account's shared lists without unsharing them.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/061_add_list_sharing.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS share_lists BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE saved_lists ADD COLUMN IF NOT EXISTS shared_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS saved_lists_shared ON saved_lists (shared_at DESC) WHERE shared_at IS NOT NULL;

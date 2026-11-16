-- Groups (added 2026-11-16 at the owner's request: a deacon's page for the people they are responsible for;
-- groups.py, the Drupal "Groups" page). A group belongs to the Drupal user who made it (a Group leader sees and
-- messages only their own; a Website administrator sees all). Its members are site accounts (user_id: they get
-- messages by email, text or both as they chose, and texts only if they agreed to them) or people typed in by
-- name and email (email only). Each membership has its own stop link (stop_token); stopped_at is set when it is
-- followed. group_messages records what was sent (never to whom).
--
-- Not in schema.sql, like the other account tables; make-public-data.sh leaves their rows out. Safe to run more
-- than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/044_add_groups.sql

CREATE TABLE IF NOT EXISTS member_groups (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  owner_uid INTEGER NOT NULL,
  owner_name TEXT NOT NULL DEFAULT '',
  owner_email TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS member_groups_by_owner ON member_groups (owner_uid);

CREATE TABLE IF NOT EXISTS group_members (
  id SERIAL PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES member_groups (id) ON DELETE CASCADE,
  user_id INTEGER REFERENCES users (id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT '',
  email TEXT,
  phone TEXT NOT NULL DEFAULT '',
  stop_token TEXT NOT NULL UNIQUE,
  stopped_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((user_id IS NOT NULL AND email IS NULL) OR (user_id IS NULL AND email IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS group_members_one_account ON group_members (group_id, user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS group_members_one_address ON group_members (group_id, lower(email)) WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS group_messages (
  id SERIAL PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES member_groups (id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('message', 'verse', 'picture')),
  subject TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL DEFAULT '',
  sent_by TEXT NOT NULL DEFAULT '',
  emailed INTEGER NOT NULL DEFAULT 0,
  texted INTEGER NOT NULL DEFAULT 0,
  skipped INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

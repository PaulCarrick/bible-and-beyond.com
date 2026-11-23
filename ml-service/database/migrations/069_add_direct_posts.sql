-- Posts to one member (added 2026-11-23 at the owner's request): a Conversations post can be sent to one member
-- (conversation_posts.recipient_id) and is then seen only by its author and that member (and the site's
-- administrators). The first time someone sends to a member, the member is asked to accept or decline
-- (message_permissions, one row per sender and recipient): until they accept, the sender's posts to them are held;
-- once they decline, the sender cannot send to them. The member can change it later on My account.
-- direct_posts.py and conversations.py.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/069_add_direct_posts.sql

ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS recipient_id INTEGER REFERENCES users (id) ON DELETE CASCADE;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'conversation_posts_recipient_board') THEN
    ALTER TABLE conversation_posts ADD CONSTRAINT conversation_posts_recipient_board
      CHECK (recipient_id IS NULL OR (board = 'conversations' AND recipient_id <> user_id));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS conversation_posts_recipient ON conversation_posts (recipient_id) WHERE recipient_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS message_permissions (
  sender_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined')),
  -- The link in the request email or text, which answers it without logging in.
  token TEXT NOT NULL UNIQUE,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- When the request email or text was sent (it goes once).
  notified_at TIMESTAMPTZ,
  answered_at TIMESTAMPTZ,
  PRIMARY KEY (sender_id, recipient_id),
  CHECK (sender_id <> recipient_id)
);

CREATE INDEX IF NOT EXISTS message_permissions_recipient ON message_permissions (recipient_id, status);

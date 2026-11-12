-- Conversations: a blog of posts written by members of the main site (conversations.py). Only accounts an
-- administrator allowed (users.use_conversations, set on the Drupal "Site users" page, false unless turned
-- on) can read, write or search them; every allowed member sees every post, and only its author can change
-- or delete one. Deleting the user deletes their posts. Like the other account tables it is not in
-- schema.sql, so re-applying that file cannot wipe it. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/028_add_conversations.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/028_add_conversations.sql)

ALTER TABLE users ADD COLUMN IF NOT EXISTS use_conversations BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS conversation_posts (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  -- The post as the editor made it, cleaned (contact.check_rich_text), and its plain text for searching.
  body TEXT NOT NULL,
  body_text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS conversation_posts_created_index ON conversation_posts (created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS conversation_posts_user_index ON conversation_posts (user_id);

-- Replies to Conversations posts (conversations.py): any member allowed Conversations (users.use_conversations)
-- can reply to any post; only a reply's author can change or delete it. Deleting the post or the user deletes
-- their replies. Like the other account tables it is not in schema.sql, so re-applying that file cannot wipe
-- it. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/029_add_conversation_replies.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/029_add_conversation_replies.sql)

CREATE TABLE IF NOT EXISTS conversation_replies (
  id BIGSERIAL PRIMARY KEY,
  post_id BIGINT NOT NULL REFERENCES conversation_posts (id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  -- The reply as the editor made it, cleaned (contact.check_rich_text), and its plain text for searching.
  body TEXT NOT NULL,
  body_text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS conversation_replies_post_index ON conversation_replies (post_id, created_at, id);
CREATE INDEX IF NOT EXISTS conversation_replies_user_index ON conversation_replies (user_id);

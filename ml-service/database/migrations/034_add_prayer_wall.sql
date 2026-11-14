-- The Prayer Wall: posts and replies like Conversations, kept apart from them by a board on each post
-- ('conversations' or 'prayer'; conversations.py). Replies belong to their post, so they need no board.
-- Every post written before this is a Conversations post. Like the other account tables it is not in
-- schema.sql. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/034_add_prayer_wall.sql

ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS board TEXT NOT NULL DEFAULT 'conversations';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'conversation_posts_board_check') THEN
    ALTER TABLE conversation_posts ADD CONSTRAINT conversation_posts_board_check CHECK (board IN ('conversations', 'prayer'));
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS conversation_posts_board_created_index ON conversation_posts (board, created_at DESC, id DESC);

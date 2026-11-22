-- Get Conversation Posts (added 2026-11-22 at the owner's request): an account an administrator ticks on the Drupal
-- "Site users" page (users.get_conversation_posts, false unless turned on) is emailed every new post and every new
-- reply on the Conversations board (conversations.send_new_post_emails, send_new_reply_emails). Each email has a
-- link that turns it off for that account (conversation_posts_token, handled by subscriptions._unsubscribe); the
-- token is made the first time the box is ticked.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/065_add_get_conversation_posts.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS get_conversation_posts BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE users ADD COLUMN IF NOT EXISTS conversation_posts_token TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS users_conversation_posts_token ON users (conversation_posts_token)
  WHERE conversation_posts_token IS NOT NULL;

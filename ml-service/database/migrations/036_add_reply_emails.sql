-- "Email me replies" on a Conversations post (added 2026-11-15 at the owner's request; conversations.py).
--
-- email_replies: when on, each new reply by someone else is emailed to the post's author (a confirmed address
-- only). reply_email_token: a random token for the "stop these emails" link in those emails (the devotionals'
-- unsubscribe link, subscriptions.py), made when the choice is first turned on. Conversations posts only; off on
-- every older post. Like the other account tables it is not in schema.sql. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/036_add_reply_emails.sql

ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS email_replies BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS reply_email_token TEXT UNIQUE;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'conversation_posts_email_replies_check') THEN
    ALTER TABLE conversation_posts ADD CONSTRAINT conversation_posts_email_replies_check
      CHECK (board = 'conversations' OR NOT email_replies);
  END IF;
END
$$;

-- Prayer Wall options (added 2026-11-15 at the owner's request) and the prayer list email.
--
-- On a Prayer Wall post (board 'prayer') the author may choose:
--   is_anonymous: the post shows "Anonymous" instead of the author's name (administrators still see who wrote it);
--   is_private: only the author and the site administrators see it, and it is never emailed;
--   email_to_prayer_list: it goes in the next prayer list email of every subscriber (not when private);
--   answered_at: when the author marked it answered (NULL when not); an answered request is not emailed.
-- listed_at is when the post joined the prayer list (set when the email choice is turned on), so a subscriber's
-- next email holds the requests listed since their last one. All of them are off (NULL) on a Conversations post.
--
-- prayer_list_subscriptions: one row per account that gets the prayer list by email each week (on send_weekday,
-- 0 Monday to 6 Sunday, at send_time), like devotional_subscriptions (prayer_list.py). sent_through is when the
-- last email's requests were read: the next holds those listed after it, and only those of the past week.
--
-- users.see_private_prayers: an administrator turned it on (Drupal Site users page) for the site's own
-- administrators; their prayer list email also holds the week's private requests.
--
-- Like the other account tables they are not in schema.sql. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/035_add_prayer_wall_options.sql

ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS is_anonymous BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS is_private BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS email_to_prayer_list BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS listed_at TIMESTAMPTZ;
ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS answered_at TIMESTAMPTZ;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'conversation_posts_prayer_options_check') THEN
    ALTER TABLE conversation_posts ADD CONSTRAINT conversation_posts_prayer_options_check CHECK (
      (board = 'prayer' OR (NOT is_anonymous AND NOT is_private AND NOT email_to_prayer_list))
      AND NOT (is_private AND email_to_prayer_list)
    );
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'conversation_posts_answered_check') THEN
    ALTER TABLE conversation_posts ADD CONSTRAINT conversation_posts_answered_check CHECK (board = 'prayer' OR answered_at IS NULL);
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS conversation_posts_prayer_list_index ON conversation_posts (listed_at)
  WHERE email_to_prayer_list;

CREATE TABLE IF NOT EXISTS prayer_list_subscriptions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
  send_weekday SMALLINT NOT NULL DEFAULT 0 CHECK (send_weekday BETWEEN 0 AND 6),
  send_time TIME NOT NULL,
  timezone TEXT NOT NULL,
  -- The visitor's own date of the last weekly email (or of the week's day when there was nothing to send).
  last_sent_on DATE,
  sent_through TIMESTAMPTZ NOT NULL DEFAULT now(),
  attempts_on DATE,
  attempts INTEGER NOT NULL DEFAULT 0,
  unsubscribe_token TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Added the same day, before this was first deployed (a database that already ran the lines above needs it).
ALTER TABLE prayer_list_subscriptions ADD COLUMN IF NOT EXISTS send_weekday SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS see_private_prayers BOOLEAN NOT NULL DEFAULT false;

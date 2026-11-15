-- A verse a day (added 2026-11-15 at the owner's request; verse_a_day.py).
--
-- One row per account that asked for a randomly chosen verse each day, by email (to a confirmed address) and,
-- if the member asked for texts, by text too. send_time is in the member's own time zone. last_sent_on is the
-- member's own date of the last one; last_verse (book:chapter:verse) keeps the next day's from repeating it.
-- unsubscribe_token is for the stop link (the devotionals' unsubscribe endpoint, subscriptions.py).
-- Like the other account tables it is not in schema.sql. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/038_add_verse_a_day.sql

CREATE TABLE IF NOT EXISTS verse_subscriptions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
  send_time TIME NOT NULL,
  timezone TEXT NOT NULL,
  last_sent_on DATE,
  last_verse TEXT,
  attempts_on DATE,
  attempts INTEGER NOT NULL DEFAULT 0,
  unsubscribe_token TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

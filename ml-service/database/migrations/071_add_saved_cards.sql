-- Saved verse cards (added 2026-11-26 at the owner's request): every card a logged-in member downloads or sends
-- from "Make your own card" is kept on their My cards page, and a group leader can attach one of their own cards to
-- a group's Send a message. The picture is a file (data/saved-cards/<file_name>, saved_cards.py), never in the
-- database; its details are here.
--
-- users.drupal_uid links a site account to a Drupal administrator's account, chosen on Site users; without it the
-- Drupal account is matched to the site account with the same email address.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/071_add_saved_cards.sql

CREATE TABLE IF NOT EXISTS saved_cards (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  translation TEXT NOT NULL,
  book SMALLINT NOT NULL,
  chapter SMALLINT NOT NULL,
  verse SMALLINT NOT NULL,
  background_id TEXT NOT NULL,
  reference TEXT NOT NULL,
  caption TEXT NOT NULL,
  words TEXT NOT NULL,
  file_name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, translation, book, chapter, verse, background_id)
);

CREATE INDEX IF NOT EXISTS saved_cards_user_created ON saved_cards (user_id, created_at DESC);

ALTER TABLE users ADD COLUMN IF NOT EXISTS drupal_uid INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS users_drupal_uid ON users (drupal_uid) WHERE drupal_uid IS NOT NULL;

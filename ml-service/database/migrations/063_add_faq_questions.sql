-- A site's own FAQ questions (added 2026-11-20 at the owner's request, first for the CR site): when this table has
-- rows they are the FAQ list, in position order under their headings; while it is empty the site uses the list
-- built into faq.py (BUILT_IN_GROUPS). Each answer and the site owner's note are kept by the question's text, as
-- before. Changed with scripts/manage_faq_questions.py. Each site's database has its own.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/063_add_faq_questions.sql

CREATE TABLE IF NOT EXISTS faq_questions (
  id SERIAL PRIMARY KEY,
  heading TEXT NOT NULL,
  question TEXT NOT NULL UNIQUE,
  position INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

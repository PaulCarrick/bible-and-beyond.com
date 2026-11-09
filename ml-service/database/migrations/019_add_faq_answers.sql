-- The answers to the fixed FAQ questions, kept so Gemini is asked again only when an answer is more than a
-- month old (faq.ANSWER_KEEP_DAYS) or the instructions sent with that question have changed. Keyed by the
-- question's wording, not its number, because the numbers move when a question is added. Safe to run more
-- than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/019_add_faq_answers.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/019_add_faq_answers.sql)

CREATE TABLE IF NOT EXISTS faq_answers (
  question TEXT PRIMARY KEY,
  answer TEXT NOT NULL,
  -- SHA-256 of the system prompt the answer was written with.
  prompt_hash TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

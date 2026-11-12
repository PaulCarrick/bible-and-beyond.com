-- The answers of the AI searches, kept so the same search again costs no AI call and is quick (ai_cache.py):
-- the verses Gemini suggested for a query (kind 'verses', ai_search.py) and the embedding of a query's words
-- (kind 'embedding', passage_embeddings.py). Like faq_answers, a row is used while it is less than 30 days old
-- and was made with the same instructions (version: a hash of the prompt, or the model and its size).
-- The query is kept only as a SHA-256 of its normalized words, so the table does not hold what visitors typed.
-- Not in schema.sql (visitor-made data, like faq_answers). Safe to run twice.

CREATE TABLE IF NOT EXISTS ai_search_cache (
  kind TEXT NOT NULL CHECK (kind IN ('verses', 'embedding')),
  query_hash TEXT NOT NULL,
  version TEXT NOT NULL,
  result JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (kind, query_hash)
);

CREATE INDEX IF NOT EXISTS ai_search_cache_created_at ON ai_search_cache (created_at);

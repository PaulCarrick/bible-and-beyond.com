-- AI search of the commentaries, devotionals, other books and songs (passage_embeddings.py).
--
-- Each passage is cut into pieces, and each piece is turned once into an embedding (256 numbers from
-- Google's gemini-embedding-001) by scripts/embed_passages.py. A search finds the pieces closest in
-- meaning to the visitor's words. The text itself stays in its own table; start_offset and end_offset
-- say which part of it a piece is, and text_hash says which text it was made from (a changed text is
-- embedded again).
--
-- Where a piece comes from, by kind:
--   commentary: source_id is the commentary, entry_id the commentary_entries row.
--   devotional: source_id is the devotional or Other book, section, unit and part its entry.
--   music:      source_id is the song (its words, title and author).
-- Like the other derived tables, a reloaded text leaves its old rows unused until the script runs again.
-- Safe to run twice.

CREATE TABLE IF NOT EXISTS passage_embeddings (
  kind TEXT NOT NULL CHECK (kind IN ('commentary', 'devotional', 'music')),
  source_id TEXT NOT NULL,
  entry_id BIGINT NOT NULL DEFAULT 0,
  section INTEGER NOT NULL DEFAULT 0,
  unit INTEGER NOT NULL DEFAULT 0,
  part INTEGER NOT NULL DEFAULT 0,
  piece INTEGER NOT NULL,
  start_offset INTEGER NOT NULL,
  end_offset INTEGER NOT NULL,
  text_hash TEXT NOT NULL,
  embedding halfvec(256) NOT NULL,
  PRIMARY KEY (kind, source_id, entry_id, section, unit, part, piece)
);

-- One index per kind, so a search of one kind does not wade through the others.
CREATE INDEX IF NOT EXISTS passage_embeddings_commentary ON passage_embeddings
  USING hnsw (embedding halfvec_cosine_ops) WHERE kind = 'commentary';
CREATE INDEX IF NOT EXISTS passage_embeddings_devotional ON passage_embeddings
  USING hnsw (embedding halfvec_cosine_ops) WHERE kind = 'devotional';
CREATE INDEX IF NOT EXISTS passage_embeddings_music ON passage_embeddings
  USING hnsw (embedding halfvec_cosine_ops) WHERE kind = 'music';

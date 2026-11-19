-- Kindle books (added 2026-11-19 at the owner's request): books in the Kindle web reader (read.amazon.com), listed
-- with the Devotionals or with the Other books (collection) but kept apart from them, since their text never comes
-- to this site (kindle_books.py). Each has a title, an optional author, the Kindle address and an optional cover picture, whose file is kept in
-- data/kindle-covers/ (cover_type is its extension, cover_version its time, for the browser's cache).
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/062_add_kindle_books.sql

CREATE TABLE IF NOT EXISTS kindle_books (
  id SERIAL PRIMARY KEY,
  collection TEXT NOT NULL CHECK (collection IN ('devotionals', 'books')),
  title TEXT NOT NULL,
  author TEXT NOT NULL DEFAULT '',
  address TEXT NOT NULL,
  is_published BOOLEAN NOT NULL DEFAULT true,
  cover_type TEXT CHECK (cover_type IN ('.png', '.jpg', '.webp', '.gif')),
  cover_version INTEGER NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

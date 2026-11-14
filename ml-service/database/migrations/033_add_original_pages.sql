-- "Preserve original pages" on the Upload form: the pages of the PDF a part of the text came from, as
-- {"document": "<20 hex>", "first": 5, "last": 9}; the reader shows those pages (pictures in data/library-pages/).
-- NULL for everything else. Adding a column with no default changes no row.
ALTER TABLE commentary_entries ADD COLUMN IF NOT EXISTS original_pages jsonb;
ALTER TABLE commentary_introductions ADD COLUMN IF NOT EXISTS original_pages jsonb;
ALTER TABLE devotional_entries ADD COLUMN IF NOT EXISTS original_pages jsonb;

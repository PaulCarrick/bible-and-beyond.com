-- Commentaries and devotionals can be hidden and shown like Bibles (Drupal's Commentaries and Devotionals
-- pages), and a commentary records where its text came from, so one uploaded from another source is
-- credited correctly. Everything loaded so far stays published and keeps the Free Use Bible API as source.
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/016_add_commentary_devotional_publishing.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/016_add_commentary_devotional_publishing.sql)

ALTER TABLE commentaries ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE commentaries ADD COLUMN IF NOT EXISTS source_name TEXT NOT NULL DEFAULT 'Free Use Bible API';
ALTER TABLE commentaries ADD COLUMN IF NOT EXISTS source_url TEXT NOT NULL DEFAULT 'https://bible.helloao.org';

ALTER TABLE devotionals ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT true;

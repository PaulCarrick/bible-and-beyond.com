-- A song's words as a PDF or a picture, shown on the music page in place of the typed words when present
-- (music.py). The file is kept in the music folder as <id>-words.pdf (or .png, .jpg, .webp, .gif); the typed
-- words stay for the search. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/024_add_music_words_file.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/024_add_music_words_file.sql)

ALTER TABLE music_tracks ADD COLUMN IF NOT EXISTS words_file_name TEXT;
ALTER TABLE music_tracks ADD COLUMN IF NOT EXISTS words_media_type TEXT;

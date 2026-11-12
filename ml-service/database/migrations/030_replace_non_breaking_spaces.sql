-- The site's editor (Quill 2) saved every space of a note, a Conversations post or a reply as a non-breaking space
-- (&nbsp;), so the browser could only wrap a paragraph in the middle of a word. The editor and the server's cleaner
-- now keep plain spaces (contact._Cleaner); this turns those already saved into plain spaces too. Only the spaces
-- change, not the words or the time a text was last changed. Safe to run more than once: once replaced, no row
-- matches. The site owner's FAQ notes are not touched.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/030_replace_non_breaking_spaces.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/030_replace_non_breaking_spaces.sql)

UPDATE notes
SET body = replace(replace(body, '&nbsp;', ' '), chr(160), ' '), body_text = replace(body_text, chr(160), ' ')
WHERE body LIKE '%&nbsp;%' OR strpos(body, chr(160)) > 0 OR strpos(body_text, chr(160)) > 0;

UPDATE conversation_posts
SET body = replace(replace(body, '&nbsp;', ' '), chr(160), ' '), body_text = replace(body_text, chr(160), ' ')
WHERE body LIKE '%&nbsp;%' OR strpos(body, chr(160)) > 0 OR strpos(body_text, chr(160)) > 0;

UPDATE conversation_replies
SET body = replace(replace(body, '&nbsp;', ' '), chr(160), ' '), body_text = replace(body_text, chr(160), ' ')
WHERE body LIKE '%&nbsp;%' OR strpos(body, chr(160)) > 0 OR strpos(body_text, chr(160)) > 0;

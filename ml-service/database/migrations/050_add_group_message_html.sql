-- Formatted group messages (added 2026-11-17 at the owner's request: the message boxes in the Drupal admin use the
-- editor). group_schedules.html keeps a scheduled message's formatting (cleaned HTML, contact.check_rich_text);
-- text keeps its plain-text copy, which texts and older schedules use. NULL for a picture message, a verse card,
-- or a message written before this.
--
-- Not in schema.sql, like the other group tables. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/050_add_group_message_html.sql

ALTER TABLE group_schedules ADD COLUMN IF NOT EXISTS html TEXT;

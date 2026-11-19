-- A scheduled email to one member of a group (added 2026-11-18 at the owner's request: "Send at" on the Email box
-- of a member in the group's list, now by default, or a later date and time). Such a schedule is a one-time
-- message with member_id set: the five-minute job emails it to that member only (groups.email_member), as Send
-- does at once. Removing the member removes it. NULL for the group's own scheduled emails.
--
-- Not in schema.sql, like the rest of the groups tables. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/052_add_group_schedule_member.sql

ALTER TABLE group_schedules ADD COLUMN IF NOT EXISTS member_id INTEGER REFERENCES group_members (id) ON DELETE CASCADE;

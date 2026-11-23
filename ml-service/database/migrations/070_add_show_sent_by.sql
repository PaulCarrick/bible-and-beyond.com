-- "Add the “Sent by …” line" (added 2026-11-23 at the owner's request): whether an email an administrator sets up
-- ends with the line saying who sent it through the site ("Sent by Paul to the group “Name” through Free Study
-- Bible", "A reminder of “Task” on …, from Paul through …"). On by default; unticked, the line is left out (a group
-- email keeps each member's stop links). Kept for scheduled group emails and for tasks' reminders; Message a day and
-- a group's Send now choose it each time.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/070_add_show_sent_by.sql

ALTER TABLE group_schedules ADD COLUMN IF NOT EXISTS show_sent_by BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS show_sent_by BOOLEAN NOT NULL DEFAULT true;

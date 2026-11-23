-- A note on a scheduled task (added 2026-11-22 at the owner's request): optional words typed on the Schedule form
-- (the group emails' editor), added under the task's notification in that person's reminders, by email and text
-- (scheduled_tasks.send_due). note_html is the cleaned HTML, note_text its plain copy; both '' when there is none.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/066_add_scheduled_task_note.sql

ALTER TABLE admin_scheduled_tasks ADD COLUMN IF NOT EXISTS note_html TEXT NOT NULL DEFAULT '';

ALTER TABLE admin_scheduled_tasks ADD COLUMN IF NOT EXISTS note_text TEXT NOT NULL DEFAULT '';

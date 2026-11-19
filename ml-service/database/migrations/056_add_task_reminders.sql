-- Task reminders (added 2026-11-19 at the owner's request: "send a reminder email for each scheduled task" and "a
-- field the days before for the first and second notices"; scheduled_tasks.send_due, run by the five-minute job).
--
-- admin_tasks: how many days before the scheduled date each notification goes (NULL: that one is not sent), the
-- time zone its 8:00 AM sending time is in (the owner's Drupal time zone when they saved it), and the owner's
-- address (the reminders' Reply-To).
-- admin_scheduled_tasks: when each reminder was sent or given up (NULL: not yet), and how it went.
--
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/056_add_task_reminders.sql

ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS first_notice_days SMALLINT CHECK (first_notice_days BETWEEN 0 AND 90);
ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS second_notice_days SMALLINT CHECK (second_notice_days BETWEEN 0 AND 90);
ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';
ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS owner_email TEXT NOT NULL DEFAULT '';

ALTER TABLE admin_scheduled_tasks ADD COLUMN IF NOT EXISTS first_notice_at TIMESTAMPTZ;
ALTER TABLE admin_scheduled_tasks ADD COLUMN IF NOT EXISTS first_notice_result TEXT NOT NULL DEFAULT '';
ALTER TABLE admin_scheduled_tasks ADD COLUMN IF NOT EXISTS second_notice_at TIMESTAMPTZ;
ALTER TABLE admin_scheduled_tasks ADD COLUMN IF NOT EXISTS second_notice_result TEXT NOT NULL DEFAULT '';

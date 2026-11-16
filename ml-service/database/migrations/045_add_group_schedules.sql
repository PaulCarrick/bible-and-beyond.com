-- Scheduled group messages (added 2026-11-16 at the owner's request: "Add a scheduled email" on a group's page;
-- group_schedules.py). A leader sets a message, a verse card or a picture message to go to the group once on a
-- date, every week on a weekday, every month on a day (31 = the last day of a shorter month), or every month on
-- the first, second, third, fourth or last of a weekday, at a time in a time zone. next_run_at is the next time
-- it goes (UTC); NULL once a one-time message has gone. The five-minute job sends what is due
-- (scripts/send_devotional_emails.py).
--
-- Not in schema.sql; make-public-data.sh leaves its rows out. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/045_add_group_schedules.sql

CREATE TABLE IF NOT EXISTS group_schedules (
  id SERIAL PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES member_groups (id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('message', 'verse', 'picture')),
  subject TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL DEFAULT '',
  repeat TEXT NOT NULL CHECK (repeat IN ('once', 'weekly', 'monthly_day', 'monthly_weekday')),
  on_date DATE,
  day_of_month INTEGER CHECK (day_of_month BETWEEN 1 AND 31),
  weekday INTEGER CHECK (weekday BETWEEN 0 AND 6),
  week_of_month INTEGER CHECK (week_of_month BETWEEN 1 AND 5),
  send_time TIME NOT NULL,
  timezone TEXT NOT NULL,
  next_run_at TIMESTAMPTZ,
  last_run_at TIMESTAMPTZ,
  last_result TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS group_schedules_due ON group_schedules (next_run_at) WHERE next_run_at IS NOT NULL;

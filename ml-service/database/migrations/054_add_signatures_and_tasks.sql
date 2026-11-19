-- Signatures and tasks (added 2026-11-19 at the owner's request; signatures.py, admin_tasks.py, the Drupal
-- "Signatures" and "Tasks" pages). Each belongs to the Drupal user who made it (owner_uid): they see only their
-- own, and someone with "administer all signatures and tasks" sees everyone's.
--
-- A signature is a name and formatted words (html, cleaned with the contact form's allowlist, and a plain-text
-- copy) to go at the foot of emails (not used by any email yet).
--
-- A task is a name, a formatted description, how often it comes round (repeat: weekly on a weekday, every two
-- weeks from a first date, or monthly on a day of the month, 29 to 31 meaning the last day in shorter months),
-- and the words of a first and a second notification (not sent yet). The formatted fields may be empty ('').
--
-- Not in schema.sql, like the other account tables; make-public-data.sh leaves their rows out. Safe to run more
-- than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/054_add_signatures_and_tasks.sql

CREATE TABLE IF NOT EXISTS admin_signatures (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  html TEXT NOT NULL,
  text TEXT NOT NULL,
  owner_uid INTEGER NOT NULL,
  owner_name TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admin_signatures_by_owner ON admin_signatures (owner_uid);

CREATE TABLE IF NOT EXISTS admin_tasks (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  description_html TEXT NOT NULL DEFAULT '',
  description_text TEXT NOT NULL DEFAULT '',
  repeat TEXT NOT NULL CHECK (repeat IN ('weekly', 'biweekly', 'monthly')),
  weekday SMALLINT CHECK (weekday BETWEEN 0 AND 6),
  first_date DATE,
  day_of_month SMALLINT CHECK (day_of_month BETWEEN 1 AND 31),
  first_notification_html TEXT NOT NULL DEFAULT '',
  first_notification_text TEXT NOT NULL DEFAULT '',
  second_notification_html TEXT NOT NULL DEFAULT '',
  second_notification_text TEXT NOT NULL DEFAULT '',
  owner_uid INTEGER NOT NULL,
  owner_name TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (repeat = 'weekly' AND weekday IS NOT NULL)
    OR (repeat = 'biweekly' AND first_date IS NOT NULL)
    OR (repeat = 'monthly' AND day_of_month IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS admin_tasks_by_owner ON admin_tasks (owner_uid);

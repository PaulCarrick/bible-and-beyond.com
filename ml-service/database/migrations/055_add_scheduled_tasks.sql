-- Scheduled tasks (added 2026-11-19 at the owner's request; scheduled_tasks.py, the Drupal "Scheduled tasks" page
-- and Schedule beside each task): one task (admin_tasks) given to one site account (users) on one of the task's
-- dates (on_date, one of its next occurrences when it was chosen). It belongs with its task: whoever may see the
-- task may see and change it. Deleting the task or the account deletes it. created_by_uid/name say which Drupal
-- user scheduled it.
--
-- Not in schema.sql, like the other account tables; make-public-data.sh leaves their rows out. Safe to run more
-- than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/055_add_scheduled_tasks.sql

CREATE TABLE IF NOT EXISTS admin_scheduled_tasks (
  id SERIAL PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES admin_tasks (id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  on_date DATE NOT NULL,
  created_by_uid INTEGER NOT NULL,
  created_by_name TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (task_id, user_id, on_date)
);

CREATE INDEX IF NOT EXISTS admin_scheduled_tasks_by_date ON admin_scheduled_tasks (on_date);
CREATE INDEX IF NOT EXISTS admin_scheduled_tasks_by_user ON admin_scheduled_tasks (user_id);

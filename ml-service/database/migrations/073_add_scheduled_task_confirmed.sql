-- A "confirmed" flag on each scheduled task (added 2026-11-27 at the owner's request): false for a new one.
-- The scheduled tasks that already exist when it is added are backfilled as confirmed (true).
--
-- The column is added with DEFAULT true, which sets every existing row to true, and the default is then made
-- false for rows added later. Both happen only when the column is first added (every migration runs again at
-- each deploy and container start, so a later run must never turn a false back to true).
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/073_add_scheduled_task_confirmed.sql

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema() AND table_name = 'admin_scheduled_tasks' AND column_name = 'confirmed'
  ) THEN
    ALTER TABLE admin_scheduled_tasks ADD COLUMN confirmed BOOLEAN NOT NULL DEFAULT true;
    ALTER TABLE admin_scheduled_tasks ALTER COLUMN confirmed SET DEFAULT false;
  END IF;
END
$$;

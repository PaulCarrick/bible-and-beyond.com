-- The sign-up sheet (added 2026-11-27 at the owner's request; signup_sheet.py):
--   admin_tasks.expected_occurrences: how many people a task expects on each of its dates (default 1). A blank
--     sheet has that many rows for the task, numbered when more than one ("Baked Goods 1", "Baked Goods 2"); a filled
--     one adds blank rows up to it; members cannot ask for a date that already has that many (member_task_requests).
--   admin_tasks.sheet_order: where the task comes within a date on the sheet (lowest first, then by name).
--   member_groups.sheet_title, sheet_notes_html: the title and the notes at the foot last used for the group's sheet.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/074_add_task_sheet_fields.sql

ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS expected_occurrences INTEGER NOT NULL DEFAULT 1;
ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS sheet_order INTEGER NOT NULL DEFAULT 0;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'admin_tasks_expected_occurrences_range') THEN
    ALTER TABLE admin_tasks ADD CONSTRAINT admin_tasks_expected_occurrences_range CHECK (expected_occurrences BETWEEN 1 AND 20);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'admin_tasks_sheet_order_range') THEN
    ALTER TABLE admin_tasks ADD CONSTRAINT admin_tasks_sheet_order_range CHECK (sheet_order BETWEEN 0 AND 999);
  END IF;
END
$$;

ALTER TABLE member_groups ADD COLUMN IF NOT EXISTS sheet_title TEXT NOT NULL DEFAULT '';
ALTER TABLE member_groups ADD COLUMN IF NOT EXISTS sheet_notes_html TEXT NOT NULL DEFAULT '';

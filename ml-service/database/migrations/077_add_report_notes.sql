-- Notes saved for a report (added 2026-11-27 at the owner's request): the notes at the foot of a group's sign-up
-- sheet are kept only when "Save this note" is ticked, and belong to that report for that group, not to every
-- report. report names the report ('sign_up_sheet'); one row per report and group.
--
-- The notes the sign-up sheet kept on the group before (member_groups.sheet_notes_html) are copied in once; a row
-- that exists already (saved or cleared since) is never overwritten, so running this again changes nothing.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/077_add_report_notes.sql

CREATE TABLE IF NOT EXISTS report_notes (
  report TEXT NOT NULL,
  group_id INTEGER NOT NULL REFERENCES member_groups (id) ON DELETE CASCADE,
  notes_html TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (report, group_id)
);

INSERT INTO report_notes (report, group_id, notes_html)
SELECT 'sign_up_sheet', id, sheet_notes_html FROM member_groups WHERE sheet_notes_html <> ''
ON CONFLICT (report, group_id) DO NOTHING;

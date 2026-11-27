-- The group a task belongs to (added 2026-11-27 at the owner's request): the sign-up sheet of a group lists only its
-- tasks (signup_sheet.py), and members may ask only for tasks of the groups they are in (member_task_requests.py).
-- NULL (every task that existed before, until a group is chosen on its Edit page): on no group's sheet and offered
-- to nobody. Deleting the group leaves its tasks without one.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/075_add_task_group.sql

ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES member_groups (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS admin_tasks_by_group ON admin_tasks (group_id);

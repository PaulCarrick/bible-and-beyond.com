-- A signature on task reminder emails (added 2026-11-23 at the owner's request): admin_tasks.signature_id, one of
-- the task owner's signatures (admin_signatures) or NULL for none. Added at the foot of every reminder email of the
-- task (scheduled_tasks.compose_reminder), not to texts. Deleting the signature leaves the task with none.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/068_add_task_signature.sql

ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS signature_id INTEGER REFERENCES admin_signatures (id) ON DELETE SET NULL;

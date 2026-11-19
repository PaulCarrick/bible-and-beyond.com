-- A scheduled email's signature (added 2026-11-19 at the owner's request: "not the group the scheduled email. Each
-- schedule can have a different signature"). One of the group leader's signatures (admin_signatures), added after
-- the words of every email the schedule sends; NULL for none. Deleting the signature leaves the schedule with none.
--
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/057_add_group_schedule_signature.sql

ALTER TABLE group_schedules ADD COLUMN IF NOT EXISTS signature_id INTEGER REFERENCES admin_signatures (id) ON DELETE SET NULL;

-- Stopping scheduled group emails (added 2026-11-17 at the owner's request: an unsubscribe link in a scheduled
-- email that stops that scheduled email only, without taking the member out of the group, and an "unsubscribe
-- all" that stops all of the group's scheduled emails). groups.py and group_schedules.py.
--
-- group_schedule_stops: one row per member per scheduled email they stopped (a lookup table, so any number of
-- members can stop any number of a group's scheduled emails). Removing the member or the schedule removes it.
-- group_members.schedules_stopped_at: set when the member stopped all the group's scheduled emails, including any
-- added later. Neither stops what the leader sends by hand (group_members.stopped_at, the group's own stop link,
-- still stops everything).
--
-- Not in schema.sql, like the other group tables; make-public-data.sh leaves its rows out. Safe to run more than
-- once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/048_add_group_schedule_stops.sql

CREATE TABLE IF NOT EXISTS group_schedule_stops (
  schedule_id INTEGER NOT NULL REFERENCES group_schedules (id) ON DELETE CASCADE,
  member_id INTEGER NOT NULL REFERENCES group_members (id) ON DELETE CASCADE,
  stopped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (schedule_id, member_id)
);

CREATE INDEX IF NOT EXISTS group_schedule_stops_member ON group_schedule_stops (member_id);

ALTER TABLE group_members ADD COLUMN IF NOT EXISTS schedules_stopped_at TIMESTAMPTZ;

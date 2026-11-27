-- A group's Description (added 2026-11-27 at the owner's request): one line such as "After Church Fellowship Time -
-- Thank you for Serving the Body", used as the title of its sign-up sheet (signup_sheet.py; the group's name when
-- empty). Called headline here, since member_groups.description already holds the leader's private notes.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/076_add_group_headline.sql

ALTER TABLE member_groups ADD COLUMN IF NOT EXISTS headline TEXT NOT NULL DEFAULT '';

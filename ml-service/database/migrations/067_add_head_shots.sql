-- Head shots (added 2026-11-23 at the owner's request): a member's own picture, uploaded on My account and shown in
-- the account icon at the top right of the site. The picture is a file in the head shots folder (head_shots.py,
-- data/head-shots/<user id>.webp), never in the database; head_shot_version is NULL when there is none and goes up
-- by one with each new picture (it is in the picture's address, so a browser never shows an old one).
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/067_add_head_shots.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS head_shot_version INTEGER;

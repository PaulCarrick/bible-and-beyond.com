-- A saved verse card on a scheduled group message and on an email to one member (added 2026-11-26 at the owner's
-- request, after the card on Send a message): the card (saved_cards) and the site account it belongs to, the one of
-- the administrator who set it up, found when it was saved. A card deleted later leaves the message without it.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/072_add_schedule_cards.sql

ALTER TABLE group_schedules ADD COLUMN IF NOT EXISTS saved_card_id INTEGER REFERENCES saved_cards (id) ON DELETE SET NULL;

ALTER TABLE group_schedules ADD COLUMN IF NOT EXISTS card_user_id INTEGER REFERENCES users (id) ON DELETE SET NULL;

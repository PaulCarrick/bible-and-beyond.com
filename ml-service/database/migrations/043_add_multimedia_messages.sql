-- Picture messages (added 2026-11-16 at the owner's request; message_cards.py): users.send_multimedia is the
-- "Send Multimedia Messages" checkbox on the sign-up form and My account. When on, the verse a day and the daily
-- devotional come as a picture (the words over one of the verse a day pictures), inline in the email and as an
-- MMS with the text, whichever the member chose (send_via_email, send_via_sms). Off for everyone until ticked.
--
-- Like the other account columns it is not in schema.sql. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/043_add_multimedia_messages.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS send_multimedia BOOLEAN NOT NULL DEFAULT false;

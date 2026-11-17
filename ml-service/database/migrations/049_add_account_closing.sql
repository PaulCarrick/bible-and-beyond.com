-- Closing an account (added 2026-11-17 at the owner's request: the member's "Delete my account" became "Close my
-- account": "let's not actually delete the account just add a disable flag and don't permit any account related
-- actions (including sending emails) and login"). users.disabled_at is set when the member closes their account
-- on the My account page (accounts.close_account). A closed account cannot log in, has no sessions or emailed
-- links, and is sent no emails and no texts (contact.send_email, sms.send_text, and the sending loops). Its data
-- stays. An administrator can reopen it (clear the flag) or delete it on Drupal's Site users page.
--
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/049_add_account_closing.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS disabled_at TIMESTAMPTZ;

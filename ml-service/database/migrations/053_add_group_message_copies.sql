-- A copy of each group email as it went out (added 2026-11-18 at the owner's request: "create an exact copy of
-- the email sent (to, bcc, subject, contents: html if possible plain text otherwise) and add a link at the end of
-- each sent email in the list to view the copy"). One row per group_messages row that emailed anyone: the
-- headers (From, To, Reply-To, Subject), the hidden recipients (bcc: every address it was emailed to, each as its
-- own copy), whether the leader got their copy, and the body as plain text and HTML (NULL when it had none).
--
-- **This records recipients on purpose** (group_messages never did): the owner asked for the Bcc. Each member's
-- copy differs only in their stop links, so the copy kept is a member's with the code in those links replaced by
-- groups.STOP_CODE_PLACEHOLDER (it stops nothing). A picture (verse cards, picture messages) is kept inside the
-- HTML as a data: address in place of its cid: one, as the cards themselves are deleted after a week.
--
-- Older messages have no row (no copy was kept). Deleting the message or the group deletes it. Not in schema.sql,
-- like the rest of the groups tables; make-public-data.sh leaves its rows out (personal data). Safe to run more
-- than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/053_add_group_message_copies.sql

CREATE TABLE IF NOT EXISTS group_message_copies (
  message_id INTEGER PRIMARY KEY REFERENCES group_messages (id) ON DELETE CASCADE,
  from_address TEXT NOT NULL DEFAULT '',
  to_address TEXT NOT NULL DEFAULT '',
  reply_to TEXT NOT NULL DEFAULT '',
  bcc TEXT[] NOT NULL DEFAULT '{}',
  leader_copy BOOLEAN NOT NULL DEFAULT false,
  subject TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL DEFAULT '',
  html TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- "Add my own message" on Make your own card (added 2026-11-28 at the owner's request): a member's own words,
-- written in the rich text editor, take the place of the verse's words on the card. A saved card keeps the message
-- as cleaned HTML (custom_cards.clean_message), so Edit on My cards opens it in the editor again; words holds its
-- plain text, as drawn on the card. NULL: the verse's own words.
--
-- A member keeps one card for each verse, background and message (it was one for each verse and background), so a
-- card with a message does not replace the same verse's card without one, or one with another message.
--
-- Safe to run more than once. Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/078_add_card_messages.sql

ALTER TABLE saved_cards ADD COLUMN IF NOT EXISTS message_html TEXT;

-- The old rule (071's UNIQUE on user, verse and background), whatever name Postgres gave it.
DO $$
DECLARE
  old_rule TEXT;
BEGIN
  FOR old_rule IN
    SELECT conname FROM pg_constraint WHERE conrelid = 'saved_cards'::regclass AND contype = 'u'
  LOOP
    EXECUTE format('ALTER TABLE saved_cards DROP CONSTRAINT %I', old_rule);
  END LOOP;
END
$$;

-- md5: a message can be long, and an index entry has a size limit.
CREATE UNIQUE INDEX IF NOT EXISTS saved_cards_one_of_each
  ON saved_cards (user_id, translation, book, chapter, verse, background_id, md5(coalesce(message_html, '')));

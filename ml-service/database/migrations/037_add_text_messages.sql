-- Text messages (SMS) through Telnyx (added 2026-11-15 at the owner's request; sms.py).
--
-- users.phone_is_cell: the member said their phone number is a cell (mobile) number.
-- users.sms_number: that number in international form (+15551234567), set only while phone_is_cell; the STOP
--   webhook finds the member by it.
-- users.sms_opt_in: the member ticked "Send me text messages": the devotional, prayer list and reply notices they
--   get by email are then also texted to sms_number.
-- users.sms_consent_at: when they last ticked it (kept as the record of their consent).
-- users.sms_stopped_at: when they replied STOP (texts then stop; sms_opt_in is turned off). START turns them
--   back on, if they had consented before.
--
-- US and Canadian phone numbers are written +1 (555) 123-4567 from now on (the owner's request; sms.format_phone);
-- the ones already stored are rewritten that way below. Others are left as typed.
--
-- Like the other account columns they are not in schema.sql. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/037_add_text_messages.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_is_cell BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sms_number TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sms_opt_in BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sms_consent_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sms_stopped_at TIMESTAMPTZ;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_sms_check') THEN
    ALTER TABLE users ADD CONSTRAINT users_sms_check CHECK (
      (sms_number IS NULL OR phone_is_cell) AND (NOT sms_opt_in OR sms_number IS NOT NULL)
    );
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS users_sms_number_index ON users (sms_number) WHERE sms_number IS NOT NULL;

UPDATE users SET phone = '+1 (' || substr(found.digits, 1, 3) || ') ' || substr(found.digits, 4, 3) || '-' || substr(found.digits, 7, 4)
FROM (
  SELECT id, right(regexp_replace(phone, '\D', '', 'g'), 10) AS digits, regexp_replace(phone, '\D', '', 'g') AS all_digits
  FROM users WHERE phone IS NOT NULL
) AS found
WHERE users.id = found.id
  AND (length(found.all_digits) = 10 OR (length(found.all_digits) = 11 AND left(found.all_digits, 1) = '1'))
  AND (users.phone !~ '^\s*\+' OR users.phone ~ '^\s*\+1')
  AND substr(found.digits, 1, 1) ~ '[2-9]' AND substr(found.digits, 4, 1) ~ '[2-9]'
  AND users.phone <> '+1 (' || substr(found.digits, 1, 3) || ') ' || substr(found.digits, 4, 3) || '-' || substr(found.digits, 7, 4);

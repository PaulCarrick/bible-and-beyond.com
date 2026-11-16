-- How each member's messages reach them: by email, by text (SMS) or both (added 2026-11-16 at the owner's request;
-- the "Send via Email" and "Send via SMS" checkboxes on the sign-up form and the My account page).
--
-- users.send_via_email: the devotional, verse a day, weekly prayer list and reply notices go by email.
-- users.send_via_sms: they go by text to sms_number. Ticking it is also the member's consent to texts
--   (sms_opt_in and sms_consent_at, migration 037); a STOP reply turns sms_opt_in off but leaves this choice, so
--   START brings the texts back, and meanwhile the notices go by email (sms.delivery_for_user).
-- At least one is on, and texts need a number. The account emails (confirm the address, reset the password)
-- always go by email whatever is chosen.
--
-- Existing members: email on for everyone (as before); SMS on only for those who already get texts
-- (sms_opt_in), so nobody's messages change. This is done once, when the columns are first added.
--
-- Like the other account columns they are not in schema.sql. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/041_add_delivery_choice.sql

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'send_via_sms'
  ) THEN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS send_via_email BOOLEAN NOT NULL DEFAULT true;
    ALTER TABLE users ADD COLUMN send_via_sms BOOLEAN NOT NULL DEFAULT false;
    UPDATE users SET send_via_sms = true WHERE sms_opt_in AND sms_number IS NOT NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_send_via_check') THEN
    ALTER TABLE users ADD CONSTRAINT users_send_via_check CHECK (
      (send_via_email OR send_via_sms) AND (NOT send_via_sms OR sms_number IS NOT NULL)
    );
  END IF;
END
$$;

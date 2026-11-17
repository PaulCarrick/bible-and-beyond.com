-- Logging in by phone number (added 2026-11-17 at the owner's request: "an alternate login by phone number. If the
-- site user doesn't have an email set then disable anything that sends emails but permit the others ... require
-- either an email or phone number"). accounts.py.
--
-- users.email may be empty (NULL) now: such an account was set up with a phone number instead, kept in login_phone
-- (+15551234567, the texting form; one account per number) and used to log in. phone_verified_at is set when the
-- member types the code texted to it (account_tokens purpose 'phone'; attempts counts wrong codes) or follows a
-- texted reset link. Every account has an email address or a login phone (users_email_or_phone). An account with
-- no email address is never sent email (send_via_email is false), so the "email or text" rule allows neither.
--
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/051_add_phone_login.sql

ALTER TABLE users ALTER COLUMN email DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS login_phone TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS users_login_phone ON users (login_phone) WHERE login_phone IS NOT NULL;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_or_phone;
ALTER TABLE users ADD CONSTRAINT users_email_or_phone CHECK (email IS NOT NULL OR login_phone IS NOT NULL);

-- Was: (send_via_email OR send_via_sms) AND (NOT send_via_sms OR sms_number IS NOT NULL).
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_send_via_check;
ALTER TABLE users ADD CONSTRAINT users_send_via_check CHECK (
  (send_via_email OR send_via_sms OR email IS NULL)
  AND (NOT send_via_sms OR sms_number IS NOT NULL)
  AND (email IS NOT NULL OR NOT send_via_email)
);

ALTER TABLE account_tokens ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE account_tokens DROP CONSTRAINT IF EXISTS account_tokens_purpose_check;
ALTER TABLE account_tokens ADD CONSTRAINT account_tokens_purpose_check CHECK (purpose IN ('verify', 'reset', 'phone'));

"""Accounts for visitors of the main site (separate from Drupal's users).

An account is an email address and a password, or (since 2026-11-17, the owner's request) a cell phone number and
a password: users.login_phone, confirmed by a texted code (phone_verified_at). An account with no email address is
never emailed; the email features (devotional emails, the prayer list, reply emails) are off for it, the others
(notes, lists, the Prayer Wall, texts it asks for) work. Passwords are kept only as a salted scrypt hash. A
logged-in browser holds a random token in an HttpOnly cookie; the database keeps only the SHA-256 of
that token, so a copy of the database cannot be used to log in.
"""

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import psycopg

from contact import CONTROL_CHARACTERS, EMAIL_LIMIT, EMAIL_PATTERN, MailUnavailable, send_plain_message
import sms
from sms import SmsProblem, check_choices, format_phone, texting_number
from head_shots import address as head_shot_address
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger("accounts")

# Kept short on purpose: the owner does not want the site to be fussy about passwords.
PASSWORD_MINIMUM = 8
PASSWORD_MAXIMUM = 128
NAME_LIMIT = 100
PHONE_LIMIT = 40
SESSION_DAYS = 30
VERIFY_LINK_HOURS = 72
RESET_LINK_MINUTES = 60
# The code texted to confirm a phone number: six digits, good for this long, and no more than this many wrong tries.
PHONE_CODE_MINUTES = 15
PHONE_CODE_ATTEMPTS = 5
# A new link is not sent to the same account more often than this, however often it is asked for.
LINK_PAUSE_SECONDS = 60

SCRYPT_COST = 2**15
SCRYPT_BLOCK_SIZE = 8
SCRYPT_PARALLELISM = 1
SCRYPT_MEMORY = 64 * 1024 * 1024


class AccountProblem(Exception):
  """The request cannot be done; the text says why and is fit to show the visitor."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


def hash_password(password: str) -> str:
  salt = secrets.token_bytes(16)
  digest = hashlib.scrypt(
    password.encode("utf-8"),
    salt=salt,
    n=SCRYPT_COST,
    r=SCRYPT_BLOCK_SIZE,
    p=SCRYPT_PARALLELISM,
    maxmem=SCRYPT_MEMORY,
  )
  return f"scrypt${SCRYPT_COST}${SCRYPT_BLOCK_SIZE}${SCRYPT_PARALLELISM}${salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
  try:
    _, cost, block_size, parallelism, salt, expected = stored.split("$")
    digest = hashlib.scrypt(
      password.encode("utf-8"),
      salt=bytes.fromhex(salt),
      n=int(cost),
      r=int(block_size),
      p=int(parallelism),
      maxmem=SCRYPT_MEMORY,
    )
    return hmac.compare_digest(digest, bytes.fromhex(expected))
  except (ValueError, TypeError):
    return False


# Checked when no account has the address, so that finding out whether an address has an account is
# not made easy by how long the answer takes.
_DUMMY_HASH = hash_password("a password that no account has")


def normalize_email(email: str) -> str:
  email = email.strip().lower()
  if not email or len(email) > EMAIL_LIMIT or not EMAIL_PATTERN.match(email):
    raise AccountProblem("Please enter a valid email address.")
  return email


def check_new_password(password: str, confirmation: str) -> None:
  if len(password) < PASSWORD_MINIMUM:
    raise AccountProblem(f"The password must be at least {PASSWORD_MINIMUM} characters.")
  if len(password) > PASSWORD_MAXIMUM:
    raise AccountProblem(f"The password can be at most {PASSWORD_MAXIMUM} characters.")
  if password != confirmation:
    raise AccountProblem("The two passwords are not the same.")


def check_profile(first_name: str, last_name: str, phone: str) -> tuple[str, str, str]:
  """Trims and checks the name and phone of an account. Each is optional (only the email and the password
  are needed to sign up) and, when given, one line of plain text."""
  first_name, last_name, phone = first_name.strip(), last_name.strip(), phone.strip()
  for label, value in (("first name", first_name), ("last name", last_name), ("phone number", phone)):
    if any(character in value for character in "\n\r\t") or CONTROL_CHARACTERS.search(value):
      raise AccountProblem(f"The {label} must be on one line.")
  for label, value in (("first name", first_name), ("last name", last_name)):
    if len(value) > NAME_LIMIT:
      raise AccountProblem(f"The {label} can be at most {NAME_LIMIT} characters.")
  if len(phone) > PHONE_LIMIT:
    raise AccountProblem(f"The phone number can be at most {PHONE_LIMIT} characters.")
  # A US number is kept as +1 (555) 123-4567.
  return first_name, last_name, format_phone(phone)


# What the site is told about a logged-in account. The columns are read in this order.
_USER_COLUMNS = """
  users.id, users.email, users.email_verified_at IS NOT NULL, users.open_ai_queries,
  COALESCE(users.first_name, ''), COALESCE(users.last_name, ''), COALESCE(users.phone, ''), users.use_conversations,
  users.phone_is_cell, users.sms_opt_in, users.sms_stopped_at IS NOT NULL, users.use_maps,
  users.send_via_email, users.send_via_sms, users.send_multimedia, users.phone_verified_at IS NOT NULL,
  users.login_phone IS NOT NULL, users.share_lists, users.head_shot_version,
  EXISTS (SELECT 1 FROM group_members gm WHERE gm.user_id = users.id)
"""


def _describe_user(row) -> dict:
  # open_ai_queries: an administrator allowed this account to ask the AI its own questions (FAQ page).
  # use_conversations: an administrator allowed this account to read and write Conversations (conversations.py).
  # The names and phone are "" when the account has none (accounts set up before they were asked for).
  return {
    "id": row[0],
    "email": row[1],
    "email_verified": row[2],
    "open_ai_queries": row[3],
    "first_name": row[4],
    "last_name": row[5],
    "phone": row[6],
    "use_conversations": row[7],
    # Text messages (sms.py): the phone is a cell number; the member asked for texts; they replied STOP since.
    "phone_is_cell": row[8],
    "sms_opt_in": row[9],
    "sms_stopped": row[10],
    # use_maps: an administrator allowed this account its own notes, pins and routes on the maps (map_marks.py).
    "use_maps": row[11],
    # How the member's notices reach them (sms.deliver): by email, by text or both (at least one is on).
    "send_via_email": row[12],
    "send_via_sms": row[13],
    # Send Multimedia Messages: the verse a day and the devotionals come as a picture (message_cards.py).
    "send_multimedia": row[14],
    # An account set up with a phone number (no email, or as well): it logs in with it, once confirmed by a code.
    "phone_verified": row[15],
    "logs_in_with_phone": row[16],
    # share_lists: an administrator allowed this account to share its lists on Public lists (saved_lists.py).
    "share_lists": row[17],
    # The member's own picture (head_shots.py; 2026-11-23): its address on this service, or None.
    "head_shot": head_shot_address(row[18]),
    # The account is a member of at least one group (groups.py; the owner's rule, 2026-11-27): only then does the
    # menu offer My scheduled tasks (scheduled_tasks.member_tasks).
    "in_a_group": row[19],
  }


def _sms_choices(phone: str, phone_is_cell: bool, sms_opt_in: bool) -> tuple[bool, str | None, bool]:
  try:
    return check_choices(phone, phone_is_cell, sms_opt_in)
  except SmsProblem as problem:
    raise AccountProblem(str(problem)) from problem


def _delivery_choices(
  phone: str, phone_is_cell: bool, send_via_email: bool, send_via_sms: bool, has_email: bool = True
) -> tuple[bool, str | None, bool, bool]:
  """(phone_is_cell, sms_number, send_via_email, send_via_sms) to save for the phone number and the checkboxes
  "This is a cell number", "Send via Email" and "Send via SMS". Send via SMS needs a US or Canadian cell number
  (refused otherwise); its tick is also the consent to texts (sms_opt_in). With texts off, email is always on, so
  a member is never left with no way to be reached."""
  phone_is_cell, sms_number, send_via_sms = _sms_choices(phone, phone_is_cell, send_via_sms)
  if not has_email:
    # No address: never by email (the member may still choose texts).
    return phone_is_cell, sms_number, False, send_via_sms
  return phone_is_cell, sms_number, bool(send_via_email or not send_via_sms), send_via_sms


def login_number(phone: str) -> str:
  """The number a phone-only account logs in with (+15551234567), or AccountProblem when it is not a US or Canadian
  number (the code that confirms it is texted)."""
  number = texting_number(phone)
  if number is None:
    raise AccountProblem("Please enter an email address, or a US or Canadian cell phone number with its area code.")
  return number


def create_account(
  email: str,
  password: str,
  confirmation: str,
  first_name: str = "",
  last_name: str = "",
  phone: str = "",
  phone_is_cell: bool = False,
  send_via_sms: bool = False,
  send_via_email: bool = True,
  send_multimedia: bool = False,
) -> dict:
  """Makes an account with an email address, or with only a cell phone number (no email: the number is its login
  and must be confirmed by a texted code, start_phone_code)."""
  email = normalize_email(email) if (email or "").strip() else None
  first_name, last_name, phone = check_profile(first_name, last_name, phone)
  login_phone = None
  if email is None:
    login_phone = login_number(phone)
    phone_is_cell = True
  phone_is_cell, sms_number, send_via_email, send_via_sms = _delivery_choices(
    phone, phone_is_cell, send_via_email, send_via_sms, has_email=email is not None
  )
  check_new_password(password, confirmation)
  password_hash = hash_password(password)
  try:
    with connect() as connection:
      row = connection.execute(
        f"""
        INSERT INTO users
          (email, password_hash, first_name, last_name, phone, phone_is_cell, sms_number, sms_opt_in, sms_consent_at,
           send_via_email, send_via_sms, send_multimedia, login_phone)
        VALUES (%s, %s, NULLIF(%s, ''), NULLIF(%s, ''), NULLIF(%s, ''), %s, %s, %s, CASE WHEN %s THEN now() END, %s, %s, %s, %s)
        RETURNING {_USER_COLUMNS}
        """,
        (
          email, password_hash, first_name, last_name, phone, phone_is_cell, sms_number, send_via_sms, send_via_sms,
          send_via_email, send_via_sms, bool(send_multimedia), login_phone,
        ),
      ).fetchone()
  except psycopg.errors.UniqueViolation:
    what = "email address" if email else "phone number"
    raise AccountProblem(f"An account with that {what} already exists. Please log in.", 409)
  return _describe_user(row)


def update_phone(
  user_id: int, phone: str, phone_is_cell: bool, send_via_sms: bool, send_via_email: bool = True,
  send_multimedia: bool | None = None,
) -> tuple[dict, str | None]:
  """Changes a member's phone number and how their notices reach them (the My account page). Returns the account
  and, when texts were just turned on (or moved to a new number), the number to send the welcome text to."""
  _, _, phone = check_profile("", "", phone)
  with connect() as connection:
    account = connection.execute("SELECT email, login_phone FROM users WHERE id = %s", (user_id,)).fetchone()
  has_email = account is None or account[0] is not None
  login_phone = None
  if account is not None and account[1] is not None:
    # Logs in with its phone: it stays a cell number; a new one is the new login, confirmed again by a code.
    login_phone = login_number(phone)
    phone_is_cell = True
  phone_is_cell, sms_number, send_via_email, sms_opt_in = _delivery_choices(
    phone, phone_is_cell, send_via_email, send_via_sms, has_email=has_email
  )
  try:
    return _update_phone(user_id, phone, phone_is_cell, sms_number, send_via_email, sms_opt_in, send_multimedia, login_phone)
  except psycopg.errors.UniqueViolation:
    raise AccountProblem("Another account already logs in with that phone number.", 409)


def _update_phone(user_id, phone, phone_is_cell, sms_number, send_via_email, sms_opt_in, send_multimedia, login_phone):
  with connect() as connection:
    before = connection.execute("SELECT sms_opt_in, sms_number FROM users WHERE id = %s", (user_id,)).fetchone()
    row = connection.execute(
      f"""
      UPDATE users SET phone = NULLIF(%(phone)s, ''), phone_is_cell = %(cell)s, sms_number = %(number)s,
        sms_opt_in = %(opt_in)s,
        sms_consent_at = CASE WHEN %(opt_in)s THEN now() ELSE sms_consent_at END,
        sms_stopped_at = CASE WHEN %(opt_in)s THEN NULL ELSE sms_stopped_at END,
        send_via_email = %(by_email)s, send_via_sms = %(opt_in)s,
        send_multimedia = COALESCE(%(multimedia)s, send_multimedia),
        phone_verified_at = CASE WHEN %(login)s::text IS NOT NULL AND login_phone IS DISTINCT FROM %(login)s THEN NULL
                                 ELSE phone_verified_at END,
        login_phone = COALESCE(%(login)s, login_phone)
      WHERE id = %(user)s RETURNING {_USER_COLUMNS}
      """,
      {
        "phone": phone, "cell": phone_is_cell, "number": sms_number, "opt_in": sms_opt_in, "by_email": send_via_email,
        "multimedia": send_multimedia, "user": user_id, "login": login_phone,
      },
    ).fetchone()
  newly_on = sms_opt_in and (before is None or not before[0] or before[1] != sms_number)
  return _describe_user(row), sms_number if newly_on else None


def _hash_token(token: str) -> str:
  return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _login_column(identifier: str) -> tuple[str, str] | None:
  """("email", address) or ("login_phone", +15551234567) for what was typed in the login box, or None."""
  identifier = (identifier or "").strip()
  if "@" in identifier:
    return "email", identifier.lower()
  number = texting_number(identifier)
  return ("login_phone", number) if number else None


def log_in(email: str, password: str) -> tuple[dict, str]:
  """Returns the user and a new session token, or raises AccountProblem (the same message whatever was wrong).
  email is what was typed in the login box: an email address, or the phone number of an account that logs in
  with it."""
  refusal = AccountProblem("The email address or phone number, or the password, is not right.", 401)
  found = _login_column(email)
  if found is None or not password or len(password) > PASSWORD_MAXIMUM:
    password_matches((password or "x")[:PASSWORD_MAXIMUM], _DUMMY_HASH)
    raise refusal
  column, value = found
  with connect() as connection:
    row = connection.execute(
      f"SELECT users.password_hash, users.disabled_at IS NOT NULL, {_USER_COLUMNS} FROM users WHERE {column} = %s",
      (value,),
    ).fetchone()
    if row is None:
      password_matches(password, _DUMMY_HASH)
      raise refusal
    if not password_matches(password, row[0]):
      raise refusal
    if row[1]:
      # Closed by its owner (close_account): said only to someone who has its password.
      raise AccountProblem("This account was closed. To reopen it, please ask us through the Contact page.", 403)
    user = _describe_user(row[2:])
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    connection.execute("DELETE FROM user_sessions WHERE expires_at < now()")
    connection.execute(
      "INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
      (_hash_token(token), user["id"], expires_at),
    )
    connection.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user["id"],))
  return user, token


def user_for_token(token: str | None) -> dict | None:
  if not token:
    return None
  with connect() as connection:
    row = connection.execute(
      f"""
      SELECT {_USER_COLUMNS}
      FROM user_sessions JOIN users ON users.id = user_sessions.user_id
      WHERE user_sessions.token_hash = %s AND user_sessions.expires_at > now() AND users.disabled_at IS NULL
      """,
      (_hash_token(token),),
    ).fetchone()
  return _describe_user(row) if row else None


def log_out(token: str | None) -> None:
  if token:
    with connect() as connection:
      connection.execute("DELETE FROM user_sessions WHERE token_hash = %s", (_hash_token(token),))


def _issue_token(connection, user_id: int, purpose: str, lifetime: timedelta) -> str | None:
  """A new emailed link for the account, replacing any earlier one; None if one was made a moment ago."""
  recent = connection.execute(
    """
    SELECT 1 FROM account_tokens
    WHERE user_id = %s AND purpose = %s AND created_at > now() - make_interval(secs => %s)
    """,
    (user_id, purpose, LINK_PAUSE_SECONDS),
  ).fetchone()
  if recent:
    return None
  connection.execute("DELETE FROM account_tokens WHERE user_id = %s AND purpose = %s", (user_id, purpose))
  token = secrets.token_urlsafe(32)
  connection.execute(
    "INSERT INTO account_tokens (token_hash, user_id, purpose, expires_at) VALUES (%s, %s, %s, %s)",
    (_hash_token(token), user_id, purpose, datetime.now(timezone.utc) + lifetime),
  )
  return token


def _use_token(connection, token: str, purpose: str) -> int:
  """The account a link belongs to; the link is used up. Raises AccountProblem if it is not good."""
  row = connection.execute(
    "DELETE FROM account_tokens WHERE token_hash = %s AND purpose = %s AND expires_at > now() RETURNING user_id",
    (_hash_token(token or ""), purpose),
  ).fetchone()
  if row is None:
    raise AccountProblem("This link has expired or has already been used.", 400)
  return row[0]


def start_verification(user_id: int) -> tuple[str, str] | None:
  """(email, token) for a verification email, or None when there is nothing to send."""
  with connect() as connection:
    row = connection.execute("SELECT email, email_verified_at IS NOT NULL FROM users WHERE id = %s", (user_id,)).fetchone()
    if row is None or row[0] is None or row[1]:
      return None
    token = _issue_token(connection, user_id, "verify", timedelta(hours=VERIFY_LINK_HOURS))
  return (row[0], token) if token else None


def verify_email(token: str) -> None:
  with connect() as connection:
    user_id = _use_token(connection, token, "verify")
    connection.execute("UPDATE users SET email_verified_at = COALESCE(email_verified_at, now()) WHERE id = %s", (user_id,))


def start_password_reset(email: str) -> tuple[str, str, str] | None:
  """("email", address, token) for a reset email, ("phone", number, token) for a reset text (an account that logs
  in with its phone), or None (no such account, or one was sent a moment ago). The caller must answer the visitor
  the same way either way."""
  if len((email or "").strip()) > EMAIL_LIMIT:
    return None
  found = _login_column(email)
  if found is None:
    return None
  column, value = found
  with connect() as connection:
    row = connection.execute(f"SELECT id FROM users WHERE {column} = %s AND disabled_at IS NULL", (value,)).fetchone()
    if row is None:
      return None
    token = _issue_token(connection, row[0], "reset", timedelta(minutes=RESET_LINK_MINUTES))
  if not token:
    return None
  return ("email" if column == "email" else "phone", value, token)


def reset_password(token: str, password: str, confirmation: str) -> None:
  """Sets a new password. Everyone logged in to the account is logged out. Following the emailed link also
  proves the address, so it counts as verified; for an account with no address the link was texted, so it proves
  the phone instead."""
  check_new_password(password, confirmation)
  password_hash = hash_password(password)
  with connect() as connection:
    user_id = _use_token(connection, token, "reset")
    connection.execute(
      """
      UPDATE users SET password_hash = %s,
        email_verified_at = CASE WHEN email IS NOT NULL THEN COALESCE(email_verified_at, now()) END,
        phone_verified_at = CASE WHEN email IS NULL THEN COALESCE(phone_verified_at, now()) ELSE phone_verified_at END
      WHERE id = %s
      """,
      (password_hash, user_id),
    )
    connection.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
    connection.execute("DELETE FROM account_tokens WHERE user_id = %s", (user_id,))


def change_password(user_id: int, session_token: str | None, current: str, password: str, confirmation: str) -> None:
  """A logged-in member chooses a new password (the My account page). The current password must be right
  (the same scrypt check as logging in, so a wrong one takes about as long). Every other session of the
  account is logged out and any emailed reset link is cancelled; the session making the change stays."""
  refusal = AccountProblem("Your current password is not right.", 422)
  if not current or len(current) > PASSWORD_MAXIMUM:
    password_matches(current[:PASSWORD_MAXIMUM], _DUMMY_HASH)
    raise refusal
  with connect() as connection:
    row = connection.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,)).fetchone()
    if row is None:
      password_matches(current, _DUMMY_HASH)
      raise AccountProblem("Please log in again.", 401)
    if not password_matches(current, row[0]):
      raise refusal
  check_new_password(password, confirmation)
  password_hash = hash_password(password)
  with connect() as connection:
    connection.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
    connection.execute(
      "DELETE FROM user_sessions WHERE user_id = %s AND token_hash <> %s",
      (user_id, _hash_token(session_token or "")),
    )
    connection.execute("DELETE FROM account_tokens WHERE user_id = %s AND purpose = 'reset'", (user_id,))


def close_account(user_id: int, password: str) -> str:
  """A logged-in member closes their own account (the My account page; added 2026-11-17 at the owner's request,
  first as a delete, then: "let's not actually delete the account just add a disable flag and don't permit any
  account related actions (including sending emails) and login"). Their password must be right (the same check as
  changing it, so a wrong one takes about as long). Sets users.disabled_at, logs out every device and cancels any
  emailed link. Nothing is deleted. One short email says it was closed (send_goodbye_email, the owner's wish) and
  after that nothing more: from now on the account cannot log in (log_in,
  user_for_token, start_password_reset) and no email or text goes to it (contact.send_email, sms.send_text and the
  sending loops). An administrator can reopen or delete it on Site users."""
  refusal = AccountProblem("Your password is not right.", 422)
  if not password or len(password) > PASSWORD_MAXIMUM:
    password_matches((password or "")[:PASSWORD_MAXIMUM], _DUMMY_HASH)
    raise refusal
  with connect() as connection:
    row = connection.execute("SELECT password_hash, email FROM users WHERE id = %s AND disabled_at IS NULL", (user_id,)).fetchone()
    if row is None:
      password_matches(password, _DUMMY_HASH)
      raise AccountProblem("Please log in again.", 401)
    if not password_matches(password, row[0]):
      raise refusal
    connection.execute("UPDATE users SET disabled_at = now() WHERE id = %s", (user_id,))
    connection.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
    connection.execute("DELETE FROM account_tokens WHERE user_id = %s", (user_id,))
  logger.info("Account %s closed by its owner.", user_id)
  return row[1]


def send_goodbye_email(address: str) -> None:
  """The one email a closed account gets: that it was closed (so they know, if it was not them). Sent past the
  closed-account guard (even_if_closed); nothing is sent to it after this."""
  title = get_public_settings()["title"]
  contact_page = site_link("").rstrip("?").rstrip("/") + "/contact"
  try:
    send_plain_message(
      address,
      f"Your {title} account was closed",
      f"The {title} account for this address was closed from its My account page. It can no longer log in, and "
      f"this is the last email you will get from the site: no more emails or texts will be sent to you.\n\n"
      f"If you did not do this, or you would like it reopened or deleted with everything stored with it, please "
      f"tell us through the Contact page: {contact_page}\n",
      even_if_closed=True,
    )
  except MailUnavailable as problem:
    logger.error("Account email not sent: %s", problem)


def site_link(query: str) -> str:
  """An address on the main site. SITE_URL says where it is (https://freestudy.bible when not set)."""
  return os.environ.get("SITE_URL", "https://freestudy.bible").rstrip("/") + "/?" + query


def send_account_email(address: str, subject: str, text: str) -> None:
  """Sends one of the account emails; a failure is logged (with no link in the log) and goes no further."""
  try:
    send_plain_message(address, subject, text)
  except MailUnavailable as problem:
    logger.error("Account email not sent: %s", problem)


def send_verification_email(address: str, token: str) -> None:
  title = get_public_settings()["title"]
  send_account_email(
    address,
    f"Confirm your email address for {title}",
    f"Please confirm that this is your email address by opening this link:\n\n"
    f"{site_link('verify=' + token)}\n\n"
    f"The link works once and for {VERIFY_LINK_HOURS} hours. If you did not set up an account on {title}, "
    f"you can ignore this email.\n",
  )


def send_reset_email(address: str, token: str) -> None:
  title = get_public_settings()["title"]
  send_account_email(
    address,
    f"Reset your password for {title}",
    f"Someone asked to reset the password of the {title} account for this address. To choose a new password, "
    f"open this link:\n\n{site_link('reset=' + token)}\n\n"
    f"The link works once and for {RESET_LINK_MINUTES} minutes. If you did not ask for this, ignore this "
    f"email: your password has not been changed.\n",
  )


# --- phone numbers (accounts that log in with one) -------------------------------------------------------------


def start_phone_code(user_id: int) -> tuple[str, str] | None:
  """(number, code) to text to an account that logs in with its phone and has not confirmed it, or None (nothing to
  confirm, or a code was sent a moment ago). A new code replaces the last one."""
  with connect() as connection:
    row = connection.execute(
      "SELECT login_phone FROM users WHERE id = %s AND login_phone IS NOT NULL AND phone_verified_at IS NULL AND disabled_at IS NULL",
      (user_id,),
    ).fetchone()
    if row is None:
      return None
    recent = connection.execute(
      """
      SELECT 1 FROM account_tokens
      WHERE user_id = %s AND purpose = 'phone' AND created_at > now() - make_interval(secs => %s)
      """,
      (user_id, LINK_PAUSE_SECONDS),
    ).fetchone()
    if recent:
      return None
    code = f"{secrets.randbelow(10**6):06d}"
    connection.execute("DELETE FROM account_tokens WHERE user_id = %s AND purpose = 'phone'", (user_id,))
    connection.execute(
      "INSERT INTO account_tokens (token_hash, user_id, purpose, expires_at) VALUES (%s, %s, 'phone', %s)",
      (_hash_token(f"{user_id}:{code}"), user_id, datetime.now(timezone.utc) + timedelta(minutes=PHONE_CODE_MINUTES)),
    )
  return row[0], code


def confirm_phone(user_id: int, code: str) -> dict:
  """The member types the code texted to their phone. Right: the phone is confirmed (texts can go to it). Wrong:
  counted; after PHONE_CODE_ATTEMPTS the code no longer works and a new one is needed. Returns the account."""
  code = "".join(character for character in (code or "") if character.isdigit())
  # The refusals are raised after the database work is done: raising inside "with connect()" would undo the count.
  refusal = None
  with connect() as connection:
    row = connection.execute(
      "SELECT token_hash, attempts FROM account_tokens WHERE user_id = %s AND purpose = 'phone' AND expires_at > now()",
      (user_id,),
    ).fetchone()
    if row is None:
      refusal = AccountProblem("That code has expired. Use “Text me a new code”.", 400)
    elif not hmac.compare_digest(row[0], _hash_token(f"{user_id}:{code}")):
      if row[1] + 1 >= PHONE_CODE_ATTEMPTS:
        connection.execute("DELETE FROM account_tokens WHERE user_id = %s AND purpose = 'phone'", (user_id,))
        refusal = AccountProblem("That code is not right, and it has been tried too many times. Use “Text me a new code”.", 400)
      else:
        connection.execute("UPDATE account_tokens SET attempts = attempts + 1 WHERE user_id = %s AND purpose = 'phone'", (user_id,))
        refusal = AccountProblem("That code is not right. Please check it and try again.", 400)
  if refusal is not None:
    raise refusal
  with connect() as connection:
    connection.execute("DELETE FROM account_tokens WHERE user_id = %s AND purpose = 'phone'", (user_id,))
    found = connection.execute(
      f"UPDATE users SET phone_verified_at = COALESCE(phone_verified_at, now()) WHERE id = %s RETURNING {_USER_COLUMNS}",
      (user_id,),
    ).fetchone()
  return _describe_user(found)


def send_phone_code(number: str, code: str) -> None:
  """Texts the code that confirms a phone number (asked for by its owner, so it goes without the texts consent)."""
  title = get_public_settings()["title"]
  if not sms.send_text(number, f"{title}: your code is {code}. It works for {PHONE_CODE_MINUTES} minutes. If you did not ask for it, ignore this text."):
    logger.error("Phone code not texted.")


def send_reset_text(number: str, token: str) -> None:
  """Texts a reset link to an account that logs in with its phone."""
  title = get_public_settings()["title"]
  text = (
    f"{title}: to choose a new password, open {site_link('reset=' + token)} (it works once, for {RESET_LINK_MINUTES} "
    "minutes). If you did not ask for this, ignore this text."
  )
  if not sms.send_text(number, text):
    logger.error("Reset link not texted.")

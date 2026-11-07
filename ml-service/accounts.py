"""Accounts for visitors of the main site (separate from Drupal's users).

An account is an email address and a password. Passwords are kept only as a salted scrypt hash. A
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

from contact import EMAIL_LIMIT, EMAIL_PATTERN, MailUnavailable, send_plain_message
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger("accounts")

PASSWORD_MINIMUM = 10
PASSWORD_MAXIMUM = 128
SESSION_DAYS = 30
VERIFY_LINK_HOURS = 72
RESET_LINK_MINUTES = 60
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


def create_account(email: str, password: str, confirmation: str) -> dict:
  email = normalize_email(email)
  check_new_password(password, confirmation)
  password_hash = hash_password(password)
  try:
    with connect() as connection:
      row = connection.execute(
        "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id, email",
        (email, password_hash),
      ).fetchone()
  except psycopg.errors.UniqueViolation:
    raise AccountProblem("An account with that email address already exists. Please log in.", 409)
  return {"id": row[0], "email": row[1], "email_verified": False, "open_ai_queries": False}


def _hash_token(token: str) -> str:
  return hashlib.sha256(token.encode("utf-8")).hexdigest()


def log_in(email: str, password: str) -> tuple[dict, str]:
  """Returns the user and a new session token, or raises AccountProblem (the same message whatever was wrong)."""
  refusal = AccountProblem("The email address or the password is not right.", 401)
  email = email.strip().lower()
  if not email or not password or len(password) > PASSWORD_MAXIMUM:
    raise refusal
  with connect() as connection:
    row = connection.execute(
      "SELECT id, email, password_hash, email_verified_at IS NOT NULL, open_ai_queries FROM users WHERE email = %s",
      (email,),
    ).fetchone()
    if row is None:
      password_matches(password, _DUMMY_HASH)
      raise refusal
    if not password_matches(password, row[2]):
      raise refusal
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    connection.execute("DELETE FROM user_sessions WHERE expires_at < now()")
    connection.execute(
      "INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
      (_hash_token(token), row[0], expires_at),
    )
    connection.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (row[0],))
  return {"id": row[0], "email": row[1], "email_verified": row[3], "open_ai_queries": row[4]}, token


def user_for_token(token: str | None) -> dict | None:
  if not token:
    return None
  with connect() as connection:
    row = connection.execute(
      """
      SELECT users.id, users.email, users.email_verified_at IS NOT NULL, users.open_ai_queries
      FROM user_sessions JOIN users ON users.id = user_sessions.user_id
      WHERE user_sessions.token_hash = %s AND user_sessions.expires_at > now()
      """,
      (_hash_token(token),),
    ).fetchone()
  # open_ai_queries: an administrator allowed this account to ask the AI its own questions (FAQ page).
  return {"id": row[0], "email": row[1], "email_verified": row[2], "open_ai_queries": row[3]} if row else None


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
    if row is None or row[1]:
      return None
    token = _issue_token(connection, user_id, "verify", timedelta(hours=VERIFY_LINK_HOURS))
  return (row[0], token) if token else None


def verify_email(token: str) -> None:
  with connect() as connection:
    user_id = _use_token(connection, token, "verify")
    connection.execute("UPDATE users SET email_verified_at = COALESCE(email_verified_at, now()) WHERE id = %s", (user_id,))


def start_password_reset(email: str) -> tuple[str, str] | None:
  """(email, token) for a reset email, or None (no such account, or one was sent a moment ago). The caller
  must answer the visitor the same way either way."""
  email = email.strip().lower()
  if not email or len(email) > EMAIL_LIMIT:
    return None
  with connect() as connection:
    row = connection.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
    if row is None:
      return None
    token = _issue_token(connection, row[0], "reset", timedelta(minutes=RESET_LINK_MINUTES))
  return (email, token) if token else None


def reset_password(token: str, password: str, confirmation: str) -> None:
  """Sets a new password. Everyone logged in to the account is logged out. Following the emailed link also
  proves the address, so it counts as verified."""
  check_new_password(password, confirmation)
  password_hash = hash_password(password)
  with connect() as connection:
    user_id = _use_token(connection, token, "reset")
    connection.execute(
      "UPDATE users SET password_hash = %s, email_verified_at = COALESCE(email_verified_at, now()) WHERE id = %s",
      (password_hash, user_id),
    )
    connection.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
    connection.execute("DELETE FROM account_tokens WHERE user_id = %s", (user_id,))


def site_link(query: str) -> str:
  """An address on the main site. SITE_URL says where it is (https://bible-and-beyond.com when not set)."""
  return os.environ.get("SITE_URL", "https://bible-and-beyond.com").rstrip("/") + "/?" + query


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

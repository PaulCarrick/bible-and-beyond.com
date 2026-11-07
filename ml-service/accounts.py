"""Accounts for visitors of the main site (separate from Drupal's users).

An account is an email address and a password. Passwords are kept only as a salted scrypt hash. A
logged-in browser holds a random token in an HttpOnly cookie; the database keeps only the SHA-256 of
that token, so a copy of the database cannot be used to log in.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import psycopg

from contact import EMAIL_LIMIT, EMAIL_PATTERN
from search import connect

PASSWORD_MINIMUM = 10
PASSWORD_MAXIMUM = 128
SESSION_DAYS = 30

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
  return {"id": row[0], "email": row[1]}


def _hash_token(token: str) -> str:
  return hashlib.sha256(token.encode("utf-8")).hexdigest()


def log_in(email: str, password: str) -> tuple[dict, str]:
  """Returns the user and a new session token, or raises AccountProblem (the same message whatever was wrong)."""
  refusal = AccountProblem("The email address or the password is not right.", 401)
  email = email.strip().lower()
  if not email or not password or len(password) > PASSWORD_MAXIMUM:
    raise refusal
  with connect() as connection:
    row = connection.execute("SELECT id, email, password_hash FROM users WHERE email = %s", (email,)).fetchone()
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
  return {"id": row[0], "email": row[1]}, token


def user_for_token(token: str | None) -> dict | None:
  if not token:
    return None
  with connect() as connection:
    row = connection.execute(
      """
      SELECT users.id, users.email
      FROM user_sessions JOIN users ON users.id = user_sessions.user_id
      WHERE user_sessions.token_hash = %s AND user_sessions.expires_at > now()
      """,
      (_hash_token(token),),
    ).fetchone()
  return {"id": row[0], "email": row[1]} if row else None


def log_out(token: str | None) -> None:
  if token:
    with connect() as connection:
      connection.execute("DELETE FROM user_sessions WHERE token_hash = %s", (_hash_token(token),))

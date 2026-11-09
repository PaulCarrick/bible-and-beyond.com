"""Managing the accounts of the main site's visitors from the Drupal admin ("Site users" page).

These are the accounts in the Bible database (accounts.py), not Drupal's own users. Drupal runs
scripts/manage_users.py, which calls these functions. Passwords are checked by the same rules as sign-up
and kept only as a scrypt hash; they are never returned or logged.
"""

import psycopg

from accounts import AccountProblem, check_new_password, check_profile, hash_password, normalize_email
from search import connect

PER_PAGE = 50
QUERY_LIMIT = 200

_COLUMNS = """
  users.id, users.email, users.created_at, users.last_login_at, users.email_verified_at IS NOT NULL,
  users.open_ai_queries, COALESCE(users.first_name, ''), COALESCE(users.last_name, ''), COALESCE(users.phone, ''),
  (SELECT count(*) FROM notes WHERE notes.user_id = users.id),
  (SELECT count(*) FROM devotional_subscriptions WHERE devotional_subscriptions.user_id = users.id)
"""


class UserProblem(Exception):
  """The change cannot be made; the text says why and is fit to show the administrator."""


def _describe(row) -> dict:
  return {
    "id": row[0],
    "email": row[1],
    "created_at": row[2].isoformat(),
    "last_login_at": row[3].isoformat() if row[3] else None,
    "email_verified": row[4],
    "open_ai_queries": row[5],
    "first_name": row[6],
    "last_name": row[7],
    "phone": row[8],
    "note_count": row[9],
    "subscription_count": row[10],
  }


def _checked_email(email: str) -> str:
  try:
    return normalize_email(email)
  except AccountProblem as problem:
    raise UserProblem(str(problem)) from problem


def _checked_password(password: str) -> None:
  try:
    check_new_password(password, password)
  except AccountProblem as problem:
    raise UserProblem(str(problem)) from problem


def _checked_profile(first_name: str, last_name: str, phone: str) -> tuple[str, str, str]:
  try:
    return check_profile(first_name, last_name, phone)
  except AccountProblem as problem:
    raise UserProblem(str(problem)) from problem


# An account matches a search when its address or its name ("first last") contains the words searched for.
_MATCHES = "(email LIKE %s OR lower(concat_ws(' ', first_name, last_name)) LIKE %s)"


def list_users(query: str = "", page: int = 1) -> dict:
  """The accounts, newest first, PER_PAGE at a time; query keeps those whose address or name contains it."""
  query = query.strip().lower()[:QUERY_LIMIT]
  page = max(page, 1)
  pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
  with connect() as connection:
    total = connection.execute(f"SELECT count(*) FROM users WHERE {_MATCHES}", (pattern, pattern)).fetchone()[0]
    rows = connection.execute(
      f"SELECT {_COLUMNS} FROM users WHERE {_MATCHES} ORDER BY users.created_at DESC, users.id DESC LIMIT %s OFFSET %s",
      (pattern, pattern, PER_PAGE, (page - 1) * PER_PAGE),
    ).fetchall()
  return {"users": [_describe(row) for row in rows], "total": total, "page": page, "per_page": PER_PAGE}


def get_user(user_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {_COLUMNS} FROM users WHERE users.id = %s", (user_id,)).fetchone()
  if row is None:
    raise UserProblem("There is no such account. It may have been deleted.")
  return _describe(row)


def create_user(
  email: str,
  password: str,
  email_verified: bool,
  open_ai_queries: bool,
  first_name: str = "",
  last_name: str = "",
  phone: str = "",
) -> dict:
  email = _checked_email(email)
  first_name, last_name, phone = _checked_profile(first_name, last_name, phone)
  _checked_password(password)
  password_hash = hash_password(password)
  try:
    with connect() as connection:
      user_id = connection.execute(
        """
        INSERT INTO users (email, password_hash, email_verified_at, open_ai_queries, first_name, last_name, phone)
        VALUES (%s, %s, CASE WHEN %s THEN now() END, %s, NULLIF(%s, ''), NULLIF(%s, ''), NULLIF(%s, ''))
        RETURNING id
        """,
        (email, password_hash, email_verified, open_ai_queries, first_name, last_name, phone),
      ).fetchone()[0]
  except psycopg.errors.UniqueViolation as error:
    raise UserProblem("An account with that email address already exists.") from error
  return get_user(user_id)


def update_user(
  user_id: int,
  email: str | None = None,
  password: str | None = None,
  email_verified: bool | None = None,
  open_ai_queries: bool | None = None,
  first_name: str | None = None,
  last_name: str | None = None,
  phone: str | None = None,
) -> dict:
  """Changes what is given and leaves the rest. A new password logs the account out everywhere. An empty
  name or phone ("") clears it."""
  current = get_user(user_id)
  changes = []
  values: list = []
  if email is not None:
    email = _checked_email(email)
    if email != current["email"]:
      changes.append("email = %s")
      values.append(email)
  checked = _checked_profile(first_name or "", last_name or "", phone or "")
  for column, given, value in zip(("first_name", "last_name", "phone"), (first_name, last_name, phone), checked):
    if given is not None and value != current[column]:
      changes.append(f"{column} = NULLIF(%s, '')")
      values.append(value)
  if password:
    _checked_password(password)
    changes.append("password_hash = %s")
    values.append(hash_password(password))
  if email_verified is not None and email_verified != current["email_verified"]:
    changes.append("email_verified_at = CASE WHEN %s THEN now() END")
    values.append(email_verified)
  if open_ai_queries is not None:
    changes.append("open_ai_queries = %s")
    values.append(open_ai_queries)
  if changes:
    try:
      with connect() as connection:
        connection.execute(f"UPDATE users SET {', '.join(changes)} WHERE id = %s", (*values, user_id))
        if password:
          # Whoever was logged in with the old password, and any reset link, no longer works.
          connection.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
          connection.execute("DELETE FROM account_tokens WHERE user_id = %s AND purpose = 'reset'", (user_id,))
    except psycopg.errors.UniqueViolation as error:
      raise UserProblem("Another account already uses that email address.") from error
  return get_user(user_id)


def delete_user(user_id: int) -> dict:
  """Deletes the account with its notes, email subscriptions, sessions and links (ON DELETE CASCADE)."""
  user = get_user(user_id)
  with connect() as connection:
    connection.execute("DELETE FROM users WHERE id = %s", (user_id,))
  return user

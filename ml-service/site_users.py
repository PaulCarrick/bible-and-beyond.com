"""Managing the accounts of the main site's visitors from the Drupal admin ("Site users" page).

These are the accounts in the Bible database (accounts.py), not Drupal's own users. Drupal runs
scripts/manage_users.py, which calls these functions. Passwords are checked by the same rules as sign-up
and kept only as a scrypt hash; they are never returned or logged.
"""

import logging
import secrets

import psycopg

import head_shots
import saved_cards

from accounts import AccountProblem, check_new_password, check_profile, hash_password, normalize_email
from search import connect
from sms import texting_number, welcome_text

logger = logging.getLogger(__name__)

PER_PAGE = 50
QUERY_LIMIT = 200

_COLUMNS = """
  users.id, users.email, users.created_at, users.last_login_at, users.email_verified_at IS NOT NULL,
  users.open_ai_queries, COALESCE(users.first_name, ''), COALESCE(users.last_name, ''), COALESCE(users.phone, ''),
  (SELECT count(*) FROM notes WHERE notes.user_id = users.id),
  (SELECT count(*) FROM devotional_subscriptions WHERE devotional_subscriptions.user_id = users.id),
  users.use_conversations, users.see_private_prayers, users.sms_opt_in, users.sms_stopped_at IS NOT NULL,
  users.use_maps, (SELECT count(*) FROM map_marks WHERE map_marks.user_id = users.id), users.disabled_at,
  users.phone_verified_at IS NOT NULL, users.login_phone, users.share_lists,
  (SELECT count(*) FROM saved_lists WHERE saved_lists.user_id = users.id AND saved_lists.shared_at IS NOT NULL),
  users.get_conversation_posts, users.drupal_uid
"""


class UserProblem(Exception):
  """The change cannot be made; the text says why and is fit to show the administrator."""


def _describe(row) -> dict:
  return {
    "id": row[0],
    # "" for an account set up with a phone number only (it logs in with login_phone; 2026-11-17).
    "email": row[1] or "",
    "created_at": row[2].isoformat(),
    "last_login_at": row[3].isoformat() if row[3] else None,
    "email_verified": row[4],
    "open_ai_queries": row[5],
    "first_name": row[6],
    "last_name": row[7],
    "phone": row[8],
    "note_count": row[9],
    "subscription_count": row[10],
    "use_conversations": row[11],
    # The site's own administrators: their prayer list email also holds private requests (prayer_list.py).
    "see_private_prayers": row[12],
    # Text messages (sms.py): chosen by the member on My account, or set here with their agreement ("Texts on",
    # texts= on create_user and update_user; 2026-11-22).
    "sms_opt_in": row[13],
    "sms_stopped": row[14],
    # Notes, pins and routes on the maps (map_marks.py).
    "use_maps": row[15],
    "map_mark_count": row[16],
    # Closed by its owner on My account (accounts.close_account): no login, no emails or texts. Reopened here.
    "closed": row[17] is not None,
    "closed_at": row[17].isoformat() if row[17] else None,
    # Phone login (accounts.py): the number it logs in with (+15551234567) and whether it is confirmed.
    "phone_verified": row[18],
    "login_phone": row[19],
    # May share its lists on Public lists (saved_lists.py), and how many it shares now.
    "share_lists": row[20],
    "shared_list_count": row[21],
    # Emailed every new Conversations post and reply (conversations.send_new_post_emails; 2026-11-22).
    "get_conversation_posts": row[22],
    # The Drupal administrator account this site account belongs to (saved_cards.account_for_admin; 2026-11-26),
    # None when it is matched by email address only.
    "drupal_uid": row[23],
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


# An account matches a search when its address or its name ("first last") contains the words searched for, or its
# phone number contains the digits searched for.
_MATCHES = (
  "(email LIKE %s OR lower(concat_ws(' ', first_name, last_name)) LIKE %s"
  " OR regexp_replace(COALESCE(phone, ''), '\\D', '', 'g') LIKE %s)"
)


def _digits_pattern(query: str) -> str:
  """The pattern for the phone digits searched for; one that matches nothing when the search has no digits."""
  digits = "".join(character for character in query if character.isdigit())
  # A phone's digits never equal "-", so without digits the phone part matches no account.
  return f"%{digits}%" if len(digits) >= 3 else "-"


# How the Site users list may be sorted (2026-11-23, the owner's request): by name or by address, either way; the
# accounts with no name (or no address) come last either way, then the newest. Without a sort, newest first.
_NAME = "lower(trim(concat_ws(' ', users.first_name, users.last_name)))"
_SORTS = {
  "name": f"({_NAME} = '') ASC, {_NAME} {{direction}}, lower(COALESCE(users.email, users.phone, '')) ASC",
  "email": f"(users.email IS NULL) ASC, lower(COALESCE(users.email, '')) {{direction}}, {_NAME} ASC",
  "newest": "users.created_at DESC",
}


def list_users(query: str = "", page: int = 1, sort: str = "newest", direction: str = "asc") -> dict:
  """The accounts, PER_PAGE at a time, sorted by name or email (direction asc or desc), or newest first; query keeps
  those whose address or name contains it."""
  if sort not in _SORTS:
    sort = "newest"
  order = _SORTS[sort].format(direction="DESC" if direction == "desc" else "ASC") + ", users.id DESC"
  query = query.strip().lower()[:QUERY_LIMIT]
  page = max(page, 1)
  pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
  with connect() as connection:
    digits = _digits_pattern(query) if query else pattern
    total = connection.execute(f"SELECT count(*) FROM users WHERE {_MATCHES}", (pattern, pattern, digits)).fetchone()[0]
    rows = connection.execute(
      f"SELECT {_COLUMNS} FROM users WHERE {_MATCHES} ORDER BY {order} LIMIT %s OFFSET %s",
      (pattern, pattern, digits, PER_PAGE, (page - 1) * PER_PAGE),
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
  use_conversations: bool = False,
  see_private_prayers: bool = False,
  use_maps: bool = False,
  phone_verified: bool = False,
  share_lists: bool = False,
  get_conversation_posts: bool = False,
  texts: bool = False,
) -> dict:
  """Adds an account with an email address, or with a cell phone number only (no email: it logs in with the number;
  phone_verified says whether it is confirmed, as email_verified does for an address). texts: the person agreed to
  texts (as Send via SMS on My account): the phone must be a US or Canadian cell number; a welcome text is sent."""
  email = _checked_email(email) if (email or "").strip() else None
  first_name, last_name, phone = _checked_profile(first_name, last_name, phone)
  login_phone = None if email else _login_number(phone)
  text_number = _texting_number(phone) if texts else None
  _checked_password(password)
  password_hash = hash_password(password)
  try:
    with connect() as connection:
      user_id = connection.execute(
        """
        INSERT INTO users
          (email, password_hash, email_verified_at, open_ai_queries, first_name, last_name, phone, use_conversations,
           see_private_prayers, use_maps, login_phone, phone_is_cell, phone_verified_at, send_via_email)
        VALUES (%s, %s, CASE WHEN %s THEN now() END, %s, NULLIF(%s, ''), NULLIF(%s, ''), NULLIF(%s, ''), %s, %s, %s,
                %s, %s, CASE WHEN %s THEN now() END, %s)
        RETURNING id
        """,
        (email, password_hash, bool(email and email_verified), open_ai_queries, first_name, last_name, phone,
         use_conversations, see_private_prayers, use_maps, login_phone, login_phone is not None,
         bool(login_phone and phone_verified), email is not None),
      ).fetchone()[0]
      if share_lists:
        connection.execute("UPDATE users SET share_lists = true WHERE id = %s", (user_id,))
      if get_conversation_posts:
        _turn_on_conversation_posts(connection, user_id)
      if text_number:
        connection.execute(
          """UPDATE users SET phone_is_cell = true, sms_number = %s, sms_opt_in = true, sms_consent_at = now(),
            sms_stopped_at = NULL, send_via_sms = true WHERE id = %s""",
          (text_number, user_id),
        )
  except psycopg.errors.UniqueViolation as error:
    what = "email address" if email else "phone number"
    raise UserProblem(f"An account with that {what} already exists.") from error
  if text_number:
    _welcome(text_number)
  return get_user(user_id)


def _texting_number(phone: str) -> str:
  number = texting_number(phone)
  if number is None:
    raise UserProblem("Texts can only be sent to a US or Canadian cell number with its area code, such as (555) 123-4567.")
  return number


def _welcome(number: str) -> None:
  """The welcome text that confirms texts are on and says how to stop. A failure never stops the change."""
  try:
    welcome_text(number)
  except Exception as problem:
    logger.error("The welcome text was not sent: %s", type(problem).__name__)


def _login_number(phone: str) -> str:
  number = texting_number(phone)
  if number is None:
    raise UserProblem("Please give an email address, or a US or Canadian cell phone number (the account then logs in with it).")
  return number


def update_user(
  user_id: int,
  email: str | None = None,
  password: str | None = None,
  email_verified: bool | None = None,
  open_ai_queries: bool | None = None,
  first_name: str | None = None,
  last_name: str | None = None,
  phone: str | None = None,
  use_conversations: bool | None = None,
  see_private_prayers: bool | None = None,
  use_maps: bool | None = None,
  share_lists: bool | None = None,
  get_conversation_posts: bool | None = None,
  closed: bool | None = None,
  phone_verified: bool | None = None,
  texts: bool | None = None,
  drupal_uid: int | None = None,
) -> dict:
  """Changes what is given and leaves the rest. drupal_uid: the Drupal administrator account this site account
  belongs to (0 unlinks it; another site account linked to that Drupal account is unlinked). A new password logs the account out everywhere. An empty
  name or phone ("") clears it. closed: False reopens an account its owner closed (it can log in again and get
  emails); True closes it, as the owner's Close my account does but with no email. An empty email ("") leaves the
  account with only its phone: it then logs in with that number (which must be a US or Canadian cell number), and
  is never emailed. phone_verified: whether that number is confirmed (a new login number is not, unless ticked).
  texts: True turns texts on (the person agreed; the phone must be a US or Canadian cell number; a welcome text goes
  when they were off or the number is new), False turns them off; the same as now changes nothing, so a member who
  replied STOP keeps their choice for START. A new number turns texts off unless texts is True."""
  current = get_user(user_id)
  changes = []
  values: list = []
  new_email = current["email"] or None
  if email is not None:
    new_email = _checked_email(email) if email.strip() else None
    if new_email != (current["email"] or None):
      changes.append("email = %s")
      values.append(new_email)
      if new_email is None:
        changes.append("email_verified_at = NULL, send_via_email = false")
      elif not current["email"]:
        changes.append("send_via_email = true")
  checked = _checked_profile(first_name or "", last_name or "", phone or "")
  new_phone = checked[2] if phone is not None else current["phone"]
  # The number it logs in with: needed when it has no email address; kept (moved to the new number) when it had one.
  login_phone = current["login_phone"]
  if new_email is None:
    login_phone = _login_number(new_phone)
  elif login_phone is not None and phone is not None:
    login_phone = texting_number(new_phone)
  if login_phone != current["login_phone"]:
    changes.append("login_phone = %s")
    values.append(login_phone)
    if phone_verified is None:
      changes.append("phone_verified_at = NULL")
  if phone_verified is not None and login_phone is not None and phone_verified != current["phone_verified"]:
    changes.append("phone_verified_at = CASE WHEN %s THEN now() END")
    values.append(phone_verified)
  new_number = False
  for column, given, value in zip(("first_name", "last_name", "phone"), (first_name, last_name, phone), checked):
    if given is not None and value != current[column]:
      changes.append(f"{column} = NULLIF(%s, '')")
      values.append(value)
      if column == "phone":
        # The same number written another way (555-123-4567 becoming +1 (555) 123-4567) is not a new number.
        number = texting_number(value)
        new_number = number is None or number != texting_number(current["phone"])
  welcome_number = None
  if texts:
    text_number = _texting_number(new_phone)
    if new_number or not current["sms_opt_in"]:
      changes.append(
        "phone_is_cell = true, sms_number = %s, sms_opt_in = true, sms_consent_at = now(), sms_stopped_at = NULL, send_via_sms = true"
      )
      values.append(text_number)
      welcome_number = text_number
  elif new_number or (texts is False and current["sms_opt_in"]):
    # A new number has not been agreed to for texts (the member turns them on again on My account, or here).
    changes.append("sms_opt_in = false, send_via_sms = false, send_via_email = %s")
    values.append(new_email is not None)
    if new_number:
      changes.append("phone_is_cell = %s, sms_number = NULL")
      values.append(login_phone is not None)
  if password:
    _checked_password(password)
    changes.append("password_hash = %s")
    values.append(hash_password(password))
  if email_verified is not None and new_email is not None and email_verified != current["email_verified"]:
    changes.append("email_verified_at = CASE WHEN %s THEN now() END")
    values.append(email_verified)
  if open_ai_queries is not None:
    changes.append("open_ai_queries = %s")
    values.append(open_ai_queries)
  if use_conversations is not None:
    changes.append("use_conversations = %s")
    values.append(use_conversations)
  if see_private_prayers is not None:
    changes.append("see_private_prayers = %s")
    values.append(see_private_prayers)
  if use_maps is not None:
    changes.append("use_maps = %s")
    values.append(use_maps)
  if share_lists is not None:
    changes.append("share_lists = %s")
    values.append(share_lists)
  if get_conversation_posts is not None:
    changes.append("get_conversation_posts = %s")
    values.append(get_conversation_posts)
    if get_conversation_posts:
      # The stop link of its emails (made once, kept when the box is unticked and ticked again).
      changes.append("conversation_posts_token = COALESCE(conversation_posts_token, %s)")
      values.append(secrets.token_urlsafe(24))
  if drupal_uid is not None:
    changes.append("drupal_uid = %s")
    values.append(drupal_uid or None)
  if closed is not None and closed != current["closed"]:
    changes.append("disabled_at = CASE WHEN %s THEN now() END")
    values.append(closed)
  if changes:
    try:
      with connect() as connection:
        if drupal_uid:
          # One site account for each Drupal account.
          connection.execute("UPDATE users SET drupal_uid = NULL WHERE drupal_uid = %s AND id <> %s", (drupal_uid, user_id))
        connection.execute(f"UPDATE users SET {', '.join(changes)} WHERE id = %s", (*values, user_id))
        if closed:
          connection.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
          connection.execute("DELETE FROM account_tokens WHERE user_id = %s", (user_id,))
        if password:
          # Whoever was logged in with the old password, and any reset link, no longer works.
          connection.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
          connection.execute("DELETE FROM account_tokens WHERE user_id = %s AND purpose = 'reset'", (user_id,))
    except psycopg.errors.UniqueViolation as error:
      raise UserProblem("Another account already uses that email address or phone number.") from error
  if welcome_number:
    _welcome(welcome_number)
  return get_user(user_id)


def _turn_on_conversation_posts(connection, user_id: int) -> None:
  """Ticks Get Conversation Posts, with the stop link its emails carry."""
  connection.execute(
    "UPDATE users SET get_conversation_posts = true, conversation_posts_token = COALESCE(conversation_posts_token, %s) WHERE id = %s",
    (secrets.token_urlsafe(24), user_id),
  )


def delete_user(user_id: int) -> dict:
  """Deletes the account with its notes, conversation posts, email subscriptions, sessions and links (ON DELETE
  CASCADE)."""
  user = get_user(user_id)
  with connect() as connection:
    # Their saved cards' pictures (saved_cards.py); the rows go with the account.
    saved_cards.remove_all(connection, user_id)
    connection.execute("DELETE FROM users WHERE id = %s", (user_id,))
  # Their head shot (head_shots.py) goes too.
  head_shots.path_for(user_id).unlink(missing_ok=True)
  return user

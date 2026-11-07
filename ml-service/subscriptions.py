"""Daily devotionals by email, for logged-in visitors with a confirmed email address.

A visitor subscribes to one devotional at a time of day in their own time zone. A job (scripts/send_devotional_emails.py,
started every few minutes by a systemd timer) sends what is due. A daily devotional sends the reading for the
visitor's own date; a devotional with chapters sends one chapter each day, in order, from where the visitor chose
to start, and stops after the last. Every email has a link that stops it without a login.
"""

import logging
import re
import secrets
import time
from datetime import date, datetime, time as clock, timezone
from email.message import EmailMessage
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from accounts import site_link
from contact import MailUnavailable, load_mail_settings, send_email
from devotionals import get_unit
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger("subscriptions")

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
ID_PATTERN = re.compile(r"^[a-z0-9-]{1,60}$")
# A broken mail server is tried this many times a day for one subscription, and no more.
ATTEMPTS_PER_DAY = 3
# The most emails one run sends (the mail server has limits); the rest go in the next run.
EMAILS_PER_RUN = 50
PAUSE_BETWEEN_EMAILS = 1.0
# Only one run at a time sends (a Postgres advisory lock number).
LOCK_NUMBER = 7281001


class SubscriptionProblem(Exception):
  """The request cannot be done; the text says why and is fit to show the visitor."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


@lru_cache(maxsize=1)
def _timezones() -> frozenset[str]:
  return frozenset(available_timezones())


def parse_time(text: str) -> clock:
  match = TIME_PATTERN.match(text or "")
  if not match:
    raise SubscriptionProblem("Please choose a time of day.")
  return clock(int(match.group(1)), int(match.group(2)))


def check_timezone(name: str) -> ZoneInfo:
  if name not in _timezones():
    raise SubscriptionProblem("Please choose a time zone from the list.")
  return ZoneInfo(name)


def _devotional(connection, devotional_id: str, must_be_published: bool = False) -> tuple[str, str, str]:
  """(id, name, kind) of a devotional, or a 404. A hidden one is still listed (so it can be stopped) but
  cannot be subscribed to (must_be_published)."""
  row = connection.execute("SELECT id, name, kind, is_published, collection FROM devotionals WHERE id = %s", (devotional_id,)).fetchone() if ID_PATTERN.match(devotional_id or "") else None
  # An Other book (collection "books") has no daily emails.
  if row is None or (must_be_published and (not row[3] or row[4] != "devotionals")):
    raise SubscriptionProblem("That devotional was not found.", 404)
  return row[:3]


def _unit_title(connection, devotional_id: str, section: int | None, unit: int | None) -> str | None:
  if section is None or unit is None:
    return None
  row = connection.execute(
    "SELECT unit_title FROM devotional_entries WHERE devotional_id = %s AND section = %s AND unit = %s LIMIT 1",
    (devotional_id, section, unit),
  ).fetchone()
  return row[0] if row else None


COLUMNS = "devotional_id, send_time, timezone, next_section, next_unit, last_sent_on"


def _row_to_subscription(connection, row) -> dict:
  devotional_id, send_time, zone, next_section, next_unit, last_sent_on = row
  _, name, kind = _devotional(connection, devotional_id)
  return {
    "devotional_id": devotional_id,
    "devotional_name": name,
    "kind": kind,
    "send_time": send_time.strftime("%H:%M"),
    "timezone": zone,
    # For a devotional with chapters: the one that will be sent next.
    "next_section": next_section,
    "next_unit": next_unit,
    "next_title": _unit_title(connection, devotional_id, next_section, next_unit),
    "last_sent_on": last_sent_on.isoformat() if last_sent_on else None,
  }


def list_subscriptions(user_id: int) -> list[dict]:
  with connect() as connection:
    rows = connection.execute(
      f"SELECT {COLUMNS} FROM devotional_subscriptions WHERE user_id = %s ORDER BY created_at", (user_id,)
    ).fetchall()
    subscriptions = []
    for row in rows:
      try:
        subscriptions.append(_row_to_subscription(connection, row))
      except SubscriptionProblem:
        continue  # its devotional has been removed
    return subscriptions


def save_subscription(
  user_id: int,
  devotional_id: str,
  send_time_text: str,
  timezone_name: str,
  start_section: int | None = None,
  start_unit: int | None = None,
  now: datetime | None = None,
) -> dict:
  """Starts the daily email of a devotional, or changes its time. Needs a confirmed email address."""
  send_time = parse_time(send_time_text)
  zone = check_timezone(timezone_name)
  local = (now or datetime.now(timezone.utc)).astimezone(zone)
  # If today's time has already gone by, the first email is tomorrow's, not one sent at once.
  has_passed = local.time() >= send_time
  with connect() as connection:
    verified = connection.execute("SELECT email_verified_at IS NOT NULL FROM users WHERE id = %s", (user_id,)).fetchone()
    if verified is None or not verified[0]:
      raise SubscriptionProblem("Please confirm your email address first: we emailed you a link when you set up the account.", 403)
    _, _, kind = _devotional(connection, devotional_id, must_be_published=True)
    next_section = next_unit = None
    if kind == "chapters":
      if start_section is None or start_unit is None:
        first = connection.execute(
          "SELECT section, unit FROM devotional_entries WHERE devotional_id = %s ORDER BY section, unit LIMIT 1", (devotional_id,)
        ).fetchone()
        start_section, start_unit = first
      if _unit_title(connection, devotional_id, start_section, start_unit) is None:
        raise SubscriptionProblem("That chapter was not found.")
      next_section, next_unit = start_section, start_unit
    row = connection.execute(
      f"""
      INSERT INTO devotional_subscriptions
        (user_id, devotional_id, send_time, timezone, next_section, next_unit, last_sent_on, unsubscribe_token)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
      ON CONFLICT (user_id, devotional_id) DO UPDATE SET
        send_time = EXCLUDED.send_time,
        timezone = EXCLUDED.timezone,
        next_section = CASE WHEN %s THEN EXCLUDED.next_section ELSE devotional_subscriptions.next_section END,
        next_unit = CASE WHEN %s THEN EXCLUDED.next_unit ELSE devotional_subscriptions.next_unit END,
        last_sent_on = CASE WHEN %s THEN %s ELSE devotional_subscriptions.last_sent_on END,
        attempts_on = NULL, attempts = 0,
        updated_at = now()
      RETURNING {COLUMNS}
      """,
      (
        user_id, devotional_id, send_time, timezone_name, next_section, next_unit,
        local.date() if has_passed else None, secrets.token_urlsafe(24),
        start_section is not None and kind == "chapters", start_section is not None and kind == "chapters",
        has_passed, local.date(),
      ),
    ).fetchone()
    return _row_to_subscription(connection, row)


def delete_subscription(user_id: int, devotional_id: str) -> None:
  with connect() as connection:
    deleted = connection.execute(
      "DELETE FROM devotional_subscriptions WHERE user_id = %s AND devotional_id = %s RETURNING id", (user_id, devotional_id)
    ).fetchone()
  if deleted is None:
    raise SubscriptionProblem("You are not getting that devotional by email.", 404)


def unsubscribe_with_token(token: str) -> str:
  """Stops the emails the token belongs to, with no login. Returns the devotional's name."""
  if not token or len(token) > 100:
    raise SubscriptionProblem("This link is not valid, or the emails have already been stopped.", 404)
  with connect() as connection:
    row = connection.execute("DELETE FROM devotional_subscriptions WHERE unsubscribe_token = %s RETURNING devotional_id", (token,)).fetchone()
    if row is None:
      raise SubscriptionProblem("This link is not valid, or the emails have already been stopped.", 404)
    found = connection.execute("SELECT name FROM devotionals WHERE id = %s", (row[0],)).fetchone()
  return found[0] if found else row[0]


# --- sending ---------------------------------------------------------------------------------------------


def compose_email(settings: dict, address: str, name: str, reading: dict, token: str, is_last: bool) -> EmailMessage:
  title = get_public_settings()["title"]
  parts = [f"{name}: {reading['title']}", ""]
  for entry in reading["entries"]:
    if entry["heading"]:
      parts += [entry["heading"].upper(), ""]
    parts += [entry["text"].strip(), ""]
  if is_last:
    parts += ["This was the last chapter, so these emails stop here.", ""]
  unsubscribe_link = site_link("unsubscribe=" + token)
  parts += [
    "--",
    f"Sent by {title}: {site_link('').rstrip('?')}",
    f"To stop these emails, open: {unsubscribe_link}",
  ]
  email = EmailMessage()
  email["Subject"] = f"{name}: {reading['title']}"
  email["From"] = settings["from_address"]
  email["To"] = address
  # One-click unsubscribe for mail programs (RFC 8058).
  one_click = site_link("").rstrip("?").rstrip("/") + "/api/subscriptions/unsubscribe?token=" + token
  email["List-Unsubscribe"] = f"<{one_click}>"
  email["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
  email.set_content("\n".join(parts) + "\n")
  return email


def _reading_for(subscription: dict, local_date: date) -> dict | None:
  if subscription["kind"] == "daily":
    return get_unit(subscription["devotional_id"], local_date.month, local_date.day)
  return get_unit(subscription["devotional_id"], subscription["next_section"], subscription["next_unit"])


def send_due(now: datetime | None = None, pause: float = PAUSE_BETWEEN_EMAILS) -> dict:
  """Sends every email that is due. Returns how many were sent, failed or skipped. Only one run sends at a time."""
  now = now or datetime.now(timezone.utc)
  result = {"sent": 0, "failed": 0, "skipped": 0, "already_running": False}
  with connect() as lock_connection:
    if not lock_connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_NUMBER,)).fetchone()[0]:
      result["already_running"] = True
      return result
    with connect() as connection:
      rows = connection.execute(
        """
        SELECT s.id, s.devotional_id, d.name, d.kind, s.send_time, s.timezone, s.next_section, s.next_unit,
               s.last_sent_on, s.attempts_on, s.attempts, s.unsubscribe_token, u.email
        FROM devotional_subscriptions s
        JOIN users u ON u.id = s.user_id
        JOIN devotionals d ON d.id = s.devotional_id AND d.is_published AND d.collection = 'devotionals'
        WHERE u.email_verified_at IS NOT NULL
        ORDER BY s.id
        """
      ).fetchall()
    settings = None
    for (sub_id, devotional_id, name, kind, send_time, zone_name, next_section, next_unit, last_sent_on,
         attempts_on, attempts, token, address) in rows:
      if result["sent"] + result["failed"] >= EMAILS_PER_RUN:
        break
      try:
        local = now.astimezone(ZoneInfo(zone_name))
      except Exception:
        result["skipped"] += 1
        continue
      today = local.date()
      if last_sent_on == today or local.time() < send_time or (attempts_on == today and attempts >= ATTEMPTS_PER_DAY):
        continue
      subscription = {"devotional_id": devotional_id, "kind": kind, "next_section": next_section, "next_unit": next_unit}
      reading = _reading_for(subscription, today)
      if reading is None:
        logger.error("Subscription %s: no reading to send for %s", sub_id, devotional_id)
        result["skipped"] += 1
        continue
      # Claim today before sending, so that nothing can send it twice.
      with connect() as connection:
        claimed = connection.execute(
          "UPDATE devotional_subscriptions SET last_sent_on = %s WHERE id = %s AND last_sent_on IS NOT DISTINCT FROM %s RETURNING id",
          (today, sub_id, last_sent_on),
        ).fetchone()
      if claimed is None:
        continue
      is_last = kind == "chapters" and reading["next"] is None
      try:
        if settings is None:
          settings = load_mail_settings()
        send_email(settings, compose_email(settings, address, name, reading, token, is_last))
      except Exception as problem:  # the mail server, drush or anything else: never stop the run, never lose the day
        logger.error("Devotional email %s not sent: %s: %s", sub_id, type(problem).__name__, problem if isinstance(problem, MailUnavailable) else "")
        with connect() as connection:
          # Try again at the next run, until today's tries are used up.
          tries = (attempts + 1) if attempts_on == today else 1
          connection.execute(
            "UPDATE devotional_subscriptions SET last_sent_on = %s, attempts_on = %s, attempts = %s WHERE id = %s",
            (last_sent_on if tries < ATTEMPTS_PER_DAY else today, today, tries, sub_id),
          )
        result["failed"] += 1
        continue
      with connect() as connection:
        if kind == "chapters":
          if reading["next"] is None:
            connection.execute("DELETE FROM devotional_subscriptions WHERE id = %s", (sub_id,))
          else:
            connection.execute(
              "UPDATE devotional_subscriptions SET next_section = %s, next_unit = %s, attempts_on = NULL, attempts = 0 WHERE id = %s",
              (reading["next"]["section"], reading["next"]["unit"], sub_id),
            )
        else:
          connection.execute("UPDATE devotional_subscriptions SET attempts_on = NULL, attempts = 0 WHERE id = %s", (sub_id,))
      result["sent"] += 1
      if pause:
        time.sleep(pause)
    lock_connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_NUMBER,))
  return result

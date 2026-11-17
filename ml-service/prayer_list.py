"""The prayer list: the Prayer Wall requests their authors chose to email, sent to subscribers once a week.

Any logged-in visitor with a confirmed email address may subscribe, choosing a day of the week and a time of day in
their own time zone (changed from daily to weekly on 2026-11-15 at the owner's request). Each email holds the
requests put on the list in the past week (conversation_posts.listed_at in the last seven days) that were not in an
earlier email (after prayer_list_subscriptions.sent_through), oldest first. A week with none sends nothing.
Answered requests are never sent, and an anonymous one says "Anonymous". Private requests go only to the site's
administrators: subscribers whose account has see_private_prayers (the Drupal Site users page), marked as private. The same job as the
devotionals sends them (scripts/send_devotional_emails.py, every five minutes). Every email has a link that stops
it without a login (the devotionals' unsubscribe link, which knows both).
"""

import logging
import secrets
import time
from datetime import date, datetime, time as clock, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from accounts import site_link
from contact import MailUnavailable, load_mail_settings, send_email
from conversations import ANONYMOUS
from search import connect
from site_settings import get_public_settings
import sms
from subscriptions import ATTEMPTS_PER_DAY, EMAILS_PER_RUN, PAUSE_BETWEEN_EMAILS, SubscriptionProblem, check_timezone, parse_time

logger = logging.getLogger("prayer_list")

# Only one run at a time sends (a Postgres advisory lock number; the devotionals use 7281001).
LOCK_NUMBER = 7281002
# The most requests one email lists (the rest are counted, with a link to the Prayer Wall).
REQUESTS_PER_EMAIL = 50
# An email holds only the requests listed in this long before it is sent.
WINDOW = timedelta(days=7)
# 0 is Monday, as Python's date.weekday() counts.
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _row_to_subscription(row) -> dict:
  send_weekday, send_time, zone, last_sent_on = row
  return {
    "send_weekday": send_weekday,
    "send_time": send_time.strftime("%H:%M"),
    "timezone": zone,
    "last_sent_on": last_sent_on.isoformat() if last_sent_on else None,
  }


def check_weekday(weekday: int) -> int:
  if weekday not in range(7):
    raise SubscriptionProblem("Please choose a day of the week.")
  return weekday


def last_due_date(local: datetime, weekday: int, send_time: clock) -> date:
  """The most recent day, up to now, on which the weekly email was due: today if it is that day and the time has
  come, else the same weekday before."""
  days_back = (local.weekday() - weekday) % 7
  if days_back == 0 and local.time() < send_time:
    days_back = 7
  return local.date() - timedelta(days=days_back)


def get_subscription(user_id: int) -> dict | None:
  with connect() as connection:
    row = connection.execute(
      "SELECT send_weekday, send_time, timezone, last_sent_on FROM prayer_list_subscriptions WHERE user_id = %s", (user_id,)
    ).fetchone()
  return _row_to_subscription(row) if row else None


def save_subscription(
  user_id: int, send_weekday: int, send_time_text: str, timezone_name: str, now: datetime | None = None
) -> dict:
  """Starts the weekly prayer list email, or changes its day and time. Needs a confirmed email address. The first
  email comes at the next chosen day and time (never at once) and holds the past week's requests."""
  send_weekday = check_weekday(send_weekday)
  send_time = parse_time(send_time_text)
  zone = check_timezone(timezone_name)
  now = now or datetime.now(timezone.utc)
  # Counting the most recent due day as done makes the next one the first.
  done_through = last_due_date(now.astimezone(zone), send_weekday, send_time)
  with connect() as connection:
    verified = connection.execute("SELECT email_verified_at IS NOT NULL, email IS NOT NULL FROM users WHERE id = %s", (user_id,)).fetchone()
    if verified is not None and not verified[1]:
      # An account set up with a phone number only (2026-11-17): these are emails.
      raise SubscriptionProblem("This is sent by email, and your account has no email address.", 403)
    if verified is None or not verified[0]:
      raise SubscriptionProblem("Please confirm your email address first: we emailed you a link when you set up the account.", 403)
    row = connection.execute(
      """
      INSERT INTO prayer_list_subscriptions
        (user_id, send_weekday, send_time, timezone, last_sent_on, sent_through, unsubscribe_token)
      VALUES (%s, %s, %s, %s, %s, %s, %s)
      ON CONFLICT (user_id) DO UPDATE SET
        send_weekday = EXCLUDED.send_weekday,
        send_time = EXCLUDED.send_time,
        timezone = EXCLUDED.timezone,
        last_sent_on = EXCLUDED.last_sent_on,
        attempts_on = NULL, attempts = 0,
        updated_at = now()
      RETURNING send_weekday, send_time, timezone, last_sent_on
      """,
      (user_id, send_weekday, send_time, timezone_name, done_through, now - WINDOW, secrets.token_urlsafe(24)),
    ).fetchone()
  return _row_to_subscription(row)


def delete_subscription(user_id: int) -> None:
  with connect() as connection:
    deleted = connection.execute("DELETE FROM prayer_list_subscriptions WHERE user_id = %s RETURNING id", (user_id,)).fetchone()
  if deleted is None:
    raise SubscriptionProblem("You are not getting the prayer list by email.", 404)


# --- sending ---------------------------------------------------------------------------------------------


def requests_listed(connection, after: datetime, through: datetime, include_private: bool = False) -> list[dict]:
  """The requests put on the list after one time (and in the week before the other) up to the other, oldest
  first. Never answered ones; private ones only with include_private (for the site's administrators)."""
  rows = connection.execute(
    """
    SELECT p.title, p.body_text, p.is_anonymous,
           COALESCE(NULLIF(concat_ws(' ', u.first_name, u.last_name), ''), 'A member'), p.created_at, p.is_private
    FROM conversation_posts p JOIN users u ON u.id = p.user_id
    WHERE p.board = 'prayer' AND p.answered_at IS NULL
      AND (p.email_to_prayer_list OR (p.is_private AND %s))
      AND p.listed_at > %s AND p.listed_at <= %s
    ORDER BY p.listed_at, p.id
    """,
    (include_private, max(after, through - WINDOW), through),
  ).fetchall()
  return [
    {
      "title": title, "text": text, "author": ANONYMOUS if is_anonymous else author,
      "created_at": created_at, "is_private": is_private,
    }
    for title, text, is_anonymous, author, created_at, is_private in rows
  ]


def compose_email(settings: dict, address: str, requests: list[dict], token: str, zone: ZoneInfo) -> EmailMessage:
  title = get_public_settings()["title"]
  count = len(requests)
  shown = requests[:REQUESTS_PER_EMAIL]
  wall = site_link("").rstrip("?").rstrip("/") + "/prayer-wall"
  parts = [
    f"{count} new prayer {'request' if count == 1 else 'requests'} on the Prayer Wall this week.",
    "",
  ]
  for request in shown:
    created = request["created_at"].astimezone(zone)
    when = f"{created:%B} {created.day}, {created.year}"
    byline = f"{request['author']}, {when}"
    if request.get("is_private"):
      # Only the site's administrators get these: say so, so it is not passed on.
      byline += " (PRIVATE: sent only to the site's administrators; please do not share it)"
    parts += [request["title"].upper(), byline, "", request["text"].strip(), "", ""]
  if count > len(shown):
    parts += [f"And {count - len(shown)} more on the Prayer Wall.", ""]
  unsubscribe_link = site_link("unsubscribe=" + token)
  parts += [
    f"Read them and reply on the Prayer Wall: {wall}",
    "",
    "--",
    f"Sent by {title}: {site_link('').rstrip('?')}",
    f"To stop these emails, open: {unsubscribe_link}",
  ]
  email = EmailMessage()
  email["Subject"] = f"Prayer list: {count} new {'request' if count == 1 else 'requests'} this week"
  email["From"] = settings["from_address"]
  email["To"] = address
  # One-click unsubscribe for mail programs (RFC 8058); the devotionals' endpoint knows these tokens too.
  one_click = site_link("").rstrip("?").rstrip("/") + "/api/subscriptions/unsubscribe?token=" + token
  email["List-Unsubscribe"] = f"<{one_click}>"
  email["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
  email.set_content("\n".join(parts) + "\n")
  return email


def send_due(now: datetime | None = None, pause: float = PAUSE_BETWEEN_EMAILS) -> dict:
  """Sends every weekly prayer list email that is due. Returns how many were sent, failed, or had nothing new
  (empty). A due day missed while the job was not running is caught up at the next run. Only one run sends at a time."""
  now = now or datetime.now(timezone.utc)
  result = {"sent": 0, "failed": 0, "empty": 0, "already_running": False}
  with connect() as lock_connection:
    if not lock_connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_NUMBER,)).fetchone()[0]:
      result["already_running"] = True
      return result
    with connect() as connection:
      rows = connection.execute(
        """
        SELECT s.id, s.send_weekday, s.send_time, s.timezone, s.last_sent_on, s.sent_through, s.attempts_on,
               s.attempts, s.unsubscribe_token, u.email, u.see_private_prayers, u.id
        FROM prayer_list_subscriptions s JOIN users u ON u.id = s.user_id
        WHERE u.email_verified_at IS NOT NULL AND u.disabled_at IS NULL
        ORDER BY s.id
        """
      ).fetchall()
    settings = None
    for sub_id, weekday, send_time, zone_name, last_sent_on, sent_through, attempts_on, attempts, token, address, is_admin, user_id in rows:
      if result["sent"] + result["failed"] >= EMAILS_PER_RUN:
        break
      try:
        zone = ZoneInfo(zone_name)
      except Exception:
        continue
      local = now.astimezone(zone)
      today = local.date()
      due_on = last_due_date(local, weekday, send_time)
      if (last_sent_on is not None and last_sent_on >= due_on) or (attempts_on == today and attempts >= ATTEMPTS_PER_DAY):
        continue
      with connect() as connection:
        requests = requests_listed(connection, sent_through, now, include_private=is_admin)
        # Claim this week before sending, so nothing can send it twice. With nothing new, the week is done.
        claimed = connection.execute(
          """
          UPDATE prayer_list_subscriptions SET last_sent_on = %s, sent_through = CASE WHEN %s THEN %s ELSE sent_through END
          WHERE id = %s AND last_sent_on IS NOT DISTINCT FROM %s RETURNING id
          """,
          (due_on, not requests, now, sub_id, last_sent_on),
        ).fetchone()
      if claimed is None:
        continue
      if not requests:
        result["empty"] += 1
        continue
      def send_the_email():
        nonlocal settings
        if settings is None:
          settings = load_mail_settings()
        send_email(settings, compose_email(settings, address, requests, token, zone))

      # A text is short: the count and the titles, with a link.
      count = len(requests)
      titles = "; ".join(request["title"] for request in requests)
      words = f"{count} new prayer {'request' if count == 1 else 'requests'} this week: {titles}."
      try:
        # By email, text or both, as the member chose (sms.deliver).
        sms.deliver(user_id, send_the_email, words, sms.site_address("/prayer-wall"))
      except Exception as problem:  # never stop the run; the requests stay for the next try
        logger.error("Prayer list %s not sent: %s: %s", sub_id, type(problem).__name__, problem if isinstance(problem, MailUnavailable) else "")
        with connect() as connection:
          tries = (attempts + 1) if attempts_on == today else 1
          connection.execute(
            "UPDATE prayer_list_subscriptions SET last_sent_on = %s, attempts_on = %s, attempts = %s WHERE id = %s",
            (last_sent_on if tries < ATTEMPTS_PER_DAY else due_on, today, tries, sub_id),
          )
        result["failed"] += 1
        continue
      with connect() as connection:
        connection.execute(
          "UPDATE prayer_list_subscriptions SET sent_through = %s, attempts_on = NULL, attempts = 0 WHERE id = %s", (now, sub_id)
        )
      result["sent"] += 1
      if pause:
        time.sleep(pause)
    lock_connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_NUMBER,))
  return result

"""A verse a day: a randomly chosen Bible verse sent to members who asked, by email and, for members who asked for
texts, by text too (added 2026-11-15 at the owner's request).

The verse is picked at random from the POOL_SIZE best-known verses: the ones other verses point to most in the
cross references (OpenBible.info's votes; Isaiah 41:10, Romans 8:31, Philippians 4:13, Joshua 1:9 ...), so a
member gets "Do not fear, for I am with you" rather than a line of a genealogy. Each member gets their own pick,
never the same verse two days running. The text is the BSB (public domain), else the first published Bible stored
on this site; never a licensed Bible.

A member chooses it on the sign-up form or the My account page, with a time of day in their own time zone. The
same five-minute job as the devotionals sends it (scripts/send_devotional_emails.py); emails go only to a confirmed
address, as the devotionals' do, and every email has a stop link (the devotionals' unsubscribe endpoint).
"""

import logging
import random
import secrets
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from accounts import site_link
from contact import MailUnavailable, load_mail_settings, send_email
from search import connect
import message_cards
import sms
from subscriptions import ATTEMPTS_PER_DAY, EMAILS_PER_RUN, PAUSE_BETWEEN_EMAILS, check_timezone, parse_time

logger = logging.getLogger("verse_a_day")

# Only one run at a time sends (a Postgres advisory lock number; the devotionals use 7281001, the prayer list 7281002).
LOCK_NUMBER = 7281003
POOL_SIZE = 1500
PREFERRED_TRANSLATION = "BSB"


def _row_to_subscription(row) -> dict:
  send_time, zone, last_sent_on = row
  return {
    "send_time": send_time.strftime("%H:%M"),
    "timezone": zone,
    "last_sent_on": last_sent_on.isoformat() if last_sent_on else None,
  }


def get_subscription(user_id: int) -> dict | None:
  with connect() as connection:
    row = connection.execute(
      "SELECT send_time, timezone, last_sent_on FROM verse_subscriptions WHERE user_id = %s", (user_id,)
    ).fetchone()
  return _row_to_subscription(row) if row else None


def save_subscription(user_id: int, send_time_text: str, timezone_name: str, now: datetime | None = None) -> dict:
  """Starts the verse a day, or changes its time. If today's time has already gone by, the first comes tomorrow.
  It can be chosen before the address is confirmed (on the sign-up form); nothing is sent until it is."""
  send_time = parse_time(send_time_text)
  zone = check_timezone(timezone_name)
  local = (now or datetime.now(timezone.utc)).astimezone(zone)
  has_passed = local.time() >= send_time
  with connect() as connection:
    row = connection.execute(
      """
      INSERT INTO verse_subscriptions (user_id, send_time, timezone, last_sent_on, unsubscribe_token)
      VALUES (%s, %s, %s, %s, %s)
      ON CONFLICT (user_id) DO UPDATE SET
        send_time = EXCLUDED.send_time,
        timezone = EXCLUDED.timezone,
        last_sent_on = CASE WHEN %s THEN %s ELSE verse_subscriptions.last_sent_on END,
        attempts_on = NULL, attempts = 0,
        updated_at = now()
      RETURNING send_time, timezone, last_sent_on
      """,
      (user_id, send_time, timezone_name, local.date() if has_passed else None, secrets.token_urlsafe(24), has_passed, local.date()),
    ).fetchone()
  return _row_to_subscription(row)


def delete_subscription(user_id: int) -> bool:
  """Stops it. True when there was one."""
  with connect() as connection:
    return connection.execute("DELETE FROM verse_subscriptions WHERE user_id = %s RETURNING id", (user_id,)).fetchone() is not None


# --- choosing the verse ------------------------------------------------------------------------------------


def verse_pool(connection) -> list[tuple[int, int, int]]:
  """The POOL_SIZE verses other verses point to most (single verses only, not ranges)."""
  rows = connection.execute(
    """
    SELECT to_book, to_chapter, to_verse FROM cross_references
    WHERE to_end_book IS NULL OR (to_end_book = to_book AND to_end_chapter = to_chapter AND to_end_verse = to_verse)
    GROUP BY to_book, to_chapter, to_verse ORDER BY sum(votes) DESC, to_book, to_chapter, to_verse LIMIT %s
    """,
    (POOL_SIZE,),
  ).fetchall()
  return [tuple(row) for row in rows]


def _translation(connection) -> tuple[int, str] | None:
  """(id, code) of the Bible to quote: the BSB when published, else the first published one stored here."""
  return connection.execute(
    "SELECT id, code FROM translations WHERE is_published ORDER BY code = %s DESC, id LIMIT 1", (PREFERRED_TRANSLATION,)
  ).fetchone()


def pick_verse(connection, pool: list[tuple[int, int, int]], avoid: str | None = None, chooser=random) -> dict | None:
  """A random verse of the pool with its text, not the one given in avoid ("book:chapter:verse")."""
  translation = _translation(connection)
  if translation is None or not pool:
    return None
  choices = [verse for verse in pool if f"{verse[0]}:{verse[1]}:{verse[2]}" != avoid] or pool
  for _ in range(5):
    book, chapter, verse = chooser.choice(choices)
    row = connection.execute(
      """
      SELECT verses.text, books.name FROM verses JOIN books ON books.number = verses.book_number
      WHERE verses.translation_id = %s AND verses.book_number = %s AND verses.chapter = %s AND verses.verse = %s
      """,
      (translation[0], book, chapter, verse),
    ).fetchone()
    if row:
      return {
        "book": book, "chapter": chapter, "verse": verse, "text": row[0].strip(),
        "reference": f"{row[1]} {chapter}:{verse}", "translation": translation[1], "key": f"{book}:{chapter}:{verse}",
      }
  return None


def verse_link(verse: dict) -> str:
  """The address that opens the Bible reader at the verse."""
  return site_link(f"read={verse['translation']}&book={verse['book']}&chapter={verse['chapter']}&verse={verse['verse']}")


# --- sending -----------------------------------------------------------------------------------------------


def compose_email(settings: dict, address: str, verse: dict, token: str, card=None) -> EmailMessage:
  site = site_link("").rstrip("?")
  email = EmailMessage()
  email["Subject"] = f"Your verse for today: {verse['reference']}"
  email["From"] = settings["from_address"]
  email["To"] = address
  one_click = site.rstrip("/") + "/api/subscriptions/unsubscribe?token=" + token
  email["List-Unsubscribe"] = f"<{one_click}>"
  email["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
  email.set_content(
    "\n".join(
      [
        # No quotation marks of our own: many verses begin or end inside a quotation already.
        verse["text"],
        f"{verse['reference']} ({verse['translation']})",
        "",
        f"Read it in context: {verse_link(verse)}",
        "",
        "--",
        # The owner's request, 2026-11-26: every verse we send says where it came from, with a link.
        message_cards.created_by(),
        f"To stop these emails, open: {site_link('unsubscribe=' + token)}",
      ]
    )
    + "\n"
  )
  # An HTML version in which the verse and its reference (the first two lines) are links to the verse on the
  # site, and, with Send Multimedia Messages, the verse as a picture above them, a link too (message_cards.py).
  message_cards.attach_to_email(email, card, f"{verse['text']} {verse['reference']}", link=verse_link(verse), linked_lines=2)
  return email


def send_due(now: datetime | None = None, pause: float = PAUSE_BETWEEN_EMAILS, chooser=random) -> dict:
  """Sends every verse a day that is due: by email, and by text to members who asked for texts. Returns how many
  were sent or failed. Only one run sends at a time."""
  now = now or datetime.now(timezone.utc)
  result = {"sent": 0, "failed": 0, "already_running": False}
  with connect() as lock_connection:
    if not lock_connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_NUMBER,)).fetchone()[0]:
      result["already_running"] = True
      return result
    with connect() as connection:
      rows = connection.execute(
        """
        SELECT s.id, s.send_time, s.timezone, s.last_sent_on, s.last_verse, s.attempts_on, s.attempts,
               s.unsubscribe_token, u.email, u.id, u.send_multimedia
        FROM verse_subscriptions s JOIN users u ON u.id = s.user_id
        WHERE (u.email_verified_at IS NOT NULL OR u.phone_verified_at IS NOT NULL) AND u.disabled_at IS NULL
        ORDER BY s.id
        """
      ).fetchall()
      pool = verse_pool(connection) if rows else []
    settings = None
    for sub_id, send_time, zone_name, last_sent_on, last_verse, attempts_on, attempts, token, address, user_id, multimedia in rows:
      if result["sent"] + result["failed"] >= EMAILS_PER_RUN:
        break
      try:
        local = now.astimezone(ZoneInfo(zone_name))
      except Exception:
        continue
      today = local.date()
      if last_sent_on == today or local.time() < send_time or (attempts_on == today and attempts >= ATTEMPTS_PER_DAY):
        continue
      with connect() as connection:
        verse = pick_verse(connection, pool, last_verse, chooser)
        if verse is None:
          logger.error("No verse to send (no published Bible, or no cross references)")
          break
        # Claim today before sending, so nothing can send it twice.
        claimed = connection.execute(
          """
          UPDATE verse_subscriptions SET last_sent_on = %s, last_verse = %s
          WHERE id = %s AND last_sent_on IS NOT DISTINCT FROM %s RETURNING id
          """,
          (today, verse["key"], sub_id, last_sent_on),
        ).fetchone()
      if claimed is None:
        continue
      # Send Multimedia Messages: the verse over a picture, in the email and with the text (None without pictures).
      card = message_cards.make_card(verse["text"], f"{verse['reference']} ({verse['translation']})") if multimedia else None

      def send_the_email():
        nonlocal settings
        if settings is None:
          settings = load_mail_settings()
        send_email(settings, compose_email(settings, address, verse, token, card))

      try:
        # By email, text or both, as the member chose (sms.deliver).
        sms.deliver(user_id, send_the_email, f"{verse['reference']}: {verse['text']}", verse_link(verse), card)
      except Exception as problem:  # never stop the run; try again at the next one
        logger.error("Verse %s not sent: %s: %s", sub_id, type(problem).__name__, problem if isinstance(problem, MailUnavailable) else "")
        with connect() as connection:
          tries = (attempts + 1) if attempts_on == today else 1
          connection.execute(
            "UPDATE verse_subscriptions SET last_sent_on = %s, attempts_on = %s, attempts = %s WHERE id = %s",
            (last_sent_on if tries < ATTEMPTS_PER_DAY else today, today, tries, sub_id),
          )
        result["failed"] += 1
        continue
      with connect() as connection:
        connection.execute("UPDATE verse_subscriptions SET attempts_on = NULL, attempts = 0 WHERE id = %s", (sub_id,))
      result["sent"] += 1
      if pause:
        time.sleep(pause)
    lock_connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_NUMBER,))
  return result

"""Text messages (SMS) through Telnyx, for members who asked for them (added 2026-11-15 at the owner's request).

Each member chooses how the devotional, verse a day, weekly prayer list and reply notices reach them: "Send via
Email" and "Send via SMS" (users.send_via_email, send_via_sms; migration 041), one or both. Ticking Send via SMS on a
cell number is also the consent to texts (users.sms_opt_in). A text is short, with a link. Texts go only to US and
Canadian numbers (the site sends from a toll-free number) and only while the member's email address is confirmed,
as the emails do. When a member chose texts only but cannot be texted (they replied STOP, or texting is not set up
on this site), the notice goes by email instead, so nothing is lost (delivery_for_user, deliver). The account
emails (confirm the address, reset the password) always go by email.

STOP is handled here as well as by Telnyx: a reply of STOP (or STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT) reaches
the webhook (POST /sms/webhook, signed by Telnyx with the public key on the Site settings screen), which turns the
member's texts off at once and answers with a confirmation; START (or UNSTOP, YES) turns them back on for a member
who had asked for them; HELP answers with what the texts are and how to stop them. If Telnyx itself refuses a
number that sent STOP (error 40300), the member's texts are turned off too. A failed text is logged (never the
number or the words) and never stops the email beside it.

The key, the number and the public key are on the Drupal Site settings screen (service_settings.py); with no key
or number, nothing is texted. OUTGOING_SMS=off in .env stops every text (for a test copy).
"""

import base64
import json
import logging
import os
import re
import time

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from search import connect
from service_settings import get_setting
from site_settings import get_public_settings

logger = logging.getLogger("sms")

TELNYX_MESSAGES = "https://api.telnyx.com/v2/messages"
TIMEOUT_SECONDS = 15
# Telnyx's error code for a number that replied STOP.
OPTED_OUT_CODE = "40300"
# A webhook older or newer than this is refused (a replayed one).
WEBHOOK_TOLERANCE_SECONDS = 300
# Longest text the site sends; longer words are cut. Two standard segments are 306 characters.
TEXT_LIMIT = 300
STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "OPTOUT", "REVOKE"}
START_WORDS = {"START", "UNSTOP", "YES"}
HELP_WORDS = {"HELP", "INFO"}


class SmsProblem(Exception):
  """A number or choice cannot be saved; the text says why and is fit to show the member."""


def texting_number(phone: str) -> str | None:
  """A US or Canadian phone number in the form Telnyx needs (+15551234567), or None when it is not one: ten
  digits, or eleven starting with 1, with any spaces, dashes, dots or brackets."""
  phone = (phone or "").strip()
  digits = re.sub(r"\D", "", phone)
  if phone.startswith("+") and not phone.startswith("+1"):
    return None
  if len(digits) == 11 and digits.startswith("1"):
    digits = digits[1:]
  if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
    return None
  return "+1" + digits


def format_phone(phone: str) -> str:
  """A US or Canadian number written the site's way, +1 (555) 123-4567 (the owner's request); anything else
  (another country's number, or one that is not a whole number) is left as it was typed."""
  number = texting_number(phone)
  if number is None:
    return (phone or "").strip()
  return f"+1 ({number[2:5]}) {number[5:8]}-{number[8:]}"


def is_configured() -> bool:
  return bool(get_setting("telnyx_api_key") and get_setting("telnyx_from_number")) and os.environ.get("OUTGOING_SMS", "on") != "off"


def _footer() -> str:
  return " Reply STOP to end texts."


def compose(words: str, link: str = "") -> str:
  """A text: the site's name, the words (cut if long), a link, and how to stop."""
  start = f"{get_public_settings()['title']}: "
  end = (f" {link}" if link else "") + _footer()
  room = TEXT_LIMIT - len(start) - len(end)
  words = " ".join(words.split())
  if len(words) > room:
    words = words[: max(room - 1, 0)].rstrip() + "…"
  return start + words + end


def _turn_off(number: str, reason: str) -> None:
  with connect() as connection:
    connection.execute(
      "UPDATE users SET sms_opt_in = false, sms_stopped_at = now() WHERE sms_number = %s AND sms_opt_in", (number,)
    )
  logger.info("Texts turned off for a member (%s)", reason)


def send_text(number: str, text: str, media_url: str | None = None) -> bool:
  """Sends one text, or a picture message (MMS) with the text when media_url is given (a public address Telnyx
  fetches the picture from; message_cards.py). True when Telnyx took it. A number that replied STOP is turned
  off here too."""
  if not is_configured():
    return False
  # Never to a closed account's number (users.disabled_at, added 2026-11-17), whichever part of the site sends.
  with connect() as connection:
    closed = connection.execute(
      "SELECT bool_and(disabled_at IS NOT NULL) FROM users WHERE sms_number = %s OR phone = %s", (number, number)
    ).fetchone()[0]
  if closed:
    logger.info("A text was not sent to a closed account.")
    return False
  message = {"from": get_setting("telnyx_from_number"), "to": number, "text": text}
  if media_url:
    message["media_urls"] = [media_url]
  try:
    response = httpx.post(
      TELNYX_MESSAGES,
      headers={"Authorization": f"Bearer {get_setting('telnyx_api_key')}"},
      json=message,
      timeout=TIMEOUT_SECONDS,
    )
  except httpx.HTTPError as problem:
    logger.error("Text not sent: %s", type(problem).__name__)
    return False
  if response.status_code < 300:
    return True
  try:
    codes = [str(error.get("code")) for error in response.json().get("errors", [])]
  except ValueError:
    codes = []
  if OPTED_OUT_CODE in codes:
    _turn_off(number, "Telnyx says the number replied STOP")
  logger.error("Text not sent: Telnyx answered %s %s", response.status_code, ",".join(codes))
  return False


def number_for_user(connection, user_id: int) -> str | None:
  """The number to text a member at, or None when they should not be texted."""
  row = connection.execute(
    """
    SELECT sms_number FROM users
    WHERE id = %s AND sms_opt_in AND sms_number IS NOT NULL
      AND (email_verified_at IS NOT NULL OR phone_verified_at IS NOT NULL)
    """,
    (user_id,),
  ).fetchone()
  return row[0] if row else None


class TextNotSent(Exception):
  """A notice the member gets only by text could not be texted (the caller tries again later)."""


def delivery_for_user(connection, user_id: int) -> tuple[bool, str | None]:
  """How a notice reaches a member: (send it by email?, the number to text it to, or None). Email when they chose
  it, or when they chose texts but cannot be texted now (STOP, no number, texting not set up here)."""
  row = connection.execute(
    "SELECT send_via_email, send_via_sms, email IS NOT NULL FROM users WHERE id = %s", (user_id,)
  ).fetchone()
  if row is None:
    return False, None
  by_email, by_text, has_email = row
  number = number_for_user(connection, user_id) if by_text and is_configured() else None
  if not has_email:
    # An account set up with a phone number only (2026-11-17): never by email; by text when it can be, else not.
    return False, number
  return bool(by_email or number is None), number


def deliver(user_id: int, send_the_email, words: str, link: str = "", picture=None) -> dict:
  """Sends one notice the way the member chose. send_the_email() sends the email and raises if it cannot. Raises
  when the notice reached the member by no way they chose, so the caller can try again; a text that fails beside
  an email that went is only logged. With a picture (a message_cards.MessageCard) the text goes as an MMS with
  it. An account with no email address and no number to text gets nothing and nothing is raised. Returns
  {"email": sent?, "text": sent?}."""
  with connect() as connection:
    by_email, number = delivery_for_user(connection, user_id)
  sent = {"email": False, "text": False}
  if by_email:
    send_the_email()
    sent["email"] = True
  if number:
    try:
      if picture is not None:
        sent["text"] = send_text(number, compose(words, link), picture.url)
      else:
        sent["text"] = send_text(number, compose(words, link))
    except Exception as problem:
      logger.error("Text for member %s not sent: %s", user_id, type(problem).__name__)
    if not sent["text"] and not by_email:
      raise TextNotSent("The text could not be sent.")
  return sent


def site_address(path: str = "") -> str:
  return os.environ.get("SITE_URL", "https://freestudy.bible").rstrip("/") + path


# --- choosing texts (the sign-up form and the My account page) -------------------------------------------


def check_choices(phone: str, phone_is_cell: bool, sms_opt_in: bool) -> tuple[bool, str | None, bool]:
  """(phone_is_cell, sms_number, sms_opt_in) to save for a phone number, "This is a cell number" and "Send via
  SMS" (whose tick is the consent to texts)."""
  phone = (phone or "").strip()
  if not phone:
    return False, None, False
  if not phone_is_cell:
    return False, None, False
  number = texting_number(phone)
  if sms_opt_in and number is None:
    raise SmsProblem("Texts can only be sent to a US or Canadian cell number with its area code, such as (555) 123-4567.")
  return True, number, bool(sms_opt_in and number)


def welcome_text(number: str) -> None:
  """The first text, sent when a member turns texts on: it confirms the choice and says how to stop."""
  send_text(
    number,
    compose(
      "You will get texts for the devotionals, verse a day, prayer list and replies you asked for. Message and data rates may apply. Reply HELP for help.",
    ),
  )


# --- the webhook (STOP, START, HELP) ----------------------------------------------------------------------


def verify_signature(body: bytes, signature: str, timestamp: str, now: float | None = None) -> bool:
  """Whether Telnyx signed this webhook: an Ed25519 signature of "timestamp|body" with the public key on the
  Site settings screen, sent at most five minutes ago."""
  public_key = get_setting("telnyx_public_key")
  if not public_key or not signature or not timestamp:
    return False
  try:
    if abs((now or time.time()) - int(timestamp)) > WEBHOOK_TOLERANCE_SECONDS:
      return False
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
    key.verify(base64.b64decode(signature), f"{timestamp}|".encode() + body)
    return True
  except (InvalidSignature, ValueError, TypeError):
    return False


def handle_webhook(body: bytes) -> str:
  """Acts on a reply to one of the site's texts. Returns what was done (for the log and the tests)."""
  try:
    event = json.loads(body)["data"]
  except (ValueError, KeyError, TypeError):
    return "ignored"
  if event.get("event_type") != "message.received":
    return "ignored"
  payload = event.get("payload") or {}
  number = (payload.get("from") or {}).get("phone_number") or ""
  word = re.sub(r"[^A-Z]", "", (payload.get("text") or "").strip().split(" ")[0].upper()) if payload.get("text") else ""
  if not number:
    return "ignored"
  title = get_public_settings()["title"]
  if word in STOP_WORDS:
    _turn_off(number, "STOP reply")
    send_text(number, f"{title}: You will get no more texts from us. Reply START to get them again.")
    return "stopped"
  if word in START_WORDS:
    with connect() as connection:
      restarted = connection.execute(
        """
        UPDATE users SET sms_opt_in = true, sms_stopped_at = NULL, send_via_sms = true
        WHERE sms_number = %s AND sms_consent_at IS NOT NULL AND phone_is_cell RETURNING id
        """,
        (number,),
      ).fetchall()
    if restarted:
      send_text(number, compose("Texts are on again.", site_address("/account")))
      return "started"
    return "unknown"
  if word in HELP_WORDS:
    send_text(
      number,
      f"{title}: texts for the devotionals, verse a day, prayer list and replies you asked for. Change them at "
      f"{site_address('/account')} . Message and data rates may apply. Reply STOP to end texts.",
    )
    return "help"
  return "ignored"

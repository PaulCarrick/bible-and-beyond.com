"""Make your own verse card (added 2026-11-26 at the owner's request), on the Verse of the day page: a visitor chooses
a Bible stored on this site, a verse and a background (one of the verse a day pictures in use, shown as
thumbnails, or the plain deep blue), sees the card, and downloads it or sends it.

- The card is drawn exactly like the Verse of the day (message_cards.render), on the chosen background.
- Anyone may make and download a card. Sending needs a logged-in member (so the site's email cannot be used by
  strangers), at most SENDS_PER_DAY cards a day for each account (kept in memory, so a restart resets it).
- A card goes to a site user chosen by name (the way they chose on My account: email, text or both, the text as a
  picture message), or to an email address typed in. Its email names the sender, has Reply-To their address when
  they have one, and ends with the "Created by" line. Addresses are never shown to the sender or logged.
- The card is saved like a picture message's (message_cards.save_card: a random name, deleted after a week), as
  an email carries it inline and a text fetches it from its address.
"""

import base64
import io
import logging
import time
from email.message import EmailMessage

import message_cards
import sms
import verse_images
from accounts import site_link
from contact import EMAIL_LIMIT, EMAIL_PATTERN, MailUnavailable, load_mail_settings, send_email
from day_cards import find_verse
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger("custom_cards")

PLAIN = "plain"
SENDS_PER_DAY = 20
_sends: dict[int, list[float]] = {}


class CardProblem(Exception):
  """The card cannot be made or sent; the text is fit for the visitor."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


# --- the backgrounds ----------------------------------------------------------------------------------------


def backgrounds() -> list[dict]:
  """The backgrounds to choose from: the verse a day pictures in use (newest first), each with the address of its
  thumbnail, then the plain one."""
  found = [
    {
      "id": image["id"],
      "title": image["title"],
      # The upload time as a version, so a replaced picture is fetched again.
      "thumbnail": f"/card-background/{image['id']}?v=" + "".join(c for c in image["created_at"][:19] if c.isdigit()),
    }
    for image in verse_images.list_images()
    if image["in_use"] and image["file_present"]
    and (verse_images.images_folder() / verse_images.thumbnail_name(image["id"])).is_file()
  ]
  return found + [{"id": PLAIN, "title": "Plain blue", "thumbnail": None}]


def background_thumbnail(image_id: str):
  """The thumbnail file of a picture in use, or None (a picture not in use is never shown)."""
  image = verse_images.get_image(image_id)
  if image is None or not image["in_use"]:
    return None
  path = verse_images.images_folder() / verse_images.thumbnail_name(image_id)
  return path if path.is_file() else None


def _background(background_id: str):
  if background_id == PLAIN:
    return message_cards.plain_background()
  image = verse_images.get_image(background_id)
  if image is None or not image["in_use"] or not image["file_present"]:
    raise CardProblem("That background is no longer available. Choose another.")
  return verse_images.images_folder() / image["file_name"]


# --- the card -----------------------------------------------------------------------------------------------


def _draw(translation: str, book: int, chapter: int, verse: int, background_id: str):
  found = find_verse(translation, book, chapter, verse)
  if found is None:
    raise CardProblem("That verse was not found in a Bible on this site.", 404)
  return found, message_cards.render(_background(background_id), found["text"], found["caption"])


def preview(translation: str, book: int, chapter: int, verse: int, background_id: str) -> dict:
  """The card as it will look, inline (a data: address), with the verse's words and caption."""
  found, card = _draw(translation, book, chapter, verse, background_id)
  buffer = io.BytesIO()
  card.save(buffer, "JPEG", quality=message_cards.JPEG_QUALITY, optimize=True, progressive=True)
  return {
    "words": found["text"],
    "caption": found["caption"],
    "image": "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode(),
    "verse": found["verse"],
  }


# --- who a card can go to -----------------------------------------------------------------------------------

_NAME = "NULLIF(concat_ws(' ', first_name, last_name), '')"


def recipients(viewer_id: int) -> list[dict]:
  """The site users a member may send a card to: the other open accounts that have a name, by name ({id, name};
  never an address)."""
  with connect() as connection:
    rows = connection.execute(
      f"""
      SELECT id, {_NAME} FROM users
      WHERE disabled_at IS NULL AND id <> %s AND {_NAME} IS NOT NULL
      ORDER BY lower({_NAME}), id
      """,
      (viewer_id,),
    ).fetchall()
  return [{"id": row[0], "name": row[1]} for row in rows]


def _sender_name(sender: dict) -> str:
  name = " ".join(part for part in (sender.get("first_name"), sender.get("last_name")) if part)
  return name or "A member"


def _check_limit(sender_id: int, now: float | None = None) -> None:
  """Refuses a member who has sent SENDS_PER_DAY cards in the last day. Only cards that went are counted."""
  now = now or time.time()
  recent = [moment for moment in _sends.get(sender_id, []) if now - moment < 24 * 60 * 60]
  _sends[sender_id] = recent
  if len(recent) >= SENDS_PER_DAY:
    raise CardProblem(f"You have sent {SENDS_PER_DAY} cards today, the most for one day. Please try again tomorrow.", 429)


def _count_send(sender_id: int) -> None:
  _sends.setdefault(sender_id, []).append(time.time())


# --- sending ------------------------------------------------------------------------------------------------


def verse_link(verse: dict) -> str:
  return site_link(f"read={verse['translation']}&book={verse['book']}&chapter={verse['chapter']}&verse={verse['verse']}")


def compose_email(settings: dict, address: str, found: dict, card, sender: dict) -> EmailMessage:
  name = _sender_name(sender)
  email = EmailMessage()
  email["Subject"] = f"{name} sent you a verse: {found['reference']}"
  email["From"] = settings["from_address"]
  email["To"] = address
  if sender.get("email"):
    email["Reply-To"] = sender["email"]
  email.set_content(
    "\n".join(
      [
        found["text"],
        found["caption"],
        "",
        f"{name} made this card for you on {get_public_settings()['title']}.",
        "",
        f"Read it in context: {verse_link(found['verse'])}",
        "",
        "--",
        message_cards.created_by(),
      ]
    )
    + "\n"
  )
  message_cards.attach_to_email(email, card, f"{found['text']} {found['caption']}", link=verse_link(found["verse"]), linked_lines=2)
  return email


def send(
  sender: dict,
  translation: str,
  book: int,
  chapter: int,
  verse: int,
  background_id: str,
  recipient_id: int | None = None,
  email_address: str | None = None,
) -> dict:
  """Sends the card to a site user (recipient_id) or an email address. Returns {"sent_to": a name or the address
  typed, "ways": [...]}."""
  email_address = (email_address or "").strip()
  if (recipient_id is None) == (not email_address):
    raise CardProblem("Choose a site user or type an email address, not both.")
  if email_address and (len(email_address) > EMAIL_LIMIT or not EMAIL_PATTERN.match(email_address)):
    raise CardProblem("That email address does not look right.")
  recipient = None
  if recipient_id is not None:
    recipient = next((person for person in recipients(sender["id"]) if person["id"] == recipient_id), None)
    if recipient is None:
      raise CardProblem("That site user cannot be sent a card.")
  _check_limit(sender["id"])
  found, picture = _draw(translation, book, chapter, verse, background_id)
  card = message_cards.save_card(picture)
  try:
    settings = load_mail_settings()
  except MailUnavailable:
    settings = None

  if email_address:
    if settings is None:
      raise CardProblem("Email cannot be sent from this site right now. Please try again later.", 503)
    try:
      send_email(settings, compose_email(settings, email_address, found, card, sender))
    except MailUnavailable as problem:
      logger.error("Verse card not emailed: %s", problem)
      raise CardProblem("The card could not be sent. Please try again later.", 502)
    _count_send(sender["id"])
    logger.info("Member %s emailed a verse card to an address", sender["id"])
    return {"sent_to": email_address, "ways": ["email"]}

  with connect() as connection:
    row = connection.execute(
      "SELECT email, email_verified_at IS NOT NULL FROM users WHERE id = %s AND disabled_at IS NULL", (recipient_id,)
    ).fetchone()
  address, confirmed = (row[0], row[1]) if row else (None, False)

  def send_the_email():
    if not address or not confirmed or settings is None:
      raise MailUnavailable("no confirmed address or no email here")
    send_email(settings, compose_email(settings, address, found, card, sender))

  words = f"{_sender_name(sender)} sent you a verse: {found['caption']}: {found['text']}"
  try:
    sent = sms.deliver(recipient_id, send_the_email, words, verse_link(found["verse"]), card)
  except Exception as problem:
    logger.error("Verse card to member %s not sent: %s", recipient_id, type(problem).__name__)
    raise CardProblem(f"The card could not be sent to {recipient['name']}. They may not have a confirmed email address or a number for texts.", 502)
  ways = [way for way in ("email", "text") if sent.get(way)]
  if not ways:
    raise CardProblem(f"The card could not be sent to {recipient['name']}. They may not have a confirmed email address or a number for texts.", 502)
  _count_send(sender["id"])
  logger.info("Member %s sent a verse card to member %s (%s)", sender["id"], recipient_id, ", ".join(ways))
  return {"sent_to": recipient["name"], "ways": ways}

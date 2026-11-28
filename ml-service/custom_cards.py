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
- "Add my own message" (added 2026-11-28 at the owner's request): the member's own words, written in the rich text
  editor, take the place of the verse's words on the card (the reference stays under them). The HTML is cleaned
  with the contact form's allowlist (contact.check_rich_text); the card shows its text, line by line, and the email
  shows the cleaned HTML with its formatting.
"""

import base64
import io
import logging
import time
from email.message import EmailMessage

import message_cards
import saved_cards
import sms
import verse_images
from accounts import site_link
from contact import EMAIL_LIMIT, EMAIL_PATTERN, ContactProblem, MailUnavailable, check_rich_text, load_mail_settings, send_email
from day_cards import find_verse
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger("custom_cards")

PLAIN = "plain"
SENDS_PER_DAY = 20
# A member's own message: the most HTML taken from the editor, and the most words (as plain text) that still fit the
# card at a size that reads (past that the card would cut it with "…").
MESSAGE_HTML_LIMIT = 20000
MESSAGE_TEXT_LIMIT = 500
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


def clean_message(message_html: str | None) -> dict | None:
  """A member's own message for the card, cleaned ({"html", "text"}), or None when there is none."""
  if message_html is None:
    return None
  try:
    return check_rich_text(message_html, MESSAGE_HTML_LIMIT, MESSAGE_TEXT_LIMIT, "message")
  except ContactProblem as problem:
    raise CardProblem(str(problem))


def _draw(translation: str, book: int, chapter: int, verse: int, background_id: str, message_html: str | None = None):
  """The verse (with "text" the words on the card: the member's own message when there is one, and "message_html"
  that message cleaned, else None) and the card drawn."""
  found = find_verse(translation, book, chapter, verse)
  if found is None:
    raise CardProblem("That verse was not found in a Bible on this site.", 404)
  message = clean_message(message_html)
  found = {**found, "message_html": None}
  if message:
    found.update(text=message["text"], message_html=message["html"])
  card = message_cards.render(_background(background_id), found["text"], found["caption"], keep_line_breaks=bool(message))
  return found, card


def preview(translation: str, book: int, chapter: int, verse: int, background_id: str, message_html: str | None = None) -> dict:
  """The card as it will look, inline (a data: address), with its words (the verse's, or the member's own message)
  and caption."""
  found, card = _draw(translation, book, chapter, verse, background_id, message_html)
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


def _what_was_sent(found: dict) -> str:
  """"a verse", or "a card" when the member wrote their own message on it."""
  return "a card" if found.get("message_html") else "a verse"


def compose_email(settings: dict, address: str, found: dict, card, sender: dict) -> EmailMessage:
  """The card's email: the words (the verse, or the member's own message) and the reference, which link to the
  verse, the card inline, and the Created by line. A message keeps its formatting in the HTML version."""
  name = _sender_name(sender)
  email = EmailMessage()
  email["Subject"] = f"{name} sent you {_what_was_sent(found)}: {found['reference']}"
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
  link = verse_link(found["verse"])
  if found.get("message_html"):
    from html import escape

    # The message as written (cleaned) and the reference as a link to the verse, in place of the plain lines.
    lead_html = (
      f'<div style="max-width:640px;font-size:18px;line-height:1.5;">{found["message_html"]}</div>'
      f'<p style="margin:0 0 4px;font-size:18px;"><a href="{escape(link)}" style="color:#1d3f8a;">{escape(found["caption"])}</a></p>'
    )
    message_cards.attach_to_email(
      email, card, f"{found['text']} {found['caption']}", link=link,
      linked_lines=len(found["text"].split("\n")) + 1, lead_html=lead_html,
    )
  else:
    message_cards.attach_to_email(email, card, f"{found['text']} {found['caption']}", link=link, linked_lines=2)
  return email


def save(
  user_id: int,
  translation: str,
  book: int,
  chapter: int,
  verse: int,
  background_id: str,
  card_id: int | None = None,
  message_html: str | None = None,
) -> dict:
  """Draws the card (with the member's own message when given) and keeps it on the member's My cards
  (saved_cards.py); card_id: the saved card being edited. The page calls it when a logged-in member downloads a
  card."""
  found, picture = _draw(translation, book, chapter, verse, background_id, message_html)
  try:
    return saved_cards.keep(user_id, found, background_id, picture, card_id)
  except saved_cards.SavedCardProblem as problem:
    raise CardProblem(str(problem), problem.status_code)


def send(
  sender: dict,
  translation: str | None,
  book: int | None,
  chapter: int | None,
  verse: int | None,
  background_id: str | None,
  recipient_id: int | None = None,
  email_address: str | None = None,
  saved_card_id: int | None = None,
  editing_card_id: int | None = None,
  message_html: str | None = None,
) -> dict:
  """Sends the card to a site user (recipient_id) or an email address: the one drawn from the verse and background
  (with the member's own message when given, and then kept on the sender's My cards, replacing editing_card_id when
  given), or the sender's saved card saved_card_id as it was kept. Returns {"sent_to": a name or the address typed, "ways": [...], "card": the saved
  card}."""
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
  if saved_card_id is not None:
    try:
      kept = saved_cards.get_card(sender["id"], saved_card_id)
      card = saved_cards.card_for_sending(sender["id"], saved_card_id)
    except saved_cards.SavedCardProblem as problem:
      raise CardProblem(str(problem), problem.status_code)
    found = {
      "text": kept["words"], "caption": kept["caption"], "reference": kept["reference"],
      "verse": {key: kept[key] for key in ("translation", "book", "chapter", "verse")},
      "message_html": kept["message_html"],
    }
    picture = None
  else:
    found, picture = _draw(translation, book, chapter, verse, background_id, message_html)
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
    return {"sent_to": email_address, "ways": ["email"], "card": _keep_sent(sender, found, background_id, picture, editing_card_id, saved_card_id)}

  with connect() as connection:
    row = connection.execute(
      "SELECT email, email_verified_at IS NOT NULL FROM users WHERE id = %s AND disabled_at IS NULL", (recipient_id,)
    ).fetchone()
  address, confirmed = (row[0], row[1]) if row else (None, False)

  def send_the_email():
    if not address or not confirmed or settings is None:
      raise MailUnavailable("no confirmed address or no email here")
    send_email(settings, compose_email(settings, address, found, card, sender))

  words = f"{_sender_name(sender)} sent you {_what_was_sent(found)}: {found['caption']}: {found['text']}"
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
  return {"sent_to": recipient["name"], "ways": ways, "card": _keep_sent(sender, found, background_id, picture, editing_card_id, saved_card_id)}


def _keep_sent(sender: dict, found: dict, background_id, picture, editing_card_id, saved_card_id) -> dict | None:
  """A card that went is kept on the sender's My cards (a saved card sent again is already there). A failure to
  keep it never undoes the send."""
  try:
    if saved_card_id is not None:
      kept = saved_cards.get_card(sender["id"], saved_card_id)
      kept.pop("file_name", None)
      return kept
    return saved_cards.keep(sender["id"], found, background_id, picture, editing_card_id)
  except Exception as problem:
    logger.error("A sent verse card was not kept: %s", type(problem).__name__)
    return None

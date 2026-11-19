"""The contact form: checks the visitor is not a robot (Google reCAPTCHA v3), cleans up the message and
sends it by email with the server settings an administrator keeps in Drupal.

Those settings include the email password, so they are never in the Bible database and never on the
public API. This module asks Drupal for them with drush when a message is sent, keeps them only for
that one message, and never logs them.
"""

import json
import logging
import os
import re
import shlex
import smtplib
import ssl
import subprocess
from email.message import EmailMessage
from email.utils import getaddresses
from html import escape
from html.parser import HTMLParser
from pathlib import Path

import httpx
from service_settings import get_setting

logger = logging.getLogger("contact")

RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
DRUPAL_DIRECTORY = Path(__file__).resolve().parent.parent / "drupal"
MAIL_SETTINGS_PHP = "echo json_encode(\\Drupal\\bible_admin\\MailSettings::load(\\Drupal::configFactory()));"

NAME_LIMIT = 100
PHONE_LIMIT = 40
EMAIL_LIMIT = 254
MESSAGE_TEXT_LIMIT = 5000
MESSAGE_HTML_LIMIT = 30000

EMAIL_PATTERN = re.compile(r"^[^\s@<>\"',;:()\[\]\\]+@[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ContactProblem(Exception):
  """The visitor's message cannot be sent; the text says why and is fit to show them."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


class MailUnavailable(Exception):
  """The message was fine but could not be sent. The reason goes in the log, not to the visitor."""


def get_recaptcha_site_key() -> str:
  # Set on the Drupal Site settings screen (service_settings.py), else in ml-service/.env.
  return get_setting("recaptcha_site_key").strip()


RECAPTCHA_ACTION = "contact"
DEFAULT_MINIMUM_SCORE = 0.5


def verify_recaptcha(token: str, remote_address: str | None) -> None:
  """Raises ContactProblem unless Google says the token is good (reCAPTCHA v3: a score from 0 to 1)."""
  secret = get_setting("recaptcha_secret_key").strip()
  if not secret or not get_recaptcha_site_key():
    raise ContactProblem("The contact form is not available right now.", 503)
  if not token:
    raise ContactProblem("The check that you are not a robot did not run. Please reload the page and try again.", 400)
  payload = {"secret": secret, "response": token}
  if remote_address:
    payload["remoteip"] = remote_address
  try:
    response = httpx.post(RECAPTCHA_VERIFY_URL, data=payload, timeout=10)
    response.raise_for_status()
    result = response.json()
  except (httpx.HTTPError, ValueError) as error:
    logger.error("reCAPTCHA could not be checked: %s", type(error).__name__)
    raise ContactProblem("The check that you are not a robot could not be done. Please try again in a moment.", 503)
  try:
    minimum_score = float(get_setting("recaptcha_minimum_score") or DEFAULT_MINIMUM_SCORE)
  except ValueError:
    minimum_score = DEFAULT_MINIMUM_SCORE
  score = result.get("score")
  if (
    not result.get("success")
    or result.get("action") != RECAPTCHA_ACTION
    or not isinstance(score, (int, float))
    or score < minimum_score
  ):
    logger.warning("reCAPTCHA refused a message: success=%s action=%s score=%s", result.get("success"), result.get("action"), score)
    raise ContactProblem("The check that you are not a robot did not pass. Please try again later.", 400)


# The formatting the editor (Quill) can make. Everything else is dropped, keeping its text.
ALLOWED_TAGS = {
  "p", "br", "strong", "b", "em", "i", "s", "u", "a", "blockquote", "pre", "code",
  "ul", "ol", "li", "h1", "h2", "h3",
}
DROPPED_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "template", "noscript"}
SAFE_LINK = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)


class _Cleaner(HTMLParser):
  """Keeps only the allowed tags, without their attributes (a link keeps a safe address). A subclass can
  allow more tags (allowed_tags) and write its own opening tags (opening)."""

  allowed_tags = ALLOWED_TAGS
  # The site's editor (Quill 2) writes every space as a non-breaking space (&nbsp;), which makes a whole paragraph
  # one long "word" that the browser can only break in the middle of a word. They are kept as plain spaces. The
  # site owner's FAQ notes (written in CKEditor, where one may be meant) keep theirs.
  keeps_non_breaking_spaces = False

  def __init__(self):
    super().__init__(convert_charrefs=True)
    self.parts: list[str] = []
    # Each open tag as (tag, closing text); the closing text is empty for a link that was dropped.
    self.open_tags: list[tuple[str, str]] = []
    self.skip_depth = 0

  def handle_starttag(self, tag, attributes):
    if tag in DROPPED_WITH_CONTENT:
      self.skip_depth += 1
      return
    if self.skip_depth or tag not in self.allowed_tags:
      return
    if tag == "br":
      self.parts.append("<br>")
      return
    opening = self.opening(tag, dict(attributes))
    if opening is None:
      self.open_tags.append((tag, ""))  # keep the text, drop the link
      return
    self.parts.append(opening)
    self.open_tags.append((tag, f"</{tag}>"))

  def opening(self, tag: str, attributes: dict) -> str | None:
    """The opening tag to write, or None for a link whose address is not safe (its text is kept)."""
    if tag == "a":
      address = (attributes.get("href") or "").strip()
      if not SAFE_LINK.match(address):
        return None
      return f'<a href="{escape(address, quote=True)}" rel="noopener noreferrer">'
    return f"<{tag}>"

  def handle_endtag(self, tag):
    if tag in DROPPED_WITH_CONTENT:
      self.skip_depth = max(0, self.skip_depth - 1)
      return
    if self.skip_depth or tag not in self.allowed_tags or tag == "br":
      return
    if any(open_tag == tag for open_tag, _ in self.open_tags):
      while self.open_tags:
        open_tag, closing = self.open_tags.pop()
        self.parts.append(closing)
        if open_tag == tag:
          break

  def handle_data(self, data):
    if not self.skip_depth:
      if not self.keeps_non_breaking_spaces:
        data = data.replace("\u00a0", " ")
      self.parts.append(escape(data, quote=False))

  def close(self):
    super().close()
    while self.open_tags:
      self.parts.append(self.open_tags.pop()[1])


# --- fonts, sizes and colours (the admin editors' Font buttons; added 2026-11-19 at the owner's request) ------------
# The choices offered by the Font plugin of the Drupal admin editors (bible_admin.ckeditor5.yml, FONT_* there must
# match). A <span> keeps a style only when every property in it is one of these; anything else (pasted styles,
# positions, url(...)) is dropped. Only the site's own editors use FormattedCleaner; visitors' text never has fonts.
FONT_FAMILIES = (
  "Arial, Helvetica, sans-serif",
  "Georgia, serif",
  "Times New Roman, Times, serif",
  "Verdana, Geneva, sans-serif",
  "Trebuchet MS, Helvetica, sans-serif",
  "Tahoma, Geneva, sans-serif",
  "Courier New, Courier, monospace",
  # Script (handwriting) fonts, added the same day at the owner's request. Many computers have them, phones mostly
  # not: there the reader's own handwriting-style font (cursive) is used instead.
  "Brush Script MT, cursive",
  "Lucida Handwriting, cursive",
  "Segoe Script, cursive",
)
FONT_SIZES = ("12px", "14px", "16px", "18px", "20px", "24px", "28px", "32px")
FONT_COLOURS = (
  "#000000", "#4d4d4d", "#999999", "#ffffff", "#c0392b", "#e67e22", "#f1c40f", "#27ae60", "#16a085", "#2980b9",
  "#1d3f8a", "#8e44ad",
)


def _font_key(value: str) -> str:
  """A font list compared without quotes, spaces or case ("'Times New Roman', Times" and "times new roman,times")."""
  return re.sub(r"[\s'\"]", "", value).lower()


_FAMILY_KEYS = {_font_key(family): family for family in FONT_FAMILIES}
_COLOUR_PATTERN = re.compile(r"^#([0-9a-f]{3}|[0-9a-f]{6})$")


def _colour(value: str) -> str | None:
  value = value.strip().lower()
  if _COLOUR_PATTERN.match(value):
    if len(value) == 4:
      value = "#" + "".join(character * 2 for character in value[1:])
    return value if value in FONT_COLOURS else None
  match = re.match(r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$", value)
  if match and all(int(part) <= 255 for part in match.groups()):
    hexadecimal = "#" + "".join(f"{int(part):02x}" for part in match.groups())
    return hexadecimal if hexadecimal in FONT_COLOURS else None
  return None


def safe_font_style(style: str) -> str:
  """The allowed part of a span's style ("font-family:Georgia, serif;font-size:18px;color:#c0392b"), or ""."""
  kept = {}
  for declaration in (style or "").split(";"):
    name, _, value = declaration.partition(":")
    name, value = name.strip().lower(), value.strip()
    if name == "font-family" and _font_key(value) in _FAMILY_KEYS:
      kept[name] = _FAMILY_KEYS[_font_key(value)]
    elif name == "font-size" and value.lower() in FONT_SIZES:
      kept[name] = value.lower()
    elif name in ("color", "background-color") and _colour(value):
      kept[name] = _colour(value)
  return ";".join(f"{name}:{value}" for name, value in kept.items())


class FormattedCleaner(_Cleaner):
  """The cleaner for the Drupal admin's editors (group emails, signatures, tasks): the contact form's allowlist plus
  <span> with a font, size, text colour or highlight from the lists above."""

  allowed_tags = ALLOWED_TAGS | {"span"}

  def opening(self, tag: str, attributes: dict) -> str | None:
    if tag == "span":
      style = safe_font_style(attributes.get("style") or "")
      # A span with nothing allowed is dropped and its words kept (as for an unsafe link).
      return f'<span style="{escape(style, quote=True)}">' if style else None
    return super().opening(tag, attributes)


def clean_message_html(html: str, cleaner_class: type[_Cleaner] = _Cleaner) -> str:
  cleaner = cleaner_class()
  cleaner.feed(html)
  cleaner.close()
  return "".join(cleaner.parts)


class _TextExtractor(HTMLParser):
  BLOCKS = {"p", "br", "blockquote", "pre", "ul", "ol", "li", "h1", "h2", "h3", "h4", "footer"}

  def __init__(self):
    super().__init__(convert_charrefs=True)
    self.parts: list[str] = []
    self.list_counters: list[int | None] = []

  def handle_starttag(self, tag, attributes):
    if tag == "ol":
      self.list_counters.append(0)
    elif tag == "ul":
      self.list_counters.append(None)
    elif tag == "li":
      self.parts.append("\n")
      if self.list_counters and self.list_counters[-1] is not None:
        self.list_counters[-1] += 1
        self.parts.append(f"{self.list_counters[-1]}. ")
      else:
        self.parts.append("- ")
    elif tag in self.BLOCKS:
      self.parts.append("\n")

  def handle_endtag(self, tag):
    if tag in ("ul", "ol") and self.list_counters:
      self.list_counters.pop()
    if tag in self.BLOCKS and tag != "li":
      self.parts.append("\n")

  def handle_data(self, data):
    self.parts.append(data)


def message_to_text(html: str) -> str:
  """The plain-text version of cleaned message HTML."""
  extractor = _TextExtractor()
  extractor.feed(html)
  extractor.close()
  text = "".join(extractor.parts)
  return re.sub(r"\n{3,}", "\n\n", text).strip()


def check_message(name: str, email: str, phone: str, message_html: str) -> dict:
  """Trims and checks what the visitor typed. Returns the clean values, or raises ContactProblem."""
  name = name.strip()
  email = email.strip()
  phone = phone.strip()
  for label, value in (("name", name), ("email address", email), ("phone number", phone)):
    if "\n" in value or "\r" in value or CONTROL_CHARACTERS.search(value):
      raise ContactProblem(f"Your {label} must be on one line.")
  if not name or len(name) > NAME_LIMIT:
    raise ContactProblem(f"Please enter your full name (up to {NAME_LIMIT} characters).")
  if not email or len(email) > EMAIL_LIMIT or not EMAIL_PATTERN.match(email):
    raise ContactProblem("Please enter a valid email address.")
  if len(phone) > PHONE_LIMIT:
    raise ContactProblem(f"The phone number can be up to {PHONE_LIMIT} characters.")
  if len(message_html) > MESSAGE_HTML_LIMIT:
    raise ContactProblem("The message is too long.")
  cleaned_html = clean_message_html(CONTROL_CHARACTERS.sub("", message_html))
  text = message_to_text(cleaned_html)
  if not text:
    raise ContactProblem("Please enter a message.")
  if len(text) > MESSAGE_TEXT_LIMIT:
    raise ContactProblem(f"The message can be up to {MESSAGE_TEXT_LIMIT} characters.")
  return {"name": name, "email": email, "phone": phone, "html": cleaned_html, "text": text}


def check_rich_text(html: str, html_limit: int, text_limit: int, what: str, cleaner_class: type[_Cleaner] = _Cleaner) -> dict:
  """Cleans text from an editor and checks its size. Returns {"html", "text"} or raises ContactProblem.

  cleaner_class allows more than the contact form's formatting (the site owner's FAQ notes use it)."""
  if len(html) > html_limit:
    raise ContactProblem(f"The {what} is too long.")
  cleaned_html = clean_message_html(CONTROL_CHARACTERS.sub("", html), cleaner_class)
  text = message_to_text(cleaned_html)
  if not text:
    raise ContactProblem(f"Please write something in the {what}.")
  if len(text) > text_limit:
    raise ContactProblem(f"The {what} can be up to {text_limit} characters.")
  return {"html": cleaned_html, "text": text}


def load_mail_settings() -> dict:
  """The email settings from Drupal. DRUSH_COMMAND names drush when it is not the one in drupal/vendor/bin.

  OUTGOING_EMAIL=off stops every email here (contact form, account links, daily devotionals) before the
  settings are read: the containers (docker/) set it, because they hold a copy of real addresses.
  """
  if os.environ.get("OUTGOING_EMAIL", "on").strip().lower() == "off":
    raise MailUnavailable("Outgoing email is turned off here (OUTGOING_EMAIL=off).")
  settings = read_drupal_mail_settings()
  for key in ("smtp_host", "smtp_port", "from_address", "to_address", "subject"):
    if not settings.get(key):
      raise MailUnavailable(f"the email setting {key} is empty")
  return settings


def read_drupal_mail_settings() -> dict:
  """The email settings as Drupal keeps them, unchecked (load_mail_settings checks them before sending)."""
  drush = shlex.split(os.environ.get("DRUSH_COMMAND", "")) or [str(DRUPAL_DIRECTORY / "vendor" / "bin" / "drush")]
  command = [*drush, "php:eval", MAIL_SETTINGS_PHP]
  try:
    completed = subprocess.run(command, cwd=DRUPAL_DIRECTORY, capture_output=True, text=True, timeout=60)
  except (OSError, subprocess.TimeoutExpired) as error:
    raise MailUnavailable(f"drush could not be run: {type(error).__name__}")
  if completed.returncode != 0:
    raise MailUnavailable("drush could not read the email settings")
  try:
    settings = json.loads(completed.stdout.strip().splitlines()[-1])
  except (ValueError, IndexError):
    raise MailUnavailable("the email settings were not understood")
  return settings


def administrator_address() -> str:
  """Where account requests go while "Login required" is on: the Contact email to address of the Site settings
  screen, or '' when it is not set or cannot be read."""
  try:
    return str(read_drupal_mail_settings().get("to_address") or "").strip()
  except MailUnavailable:
    return ""


def build_email(settings: dict, values: dict) -> EmailMessage:
  email = EmailMessage()
  email["Subject"] = settings["subject"]
  email["From"] = settings["from_address"]
  email["To"] = settings["to_address"]
  email["Reply-To"] = f'{values["name"].replace(chr(34), "")} <{values["email"]}>'
  details = [f'Name: {values["name"]}', f'Email: {values["email"]}']
  if values["phone"]:
    details.append(f'Phone: {values["phone"]}')
  email.set_content("\n".join(details) + "\n\n" + values["text"] + "\n")
  detail_html = "".join(f"<p>{escape(line)}</p>" for line in details)
  email.add_alternative(f"<html><body>{detail_html}<hr>{values['html']}</body></html>", subtype="html")
  return email


def closed_addresses(addresses: list[str]) -> set[str]:
  """Which of these addresses (lower case) belong to accounts their owners closed (users.disabled_at; added
  2026-11-17): no email ever goes to them."""
  wanted = sorted({address.strip().lower() for address in addresses if address and address.strip()})
  if not wanted:
    return set()
  from search import connect  # here, not at the top: search is not needed for the contact form's own checks

  with connect() as connection:
    rows = connection.execute("SELECT lower(email) FROM users WHERE disabled_at IS NOT NULL AND lower(email) = ANY(%s)", (wanted,)).fetchall()
  return {row[0] for row in rows}


def send_email(settings: dict, email: EmailMessage, recipients: list[str] | None = None, even_if_closed: bool = False) -> None:
  """Sends one email: to recipients (its real delivery, when that is not who its To shows), else to its To, Cc and
  Bcc. An address of a closed account (closed_addresses) is left out, whichever part of the site sends; with
  nobody left, nothing is sent. even_if_closed is only for the email that tells a member their account was
  closed (accounts.send_goodbye_email), the last one it ever gets."""
  targets = list(recipients) if recipients else [address for _, address in getaddresses(email.get_all("To", []) + email.get_all("Cc", []) + email.get_all("Bcc", []))]
  closed = set() if even_if_closed else closed_addresses(targets)
  if closed:
    targets = [address for address in targets if address.strip().lower() not in closed]
    logger.info("An email was not sent to %d closed account(s).", len(closed))
    if not targets:
      return
    recipients = targets
  host = settings["smtp_host"]
  port = int(settings["smtp_port"])
  authentication = settings.get("smtp_authentication", "login")
  username = settings.get("smtp_username") or ""
  password = settings.get("smtp_password") or ""
  context = ssl.create_default_context()
  try:
    if port == 465:
      connection = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
    else:
      connection = smtplib.SMTP(host, port, timeout=30)
    with connection:
      connection.ehlo()
      if port != 465 and connection.has_extn("starttls"):
        connection.starttls(context=context)
        connection.ehlo()
      if authentication != "none" and username and password:
        if authentication in ("plain", "login", "cram-md5"):
          # Use the method the administrator chose rather than whichever the server lists first.
          connection.esmtp_features["auth"] = authentication.upper()
        connection.login(username, password)
      # recipients: who it is really delivered to, when that is not who its To shows (a group email: To shows the
      # leader, and each member gets it as a hidden recipient, so no member's address is shown; groups.py).
      connection.send_message(email, to_addrs=recipients) if recipients else connection.send_message(email)
  except (OSError, smtplib.SMTPException) as error:
    raise MailUnavailable(f"the message could not be sent: {type(error).__name__}")


def send_contact_message(values: dict) -> None:
  settings = load_mail_settings()
  send_email(settings, build_email(settings, values))


def send_plain_message(to_address: str, subject: str, text: str, even_if_closed: bool = False) -> None:
  """Sends a short plain-text email from the site's address, with the settings kept in Drupal."""
  settings = load_mail_settings()
  email = EmailMessage()
  email["Subject"] = subject
  email["From"] = settings["from_address"]
  email["To"] = to_address
  email.set_content(text)
  send_email(settings, email, even_if_closed=even_if_closed)

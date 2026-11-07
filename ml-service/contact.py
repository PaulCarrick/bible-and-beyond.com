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
from html import escape
from html.parser import HTMLParser
from pathlib import Path

import httpx

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
  return os.environ.get("RECAPTCHA_SITE_KEY", "").strip()


RECAPTCHA_ACTION = "contact"
DEFAULT_MINIMUM_SCORE = 0.5


def verify_recaptcha(token: str, remote_address: str | None) -> None:
  """Raises ContactProblem unless Google says the token is good (reCAPTCHA v3: a score from 0 to 1)."""
  secret = os.environ.get("RECAPTCHA_SECRET_KEY", "").strip()
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
    minimum_score = float(os.environ.get("RECAPTCHA_MINIMUM_SCORE", DEFAULT_MINIMUM_SCORE))
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
    if self.skip_depth or tag not in ALLOWED_TAGS:
      return
    if tag == "br":
      self.parts.append("<br>")
      return
    if tag == "a":
      address = (dict(attributes).get("href") or "").strip()
      if not SAFE_LINK.match(address):
        self.open_tags.append((tag, ""))  # keep the text, drop the link
        return
      self.parts.append(f'<a href="{escape(address, quote=True)}" rel="noopener noreferrer">')
    else:
      self.parts.append(f"<{tag}>")
    self.open_tags.append((tag, f"</{tag}>"))

  def handle_endtag(self, tag):
    if tag in DROPPED_WITH_CONTENT:
      self.skip_depth = max(0, self.skip_depth - 1)
      return
    if self.skip_depth or tag not in ALLOWED_TAGS or tag == "br":
      return
    if any(open_tag == tag for open_tag, _ in self.open_tags):
      while self.open_tags:
        open_tag, closing = self.open_tags.pop()
        self.parts.append(closing)
        if open_tag == tag:
          break

  def handle_data(self, data):
    if not self.skip_depth:
      self.parts.append(escape(data, quote=False))

  def close(self):
    super().close()
    while self.open_tags:
      self.parts.append(self.open_tags.pop()[1])


def clean_message_html(html: str) -> str:
  cleaner = _Cleaner()
  cleaner.feed(html)
  cleaner.close()
  return "".join(cleaner.parts)


class _TextExtractor(HTMLParser):
  BLOCKS = {"p", "br", "blockquote", "pre", "ul", "ol", "li", "h1", "h2", "h3"}

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


def load_mail_settings() -> dict:
  """The email settings from Drupal. DRUSH_COMMAND names drush when it is not the one in drupal/vendor/bin."""
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
  for key in ("smtp_host", "smtp_port", "from_address", "to_address", "subject"):
    if not settings.get(key):
      raise MailUnavailable(f"the email setting {key} is empty")
  return settings


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


def send_email(settings: dict, email: EmailMessage) -> None:
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
      connection.send_message(email)
  except (OSError, smtplib.SMTPException) as error:
    raise MailUnavailable(f"the message could not be sent: {type(error).__name__}")


def send_contact_message(values: dict) -> None:
  settings = load_mail_settings()
  send_email(settings, build_email(settings, values))


def send_plain_message(to_address: str, subject: str, text: str) -> None:
  """Sends a short plain-text email from the site's address, with the settings kept in Drupal."""
  settings = load_mail_settings()
  email = EmailMessage()
  email["Subject"] = subject
  email["From"] = settings["from_address"]
  email["To"] = to_address
  email.set_content(text)
  send_email(settings, email)

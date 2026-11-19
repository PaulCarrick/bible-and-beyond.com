"""Formatted words typed in the Drupal admin's editor (CKEditor 5, text format group_email), for the signatures and
tasks (signatures.py, admin_tasks.py).

What Drupal sends is {"html": ...} from the editor or {"text": ...} from the plain box shown when the editor is
missing. Either way the result is cleaned HTML (the contact form's allowlist, contact.check_rich_text) and its
plain-text copy, ready for an email's HTML and text parts.
"""

from html import escape

from contact import ContactProblem, FormattedCleaner, check_rich_text

HTML_LIMIT = 100_000
TEXT_LIMIT = 20_000


class FormattedTextProblem(Exception):
  """The words cannot be kept; the text says why and is fit to show the administrator."""


def text_to_html(text: str) -> str:
  """Plain text as paragraphs, a single line break kept as <br>."""
  paragraphs = [paragraph.strip() for paragraph in text.replace("\r\n", "\n").split("\n\n")]
  return "".join(f"<p>{escape(paragraph).replace(chr(10), '<br>')}</p>" for paragraph in paragraphs if paragraph)


def clean(value, what: str, required: bool) -> dict:
  """{"html", "text"} from {"html": ...} or {"text": ...} (or None). An empty value gives "" for both, unless
  required. Raises FormattedTextProblem."""
  if value is None:
    value = {}
  if not isinstance(value, dict):
    raise FormattedTextProblem(f"The {what} could not be read.")
  html = value.get("html")
  if html is None:
    text = value.get("text") or ""
    if not isinstance(text, str):
      raise FormattedTextProblem(f"The {what} could not be read.")
    html = text_to_html(text)
  if not isinstance(html, str):
    raise FormattedTextProblem(f"The {what} could not be read.")
  try:
    return check_rich_text(html, HTML_LIMIT, TEXT_LIMIT, what, FormattedCleaner)
  except ContactProblem as problem:
    if not required and str(problem).startswith("Please write something"):
      return {"html": "", "text": ""}
    raise FormattedTextProblem(str(problem)) from problem


def one_line(value, what: str, limit: int) -> str:
  """A required name: plain text on one line, spaces tidied."""
  if not isinstance(value, str):
    raise FormattedTextProblem(f"The {what} is needed.")
  value = " ".join(value.split())
  if not value:
    raise FormattedTextProblem(f"The {what} is needed.")
  if any(ord(character) < 32 or ord(character) == 127 for character in value):
    raise FormattedTextProblem(f"The {what} must be plain text on one line.")
  if len(value) > limit:
    raise FormattedTextProblem(f"The {what} can be at most {limit} characters.")
  return value

"""The site owner's notes on the FAQ answers ("A note from the site owner"), kept in the faq_notes table.

The owner adds, changes and deletes them on the Drupal "FAQ notes" page, which runs scripts/manage_faq_notes.py.
A note belongs to one FAQ question, by its wording (as the stored answers are), so rewording a question in
faq.py leaves its note unused until it is moved to the new wording on that page.

A note is HTML from the editor, cleaned with an allowlist built on the contact form's (contact.py): it also
keeps superscript verse numbers, citations, a quotation's footer, the lang of a Greek or Hebrew word, a
link's description, and links to pages of this site (/?read=... for a verse, /faq?question=... for another
answer, /books?book=... for a book, /search and the other page addresses). Links to a verse, to a book and to
other websites open in a new tab.
"""

import logging
import os
import re
from html import escape
from urllib.parse import parse_qs, urlsplit

from contact import ALLOWED_TAGS, SAFE_LINK, ContactProblem, _Cleaner, check_rich_text, clean_message_html, message_to_text
from faq import QUESTIONS
from search import connect

NOTE_HTML_LIMIT = 200_000
NOTE_TEXT_LIMIT = 20_000
PREVIEW_LENGTH = 160
LABEL_LIMIT = 300

NOTE_TAGS = ALLOWED_TAGS | {"sup", "sub", "cite", "footer", "h4"}
LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$")
# The addresses of this site, so a link copied from the browser (https://bible-and-beyond.com/...) is stored
# as an address on this site and works locally and in the containers too.
SITE_HOSTS = {"bible-and-beyond.com", "www.bible-and-beyond.com"}


class NoteProblem(Exception):
  """A note cannot be saved; the text says why and is fit to show the administrator."""


def _site_hosts() -> set[str]:
  hosts = set(SITE_HOSTS)
  site_host = urlsplit(os.environ.get("SITE_URL", "")).hostname
  if site_host:
    hosts.add(site_host.lower())
  return hosts


def safe_note_address(address: str) -> str | None:
  """The address to keep for a link in a note, or None when it is not safe (the text is kept, the link dropped)."""
  address = address.strip()
  if re.match(r"^https?://", address, re.IGNORECASE):
    parts = urlsplit(address)
    if (parts.hostname or "").lower() in _site_hosts():
      address = (parts.path or "/") + (f"?{parts.query}" if parts.query else "") + (f"#{parts.fragment}" if parts.fragment else "")
    else:
      return address
  if address.startswith("/") and not address.startswith("//") and "\\" not in address:
    return address
  return address if SAFE_LINK.match(address) else None


def opens_in_new_tab(address: str) -> bool:
  """Whether a link on this site opens in a new tab, so the FAQ stays open: a verse (/?read=...) or a book of
  the Other books (/books?book=...)."""
  parts = urlsplit(address)
  query = parse_qs(parts.query)
  return address.startswith("/") and ((parts.path == "/" and "read" in query) or (parts.path == "/books" and "book" in query))


class _NoteCleaner(_Cleaner):
  allowed_tags = NOTE_TAGS
  keeps_non_breaking_spaces = True

  def opening(self, tag: str, attributes: dict) -> str | None:
    language = (attributes.get("lang") or "").strip()
    language_attribute = f' lang="{language}"' if LANGUAGE_PATTERN.match(language) else ""
    if tag != "a":
      return f"<{tag}{language_attribute}>"
    address = safe_note_address(attributes.get("href") or "")
    if address is None:
      return None
    opening = f'<a href="{escape(address, quote=True)}"'
    if not address.startswith("/"):
      opening += ' target="_blank" rel="noopener noreferrer"'
    elif opens_in_new_tab(address):
      opening += ' target="_blank" rel="noopener"'
    label = " ".join((attributes.get("aria-label") or "").split())[:LABEL_LIMIT]
    if label:
      opening += f' aria-label="{escape(label, quote=True)}"'
    return opening + f"{language_attribute}>"


def clean_note_html(html: str) -> str:
  """A note's HTML with only what the allowlist keeps."""
  return clean_message_html(html, _NoteCleaner)


def check_note(html: str) -> dict:
  """Cleans a note and checks its size. Returns {"html", "text"} or raises NoteProblem."""
  try:
    return check_rich_text(html, NOTE_HTML_LIMIT, NOTE_TEXT_LIMIT, "note", _NoteCleaner)
  except ContactProblem as problem:
    raise NoteProblem(str(problem)) from problem


def question_number(question: str) -> int | None:
  for number, listed in QUESTIONS.items():
    if listed == question:
      return number
  return None


def _describe(row) -> dict:
  note_id, question, body, created_at, updated_at = row
  text = " ".join(message_to_text(body).split())
  number = question_number(question)
  return {
    "id": note_id,
    "question": question,
    "question_number": number,
    "is_listed": number is not None,
    "html": body,
    "preview": text if len(text) <= PREVIEW_LENGTH else text[:PREVIEW_LENGTH].rstrip() + "…",
    "created_at": created_at.isoformat(),
    "updated_at": updated_at.isoformat(),
  }


COLUMNS = "id, question, body, created_at, updated_at"


def list_notes() -> list[dict]:
  """Every note, in the order of their questions on the FAQ page; notes on questions no longer listed last."""
  with connect() as connection:
    rows = connection.execute(f"SELECT {COLUMNS} FROM faq_notes").fetchall()
  notes = [_describe(row) for row in rows]
  return sorted(notes, key=lambda note: (note["question_number"] is None, note["question_number"] or 0, note["question"]))


def get_note(note_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {COLUMNS} FROM faq_notes WHERE id = %s", (note_id,)).fetchone()
  if row is None:
    raise NoteProblem("That note does not exist (it may have been deleted).")
  return _describe(row)


def _check_question(question: str, current_question: str | None = None) -> str:
  question = question.strip()
  if question not in QUESTIONS.values() and question != current_question:
    raise NoteProblem("Please choose a question from the FAQ list.")
  return question


def _taken_problem(question: str) -> NoteProblem:
  return NoteProblem(f"The question “{question}” already has a note. Edit that one instead.")


def create_note(question: str, html: str) -> dict:
  question = _check_question(question)
  checked = check_note(html)
  with connect() as connection:
    if connection.execute("SELECT 1 FROM faq_notes WHERE question = %s", (question,)).fetchone():
      raise _taken_problem(question)
    row = connection.execute(
      f"INSERT INTO faq_notes (question, body) VALUES (%s, %s) RETURNING {COLUMNS}", (question, checked["html"])
    ).fetchone()
  return _describe(row)


def update_note(note_id: int, question: str, html: str) -> dict:
  """Replaces a note's text and question. A question no longer on the FAQ list may be kept, not chosen anew."""
  current = get_note(note_id)
  question = _check_question(question, current["question"])
  checked = check_note(html)
  with connect() as connection:
    if connection.execute("SELECT 1 FROM faq_notes WHERE question = %s AND id <> %s", (question, note_id)).fetchone():
      raise _taken_problem(question)
    row = connection.execute(
      f"UPDATE faq_notes SET question = %s, body = %s, updated_at = now() WHERE id = %s RETURNING {COLUMNS}",
      (question, checked["html"], note_id),
    ).fetchone()
  if row is None:
    raise NoteProblem("That note does not exist (it may have been deleted).")
  return _describe(row)


def delete_note(note_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"DELETE FROM faq_notes WHERE id = %s RETURNING {COLUMNS}", (note_id,)).fetchone()
  if row is None:
    raise NoteProblem("That note does not exist (it may have been deleted).")
  return _describe(row)


def note_for_question(question: str) -> str:
  """The note on a question as cleaned HTML, or '' when it has none. Cleaned again here, as a safeguard."""
  with connect() as connection:
    row = connection.execute("SELECT body FROM faq_notes WHERE question = %s", (question,)).fetchone()
  return clean_note_html(row[0]) if row else ""



def owner_note_or_nothing(question: str) -> str:
  """The note for an answer on the FAQ page; '' when there is none or it cannot be read (the answer still shows)."""
  try:
    return note_for_question(question)
  except Exception as error:
    logging.getLogger("faq").warning("Owner's note on an FAQ question not read: %s", error)
    return ""

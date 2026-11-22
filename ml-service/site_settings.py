"""Settings an administrator can change without a deploy, kept in the site_settings table.

The Drupal "Site settings" page changes them through scripts/manage_settings.py, and the public
site reads them here. A missing or invalid value falls back to the default.

Only these are kept here: the numbers for the verse windows, the texts the public pages show (the site
title, the copyright line and the welcome page's first paragraph) and whether a login is required to use
the site at all. The email server settings, which include a password, live
in Drupal and never reach this table or the public API.
"""

import json
import re
from html import escape

from search import connect

# The most verses that can be shown before or after a verse in "Show in Context".
CONTEXT_LIMIT = 50

# Each number setting with the smallest and largest whole number an administrator may choose.
LIMITS = {
  "context_verses_before": (0, CONTEXT_LIMIT),
  "context_verses_after": (0, CONTEXT_LIMIT),
  "related_verses_limit": (1, 50),
}

# Each text setting with the fewest and most characters allowed. The title cannot be empty; the
# copyright line can (then the page shows none).
TEXT_LIMITS = {
  "site_title": (1, 60),
  "copyright_text": (0, 300),
  # Who the site is for, added to the FAQ's instructions to Gemini (faq.site_prompt); empty for none. Never public.
  "faq_about": (0, 2000),
}

# The welcome paragraph is formatted (the admin's editor, so it can have links): cleaned HTML, at most this many
# characters of HTML and of its words.
WELCOME_HTML_LIMIT = 20_000
WELCOME_TEXT_LIMIT = 3_000

# Each yes-or-no setting.
BOOLEANS = {"login_required", "check_posts"}

WELCOME_TEXT = (
  "Bible and Beyond is a free, non-commercial site for reading and studying the Bible. It brings together "
  "public-domain Bibles, the Hebrew and Greek behind the English, cross references, classic commentaries and "
  "devotional books, so that from a single verse you can see what it says in the original languages, what other "
  "verses it points to, and what great teachers have written about it."
)

DEFAULTS = {
  "context_verses_before": 5,
  "context_verses_after": 10,
  "related_verses_limit": 10,
  "site_title": "Bible and Beyond",
  "copyright_text": "Copyright © 2026 by Paul Carrick. All Rights Reserved.",
  # Cleaned HTML (see save_settings); the words the Welcome page had before it could be changed.
  "welcome_text": f"<p>{escape(WELCOME_TEXT)}</p>",
  # When on, only the sign-in pages work until a visitor logs in (main.py require_login).
  "login_required": False,
  "faq_about": "",
  # When on, Gemini checks each new or changed Conversations and Prayer Wall post and reply (post_moderation.py).
  "check_posts": False,
}

# A line of plain text: no line breaks or other control characters.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class SettingsProblem(ValueError):
  """A value is not allowed. The message is written for the administrator."""


def label_of(key):
  return key.replace("_", " ")


def is_valid(key, value):
  if key in BOOLEANS:
    return isinstance(value, bool)
  if key == "welcome_text":
    return isinstance(value, str) and 0 < len(value.strip()) <= WELCOME_HTML_LIMIT
  if key in TEXT_LIMITS:
    smallest, largest = TEXT_LIMITS[key]
    return (
      isinstance(value, str)
      and value == value.strip()
      and smallest <= len(value) <= largest
      and not CONTROL_CHARACTERS.search(value)
    )
  smallest, largest = LIMITS[key]
  return isinstance(value, int) and not isinstance(value, bool) and smallest <= value <= largest


def get_settings():
  with connect() as connection:
    rows = connection.execute(
      "SELECT key, value FROM site_settings WHERE key = ANY(%s)", (list(DEFAULTS),)
    ).fetchall()
  stored = dict(rows)
  settings = {
    key: stored[key] if is_valid(key, stored.get(key)) else default
    for key, default in DEFAULTS.items()
  }
  # Saved as plain text before it had the editor (2026-11-19): shown as a paragraph.
  if not settings["welcome_text"].lstrip().startswith("<"):
    settings["welcome_text"] = f"<p>{escape(settings['welcome_text'])}</p>"
  return settings


def get_public_settings():
  """What the public pages may know: the title, the copyright line, the welcome paragraph and whether a login
  is required, and nothing else."""
  settings = get_settings()
  return {
    "title": settings["site_title"],
    "copyright": settings["copyright_text"],
    "welcome_html": settings["welcome_text"],
    "login_required": settings["login_required"],
  }


def is_login_required():
  return get_settings()["login_required"]


def clean_welcome(value):
  """The welcome paragraph as cleaned HTML, from {"html"}, {"text"} or a plain string. Raises SettingsProblem."""
  from contact import ContactProblem, FormattedCleaner, check_rich_text
  from formatted_text import text_to_html

  if isinstance(value, str):
    value = {"text": value}
  if not isinstance(value, dict):
    raise SettingsProblem("The welcome paragraph could not be read.")
  html = value["html"] if isinstance(value.get("html"), str) else text_to_html(str(value.get("text") or ""))
  try:
    return check_rich_text(html, WELCOME_HTML_LIMIT, WELCOME_TEXT_LIMIT, "welcome paragraph", FormattedCleaner)["html"]
  except ContactProblem as problem:
    raise SettingsProblem(str(problem)) from problem


def save_settings(values):
  """Check every value, then save them all together. Nothing is saved if one is not allowed.

  Text values are trimmed first, so a stray space at either end is not an error. The welcome paragraph comes from
  the admin's editor as {"html": ...} (or {"text": ...} from the plain box shown when the editor is missing; a plain
  string is taken as text too) and is kept as cleaned HTML, the links and formatting of the other editor boxes.
  """
  unknown = [key for key in values if key not in DEFAULTS]
  if unknown:
    raise SettingsProblem(f"Unknown setting: {', '.join(unknown)}.")
  cleaned = {key: value.strip() if isinstance(value, str) else value for key, value in values.items()}
  if "welcome_text" in cleaned:
    cleaned["welcome_text"] = clean_welcome(cleaned["welcome_text"])
  for key, value in cleaned.items():
    if is_valid(key, value):
      continue
    if key in BOOLEANS:
      raise SettingsProblem(f"The {label_of(key)} setting must be on or off.")
    if key in TEXT_LIMITS:
      smallest, largest = TEXT_LIMITS[key]
      if isinstance(value, str) and CONTROL_CHARACTERS.search(value):
        raise SettingsProblem(f"The {label_of(key)} must be one line of plain text.")
      if smallest == 1:
        raise SettingsProblem(f"The {label_of(key)} must be from {smallest} to {largest} characters.")
      raise SettingsProblem(f"The {label_of(key)} can be at most {largest} characters.")
    smallest, largest = LIMITS[key]
    raise SettingsProblem(f"The {label_of(key)} must be a whole number from {smallest} to {largest}.")

  with connect() as connection:
    for key, value in cleaned.items():
      connection.execute(
        """
        INSERT INTO site_settings (key, value) VALUES (%s, %s::jsonb)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (key, json.dumps(value)),
      )
  return get_settings()

"""Settings an administrator can change without a deploy, kept in the site_settings table.

The Drupal "Site settings" page changes them through scripts/manage_settings.py, and the public
site reads them here. A missing or invalid value falls back to the default.

Only these are kept here: the numbers for the verse windows and the two texts the public pages show
(the site title and the copyright line). The email server settings, which include a password, live
in Drupal and never reach this table or the public API.
"""

import json
import re

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
}

DEFAULTS = {
  "context_verses_before": 5,
  "context_verses_after": 10,
  "related_verses_limit": 10,
  "site_title": "Bible and Beyond",
  "copyright_text": "Copyright © 2026 by Paul Carrick. All Rights Reserved.",
}

# A line of plain text: no line breaks or other control characters.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class SettingsProblem(ValueError):
  """A value is not allowed. The message is written for the administrator."""


def label_of(key):
  return key.replace("_", " ")


def is_valid(key, value):
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
  return {
    key: stored[key] if is_valid(key, stored.get(key)) else default
    for key, default in DEFAULTS.items()
  }


def get_public_settings():
  """What the public pages may know: the title and the copyright line, and nothing else."""
  settings = get_settings()
  return {"title": settings["site_title"], "copyright": settings["copyright_text"]}


def save_settings(values):
  """Check every value, then save them all together. Nothing is saved if one is not allowed.

  Text values are trimmed first, so a stray space at either end is not an error.
  """
  unknown = [key for key in values if key not in DEFAULTS]
  if unknown:
    raise SettingsProblem(f"Unknown setting: {', '.join(unknown)}.")
  cleaned = {key: value.strip() if isinstance(value, str) else value for key, value in values.items()}
  for key, value in cleaned.items():
    if is_valid(key, value):
      continue
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

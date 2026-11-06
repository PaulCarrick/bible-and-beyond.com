"""Settings an administrator can change without a deploy, kept in the site_settings table.

The Drupal "Search settings" page changes them through scripts/manage_settings.py, and the
public site reads them here. A missing or invalid value falls back to the default.
"""

from search import connect

# The most verses that can be shown before or after a verse in "Show in Context".
CONTEXT_LIMIT = 50

# Each setting with the smallest and largest whole number an administrator may choose.
LIMITS = {
  "context_verses_before": (0, CONTEXT_LIMIT),
  "context_verses_after": (0, CONTEXT_LIMIT),
  "related_verses_limit": (1, 50),
}

DEFAULTS = {
  "context_verses_before": 5,
  "context_verses_after": 10,
  "related_verses_limit": 10,
}


class SettingsProblem(ValueError):
  """A value is not allowed. The message is written for the administrator."""


def is_valid(key, value):
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


def save_settings(values):
  """Check every value, then save them all together. Nothing is saved if one is not allowed."""
  unknown = [key for key in values if key not in DEFAULTS]
  if unknown:
    raise SettingsProblem(f"Unknown setting: {', '.join(unknown)}.")
  for key, value in values.items():
    if not is_valid(key, value):
      smallest, largest = LIMITS[key]
      label = key.replace("_", " ")
      raise SettingsProblem(f"The {label} must be a whole number from {smallest} to {largest}.")

  with connect() as connection:
    for key, value in values.items():
      connection.execute(
        """
        INSERT INTO site_settings (key, value) VALUES (%s, to_jsonb(%s::int))
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (key, value),
      )
  return get_settings()

"""Verse of the day and Devotional of the day (added 2026-11-16 at the owner's request): two sidebar pages that
show a picture made the same way as the picture messages (message_cards.py), with a Download button.

- The verse is chosen at random each time from the verse a day's well-known verses (verse_a_day.verse_pool and
  pick_verse; the BSB, else the first published Bible stored here).
- The devotional is today's reading (the visitor's own date) of one of the published daily devotionals, chosen
  at random; for one with a morning and an evening reading (Morning and Evening), the morning one until 5 pm
  (the visitor's own hour) and the evening one after.
- The background is one of the verse a day pictures in use, chosen at random, or a plain deep blue when there
  is none.

Every request makes a new picture, sent back inline (a data: address) and never saved, so a busy visitor cannot
fill the server's disk; Download saves that same picture.
"""

import base64
import io
import random
from datetime import date
from functools import lru_cache

import message_cards
import verse_images
import verse_a_day
from devotionals import get_unit
from search import connect

EVENING_HOUR = 17


class DayCardProblem(Exception):
  """Nothing can be shown (no published Bible or devotional); the text is fit for the visitor."""


@lru_cache(maxsize=1)
def _pool() -> tuple:
  # The well-known verses do not change while the service runs; finding them reads every cross reference.
  with connect() as connection:
    return tuple(verse_a_day.verse_pool(connection))


def _picture(words: str, caption: str, chooser) -> str:
  """The card as a data: address (a JPEG)."""
  chosen = verse_images.random_image(chooser)
  background = chosen[1] if chosen else message_cards.plain_background()
  card = message_cards.render(background, words, caption)
  buffer = io.BytesIO()
  card.save(buffer, "JPEG", quality=message_cards.JPEG_QUALITY, optimize=True, progressive=True)
  return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def verse_card(chooser=random) -> dict:
  """A random well-known verse on a random picture."""
  with connect() as connection:
    verse = verse_a_day.pick_verse(connection, list(_pool()), chooser=chooser)
  if verse is None:
    raise DayCardProblem("There is no verse to show yet.")
  caption = f"{verse['reference']} ({verse['translation']})"
  return {
    "words": verse["text"],
    "caption": caption,
    "image": _picture(verse["text"], caption, chooser),
    "verse": {key: verse[key] for key in ("translation", "book", "chapter", "verse")},
  }


def chosen_verse_card(translation: str, book: int, chapter: int, verse: int, chooser=random) -> dict:
  """The card of one verse, as "Download Card" under a search result asks for (added 2026-11-16): its text in
  that Bible, if the Bible is stored here and published (the licensed Bibles never are: their text must not be
  changed or kept), on a random picture."""
  with connect() as connection:
    row = connection.execute(
      """
      SELECT verses.text, books.name, translations.code FROM verses
      JOIN translations ON translations.id = verses.translation_id AND translations.is_published
      JOIN books ON books.number = verses.book_number
      WHERE translations.code = %s AND verses.book_number = %s AND verses.chapter = %s AND verses.verse = %s
      """,
      (translation, book, chapter, verse),
    ).fetchone()
  if row is None:
    raise DayCardProblem("That verse was not found in a Bible on this site.")
  text, book_name, code = row[0].strip(), row[1], row[2]
  caption = f"{book_name} {chapter}:{verse} ({code})"
  return {
    "words": text,
    "caption": caption,
    "image": _picture(text, caption, chooser),
    "verse": {"translation": code, "book": book, "chapter": chapter, "verse": verse},
  }


def _daily_devotionals() -> list[str]:
  with connect() as connection:
    rows = connection.execute(
      "SELECT id FROM devotionals WHERE kind = 'daily' AND is_published AND collection = 'devotionals' ORDER BY id"
    ).fetchall()
  return [row[0] for row in rows]


def devotional_card(today: date, hour: int, chooser=random) -> dict:
  """Today's reading of a daily devotional chosen at random, on a random picture."""
  devotional_ids = _daily_devotionals()
  if not devotional_ids:
    raise DayCardProblem("There is no daily devotional to show yet.")
  devotional_id = chooser.choice(devotional_ids)
  reading = get_unit(devotional_id, today.month, today.day)
  if reading is None or not reading["entries"]:
    raise DayCardProblem("Today's reading could not be found.")
  # Morning and Evening: the evening reading from 5 pm.
  entry = 1 if hour >= EVENING_HOUR and len(reading["entries"]) > 1 else 0
  words, caption = message_cards.devotional_words(reading, entry)
  return {
    "words": words,
    "caption": caption,
    "image": _picture(words, caption, chooser),
    "reading": {
      "devotional": devotional_id,
      "name": reading["devotional"]["name"],
      "section": reading["section"],
      "unit": reading["unit"],
      "title": reading["title"],
      "heading": reading["entries"][entry]["heading"],
    },
  }

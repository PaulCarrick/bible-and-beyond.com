"""Tests for Verse of the day and Devotional of the day (day_cards.py). They read the real Bible and devotionals
and save nothing."""

import base64
import io
import random
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import day_cards
from main import app

client = TestClient(app)


def picture_of(card: dict) -> Image.Image:
  assert card["image"].startswith("data:image/jpeg;base64,")
  return Image.open(io.BytesIO(base64.b64decode(card["image"].split(",", 1)[1])))


def test_the_verse_is_a_well_known_verse_as_a_picture():
  card = day_cards.verse_card(random.Random(1))
  assert picture_of(card).size == (1080, 1350)
  verse = card["verse"]
  assert (verse["book"], verse["chapter"], verse["verse"]) in day_cards._pool()
  assert card["caption"].endswith(f"({verse['translation']})") and card["words"]


def test_the_verse_is_random():
  captions = {day_cards.verse_card(random.Random(seed))["caption"] for seed in range(6)}
  assert len(captions) > 1


def test_the_devotional_is_todays_reading_of_a_published_daily_devotional():
  offered = []

  class Chooser(random.Random):
    def choice(self, options):
      if options and isinstance(options[0], str):
        offered.extend(options)
      return super().choice(options)

  card = day_cards.devotional_card(date(2026, 11, 16), 8, Chooser(2))
  reading = card["reading"]
  assert (reading["section"], reading["unit"], reading["title"]) == (11, 16, "November 16")
  # Chosen from every published daily devotional, none named in the code.
  assert set(offered) == set(day_cards._daily_devotionals()) and reading["devotional"] in offered
  assert picture_of(card).size == (1080, 1350)


def test_the_evening_reading_from_five_oclock():
  morning = day_cards.devotional_card(date(2026, 11, 16), 16, random.Random(3))
  evening = day_cards.devotional_card(date(2026, 11, 16), 17, random.Random(3))
  if morning["reading"]["heading"]:  # a devotional with a morning and an evening reading
    assert morning["reading"]["heading"] == "Morning" and evening["reading"]["heading"] == "Evening"
    assert morning["words"] != evening["words"]


def test_the_endpoints():
  verse = client.get("/day-card/verse")
  assert verse.status_code == 200 and verse.json()["verse"]
  today = date.today()
  devotional = client.get("/day-card/devotional", params={"day": today.isoformat(), "hour": 9})
  assert devotional.status_code == 200 and devotional.json()["reading"]["unit"] == today.day
  # Only today, give or take a day for time zones.
  assert client.get("/day-card/devotional", params={"day": (today + timedelta(days=5)).isoformat()}).status_code == 422
  assert client.get("/day-card/devotional", params={"day": "not a date"}).status_code == 422


def test_without_a_daily_devotional_the_page_says_so(monkeypatch):
  monkeypatch.setattr(day_cards, "_daily_devotionals", lambda: [])
  answer = client.get("/day-card/devotional", params={"day": date.today().isoformat()})
  assert answer.status_code == 404 and "no daily devotional" in answer.json()["detail"]


@pytest.mark.parametrize(
  "text, words, caption",
  [
    ("Fellow citizens with the saints.—EPH. 2:19.\n\nMore.", "Fellow citizens with the saints.", "Eph. 2:19"),
    ("I press toward the mark.—PHI. 3:13,14.\n\nMore.", "I press toward the mark.", "Phi. 3:13,14"),
    ("“The Lord is my portion.”\n\nLamentations 3:24\n\nMore.", "“The Lord is my portion.”", "Lamentations 3:24"),
  ],
)
def test_the_opening_verse_and_reference_are_found(text, words, caption):
  from message_cards import devotional_words

  assert devotional_words({"title": "November 16", "entries": [{"heading": "", "text": text}]}) == (words, caption)

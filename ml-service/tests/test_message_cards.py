"""Tests for picture messages (message_cards.py, "Send Multimedia Messages"). Mail and Telnyx are faked: nothing
is sent. They use the real tables with their own users and pictures, temporary folders (conftest.py), and
remove their rows after."""

import random
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import accounts
import message_cards
import sms
import verse_a_day
import verse_images
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "message-cards-test.example"
client = TestClient(app)


@pytest.fixture(autouse=True)
def outbox(monkeypatch, tmp_path):
  sent = {"emails": [], "texts": []}
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(sms, "is_configured", lambda: True)
  monkeypatch.setattr(sms, "send_text", lambda number, text, media_url=None: sent["texts"].append((number, text, media_url)) or True)
  monkeypatch.setattr(verse_a_day, "load_mail_settings", lambda: {"from_address": "site@example.test"})
  monkeypatch.setattr(verse_a_day, "send_email", lambda settings, email: sent["emails"].append(email))
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")
      connection.execute("DELETE FROM verse_images WHERE id LIKE 'test-mc-%'")

  clear()
  client.cookies.clear()
  yield sent
  clear()


def background(tmp_path, colour=(240, 230, 200), name="light.jpg"):
  path = tmp_path / name
  Image.new("RGB", (1600, 900), colour).save(path, "JPEG")
  return path


def add_picture(tmp_path, image_id="test-mc-light", colour=(240, 230, 200)):
  path = background(tmp_path, colour, image_id + ".jpg")
  return verse_images.upload(path, path.name, image_id, image_id)


def only_ours():
  """A chooser that picks this test's pictures only (the real table may hold the owner's)."""

  class Chooser:
    def choice(self, images):
      return [image for image in images if image["id"].startswith("test-mc-")][0]

  return Chooser()


def register(name="ann", **extra):
  client.cookies.clear()
  response = client.post(
    "/account/register",
    json={"email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD, **extra},
  )
  assert response.status_code == 200, response.text
  user = response.json()["user"]
  with connect() as connection:
    connection.execute("UPDATE users SET email_verified_at = now() WHERE id = %s", (user["id"],))
  return user


def test_a_card_is_a_portrait_jpeg_with_the_words_drawn_over_the_picture(tmp_path):
  plain = background(tmp_path)
  card = message_cards.render(plain, "For God so loved the world.", "John 3:16 (BSB)")
  assert card.size == (message_cards.WIDTH, message_cards.HEIGHT)
  # White words with a dark outline: both are on the card, which a plain picture does not have.
  colours = {colour for _, colour in card.getcolors(maxcolors=1_000_000)}
  assert (255, 255, 255) in colours and any(sum(colour) < 120 for colour in colours)


def test_short_words_are_large_and_long_ones_shrink_or_are_cut():
  size_short, lines_short = message_cards.fit_text("Jesus wept.", 900, 900)
  assert size_short == message_cards.LARGEST_SIZE and lines_short == ["Jesus wept."]
  size_long, lines_long = message_cards.fit_text("word " * 120, 900, 900)
  assert size_long < size_short
  size_cut, lines_cut = message_cards.fit_text("word " * 2000, 900, 900)
  assert size_cut == message_cards.SMALLEST_SIZE and lines_cut[-1].endswith("…")


def test_the_devotional_card_uses_the_opening_verse_and_reference():
  reading = {"title": "November 16", "entries": [{"heading": "Morning", "text": "“The Lord is my portion.”\n\nLamentations 3:24\n\nIt is not..."}]}
  assert message_cards.devotional_words(reading) == ("“The Lord is my portion.”", "Lamentations 3:24")
  chapter = {"title": "Chapter 1", "entries": [{"heading": "", "text": "He that followeth Me walketh not in darkness.\n\nMore."}]}
  assert message_cards.devotional_words(chapter) == ("He that followeth Me walketh not in darkness.", "Chapter 1")


def test_make_card_saves_a_card_served_at_a_random_address(tmp_path):
  add_picture(tmp_path)
  card = message_cards.make_card("Jesus wept.", "John 11:35", only_ours())
  assert card is not None and card.path.is_file() and card.path.stat().st_size < 1_000_000
  assert card.url.startswith("https://site.example/api/message-card/") and card.url.endswith(".jpg")
  name = card.url.rsplit("/", 1)[1]
  response = client.get(f"/message-card/{name}")
  assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
  assert client.get("/message-card/not-a-card.jpg").status_code == 404
  assert client.get("/message-card/..%2Fsecret.jpg").status_code == 404


def test_old_cards_are_removed(tmp_path):
  add_picture(tmp_path)
  card = message_cards.make_card("Jesus wept.", "", only_ours())
  assert message_cards.remove_old_cards(now=time.time() + (message_cards.KEEP_DAYS + 1) * 86400) == 1
  assert not card.path.exists()


def test_no_picture_in_use_means_no_card(tmp_path, monkeypatch):
  monkeypatch.setattr(verse_images, "random_image", lambda chooser=None: None)
  assert message_cards.make_card("Jesus wept.") is None


def test_the_choice_is_saved_and_kept_when_not_sent():
  user = register()
  assert user["send_multimedia"] is False
  changed = client.put("/account/phone", json={"phone": "", "send_multimedia": True}).json()["user"]
  assert changed["send_multimedia"] is True
  # A save that does not mention it leaves it as it is.
  assert client.put("/account/phone", json={"phone": ""}).json()["user"]["send_multimedia"] is True
  assert register("bob", send_multimedia=True)["send_multimedia"] is True


def at(day, hour, minute=0):
  return datetime(2030, 3, day, hour, minute, tzinfo=timezone.utc)


@pytest.mark.parametrize("multimedia", [True, False])
def test_the_verse_a_day_comes_as_a_picture_by_email_and_mms(outbox, tmp_path, monkeypatch, multimedia):
  add_picture(tmp_path)
  real_make_card = message_cards.make_card
  monkeypatch.setattr(message_cards, "make_card", lambda text, caption="", chooser=None: real_make_card(text, caption, only_ours()))
  user = register(phone="555 234 5678", phone_is_cell=True, send_via_sms=True, send_multimedia=multimedia)
  outbox["texts"].clear()
  verse_a_day.save_subscription(user["id"], "07:00", "UTC", now=at(1, 12))
  assert verse_a_day.send_due(at(2, 7, 1), pause=0, chooser=random.Random(5))["sent"] == 1
  email = outbox["emails"][0]
  number, text, media_url = outbox["texts"][0]
  if multimedia:
    assert email.is_multipart()
    html = email.get_body(("html",))
    assert "cid:" in html.get_content()
    pictures = [part for part in email.walk() if part.get_content_type() == "image/jpeg"]
    assert len(pictures) == 1 and pictures[0].get_content()[:3] == b"\xff\xd8\xff"
    # The plain text is still there for mail programs that want it.
    assert "Read it in context" in email.get_body(("plain",)).get_content()
    assert media_url and media_url.startswith("https://site.example/api/message-card/")
    # The picture is a link to the verse.
    assert '<a href="https://site.example/?read=BSB&amp;book=' in html.get_content().split("<img")[0]
  else:
    assert not [part for part in email.walk() if part.get_content_type() == "image/jpeg"] and media_url is None
  assert number == "+15552345678" and "read=BSB" in text


def test_with_no_picture_a_multimedia_member_still_gets_the_plain_verse(outbox, monkeypatch):
  monkeypatch.setattr(message_cards, "make_card", lambda text, caption="", chooser=None: None)
  user = register(send_multimedia=True)
  verse_a_day.save_subscription(user["id"], "07:00", "UTC", now=at(1, 12))
  assert verse_a_day.send_due(at(2, 7, 1), pause=0)["sent"] == 1
  assert not [part for part in outbox["emails"][0].walk() if part.get_content_type() == "image/jpeg"]


def test_the_verse_and_its_reference_are_links_to_the_verse_on_the_site(outbox):
  user = register()
  verse_a_day.save_subscription(user["id"], "07:00", "UTC", now=at(1, 12))
  assert verse_a_day.send_due(at(2, 7, 1), pause=0, chooser=random.Random(5))["sent"] == 1
  email = outbox["emails"][0]
  plain = email.get_body(("plain",)).get_content()
  verse_text, reference = plain.split("\n")[:2]
  link = next(line for line in plain.split("\n") if line.startswith("Read it in context: ")).split(": ", 1)[1]
  html = email.get_body(("html",)).get_content()
  from html import escape

  assert f'<a href="{escape(link)}" style="color:#1d3f8a;">{escape(verse_text)}</a>' in html
  assert f'<a href="{escape(link)}" style="color:#1d3f8a;">{escape(reference)}</a>' in html
  # The other addresses (the stop link) are links too.
  assert html.count("<a href=") >= 4


def test_telnyx_is_sent_the_picture_address(monkeypatch):
  posted = []

  class Taken:
    status_code = 200

  monkeypatch.undo()
  monkeypatch.setattr(sms, "is_configured", lambda: True)
  monkeypatch.setattr(sms, "get_setting", lambda name: {"telnyx_api_key": "KEY", "telnyx_from_number": "+18885550100"}.get(name, ""))
  monkeypatch.setattr(sms.httpx, "post", lambda url, headers, json, timeout: posted.append(json) or Taken())
  assert sms.send_text("+15552345678", "hello", "https://site.example/api/message-card/x.jpg") is True
  assert sms.send_text("+15552345678", "hello") is True
  assert posted[0]["media_urls"] == ["https://site.example/api/message-card/x.jpg"] and "media_urls" not in posted[1]


def test_the_email_text_is_written_as_paragraphs():
  text = "Morning and Evening: November 17\n\nMORNING\n\nFirst paragraph,\nsecond line.\n\nAnother paragraph.\n\n--\nSent by the site: https://site.example/\nTo stop these emails, open: https://site.example/?unsubscribe=T"
  html = message_cards.paragraphs_html(text)
  assert html.count("<p style=\"margin:0 0 14px") == 3
  assert ">MORNING</h3>" in html
  assert "First paragraph,<br>second line." in html
  assert "<hr " in html and "color:#666" in html and '<a href="https://site.example/?unsubscribe=T">' in html
  # A lone signature line with nothing after it does no harm.
  assert "<hr" not in message_cards.paragraphs_html("Hello.\n\n--")

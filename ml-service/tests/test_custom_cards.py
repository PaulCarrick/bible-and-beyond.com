"""Tests for Make your own verse card (custom_cards.py) and the "Created by" line on the verse a day. Mail and
Telnyx are faked: nothing is sent. They use the real tables with their own users and pictures, temporary folders
(conftest.py), and remove their rows after."""

import base64
import random
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import accounts
import custom_cards
import sms
import verse_a_day
import verse_images
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "custom-cards-test.example"
JOHN_3_16 = {"translation": "BSB", "book": 43, "chapter": 3, "verse": 16}
client = TestClient(app)


@pytest.fixture(autouse=True)
def outbox(monkeypatch):
  sent = {"emails": [], "texts": []}
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(sms, "is_configured", lambda: True)
  monkeypatch.setattr(sms, "send_text", lambda number, text, media_url=None: sent["texts"].append((number, text, media_url)) or True)
  settings = lambda: {"from_address": "site@example.test"}
  record = lambda settings, email: sent["emails"].append(email)
  for module in (custom_cards, verse_a_day):
    monkeypatch.setattr(module, "load_mail_settings", settings)
    monkeypatch.setattr(module, "send_email", record)
  monkeypatch.setenv("SITE_URL", "https://site.example")
  custom_cards._sends.clear()

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")
      connection.execute("DELETE FROM verse_images WHERE id LIKE 'test-cc-%'")

  clear()
  client.cookies.clear()
  yield sent
  clear()


def add_picture(tmp_path, image_id="test-cc-sky", in_use=True):
  path = tmp_path / f"{image_id}.jpg"
  Image.new("RGB", (1600, 900), (120, 160, 220)).save(path, "JPEG")
  verse_images.upload(path, path.name, image_id, "Sky")
  if not in_use:
    verse_images.set_in_use(image_id, False)


def register(name, **extra):
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


def card(background="plain", **extra):
  return {**JOHN_3_16, "background": background, **extra}


def test_the_backgrounds_are_the_pictures_in_use_with_thumbnails_and_plain_last(tmp_path):
  add_picture(tmp_path)
  add_picture(tmp_path, "test-cc-hidden", in_use=False)
  found = client.get("/card-backgrounds").json()["backgrounds"]
  ids = [background["id"] for background in found]
  assert "test-cc-sky" in ids and "test-cc-hidden" not in ids
  assert ids[-1] == "plain" and found[-1]["thumbnail"] is None
  ours = next(background for background in found if background["id"] == "test-cc-sky")
  thumbnail = client.get(ours["thumbnail"])
  assert thumbnail.status_code == 200 and thumbnail.headers["content-type"] == "image/webp"
  # A picture out of use is never shown.
  assert client.get("/card-background/test-cc-hidden").status_code == 404


def test_the_preview_is_the_chosen_verse_on_the_chosen_background(tmp_path):
  add_picture(tmp_path)
  for background in ("plain", "test-cc-sky"):
    answer = client.get("/day-card/custom", params=card(background))
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["caption"] == "John 3:16 (BSB)" and body["verse"] == JOHN_3_16
    assert body["image"].startswith("data:image/jpeg;base64,")
    assert base64.b64decode(body["image"].split(",", 1)[1])[:3] == b"\xff\xd8\xff"
  assert client.get("/day-card/custom", params=card("test-cc-nothing")).status_code == 422
  assert client.get("/day-card/custom", params={**card(), "translation": "NIV"}).status_code == 404


def test_only_a_logged_in_member_may_list_people_or_send_and_names_are_shown_never_addresses():
  assert client.get("/card-recipients").status_code == 401
  assert client.post("/day-card/send", json=card(email="someone@example.test")).status_code == 401
  ruth = register("ruth", first_name="Ruth", last_name="Lee")
  register("noname")
  ann = register("ann", first_name="Ann", last_name="Smith")
  people = client.get("/card-recipients").json()["recipients"]
  assert {"id": ruth["id"], "name": "Ruth Lee"} in people
  assert all(set(person) == {"id", "name"} for person in people)
  assert all("@" not in person["name"] for person in people)
  assert ruth["id"] in [person["id"] for person in people] and ann["id"] not in [person["id"] for person in people]


def test_a_card_to_a_site_user_goes_their_way_with_the_sender_and_created_by_line(outbox):
  ruth = register("ruth", first_name="Ruth", last_name="Lee")
  register("ann", first_name="Ann", last_name="Smith")
  answer = client.post("/day-card/send", json=card(recipient_id=ruth["id"]))
  assert answer.status_code == 200, answer.text
  assert answer.json() == {"sent_to": "Ruth Lee", "ways": ["email"]}
  email = outbox["emails"][0]
  assert email["To"] == f"ruth@{DOMAIN}"
  assert email["Reply-To"] == f"ann@{DOMAIN}"
  assert email["Subject"] == "Ann Smith sent you a verse: John 3:16"
  plain = email.get_body(("plain",)).get_content()
  assert plain.startswith("For God so loved the world")
  assert "\nJohn 3:16 (BSB)\n" in plain and "Ann Smith made this card for you" in plain
  last_line = plain.rstrip().split("\n")[-1]
  assert last_line.startswith("Created by ") and last_line.endswith("(https://site.example)")
  html = email.get_body(("html",)).get_content()
  assert '<a href="https://site.example">https://site.example</a>' in html
  # The card is in the email, inline.
  assert any(part.get_content_type() == "image/jpeg" for part in email.walk())


def test_a_site_user_who_chose_texts_gets_the_card_as_a_picture_message(outbox):
  ruth = register("ruth", first_name="Ruth", last_name="Lee", phone="(555) 201-4567", phone_is_cell=True, send_via_sms=True)
  with connect() as connection:
    connection.execute("UPDATE users SET send_via_email = false WHERE id = %s", (ruth["id"],))
  register("ann", first_name="Ann", last_name="Smith")
  answer = client.post("/day-card/send", json=card(recipient_id=ruth["id"]))
  assert answer.status_code == 200, answer.text
  assert answer.json()["ways"] == ["text"]
  (number, text, media_url) = outbox["texts"][-1]
  assert "Ann Smith sent you a verse" in text and media_url.startswith("https://site.example/api/message-card/")


def test_a_card_to_a_typed_address_and_the_checks(outbox):
  ruth = register("ruth", first_name="Ruth", last_name="Lee")
  register("ann", first_name="Ann", last_name="Smith")
  answer = client.post("/day-card/send", json=card(email="friend@example.test"))
  assert answer.status_code == 200, answer.text
  assert answer.json() == {"sent_to": "friend@example.test", "ways": ["email"]}
  assert outbox["emails"][-1]["To"] == "friend@example.test"
  assert client.post("/day-card/send", json=card(email="not an address")).status_code == 422
  assert client.post("/day-card/send", json=card()).status_code == 422
  assert client.post("/day-card/send", json=card(email="friend@example.test", recipient_id=ruth["id"])).status_code == 422
  assert client.post("/day-card/send", json=card(recipient_id=999999999)).status_code == 422


def test_a_member_may_send_only_so_many_cards_a_day(outbox, monkeypatch):
  monkeypatch.setattr(custom_cards, "SENDS_PER_DAY", 2)
  register("ann", first_name="Ann", last_name="Smith")
  # A card that could not go is not counted.
  monkeypatch.setattr(custom_cards, "load_mail_settings", lambda: (_ for _ in ()).throw(custom_cards.MailUnavailable("off")))
  assert client.post("/day-card/send", json=card(email="friend@example.test")).status_code == 503
  monkeypatch.setattr(custom_cards, "load_mail_settings", lambda: {"from_address": "site@example.test"})
  for _ in range(2):
    assert client.post("/day-card/send", json=card(email="friend@example.test")).status_code == 200
  refused = client.post("/day-card/send", json=card(email="friend@example.test"))
  assert refused.status_code == 429 and "tomorrow" in refused.json()["detail"]


def test_the_verse_a_day_email_ends_with_the_created_by_line(outbox):
  user = register("ann", first_name="Ann", last_name="Smith")
  moment = lambda day, hour, minute=0: datetime(2026, 3, day, hour, minute, tzinfo=timezone.utc)
  verse_a_day.save_subscription(user["id"], "07:00", "UTC", now=moment(1, 12))
  assert verse_a_day.send_due(moment(2, 7, 1), pause=0, chooser=random.Random(5))["sent"] == 1
  plain = outbox["emails"][0].get_body(("plain",)).get_content()
  lines = plain.rstrip().split("\n")
  assert lines[-2].startswith("Created by ") and lines[-2].endswith("(https://site.example)")
  assert lines[-1].startswith("To stop these emails")

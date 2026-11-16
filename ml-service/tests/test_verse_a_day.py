"""Tests for the verse a day (verse_a_day.py). Mail and Telnyx are faked: nothing is sent. They use the real verses
and cross references, and remove their own users after."""

import random
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import accounts
import sms
import verse_a_day
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "verse-a-day-test.example"
client = TestClient(app)


@pytest.fixture(autouse=True)
def sent(monkeypatch):
  outbox = {"emails": [], "texts": []}
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(verse_a_day, "load_mail_settings", lambda: {"from_address": "site@example.test"})
  monkeypatch.setattr(verse_a_day, "send_email", lambda settings, email: outbox["emails"].append(email))
  monkeypatch.setattr(sms, "is_configured", lambda: True)
  monkeypatch.setattr(sms, "send_text", lambda number, text: outbox["texts"].append((number, text)) or True)
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield outbox
  clear()


def register(name="ann", **extra):
  client.cookies.clear()
  return client.post(
    "/account/register",
    json={"email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD, **extra},
  )


def confirm(user_id):
  with connect() as connection:
    connection.execute("UPDATE users SET email_verified_at = now() WHERE id = %s", (user_id,))


def at(day, hour, minute=0):
  return datetime(2030, 3, day, hour, minute, tzinfo=timezone.utc)


def test_the_pool_is_well_known_verses_with_text():
  with connect() as connection:
    pool = verse_a_day.verse_pool(connection)
    assert len(pool) == verse_a_day.POOL_SIZE
    assert (23, 41, 10) in pool  # Isaiah 41:10, the most pointed to
    verse = verse_a_day.pick_verse(connection, pool, chooser=random.Random(7))
  assert verse["translation"] == "BSB" and verse["text"] and verse["reference"].endswith(f"{verse['chapter']}:{verse['verse']}")


def test_the_next_day_never_repeats_the_last_verse():
  with connect() as connection:
    pool = verse_a_day.verse_pool(connection)[:2]
    first = verse_a_day.pick_verse(connection, pool, chooser=random.Random(1))
    for seed in range(10):
      assert verse_a_day.pick_verse(connection, pool, avoid=first["key"], chooser=random.Random(seed))["key"] != first["key"]


def test_signing_up_with_a_verse_a_day(sent):
  response = register(verse_a_day=True, verse_time="06:30", timezone="America/Chicago")
  assert response.status_code == 200
  saved = client.get("/verse-subscription").json()["subscription"]
  assert saved["send_time"] == "06:30" and saved["timezone"] == "America/Chicago"
  assert register("bob", verse_a_day=True, verse_time="25:00", timezone="UTC").status_code == 422
  # The bad one made no account.
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM users WHERE email = %s", (f"bob@{DOMAIN}",)).fetchone()[0] == 0


def test_my_account_turns_it_on_changes_and_stops():
  register()
  assert client.get("/verse-subscription").json()["subscription"] is None
  assert client.put("/verse-subscription", json={"send_time": "08:00", "timezone": "UTC"}).json()["subscription"]["send_time"] == "08:00"
  assert client.put("/verse-subscription", json={"send_time": "09:15", "timezone": "UTC"}).json()["subscription"]["send_time"] == "09:15"
  assert client.delete("/verse-subscription").status_code == 200
  assert client.get("/verse-subscription").json()["subscription"] is None
  client.cookies.clear()
  assert client.get("/verse-subscription").status_code == 401


def test_it_is_sent_once_a_day_at_the_members_time_by_email_and_text(sent):
  user_id = register(phone="555 234 5678", phone_is_cell=True, send_via_sms=True).json()["user"]["id"]
  confirm(user_id)
  sent["texts"].clear()  # the welcome text
  verse_a_day.save_subscription(user_id, "07:00", "UTC", now=at(1, 12))
  assert verse_a_day.send_due(at(2, 6, 59), pause=0)["sent"] == 0
  assert verse_a_day.send_due(at(2, 7, 1), pause=0, chooser=random.Random(3))["sent"] == 1
  assert verse_a_day.send_due(at(2, 9), pause=0)["sent"] == 0
  email = sent["emails"][0]
  assert email["Subject"].startswith("Your verse for today: ") and email["To"] == f"ann@{DOMAIN}"
  text = email.get_content()
  assert "(BSB)" in text and "https://site.example/?read=BSB&book=" in text
  assert email["List-Unsubscribe"].startswith("<https://site.example/api/subscriptions/unsubscribe?token=")
  assert sent["texts"][0][0] == "+15552345678" and "read=BSB" in sent["texts"][0][1]
  # The next day, another verse.
  assert verse_a_day.send_due(at(3, 7, 1), pause=0)["sent"] == 1
  assert sent["emails"][1]["Subject"] != email["Subject"]


def test_an_unconfirmed_address_gets_nothing(sent):
  user_id = register().json()["user"]["id"]
  verse_a_day.save_subscription(user_id, "07:00", "UTC", now=at(1, 12))
  assert verse_a_day.send_due(at(2, 7, 1), pause=0)["sent"] == 0 and sent["emails"] == []


def test_the_stop_link_ends_it(sent):
  user_id = register().json()["user"]["id"]
  verse_a_day.save_subscription(user_id, "07:00", "UTC", now=at(1, 12))
  with connect() as connection:
    token = connection.execute("SELECT unsubscribe_token FROM verse_subscriptions WHERE user_id = %s", (user_id,)).fetchone()[0]
  response = client.post("/subscriptions/unsubscribe", params={"token": token})
  assert response.status_code == 200 and response.json()["devotional"] == "the verse a day"
  assert verse_a_day.get_subscription(user_id) is None

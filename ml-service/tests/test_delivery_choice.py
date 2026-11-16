"""Tests for "Send via Email" and "Send via SMS" (users.send_via_email, send_via_sms; migration 041): the choice on
the sign-up form and My account, and the senders following it (sms.deliver). Mail and Telnyx are faked: nothing is
sent. They use the real tables and remove their own users after."""

import random
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import accounts
import conversations
import site_users
import sms
import verse_a_day
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "delivery-choice-test.example"
NUMBER = "+15552345678"
client = TestClient(app)


@pytest.fixture(autouse=True)
def outbox(monkeypatch):
  sent = {"emails": [], "texts": []}
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(sms, "is_configured", lambda: True)
  monkeypatch.setattr(sms, "send_text", lambda number, text: sent["texts"].append((number, text)) or True)
  for module in (verse_a_day, conversations):
    monkeypatch.setattr(module, "load_mail_settings", lambda: {"from_address": "site@example.test"})
    monkeypatch.setattr(module, "send_email", lambda settings, email: sent["emails"].append(email))
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield sent
  clear()


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


def choose(by_email, by_text, phone="555 234 5678", cell=True):
  return client.put(
    "/account/phone", json={"phone": phone, "phone_is_cell": cell, "send_via_email": by_email, "send_via_sms": by_text}
  )


def at(day, hour, minute=0):
  return datetime(2030, 3, day, hour, minute, tzinfo=timezone.utc)


def send_verse(user_id, day):
  verse_a_day.save_subscription(user_id, "07:00", "UTC", now=at(day - 1, 12))
  return verse_a_day.send_due(at(day, 7, 1), pause=0, chooser=random.Random(day))


def test_a_new_account_gets_email_only_unless_it_asks_for_texts(outbox):
  user = register()
  assert user["send_via_email"] is True and user["send_via_sms"] is False
  user = register("bob", phone="555 234 5678", phone_is_cell=True, send_via_sms=True, send_via_email=False)
  assert user["send_via_email"] is False and user["send_via_sms"] is True and user["sms_opt_in"] is True
  assert outbox["texts"][0][0] == NUMBER  # the welcome text


def test_my_account_saves_email_sms_or_both(outbox):
  register()
  for by_email, by_text in ((False, True), (True, True), (True, False)):
    response = choose(by_email, by_text)
    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert (user["send_via_email"], user["send_via_sms"], user["sms_opt_in"]) == (by_email, by_text, by_text)
  # Only one welcome text, when texts were first turned on.
  assert len(outbox["texts"]) == 1


def test_sms_needs_a_number_that_can_be_texted_and_email_stays_on_without_it():
  register()
  response = choose(False, True, phone="+44 20 7946 0958")
  assert response.status_code == 422 and "US or Canadian" in response.json()["detail"]
  # With no phone (or not a cell number) SMS is off, and email is kept on even if it was unticked.
  user = choose(False, True, phone="").json()["user"]
  assert (user["send_via_email"], user["send_via_sms"]) == (True, False)
  user = choose(False, False, cell=False).json()["user"]
  assert (user["send_via_email"], user["send_via_sms"]) == (True, False)


def test_the_database_refuses_no_way_at_all_or_sms_without_a_number():
  user = register()
  with connect() as connection:
    with pytest.raises(Exception):
      connection.execute("UPDATE users SET send_via_email = false WHERE id = %s", (user["id"],))
  with connect() as connection:
    with pytest.raises(Exception):
      connection.execute("UPDATE users SET send_via_sms = true WHERE id = %s", (user["id"],))


@pytest.mark.parametrize("by_email, by_text", [(True, False), (False, True), (True, True)])
def test_the_verse_a_day_goes_the_way_chosen(outbox, by_email, by_text):
  user = register()
  choose(by_email, by_text)
  outbox["texts"].clear()
  assert send_verse(user["id"], 2)["sent"] == 1
  assert len(outbox["emails"]) == int(by_email)
  assert len(outbox["texts"]) == int(by_text)
  if by_text:
    assert outbox["texts"][0][0] == NUMBER and "read=BSB" in outbox["texts"][0][1]


def test_sms_only_falls_back_to_email_when_texts_cannot_go(outbox, monkeypatch):
  user = register()
  choose(False, True)
  outbox["texts"].clear()
  # The member replied STOP: texts stop, the choice stays, and the notices come by email meanwhile.
  with connect() as connection:
    connection.execute("UPDATE users SET sms_opt_in = false, sms_stopped_at = now() WHERE id = %s", (user["id"],))
    assert sms.delivery_for_user(connection, user["id"]) == (True, None)
  assert send_verse(user["id"], 2)["sent"] == 1
  assert len(outbox["emails"]) == 1 and outbox["texts"] == []
  # START brings the texts back, in place of the email.
  sms.handle_webhook(
    b'{"data": {"event_type": "message.received", "payload": {"from": {"phone_number": "+15552345678"}, "text": "START"}}}'
  )
  with connect() as connection:
    assert sms.delivery_for_user(connection, user["id"]) == (False, NUMBER)
  # Texting not set up on this site: email.
  monkeypatch.setattr(sms, "is_configured", lambda: False)
  with connect() as connection:
    assert sms.delivery_for_user(connection, user["id"]) == (True, None)


def test_a_failed_text_for_an_sms_only_member_is_tried_again(outbox, monkeypatch):
  user = register()
  choose(False, True)
  monkeypatch.setattr(sms, "send_text", lambda number, text: False)
  assert send_verse(user["id"], 2)["failed"] == 1
  monkeypatch.setattr(sms, "send_text", lambda number, text: outbox["texts"].append((number, text)) or True)
  outbox["texts"].clear()
  assert verse_a_day.send_due(at(2, 7, 10), pause=0)["sent"] == 1
  assert len(outbox["texts"]) == 1 and outbox["emails"] == []


def test_a_failed_text_beside_an_email_is_not_a_failure(outbox, monkeypatch):
  user = register()
  choose(True, True)
  monkeypatch.setattr(sms, "send_text", lambda number, text: False)
  assert send_verse(user["id"], 2)["sent"] == 1 and len(outbox["emails"]) == 1


def test_a_reply_notice_goes_the_way_the_author_chose(outbox):
  author = register("ann")
  choose(False, True)
  with connect() as connection:
    connection.execute("UPDATE users SET use_conversations = true WHERE email LIKE %s", (f"%@{DOMAIN}",))
  post = client.post("/conversations", json={"title": "Grace", "body": "<p>x</p>", "email_replies": True}).json()["post"]
  register("bob")
  with connect() as connection:
    connection.execute("UPDATE users SET use_conversations = true WHERE email = %s", (f"bob@{DOMAIN}",))
  outbox["texts"].clear()
  assert client.post(f"/conversations/{post['id']}/replies", json={"body": "<p>Amen</p>"}).status_code == 200
  assert outbox["emails"] == []
  assert len(outbox["texts"]) == 1 and outbox["texts"][0][0] == NUMBER and "replied to “Grace”" in outbox["texts"][0][1]
  assert author["id"]


def test_an_administrator_changing_the_number_turns_sms_off_and_email_on():
  user = register()
  choose(False, True)
  changed = site_users.update_user(user["id"], phone="555-987-6543")
  assert changed["sms_opt_in"] is False
  with connect() as connection:
    assert connection.execute("SELECT send_via_email, send_via_sms FROM users WHERE id = %s", (user["id"],)).fetchone() == (True, False)


def test_account_emails_ignore_the_choice(monkeypatch):
  register()
  choose(False, True)
  emails = []
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: emails.append(address))
  client.cookies.clear()
  assert client.post("/account/forgot-password", json={"email": f"ann@{DOMAIN}"}).status_code == 200
  assert emails == [f"ann@{DOMAIN}"]

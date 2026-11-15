"""Tests for text messages (sms.py). Telnyx is faked: nothing is sent. They use the real tables and remove their own
users after."""

import base64
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

import accounts
import prayer_list
import site_users
import sms
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "sms-test.example"
client = TestClient(app)
PRIVATE_KEY = Ed25519PrivateKey.generate()
PUBLIC_KEY = base64.b64encode(PRIVATE_KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
SETTINGS = {"telnyx_api_key": "KEY", "telnyx_from_number": "+18885550100", "telnyx_public_key": PUBLIC_KEY}


@pytest.fixture(autouse=True)
def texts(monkeypatch):
  sent = []
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(sms, "get_setting", lambda name: SETTINGS.get(name, ""))
  monkeypatch.setattr(sms, "send_text", lambda number, text: sent.append((number, text)) or True)
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield sent
  clear()


def register(name="ann", phone="555 234 5678", cell=True, texts=True):
  client.cookies.clear()
  response = client.post(
    "/account/register",
    json={
      "email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD,
      "first_name": name.title(), "last_name": "Test", "phone": phone, "phone_is_cell": cell, "sms_opt_in": texts,
    },
  )
  return response


def confirm(user_id):
  with connect() as connection:
    connection.execute("UPDATE users SET email_verified_at = now() WHERE id = %s", (user_id,))


@pytest.mark.parametrize(
  "typed, number, shown",
  [
    ("555-234-5678", "+15552345678", "+1 (555) 234-5678"),
    ("(555) 234 5678", "+15552345678", "+1 (555) 234-5678"),
    ("1 555 234 5678", "+15552345678", "+1 (555) 234-5678"),
    ("+1 (555) 234-5678", "+15552345678", "+1 (555) 234-5678"),
    ("+44 20 7946 0958", None, "+44 20 7946 0958"),
    ("555-1234", None, "555-1234"),
    ("055-234-5678", None, "055-234-5678"),
  ],
)
def test_numbers_are_read_and_written_the_us_way(typed, number, shown):
  assert sms.texting_number(typed) == number
  assert sms.format_phone(typed) == shown


def test_signing_up_with_texts_keeps_the_choice_and_sends_a_welcome_text(texts):
  response = register()
  assert response.status_code == 200
  user = response.json()["user"]
  assert user["phone"] == "+1 (555) 234-5678" and user["phone_is_cell"] and user["sms_opt_in"] and not user["sms_stopped"]
  assert texts[0][0] == "+15552345678" and "Reply STOP" in texts[0][1] and "rates may apply" in texts[0][1]


def test_texts_need_a_cell_number_that_can_be_texted(texts):
  assert register("ann", cell=False).json()["user"]["sms_opt_in"] is False
  response = register("bob", phone="+44 20 7946 0958")
  assert response.status_code == 422 and "US or Canadian" in response.json()["detail"]
  assert texts == []


def test_my_account_turns_texts_on_and_off(texts):
  register(texts=False)
  user = client.put("/account/phone", json={"phone": "5552345678", "phone_is_cell": True, "sms_opt_in": True}).json()["user"]
  assert user["sms_opt_in"] and user["phone"] == "+1 (555) 234-5678" and len(texts) == 1
  # Saving again with no change sends no second welcome.
  client.put("/account/phone", json={"phone": "5552345678", "phone_is_cell": True, "sms_opt_in": True})
  assert len(texts) == 1
  user = client.put("/account/phone", json={"phone": "5552345678", "phone_is_cell": True, "sms_opt_in": False}).json()["user"]
  assert user["sms_opt_in"] is False
  client.cookies.clear()
  assert client.put("/account/phone", json={"phone": "", "phone_is_cell": False, "sms_opt_in": False}).status_code == 401


def signed(event: dict, when: float | None = None) -> tuple[bytes, dict]:
  body = json.dumps({"data": event}).encode()
  timestamp = str(int(when or time.time()))
  signature = base64.b64encode(PRIVATE_KEY.sign(f"{timestamp}|".encode() + body)).decode()
  return body, {"telnyx-signature-ed25519": signature, "telnyx-timestamp": timestamp, "content-type": "application/json"}


def reply_event(text, number="+15552345678"):
  return {"event_type": "message.received", "payload": {"from": {"phone_number": number}, "text": text}}


def test_stop_start_and_help_replies(texts):
  user_id = register().json()["user"]["id"]
  texts.clear()
  body, headers = signed(reply_event("Stop"))
  assert client.post("/sms/webhook", content=body, headers=headers).json() == {"done": "stopped"}
  with connect() as connection:
    assert connection.execute("SELECT sms_opt_in, sms_stopped_at IS NOT NULL FROM users WHERE id = %s", (user_id,)).fetchone() == (False, True)
  assert "no more texts" in texts[-1][1]

  body, headers = signed(reply_event("START"))
  assert client.post("/sms/webhook", content=body, headers=headers).json() == {"done": "started"}
  with connect() as connection:
    assert connection.execute("SELECT sms_opt_in, sms_stopped_at IS NULL FROM users WHERE id = %s", (user_id,)).fetchone() == (True, True)

  body, headers = signed(reply_event("help"))
  assert client.post("/sms/webhook", content=body, headers=headers).json() == {"done": "help"}
  assert "Reply STOP" in texts[-1][1]


def test_start_does_not_turn_on_texts_for_someone_who_never_asked(texts):
  register(texts=False)
  body, headers = signed(reply_event("START"))
  assert client.post("/sms/webhook", content=body, headers=headers).json() == {"done": "unknown"}


def test_an_unsigned_or_old_webhook_is_refused():
  body, headers = signed(reply_event("STOP"))
  assert client.post("/sms/webhook", content=body, headers={**headers, "telnyx-signature-ed25519": "bad"}).status_code == 401
  body, headers = signed(reply_event("STOP"), when=time.time() - 3600)
  assert client.post("/sms/webhook", content=body, headers=headers).status_code == 401


def test_telnyx_refusing_a_stopped_number_turns_texts_off(monkeypatch):
  user_id = register().json()["user"]["id"]
  monkeypatch.undo()
  monkeypatch.setattr(sms, "get_setting", lambda name: SETTINGS.get(name, ""))

  class Refused:
    status_code = 400

    def json(self):
      return {"errors": [{"code": "40300", "title": "Blocked due to STOP message"}]}

  monkeypatch.setattr(sms.httpx, "post", lambda *arguments, **options: Refused())
  assert sms.send_text("+15552345678", "hello") is False
  with connect() as connection:
    assert connection.execute("SELECT sms_opt_in FROM users WHERE id = %s", (user_id,)).fetchone()[0] is False


def test_the_prayer_list_is_texted_as_well_as_emailed(texts, monkeypatch):
  emails = []
  monkeypatch.setattr(prayer_list, "load_mail_settings", lambda: {"from_address": "site@example.test"})
  monkeypatch.setattr(prayer_list, "send_email", lambda settings, email: emails.append(email))
  reader = register("ruth").json()["user"]["id"]
  confirm(reader)
  friday_noon = datetime(2030, 3, 1, 12, tzinfo=timezone.utc)
  prayer_list.save_subscription(reader, 5, "07:00", "UTC", now=friday_noon)
  register("ann", texts=False)
  with connect() as connection:
    connection.execute("UPDATE users SET use_conversations = true WHERE email = %s", (f"ann@{DOMAIN}",))
  post = client.post("/conversations", json={"title": "Travel", "body": "<p>x</p>", "board": "prayer", "email_to_prayer_list": True}).json()["post"]
  with connect() as connection:
    connection.execute("UPDATE conversation_posts SET listed_at = %s WHERE id = %s", (friday_noon + timedelta(hours=1), post["id"]))
  texts.clear()
  assert prayer_list.send_due(datetime(2030, 3, 2, 7, 1, tzinfo=timezone.utc), pause=0)["sent"] == 1
  assert len(emails) == 1 and len(texts) == 1
  assert texts[0][0] == "+15552345678" and "1 new prayer request this week: Travel." in texts[0][1] and "/prayer-wall" in texts[0][1]


def test_an_unconfirmed_address_gets_no_texts(texts):
  user_id = register().json()["user"]["id"]
  texts.clear()
  assert sms.text_user(user_id, "hello") is False
  confirm(user_id)
  assert sms.text_user(user_id, "hello") is True


def test_a_long_text_is_cut():
  text = sms.compose("word " * 200, "https://site.example/x")
  assert len(text) <= sms.TEXT_LIMIT and text.endswith("https://site.example/x Reply STOP to end texts.")


def test_an_administrator_changing_the_number_turns_texts_off_but_rewriting_it_does_not():
  user_id = register().json()["user"]["id"]
  assert site_users.update_user(user_id, phone="555.234.5678")["sms_opt_in"] is True
  assert site_users.get_user(user_id)["phone"] == "+1 (555) 234-5678"
  assert site_users.update_user(user_id, phone="555-987-6543")["sms_opt_in"] is False

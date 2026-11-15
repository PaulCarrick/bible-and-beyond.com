"""Tests for "Email me replies" on Conversations posts. The mail server is faked: nothing is sent. They use the
real tables and remove their own users (and so their posts) after."""

import pytest
from fastapi.testclient import TestClient

import accounts
import conversations
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "reply-emails-test.example"
client = TestClient(app)
SETTINGS = {"smtp_host": "x", "smtp_port": 25, "from_address": "site@example.test", "to_address": "o@example.test", "subject": "s"}


@pytest.fixture(autouse=True)
def sent(monkeypatch):
  emails = []
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(conversations, "load_mail_settings", lambda: SETTINGS)
  monkeypatch.setattr(conversations, "send_email", lambda settings, email: emails.append(email))
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield emails
  clear()


def sign_up(name, verified=True):
  client.cookies.clear()
  response = client.post(
    "/account/register",
    json={"email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD, "first_name": name.title(), "last_name": "Test"},
  )
  user_id = response.json()["user"]["id"]
  with connect() as connection:
    connection.execute(
      "UPDATE users SET use_conversations = true, email_verified_at = CASE WHEN %s THEN now() END WHERE id = %s", (verified, user_id)
    )
  return user_id


def log_in(name):
  client.cookies.clear()
  assert client.post("/account/login", json={"email": f"{name}@{DOMAIN}", "password": PASSWORD}).status_code == 200


def write_post(title="Grace", **options):
  response = client.post("/conversations", json={"title": title, "body": "<p>On grace</p>", **options})
  assert response.status_code == 200, response.text
  return response.json()["post"]


def reply(post_id, text="<p>Amen to that</p>"):
  response = client.post(f"/conversations/{post_id}/replies", json={"body": text})
  assert response.status_code == 200, response.text


def test_a_reply_is_emailed_to_the_author_who_asked(sent):
  sign_up("ann")
  post = write_post(email_replies=True)
  assert post["email_replies"] is True
  sign_up("bob")
  # Others are not told whether the author gets replies by email.
  assert client.get("/conversations").json()["posts"][0]["email_replies"] is False
  reply(post["id"], "<p>Amen to <strong>that</strong></p>")

  assert len(sent) == 1
  email = sent[0]
  assert email["To"] == f"ann@{DOMAIN}" and email["Subject"] == "New reply to your post “Grace”"
  text = email.get_content()
  assert "Bob Test replied" in text and "Amen to that" in text and "https://site.example/conversations" in text
  assert email["List-Unsubscribe"].startswith("<https://site.example/api/subscriptions/unsubscribe?token=")


def test_nothing_is_sent_when_not_asked_for_or_to_oneself_or_to_an_unconfirmed_address(sent):
  sign_up("ann")
  quiet = write_post("Quiet")
  asked = write_post("Asked", email_replies=True)
  reply(asked["id"])  # the author's own reply
  sign_up("bob")
  reply(quiet["id"])
  assert sent == []

  sign_up("cara", verified=False)
  unconfirmed = write_post("Unconfirmed", email_replies=True)
  log_in("bob")
  reply(unconfirmed["id"])
  assert sent == []


def test_the_choice_can_be_changed_with_edit(sent):
  sign_up("ann")
  post = write_post()
  changed = client.put(f"/conversations/{post['id']}", json={"title": "Grace", "body": "<p>x</p>", "email_replies": True}).json()["post"]
  assert changed["email_replies"] is True
  sign_up("bob")
  reply(post["id"])
  assert len(sent) == 1
  log_in("ann")
  client.put(f"/conversations/{post['id']}", json={"title": "Grace", "body": "<p>x</p>", "email_replies": False})
  log_in("bob")
  reply(post["id"])
  assert len(sent) == 1


def test_the_stop_link_turns_it_off(sent):
  sign_up("ann")
  post = write_post(email_replies=True)
  with connect() as connection:
    token = connection.execute("SELECT reply_email_token FROM conversation_posts WHERE id = %s", (post["id"],)).fetchone()[0]
  response = client.post("/subscriptions/unsubscribe", params={"token": token})
  assert response.status_code == 200 and response.json()["devotional"] == "replies to your post “Grace”"
  sign_up("bob")
  reply(post["id"])
  assert sent == []


def test_prayer_wall_posts_cannot_ask_for_it():
  sign_up("ann")
  response = client.post("/conversations", json={"title": "x", "body": "<p>x</p>", "board": "prayer", "email_replies": True})
  assert response.status_code == 422


def test_a_mail_failure_does_not_stop_the_reply(sent, monkeypatch):
  def fail(settings, email):
    raise conversations.MailUnavailable("down")

  monkeypatch.setattr(conversations, "send_email", fail)
  sign_up("ann")
  post = write_post(email_replies=True)
  sign_up("bob")
  reply(post["id"])
  log_in("ann")
  assert len(client.get("/conversations").json()["posts"][0]["replies"]) == 1

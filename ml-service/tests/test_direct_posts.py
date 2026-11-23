"""Tests for posts to one member (direct_posts.py): the first post asks the member to accept or decline, held
posts show once accepted, a decline stops the sender, and the answer can change. Mail is faked; real tables, their
own @direct-posts-test.example accounts."""

import pytest
from fastapi.testclient import TestClient

import accounts
import conversations
import direct_posts
import post_moderation
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "direct-posts-test.example"
client = TestClient(app)
SETTINGS = {"smtp_host": "x", "smtp_port": 25, "from_address": "site@example.test", "to_address": "o@example.test", "subject": "s"}


@pytest.fixture(autouse=True)
def mailbox(monkeypatch):
  sent = []
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  for module in (conversations, direct_posts):
    monkeypatch.setattr(module, "load_mail_settings", lambda: SETTINGS)
    monkeypatch.setattr(module, "send_email", lambda settings, email, recipients=None: sent.append(email))
  checked = []
  monkeypatch.setattr(post_moderation, "check", lambda text, title="", board="conversations", what="post": checked.append(text))

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield {"sent": sent, "checked": checked}
  clear()


def sign_up(name, watcher=False):
  client.cookies.clear()
  response = client.post(
    "/account/register",
    json={"email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD, "first_name": name.title(), "last_name": "Test"},
  )
  user_id = response.json()["user"]["id"]
  with connect() as connection:
    connection.execute(
      "UPDATE users SET use_conversations = true, email_verified_at = now(), get_conversation_posts = %s, conversation_posts_token = 'tok-' || id WHERE id = %s",
      (watcher, user_id),
    )
  return user_id


def log_in(name):
  client.cookies.clear()
  assert client.post("/account/login", json={"email": f"{name}@{DOMAIN}", "password": PASSWORD}).status_code == 200


def send(to, title="Hello", body="<p>Just for you</p>"):
  return client.post("/conversations", json={"title": title, "body": body, "recipient_id": to})


def titles():
  return [post["title"] for post in client.get("/conversations").json()["posts"]]


def test_the_first_post_asks_and_is_held_until_accepted(mailbox):
  ruth = sign_up("ruth")
  sign_up("watcher", watcher=True)
  paul = sign_up("paul")
  assert any(member["id"] == ruth for member in client.get("/conversations/members").json()["members"])
  posted = send(ruth)
  assert posted.status_code == 200
  post = posted.json()["post"]
  assert post["recipient"]["name"] == "Ruth Test" and post["delivery"] == "pending"
  assert mailbox["checked"] == []  # a private post never goes to the AI check
  # One email: the request to Ruth (not the post's words, and nothing to Get Conversation Posts).
  assert len(mailbox["sent"]) == 1 and mailbox["sent"][0]["To"] == f"ruth@{DOMAIN}"
  request_text = mailbox["sent"][0].get_content()
  assert "Paul Test would like to send you private posts" in request_text and "Just for you" not in request_text
  assert "message-request=" in request_text
  # A second post while waiting: no second request.
  send(ruth, "Again")
  assert len(mailbox["sent"]) == 1
  assert titles()[:2] == ["Again", "Hello"]  # the author sees their own

  log_in("ruth")
  assert "Hello" not in titles()  # held
  waiting = client.get("/message-requests").json()["requests"]
  assert [(item["sender_id"], item["sender"]) for item in waiting] == [(paul, "Paul Test")]
  assert client.put(f"/message-permissions/{paul}", json={"accept": True}).json()["permission"]["status"] == "accepted"
  assert {"Hello", "Again"} <= set(titles())
  assert client.get("/message-requests").json()["requests"] == []

  # Others never see it.
  log_in("watcher")
  assert "Hello" not in titles()
  client.cookies.clear()
  assert "Hello" not in titles()

  # After accepting: the next post arrives with a note, never another request; replies tell the other one.
  mailbox["sent"].clear()
  log_in("paul")
  third = send(ruth, "Third").json()["post"]
  assert len(mailbox["sent"]) == 1 and mailbox["sent"][0]["Subject"] == "New post from Paul Test: “Third”"
  log_in("ruth")
  mailbox["sent"].clear()
  assert client.post(f"/conversations/{third['id']}/replies", json={"body": "<p>Thank you</p>"}).status_code == 200
  assert [email["To"] for email in mailbox["sent"]] == [f"paul@{DOMAIN}"]
  log_in("watcher")
  assert client.post(f"/conversations/{third['id']}/replies", json={"body": "<p>Me too</p>"}).status_code == 404


def test_a_decline_stops_the_sender_and_can_be_changed(mailbox):
  ruth = sign_up("ruth")
  paul = sign_up("paul")
  send(ruth)
  token = mailbox["sent"][0].get_content().split("message-request=")[1].split()[0]
  client.cookies.clear()
  # The link works without logging in.
  shown = client.get("/message-request", params={"token": token}).json()["request"]
  assert (shown["sender"], shown["status"], shown["recipient_first_name"]) == ("Paul Test", "pending", "Ruth")
  assert client.post("/message-request", json={"token": token, "accept": False}).json()["permission"]["status"] == "declined"
  assert client.get("/message-request", params={"token": "nonsense"}).status_code == 404

  log_in("paul")
  refused = send(ruth, "Once more")
  assert refused.status_code == 403 and "not accepting posts from you" in refused.json()["detail"]
  assert client.get("/conversations").json()["posts"][0]["delivery"] == "declined"
  log_in("ruth")
  assert "Hello" not in titles()
  assert [item["status"] for item in client.get("/message-permissions").json()["permissions"]] == ["declined"]
  # Changed on My account: the held post shows, and Paul may send again.
  client.put(f"/message-permissions/{paul}", json={"accept": True})
  assert "Hello" in titles()
  log_in("paul")
  assert send(ruth, "Once more").status_code == 200


def test_refusals(mailbox):
  ruth = sign_up("ruth")
  me = sign_up("paul")
  assert send(me).status_code == 422
  assert send(999999999).status_code == 422
  prayer = client.post("/conversations", json={"title": "x", "body": "<p>x</p>", "board": "prayer", "recipient_id": ruth})
  assert prayer.status_code == 422
  with connect() as connection:
    connection.execute("UPDATE users SET use_conversations = false WHERE id = %s", (ruth,))
  assert send(ruth).status_code == 422
  assert all(member["id"] != ruth for member in client.get("/conversations/members").json()["members"])

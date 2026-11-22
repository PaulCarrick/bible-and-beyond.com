"""Tests for Get Conversation Posts: accounts with the flag are emailed every new Conversations post and reply. The
mail server is faked: nothing is sent. They use the real tables and remove their own users (and so their posts)."""

import pytest
from fastapi.testclient import TestClient

import accounts
import conversations
import site_users
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "conversation-posts-test.example"
client = TestClient(app)
SETTINGS = {"smtp_host": "x", "smtp_port": 25, "from_address": "site@example.test", "to_address": "o@example.test", "subject": "s"}


@pytest.fixture(autouse=True)
def sent(monkeypatch):
  emails = []
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(conversations, "load_mail_settings", lambda: SETTINGS)
  monkeypatch.setattr(conversations, "send_email", lambda settings, email: emails.append(email))
  monkeypatch.setattr(conversations, "WATCHER_EMAIL_PAUSE_SECONDS", 0)
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield emails
  clear()


def sign_up(name, verified=True, gets_posts=False):
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
  if gets_posts:
    # As the Drupal Site users page does it.
    site_users.update_user(user_id, get_conversation_posts=True)
  return user_id


def log_in(name):
  client.cookies.clear()
  assert client.post("/account/login", json={"email": f"{name}@{DOMAIN}", "password": PASSWORD}).status_code == 200


def write_post(title="Grace", **options):
  response = client.post("/conversations", json={"title": title, "body": "<p>On <strong>grace</strong></p>", **options})
  assert response.status_code == 200, response.text
  return response.json()["post"]


def reply(post_id, text="<p>Amen to that</p>"):
  response = client.post(f"/conversations/{post_id}/replies", json={"body": text})
  assert response.status_code == 200, response.text


def to(emails):
  return sorted(email["To"] for email in emails)


def test_a_new_post_and_a_new_reply_are_emailed_to_each_account_with_the_flag(sent):
  sign_up("watcher", gets_posts=True)
  sign_up("other", gets_posts=True)
  sign_up("plain")  # no flag: never emailed
  sign_up("ann")
  post = write_post()

  assert to(sent) == [f"other@{DOMAIN}", f"watcher@{DOMAIN}"]
  email = sent[0]
  assert email["Subject"] == "New post in Conversations: “Grace”"
  text = email.get_content()
  assert "Ann Test posted in Conversations:" in text and "Grace" in text and "On grace" in text
  assert "https://site.example/conversations" in text and "Get Conversation Posts" in text
  assert email["List-Unsubscribe"].startswith("<https://site.example/api/subscriptions/unsubscribe?token=")
  # Each one has its own stop link.
  assert sent[0]["List-Unsubscribe"] != sent[1]["List-Unsubscribe"]

  sent.clear()
  sign_up("bob")
  reply(post["id"], "<p>Amen to <em>that</em></p>")
  assert to(sent) == [f"other@{DOMAIN}", f"watcher@{DOMAIN}"]
  assert sent[0]["Subject"] == "New reply in Conversations: “Grace”"
  assert "Bob Test replied to “Grace” in Conversations:" in sent[0].get_content() and "Amen to that" in sent[0].get_content()


def test_not_to_the_writer_an_unconfirmed_or_closed_account_or_for_the_prayer_wall(sent):
  sign_up("unconfirmed", verified=False, gets_posts=True)
  closed = sign_up("closed", gets_posts=True)
  with connect() as connection:
    connection.execute("UPDATE users SET disabled_at = now() WHERE id = %s", (closed,))
  sign_up("watcher", gets_posts=True)
  post = write_post()  # by the watcher: not to themself
  assert sent == []
  write_post("Please pray", board="prayer")
  assert sent == []
  reply(post["id"])  # their own reply
  assert sent == []


def test_a_post_author_who_gets_replies_already_is_not_sent_it_twice(sent):
  sign_up("ann", gets_posts=True)
  post = write_post(email_replies=True)
  sign_up("bob")
  reply(post["id"])
  # Ann gets the "Email me replies" email only.
  assert len(sent) == 1 and sent[0]["Subject"] == "New reply to your post “Grace”"


def test_the_stop_link_turns_the_flag_off(sent):
  watcher = sign_up("watcher", gets_posts=True)
  sign_up("ann")
  write_post()
  token = sent[0]["List-Unsubscribe"].split("token=")[1].rstrip(">")
  response = client.post("/subscriptions/unsubscribe", params={"token": token})
  assert response.status_code == 200 and response.json()["devotional"] == "new Conversations posts and replies"
  assert site_users.get_user(watcher)["get_conversation_posts"] is False

  sent.clear()
  write_post("Again")
  assert sent == []
  # Ticked again on Site users, the same link works again.
  site_users.update_user(watcher, get_conversation_posts=True)
  write_post("Once more")
  assert len(sent) == 1 and sent[0]["List-Unsubscribe"].endswith(f"token={token}>")


def test_a_mail_failure_does_not_stop_the_post(sent, monkeypatch):
  def fail(settings, email):
    raise conversations.MailUnavailable("down")

  monkeypatch.setattr(conversations, "send_email", fail)
  sign_up("watcher", gets_posts=True)
  sign_up("ann")
  write_post()
  assert len(client.get("/conversations").json()["posts"]) >= 1


def test_the_users_tool_sets_and_shows_the_flag():
  import json
  import subprocess
  import sys
  from pathlib import Path

  tool = Path(__file__).resolve().parent.parent / "scripts" / "manage_users.py"

  def run(*arguments, password=None):
    answer = subprocess.run([sys.executable, str(tool), *arguments], input=password, capture_output=True, text=True)
    return json.loads(answer.stdout)

  made = run("create", f"--email=tool@{DOMAIN}", "--get-conversation-posts", "--password-on-input", password=PASSWORD + "\n")
  assert made["ok"] and made["user"]["get_conversation_posts"] is True
  changed = run("update", f"--id={made['user']['id']}", "--get-conversation-posts=no")
  assert changed["user"]["get_conversation_posts"] is False

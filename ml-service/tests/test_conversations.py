"""Tests for Conversations. They use the real tables and remove their own users (and so their posts) after."""

import pytest
from fastapi.testclient import TestClient

import accounts
import conversations
from main import app
from search import connect

PASSWORD = "correct horse battery"
client = TestClient(app)
POST = {"title": "Grace", "body": "<p>On <strong>grace</strong> and mercy</p>"}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)

  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM users WHERE email LIKE '%@conversations-test.example'")

  clear()
  client.cookies.clear()
  yield
  clear()


def sign_up(name="ann", allowed=True, last_name="Test"):
  """A new account, logged in (the client keeps its cookie), with use_conversations on or off."""
  client.cookies.clear()
  response = client.post(
    "/account/register",
    json={
      "email": f"{name}@conversations-test.example",
      "password": PASSWORD,
      "password_confirmation": PASSWORD,
      "first_name": name.title(),
      "last_name": last_name,
    },
  )
  assert response.status_code == 200
  user_id = response.json()["user"]["id"]
  with connect() as connection:
    connection.execute("UPDATE users SET use_conversations = %s WHERE id = %s", (allowed, user_id))
  return user_id


def log_in(name):
  client.cookies.clear()
  assert client.post("/account/login", json={"email": f"{name}@conversations-test.example", "password": PASSWORD}).status_code == 200


def test_every_endpoint_needs_a_login():
  assert client.get("/conversations").status_code == 401
  assert client.post("/conversations", json=POST).status_code == 401
  assert client.put("/conversations/1", json=POST).status_code == 401
  assert client.delete("/conversations/1").status_code == 401


def test_every_endpoint_needs_the_flag_and_it_starts_off():
  client.post(
    "/account/register",
    json={"email": "new@conversations-test.example", "password": PASSWORD, "password_confirmation": PASSWORD},
  )
  assert client.get("/account/me").json()["user"]["use_conversations"] is False

  assert client.get("/conversations").status_code == 403
  assert client.post("/conversations", json=POST).status_code == 403
  assert client.put("/conversations/1", json=POST).status_code == 403
  assert client.delete("/conversations/1").status_code == 403


def test_the_flag_is_in_the_login_answer_and_account_me():
  sign_up()
  assert client.get("/account/me").json()["user"]["use_conversations"] is True
  response = client.post("/account/login", json={"email": "ann@conversations-test.example", "password": PASSWORD})
  assert response.json()["user"]["use_conversations"] is True


def test_a_post_is_saved_cleaned_and_seen_by_every_allowed_member():
  sign_up("ann")
  saved = client.post(
    "/conversations", json={"title": "  Grace  alone ", "body": '<p onclick="x()">Hi<script>alert(1)</script></p>'}
  )
  assert saved.status_code == 200
  post = saved.json()["post"]
  assert post["title"] == "Grace alone" and post["author"] == "Ann Test" and post["is_mine"] is True
  assert "script" not in post["body"] and "onclick" not in post["body"] and "Hi" in post["body"]

  sign_up("bob")
  listed = client.get("/conversations").json()
  assert [entry["id"] for entry in listed["posts"]] == [post["id"]]
  assert listed["posts"][0]["is_mine"] is False and listed["total"] == 1


def test_posts_come_newest_first_and_page():
  sign_up()
  ids = [client.post("/conversations", json={**POST, "title": f"Post {number}"}).json()["post"]["id"] for number in range(3)]

  first_page = client.get("/conversations", params={"per_page": 2}).json()
  second_page = client.get("/conversations", params={"per_page": 2, "page": 2}).json()

  assert [post["id"] for post in first_page["posts"]] == [ids[2], ids[1]]
  assert [post["id"] for post in second_page["posts"]] == [ids[0]]
  assert first_page["total"] == 3
  assert client.get("/conversations", params={"per_page": 51}).status_code == 422


def test_search_matches_every_word_in_the_title_text_or_author_and_mine_keeps_ones_own():
  sign_up("ann")
  grace = client.post("/conversations", json=POST).json()["post"]
  sign_up("bob", last_name="Carver")
  hope = client.post("/conversations", json={"title": "Hope", "body": "<p>Hope in 100% of trials</p>"}).json()["post"]

  def found(**params):
    return [post["id"] for post in client.get("/conversations", params=params).json()["posts"]]

  assert found(query="MERCY") == [grace["id"]]
  assert found(query="hop") == [hope["id"]]
  assert found(query="carver") == [hope["id"]]
  assert found(query="grace hope") == []
  assert found(query="100%") == [hope["id"]]
  assert found(query="0%") == [hope["id"]] and found(query="%") == [hope["id"]]
  assert found(mine="true") == [hope["id"]]


def test_only_the_author_can_change_or_delete_a_post():
  sign_up("ann")
  post = client.post("/conversations", json=POST).json()["post"]
  sign_up("bob")

  assert client.put(f"/conversations/{post['id']}", json={"title": "Mine now", "body": "<p>x</p>"}).status_code == 404
  assert client.delete(f"/conversations/{post['id']}").status_code == 404

  log_in("ann")
  changed = client.put(f"/conversations/{post['id']}", json={"title": "Grace again", "body": "<p>More</p>"})
  assert changed.status_code == 200
  assert changed.json()["post"]["title"] == "Grace again" and changed.json()["post"]["updated_at"] >= post["created_at"]
  assert client.delete(f"/conversations/{post['id']}").status_code == 200
  assert client.get("/conversations").json()["total"] == 0
  assert client.delete(f"/conversations/{post['id']}").status_code == 404


def test_a_post_needs_a_title_and_text_within_the_limits():
  sign_up()
  assert client.post("/conversations", json={"title": " ", "body": "<p>x</p>"}).status_code == 422
  assert client.post("/conversations", json={"title": "T", "body": "<p> </p>"}).status_code == 422
  assert client.post("/conversations", json={"title": "x" * 201, "body": "<p>x</p>"}).status_code == 422
  too_long = "<p>" + "a" * (conversations.POST_TEXT_LIMIT + 1) + "</p>"
  assert client.post("/conversations", json={"title": "T", "body": too_long}).status_code == 422


def test_an_account_has_a_limit_of_posts(monkeypatch):
  sign_up()
  monkeypatch.setattr(conversations, "MAX_POSTS_PER_USER", 1)
  assert client.post("/conversations", json=POST).status_code == 200
  assert client.post("/conversations", json=POST).status_code == 422


def test_an_author_without_a_name_is_a_member_and_never_their_address():
  client.post(
    "/account/register",
    json={"email": "noname@conversations-test.example", "password": PASSWORD, "password_confirmation": PASSWORD},
  )
  with connect() as connection:
    connection.execute("UPDATE users SET use_conversations = true WHERE email = 'noname@conversations-test.example'")
  post = client.post("/conversations", json=POST).json()["post"]
  assert post["author"] == "A member"


def test_turning_the_flag_off_stops_the_account_and_deleting_the_user_deletes_the_posts():
  user_id = sign_up()
  client.post("/conversations", json=POST)
  with connect() as connection:
    connection.execute("UPDATE users SET use_conversations = false WHERE id = %s", (user_id,))
  assert client.get("/conversations").status_code == 403
  with connect() as connection:
    connection.execute("DELETE FROM users WHERE id = %s", (user_id,))
    assert connection.execute("SELECT count(*) FROM conversation_posts WHERE user_id = %s", (user_id,)).fetchone()[0] == 0


def test_site_users_can_set_the_flag():
  import site_users

  user = site_users.create_user("admin-made@conversations-test.example", PASSWORD, True, False, use_conversations=True)
  assert user["use_conversations"] is True
  assert site_users.update_user(user["id"], use_conversations=False)["use_conversations"] is False
  assert site_users.update_user(user["id"], email_verified=False)["use_conversations"] is False


def run_tool(*arguments):
  import json
  import subprocess
  import sys
  from pathlib import Path

  script = Path(__file__).resolve().parent.parent / "scripts" / "manage_conversations.py"
  completed = subprocess.run([sys.executable, str(script), *arguments], capture_output=True, text=True)
  return completed.returncode, json.loads(completed.stdout)


def test_an_administrator_lists_and_deletes_any_post_with_the_tool():
  sign_up("ann")
  post = client.post("/conversations", json={"title": "Grace", "body": "<p>" + "word " * 100 + "</p>"}).json()["post"]

  status, listing = run_tool("list", "--query=ann@conversations-test")
  assert status == 0 and [entry["id"] for entry in listing["posts"]] == [post["id"]]
  entry = listing["posts"][0]
  assert entry["author"] == "Ann Test" and entry["author_email"] == "ann@conversations-test.example"
  assert entry["excerpt"].endswith("…") and len(entry["excerpt"]) <= conversations.EXCERPT_LENGTH + 1

  status, deleted = run_tool("delete", f"--id={post['id']}")
  assert status == 0 and deleted["post"]["title"] == "Grace"
  assert client.get("/conversations").json()["total"] == 0
  status, missing = run_tool("get", f"--id={post['id']}")
  assert status == 1 and missing["ok"] is False and "no such post" in missing["error"]

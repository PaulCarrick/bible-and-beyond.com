"""Tests for "Check posts with AI": Gemini (faked here, nothing is sent) checks Conversations and Prayer Wall posts and
replies before they are saved, while the site setting is on. They use the real tables, remove their own users (and
so their posts), and put the setting back as it was."""

import pytest
from fastapi.testclient import TestClient

import accounts
import conversations
import post_moderation
import site_settings
from faq import FaqUnavailable
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "post-moderation-test.example"
client = TestClient(app)


@pytest.fixture(autouse=True)
def gemini(monkeypatch):
  """What the fake Gemini was asked, and what it answers (set answer["text"], or answer["error"] to fail)."""
  asked = []
  answer = {"text": "ALLOWED", "error": None}

  def fake_gemini(question, system_prompt, total_seconds):
    asked.append(question)
    if answer["error"]:
      raise answer["error"]
    return answer["text"]

  monkeypatch.setattr(post_moderation, "ask_gemini", fake_gemini)
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(conversations, "send_email", lambda settings, email: None)
  before = site_settings.get_settings()["check_posts"]

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  site_settings.save_settings({"check_posts": True})
  yield {"asked": asked, "answer": answer}
  site_settings.save_settings({"check_posts": before})
  clear()


def sign_up(name):
  client.cookies.clear()
  response = client.post(
    "/account/register",
    json={"email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD, "first_name": name.title(), "last_name": "Test"},
  )
  with connect() as connection:
    connection.execute("UPDATE users SET use_conversations = true WHERE id = %s", (response.json()["user"]["id"],))


def post(title="Grace", body="<p>On grace</p>", **options):
  return client.post("/conversations", json={"title": title, "body": body, **options})


def my_posts(board="conversations"):
  return client.get("/conversations", params={"mine": "true", "board": board}).json()["posts"]


def test_an_allowed_post_is_saved_and_gemini_saw_its_title_and_text(gemini):
  sign_up("ann")
  response = post("Grace", "<p>On <strong>grace</strong> alone</p>")
  assert response.status_code == 200
  assert len(gemini["asked"]) == 1
  question = gemini["asked"][0]
  assert "Conversations" in question and "Title: Grace" in question and "On grace alone" in question
  assert "<strong>" not in question  # the plain text only


def test_a_rejected_post_is_refused_with_the_reason_and_not_saved(gemini):
  sign_up("ann")
  gemini["answer"]["text"] = "REJECTED: political campaigning"
  response = post("Vote", "<p>Vote for my candidate</p>")
  assert response.status_code == 422
  message = response.json()["detail"]
  assert "This post was not accepted (political campaigning)" in message
  assert "profanity, political messages, advertising" in message
  assert my_posts() == []


def test_the_prayer_wall_and_replies_are_checked_too(gemini):
  sign_up("ann")
  assert post("Please pray", "<p>For my mother</p>", board="prayer").status_code == 200
  assert "the Prayer Wall" in gemini["asked"][-1]
  conversation = post().json()["post"]
  gemini["answer"]["text"] = "REJECTED: advertising"
  response = client.post(f"/conversations/{conversation['id']}/replies", json={"body": "<p>Buy my product</p>"})
  assert response.status_code == 422 and "This reply was not accepted (advertising)" in response.json()["detail"]
  assert my_posts()[0]["replies"] == []
  assert gemini["asked"][-1].startswith("A reply for Conversations.")


def test_an_edit_is_checked_and_a_rejected_one_keeps_the_old_text(gemini):
  sign_up("ann")
  saved = post("Grace", "<p>Kind words</p>").json()["post"]
  gemini["answer"]["text"] = "REJECTED: profanity"
  response = client.put(f"/conversations/{saved['id']}", json={"title": "Grace", "body": "<p>Rude words</p>"})
  assert response.status_code == 422
  assert "Kind words" in my_posts()[0]["body"]

  reply = client.post(f"/conversations/{saved['id']}/replies", json={"body": "<p>x</p>"})
  assert reply.status_code == 422  # still rejecting
  gemini["answer"]["text"] = "ALLOWED"
  reply_id = client.post(f"/conversations/{saved['id']}/replies", json={"body": "<p>Amen</p>"}).json()["reply"]["id"]
  gemini["answer"]["text"] = "REJECTED: insult"
  changed = client.put(f"/conversations/replies/{reply_id}", json={"body": "<p>Rude</p>"})
  assert changed.status_code == 422
  assert "Amen" in my_posts()[0]["replies"][0]["body"]


def test_someone_elses_post_is_not_found_before_gemini_is_asked(gemini):
  sign_up("ann")
  saved = post().json()["post"]
  sign_up("bob")
  asked = len(gemini["asked"])
  response = client.put(f"/conversations/{saved['id']}", json={"title": "Mine now", "body": "<p>x</p>"})
  assert response.status_code == 404 and len(gemini["asked"]) == asked


def test_when_gemini_fails_or_answers_oddly_the_post_is_accepted(gemini):
  sign_up("ann")
  gemini["answer"]["error"] = FaqUnavailable("busy")
  assert post("One").status_code == 200
  gemini["answer"]["error"] = None
  gemini["answer"]["text"] = "I think this is fine."
  assert post("Two").status_code == 200
  assert len(my_posts()) == 2


def test_when_the_setting_is_off_gemini_is_not_asked(gemini):
  site_settings.save_settings({"check_posts": False})
  sign_up("ann")
  gemini["answer"]["text"] = "REJECTED: anything"
  assert post().status_code == 200
  assert gemini["asked"] == []


def test_the_settings_tool_turns_it_on_and_off():
  import json
  import subprocess
  import sys
  from pathlib import Path

  tool = Path(__file__).resolve().parent.parent / "scripts" / "manage_settings.py"
  for choice, expected in (("no", False), ("yes", True)):
    answer = subprocess.run([sys.executable, str(tool), "set", f"--check-posts={choice}"], capture_output=True, text=True)
    assert json.loads(answer.stdout)["settings"]["check_posts"] is expected

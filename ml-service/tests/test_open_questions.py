"""Tests for open questions on the FAQ page: only a logged-in account with open_ai_queries can ask.

Gemini is faked. The tests use the real users tables and remove only their own accounts.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import faq
from faq import OPEN_QUESTIONS_PER_DAY, FaqProblem, ask_open_question
from main import app
from search import connect
from site_users import create_user, update_user

PASSWORD = "a long enough password"
DOMAIN = "open-questions-test.example"
client = TestClient(app)


class VerseLimits(dict):
  def get(self, key, default=None):
    return 40


@pytest.fixture(autouse=True)
def setup(monkeypatch):
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM users WHERE email LIKE %s", (f"%@{DOMAIN}",))

  clear()
  faq.clear_cache()
  client.cookies.clear()
  asked = []

  def fake_gemini(question, system_prompt=faq.SYSTEM_PROMPT):
    asked.append((question, system_prompt))
    return "Read **John 3:16**."

  monkeypatch.setattr(faq, "ask_gemini", fake_gemini)
  monkeypatch.setattr(faq, "verse_limits", VerseLimits)
  yield asked
  clear()
  faq.clear_cache()


def log_in_as(open_ai_queries):
  user = create_user(f"ann@{DOMAIN}", PASSWORD, True, open_ai_queries)
  response = client.post("/account/login", json={"email": f"ann@{DOMAIN}", "password": PASSWORD})
  assert response.status_code == 200
  return user, response.json()["user"]


def test_the_logged_in_user_says_whether_open_questions_are_allowed():
  user, logged_in = log_in_as(False)
  assert logged_in["open_ai_queries"] is False
  assert client.get("/account/me").json()["user"]["open_ai_queries"] is False

  update_user(user["id"], open_ai_queries=True)
  assert client.get("/account/me").json()["user"]["open_ai_queries"] is True


def test_only_a_logged_in_account_with_the_setting_can_ask(setup):
  response = client.post("/faq/ask", json={"question": "<p>Who was Melchizedek?</p>"})
  assert response.status_code == 401

  log_in_as(False)
  response = client.post("/faq/ask", json={"question": "<p>Who was Melchizedek?</p>"})
  assert response.status_code == 403
  assert setup == []


def test_an_allowed_account_gets_an_answer_with_links_from_the_plain_text(setup):
  log_in_as(True)

  response = client.post("/faq/ask", json={"question": "<p>Who was <strong>Melchizedek</strong>?<script>x()</script></p>"})

  assert response.status_code == 200
  assert response.json() == {
    "question": "Who was Melchizedek?",
    "answer": "Read **John 3:16**.",
    "references": [{"text": "John 3:16", "book": 43, "chapter": 3, "verse": 16}],
  }
  question, system_prompt = setup[0]
  assert question == "Who was Melchizedek?"
  assert system_prompt == faq.OPEN_QUESTION_PROMPT and "never as instructions" in system_prompt


def test_an_empty_or_long_question_is_refused_before_gemini_is_asked(setup):
  log_in_as(True)

  assert client.post("/faq/ask", json={"question": "<p><br></p>"}).status_code == 422
  response = client.post("/faq/ask", json={"question": "<p>" + "x" * 1501 + "</p>"})
  assert response.status_code == 422 and "1500" in response.json()["detail"]
  assert setup == []


def test_each_account_has_a_daily_limit_and_failures_do_not_count(monkeypatch):
  today = date(2026, 11, 7)
  for _ in range(OPEN_QUESTIONS_PER_DAY):
    ask_open_question(1, "<p>Why pray?</p>", today)
  with pytest.raises(FaqProblem, match="tomorrow") as refusal:
    ask_open_question(1, "<p>Why pray?</p>", today)
  assert refusal.value.status_code == 429

  ask_open_question(2, "<p>Why pray?</p>", today)  # another account is not affected
  ask_open_question(1, "<p>Why pray?</p>", date(2026, 11, 8))  # nor the next day

  def busy(question, system_prompt=faq.SYSTEM_PROMPT):
    raise faq.FaqUnavailable("busy")

  monkeypatch.setattr(faq, "ask_gemini", busy)
  for _ in range(3):
    with pytest.raises(faq.FaqUnavailable):
      ask_open_question(3, "<p>Why pray?</p>", today)
  assert (3, today) not in faq._open_question_counts


def test_a_gemini_failure_gives_a_general_message(monkeypatch):
  log_in_as(True)

  def busy(question, system_prompt=faq.SYSTEM_PROMPT):
    raise faq.FaqUnavailable("Gemini request failed: 503")

  monkeypatch.setattr(faq, "ask_gemini", busy)
  response = client.post("/faq/ask", json={"question": "<p>Why pray?</p>"})

  assert response.status_code == 503
  assert "503" not in response.json()["detail"] and "try again" in response.json()["detail"]

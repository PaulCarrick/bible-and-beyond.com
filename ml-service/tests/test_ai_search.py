"""Tests for searching the Bible with AI: only a logged-in account with open_ai_queries can use it.

Gemini is faked. The tests use the real verses and users tables and remove only their own accounts.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import ai_search
import faq
from ai_search import AI_SEARCHES_PER_DAY, AiSearchProblem, find_verses, read_references
from main import app
from search import connect
from site_users import create_user

PASSWORD = "a long enough password"
DOMAIN = "ai-search-test.example"
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
  ai_search.clear_cache()
  client.cookies.clear()
  asked = []

  def fake_gemini(question, system_prompt=faq.SYSTEM_PROMPT, total_seconds=faq.TOTAL_SECONDS):
    asked.append({"question": question, "system_prompt": system_prompt, "total_seconds": total_seconds})
    return "Romans 5:8\nJohn 3:16\n1 John 4:9-10\nJohn 3:16\nHezekiah 1:1\n"

  monkeypatch.setattr(faq, "ask_gemini", fake_gemini)
  yield asked
  clear()
  ai_search.clear_cache()


def log_in_as(open_ai_queries):
  create_user(f"ann@{DOMAIN}", PASSWORD, True, open_ai_queries)
  response = client.post("/account/login", json={"email": f"ann@{DOMAIN}", "password": PASSWORD})
  assert response.status_code == 200


def ai_search_request(**parameters):
  return client.get("/search", params={"query": "the love of God", "match_mode": "ai", "translations": "BSB", **parameters})


def test_only_a_logged_in_account_with_the_setting_can_search_with_ai(setup):
  assert ai_search_request().status_code == 401

  log_in_as(False)
  assert ai_search_request().status_code == 403
  assert setup == []


def test_the_verses_gemini_names_are_listed_from_our_bible(setup):
  log_in_as(True)

  response = ai_search_request()

  assert response.status_code == 200
  body = response.json()
  assert setup[0]["question"] == "Search for Bible verses related to: the love of God"
  assert setup[0]["total_seconds"] < 40  # nginx waits 40 seconds for a search.
  assert body["ai"] is True
  assert body["ai_verse_count"] == 3
  assert body["terms"] == []
  # Listed in Bible order, like any search; a range gives its first verse; a repeat and a made-up book are dropped.
  assert [result["reference"] for result in body["results"]] == ["John 3:16", "Romans 5:8", "1 John 4:9"]
  assert all(result["translation"] == "BSB" for result in body["results"])
  assert {entry["book_number"] for entry in body["book_counts"]} == {43, 45, 62}


def test_paging_and_the_book_filter_do_not_ask_gemini_again(setup):
  log_in_as(True)
  ai_search_request()

  response = ai_search_request(book=45, per_page=1)

  assert response.status_code == 200
  assert [result["reference"] for result in response.json()["results"]] == ["Romans 5:8"]
  assert len(setup) == 1


def test_the_licensed_bibles_are_refused(setup):
  log_in_as(True)

  response = client.get("/search", params={"query": "love", "match_mode": "ai", "translations": "NIV"})

  assert response.status_code == 422
  assert setup == []


def test_gemini_failing_gives_a_general_message(monkeypatch):
  log_in_as(True)

  def failing_gemini(question, system_prompt=faq.SYSTEM_PROMPT, total_seconds=faq.TOTAL_SECONDS):
    raise faq.FaqUnavailable("busy")

  monkeypatch.setattr(faq, "ask_gemini", failing_gemini)
  response = ai_search_request()

  assert response.status_code == 503
  assert "busy" not in response.json()["detail"]


def test_reading_references():
  # Verses in each chapter: only John 3 and Psalm 23 exist here.
  limits = {(43, 3): 36, (19, 23): 6}
  answer = "John 3:16\nJohn 3:16-18\nPsalm 23:1\nNot a verse\nJohn 99:1\nNONE"
  assert read_references(answer, limits) == [(43, 3, 16), (19, 23, 1)]
  assert read_references("NONE", limits) == []


def test_each_account_has_a_daily_limit_of_new_searches(setup):
  today = date(2026, 11, 11)
  for number in range(AI_SEARCHES_PER_DAY):
    find_verses(7, f"topic {number}", today)

  # A query already asked is kept, so it does not count.
  find_verses(7, "TOPIC   0", today)
  with pytest.raises(AiSearchProblem) as problem:
    find_verses(7, "one more topic", today)
  assert problem.value.status_code == 429
  assert len(setup) == AI_SEARCHES_PER_DAY
  # Another account, or the next day, may search again.
  find_verses(8, "one more topic", today)
  find_verses(7, "another topic", date(2026, 11, 12))

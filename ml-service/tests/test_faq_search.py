"""Tests for searching the FAQ (faq.search_faq, the FAQ group of Search everything). They set the stored notes and
answers aside and put them back afterwards."""

import pytest
from fastapi.testclient import TestClient

import faq
import site_search
from main import app
from search import connect

client = TestClient(app)
GRACE = "Is a Christian saved by grace alone?"
SUFFERING = "Why does a loving God allow suffering and evil?"
DOUBT = "Does having doubts mean I’m losing my faith?"


@pytest.fixture(autouse=True)
def own_notes_and_answers():
  with connect() as connection:
    notes = connection.execute("SELECT id, question, body, created_at, updated_at FROM faq_notes").fetchall()
    answers = connection.execute("SELECT question, answer, prompt_hash, fetched_at FROM faq_answers").fetchall()
    connection.execute("DELETE FROM faq_notes")
    connection.execute("DELETE FROM faq_answers")
    connection.execute("INSERT INTO faq_notes (question, body) VALUES (%s, %s)", (SUFFERING, "<p>Our <strong>zebrafinch</strong> group meets on Tuesdays.</p>"))
    connection.execute(
      "INSERT INTO faq_answers (question, answer, prompt_hash) VALUES (%s, %s, 'test')",
      (DOUBT, "## Doubt\n\nHonest **quokka** questions are part of a growing faith (Mark 9:24)."),
    )
  yield
  with connect() as connection:
    connection.execute("DELETE FROM faq_notes")
    connection.execute("DELETE FROM faq_answers")
    for row in notes:
      connection.execute("INSERT INTO faq_notes (id, question, body, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)", row)
    connection.execute("SELECT setval(pg_get_serial_sequence('faq_notes', 'id'), GREATEST((SELECT max(id) FROM faq_notes), 1))")
    for row in answers:
      connection.execute("INSERT INTO faq_answers (question, answer, prompt_hash, fetched_at) VALUES (%s, %s, %s, %s)", row)


def test_the_questions_notes_and_stored_answers_are_searched():
  by_question = faq.search_faq("grace alone", "all", 1, 10)
  assert [result["question"] for result in by_question["results"]] == [GRACE]
  assert by_question["results"][0]["id"] == 9 and by_question["results"][0]["group"]

  by_note = faq.search_faq("zebrafinch", "all", 1, 10)
  assert [result["question"] for result in by_note["results"]] == [SUFFERING]
  # The excerpt is the note's words, without its tags, with the word found marked.
  assert "\u0001zebrafinch\u0002" in by_note["results"][0]["text"] and "<" not in by_note["results"][0]["text"]

  by_answer = faq.search_faq("quokka", "all", 1, 10)
  assert [result["question"] for result in by_answer["results"]] == [DOUBT]
  assert "**" not in by_answer["results"][0]["text"] and "##" not in by_answer["results"][0]["text"]
  nothing = faq.search_faq("nothingmatcheswordzz", "all", 1, 10)
  assert nothing["total"] == 0 and nothing["results"] == []


def test_the_faq_is_a_group_of_search_everything_but_not_of_the_search_by_meaning():
  found = client.get("/search-everything", params={"query": "quokka"}).json()
  faq_groups = [group for group in found["groups"] if group["kind"] == "faq"]
  assert faq_groups and faq_groups[0]["results"][0]["question"] == DOUBT
  more = client.get("/search-everything", params={"query": "faith", "kind": "faq", "per_page": 2}).json()
  assert more["groups"][0]["kind"] == "faq" and len(more["groups"][0]["results"]) <= 2
  assert "faq" not in site_search.AI_KINDS
  assert site_search.search_everything_with_ai(1, "faith", "faq")["groups"][0]["results"] == []


def test_a_question_whose_own_words_match_comes_first():
  # "suffering" is in the suffering question itself; another question's answer that mentions it comes after.
  with connect() as connection:
    connection.execute("INSERT INTO faq_answers (question, answer, prompt_hash) VALUES (%s, %s, 'test')", (GRACE, "Grace meets us in suffering and suffering again."))
  found = faq.search_faq("suffering", "all", 1, 10)
  assert found["results"][0]["question"] == SUFFERING and GRACE in [result["question"] for result in found["results"]]

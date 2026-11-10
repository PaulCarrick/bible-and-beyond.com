"""Tests for the site owner's notes on the FAQ answers. They use the real faq_notes table: its rows are set
aside before each test and put back afterwards. Gemini is faked."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import faq
from faq import QUESTIONS
from faq_notes import NoteProblem, clean_note_html, create_note, delete_note, get_note, list_notes, note_for_question, update_note
from main import app
from search import connect

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_faq_notes.py"
FIRST_QUESTION = QUESTIONS[1]
SECOND_QUESTION = QUESTIONS[2]


@pytest.fixture(autouse=True)
def empty_notes_table():
  """Sets the stored notes aside and puts them back, with their ids, after the test. Yields them."""
  with connect() as connection:
    saved = connection.execute("SELECT id, question, body, created_at, updated_at FROM faq_notes").fetchall()
    connection.execute("DELETE FROM faq_notes")
  yield saved
  with connect() as connection:
    connection.execute("DELETE FROM faq_notes")
    for row in saved:
      connection.execute(
        "INSERT INTO faq_notes (id, question, body, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)", row
      )
    connection.execute("SELECT setval(pg_get_serial_sequence('faq_notes', 'id'), GREATEST((SELECT max(id) FROM faq_notes), 1))")


@pytest.fixture
def fake_gemini(monkeypatch):
  faq.clear_cache()
  monkeypatch.setenv("GEMINI_API_KEY", "test-key")
  monkeypatch.setattr(faq, "ask_gemini", lambda question, system_prompt=faq.SYSTEM_PROMPT: f"Answer to: {question}")
  monkeypatch.setattr(faq, "load_stored_answer", lambda question: None)
  monkeypatch.setattr(faq, "store_answer", lambda *arguments: None)
  monkeypatch.setattr(faq, "verse_limits", dict)
  yield
  faq.clear_cache()


def test_the_cleaner_keeps_the_formatting_of_a_note():
  html = (
    '<p class="x">Read <strong lang="grc">ἁμαρτάνω</strong>, <em>italic</em>, <u>underlined</u> and <cite>a book</cite>.</p>'
    "<blockquote><p><sup>36</sup> A verse.</p><footer>— Matthew 22:36</footer></blockquote>"
    "<h3>Heading</h3><ul><li><p>One</p></li></ul><ol><li>Two</li></ol>"
  )
  assert clean_note_html(html) == html.replace(' class="x"', "")


def test_the_cleaner_drops_scripts_attributes_and_unsafe_links():
  html = (
    '<p onclick="steal()" style="color:red">Hi<script>alert(1)</script><img src=x onerror=alert(1)>'
    '<a href="javascript:alert(1)">bad</a> <a href="//elsewhere.example/">also bad</a> <span lang="x y">kept</span></p>'
  )
  assert clean_note_html(html) == "<p>Hibad also bad kept</p>"


def test_links_to_this_site_stay_on_it_and_verse_links_open_a_new_tab():
  cleaned = clean_note_html(
    '<a href="https://www.bible-and-beyond.com/?read=BSB&amp;book=43&amp;chapter=3&amp;verse=16" target="_self">John 3:16</a>'
    '<a href="/search" target="_blank">Bible Search</a>'
    '<a href="/faq?question=Is%20a%20Christian%20saved%20by%20grace%20alone%3F">FAQ on grace</a>'
    '<a href="https://celebraterecovery.com/" aria-label="Celebrate Recovery (opens its website in a new tab)">CR</a>'
  )
  assert cleaned == (
    '<a href="/?read=BSB&amp;book=43&amp;chapter=3&amp;verse=16" target="_blank" rel="noopener">John 3:16</a>'
    '<a href="/search">Bible Search</a>'
    '<a href="/faq?question=Is%20a%20Christian%20saved%20by%20grace%20alone%3F">FAQ on grace</a>'
    '<a href="https://celebraterecovery.com/" target="_blank" rel="noopener noreferrer"'
    ' aria-label="Celebrate Recovery (opens its website in a new tab)">CR</a>'
  )


def test_the_owners_notes_are_unchanged_by_cleaning_again(empty_notes_table):
  assert empty_notes_table, "the migration should have stored the owner's notes"
  for _, question, body, _, _ in empty_notes_table:
    assert clean_note_html(body) == body, question


def test_a_note_is_added_changed_and_deleted():
  note = create_note(f" {FIRST_QUESTION} ", "<p>My <strong>note</strong></p><script>x</script>")
  assert note["question"] == FIRST_QUESTION
  assert note["question_number"] == 1
  assert note["html"] == "<p>My <strong>note</strong></p>"
  assert note["preview"] == "My note"
  assert get_note(note["id"])["html"] == note["html"]

  changed = update_note(note["id"], SECOND_QUESTION, "<p>Changed</p>")
  assert changed["question"] == SECOND_QUESTION
  assert changed["updated_at"] >= note["updated_at"]
  assert note_for_question(SECOND_QUESTION) == "<p>Changed</p>"
  assert note_for_question(FIRST_QUESTION) == ""

  delete_note(note["id"])
  assert list_notes() == []
  with pytest.raises(NoteProblem):
    get_note(note["id"])


def test_a_question_has_one_note_and_must_be_on_the_list():
  create_note(FIRST_QUESTION, "<p>One</p>")
  with pytest.raises(NoteProblem, match="already has a note"):
    create_note(FIRST_QUESTION, "<p>Two</p>")
  with pytest.raises(NoteProblem, match="choose a question"):
    create_note("Write me a poem", "<p>Three</p>")
  with pytest.raises(NoteProblem, match="write something"):
    create_note(SECOND_QUESTION, "<p> </p><script>only this</script>")


def test_a_note_on_a_reworded_question_can_keep_its_old_wording():
  with connect() as connection:
    note_id = connection.execute(
      "INSERT INTO faq_notes (question, body) VALUES ('An old wording?', '<p>Old</p>') RETURNING id"
    ).fetchone()[0]
  note = update_note(note_id, "An old wording?", "<p>Still here</p>")
  assert note["is_listed"] is False
  assert list_notes()[-1]["question"] == "An old wording?"
  assert update_note(note_id, FIRST_QUESTION, "<p>Moved</p>")["is_listed"] is True
  with pytest.raises(NoteProblem):
    update_note(note_id, "An old wording?", "<p>Cannot go back</p>")


def test_the_answer_comes_with_its_note(fake_gemini):
  create_note(QUESTIONS[3], '<p>See <a href="/search">Bible Search</a>.</p>')
  with_note = client.post("/faq/answer", json={"question_id": 3}).json()
  without_note = client.post("/faq/answer", json={"question_id": 4}).json()
  assert with_note["owner_note"] == '<p>See <a href="/search">Bible Search</a>.</p>'
  assert with_note["answer"] == f"Answer to: {QUESTIONS[3]}"
  assert without_note["owner_note"] == ""


def test_a_database_problem_still_gives_the_answer(fake_gemini, monkeypatch):
  import faq_notes

  def broken(question):
    raise RuntimeError("database down")

  monkeypatch.setattr(faq_notes, "note_for_question", broken)
  response = client.post("/faq/answer", json={"question_id": 5})
  assert response.status_code == 200
  assert response.json()["owner_note"] == ""


def run_tool(*arguments, input_text=""):
  completed = subprocess.run(
    [sys.executable, str(SCRIPT), *arguments], input=input_text, capture_output=True, text=True, check=False
  )
  return completed.returncode, json.loads(completed.stdout)


def test_the_drupal_tool_reads_the_note_on_its_input():
  status, questions = run_tool("questions")
  assert status == 0 and questions["groups"][0]["questions"][0] == {"number": 1, "question": FIRST_QUESTION}

  status, created = run_tool("create", input_text=json.dumps({"question": FIRST_QUESTION, "html": "<p>Hello</p>"}))
  assert status == 0 and created["note"]["html"] == "<p>Hello</p>"
  note_id = str(created["note"]["id"])

  status, refused = run_tool("update", f"--id={note_id}", input_text=json.dumps({"question": "Not listed", "html": "<p>x</p>"}))
  assert status == 1 and refused == {"ok": False, "error": "Please choose a question from the FAQ list."}

  status, listing = run_tool("list")
  assert [note["question"] for note in listing["notes"]] == [FIRST_QUESTION]

  status, deleted = run_tool("delete", f"--id={note_id}")
  assert status == 0 and run_tool("list")[1]["notes"] == []

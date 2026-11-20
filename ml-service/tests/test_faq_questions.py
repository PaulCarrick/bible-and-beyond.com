"""Tests for a site's own FAQ questions (faq_questions, migration 063) and its description for Gemini (faq_about).
They use the real tables and leave them empty (the built-in list) afterwards."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import faq
import faq_notes
from main import app
from search import connect
from site_settings import save_settings

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_faq_questions.py"
CR = {
  "about": "The Celebrate Recovery ministry of a church: readers are in Christ-centred recovery.",
  "groups": [
    {"heading": "Celebrate Recovery", "questions": ["What is Celebrate Recovery?", "What is a hurt, habit, or hang-up?"]},
    {"heading": "Recovery and the Bible", "questions": ["Are the 12 Steps based on the Bible?"]},
  ],
}


@pytest.fixture(autouse=True)
def clean():
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM faq_questions")
      connection.execute("DELETE FROM site_settings WHERE key = 'faq_about'")
      # The answers these tests store (kept by question text), so a second run asks again.
      connection.execute("DELETE FROM faq_answers WHERE question = ANY(%s)", ([q for g in CR["groups"] for q in g["questions"]],))

  clear()
  yield
  clear()


def run(*arguments, document=None):
  completed = subprocess.run([sys.executable, str(SCRIPT), *arguments], input=json.dumps(document) if document else "",
                             capture_output=True, text=True, check=False)
  return completed.returncode, json.loads(completed.stdout)


def test_without_its_own_questions_a_site_keeps_the_built_in_list():
  groups = faq.question_groups()
  assert [heading for heading, _ in groups] == [heading for heading, _ in faq.BUILT_IN_GROUPS]
  assert faq.current_questions() == faq.QUESTIONS
  assert faq.site_prompt() == faq.SYSTEM_PROMPT


def test_a_sites_own_questions_replace_the_list_and_its_description_goes_to_gemini(monkeypatch):
  status, result = run("replace", document=CR)
  assert status == 0 and result["source"] == "site"
  listed = client.get("/faq").json()["groups"]
  assert [group["heading"] for group in listed] == ["Celebrate Recovery", "Recovery and the Bible"]
  first = listed[0]["questions"][0]
  assert first["question"] == "What is Celebrate Recovery?"

  prompts = []
  monkeypatch.setattr(faq, "ask_gemini", lambda question, system_prompt=faq.SYSTEM_PROMPT: prompts.append(system_prompt) or f"Answer to {question}")
  answered = client.post("/faq/answer", json={"question_id": first["id"]})
  assert answered.status_code == 200, answered.text
  assert answered.json()["question"] == "What is Celebrate Recovery?"
  assert prompts[0].startswith(faq.SYSTEM_PROMPT) and "Christ-centred recovery" in prompts[0]

  # A built-in question's number is no longer one of the site's.
  assert client.post("/faq/answer", json={"question_id": 999999}).status_code == 404
  # Notes go with the site's own questions only.
  assert faq_notes.question_number("What is Celebrate Recovery?") == first["id"]
  assert faq_notes.question_number(faq.QUESTIONS[1]) is None


def test_bad_lists_are_refused_and_built_in_goes_back():
  for bad in ({"groups": []}, {"groups": [{"heading": "", "questions": ["x"]}]},
              {"groups": [{"heading": "A", "questions": ["Same?", "Same?"]}]}):
    status, result = run("replace", document=bad)
    assert status == 1 and not result["ok"]
  run("replace", document=CR)
  status, result = run("built-in")
  assert status == 0 and result["source"] == "built-in" and result["about"] == ""
  assert faq.current_questions() == faq.QUESTIONS


def test_the_open_question_prompt_carries_the_description(monkeypatch):
  save_settings({"faq_about": "A recovery ministry."})
  sent = []
  monkeypatch.setattr(faq, "ask_gemini", lambda question, system_prompt=faq.SYSTEM_PROMPT: sent.append(system_prompt) or "Answer")
  faq.ask_open_question(1, "<p>How do I start?</p>")
  assert sent[0].startswith(faq.SYSTEM_PROMPT) and "A recovery ministry." in sent[0] and sent[0].endswith(faq.OPEN_QUESTION_RULES)


import faq_questions  # noqa: E402
from faq_questions import QuestionsProblem  # noqa: E402


def test_the_first_change_makes_the_built_in_list_the_sites_own():
  assert faq_questions.describe()["source"] == "built-in"
  second = faq.QUESTIONS[2]
  faq_questions.move_question(2, "up")
  listed = faq_questions.describe()
  assert listed["source"] == "site"
  first_group = [entry["question"] for entry in listed["groups"][0]["questions"]]
  assert first_group[:2] == [second, faq.QUESTIONS[1]]
  assert sum(len(group["questions"]) for group in listed["groups"]) == len(faq.QUESTIONS)


def test_add_reword_regroup_move_and_delete(monkeypatch):
  run("replace", document=CR)
  ids = {entry["question"]: entry["id"] for group in faq_questions.describe()["groups"] for entry in group["questions"]}

  added = faq_questions.add_question("Celebrate Recovery", "  Where  are meetings held? ")
  assert added["question"] == "Where are meetings held?" and added["heading"] == "Celebrate Recovery"
  groups = faq_questions.describe()["groups"]
  assert [entry["question"] for entry in groups[0]["questions"]][-1] == "Where are meetings held?"
  with pytest.raises(QuestionsProblem, match="already"):
    faq_questions.add_question("Celebrate Recovery", "Where are meetings held?")

  # Rewording moves the owner's note with the question.
  with connect() as connection:
    connection.execute("DELETE FROM faq_notes WHERE question IN ('What is Celebrate Recovery?', 'What is CR?')")
    connection.execute("INSERT INTO faq_notes (question, body) VALUES ('What is Celebrate Recovery?', '<p>Ours meets Tuesdays.</p>')")
  faq_questions.update_question(ids["What is Celebrate Recovery?"], "Celebrate Recovery", "What is CR?")
  with connect() as connection:
    moved = connection.execute("SELECT count(*) FROM faq_notes WHERE question = 'What is CR?'").fetchone()[0]
    connection.execute("DELETE FROM faq_notes WHERE question = 'What is CR?'")
  assert moved == 1

  # A new heading puts it last in that heading's group.
  faq_questions.update_question(ids["What is a hurt, habit, or hang-up?"], "Recovery and the Bible", "What is a hurt, habit, or hang-up?")
  groups = faq_questions.describe()["groups"]
  assert [entry["question"] for entry in groups[1]["questions"]] == ["Are the 12 Steps based on the Bible?", "What is a hurt, habit, or hang-up?"]

  faq_questions.move_question(ids["What is a hurt, habit, or hang-up?"], "up")
  assert faq_questions.describe()["groups"][1]["questions"][0]["question"] == "What is a hurt, habit, or hang-up?"
  # Already first in its group: nothing changes.
  faq_questions.move_question(ids["What is a hurt, habit, or hang-up?"], "up")
  assert faq_questions.describe()["groups"][1]["questions"][0]["question"] == "What is a hurt, habit, or hang-up?"

  faq_questions.delete_question(added["id"])
  assert all(entry["question"] != "Where are meetings held?" for group in faq_questions.describe()["groups"] for entry in group["questions"])
  with pytest.raises(QuestionsProblem, match="not found"):
    faq_questions.delete_question(added["id"])
  assert faq_questions.set_about("  A   ministry. ") == "A ministry."

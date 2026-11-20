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

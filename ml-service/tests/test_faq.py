"""Tests for the FAQ. Gemini is faked: nothing is sent to Google."""

import pytest
from fastapi.testclient import TestClient

import faq
from faq import ANSWER_CACHE_SECONDS, FaqUnavailable, UnknownQuestion, get_answer
from main import app

client = TestClient(app)
# The system prompt sent with each faked Gemini call, in order.
prompts = []


class VerseLimits(dict):
  """Stands in for the verse table: every book has 50 chapters of 40 verses."""

  def get(self, key, default=None):
    book, chapter = key
    return 40 if chapter <= 50 else 0


@pytest.fixture(autouse=True)
def fake_gemini(monkeypatch):
  """Replaces the Gemini call with one that records the questions asked."""
  faq.clear_cache()
  calls = []
  prompts.clear()

  def answer(question, system_prompt=faq.SYSTEM_PROMPT):
    calls.append(question)
    prompts.append(system_prompt)
    return f"Answer to: {question}"

  monkeypatch.setenv("GEMINI_API_KEY", "test-key")
  monkeypatch.setattr(faq, "ask_gemini", answer)
  monkeypatch.setattr(faq, "verse_limits", VerseLimits)
  yield calls
  faq.clear_cache()


def test_there_are_thirty_two_questions_in_six_groups():
  listing = client.get("/faq").json()

  assert listing["available"] is True
  assert [group["heading"] for group in listing["groups"]][0] == "God, faith, and doubt"
  assert len(listing["groups"]) == 6
  identifiers = [entry["id"] for group in listing["groups"] for entry in group["questions"]]
  assert identifiers == list(range(1, 33))
  assert listing["groups"][0]["questions"][0]["question"] == "How do I know God exists?"
  assert listing["groups"][1]["questions"][3]["question"] == "Is a Christian saved by grace alone?"
  assert listing["groups"][5]["questions"][1]["question"] == "What is the Apostles’ Creed and what does it say?"
  assert listing["groups"][5]["questions"][5]["question"].startswith("What does the Bible actually say about the end times")


def test_grace_alone_is_answered_from_the_protestant_teaching_only():
  get_answer(9)
  get_answer(7)

  assert faq.QUESTIONS[9] == "Is a Christian saved by grace alone?"
  assert prompts[0].startswith(faq.SYSTEM_PROMPT)
  assert "Protestant (Reformation)" in prompts[0] and "Ephesians 2:8-9" in prompts[0]
  assert prompts[1] == faq.SYSTEM_PROMPT


def test_the_listing_says_when_no_key_is_set(monkeypatch):
  monkeypatch.setenv("GEMINI_API_KEY", "  ")

  assert client.get("/faq").json()["available"] is False


def test_an_answer_is_asked_once_and_kept_for_a_day(fake_gemini):
  first = client.post("/faq/answer", json={"question_id": 7})
  second = client.post("/faq/answer", json={"question_id": 7})

  assert first.status_code == 200
  assert first.json() == {
    "question_id": 7,
    "question": "What evidence is there that Jesus rose from the dead?",
    "answer": "Answer to: What evidence is there that Jesus rose from the dead?",
    "references": [],
  }
  assert second.json() == first.json()
  assert fake_gemini == ["What evidence is there that Jesus rose from the dead?"]


def test_an_answer_is_asked_again_after_a_day(fake_gemini):
  get_answer(1, now=1000.0)
  get_answer(1, now=1000.0 + ANSWER_CACHE_SECONDS - 1)
  assert len(fake_gemini) == 1

  get_answer(1, now=1000.0 + ANSWER_CACHE_SECONDS)
  assert len(fake_gemini) == 2


def test_only_listed_questions_can_be_asked(fake_gemini):
  for question_id in (0, 33, -1):
    response = client.post("/faq/answer", json={"question_id": question_id})
    assert response.status_code == 404
  assert client.post("/faq/answer", json={"question": "Write me a poem"}).status_code == 422
  assert client.post("/faq/answer", json={"question_id": "Write me a poem"}).status_code == 422
  with pytest.raises(UnknownQuestion):
    get_answer(99)
  assert fake_gemini == []


def test_a_failure_gives_a_clear_message_and_is_not_kept(monkeypatch):
  calls = []

  def failing(question, system_prompt=None):
    calls.append(question)
    raise FaqUnavailable("Gemini request failed (ServerError): 500")

  monkeypatch.setattr(faq, "ask_gemini", failing)
  response = client.post("/faq/answer", json={"question_id": 3})

  assert response.status_code == 503
  assert "not available" in response.json()["detail"]
  assert "Gemini request failed" not in response.json()["detail"]

  client.post("/faq/answer", json={"question_id": 3})
  assert len(calls) == 2


def test_a_missing_key_is_refused_before_calling_google(monkeypatch):
  monkeypatch.undo()
  monkeypatch.setenv("GEMINI_API_KEY", "")

  with pytest.raises(FaqUnavailable, match="not set up"):
    faq.ask_gemini("How should I pray?")


def test_the_real_call_sends_the_instructions_and_returns_the_text(monkeypatch):
  monkeypatch.undo()
  monkeypatch.setenv("GEMINI_API_KEY", "test-key")
  monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
  sent = {}

  class FakeResponse:
    text = "  **Pray** simply (Matthew 6:9-13).  "

  class FakeModels:
    def generate_content(self, model, contents, config):
      sent.update(model=model, contents=contents, config=config)
      return FakeResponse()

  class FakeClient:
    def __init__(self, api_key, http_options):
      sent["api_key"] = api_key
      self.models = FakeModels()

  from google import genai

  monkeypatch.setattr(genai, "Client", FakeClient)

  assert faq.ask_gemini("How should I pray?") == "**Pray** simply (Matthew 6:9-13)."
  assert sent["api_key"] == "test-key"
  assert sent["model"] == "gemini-test-model"
  assert sent["contents"] == "How should I pray?"
  assert sent["config"].system_instruction == faq.SYSTEM_PROMPT


def test_an_empty_answer_counts_as_a_failure(monkeypatch):
  monkeypatch.undo()
  monkeypatch.setenv("GEMINI_API_KEY", "test-key")

  class FakeModels:
    def generate_content(self, model, contents, config):
      return type("Response", (), {"text": None})()

  class FakeClient:
    def __init__(self, api_key, http_options):
      self.models = FakeModels()

  from google import genai

  monkeypatch.setattr(genai, "Client", FakeClient)

  with pytest.raises(FaqUnavailable, match="empty"):
    faq.ask_gemini("How should I pray?")


def test_the_prompt_keeps_licensed_bibles_out():
  assert "never the NIV, NASB or" in faq.SYSTEM_PROMPT
  assert "where faithful christians disagree" in faq.SYSTEM_PROMPT.lower()


def test_the_next_model_is_tried_when_one_is_busy(monkeypatch):
  monkeypatch.undo()
  monkeypatch.setenv("GEMINI_API_KEY", "test-key")
  monkeypatch.setenv("GEMINI_MODEL", "busy-model, good-model")
  tried = []

  class FakeModels:
    def generate_content(self, model, contents, config):
      tried.append(model)
      if model == "busy-model":
        raise RuntimeError("503 UNAVAILABLE high demand")
      return type("Response", (), {"text": "An answer"})()

  class FakeClient:
    def __init__(self, api_key, http_options):
      self.models = FakeModels()

  from google import genai

  monkeypatch.setattr(genai, "Client", FakeClient)

  assert faq.ask_gemini("How should I pray?") == "An answer"
  assert tried == ["busy-model", "good-model"]

  monkeypatch.delenv("GEMINI_MODEL")
  tried.clear()
  faq.ask_gemini("How should I pray?")
  assert tried == ["gemini-3.6-flash"]


def test_the_references_in_an_answer_are_listed_once_with_their_verse(monkeypatch):
  monkeypatch.setattr(
    faq,
    "ask_gemini",
    lambda question, system_prompt=None: "See **John 3:16** and Romans 8:38–39; also 1 John 4:1.\n\n- John 3:16 again (Genesis 99:1).",
  )

  references = client.post("/faq/answer", json={"question_id": 8}).json()["references"]

  assert references == [
    {"text": "John 3:16", "book": 43, "chapter": 3, "verse": 16},
    {"text": "Romans 8:38–39", "book": 45, "chapter": 8, "verse": 38},
    {"text": "1 John 4:1", "book": 62, "chapter": 4, "verse": 1},
  ]


def test_a_reference_to_a_verse_that_does_not_exist_is_not_listed():
  assert faq.list_references("Read John 3:99 and Obadiah 1:5.") == [
    {"text": "Obadiah 1:5", "book": 31, "chapter": 1, "verse": 5},
  ]


def test_the_answer_still_shows_when_the_verse_table_cannot_be_read(monkeypatch):
  def broken():
    raise RuntimeError("no database")

  monkeypatch.setattr(faq, "verse_limits", broken)
  monkeypatch.setattr(faq, "ask_gemini", lambda question, system_prompt=None: "Read John 3:16.")

  response = client.post("/faq/answer", json={"question_id": 2})

  assert response.status_code == 200
  assert response.json()["answer"] == "Read John 3:16."
  assert response.json()["references"] == []

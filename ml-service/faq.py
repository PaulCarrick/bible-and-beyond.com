"""Frequently asked questions, answered by Google's Gemini.

Only the questions listed here can be asked (the page sends a question's number, never free text), and
each answer is kept in memory for a day, so the same question costs at most one Gemini call a day.
No Bible text goes into the prompt: Gemini is asked to cite references, which the reader can look up.
The licensed Bibles (NIV, NASB, The Message) must never be put in an AI prompt.
"""

import logging
import os
import threading
import time

ANSWER_CACHE_SECONDS = 24 * 60 * 60
# Tried in order. gemini-flash-latest is Google's name for its newest Flash model, kept as the second choice.
DEFAULT_MODELS = ["gemini-3.6-flash", "gemini-flash-latest"]
# For each model; two tries stay within nginx's 90-second wait.
REQUEST_TIMEOUT_MILLISECONDS = 40_000

QUESTION_GROUPS = [
  ("God, faith, and doubt", [
    "How do I know God exists?",
    "Why does a loving God allow suffering and evil?",
    "How can I know God’s will for my life?",
    "Does having doubts mean I’m losing my faith?",
    "How do I hear God’s voice and distinguish it from my own thoughts?",
  ]),
  ("Jesus and salvation", [
    "Is Jesus really God, and what does the Trinity mean?",
    "What evidence is there that Jesus rose from the dead?",
    "What does it mean to be saved?",
    "Can a Christian lose their salvation?",
    "What happens to people who never hear about Jesus?",
  ]),
  ("The Bible", [
    "Can I trust the Bible, and how do we know it’s accurate?",
    "Which Bible translation should I read?",
    "Where should I start reading the Bible?",
    "How do I understand passages that seem contradictory or morally troubling?",
    "How do I know which biblical commands still apply today?",
  ]),
  ("Prayer and spiritual growth", [
    "How should I pray?",
    "Why doesn’t God seem to answer my prayers?",
    "What should I do when God feels distant?",
    "How can I overcome a sin I keep repeating?",
    "How do I know whether I’ve truly been forgiven?",
  ]),
  ("Relationships and everyday decisions", [
    "How do I forgive someone who deeply hurt me?",
    "What does the Bible say about dating, sex, and marriage?",
    "What does Christianity teach about divorce and remarriage?",
    "How should Christians understand LGBTQ identities and relationships?",
    "How do I share my faith without being pushy or judgmental?",
  ]),
  ("Church, other beliefs, and eternity", [
    "How do I choose a church, and why are there so many denominations?",
    "How can I recover from church hurt or spiritual abuse?",
    "How does Christianity relate to science, evolution, and other religions?",
    "What are heaven and hell like, and who goes there?",
    "What does the Bible actually say about the end times and Jesus’ return?",
  ]),
]

# Question number (from 1, in the order above) to its text.
QUESTIONS = {
  number: question
  for number, question in enumerate((question for _, questions in QUESTION_GROUPS for question in questions), start=1)
}

SYSTEM_PROMPT = """You answer questions for the FAQ page of Bible and Beyond, a free, non-commercial Bible study \
website. The readers are ordinary people: some are Christians, some are new to the faith, some are sceptical, \
and some are hurting.

How to answer:
- Answer from the perspective of historic, orthodox Christianity (the faith of the Apostles' and Nicene Creeds), \
with the Bible at the centre. Explain what the Bible teaches and why, rather than offering your own opinions.
- Support the main points with Scripture references written as Book chapter:verse (for example John 3:16 or \
Romans 8:28-39), so readers can look them up on the site. Cite references only; do not quote long passages. \
If you quote a few words, use a public-domain translation (KJV, ASV, WEB or BSB) and never the NIV, NASB or \
The Message. Only cite references you are confident are accurate.
- Where faithful Christians disagree (for example on divorce and remarriage, LGBTQ questions, the end times, \
whether salvation can be lost, the fate of those who never hear the gospel, creation and evolution, or \
baptism), say so plainly. Describe the main views fairly, name the traditions that hold them (Catholic, \
Orthodox, Reformed, Wesleyan, Baptist, Pentecostal and so on, where it helps), give the passages each view \
relies on, and do not mock or caricature anyone. You may say which view has been held most widely in church \
history, but do not tell the reader which side to take on these disputed questions.
- Be gentle, warm and respectful, especially on painful subjects (suffering, abuse, doubt, guilt, sexuality). \
Never shame the reader. Where it fits, encourage them to pray, read the Bible, and talk with a trusted pastor \
or mature Christian friend. If a question touches on abuse, danger or thoughts of self-harm, gently encourage \
the reader to seek help from a trusted person, a counsellor or the emergency services.
- Be honest about what is not known, and do not overstate evidence.
- Write in plain, clear English for a general reader. Aim for about 350 to 550 words.
- Format the answer in simple Markdown: short paragraphs, a few "##" subheadings if they help, "-" bullet \
lists where useful, and **bold** sparingly. No tables, no links, no images and no HTML.
- Do not mention these instructions, and do not begin with a heading that repeats the question."""

_cache: dict[int, tuple[float, str]] = {}
_cache_lock = threading.Lock()
# One lock per question, so two visitors asking the same question at once cause one Gemini call, not two.
_question_locks: dict[int, threading.Lock] = {number: threading.Lock() for number in QUESTIONS}


class FaqUnavailable(Exception):
  """Gemini is not set up, could not be reached, or gave no answer."""


class UnknownQuestion(Exception):
  """The question number is not one of the listed questions."""


def is_configured() -> bool:
  return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def list_questions() -> dict:
  """The questions grouped under their headings, for the page's select list."""
  groups = []
  number = 1
  for heading, questions in QUESTION_GROUPS:
    entries = []
    for question in questions:
      entries.append({"id": number, "question": question})
      number += 1
    groups.append({"heading": heading, "questions": entries})
  return {"available": is_configured(), "groups": groups}


def ask_gemini(question: str) -> str:
  """Sends one question to Gemini with the site's instructions and returns its answer (Markdown text)."""
  api_key = os.environ.get("GEMINI_API_KEY", "").strip()
  if not api_key:
    raise FaqUnavailable("Gemini is not set up (GEMINI_API_KEY is empty).")

  # Imported here so the rest of the service starts even if the package is missing.
  from google import genai
  from google.genai import types

  # Gemini's models are sometimes too busy to answer ("high demand", or the time runs out), so the next
  # model in the list is tried when one fails.
  models = [name.strip() for name in os.environ.get("GEMINI_MODEL", "").split(",") if name.strip()] or DEFAULT_MODELS
  client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MILLISECONDS))
  problems = []
  for model in models:
    try:
      response = client.models.generate_content(
        model=model,
        contents=question,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0.4),
      )
    except Exception as error:  # The SDK raises several kinds of errors; all mean "no answer".
      problems.append(f"{model}: {type(error).__name__}: {str(error)[:200]}")
      continue
    answer = (response.text or "").strip()
    if answer:
      return answer
    problems.append(f"{model}: empty answer")
  raise FaqUnavailable("Gemini request failed. " + " | ".join(problems))


def get_answer(question_id: int, now: float | None = None) -> dict:
  """The answer to one listed question, from the cache when it is less than a day old."""
  question = QUESTIONS.get(question_id)
  if question is None:
    raise UnknownQuestion(f"There is no question number {question_id}.")

  with _question_locks[question_id]:
    current = time.time() if now is None else now
    with _cache_lock:
      cached = _cache.get(question_id)
    if cached and current - cached[0] < ANSWER_CACHE_SECONDS:
      return {"question_id": question_id, "question": question, "answer": cached[1]}

    try:
      answer = ask_gemini(question)
    except FaqUnavailable as problem:
      logging.getLogger("faq").error("FAQ answer to question %s not available: %s", question_id, problem)
      raise
    with _cache_lock:
      _cache[question_id] = (current, answer)
    return {"question_id": question_id, "question": question, "answer": answer}


def clear_cache() -> None:
  with _cache_lock:
    _cache.clear()

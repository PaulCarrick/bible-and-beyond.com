"""Editing a site's own FAQ questions (faq_questions, migration 063) and the words about who the site is for
(the faq_about site setting, added to Gemini's instructions). Used by the Drupal "FAQ questions" page through
scripts/manage_faq_questions.py (added 2026-11-20 at the owner's request).

While a site has none of its own, its FAQ is the list built into faq.py. The first change copies that list into
the table, so the change is made to it and the rest stay. Questions are numbered by their table id; a built-in
question keeps the number the page showed (from 1) until then.

A question's answer and the site owner's note are kept by its text. Rewording a question moves its note with it
(unless the new wording has one already); its answer is fetched again for the new wording.
"""

from faq import BUILT_IN_GROUPS, question_groups
from search import connect
from site_settings import SettingsProblem, get_settings, save_settings

MAX_QUESTIONS = 200
QUESTION_LIMIT = 300
HEADING_LIMIT = 200
ABOUT_LIMIT = 2000


class QuestionsProblem(Exception):
  """The change cannot be made; the text says why and is fit to show the administrator."""


def describe() -> dict:
  with connect() as connection:
    own = connection.execute("SELECT count(*) FROM faq_questions").fetchone()[0]
  groups = [
    {"heading": heading, "questions": [{"id": question_id, "question": question} for question_id, question in listed]}
    for heading, listed in question_groups()
  ]
  return {"source": "site" if own else "built-in", "about": get_settings()["faq_about"], "groups": groups}


def _text(value, what: str, limit: int) -> str:
  text = " ".join(str(value or "").split())
  if not text or len(text) > limit:
    raise QuestionsProblem(f"The {what} must be 1 to {limit} characters.")
  return text


def _renumber(connection) -> None:
  rows = connection.execute("SELECT id FROM faq_questions ORDER BY position, id").fetchall()
  for position, (question_id,) in enumerate(rows, start=1):
    connection.execute("UPDATE faq_questions SET position = %s WHERE id = %s", (position, question_id))


def _make_own(connection) -> None:
  """Copies the built-in list into the table, when the site has none of its own yet."""
  if connection.execute("SELECT count(*) FROM faq_questions").fetchone()[0]:
    return
  position = 0
  for heading, questions in BUILT_IN_GROUPS:
    for question in questions:
      position += 1
      connection.execute("INSERT INTO faq_questions (heading, question, position) VALUES (%s, %s, %s)", (heading, question, position))


def _row(connection, question_id: int, question_text: str | None):
  """The table row of a question shown with this number (looked up by its text when the list was the built-in one)."""
  if question_text is not None:
    row = connection.execute("SELECT id, heading, question, position FROM faq_questions WHERE question = %s", (question_text,)).fetchone()
  else:
    row = connection.execute("SELECT id, heading, question, position FROM faq_questions WHERE id = %s", (question_id,)).fetchone()
  if row is None:
    raise QuestionsProblem("That question was not found. It may have been changed or deleted.")
  return row


def _shown_text(question_id: int) -> str | None:
  """The text of the question shown with this number on a site still using the built-in list, else None."""
  if describe()["source"] == "site":
    return None
  for group in describe()["groups"]:
    for entry in group["questions"]:
      if entry["id"] == question_id:
        return entry["question"]
  raise QuestionsProblem("That question was not found. It may have been changed or deleted.")


def get_question(question_id: int) -> dict:
  for group in describe()["groups"]:
    for entry in group["questions"]:
      if entry["id"] == question_id:
        return {**entry, "heading": group["heading"]}
  raise QuestionsProblem("That question was not found. It may have been changed or deleted.")


def add_question(heading, question) -> dict:
  heading, question = _text(heading, "heading", HEADING_LIMIT), _text(question, "question", QUESTION_LIMIT)
  with connect() as connection:
    _make_own(connection)
    if connection.execute("SELECT count(*) FROM faq_questions").fetchone()[0] >= MAX_QUESTIONS:
      raise QuestionsProblem(f"There can be up to {MAX_QUESTIONS} questions. Delete one first.")
    if connection.execute("SELECT 1 FROM faq_questions WHERE question = %s", (question,)).fetchone():
      raise QuestionsProblem("That question is on the list already.")
    # At the end of its heading's group, or at the end of the list for a new heading.
    last = connection.execute("SELECT max(position) FROM faq_questions WHERE heading = %s", (heading,)).fetchone()[0]
    if last is None:
      last = connection.execute("SELECT coalesce(max(position), 0) FROM faq_questions").fetchone()[0]
    connection.execute("UPDATE faq_questions SET position = position + 1 WHERE position > %s", (last,))
    new_id = connection.execute(
      "INSERT INTO faq_questions (heading, question, position) VALUES (%s, %s, %s) RETURNING id", (heading, question, last + 1)
    ).fetchone()[0]
    _renumber(connection)
  return get_question(new_id)


def update_question(question_id: int, heading, question) -> dict:
  heading, question = _text(heading, "heading", HEADING_LIMIT), _text(question, "question", QUESTION_LIMIT)
  shown = _shown_text(question_id)
  with connect() as connection:
    _make_own(connection)
    row_id, old_heading, old_question, position = _row(connection, question_id, shown)
    if question != old_question and connection.execute("SELECT 1 FROM faq_questions WHERE question = %s", (question,)).fetchone():
      raise QuestionsProblem("Another question already has that wording.")
    connection.execute("UPDATE faq_questions SET heading = %s, question = %s WHERE id = %s", (heading, question, row_id))
    if heading != old_heading:
      # Under a new heading it goes last in that heading's group (or last in the list for a new heading): with every
      # position doubled, the place just after that one is free.
      connection.execute("UPDATE faq_questions SET position = position * 2")
      last = connection.execute(
        "SELECT max(position) FROM faq_questions WHERE heading = %s AND id <> %s", (heading, row_id)
      ).fetchone()[0]
      if last is None:
        last = connection.execute("SELECT max(position) FROM faq_questions").fetchone()[0]
      connection.execute("UPDATE faq_questions SET position = %s WHERE id = %s", (last + 1, row_id))
      _renumber(connection)
    if question != old_question and not connection.execute("SELECT 1 FROM faq_notes WHERE question = %s", (question,)).fetchone():
      connection.execute("UPDATE faq_notes SET question = %s, updated_at = now() WHERE question = %s", (question, old_question))
  return get_question(row_id)


def delete_question(question_id: int) -> dict:
  shown = _shown_text(question_id)
  with connect() as connection:
    _make_own(connection)
    row_id, heading, question, _ = _row(connection, question_id, shown)
    if connection.execute("SELECT count(*) FROM faq_questions").fetchone()[0] <= 1:
      raise QuestionsProblem("The FAQ needs at least one question. Add another before deleting this one.")
    connection.execute("DELETE FROM faq_questions WHERE id = %s", (row_id,))
    _renumber(connection)
  return {"id": row_id, "heading": heading, "question": question}


def move_question(question_id: int, direction: str) -> dict:
  """Up or down one place within its heading's group."""
  if direction not in ("up", "down"):
    raise QuestionsProblem("A question moves up or down.")
  shown = _shown_text(question_id)
  with connect() as connection:
    _make_own(connection)
    row_id, heading, _, position = _row(connection, question_id, shown)
    neighbour = connection.execute(
      f"""SELECT id, position FROM faq_questions WHERE heading = %s AND position {'<' if direction == 'up' else '>'} %s
      ORDER BY position {'DESC' if direction == 'up' else 'ASC'} LIMIT 1""",
      (heading, position),
    ).fetchone()
    if neighbour is not None:
      connection.execute("UPDATE faq_questions SET position = %s WHERE id = %s", (neighbour[1], row_id))
      connection.execute("UPDATE faq_questions SET position = %s WHERE id = %s", (position, neighbour[0]))
  return get_question(row_id)


def set_about(text) -> str:
  about = " ".join(str(text or "").split())
  if len(about) > ABOUT_LIMIT:
    raise QuestionsProblem(f"The words about the site can be at most {ABOUT_LIMIT} characters.")
  try:
    return save_settings({"faq_about": about})["faq_about"]
  except SettingsProblem as problem:
    raise QuestionsProblem(str(problem)) from problem


def replace_all(document) -> dict:
  """The whole list at once: {"about", "groups": [{"heading", "questions": [...]}]}."""
  if not isinstance(document, dict) or not isinstance(document.get("groups"), list) or not document["groups"]:
    raise QuestionsProblem('Give {"groups": [{"heading": ..., "questions": [...]}], "about": ...}.')
  rows, seen = [], set()
  for group in document["groups"]:
    if not isinstance(group, dict) or not isinstance(group.get("questions"), list) or not group["questions"]:
      raise QuestionsProblem("Every group needs a heading and at least one question.")
    heading = _text(group.get("heading"), "heading", HEADING_LIMIT)
    for question in group["questions"]:
      question = _text(question, "question", QUESTION_LIMIT)
      if question in seen:
        raise QuestionsProblem(f"This question is listed twice: {question}")
      seen.add(question)
      rows.append((heading, question))
  if len(rows) > MAX_QUESTIONS:
    raise QuestionsProblem(f"At most {MAX_QUESTIONS} questions.")
  if not isinstance(document.get("about", ""), str):
    raise QuestionsProblem('"about" must be text.')
  set_about(document.get("about", ""))
  with connect() as connection:
    connection.execute("DELETE FROM faq_questions")
    for position, (heading, question) in enumerate(rows, start=1):
      connection.execute("INSERT INTO faq_questions (heading, question, position) VALUES (%s, %s, %s)", (heading, question, position))
  return describe()


def use_built_in() -> dict:
  """Back to the built-in list, with no words about the site."""
  set_about("")
  with connect() as connection:
    connection.execute("DELETE FROM faq_questions")
  return describe()

"""Show or replace this site's own FAQ questions (faq_questions, migration 063) and the words about who the site is
for (the faq_about site setting, added to Gemini's instructions). While a site has none of its own, its FAQ is the
list built into faq.py.

Every command prints one JSON object with "ok". The new list goes on the standard input as JSON:

    manage_faq_questions.py list
    manage_faq_questions.py replace     input {"about": "...", "groups": [{"heading": "...", "questions": ["..."]}]}
    manage_faq_questions.py built-in    go back to the built-in list (and no "about")

Answers and the site owner's notes are kept by the question's text, so a question kept in a new list keeps them.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import faq  # noqa: E402
from search import connect  # noqa: E402
from site_settings import SettingsProblem, get_settings, save_settings  # noqa: E402

MAX_QUESTIONS = 200
QUESTION_LIMIT = 300
HEADING_LIMIT = 200


class QuestionsProblem(Exception):
  pass


def describe() -> dict:
  with connect() as connection:
    own = connection.execute("SELECT count(*) FROM faq_questions").fetchone()[0]
  groups = [{"heading": heading, "questions": [question for _, question in listed]} for heading, listed in faq.question_groups()]
  return {"ok": True, "source": "site" if own else "built-in", "about": get_settings()["faq_about"], "groups": groups}


def checked(document) -> tuple[str, list[tuple[str, str]]]:
  if not isinstance(document, dict) or not isinstance(document.get("groups"), list) or not document["groups"]:
    raise QuestionsProblem('Give {"groups": [{"heading": ..., "questions": [...]}], "about": ...}.')
  rows, seen = [], set()
  for group in document["groups"]:
    if not isinstance(group, dict) or not isinstance(group.get("questions"), list) or not group["questions"]:
      raise QuestionsProblem("Every group needs a heading and at least one question.")
    heading = " ".join(str(group.get("heading") or "").split())
    if not heading or len(heading) > HEADING_LIMIT:
      raise QuestionsProblem(f"Every heading must be 1 to {HEADING_LIMIT} characters.")
    for question in group["questions"]:
      question = " ".join(str(question or "").split())
      if not question or len(question) > QUESTION_LIMIT:
        raise QuestionsProblem(f"Every question must be 1 to {QUESTION_LIMIT} characters.")
      if question in seen:
        raise QuestionsProblem(f"This question is listed twice: {question}")
      seen.add(question)
      rows.append((heading, question))
  if len(rows) > MAX_QUESTIONS:
    raise QuestionsProblem(f"At most {MAX_QUESTIONS} questions.")
  about = document.get("about", "")
  if not isinstance(about, str):
    raise QuestionsProblem('"about" must be text.')
  return " ".join(about.split()), rows


def replace(document) -> dict:
  about, rows = checked(document)
  try:
    save_settings({"faq_about": about})
  except SettingsProblem as problem:
    raise QuestionsProblem(str(problem)) from problem
  with connect() as connection:
    connection.execute("DELETE FROM faq_questions")
    for position, (heading, question) in enumerate(rows, start=1):
      connection.execute("INSERT INTO faq_questions (heading, question, position) VALUES (%s, %s, %s)", (heading, question, position))
  return describe()


def built_in() -> dict:
  save_settings({"faq_about": ""})
  with connect() as connection:
    connection.execute("DELETE FROM faq_questions")
  return describe()


def main():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("command", choices=["list", "replace", "built-in"])
  arguments = parser.parse_args()
  try:
    if arguments.command == "list":
      result = describe()
    elif arguments.command == "built-in":
      result = built_in()
    else:
      try:
        document = json.loads(sys.stdin.read())
      except json.JSONDecodeError as error:
        raise QuestionsProblem("The list could not be read as JSON.") from error
      result = replace(document)
  except QuestionsProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
  main()

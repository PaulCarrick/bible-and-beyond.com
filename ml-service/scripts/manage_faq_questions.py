"""Show or change this site's own FAQ questions and the words about who the site is for (faq_questions.py). Used by
the Drupal "FAQ questions" page. While a site has none of its own, its FAQ is the list built into faq.py; the first
change makes that list the site's own.

Every command prints one JSON object with "ok": true, or "ok": false and an "error" for the administrator (the exit
status is then not 0). Details go on the standard input as JSON.

    manage_faq_questions.py list
    manage_faq_questions.py get --id=ID
    manage_faq_questions.py add                         input {"heading": "...", "question": "..."}
    manage_faq_questions.py update --id=ID              input {"heading": "...", "question": "..."}
    manage_faq_questions.py delete --id=ID
    manage_faq_questions.py move --id=ID --direction=up|down
    manage_faq_questions.py about                       input {"about": "..."}
    manage_faq_questions.py replace                     input {"about": "...", "groups": [{"heading": "...", "questions": ["..."]}]}
    manage_faq_questions.py built-in                    back to the built-in list (and no words about the site)
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import faq_questions  # noqa: E402
from faq_questions import QuestionsProblem  # noqa: E402


def parse_arguments(arguments=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  for name in ("list", "add", "about", "replace", "built-in"):
    commands.add_parser(name)
  for name in ("get", "update", "delete"):
    commands.add_parser(name).add_argument("--id", type=int, required=True)
  move = commands.add_parser("move")
  move.add_argument("--id", type=int, required=True)
  move.add_argument("--direction", choices=["up", "down"], required=True)
  return parser.parse_args(arguments)


def read_input() -> dict:
  try:
    details = json.loads(sys.stdin.read())
  except json.JSONDecodeError as error:
    raise QuestionsProblem("The details could not be read.") from error
  if not isinstance(details, dict):
    raise QuestionsProblem("The details could not be read.")
  return details


def run(arguments) -> dict:
  command = arguments.command
  if command == "list":
    return faq_questions.describe()
  if command == "get":
    return {"question": faq_questions.get_question(arguments.id)}
  if command == "delete":
    return {"question": faq_questions.delete_question(arguments.id)}
  if command == "move":
    return {"question": faq_questions.move_question(arguments.id, arguments.direction)}
  if command == "built-in":
    return faq_questions.use_built_in()
  details = read_input()
  if command == "add":
    return {"question": faq_questions.add_question(details.get("heading"), details.get("question"))}
  if command == "update":
    return {"question": faq_questions.update_question(arguments.id, details.get("heading"), details.get("question"))}
  if command == "about":
    return {"about": faq_questions.set_about(details.get("about"))}
  return faq_questions.replace_all(details)


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except QuestionsProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps({"ok": True, **result}, ensure_ascii=False))


if __name__ == "__main__":
  main()

"""List, add, change and delete the site owner's notes on the FAQ answers. Used by the Drupal "FAQ notes" page.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0.

    manage_faq_notes.py questions          the FAQ questions, grouped as on the FAQ page
    manage_faq_notes.py list               every note (with a short preview of its text)
    manage_faq_notes.py get --id=3
    manage_faq_notes.py create             reads {"question": ..., "html": ...} as JSON on the standard input
    manage_faq_notes.py update --id=3      the same
    manage_faq_notes.py delete --id=3

The note is sent on the standard input rather than as an argument, because it can be long.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faq import QUESTION_GROUPS  # noqa: E402
from faq_notes import NoteProblem, create_note, delete_note, get_note, list_notes, update_note  # noqa: E402


def parse_arguments():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("questions")
  commands.add_parser("list")
  commands.add_parser("create")
  for name in ("get", "update", "delete"):
    commands.add_parser(name).add_argument("--id", type=int, required=True)
  return parser.parse_args()


def read_note() -> tuple[str, str]:
  try:
    values = json.loads(sys.stdin.read())
  except json.JSONDecodeError as error:
    raise NoteProblem("The note could not be read.") from error
  if not isinstance(values, dict) or not isinstance(values.get("question"), str) or not isinstance(values.get("html"), str):
    raise NoteProblem("The note could not be read.")
  return values["question"], values["html"]


def list_question_groups() -> list[dict]:
  groups = []
  number = 1
  for heading, questions in QUESTION_GROUPS:
    entries = []
    for question in questions:
      entries.append({"number": number, "question": question})
      number += 1
    groups.append({"heading": heading, "questions": entries})
  return groups


def run(arguments) -> dict:
  if arguments.command == "questions":
    return {"ok": True, "groups": list_question_groups()}
  if arguments.command == "list":
    return {"ok": True, "notes": list_notes()}
  if arguments.command == "get":
    return {"ok": True, "note": get_note(arguments.id)}
  if arguments.command == "delete":
    return {"ok": True, "note": delete_note(arguments.id)}
  question, html = read_note()
  if arguments.command == "create":
    return {"ok": True, "note": create_note(question, html)}
  return {"ok": True, "note": update_note(arguments.id, question, html)}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except NoteProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

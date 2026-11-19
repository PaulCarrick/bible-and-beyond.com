"""List, add, change and delete tasks (admin_tasks.py). Used by the Drupal "Tasks" page.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0. The details go on the standard input as JSON.

    manage_tasks.py list [--owner=UID]          everyone's, or one person's
    manage_tasks.py get --id=ID
    manage_tasks.py create --owner=UID          input {name, description, repeat, weekday, first_date, day_of_month,
                                                first_notification, second_notification, owner_name}; the formatted
                                                fields are {html} or {text}
    manage_tasks.py update --id=ID              input as create
    manage_tasks.py delete --id=ID
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import admin_tasks  # noqa: E402
from admin_tasks import TaskProblem  # noqa: E402


def parse_arguments(arguments=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("list").add_argument("--owner", type=int)
  commands.add_parser("create").add_argument("--owner", type=int, required=True)
  for name in ("get", "update", "delete"):
    commands.add_parser(name).add_argument("--id", type=int, required=True)
  return parser.parse_args(arguments)


def read_details() -> dict:
  try:
    details = json.loads(sys.stdin.read())
  except json.JSONDecodeError as error:
    raise TaskProblem("The task could not be read.") from error
  if not isinstance(details, dict):
    raise TaskProblem("The task could not be read.")
  return details


def run(arguments) -> dict:
  if arguments.command == "list":
    return {"ok": True, "tasks": admin_tasks.list_tasks(arguments.owner)}
  if arguments.command == "get":
    return {"ok": True, "task": admin_tasks.get_task(arguments.id)}
  if arguments.command == "delete":
    return {"ok": True, "task": admin_tasks.delete_task(arguments.id)}
  details = read_details()
  if arguments.command == "create":
    return {"ok": True, "task": admin_tasks.create_task(details, arguments.owner, str(details.get("owner_name") or ""))}
  return {"ok": True, "task": admin_tasks.update_task(arguments.id, details)}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except TaskProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

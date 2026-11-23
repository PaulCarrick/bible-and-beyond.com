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
    manage_tasks.py schedule-options --id=ID    the task, its next 4 dates and the site users, for the Schedule form
    manage_tasks.py schedules [--owner=UID]     the scheduled tasks, of everyone's tasks or one person's
    manage_tasks.py get-schedule --schedule=ID
    manage_tasks.py add-schedule --id=ID --by=UID   input {user_id, on_date, created_by_name}
    manage_tasks.py update-schedule --schedule=ID   input {user_id, on_date}
    manage_tasks.py remove-schedule --schedule=ID
    manage_tasks.py day-options --date=YYYY-MM-DD [--owner=UID]   the tasks falling on that date, and the site users
    manage_tasks.py day-dates [--owner=UID]                 the dates from today on with something scheduled
    manage_tasks.py day-people --date=YYYY-MM-DD [--owner=UID]   the people scheduled that day, with their tasks
    manage_tasks.py send-day-message --by=UID [--owner=UID]   input {on_date, user_ids, subject, message, signature_id, sender_name, sender_email}
    manage_tasks.py add-schedules --by=UID [--owner=UID]   input {on_date, created_by_name, items: [{task_id, user_id, note}]}
"""

import argparse
from datetime import date
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import admin_tasks  # noqa: E402
import day_messages  # noqa: E402
import scheduled_tasks  # noqa: E402
from admin_tasks import TaskProblem  # noqa: E402


def parse_arguments(arguments=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("list").add_argument("--owner", type=int)
  commands.add_parser("create").add_argument("--owner", type=int, required=True)
  for name in ("get", "update", "delete", "schedule-options"):
    commands.add_parser(name).add_argument("--id", type=int, required=True)
  commands.add_parser("schedules").add_argument("--owner", type=int)
  add = commands.add_parser("add-schedule")
  add.add_argument("--id", type=int, required=True)
  add.add_argument("--by", type=int, required=True)
  day = commands.add_parser("day-options")
  day.add_argument("--date", required=True)
  day.add_argument("--owner", type=int)
  commands.add_parser("day-dates").add_argument("--owner", type=int)
  day_people = commands.add_parser("day-people")
  day_people.add_argument("--date", required=True)
  day_people.add_argument("--owner", type=int)
  message = commands.add_parser("send-day-message")
  message.add_argument("--by", type=int, required=True)
  message.add_argument("--owner", type=int)
  # Uploaded files to attach, each with the name it had (repeat both, in the same order).
  message.add_argument("--attachment", action="append", default=[])
  message.add_argument("--attachment-name", action="append", default=[])
  many = commands.add_parser("add-schedules")
  many.add_argument("--by", type=int, required=True)
  many.add_argument("--owner", type=int)
  for name in ("get-schedule", "update-schedule", "remove-schedule"):
    commands.add_parser(name).add_argument("--schedule", type=int, required=True)
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
  if arguments.command == "schedule-options":
    return {"ok": True, **scheduled_tasks.options(arguments.id)}
  if arguments.command == "schedules":
    return {"ok": True, "schedules": scheduled_tasks.list_scheduled(arguments.owner)}
  if arguments.command == "get-schedule":
    return {"ok": True, "schedule": scheduled_tasks.get_scheduled(arguments.schedule)}
  if arguments.command == "day-dates":
    return {"ok": True, "dates": day_messages.dates(arguments.owner)}
  if arguments.command == "day-people":
    try:
      on_date = date.fromisoformat(arguments.date)
    except ValueError as error:
      raise TaskProblem("Choose a date.") from error
    return {"ok": True, "people": day_messages.people(on_date, arguments.owner)}
  if arguments.command == "day-options":
    try:
      on_date = date.fromisoformat(arguments.date)
    except ValueError as error:
      raise TaskProblem("Choose a date.") from error
    return {"ok": True, **scheduled_tasks.day_options(on_date, arguments.owner)}
  if arguments.command == "remove-schedule":
    return {"ok": True, "schedule": scheduled_tasks.remove_scheduled(arguments.schedule)}
  details = read_details()
  if arguments.command == "send-day-message":
    if len(arguments.attachment) != len(arguments.attachment_name):
      raise TaskProblem("The attached files could not be read.")
    attachments = list(zip(arguments.attachment, arguments.attachment_name))
    return {"ok": True, **day_messages.send(details, arguments.by, arguments.owner, attachments)}
  if arguments.command == "add-schedules":
    added = scheduled_tasks.add_many(details, arguments.by, str(details.get("created_by_name") or ""), arguments.owner)
    return {"ok": True, "schedules": added}
  if arguments.command == "add-schedule":
    return {"ok": True, "schedule": scheduled_tasks.add_scheduled(arguments.id, details, arguments.by, str(details.get("created_by_name") or ""))}
  if arguments.command == "update-schedule":
    return {"ok": True, "schedule": scheduled_tasks.update_scheduled(arguments.schedule, details)}
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

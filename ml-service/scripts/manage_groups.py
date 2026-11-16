"""Groups, their members and their messages (groups.py). Used by the Drupal "Groups" page.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the leader, and the exit status is not 0. Details (names, addresses, words) go on the
tool's standard input as JSON, never as arguments, so they never show in the server's process list.

    manage_groups.py list [--owner=UID]                every group, or one leader's
    manage_groups.py get --group=ID                    a group with its members and latest messages
    manage_groups.py save [--group=ID] --owner=UID [--set-owner]   input {name, description, owner_name, owner_email}
                                                       (--set-owner: the group moves to that leader)
    manage_groups.py delete --group=ID
    manage_groups.py add-member --group=ID             input {email, name, phone}
    manage_groups.py update-member --group=ID --member=ID   input {email, name, phone}
    manage_groups.py remove-member --group=ID --member=ID
    manage_groups.py preview-verse                     a random verse card (its name, picture and verse)
    manage_groups.py preview-picture                   input {text}: the words on a random picture
    manage_groups.py send --group=ID --kind=message|verse|picture   input {subject, text, card, verse, sent_by}
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import groups  # noqa: E402
from groups import GroupProblem  # noqa: E402


def parse_arguments(arguments=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("list").add_argument("--owner", type=int)
  for name in ("get", "delete", "add-member"):
    commands.add_parser(name).add_argument("--group", type=int, required=True)
  save = commands.add_parser("save")
  save.add_argument("--group", type=int)
  save.add_argument("--owner", type=int, required=True)
  save.add_argument("--set-owner", action="store_true")
  for name in ("update-member", "remove-member"):
    member = commands.add_parser(name)
    member.add_argument("--group", type=int, required=True)
    member.add_argument("--member", type=int, required=True)
  commands.add_parser("preview-verse")
  commands.add_parser("preview-picture")
  send = commands.add_parser("send")
  send.add_argument("--group", type=int, required=True)
  send.add_argument("--kind", required=True, choices=groups.KINDS)
  return parser.parse_args(arguments)


def read_input() -> dict:
  text = sys.stdin.read()
  if not text.strip():
    return {}
  try:
    details = json.loads(text)
  except ValueError as error:
    raise GroupProblem("The details could not be read.") from error
  if not isinstance(details, dict):
    raise GroupProblem("The details could not be read.")
  return details


def run(arguments) -> dict:
  command = arguments.command
  if command == "list":
    return {"ok": True, "groups": groups.list_groups(arguments.owner)}
  if command == "get":
    group = groups.get_group(arguments.group)
    group["sent"] = groups.list_sent(arguments.group)
    return {"ok": True, "group": group}
  if command == "save":
    details = read_input()
    group = groups.save_group(
      arguments.group, details, arguments.owner, str(details.get("owner_name", "")), str(details.get("owner_email", "")),
      set_owner=arguments.set_owner,
    )
    return {"ok": True, "group": group}
  if command == "delete":
    return {"ok": True, "group": groups.delete_group(arguments.group)}
  if command == "add-member":
    return {"ok": True, "member": groups.add_member(arguments.group, read_input())}
  if command == "update-member":
    return {"ok": True, "member": groups.update_member(arguments.group, arguments.member, read_input())}
  if command == "remove-member":
    return {"ok": True, "member": groups.remove_member(arguments.group, arguments.member)}
  if command == "preview-verse":
    return {"ok": True, "preview": groups.preview_verse()}
  if command == "preview-picture":
    return {"ok": True, "preview": groups.preview_picture(str(read_input().get("text", "")))}
  details = read_input()
  counts = groups.send(arguments.group, arguments.kind, details, str(details.get("sent_by", "")))
  return {"ok": True, "counts": counts}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except GroupProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

"""Groups, their members and their messages (groups.py). Used by the Drupal "Groups" page.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the leader, and the exit status is not 0. Details (names, addresses, words) go on the
tool's standard input as JSON, never as arguments, so they never show in the server's process list.

    manage_groups.py list [--owner=UID]                every group, or one leader's
    manage_groups.py get --group=ID                    a group with its members and latest messages
    manage_groups.py sent-copy --group=ID --message=ID the copy kept of one sent email (to, bcc, subject, html, text)
    manage_groups.py save [--group=ID] --owner=UID [--set-owner]   input {name, description, owner_name, owner_email}
                                                       (--set-owner: the group moves to that leader)
    manage_groups.py delete --group=ID
    manage_groups.py add-member --group=ID             input {email, name, phone}
    manage_groups.py restart-schedules --group=ID --member=ID   the member's stopped scheduled emails start again
    manage_groups.py candidates --group=ID             the site's accounts not in the group yet
    manage_groups.py add-accounts --group=ID           input {user_ids: [...]}: those accounts
    manage_groups.py update-member --group=ID --member=ID   input {email, name, phone}
    manage_groups.py remove-member --group=ID --member=ID
    manage_groups.py email-member --group=ID --member=ID    input {subject, html or text, signature_id, sent_by}: an email to that member only;
                                                       with {on_date, send_time, timezone} it is kept to send then
    manage_groups.py preview-verse                     a random verse card (its name, picture and verse)
    manage_groups.py preview-picture                   input {text}: the words on a random picture
    manage_groups.py send --group=ID --kind=message|verse|picture   input {subject, text, card, verse, sent_by}
    manage_groups.py add-schedule --group=ID           input {kind, subject, text, repeat, on_date, day_of_month,
                                                       weekday, week_of_month, send_time, timezone, created_by}
    manage_groups.py get-schedule --group=ID --schedule=ID
    manage_groups.py update-schedule --group=ID --schedule=ID   input as add-schedule
    manage_groups.py remove-schedule --group=ID --schedule=ID
    manage_groups.py test-schedule --group=ID --schedule=ID     send it now to the group's leader only
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import group_schedules  # noqa: E402
import groups  # noqa: E402
from groups import GroupProblem  # noqa: E402


def parse_arguments(arguments=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("list").add_argument("--owner", type=int)
  for name in ("get", "delete", "add-member", "add-schedule", "candidates", "add-accounts"):
    commands.add_parser(name).add_argument("--group", type=int, required=True)
  save = commands.add_parser("save")
  save.add_argument("--group", type=int)
  save.add_argument("--owner", type=int, required=True)
  save.add_argument("--set-owner", action="store_true")
  for name in ("update-member", "remove-member", "email-member", "restart-schedules"):
    member = commands.add_parser(name)
    member.add_argument("--group", type=int, required=True)
    member.add_argument("--member", type=int, required=True)
  for name in ("get-schedule", "update-schedule", "remove-schedule", "test-schedule"):
    schedule = commands.add_parser(name)
    schedule.add_argument("--group", type=int, required=True)
    schedule.add_argument("--schedule", type=int, required=True)
  sent_copy = commands.add_parser("sent-copy")
  sent_copy.add_argument("--group", type=int, required=True)
  sent_copy.add_argument("--message", type=int, required=True)
  # The administrator's own saved verse cards (saved_cards.admin_cards), to attach one to a message.
  my_cards = commands.add_parser("my-cards")
  my_cards.add_argument("--drupal-uid", type=int, required=True)
  my_cards.add_argument("--email", default="")
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
  # A saved card's account is found from the sender ("admin"), never given by the caller (groups.card_owner).
  details.pop("card_user_id", None)
  return details


def run(arguments) -> dict:
  command = arguments.command
  if command == "list":
    return {"ok": True, "groups": groups.list_groups(arguments.owner)}
  if command == "get":
    group = groups.get_group(arguments.group)
    group["sent"] = groups.list_sent(arguments.group)
    group["schedules"] = group_schedules.list_schedules(arguments.group)
    return {"ok": True, "group": group}
  if command == "sent-copy":
    return {"ok": True, "copy": groups.get_copy(arguments.group, arguments.message)}
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
  if command == "email-member":
    details = read_input()
    html = details.get("html")
    if details.get("on_date"):
      # "Send at" a later time: kept as a one-time scheduled email to that member (group_schedules.py).
      schedule = group_schedules.schedule_member_email(arguments.group, arguments.member, details, str(details.get("sent_by", "")))
      member = next(each for each in groups.get_group(arguments.group)["members"] if each["id"] == arguments.member)
      return {"ok": True, "member": {"id": member["id"], "name": member["name"]}, "schedule": schedule}
    signature_id = groups.leader_signature(groups.get_group(arguments.group), details.get("signature_id"))
    member = groups.email_member(
      arguments.group, arguments.member, str(details.get("text", "")), str(details.get("sent_by", "")),
      html=str(html) if html is not None else None, subject=str(details.get("subject") or ""),
      signature=groups.signature_words(signature_id), card=groups._saved_card(details),
    )
    return {"ok": True, "member": member}
  if command == "restart-schedules":
    return {"ok": True, "member": groups.restart_schedules(arguments.group, arguments.member)}
  if command == "candidates":
    return {"ok": True, "accounts": groups.list_candidates(arguments.group)}
  if command == "add-accounts":
    return {"ok": True, "members": groups.add_accounts(arguments.group, read_input().get("user_ids") or [])}
  if command == "add-schedule":
    details = read_input()
    return {"ok": True, "schedule": group_schedules.add_schedule(arguments.group, details, str(details.get("created_by", "")))}
  if command == "get-schedule":
    return {"ok": True, "schedule": group_schedules.get_schedule(arguments.group, arguments.schedule)}
  if command == "update-schedule":
    return {"ok": True, "schedule": group_schedules.update_schedule(arguments.group, arguments.schedule, read_input())}
  if command == "remove-schedule":
    return {"ok": True, "schedule": group_schedules.remove_schedule(arguments.group, arguments.schedule)}
  if command == "test-schedule":
    return {"ok": True, **group_schedules.send_test(arguments.group, arguments.schedule)}
  if command == "my-cards":
    import saved_cards

    return {"ok": True, **saved_cards.admin_cards(arguments.drupal_uid, arguments.email)}
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

"""List, add, change and delete the external sites (external_sites.py). Used by the Drupal "External sites" page.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0. The details go on the standard input as JSON.

    manage_external_sites.py list
    manage_external_sites.py get --id=ID
    manage_external_sites.py create          input {name, address, notes, sign_in_address, created_by}
    manage_external_sites.py update --id=ID  input {name, address, notes, sign_in_address}
    manage_external_sites.py delete --id=ID
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import external_sites  # noqa: E402
from external_sites import ExternalSiteProblem  # noqa: E402


def parse_arguments(arguments=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("list")
  commands.add_parser("create")
  for name in ("get", "update", "delete"):
    commands.add_parser(name).add_argument("--id", type=int, required=True)
  return parser.parse_args(arguments)


def read_details() -> dict:
  try:
    details = json.loads(sys.stdin.read())
  except json.JSONDecodeError as error:
    raise ExternalSiteProblem("The site could not be read.") from error
  if not isinstance(details, dict):
    raise ExternalSiteProblem("The site could not be read.")
  return details


def run(arguments) -> dict:
  if arguments.command == "list":
    return {"ok": True, "sites": external_sites.list_sites()}
  if arguments.command == "get":
    return {"ok": True, "site": external_sites.get_site(arguments.id)}
  if arguments.command == "delete":
    return {"ok": True, "site": external_sites.delete_site(arguments.id)}
  details = read_details()
  if arguments.command == "create":
    return {"ok": True, "site": external_sites.create_site(details, str(details.get("created_by") or ""))}
  return {"ok": True, "site": external_sites.update_site(arguments.id, details)}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except ExternalSiteProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

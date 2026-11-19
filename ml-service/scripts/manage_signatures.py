"""List, add, change and delete signatures (signatures.py). Used by the Drupal "Signatures" page.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0. The words go on the standard input as JSON.

    manage_signatures.py list [--owner=UID]          everyone's, or one person's
    manage_signatures.py get --id=ID
    manage_signatures.py create --owner=UID          input {name, signature: {html} or {text}, owner_name}
    manage_signatures.py update --id=ID              input {name, signature}
    manage_signatures.py delete --id=ID
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import signatures  # noqa: E402
from signatures import SignatureProblem  # noqa: E402


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
    raise SignatureProblem("The signature could not be read.") from error
  if not isinstance(details, dict):
    raise SignatureProblem("The signature could not be read.")
  return details


def run(arguments) -> dict:
  if arguments.command == "list":
    return {"ok": True, "signatures": signatures.list_signatures(arguments.owner)}
  if arguments.command == "get":
    return {"ok": True, "signature": signatures.get_signature(arguments.id)}
  if arguments.command == "delete":
    return {"ok": True, "signature": signatures.delete_signature(arguments.id)}
  details = read_details()
  if arguments.command == "create":
    return {"ok": True, "signature": signatures.create_signature(details, arguments.owner, str(details.get("owner_name") or ""))}
  return {"ok": True, "signature": signatures.update_signature(arguments.id, details)}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except SignatureProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

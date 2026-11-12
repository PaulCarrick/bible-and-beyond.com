"""List, read and delete the members' posts of Conversations. Used by the Drupal "Conversations" admin page.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0.

    manage_conversations.py list [--query=words] [--page=1]
    manage_conversations.py get --id=7
    manage_conversations.py delete --id=7
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conversations import ConversationProblem, admin_delete_post, admin_get_post, admin_list_posts  # noqa: E402


def parse_arguments():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  listing = commands.add_parser("list")
  listing.add_argument("--query", default="")
  listing.add_argument("--page", type=int, default=1)
  for name in ("get", "delete"):
    commands.add_parser(name).add_argument("--id", type=int, required=True)
  return parser.parse_args()


def run(arguments) -> dict:
  if arguments.command == "list":
    return {"ok": True, **admin_list_posts(arguments.query, arguments.page)}
  if arguments.command == "get":
    return {"ok": True, "post": admin_get_post(arguments.id)}
  return {"ok": True, "post": admin_delete_post(arguments.id)}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except ConversationProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

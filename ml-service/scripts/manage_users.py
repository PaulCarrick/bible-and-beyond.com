"""List, add, change and delete the accounts of the main site. Used by the Drupal "Site users" page.

These are the visitors' accounts in the Bible database, not Drupal's users. Every command prints one JSON
object. On success it has "ok": true. On failure it has "ok": false and an "error" written for the
administrator, and the exit status is not 0.

    manage_users.py list [--query=part-of-an-address-or-name] [--page=1]
    manage_users.py get --id=7
    manage_users.py create [--email=ann@example.com] [--first-name=Ann] [--last-name=Lee] [--phone=...]
                           [--email-verified] [--phone-verified] [--open-ai-queries] [--use-conversations] [--see-private-prayers] [--use-maps] [--share-lists] [--get-conversation-posts] [--texts] --password-on-input
    manage_users.py update --id=7 [--email=...] [--first-name=...] [--last-name=...] [--phone=...]
                           [--email-verified=yes|no] [--open-ai-queries=yes|no] [--use-conversations=yes|no] [--see-private-prayers=yes|no] [--use-maps=yes|no] [--share-lists=yes|no] [--get-conversation-posts=yes|no] [--closed=yes|no] [--phone-verified=yes|no] [--texts=yes|no]
                           [--password-on-input]

An empty --first-name=, --last-name= or --phone= on update clears it; leaving the option out keeps it. Without an
email (an empty --email=), the account logs in with its phone, which must then be a US or Canadian cell number.
    manage_users.py delete --id=7

A password is never given as an argument (other users of the server could see it in the process list):
with --password-on-input it is read as the first line of the standard input.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from site_users import UserProblem, create_user, delete_user, get_user, list_users, update_user  # noqa: E402


def yes_or_no(value: str) -> bool:
  if value not in ("yes", "no"):
    raise argparse.ArgumentTypeError("use yes or no")
  return value == "yes"


def parse_arguments():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  listing = commands.add_parser("list")
  listing.add_argument("--query", default="")
  listing.add_argument("--page", type=int, default=1)
  for name in ("get", "delete"):
    commands.add_parser(name).add_argument("--id", type=int, required=True)
  create = commands.add_parser("create")
  create.add_argument("--email", default="")
  create.add_argument("--first-name", default="")
  create.add_argument("--last-name", default="")
  create.add_argument("--phone", default="")
  create.add_argument("--email-verified", action="store_true")
  create.add_argument("--open-ai-queries", action="store_true")
  create.add_argument("--use-conversations", action="store_true")
  create.add_argument("--see-private-prayers", action="store_true")
  create.add_argument("--use-maps", action="store_true")
  create.add_argument("--share-lists", action="store_true")
  create.add_argument("--get-conversation-posts", action="store_true")
  create.add_argument("--phone-verified", action="store_true")
  create.add_argument("--texts", action="store_true")
  create.add_argument("--password-on-input", action="store_true")
  update = commands.add_parser("update")
  update.add_argument("--id", type=int, required=True)
  update.add_argument("--email")
  update.add_argument("--first-name")
  update.add_argument("--last-name")
  update.add_argument("--phone")
  update.add_argument("--email-verified", type=yes_or_no)
  update.add_argument("--open-ai-queries", type=yes_or_no)
  update.add_argument("--use-conversations", type=yes_or_no)
  update.add_argument("--see-private-prayers", type=yes_or_no)
  update.add_argument("--use-maps", type=yes_or_no)
  update.add_argument("--share-lists", type=yes_or_no)
  update.add_argument("--get-conversation-posts", type=yes_or_no)
  update.add_argument("--closed", type=yes_or_no)
  update.add_argument("--phone-verified", type=yes_or_no)
  update.add_argument("--texts", type=yes_or_no)
  update.add_argument("--password-on-input", action="store_true")
  return parser.parse_args()


def read_password() -> str:
  return sys.stdin.readline().rstrip("\r\n")


def run(arguments) -> dict:
  if arguments.command == "list":
    return {"ok": True, **list_users(arguments.query, arguments.page)}
  if arguments.command == "get":
    return {"ok": True, "user": get_user(arguments.id)}
  if arguments.command == "delete":
    return {"ok": True, "user": delete_user(arguments.id)}
  if arguments.command == "create":
    if not arguments.password_on_input:
      raise UserProblem("A new account needs a password.")
    user = create_user(
      arguments.email,
      read_password(),
      arguments.email_verified,
      arguments.open_ai_queries,
      first_name=arguments.first_name,
      last_name=arguments.last_name,
      phone=arguments.phone,
      use_conversations=arguments.use_conversations,
      see_private_prayers=arguments.see_private_prayers,
      use_maps=arguments.use_maps,
      phone_verified=arguments.phone_verified,
      share_lists=arguments.share_lists,
      get_conversation_posts=arguments.get_conversation_posts,
      texts=arguments.texts,
    )
    return {"ok": True, "user": user}
  password = read_password() if arguments.password_on_input else None
  user = update_user(
    arguments.id,
    email=arguments.email,
    password=password,
    email_verified=arguments.email_verified,
    open_ai_queries=arguments.open_ai_queries,
    first_name=arguments.first_name,
    last_name=arguments.last_name,
    phone=arguments.phone,
    use_conversations=arguments.use_conversations,
    see_private_prayers=arguments.see_private_prayers,
    use_maps=arguments.use_maps,
    share_lists=arguments.share_lists,
    get_conversation_posts=arguments.get_conversation_posts,
    closed=arguments.closed,
    phone_verified=arguments.phone_verified,
    texts=arguments.texts,
  )
  return {"ok": True, "user": user}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except UserProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

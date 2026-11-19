"""List, add, change and delete the Kindle books (kindle_books.py), and set or remove a book's picture. Used by the
Kindle books part of the Drupal "Devotionals" and "Other books" pages.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0. A book's details go on the standard input as
JSON: {collection (devotionals or books; kept when changing), title, author, address, is_published, created_by}.

    manage_kindle_books.py list [--collection=devotionals|books]
    manage_kindle_books.py get --id=ID
    manage_kindle_books.py create
    manage_kindle_books.py update --id=ID
    manage_kindle_books.py delete --id=ID
    manage_kindle_books.py cover --id=ID --file=PATH --name=ORIGINAL_NAME
    manage_kindle_books.py remove-cover --id=ID
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kindle_books  # noqa: E402
from kindle_books import KindleBookProblem  # noqa: E402


def parse_arguments(arguments=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("list").add_argument("--collection", choices=sorted(kindle_books.COLLECTIONS))
  commands.add_parser("create")
  for name in ("get", "update", "delete", "remove-cover"):
    commands.add_parser(name).add_argument("--id", type=int, required=True)
  cover = commands.add_parser("cover")
  cover.add_argument("--id", type=int, required=True)
  cover.add_argument("--file", required=True)
  cover.add_argument("--name", required=True)
  return parser.parse_args(arguments)


def read_details() -> dict:
  try:
    details = json.loads(sys.stdin.read())
  except json.JSONDecodeError as error:
    raise KindleBookProblem("The book could not be read.") from error
  if not isinstance(details, dict):
    raise KindleBookProblem("The book could not be read.")
  return details


def run(arguments) -> dict:
  if arguments.command == "list":
    return {"ok": True, "books": kindle_books.list_books(arguments.collection)}
  if arguments.command == "get":
    return {"ok": True, "book": {**kindle_books.get_book(arguments.id), "cover_data_uri": kindle_books.cover_data_uri(arguments.id)}}
  if arguments.command == "delete":
    return {"ok": True, "book": kindle_books.delete_book(arguments.id)}
  if arguments.command == "cover":
    return {"ok": True, "book": kindle_books.save_cover(arguments.id, Path(arguments.file), arguments.name)}
  if arguments.command == "remove-cover":
    return {"ok": True, "book": kindle_books.remove_cover(arguments.id)}
  details = read_details()
  if arguments.command == "create":
    return {"ok": True, "book": kindle_books.create_book(details, str(details.get("created_by") or ""))}
  return {"ok": True, "book": kindle_books.update_book(arguments.id, details)}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except KindleBookProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

"""Manage the commentaries and devotionals. Used by the Drupal Commentaries and Devotionals pages.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0.

    manage_library.py list --kind=commentary|devotional
    manage_library.py publish|unpublish|delete --kind=... --id=matthew-henry
    manage_library.py refresh --kind=... --id=matthew-henry     (starts reloading from the source, in the background)
    manage_library.py set-credit --kind=book --id=apostles-creed --credit="..."   (its own credit line; empty for the usual one)
    manage_library.py get --kind=... --id=...                   (its details, for the Edit page)
    manage_library.py update --kind=... --id=... < details.json (changes its details: name, author or short name,
        translator, source name and address, license address or credit line; the text is not touched)
    manage_library.py preview|import FILE --kind=commentary --id=... --name=... --short-name=... \\
        --source-name=... [--source-url=...] [--license-url=...]
    manage_library.py preview|import FILE --kind=devotional --id=... --name=... --author=... \\
        --devotional-kind=daily|chapters --source-name=... [--source-url=...] [--translator=...] [--whole]
    (--whole: a PDF or Word document is one chapter, not cut at its headings)

The file formats are described in library_upload.py. An upload that is new stays hidden until published.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from library_admin import (  # noqa: E402
  LibraryProblem, delete, get_details, list_items, refresh, run_refresh, set_credit, set_published, update_details,
)
from library_upload import UploadProblem, import_file, preview  # noqa: E402


def parse_arguments():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  for name in ("list", "get", "update", "publish", "unpublish", "delete", "refresh", "run-refresh"):
    command = commands.add_parser(name)
    command.add_argument("--kind", required=True, choices=["commentary", "devotional", "book"])
    if name != "list":
      command.add_argument("--id", required=True)
  credit = commands.add_parser("set-credit")
  credit.add_argument("--kind", required=True, choices=["devotional", "book"])
  credit.add_argument("--id", required=True)
  credit.add_argument("--credit", required=True)
  for name in ("preview", "import"):
    command = commands.add_parser(name)
    command.add_argument("file")
    command.add_argument("--kind", required=True, choices=["commentary", "devotional", "book"])
    command.add_argument("--id", required=True)
    command.add_argument("--name", required=True)
    command.add_argument("--short-name", default="")
    command.add_argument("--author", default="")
    command.add_argument("--devotional-kind", default="")
    command.add_argument("--source-name", default="")
    command.add_argument("--source-url", default="")
    command.add_argument("--license-url", default="")
    command.add_argument("--translator", default="")
    # A commentary from a PDF or Word document with no headings naming passages: the passage it is about.
    command.add_argument("--passage", default="")
    # Its own credit line (devotionals and books); left out, it keeps the one it has; empty, the usual line.
    command.add_argument("--credit", default=None)
    # Words the searches also find it by (devotionals and books); left out or empty, it keeps the ones it has.
    command.add_argument("--keywords", default=None)
    # A PDF or Word document kept whole as one chapter, its headings inside it (a book or a devotional by chapter).
    command.add_argument("--whole", action="store_true")
  return parser.parse_args()


def details(arguments) -> dict:
  return {
    "id": arguments.id, "name": arguments.name, "short_name": arguments.short_name, "author": arguments.author,
    "kind": arguments.devotional_kind, "source_name": arguments.source_name, "source_url": arguments.source_url,
    "license_url": arguments.license_url, "translator": arguments.translator, "credit": arguments.credit,
    "keywords": arguments.keywords, "passage": arguments.passage, "whole": arguments.whole,
  }


def run(arguments) -> dict:
  command, kind = arguments.command, arguments.kind
  if command == "list":
    return {"ok": True, "items": list_items(kind)}
  if command in ("publish", "unpublish"):
    return {"ok": True, **set_published(kind, arguments.id, command == "publish")}
  if command == "delete":
    return {"ok": True, **delete(kind, arguments.id)}
  if command == "get":
    return {"ok": True, "item": get_details(kind, arguments.id)}
  if command == "update":
    # The details come as JSON on the standard input (the Drupal form sends them so).
    try:
      changes = json.loads(sys.stdin.read() or "{}")
    except ValueError:
      raise LibraryProblem("The details could not be read.")
    if not isinstance(changes, dict):
      raise LibraryProblem("The details could not be read.")
    return {"ok": True, "item": update_details(kind, arguments.id, changes)}
  if command == "set-credit":
    return {"ok": True, **set_credit(kind, arguments.id, arguments.credit)}
  if command == "refresh":
    return {"ok": True, **refresh(kind, arguments.id)}
  path = Path(arguments.file)
  if not path.is_file():
    raise UploadProblem("The uploaded file was not found.")
  if command == "preview":
    return {"ok": True, **preview(kind, path, details(arguments))}
  return {"ok": True, **import_file(kind, path, details(arguments))}


def main():
  arguments = parse_arguments()
  if arguments.command == "run-refresh":
    # The background part of "refresh": it records its progress itself (library_admin.run_refresh).
    run_refresh(arguments.kind, arguments.id)
    return
  try:
    result = run(arguments)
  except (LibraryProblem, UploadProblem) as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

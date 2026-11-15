"""Upload, change, publish, hide and delete the maps. Used by the Drupal "Maps" page.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0.

    manage_maps.py list                                   every map, hidden ones too
    manage_maps.py get --id=pauls-journeys
    manage_maps.py upload FILE --name=journeys.pdf --id=pauls-journeys [--page=1]
                                                          reads {"title", "description", "source", "keywords", "verses"}
                                                          as JSON on the input (keywords or verses left out: the map's are kept)
    manage_maps.py update --id=pauls-journeys [--page=2]  the same details, without a new file (--page draws
                                                          another page of the map's PDF)
    manage_maps.py check-verses                           reads {"verses"} on the input and lists them, or says
                                                          which are not understood
    manage_maps.py publish|unpublish|delete --id=pauls-journeys

--name is the file's name as uploaded (its extension says what it should be; the first bytes are checked). The
details are sent on the standard input rather than as arguments, because the description can be long.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maps import (  # noqa: E402
  MapProblem,
  delete,
  get_map,
  list_maps,
  parse_verses,
  set_published,
  update_details,
  upload,
)


def parse_arguments():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("list")
  commands.add_parser("check-verses")
  for name in ("get", "publish", "unpublish", "delete"):
    commands.add_parser(name).add_argument("--id", required=True)
  updating = commands.add_parser("update")
  updating.add_argument("--id", required=True)
  updating.add_argument("--page", type=int, default=None)
  uploading = commands.add_parser("upload")
  uploading.add_argument("file")
  uploading.add_argument("--name", required=True)
  uploading.add_argument("--id", required=True)
  uploading.add_argument("--page", type=int, default=1)
  return parser.parse_args()


def read_details() -> dict:
  try:
    details = json.loads(sys.stdin.read())
  except json.JSONDecodeError as error:
    raise MapProblem("The details could not be read.") from error
  if not isinstance(details, dict):
    raise MapProblem("The details could not be read.")
  return details


def run(arguments) -> dict:
  if arguments.command == "list":
    return {"ok": True, "maps": list_maps(published_only=False)}
  if arguments.command == "check-verses":
    return {"ok": True, "verses": parse_verses(read_details().get("verses", ""))}
  if arguments.command == "get":
    found = get_map(arguments.id, published_only=False)
    if found is None:
      raise MapProblem("That map does not exist (it may have been deleted).")
    return {"ok": True, "map": found}
  if arguments.command in ("publish", "unpublish"):
    return {"ok": True, "map": set_published(arguments.id, arguments.command == "publish")}
  if arguments.command == "delete":
    return {"ok": True, "map": delete(arguments.id)}
  if arguments.command == "update":
    return {"ok": True, "map": update_details(arguments.id, read_details(), arguments.page)}
  path = Path(arguments.file)
  if not path.is_file():
    raise MapProblem("The uploaded file was not found.")
  return {"ok": True, "map": upload(path, arguments.name, arguments.id, read_details(), arguments.page)}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except MapProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

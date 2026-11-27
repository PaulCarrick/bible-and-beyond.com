"""List, upload, take out of use and delete the verse a day pictures. Used by the Drupal "Verse a day
pictures" page (verse_images.py).

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0.

    manage_verse_images.py list                      every picture, newest first, each with a thumbnail (data:)
    manage_verse_images.py get --id=ID
    manage_verse_images.py upload FILE --name=ORIGINAL-NAME --id=ID --title=TITLE
    manage_verse_images.py preview --id=ID           the picture with a larger copy (data:) to show it enlarged
    manage_verse_images.py rename --id=ID --title=TITLE   a new name; the id and the files stay
    manage_verse_images.py use --id=ID               back in the random choice
    manage_verse_images.py unuse --id=ID             kept, but left out of the random choice
    manage_verse_images.py delete --id=ID            the picture and its files
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import verse_images  # noqa: E402
from verse_images import ImageProblem  # noqa: E402


def parse_arguments(arguments=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("list")
  upload = commands.add_parser("upload")
  upload.add_argument("file")
  upload.add_argument("--name", required=True)
  upload.add_argument("--id", required=True)
  upload.add_argument("--title", required=True)
  rename = commands.add_parser("rename")
  rename.add_argument("--id", required=True)
  rename.add_argument("--title", required=True)
  for command in ("get", "preview", "use", "unuse", "delete"):
    commands.add_parser(command).add_argument("--id", required=True)
  return parser.parse_args(arguments)


def run(arguments) -> dict:
  if arguments.command == "list":
    return {"ok": True, "images": verse_images.list_images(with_thumbnails=True)}
  if arguments.command == "upload":
    path = Path(arguments.file)
    if not path.is_file():
      raise ImageProblem("The uploaded file was not found.")
    return {"ok": True, "image": verse_images.upload(path, arguments.name, arguments.id, arguments.title)}
  if arguments.command == "get":
    image = verse_images.get_image(arguments.id)
    if image is None:
      raise ImageProblem("That picture does not exist (it may have been deleted).")
    return {"ok": True, "image": image}
  if arguments.command == "preview":
    return {"ok": True, "image": verse_images.preview(arguments.id)}
  if arguments.command == "rename":
    return {"ok": True, "image": verse_images.rename(arguments.id, arguments.title)}
  if arguments.command in ("use", "unuse"):
    return {"ok": True, "image": verse_images.set_in_use(arguments.id, arguments.command == "use")}
  return {"ok": True, "image": verse_images.delete(arguments.id)}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except ImageProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

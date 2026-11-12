"""Show, replace and remove the site's two icons. Used by the Drupal Site settings screen.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0.

    manage_site_icons.py get                                  each icon: null, or its type, size and a preview
    manage_site_icons.py upload --kind=header|tab --file=PATH --name=ORIGINAL-NAME
    manage_site_icons.py remove --kind=header|tab             back to the site's own icon
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import site_icons  # noqa: E402
from site_icons import IconProblem  # noqa: E402


def parse_arguments():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("get")
  upload = commands.add_parser("upload")
  upload.add_argument("--kind", required=True)
  upload.add_argument("--file", required=True)
  upload.add_argument("--name", required=True)
  commands.add_parser("remove").add_argument("--kind", required=True)
  return parser.parse_args()


def run(arguments) -> dict:
  if arguments.command == "upload":
    path = Path(arguments.file)
    if not path.is_file():
      raise IconProblem("The uploaded file was not found.")
    site_icons.save(arguments.kind, path, arguments.name)
  elif arguments.command == "remove":
    site_icons.remove(arguments.kind)
  return {"ok": True, "icons": site_icons.describe(with_data=True)}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except IconProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

"""Read and change the keys and options of the outside services (Gemini, API.Bible, reCAPTCHA).

Used by the Drupal "Site settings" screen. Every command prints one JSON object. On success it has
"ok": true. On failure it has "ok": false and an "error" written for the administrator, and the exit
status is not 0. The keys themselves are never printed: "get" only says whether each is set and where it
comes from (saved on the screen, ml-service/.env, or the default).

    manage_service_settings.py get
    manage_service_settings.py set      (reads {"values": {name: value}, "remove": [name, ...]} as JSON
                                         from the standard input, so no key appears in the process list)

On "set", an empty key keeps the one in use, and every value is then saved to the settings file, so
.env is no longer used for them.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from service_settings import ServiceSettingsProblem, describe, save  # noqa: E402


def run(command: str) -> dict:
  if command == "get":
    return {"ok": True, **describe()}
  try:
    request = json.loads(sys.stdin.read() or "{}")
  except ValueError as error:
    raise ServiceSettingsProblem("The settings could not be read.") from error
  values = request.get("values", {})
  remove = request.get("remove", [])
  if not isinstance(values, dict) or not isinstance(remove, list):
    raise ServiceSettingsProblem("The settings could not be read.")
  return {"ok": True, **save(values, remove)}


def main():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("command", choices=["get", "set"])
  arguments = parser.parse_args()
  try:
    result = run(arguments.command)
  except ServiceSettingsProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace (or a key) to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

"""Read and change the site settings. Used by the Drupal "Search settings" page.

Every command prints one JSON object. On success it has "ok": true. On failure it has
"ok": false and an "error" written for the administrator, and the exit status is not 0.

    manage_settings.py get
    manage_settings.py set --context-verses-before 5 --context-verses-after 10 --related-verses-limit 10

On "set", any setting you leave out is not changed.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from site_settings import CONTEXT_LIMIT, LIMITS, SettingsProblem, get_settings, save_settings  # noqa: E402


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("get")
    change = commands.add_parser("set")
    change.add_argument("--context-verses-before", type=int)
    change.add_argument("--context-verses-after", type=int)
    change.add_argument("--related-verses-limit", type=int)
    return parser.parse_args()


def describe(settings):
    limits = {key: {"min": smallest, "max": largest} for key, (smallest, largest) in LIMITS.items()}
    return {"ok": True, "settings": settings, "limits": limits, "context_limit": CONTEXT_LIMIT}


def run(arguments):
    if arguments.command == "get":
        return describe(get_settings())
    chosen = {
        "context_verses_before": arguments.context_verses_before,
        "context_verses_after": arguments.context_verses_after,
        "related_verses_limit": arguments.related_verses_limit,
    }
    changes = {key: value for key, value in chosen.items() if value is not None}
    if not changes:
        raise SettingsProblem("Give at least one setting to change.")
    return describe(save_settings(changes))


def main():
    arguments = parse_arguments()
    try:
        result = run(arguments)
    except SettingsProblem as problem:
        print(json.dumps({"ok": False, "error": str(problem)}))
        sys.exit(1)
    except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
        sys.exit(2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

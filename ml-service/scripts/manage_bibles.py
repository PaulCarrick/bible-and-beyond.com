"""Manage the Bible translations in the search database. Used by the Drupal "Bibles" admin page.

Every command prints one JSON object. On success it has "ok": true. On failure it has
"ok": false and an "error" written for the administrator, and the exit status is not 0.

    manage_bibles.py formats
    manage_bibles.py list
    manage_bibles.py preview FILE --code NASB95 --name "..." --license "..."
    manage_bibles.py import  FILE --code NASB95 --name "..." --license "..."
    manage_bibles.py publish CODE
    manage_bibles.py unpublish CODE
    manage_bibles.py delete CODE

"import" saves a new translation as hidden; an existing one keeps its published state.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bible_import.catalog import delete_translation, list_translations, set_published  # noqa: E402
from bible_import.errors import ImportProblem  # noqa: E402
from bible_import.formats import READERS  # noqa: E402
from bible_import.importer import TranslationDetails, import_file, preview_file  # noqa: E402


def add_file_arguments(parser):
    parser.add_argument("file_path")
    parser.add_argument("--code", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--language", default="en")
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--format", default="auto", dest="format_id")
    parser.add_argument("--strip-brackets", action="store_true")
    parser.add_argument("--skip-unmatched-books", action="store_true")


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("formats")
    commands.add_parser("list")
    add_file_arguments(commands.add_parser("preview"))
    add_file_arguments(commands.add_parser("import"))
    for command in ("publish", "unpublish", "delete"):
        commands.add_parser(command).add_argument("code")
    return parser.parse_args()


def details_from(arguments):
    return TranslationDetails(
        code=arguments.code,
        name=arguments.name,
        language=arguments.language,
        license=arguments.license,
        source_url=arguments.source_url,
    )


def run(arguments):
    if arguments.command == "formats":
        return {
            "ok": True,
            "formats": [
                {"id": reader.id, "name": reader.name, "description": reader.description} for reader in READERS
            ],
        }
    if arguments.command == "list":
        return {"ok": True, "translations": list_translations()}
    if arguments.command == "preview":
        return preview_file(
            arguments.file_path,
            details_from(arguments),
            arguments.format_id,
            arguments.strip_brackets,
            arguments.skip_unmatched_books,
        )
    if arguments.command == "import":
        return import_file(
            arguments.file_path,
            details_from(arguments),
            arguments.format_id,
            arguments.strip_brackets,
            arguments.skip_unmatched_books,
            publish_new=False,
        )
    if arguments.command in ("publish", "unpublish"):
        return set_published(arguments.code.strip().upper(), arguments.command == "publish")
    return delete_translation(arguments.code.strip().upper())


def main():
    arguments = parse_arguments()
    try:
        result = run(arguments)
    except ImportProblem as problem:
        print(json.dumps({"ok": False, "error": str(problem)}))
        sys.exit(1)
    except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
        sys.exit(2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

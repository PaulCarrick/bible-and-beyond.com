"""Import a verse-per-line Bible text file into Postgres from the command line.

Two line formats are supported (detected automatically, or choose one with --format):
    Genesis 1:1<TAB>In the beginning...      (Berean Bible bsb.txt)
    GEN 1:1 In the beginning...              (eBible.org *_vpl.txt)
Book names and codes are matched against books.name, books.code and books.aliases.
Lines that don't match the format (headers, notes) are skipped.

Apply the schema first (database/schema.sql), then run, for example:
    .venv/bin/python scripts/import_bible.py data/bsb.txt \
        --code BSB \
        --name "Berean Standard Bible" \
        --license "Public domain" \
        --source-url "https://berean.bible"

    .venv/bin/python scripts/import_bible.py data/eng-kjv2006_vpl.txt \
        --code KJV \
        --name "King James Version" \
        --license "Public domain" \
        --source-url "https://ebible.org/find/details.php?id=eng-kjv2006" \
        --strip-brackets

A translation imported here is published straight away (add --unpublished to keep it hidden).
Re-running for the same translation code replaces that translation's verses.
The Drupal "Bibles" page uses the same code through scripts/manage_bibles.py.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bible_import.errors import ImportProblem  # noqa: E402
from bible_import.formats import READERS  # noqa: E402
from bible_import.importer import TranslationDetails, import_file, preview_file  # noqa: E402


def parse_arguments():
    parser = argparse.ArgumentParser(description="Import a Bible translation into Postgres.")
    parser.add_argument("file_path", help="Path to the verse-per-line text file")
    parser.add_argument("--code", required=True, help="Short translation code, e.g. BSB")
    parser.add_argument("--name", required=True, help="Full translation name")
    parser.add_argument("--license", required=True, help="License, e.g. 'Public domain'")
    parser.add_argument("--language", default="en", help="Language code (default: en)")
    parser.add_argument("--source-url", default=None, help="Where the text came from")
    parser.add_argument(
        "--format",
        default="auto",
        choices=["auto", *[reader.id for reader in READERS]],
        dest="format_id",
        help="File format (default: detect it)",
    )
    parser.add_argument(
        "--strip-brackets",
        action="store_true",
        help="Remove [ and ] around words (KJV marks supplied words this way)",
    )
    parser.add_argument(
        "--skip-unmatched-books",
        action="store_true",
        help="Skip books not in the books table (e.g. Apocrypha) instead of stopping",
    )
    parser.add_argument(
        "--unpublished",
        action="store_true",
        help="Keep a new translation hidden from search until it is published",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported; save nothing")
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    details = TranslationDetails(
        code=arguments.code,
        name=arguments.name,
        language=arguments.language,
        license=arguments.license,
        source_url=arguments.source_url,
    )

    try:
        if arguments.dry_run:
            preview = preview_file(
                arguments.file_path, details, arguments.format_id, arguments.strip_brackets, arguments.skip_unmatched_books
            )
            print(
                f"Would import {preview['code']}: {preview['verse_count']} verses in {preview['book_count']} books "
                f"({preview['format']['name']})"
            )
            for line in [*preview["warnings"], *preview["blocking_errors"]]:
                print(f"  {line}")
            sys.exit(0 if preview["can_import"] else 1)

        result = import_file(
            arguments.file_path,
            details,
            arguments.format_id,
            arguments.strip_brackets,
            arguments.skip_unmatched_books,
            publish_new=not arguments.unpublished,
        )
    except ImportProblem as problem:
        sys.exit(str(problem))

    print(f"Imported {result['code']}: {result['verse_count']} verses in {result['book_count']} books")
    for warning in result["warnings"]:
        print(f"Note: {warning}")
    if result["book_count"] != 66:
        print(f"Warning: expected 66 books, found {result['book_count']}.")


if __name__ == "__main__":
    main()

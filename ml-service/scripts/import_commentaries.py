"""Load the downloaded public-domain commentaries into Postgres.

Download them first with scripts/download_commentaries.py, then run (from ml-service):

    .venv/bin/python scripts/import_commentaries.py data/commentaries

This replaces everything of each commentary it loads (all of them unless some are named after the
folder). Use --dry-run to check the files without saving.

The commentaries are marked Public Domain by the Free Use Bible API (bible.helloao.org).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commentaries import (  # noqa: E402
    COMMENTARIES,
    CommentaryProblem,
    book_numbers_by_code,
    check_ids,
    read_commentary,
    replace_commentary,
)


def main():
    parser = argparse.ArgumentParser(description="Load public-domain commentaries.")
    parser.add_argument("folder", help="Folder the files were downloaded to")
    parser.add_argument("commentaries", nargs="*", help="Which ones (default: all that are in the folder)")
    parser.add_argument("--dry-run", action="store_true", help="Read and check the files, but save nothing")
    arguments = parser.parse_args()

    try:
        ids = check_ids(arguments.commentaries) if arguments.commentaries else [
            commentary_id for commentary_id in COMMENTARIES if (Path(arguments.folder) / commentary_id).is_dir()
        ]
        if not ids:
            sys.exit(f"No commentaries found in {arguments.folder}.")
        book_numbers = book_numbers_by_code()
        for commentary_id in ids:
            entries, introductions = read_commentary(arguments.folder, commentary_id, book_numbers)
            print(f"{commentary_id}: {len(entries):,} entries, {len(introductions):,} introductions")
            if not arguments.dry_run:
                print(f"  saved {replace_commentary(commentary_id, entries, introductions):,} entries")
    except CommentaryProblem as problem:
        sys.exit(str(problem))
    if arguments.dry_run:
        print("Dry run: nothing was saved.")


if __name__ == "__main__":
    main()

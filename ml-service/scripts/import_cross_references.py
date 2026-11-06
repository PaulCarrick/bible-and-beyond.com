"""Load the OpenBible.info cross references into Postgres.

Download "cross-references.zip" from https://www.openbible.info/labs/cross-references/, unzip it,
and run (from ml-service):

    .venv/bin/python scripts/import_cross_references.py /path/to/cross_references.txt

This replaces every cross reference in the database with the contents of the file. Rows with zero
or negative votes are left out. Use --dry-run to see what would be loaded without saving.

The data is licensed CC BY 4.0 and must be credited (the site does this on the search page and on
the Bible copyright notices page). It is based mainly on the Treasury of Scripture Knowledge.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cross_references import CrossReferenceProblem, read_file, replace_all  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Load OpenBible.info cross references.")
    parser.add_argument("file_path", help="Path to cross_references.txt")
    parser.add_argument("--minimum-votes", type=int, default=1, help="Leave out rows with fewer votes (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Read and check the file, but save nothing")
    arguments = parser.parse_args()

    try:
        references, skipped = read_file(arguments.file_path, arguments.minimum_votes)
    except CrossReferenceProblem as problem:
        sys.exit(str(problem))

    print(f"Read {len(references):,} cross references; left out {skipped:,} with fewer than {arguments.minimum_votes} votes.")
    if arguments.dry_run:
        print("Dry run: nothing was saved.")
        return
    print(f"Saved {replace_all(references):,} cross references.")


if __name__ == "__main__":
    main()

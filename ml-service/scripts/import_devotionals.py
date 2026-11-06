"""Load the downloaded devotionals into Postgres.

Download them first with scripts/download_devotionals.py, then run (from ml-service):

    .venv/bin/python scripts/import_devotionals.py data/devotionals

This replaces everything of each devotional it loads (all of them unless some are named after the
folder). A file that does not have all the days or chapters it should is refused. Use --dry-run to
read and check the files without saving.

All four are in the public domain; see devotionals.py for where each comes from.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devotionals import (  # noqa: E402
    DEVOTIONALS,
    DevotionalProblem,
    check_ids,
    file_path,
    read_devotional,
    replace_devotional,
)


def main():
    parser = argparse.ArgumentParser(description="Load public-domain devotionals.")
    parser.add_argument("folder", help="Folder the files were downloaded to")
    parser.add_argument("devotionals", nargs="*", help="Which ones (default: all that are in the folder)")
    parser.add_argument("--dry-run", action="store_true", help="Read and check the files, but save nothing")
    arguments = parser.parse_args()

    try:
        ids = check_ids(arguments.devotionals) if arguments.devotionals else [
            devotional_id for devotional_id in DEVOTIONALS if file_path(arguments.folder, devotional_id).exists()
        ]
        if not ids:
            sys.exit(f"No devotionals found in {arguments.folder}.")
        for devotional_id in ids:
            parsed = read_devotional(arguments.folder, devotional_id)
            units = len({(entry.section, entry.unit) for entry in parsed.entries})
            print(f"{devotional_id}: {len(parsed.sections)} sections, {units} days or chapters, {len(parsed.entries)} entries")
            if not arguments.dry_run:
                print(f"  saved {replace_devotional(devotional_id, parsed):,} entries")
    except DevotionalProblem as problem:
        sys.exit(str(problem))
    if arguments.dry_run:
        print("Dry run: nothing was saved.")


if __name__ == "__main__":
    main()

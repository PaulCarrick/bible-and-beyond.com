"""Download the public-domain devotionals.

Run (from ml-service):

    .venv/bin/python scripts/download_devotionals.py data/devotionals

It saves one file for each devotional in that folder (git-ignored, about 3 MB): Spurgeon's Morning
and Evening and Daily Light on the Daily Path from the Christian Classics Ethereal Library, and The
Imitation of Christ and The Practice of the Presence of God from Project Gutenberg. Name devotionals
after the folder to fetch only some. Then load them with scripts/import_devotionals.py.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devotionals import DEVOTIONALS, DevotionalProblem, check_ids, download  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Download public-domain devotionals.")
    parser.add_argument("folder", help="Folder to save the files in")
    parser.add_argument("devotionals", nargs="*", help=f"Which ones (default: all of {', '.join(DEVOTIONALS)})")
    arguments = parser.parse_args()
    try:
        ids = check_ids(arguments.devotionals or list(DEVOTIONALS))
        count = download(arguments.folder, ids)
    except DevotionalProblem as problem:
        sys.exit(str(problem))
    print(f"Downloaded {count} files.")


if __name__ == "__main__":
    main()

"""Download the public-domain commentaries from the Free Use Bible API (bible.helloao.org).

Run (from ml-service):

    .venv/bin/python scripts/download_commentaries.py data/commentaries

It saves one JSON file per chapter under that folder (about 6,000 files, a few hundred megabytes;
git-ignored) and can be stopped and run again: files that are already there are kept. Name
commentaries after the folder to fetch only some, for example: ... data/commentaries john-gill.
Then load them with scripts/import_commentaries.py.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commentaries import COMMENTARIES, CommentaryProblem, check_ids, download  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Download public-domain commentaries.")
    parser.add_argument("folder", help="Folder to save the files in")
    parser.add_argument("commentaries", nargs="*", help=f"Which ones (default: all of {', '.join(COMMENTARIES)})")
    arguments = parser.parse_args()
    try:
        ids = check_ids(arguments.commentaries or list(COMMENTARIES))
        count = download(arguments.folder, ids)
    except CommentaryProblem as problem:
        sys.exit(str(problem))
    print(f"Downloaded {count:,} chapter files.")


if __name__ == "__main__":
    main()

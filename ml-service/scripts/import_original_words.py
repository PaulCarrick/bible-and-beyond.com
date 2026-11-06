"""Load the STEPBible Hebrew and Greek words and lexicon into Postgres.

Download these files from https://github.com/STEPBible/STEPBible-Data (folders "Translators
Amalgamated OT+NT" and "Lexicons") into one folder, for example ml-service/data/stepbible/
(git-ignored), and run (from ml-service):

    .venv/bin/python scripts/import_original_words.py data/stepbible

The folder must hold the four TAHOT files, the two TAGNT files, TBESH and TBESG; their names may be
shortened, but each must start with its letters (tahot, tagnt, tbesh, tbesg), in any case. This
replaces every original word and lexicon entry in the database. Use --dry-run to check the files
without saving.

The data is licensed CC BY 4.0 and must be credited to STEP Bible (the site does this in the
Original Words window and on the Bible copyright notices page).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_words import (  # noqa: E402
    OriginalWordsProblem,
    link_words_to_lexicon,
    read_lexicon,
    read_words,
    replace_all,
)


def main():
    parser = argparse.ArgumentParser(description="Load STEPBible original words and lexicon.")
    parser.add_argument("folder", help="Folder holding the STEPBible files")
    parser.add_argument("--dry-run", action="store_true", help="Read and check the files, but save nothing")
    arguments = parser.parse_args()

    folder = Path(arguments.folder)
    files = sorted(folder.glob("*.txt"))
    word_files = [path for path in files if path.name.lower().startswith(("tahot", "tagnt"))]
    lexicon_files = [path for path in files if path.name.lower().startswith(("tbesh", "tbesg"))]
    if len(word_files) != 6 or len(lexicon_files) != 2:
        sys.exit(
            f"Expected 4 TAHOT and 2 TAGNT files and TBESH and TBESG in {folder}; found "
            f"{len(word_files)} word files and {len(lexicon_files)} lexicon files."
        )

    try:
        words = read_words(word_files)
        entries = read_lexicon(lexicon_files)
        words = link_words_to_lexicon(words, entries)
    except OriginalWordsProblem as problem:
        sys.exit(str(problem))

    print(f"Read {len(words):,} words and {len(entries):,} lexicon entries.")
    if arguments.dry_run:
        print("Dry run: nothing was saved.")
        return
    word_count, entry_count = replace_all(words, entries)
    print(f"Saved {word_count:,} words and {entry_count:,} lexicon entries.")


if __name__ == "__main__":
    main()

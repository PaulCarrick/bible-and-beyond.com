"""Link the English words of the Berean Standard Bible to their Strong's numbers.

Download "BSB Translation Tables - tsv" (https://bereanbible.com/bsb_tables.tsv, about 85 MB) and
run (from ml-service):

    .venv/bin/python scripts/import_word_links.py data/bsb_tables.tsv

The BSB must already be imported (code BSB). This replaces every word link of that Bible. Use
--dry-run to see how many verses line up without saving. Run it again whenever the BSB text is
re-imported (links for changed verses stop being used until then).

The Berean texts and tables are public domain (since 2023-04-30).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from word_links import (  # noqa: E402
    WordLinksProblem,
    build_links,
    load_verse_rows,
    read_table,
    replace_links,
)


def main():
    parser = argparse.ArgumentParser(description="Link English words to Strong's numbers.")
    parser.add_argument("table_path", help="Path to bsb_tables.tsv")
    parser.add_argument("--code", default="BSB", help="Code of the Bible the table belongs to (default: BSB)")
    parser.add_argument("--dry-run", action="store_true", help="Check the table, but save nothing")
    arguments = parser.parse_args()

    verse_rows = load_verse_rows(arguments.code)
    if not verse_rows:
        sys.exit(f"The Bible {arguments.code} is not in the database.")
    try:
        table = read_table(arguments.table_path)
    except WordLinksProblem as problem:
        sys.exit(str(problem))

    rows, summary = build_links(table, verse_rows)
    print(
        f"{summary['verses']:,} verses in {arguments.code}: {summary['linked']:,} linked "
        f"({summary['words']:,} words), {summary['did_not_line_up']:,} did not line up, "
        f"{summary['not_in_table']:,} not in the table."
    )
    if arguments.dry_run:
        print("Dry run: nothing was saved.")
        return
    print(f"Saved links for {replace_links(arguments.code, rows):,} verses.")


if __name__ == "__main__":
    main()

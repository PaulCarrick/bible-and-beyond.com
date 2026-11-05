"""Import a verse-per-line Bible text file into Postgres.

The file must have one verse per line in the form:
    Book Chapter:Verse<TAB>Text
Lines that don't match (headers, notes) are skipped.

Apply the schema first (database/schema.sql), then run, for example:
    .venv/bin/python scripts/import_bible.py data/bsb.txt \
        --code BSB \
        --name "Berean Standard Bible" \
        --license "Public domain" \
        --source-url "https://berean.bible"

Re-running for the same translation code replaces that translation's verses.
"""

import argparse
import os
import re
import sys

import psycopg
from dotenv import load_dotenv

VERSE_LINE_PATTERN = re.compile(r"^(?P<book>.+?) (?P<chapter>\d+):(?P<verse>\d+)\t(?P<text>.+)$")


def normalize_book_name(book_name):
    """Make book names comparable: case, spaces and periods are ignored."""
    return re.sub(r"[\s.]", "", book_name).lower()


def parse_arguments():
    parser = argparse.ArgumentParser(description="Import a Bible translation into Postgres.")
    parser.add_argument("file_path", help="Path to the verse-per-line text file")
    parser.add_argument("--code", required=True, help="Short translation code, e.g. BSB")
    parser.add_argument("--name", required=True, help="Full translation name")
    parser.add_argument("--license", required=True, help="License, e.g. 'Public domain'")
    parser.add_argument("--language", default="en", help="Language code (default: en)")
    parser.add_argument("--source-url", default=None, help="Where the text came from")
    return parser.parse_args()


def read_verse_lines(file_path):
    verse_lines = []

    with open(file_path, encoding="utf-8-sig") as bible_file:
        for line in bible_file:
            match = VERSE_LINE_PATTERN.match(line.rstrip("\n"))
            if match:
                verse_lines.append(
                    (
                        match["book"].strip(),
                        int(match["chapter"]),
                        int(match["verse"]),
                        match["text"].strip(),
                    )
                )

    return verse_lines


def load_book_lookup(cursor):
    cursor.execute("SELECT number, name, aliases FROM books")
    book_lookup = {}

    for book_number, book_name, aliases in cursor.fetchall():
        for name in [book_name, *aliases]:
            book_lookup[normalize_book_name(name)] = book_number

    return book_lookup


def map_verses_to_books(verse_lines, book_lookup):
    mapped_verses = []
    unmatched_book_names = []

    for book_name, chapter, verse, text in verse_lines:
        book_number = book_lookup.get(normalize_book_name(book_name))
        if book_number is None:
            if book_name not in unmatched_book_names:
                unmatched_book_names.append(book_name)
            continue
        mapped_verses.append((book_number, chapter, verse, text))

    return mapped_verses, unmatched_book_names


def save_translation(cursor, arguments):
    cursor.execute(
        """
        INSERT INTO translations (code, name, language, license, source_url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE
            SET name = EXCLUDED.name,
                language = EXCLUDED.language,
                license = EXCLUDED.license,
                source_url = EXCLUDED.source_url
        RETURNING id
        """,
        (arguments.code, arguments.name, arguments.language, arguments.license, arguments.source_url),
    )
    return cursor.fetchone()[0]


def main():
    arguments = parse_arguments()

    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set. Add it to ml-service/.env.")

    verse_lines = read_verse_lines(arguments.file_path)
    if not verse_lines:
        sys.exit(f"No verse lines found in {arguments.file_path}. Expected 'Book Chapter:Verse<TAB>Text'.")

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            book_lookup = load_book_lookup(cursor)
            if not book_lookup:
                sys.exit("The books table is empty. Apply database/schema.sql first.")

            mapped_verses, unmatched_book_names = map_verses_to_books(verse_lines, book_lookup)
            if unmatched_book_names:
                sys.exit(
                    "These book names don't match any book name or alias: "
                    + ", ".join(unmatched_book_names)
                    + "\nAdd them to the aliases column in database/schema.sql (or the books table) and re-run."
                )

            translation_id = save_translation(cursor, arguments)
            cursor.execute("DELETE FROM verses WHERE translation_id = %s", (translation_id,))

            with cursor.copy(
                "COPY verses (translation_id, book_number, chapter, verse, text) FROM STDIN"
            ) as copy:
                for book_number, chapter, verse, text in mapped_verses:
                    copy.write_row((translation_id, book_number, chapter, verse, text))

            cursor.execute(
                "SELECT COUNT(DISTINCT book_number), COUNT(*) FROM verses WHERE translation_id = %s",
                (translation_id,),
            )
            book_count, verse_count = cursor.fetchone()

    print(f"Imported {arguments.code}: {verse_count} verses in {book_count} books")
    if book_count != 66:
        print(f"Warning: expected 66 books, found {book_count}.")


if __name__ == "__main__":
    main()

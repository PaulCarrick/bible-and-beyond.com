"""Validate, preview and import a Bible translation file into the search database.

Re-importing an existing code replaces that translation's verses. A new translation starts
hidden (not published) when asked to, so an administrator can check it before the public sees it.
"""

import re
from dataclasses import dataclass, field

from api_bible import API_BIBLES
from bible_import.errors import ImportProblem
from bible_import.formats import detect_reader, reader_by_id
from search import connect

CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,10}$")
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
SOURCE_URL_PATTERN = re.compile(r"^https?://\S+$")
WELL_KNOWN_VERSE = (43, 3, 16)  # John 3:16, shown in the preview when the file has it
BOOK_COUNT = 66
LISTED_NAME_LIMIT = 20


@dataclass
class TranslationDetails:
  code: str
  name: str
  language: str = "en"
  license: str = ""
  source_url: str | None = None


@dataclass
class Prepared:
  """A file that has been read and matched against the books table, ready to preview or import."""

  reader: object
  verses: list = field(default_factory=list)  # (book_number, chapter, verse, text)
  skipped_count: int = 0
  skipped_samples: list = field(default_factory=list)
  unmatched_books: dict = field(default_factory=dict)  # name in the file -> number of lines
  duplicate_count: int = 0
  duplicate_examples: list = field(default_factory=list)  # (book_number, chapter, verse)


def validate_details(details):
  """Return cleaned-up details, or raise ImportProblem saying what is wrong."""
  code = (details.code or "").strip().upper()
  name = (details.name or "").strip()
  language = (details.language or "en").strip()
  license_text = (details.license or "").strip()
  source_url = (details.source_url or "").strip() or None

  if not CODE_PATTERN.match(code):
    raise ImportProblem("The code must be 2 to 10 letters or digits, such as NASB95.")
  if code in API_BIBLES:
    raise ImportProblem(
      f"{code} is the code of a licensed Bible that is served through API.Bible. Choose a different code."
    )
  if not 1 <= len(name) <= 100:
    raise ImportProblem("The name is required and can be at most 100 characters.")
  if not LANGUAGE_PATTERN.match(language):
    raise ImportProblem("The language must be a language code such as en or es.")
  if not 1 <= len(license_text) <= 300:
    raise ImportProblem("The license is required (for example 'Public domain') and can be at most 300 characters.")
  if source_url is not None and (len(source_url) > 500 or not SOURCE_URL_PATTERN.match(source_url)):
    raise ImportProblem("The source link must start with http:// or https://.")

  return TranslationDetails(code, name, language, license_text, source_url)


def clean_text(text, strip_brackets):
  text = text.replace("¶", "")  # paragraph marks (pilcrow)
  if strip_brackets:
    text = text.replace("[", "").replace("]", "")
  return re.sub(r"\s+", " ", text).strip()


def normalize_book_name(book_name):
  """Make book names comparable: case, spaces and periods are ignored."""
  return re.sub(r"[\s.]", "", book_name).lower()


def load_books(cursor):
  cursor.execute("SELECT number, code, name, aliases FROM books ORDER BY number")
  book_names = {}
  book_lookup = {}
  for book_number, book_code, book_name, aliases in cursor.fetchall():
    book_names[book_number] = book_name
    for name in [book_code, book_name, *aliases]:
      book_lookup[normalize_book_name(name)] = book_number
  return book_names, book_lookup


def prepare(path, format_id, strip_brackets, book_lookup):
  reader = detect_reader(path) if format_id in (None, "", "auto") else reader_by_id(format_id)
  read_result = reader.read(path)
  prepared = Prepared(
    reader=reader,
    skipped_count=read_result.skipped_count,
    skipped_samples=read_result.skipped_samples,
  )

  seen = set()
  for raw_verse in read_result.verses:
    book_number = book_lookup.get(normalize_book_name(raw_verse.book))
    if book_number is None:
      prepared.unmatched_books[raw_verse.book] = prepared.unmatched_books.get(raw_verse.book, 0) + 1
      continue
    reference = (book_number, raw_verse.chapter, raw_verse.verse)
    if reference in seen:
      prepared.duplicate_count += 1
      if len(prepared.duplicate_examples) < 5:
        prepared.duplicate_examples.append(reference)
    seen.add(reference)
    prepared.verses.append((*reference, clean_text(raw_verse.text, strip_brackets)))
  return prepared


def listed(names):
  shown = sorted(names)[:LISTED_NAME_LIMIT]
  extra = len(names) - len(shown)
  return ", ".join(shown) + (f" and {extra} more" if extra > 0 else "")


def build_preview(cursor, prepared, details, skip_unmatched_books, book_names):
  chapters_by_book = {}
  verse_counts = {}
  for book_number, chapter, _verse, _text in prepared.verses:
    chapters_by_book.setdefault(book_number, set()).add(chapter)
    verse_counts[book_number] = verse_counts.get(book_number, 0) + 1

  cursor.execute(
    "SELECT t.is_published, (SELECT COUNT(*) FROM verses v WHERE v.translation_id = t.id) "
    "FROM translations t WHERE t.code = %s",
    (details.code,),
  )
  existing_row = cursor.fetchone()
  existing = {"is_published": existing_row[0], "verse_count": existing_row[1]} if existing_row else None

  blocking_errors = []
  warnings = []

  if not prepared.verses:
    blocking_errors.append("No verses could be read from the file.")
  if prepared.unmatched_books and not skip_unmatched_books:
    blocking_errors.append(
      "These book names in the file do not match any Bible book: "
      + listed(prepared.unmatched_books)
      + ". Tick 'Skip books I do not recognize' to leave them out."
    )
  elif prepared.unmatched_books:
    warnings.append("These books are not recognized and will be left out: " + listed(prepared.unmatched_books) + ".")
  if prepared.duplicate_count:
    examples = ", ".join(
      f"{book_names[book_number]} {chapter}:{verse}" for book_number, chapter, verse in prepared.duplicate_examples
    )
    blocking_errors.append(
      f"{prepared.duplicate_count} verses appear more than once (for example {examples}). "
      "The file may contain two Bibles or two versions of the same book."
    )
  if prepared.skipped_count:
    warnings.append(f"{prepared.skipped_count} lines in the file are not verses and will be ignored.")
  if prepared.verses and len(verse_counts) < BOOK_COUNT:
    warnings.append(f"The file has {len(verse_counts)} of the {BOOK_COUNT} books.")
  if existing:
    state = "published" if existing["is_published"] else "hidden"
    warnings.append(
      f"{details.code} already exists ({state}, {existing['verse_count']} verses). Importing replaces its text."
    )

  samples = []
  if prepared.verses:
    ordered = sorted(prepared.verses, key=lambda verse: verse[:3])
    chosen = [ordered[0]]
    well_known = next((verse for verse in ordered if verse[:3] == WELL_KNOWN_VERSE), None)
    if well_known:
      chosen.append(well_known)
    if ordered[-1] not in chosen:
      chosen.append(ordered[-1])
    for book_number, chapter, verse, text in chosen:
      samples.append(
        {"reference": f"{book_names[book_number]} {chapter}:{verse}", "text": text[:300]}
      )

  return {
    "ok": True,
    "can_import": not blocking_errors,
    "format": {"id": prepared.reader.id, "name": prepared.reader.name},
    "code": details.code,
    "existing": existing,
    "verse_count": len(prepared.verses),
    "book_count": len(verse_counts),
    "books": [
      {
        "number": number,
        "name": book_names[number],
        "verse_count": verse_counts[number],
        "chapter_count": len(chapters_by_book[number]),
      }
      for number in sorted(verse_counts)
    ],
    "missing_books": [name for number, name in book_names.items() if number not in verse_counts],
    "skipped_line_count": prepared.skipped_count,
    "skipped_line_samples": prepared.skipped_samples,
    "unmatched_books": [
      {"name": name, "lines": count} for name, count in sorted(prepared.unmatched_books.items())
    ],
    "samples": samples,
    "blocking_errors": blocking_errors,
    "warnings": warnings,
  }


def preview_file(path, details, format_id="auto", strip_brackets=False, skip_unmatched_books=False):
  """Read the file and say what an import would do, without saving anything."""
  details = validate_details(details)
  with connect() as connection:
    with connection.cursor() as cursor:
      book_names, book_lookup = load_books(cursor)
      if not book_lookup:
        raise ImportProblem("The books table is empty. Apply database/schema.sql first.")
      prepared = prepare(path, format_id, strip_brackets, book_lookup)
      return build_preview(cursor, prepared, details, skip_unmatched_books, book_names)


def save_translation(cursor, details, publish_new):
  """Add the translation, or update the details of an existing one (which keeps its published state)."""
  cursor.execute(
    """
    INSERT INTO translations (code, name, language, license, source_url, is_published)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (code) DO UPDATE
      SET name = EXCLUDED.name,
          language = EXCLUDED.language,
          license = EXCLUDED.license,
          source_url = EXCLUDED.source_url
    RETURNING id, is_published, (xmax = 0) AS was_inserted
    """,
    (details.code, details.name, details.language, details.license, details.source_url, publish_new),
  )
  return cursor.fetchone()


def import_file(
  path,
  details,
  format_id="auto",
  strip_brackets=False,
  skip_unmatched_books=False,
  publish_new=False,
):
  """Import the file in one transaction. Nothing is saved if anything goes wrong."""
  details = validate_details(details)
  with connect() as connection:
    with connection.cursor() as cursor:
      book_names, book_lookup = load_books(cursor)
      if not book_lookup:
        raise ImportProblem("The books table is empty. Apply database/schema.sql first.")
      prepared = prepare(path, format_id, strip_brackets, book_lookup)
      preview = build_preview(cursor, prepared, details, skip_unmatched_books, book_names)
      if not preview["can_import"]:
        raise ImportProblem(" ".join(preview["blocking_errors"]))

      translation_id, is_published, was_inserted = save_translation(cursor, details, publish_new)
      cursor.execute("DELETE FROM verses WHERE translation_id = %s", (translation_id,))
      with cursor.copy(
        "COPY verses (translation_id, book_number, chapter, verse, text) FROM STDIN"
      ) as copy:
        for book_number, chapter, verse, text in prepared.verses:
          copy.write_row((translation_id, book_number, chapter, verse, text))

  return {
    "ok": True,
    "code": details.code,
    "verse_count": preview["verse_count"],
    "book_count": preview["book_count"],
    "replaced": not was_inserted,
    "is_published": is_published,
    "warnings": preview["warnings"],
  }

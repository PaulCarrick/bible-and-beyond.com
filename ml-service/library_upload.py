"""Uploading a commentary or a devotional from a file (the Drupal Commentaries and Devotionals pages).

Both files are tab-separated text in UTF-8 (a spreadsheet can save one as "Tab-delimited text"), with a
header row naming the columns, one row per note or reading. In the text column, "\\n" is a new line (two
make a new paragraph) and "\\\\" a backslash.

A commentary:   book  chapter  verse  end_verse  text
  - book: 1 to 66, a code such as JHN, or a name such as John or 1 Corinthians.
  - chapter 0 is the introduction to the book (verse empty).
  - verse empty (or 0) is the introduction to the chapter.
  - end_verse: empty for the verse alone, a later verse for a range, or "end" to the end of the chapter.

A devotional:   section  section_title  unit  unit_title  heading  text
  - Daily (kind "daily"): section is the month (1 to 12) and unit the day; the titles may be left empty
    ("January" and "January 1" are filled in). Several rows for one day (a morning and an evening
    reading) are kept in their order, with their heading ("Morning", "Evening").
  - By chapter (kind "chapters"): section is the part or book (a number; 0 for a preface) with its title,
    unit is the chapter with its title (both titles needed on the first row of each).

Nothing is saved until the import; the preview says what would be.
"""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from bible_import.importer import load_books, normalize_book_name
from commentaries import COMMENTARIES
from devotionals import MONTHS, SOURCES, Entry, Parsed
from scripture_references import verse_limits
from search import connect

MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_TEXT_CHARACTERS = 1_000_000
MAX_PROBLEMS_SHOWN = 20
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
URL_PATTERN = re.compile(r"^https?://[^\s]+$")
PUBLIC_DOMAIN_MARK = "https://creativecommons.org/publicdomain/mark/1.0/"
DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

COMMENTARY_COLUMNS = ["book", "chapter", "verse", "end_verse", "text"]
DEVOTIONAL_COLUMNS = ["section", "section_title", "unit", "unit_title", "heading", "text"]


class UploadProblem(ValueError):
  """The file or the details cannot be used; the message is written for the administrator."""


@dataclass
class ReadResult:
  problems: list = field(default_factory=list)  # each stops the import
  warnings: list = field(default_factory=list)  # worth knowing, the import can go ahead


def unescape(text: str) -> str:
  """The text column: "\\n" is a new line, "\\\\" a backslash."""
  return re.sub(r"\\(\\|n)", lambda match: "\\" if match.group(1) == "\\" else "\n", text).strip()


def read_rows(path: Path, columns: list[str]):
  """(line number, row as a dict) for each row of a tab-separated file with the given header."""
  if path.stat().st_size > MAX_FILE_BYTES:
    raise UploadProblem(f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
  try:
    with open(path, encoding="utf-8-sig", newline="") as file:
      reader = csv.reader(file, delimiter="\t", quoting=csv.QUOTE_NONE)
      header = [name.strip().lower() for name in next(reader, [])]
      if header != columns:
        raise UploadProblem(
          f"The first row must name the columns, separated by tabs: {' '.join(columns)}. It is: {' '.join(header) or '(empty)'}."
        )
      for line_number, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
          continue
        if len(row) != len(columns):
          yield line_number, None
          continue
        yield line_number, dict(zip(columns, row))
  except UnicodeDecodeError as error:
    raise UploadProblem("The file is not UTF-8 text. Save it as UTF-8 (\"Tab-delimited text\", UTF-8).") from error


def whole_number(value: str, smallest: int):
  value = value.strip()
  return int(value) if value.isdigit() and int(value) >= smallest else None


def note(result: ReadResult, kind: str, message: str):
  target = result.problems if kind == "problem" else result.warnings
  if len(target) < MAX_PROBLEMS_SHOWN:
    target.append(message)
  elif len(target) == MAX_PROBLEMS_SHOWN:
    target.append("(more not shown)")


# --- commentaries --------------------------------------------------------------------------------------


def read_commentary_file(path: Path):
  """(entries, introductions, result, book names). Entries and introductions are as save_commentary takes them."""
  with connect() as connection:
    with connection.cursor() as cursor:
      book_names, book_lookup = load_books(cursor)
  limits = verse_limits()
  entries, introductions = [], []
  seen_entries, seen_introductions = set(), set()
  result = ReadResult()
  for line_number, row in read_rows(path, COMMENTARY_COLUMNS):
    if row is None:
      note(result, "problem", f"Line {line_number}: it must have {len(COMMENTARY_COLUMNS)} columns, separated by tabs.")
      continue
    book_value = row["book"].strip()
    book = int(book_value) if book_value.isdigit() and 1 <= int(book_value) <= 66 else book_lookup.get(normalize_book_name(book_value))
    chapter = whole_number(row["chapter"], 0)
    verse_value = row["verse"].strip()
    verse = 0 if verse_value in ("", "0") else whole_number(verse_value, 1)
    end_value = row["end_verse"].strip().lower()
    text = unescape(row["text"])
    if book is None:
      note(result, "problem", f"Line {line_number}: the book '{book_value}' is not one of the 66 books.")
      continue
    if chapter is None or verse is None:
      note(result, "problem", f"Line {line_number}: chapter and verse must be whole numbers.")
      continue
    if not text:
      note(result, "problem", f"Line {line_number}: the text is empty.")
      continue
    if len(text) > MAX_TEXT_CHARACTERS:
      note(result, "problem", f"Line {line_number}: the text is longer than {MAX_TEXT_CHARACTERS:,} characters.")
      continue
    if chapter == 0 or verse == 0:
      if chapter == 0 and verse != 0:
        note(result, "problem", f"Line {line_number}: an introduction to a book (chapter 0) has no verse.")
        continue
      if end_value:
        note(result, "problem", f"Line {line_number}: an introduction has no end_verse.")
        continue
      if (book, chapter) in seen_introductions:
        note(result, "problem", f"Line {line_number}: {book_names[book]} {chapter or ''} already has an introduction.".replace("  ", " "))
        continue
      seen_introductions.add((book, chapter))
      introductions.append((book, chapter, text))
      continue
    if end_value == "":
      end_verse = verse
    elif end_value == "end":
      end_verse = None
    else:
      end_verse = whole_number(end_value, verse)
      if end_verse is None:
        note(result, "problem", f"Line {line_number}: end_verse must be empty, \"end\", or a verse from {verse} on.")
        continue
    if (book, chapter, verse) in seen_entries:
      note(result, "problem", f"Line {line_number}: {book_names[book]} {chapter}:{verse} already has a note.")
      continue
    seen_entries.add((book, chapter, verse))
    last_verse = limits.get((book, chapter), 0)
    if verse > last_verse:
      note(result, "warning", f"Line {line_number}: {book_names[book]} {chapter}:{verse} is not in the Bibles here; it will never be shown.")
    entries.append((book, chapter, verse, end_verse, text))
  if not entries and not result.problems:
    result.problems.append("The file has no notes.")
  return entries, introductions, result, book_names


# --- devotionals ---------------------------------------------------------------------------------------


def read_devotional_file(path: Path, kind: str):
  """(Parsed, result) for a daily or a by-chapter devotional."""
  if kind not in ("daily", "chapters"):
    raise UploadProblem("The kind must be daily or chapters.")
  result = ReadResult()
  sections: dict[int, str] = {}
  unit_titles: dict[tuple[int, int], str] = {}
  entries = []
  parts: dict[tuple[int, int], int] = {}
  for line_number, row in read_rows(path, DEVOTIONAL_COLUMNS):
    if row is None:
      note(result, "problem", f"Line {line_number}: it must have {len(DEVOTIONAL_COLUMNS)} columns, separated by tabs.")
      continue
    section = whole_number(row["section"], 0)
    unit = whole_number(row["unit"], 1)
    section_title = " ".join(row["section_title"].split())
    unit_title = " ".join(row["unit_title"].split())
    heading = " ".join(row["heading"].split())
    text = unescape(row["text"])
    if section is None or unit is None:
      note(result, "problem", f"Line {line_number}: section and unit must be whole numbers.")
      continue
    if not text:
      note(result, "problem", f"Line {line_number}: the text is empty.")
      continue
    if len(text) > MAX_TEXT_CHARACTERS:
      note(result, "problem", f"Line {line_number}: the text is longer than {MAX_TEXT_CHARACTERS:,} characters.")
      continue
    if kind == "daily":
      if not 1 <= section <= 12 or unit > DAYS_IN_MONTH[section - 1]:
        note(result, "problem", f"Line {line_number}: month {section}, day {unit} is not a date.")
        continue
      section_title = section_title or MONTHS[section - 1]
      unit_title = unit_title or f"{MONTHS[section - 1]} {unit}"
    if section in sections:
      if section_title and section_title != sections[section]:
        note(result, "problem", f"Line {line_number}: section {section} is called '{sections[section]}' earlier.")
        continue
    else:
      if not section_title:
        note(result, "problem", f"Line {line_number}: the first row of section {section} needs its section_title.")
        continue
      sections[section] = section_title
    key = (section, unit)
    if key in unit_titles:
      if unit_title and unit_title != unit_titles[key]:
        note(result, "problem", f"Line {line_number}: unit {unit} of section {section} is called '{unit_titles[key]}' earlier.")
        continue
    else:
      if not unit_title:
        note(result, "problem", f"Line {line_number}: the first row of unit {unit} of section {section} needs its unit_title.")
        continue
      unit_titles[key] = unit_title
    parts[key] = parts.get(key, 0) + 1
    entries.append(Entry(section, unit, parts[key], unit_titles[key], heading, text))
  if not entries and not result.problems:
    result.problems.append("The file has no readings.")
  if kind == "daily" and entries:
    missing = 366 - len(unit_titles)
    if missing:
      note(result, "warning", f"{missing} of the 366 days have no reading (on those days the email is skipped).")
  return Parsed(sorted(sections.items()), sorted(entries, key=lambda entry: (entry.section, entry.unit, entry.part))), result


# --- the details typed in the form ---------------------------------------------------------------------


def check_details(kind: str, details: dict) -> dict:
  """The details typed in the form, cleaned; raises UploadProblem when one is wrong."""
  cleaned = {key: " ".join(str(value or "").split()) for key, value in details.items()}
  item_id = cleaned.get("id", "").lower()
  if not ID_PATTERN.match(item_id):
    raise UploadProblem("The id must be 3 to 50 lowercase letters, digits and hyphens, such as matthew-poole.")
  known = COMMENTARIES if kind == "commentary" else SOURCES
  if item_id in known:
    raise UploadProblem(f"{item_id} is one of the texts loaded from their source; use Refresh to reload it.")
  if kind in ("devotional", "book"):
    # Devotionals and Other books share a table: an id of one may not be taken by the other.
    collection = "books" if kind == "book" else "devotionals"
    with connect() as connection:
      row = connection.execute("SELECT collection FROM devotionals WHERE id = %s", (item_id,)).fetchone()
    if row and row[0] != collection:
      other = "an Other book" if row[0] == "books" else "a devotional"
      raise UploadProblem(f"{item_id} is already {other}; choose another id.")
    cleaned["collection"] = collection
  cleaned["id"] = item_id
  required = ["name", "short_name", "source_name"] if kind == "commentary" else ["name", "author", "source_name"]
  for key in required:
    if not cleaned.get(key):
      raise UploadProblem(f"Fill in the {key.replace('_', ' ')}.")
    if len(cleaned[key]) > 200:
      raise UploadProblem(f"The {key.replace('_', ' ')} can be at most 200 characters.")
  if kind == "commentary" and len(cleaned["short_name"]) > 40:
    raise UploadProblem("The short name can be at most 40 characters (it is used on the tabs).")
  for key in ("source_url", "license_url"):
    if cleaned.get(key) and not URL_PATTERN.match(cleaned[key]):
      raise UploadProblem(f"The {key.replace('_', ' ')} must start with https:// or http://.")
  if kind == "commentary":
    cleaned["license_url"] = cleaned.get("license_url") or PUBLIC_DOMAIN_MARK
  else:
    if kind == "book":
      cleaned["kind"] = "chapters"  # an Other book is always read by chapter
    if cleaned.get("kind") not in ("daily", "chapters"):
      raise UploadProblem("Choose whether the devotional is daily or by chapter.")
    cleaned["translator"] = cleaned.get("translator") or None
  cleaned["source_url"] = cleaned.get("source_url") or ""
  return cleaned


def existing(kind: str, item_id: str):
  """What is in the database under this id now: {is_published, count}, or None."""
  table, entries = ("commentaries", "commentary_entries") if kind == "commentary" else ("devotionals", "devotional_entries")
  key = "commentary_id" if kind == "commentary" else "devotional_id"
  with connect() as connection:
    row = connection.execute(
      f"SELECT is_published, (SELECT count(*) FROM {entries} WHERE {key} = %s) FROM {table} WHERE id = %s", (item_id, item_id)
    ).fetchone()
  return {"is_published": row[0], "count": row[1]} if row else None


def preview(kind: str, path: Path, details: dict) -> dict:
  """What importing the file would do. Saves nothing."""
  cleaned = check_details(kind, details)
  if kind == "commentary":
    entries, introductions, result, book_names = read_commentary_file(path)
    covered = sorted({book for book, *_ in entries})
    summary = {
      "notes": len(entries),
      "introductions": len(introductions),
      "books": [book_names[book] for book in covered],
      "samples": [
        {"place": f"{book_names[book]} {chapter}:{verse}" + ("" if end == verse else f"–{end}" if end else " to the end of the chapter"), "text": text[:300]}
        for book, chapter, verse, end, text in entries[:3]
      ],
    }
  else:
    parsed, result = read_devotional_file(path, cleaned["kind"])
    units = sorted({(entry.section, entry.unit, entry.unit_title) for entry in parsed.entries})
    summary = {
      "readings": len(parsed.entries),
      "units": len(units),
      "sections": [title for _, title in parsed.sections],
      "samples": [
        {"place": entry.unit_title + (f" ({entry.heading})" if entry.heading else ""), "text": entry.text[:300]}
        for entry in parsed.entries[:3]
      ],
    }
  return {
    "kind": kind,
    "details": cleaned,
    "summary": summary,
    "problems": result.problems,
    "warnings": result.warnings,
    "existing": existing(kind, cleaned["id"]),
    "can_import": not result.problems,
  }


def import_file(kind: str, path: Path, details: dict) -> dict:
  """Saves the file. A new one stays hidden until published; one already there keeps its state."""
  from commentaries import save_commentary
  from devotionals import save_devotional

  cleaned = check_details(kind, details)
  if kind == "commentary":
    entries, introductions, result, _ = read_commentary_file(path)
    if result.problems:
      raise UploadProblem("The file has problems: " + " ".join(result.problems[:3]))
    count = save_commentary(
      cleaned["id"], cleaned["name"], cleaned["short_name"], cleaned["source_name"], cleaned["source_url"],
      cleaned["license_url"], entries, introductions, publish_if_new=False,
    )
  else:
    parsed, result = read_devotional_file(path, cleaned["kind"])
    if result.problems:
      raise UploadProblem("The file has problems: " + " ".join(result.problems[:3]))
    count = save_devotional(cleaned["id"], cleaned, parsed, publish_if_new=False)
  state = existing(kind, cleaned["id"])
  return {"id": cleaned["id"], "name": cleaned["name"], "count": count, "is_published": state["is_published"]}

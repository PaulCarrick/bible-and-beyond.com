"""Public-domain devotionals ("Devotionals" tab): download, read, load and look up.

Four books, from two sources:

- Spurgeon's "Morning and Evening" and "Daily Light on the Daily Path": the Christian Classics
  Ethereal Library's ThML files (https://ccel.org), each marked Public Domain in its own header.
  Both have a morning and an evening reading for every day of the year, 366 days.
- "The Imitation of Christ" (William Benham's 1886 translation, Project Gutenberg eBook #1653) and
  "The Practice of the Presence of God" (Project Gutenberg eBook #13871): plain text, read by their
  headings.

A devotional is a list of sections and, in each, units. A daily devotional's sections are months and
its units are days (a day has a morning and an evening entry). A book with chapters has its books or
parts as sections and its chapters as units (one entry each).
"""

import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from defusedxml import ElementTree

from scripture_references import find_references
from search import connect

MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
]
ORDINALS = {
  "FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5, "SIXTH": 6, "SEVENTH": 7, "EIGHTH": 8,
  "NINTH": 9, "TENTH": 10, "ELEVENTH": 11, "TWELFTH": 12, "THIRTEENTH": 13, "FOURTEENTH": 14,
  "FIFTEENTH": 15, "SIXTEENTH": 16, "SEVENTEENTH": 17, "EIGHTEENTH": 18, "NINETEENTH": 19, "TWENTIETH": 20,
}
SMALL_WORDS = {"a", "an", "and", "for", "in", "of", "on", "the", "to"}


class DevotionalProblem(ValueError):
  """A file cannot be understood. The message says what is wrong."""


@dataclass(frozen=True)
class Entry:
  section: int
  unit: int
  part: int
  unit_title: str
  heading: str  # "Morning" or "Evening"; empty for a chapter
  text: str  # paragraphs separated by a blank line


@dataclass(frozen=True)
class Parsed:
  sections: list  # [(number, title)]
  entries: list  # [Entry]


# id -> what it is, where it comes from, and how many units it must have (a file that is cut short
# or changed shape is refused rather than loaded half-way).
DEVOTIONALS = {
  "morning-and-evening": {
    "name": "Morning and Evening",
    "author": "Charles H. Spurgeon",
    "kind": "daily",
    "source_name": "Christian Classics Ethereal Library",
    "source_url": "https://ccel.org/ccel/spurgeon/morneve",
    "translator": None,
    "download_url": "https://www.ccel.org/ccel/s/spurgeon/morneve.xml",
    "file_name": "morning-and-evening.xml",
    "units": 366,
  },
  "daily-light": {
    "name": "Daily Light on the Daily Path",
    "author": "The Bagster family",
    "kind": "daily",
    "source_name": "Christian Classics Ethereal Library",
    "source_url": "https://ccel.org/ccel/anonymous/daily_light",
    "translator": None,
    "download_url": "https://www.ccel.org/ccel/a/anonymous/daily_light.xml",
    "file_name": "daily-light.xml",
    "units": 366,
  },
  "imitation-of-christ": {
    "name": "The Imitation of Christ",
    "author": "Thomas à Kempis",
    "kind": "chapters",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/1653",
    "translator": "translated by William Benham, 1886",
    "download_url": "https://www.gutenberg.org/cache/epub/1653/pg1653.txt",
    "file_name": "imitation-of-christ.txt",
    "units": 114,
  },
  "practice-of-the-presence-of-god": {
    "name": "The Practice of the Presence of God",
    "author": "Brother Lawrence",
    "kind": "chapters",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/13871",
    "translator": "translated from the French",
    "download_url": "https://www.gutenberg.org/cache/epub/13871/pg13871.txt",
    "file_name": "practice-of-the-presence-of-god.txt",
    "units": 20,
  },
}


# --- helpers ---------------------------------------------------------------------------------------------


def collapse(text):
  return re.sub(r"\s+", " ", text).strip()


def title_case(text):
  """"ADMONITIONS PROFITABLE FOR THE SPIRITUAL LIFE" as "Admonitions Profitable for the Spiritual Life"."""
  words = text.lower().split()
  return " ".join(
    word if index > 0 and word in SMALL_WORDS else word.capitalize() for index, word in enumerate(words)
  )


# --- the CCEL daily devotionals (Morning and Evening, Daily Light) ----------------------------------------------

DAILY_TITLE = re.compile(r"^(Morning|Evening), (%s) (\d{1,2})$" % "|".join(MONTHS))
# The line that opens a Daily Light reading ("JANUARY 1 MORNING"); the reading's heading says it already.
DAILY_HEADING_LINE = re.compile(r"^(%s) \d{1,2}\s*(MORNING|EVENING)$" % "|".join(month.upper() for month in MONTHS))
REFERENCE_SEPARATORS = set(".-–—;, ")


def paragraphs_of_element(element):
  """The text lines of one paragraph of a CCEL file.

  Most are one line. A Daily Light list of references ("John 17:24. -II Tim. 1:12. -Phi. 1:6.I Cor.
  9:24,25. -Heb. 12:1,2.") holds groups of references: a group runs on with ". -" and ends with a
  plain ".". Each group becomes a line of references separated by semicolons.
  """
  references = list(element.iter("scripRef"))
  full_text = "".join(element.itertext())
  if references:
    leftover = full_text
    for reference in references:
      leftover = leftover.replace("".join(reference.itertext()), "", 1)
    if leftover.strip() and set(leftover) <= REFERENCE_SEPARATORS | {"\n"}:
      lines = []
      group = []
      for reference in references:
        group.append(collapse("".join(reference.itertext())))
        if "-" not in (reference.tail or ""):
          lines.append("; ".join(group))
          group = []
      if group:
        lines.append("; ".join(group))
      return lines
  text = collapse(full_text)
  if not text or DAILY_HEADING_LINE.match(text.upper()):
    return []
  return [text]


def parse_ccel_daily(path):
  """Read a CCEL daily devotional: one morning and one evening reading for each day of the year."""
  body = ElementTree.parse(path).getroot().find("ThML.body")
  if body is None:
    raise DevotionalProblem(f"{path} has no text.")
  readings = {}
  for division in body.iter("div2"):
    match = DAILY_TITLE.match(division.get("title") or "")
    if match is None:
      continue  # the index of scripture references and the like
    period, month_name, day = match[1], match[2], int(match[3])
    lines = []
    for child in division:
      if child.tag in ("p", "h3") and child.get("class") != "crossref":
        lines.extend(paragraphs_of_element(child))
    if not lines:
      raise DevotionalProblem(f"{path}: the {period.lower()} reading of {month_name} {day} is empty.")
    readings[(MONTHS.index(month_name) + 1, day, period)] = "\n\n".join(lines)

  entries = []
  for (month, day, period), text in sorted(readings.items(), key=lambda item: (item[0][0], item[0][1], item[0][2] != "Morning")):
    entries.append(Entry(month, day, 1 if period == "Morning" else 2, f"{MONTHS[month - 1]} {day}", period, text))
  return Parsed([(number, name) for number, name in enumerate(MONTHS, start=1)], entries)


# --- the Project Gutenberg books ---------------------------------------------------------------------------------


def gutenberg_lines(path):
  """The lines of a Project Gutenberg book between its start and end notices."""
  text = Path(path).read_text(encoding="utf-8-sig").replace("\r", "")
  start = text.find("*** START OF")
  end = text.find("*** END OF")
  if start < 0 or end < 0:
    raise DevotionalProblem(f"{path} is not a Project Gutenberg text (no start and end notices).")
  return text[text.index("\n", start) + 1:end].split("\n")


def paragraphs_of_lines(lines):
  """Join the hard-wrapped lines of a book into paragraphs (a blank line ends one)."""
  paragraphs = []
  current = []
  for line in lines:
    if line.strip():
      current.append(line.strip())
    elif current:
      paragraphs.append(" ".join(current))
      current = []
  if current:
    paragraphs.append(" ".join(current))
  # Gutenberg marks italics with underscores.
  return [re.sub(r"_([^_\n]+)_", r"\1", paragraph) for paragraph in paragraphs]


BOOK_HEADING = re.compile(r"^THE (FIRST|SECOND|THIRD|FOURTH) BOOK$")
CHAPTER_HEADING = re.compile(r"^CHAPTER ([IVXLC]+)\.?$")


def parse_imitation(path):
  """Read The Imitation of Christ: four books, each of chapters."""
  lines = gutenberg_lines(path)
  # The contents at the top repeats every heading; the book itself starts at the last "THE FIRST BOOK".
  starts = [index for index, line in enumerate(lines) if line.strip() == "THE FIRST BOOK"]
  if not starts:
    raise DevotionalProblem(f"{path}: I cannot find the start of the first book.")

  sections = []
  entries = []
  section = 0
  unit = 0
  chapter = None  # (section, unit, unit_title)
  body = []

  def finish_chapter():
    if chapter is not None:
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(chapter[0], chapter[1], 1, chapter[2], "", text))

  index = starts[-1]
  while index < len(lines):
    line = lines[index].strip()
    book = BOOK_HEADING.match(line)
    chapter_heading = CHAPTER_HEADING.match(line)
    if book:
      finish_chapter()
      chapter, body = None, []
      subtitle = []
      index += 1
      while index < len(lines) and lines[index].strip():
        subtitle.append(lines[index].strip())
        index += 1
      section += 1
      unit = 0
      sections.append((section, f"The {book[1].capitalize()} Book: {title_case(' '.join(subtitle))}"))
    elif chapter_heading and section > 0:
      finish_chapter()
      body = []
      title = []
      index += 1
      while index < len(lines) and not lines[index].strip():
        index += 1
      while index < len(lines) and lines[index].strip():
        title.append(lines[index].strip())
        index += 1
      unit += 1
      chapter = (section, unit, f"Chapter {chapter_heading[1]}. {collapse(' '.join(title))}")
      continue
    elif chapter is not None:
      body.append(lines[index])
    index += 1
  finish_chapter()
  if not entries:
    raise DevotionalProblem(f"{path}: no chapters were found.")
  return Parsed(sections, entries)


PRACTICE_HEADING = re.compile(r"^([A-Z]+) (CONVERSATION|LETTER)\.?$")


def parse_practice(path):
  """Read The Practice of the Presence of God: a preface, four conversations and the letters."""
  lines = gutenberg_lines(path)
  sections = []
  entries = []
  current = None  # (section, unit, unit_title)
  body = []
  conversations_section = None
  letters_section = None
  seen_preface = False

  def finish():
    if current is not None:
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(current[0], current[1], 1, current[2], "", text))

  for line in lines:
    stripped = line.strip()
    heading = PRACTICE_HEADING.match(stripped)
    if stripped == "PREFACE." and not seen_preface:
      finish()
      seen_preface = True
      sections.append((1, "Preface"))
      current, body = (1, 1, "Preface"), []
    elif heading and heading[1] in ORDINALS and seen_preface:
      finish()
      kind = heading[2]
      if kind == "CONVERSATION" and conversations_section is None:
        conversations_section = len(sections) + 1
        sections.append((conversations_section, "Conversations"))
      if kind == "LETTER" and letters_section is None:
        letters_section = len(sections) + 1
        sections.append((letters_section, "Letters"))
      section = conversations_section if kind == "CONVERSATION" else letters_section
      current, body = (section, ORDINALS[heading[1]], f"{title_case(stripped.rstrip('.'))}"), []
    elif current is not None and stripped not in ("CONVERSATIONS.", "LETTERS."):
      body.append(line)
  finish()
  if not entries:
    raise DevotionalProblem(f"{path}: no conversations or letters were found.")
  return Parsed(sections, entries)


PARSERS = {
  "morning-and-evening": parse_ccel_daily,
  "daily-light": parse_ccel_daily,
  "imitation-of-christ": parse_imitation,
  "practice-of-the-presence-of-god": parse_practice,
}


def check_ids(devotional_ids):
  unknown = [devotional_id for devotional_id in devotional_ids if devotional_id not in DEVOTIONALS]
  if unknown:
    raise DevotionalProblem(f"Unknown devotional: {', '.join(unknown)}. Known: {', '.join(DEVOTIONALS)}.")
  return devotional_ids


def file_path(folder, devotional_id):
  return Path(folder) / DEVOTIONALS[devotional_id]["file_name"]


def read_devotional(folder, devotional_id):
  """Read one downloaded devotional and check it has all the units it should."""
  path = file_path(folder, devotional_id)
  if not path.exists():
    raise DevotionalProblem(f"{path} is missing. Download the devotionals first.")
  parsed = PARSERS[devotional_id](path)
  found = len({(entry.section, entry.unit) for entry in parsed.entries})
  expected = DEVOTIONALS[devotional_id]["units"]
  if found != expected:
    raise DevotionalProblem(f"{path}: expected {expected} days or chapters; found {found}.")
  return parsed


# --- downloading ---------------------------------------------------------------------------------------------


def download(folder, devotional_ids, report=print):
  """Save the source file of each devotional in folder. Returns the number of files saved."""
  folder = Path(folder)
  folder.mkdir(parents=True, exist_ok=True)
  saved = 0
  with httpx.Client(follow_redirects=True, timeout=120) as client:
    for devotional_id in devotional_ids:
      source = DEVOTIONALS[devotional_id]
      report(f"{devotional_id}: {source['download_url']}")
      response = client.get(source["download_url"])
      if response.status_code != 200 or len(response.content) < 10_000:
        raise DevotionalProblem(f"Could not download {source['download_url']} (status {response.status_code}).")
      file_path(folder, devotional_id).write_bytes(response.content)
      saved += 1
  return saved


# --- loading -------------------------------------------------------------------------------------------------


def replace_devotional(devotional_id, parsed):
  """Replace one devotional's sections and entries in the database, in one transaction."""
  source = DEVOTIONALS[devotional_id]
  position = list(DEVOTIONALS).index(devotional_id) + 1
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute(
        "INSERT INTO devotionals (id, name, author, kind, position, source_name, source_url, translator) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, "
        "author = EXCLUDED.author, kind = EXCLUDED.kind, position = EXCLUDED.position, "
        "source_name = EXCLUDED.source_name, source_url = EXCLUDED.source_url, translator = EXCLUDED.translator",
        (
          devotional_id, source["name"], source["author"], source["kind"], position,
          source["source_name"], source["source_url"], source["translator"],
        ),
      )
      cursor.execute("DELETE FROM devotional_entries WHERE devotional_id = %s", (devotional_id,))
      cursor.execute("DELETE FROM devotional_sections WHERE devotional_id = %s", (devotional_id,))
      with cursor.copy("COPY devotional_sections (devotional_id, number, title) FROM STDIN") as copy:
        for number, title in parsed.sections:
          copy.write_row((devotional_id, number, title))
      with cursor.copy(
        "COPY devotional_entries (devotional_id, section, unit, part, unit_title, heading, text) FROM STDIN"
      ) as copy:
        for entry in parsed.entries:
          copy.write_row((devotional_id, entry.section, entry.unit, entry.part, entry.unit_title, entry.heading, entry.text))
      cursor.execute("SELECT COUNT(*) FROM devotional_entries WHERE devotional_id = %s", (devotional_id,))
      return cursor.fetchone()[0]


# --- looking up -----------------------------------------------------------------------------------------------

DESCRIBE_COLUMNS = "id, name, author, kind, source_name, source_url, translator"


def describe(row):
  keys = ("id", "name", "author", "kind", "source_name", "source_url", "translator")
  return dict(zip(keys, row))


def list_devotionals():
  with connect() as connection:
    rows = connection.execute(f"SELECT {DESCRIBE_COLUMNS} FROM devotionals ORDER BY position").fetchall()
  return [describe(row) for row in rows]


def get_contents(devotional_id):
  """The sections of a devotional with the units in each, for choosing what to read. None if unknown."""
  with connect() as connection:
    row = connection.execute(f"SELECT {DESCRIBE_COLUMNS} FROM devotionals WHERE id = %s", (devotional_id,)).fetchone()
    if row is None:
      return None
    sections = connection.execute(
      "SELECT number, title FROM devotional_sections WHERE devotional_id = %s ORDER BY number", (devotional_id,)
    ).fetchall()
    units = connection.execute(
      "SELECT DISTINCT section, unit, unit_title FROM devotional_entries WHERE devotional_id = %s ORDER BY section, unit",
      (devotional_id,),
    ).fetchall()
  by_section = {number: {"number": number, "title": title, "units": []} for number, title in sections}
  for section, unit, title in units:
    by_section[section]["units"].append({"number": unit, "title": title})
  return {"devotional": describe(row), "sections": [section for section in by_section.values() if section["units"]]}


def get_unit(devotional_id, section, unit):
  """One day or chapter: its entries in order, with the units before and after it. None if there is none."""
  with connect() as connection:
    row = connection.execute(f"SELECT {DESCRIBE_COLUMNS} FROM devotionals WHERE id = %s", (devotional_id,)).fetchone()
    entries = connection.execute(
      "SELECT unit_title, heading, text FROM devotional_entries "
      "WHERE devotional_id = %s AND section = %s AND unit = %s ORDER BY part",
      (devotional_id, section, unit),
    ).fetchall()
    if row is None or not entries:
      return None
    section_title = connection.execute(
      "SELECT title FROM devotional_sections WHERE devotional_id = %s AND number = %s", (devotional_id, section)
    ).fetchone()[0]
    units = connection.execute(
      "SELECT DISTINCT e.section, e.unit, e.unit_title, s.title FROM devotional_entries e "
      "JOIN devotional_sections s ON s.devotional_id = e.devotional_id AND s.number = e.section "
      "WHERE e.devotional_id = %s ORDER BY e.section, e.unit",
      (devotional_id,),
    ).fetchall()

  position = next(index for index, found in enumerate(units) if (found[0], found[1]) == (section, unit))

  def neighbour(index):
    if 0 <= index < len(units):
      found_section, found_unit, title, found_section_title = units[index]
      return {"section": found_section, "unit": found_unit, "title": title, "section_title": found_section_title}
    return None

  return {
    "devotional": describe(row),
    "section": section,
    "section_title": section_title,
    "unit": unit,
    "title": entries[0][0],
    "entries": [
      {"heading": heading, "text": text, "references": find_references(text)}
      for _title, heading, text in entries
    ],
    "previous": neighbour(position - 1),
    "next": neighbour(position + 1),
  }

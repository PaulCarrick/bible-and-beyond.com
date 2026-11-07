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
from commentaries import HEADLINE_OPTIONS
from search import connect, parse_terms

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

# The "Other books" page: books read a chapter at a time, kept in the same tables with collection
# "books" (migration 017). No daily emails.
BOOKS = {
  "orthodoxy": {
    "name": "Orthodoxy",
    "author": "G. K. Chesterton",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/130",
    "translator": None,
    "download_url": "https://www.gutenberg.org/cache/epub/130/pg130.txt",
    "file_name": "orthodoxy.txt",
    "units": 10,
  },
  "confessions-of-augustine": {
    "name": "The Confessions of St. Augustine",
    "author": "Augustine of Hippo",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/3296",
    "translator": "translated by E. B. Pusey",
    "download_url": "https://www.gutenberg.org/cache/epub/3296/pg3296.txt",
    "file_name": "confessions-of-augustine.txt",
    "units": 13,
  },
  "jesus-the-christ": {
    "name": "Jesus the Christ",
    "author": "James E. Talmage",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/22542",
    "translator": None,
    "download_url": "https://www.gutenberg.org/cache/epub/22542/pg22542.txt",
    "file_name": "jesus-the-christ.txt",
    "units": 44,
  },
  "pursuit-of-god": {
    "name": "The Pursuit of God",
    "author": "A. W. Tozer",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/25141",
    "translator": None,
    "download_url": "https://www.gutenberg.org/cache/epub/25141/pg25141.txt",
    "file_name": "pursuit-of-god.txt",
    "units": 12,
  },
  "grace-abounding": {
    "name": "Grace Abounding to the Chief of Sinners",
    "author": "John Bunyan",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/654",
    "translator": None,
    "download_url": "https://www.gutenberg.org/cache/epub/654/pg654.txt",
    "file_name": "grace-abounding.txt",
    "units": 12,
  },
  "summa-theologica-part-1": {
    "name": "Summa Theologica, Part I (Prima Pars)",
    "author": "Thomas Aquinas",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/17611",
    "translator": "translated by the Fathers of the English Dominican Province",
    "download_url": "https://www.gutenberg.org/cache/epub/17611/pg17611.txt",
    "file_name": "summa-theologica-part-1.txt",
    "units": 120,
  },
  "maclaren-expositions-corinthians-to-timothy": {
    "name": "Expositions of Holy Scripture: 2 Corinthians to 1 Timothy",
    "author": "Alexander Maclaren",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/21190",
    "translator": None,
    "download_url": "https://www.gutenberg.org/cache/epub/21190/pg21190.txt",
    "file_name": "maclaren-expositions-corinthians-to-timothy.txt",
    "units": 87,
  },
  "prayers-of-the-early-church": {
    "name": "Prayers of the Early Church",
    "author": "edited by J. Manning Potts",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/48247",
    "translator": None,
    "download_url": "https://www.gutenberg.org/cache/epub/48247/pg48247.txt",
    "file_name": "prayers-of-the-early-church.txt",
    "units": 6,
  },
  "table-talk-of-martin-luther": {
    "name": "Selections from the Table Talk of Martin Luther",
    "author": "Martin Luther",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/9841",
    "translator": "translated by Captain Henry Bell",
    "download_url": "https://www.gutenberg.org/cache/epub/9841/pg9841.txt",
    "file_name": "table-talk-of-martin-luther.txt",
    "units": 13,
  },
  "summa-theologica-part-2-2": {
    "name": "Summa Theologica, Part II-II (Secunda Secundae)",
    "author": "Thomas Aquinas",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/18755",
    "translator": "translated by the Fathers of the English Dominican Province",
    "download_url": "https://www.gutenberg.org/cache/epub/18755/pg18755.txt",
    "file_name": "summa-theologica-part-2-2.txt",
    "units": 189,
  },
  "summa-theologica-part-3": {
    "name": "Summa Theologica, Part III (Tertia Pars)",
    "author": "Thomas Aquinas",
    "kind": "chapters",
    "collection": "books",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/19950",
    "translator": "translated by the Fathers of the English Dominican Province",
    "download_url": "https://www.gutenberg.org/cache/epub/19950/pg19950.txt",
    "file_name": "summa-theologica-part-3.txt",
    "units": 91,
  },
}

# Everything that can be downloaded and loaded from a known source, devotionals and books.
SOURCES = {**DEVOTIONALS, **BOOKS}


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


ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"]
ORTHODOXY_HEADING = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX) ([A-Z][A-Z ,'-]+)$")
CONFESSIONS_HEADING = re.compile(r"^BOOK (%s)$" % "|".join(ROMAN_NUMERALS))


def parse_orthodoxy(path):
  """Read Orthodoxy (G. K. Chesterton): the preface, then nine chapters headed "II THE MANIAC"."""
  lines = gutenberg_lines(path)
  titles = {}  # chapter number -> title as the contents list writes it ("The Maniac")
  for line in lines:
    match = re.match(r"^\s*(I|II|III|IV|V|VI|VII|VIII|IX)\.\s+(\S.*)$", line)
    if match:
      titles.setdefault(ROMAN_NUMERALS.index(match[1]) + 1, match[2].strip())
  sections = [(1, "Preface"), (2, "Chapters")]
  entries = []
  current = None
  body = []

  def finish():
    if current is not None:
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(current[0], current[1], 1, current[2], "", text))

  for line in lines:
    stripped = line.strip()
    heading = ORTHODOXY_HEADING.match(stripped)
    if stripped == "PREFACE" and current is None:
      current, body = (1, 1, "Preface"), []
    elif heading and current is not None:
      finish()
      number = ROMAN_NUMERALS.index(heading[1]) + 1
      current, body = (2, number, titles.get(number) or title_case(heading[2])), []
    elif stripped == "CONTENTS" and current is not None and current[0] == 1:
      # The contents list ends the preface; the chapters' own headings follow.
      finish()
      current, body = (0, 0, ""), []
    elif current is not None and current[0] != 0:
      body.append(line)
  finish()
  entries = [entry for entry in entries if entry.section != 0]
  if not entries:
    raise DevotionalProblem(f"{path}: no chapters were found.")
  return Parsed(sections, entries)


def parse_confessions(path):
  """Read the Confessions of St. Augustine (Pusey): thirteen Books, each one unit to read."""
  lines = gutenberg_lines(path)
  entries = []
  current = None
  body = []

  def finish():
    if current is not None:
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(1, current, 1, f"Book {ROMAN_NUMERALS[current - 1]}", "", text))

  for line in lines:
    heading = CONFESSIONS_HEADING.match(line.strip())
    if heading:
      finish()
      current, body = ROMAN_NUMERALS.index(heading[1]) + 1, []
    elif current is not None:
      body.append(line)
  finish()
  if not entries:
    raise DevotionalProblem(f"{path}: no Books were found.")
  return Parsed([(1, "The Confessions")], entries)


TALMAGE_CHAPTER = re.compile(r"^CHAPTER (\d+)\.$")


def parse_jesus_the_christ(path):
  """Read Jesus the Christ (James E. Talmage): two prefaces, then 42 chapters headed "CHAPTER 2." with the
  title in capitals on the lines after. Each chapter's notes and footnotes stay at its end."""
  lines = gutenberg_lines(path)
  sections = [(1, "Prefaces"), (2, "Chapters")]
  entries = []
  current = None  # (section, unit, title); section 0 while skipping the contents list
  body = []
  title_lines = None  # collecting a chapter's title, until the first blank line after it

  def finish():
    if current is not None and current[0] != 0:
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(current[0], current[1], 1, current[2], "", text))

  for line in lines:
    stripped = line.strip()
    chapter = TALMAGE_CHAPTER.match(stripped)
    if title_lines is not None:
      if stripped:
        title_lines.append(stripped)
        continue
      if title_lines:
        current = (current[0], current[1], title_case(" ".join(title_lines).rstrip(".")))
        title_lines = None
      continue
    if stripped == "PREFACE." and current is None:
      current, body = (1, 1, "Preface"), []
    elif stripped == "PREFACE TO THE SIXTH EDITION." and current is not None and current[0] == 1:
      finish()
      current, body = (1, 2, "Preface to the Sixth Edition"), []
    elif stripped == "CONTENTS." and current is not None and current[0] == 1:
      finish()
      current, body = (0, 0, ""), []
    elif chapter and current is not None:
      finish()
      current, body, title_lines = (2, int(chapter[1]), ""), [], []
    elif current is not None and current[0] != 0:
      body.append(line)
  finish()
  if not entries:
    raise DevotionalProblem(f"{path}: no chapters were found.")
  return Parsed(sections, entries)


def parse_pursuit_of_god(path):
  """Read The Pursuit of God (A. W. Tozer): Samuel Zwemer's introduction, the preface, then ten chapters, each
  a line with its Roman numeral followed by its title in italics."""
  lines = gutenberg_lines(path)
  sections = [(1, "Introduction and Preface"), (2, "Chapters")]
  entries = []
  current = None
  body = []
  awaiting_title = False

  def finish():
    if current is not None:
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(current[0], current[1], 1, current[2], "", text))

  for line in lines:
    stripped = line.strip()
    if awaiting_title:
      if stripped:
        current = (current[0], current[1], stripped.strip("_").strip())
        awaiting_title = False
      continue
    if stripped == "Introduction" and current is None:
      current, body = (1, 1, "Introduction"), []
    elif stripped == "Preface" and current is not None and current[:2] == (1, 1):
      finish()
      current, body = (1, 2, "Preface"), []
    elif stripped in ROMAN_NUMERALS[:10] and current is not None:
      finish()
      current, body, awaiting_title = (2, ROMAN_NUMERALS.index(stripped) + 1, ""), [], True
    elif current is not None:
      body.append(line)
  finish()
  if not entries:
    raise DevotionalProblem(f"{path}: no chapters were found.")
  return Parsed(sections, entries)


PAGE_MARK = re.compile(r"\{\d+\}")


def parse_grace_abounding(path):
  """Read Grace Abounding (John Bunyan): the preface, the 339 numbered paragraphs in groups of 50, the account
  of his imprisonment and the conclusion; then A Relation of My Imprisonment and the postscript. The
  edition's page numbers ({17}) and picture notes are left out."""
  lines = [PAGE_MARK.sub("", line) for line in gutenberg_lines(path) if not line.strip().startswith("[Picture")]
  sections = [(1, "Grace Abounding"), (2, "A Relation of My Imprisonment")]
  headings = {
    "A PREFACE": (1, "A Preface"),
    "A BRIEF ACCOUNT OF THE AUTHOR’S IMPRISONMENT": (1, "A Brief Account of the Author’s Imprisonment"),
    "THE CONCLUSION": (1, "The Conclusion"),
    "A RELATION OF MY IMPRISONMENT IN THE MONTH OF NOVEMBER 1660": (2, "A Relation of My Imprisonment"),
    "POSTSCRIPT": (2, "Postscript"),
  }
  entries = []
  units = {1: 0, 2: 0}
  current = None  # (section, unit, title)
  body = []
  in_main = False

  def finish():
    if current is not None:
      # A part's heading may be followed by a subtitle in capitals ("OR, BRIEF ACCOUNT OF ..."): left out.
      while body and (not body[0].strip() or body[0].strip().isupper()):
        body.pop(0)
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(current[0], current[1], 1, current[2], "", text))

  def start(section, title):
    nonlocal current, body
    finish()
    units[section] += 1
    current, body = (section, units[section], title), []

  # The 339 numbered paragraphs (the first has no number) are read in groups of 50, each titled with the
  # paragraphs it holds; the headings after them each begin a unit of their own.
  past_contents = False
  in_main = False
  first_paragraph = last_paragraph = 0

  def start_group(first):
    nonlocal first_paragraph, last_paragraph
    start(1, "")
    first_paragraph = last_paragraph = first

  def close_group():
    if current is not None and current[2] == "":
      retitle(f"Paragraphs {first_paragraph}–{last_paragraph}")

  def retitle(title):
    nonlocal current
    current = (current[0], current[1], title)

  for line in lines:
    stripped = line.strip()
    paragraph = re.match(r"^(\d{1,3})\.  ", line)
    if not past_contents:
      if stripped == "A PREFACE":
        past_contents = True
        start(*headings[stripped])
      continue
    if stripped == "GRACE ABOUNDING TO THE CHIEF OF SINNERS" and not in_main:
      in_main = True
      start_group(1)
    elif stripped in headings:
      if in_main:
        close_group()
        in_main = False
      start(*headings[stripped])
    elif in_main and paragraph:
      number = int(paragraph[1])
      if (number - 1) % 50 == 0:
        close_group()
        start_group(number)
      last_paragraph = number
      body.append(line)
    elif current is not None and not (in_main and stripped.startswith("A BRIEF RELATION OF THE EXCEEDING")):
      body.append(line)
  close_group()
  finish()
  if not entries:
    raise DevotionalProblem(f"{path}: nothing was found.")
  return Parsed(sections, entries)


SUMMA_QUESTION = re.compile(r"^QUESTION (\d{1,3})$")
# The treatises of each Part, by the Question each begins at (the texts have no headings for them).
SUMMA_TREATISES_PART_2_2 = [
  (1, "Treatise on the Theological Virtues"), (47, "Treatise on Prudence and Justice"),
  (123, "Treatise on Fortitude and Temperance"), (171, "Treatise on Gratuitous Graces"),
  (183, "Treatise on the States of Life"),
]
SUMMA_TREATISES_PART_3 = [
  (1, "Treatise on the Incarnation"), (60, "Treatise on the Sacraments"), (66, "Treatise on Baptism"),
  (72, "Treatise on Confirmation"), (73, "Treatise on the Holy Eucharist"), (84, "Treatise on Penance"),
]
SUMMA_TREATISES = [
  (1, "Sacred Doctrine"), (2, "Treatise on the One God"), (27, "Treatise on the Trinity"),
  (44, "Treatise on the Creation"), (50, "Treatise on the Angels"), (65, "Treatise on the Work of the Six Days"),
  (75, "Treatise on Man"), (103, "Treatise on the Divine Government"),
]


def parse_summa_part_1(path):
  return parse_summa(path, SUMMA_TREATISES)


def parse_summa_part_2_2(path):
  return parse_summa(path, SUMMA_TREATISES_PART_2_2)


def parse_summa_part_3(path):
  return parse_summa(path, SUMMA_TREATISES_PART_3)


# "TREATISE ON MAN (QQ. 75-102)": a heading between two Questions, shown as the section instead.
SUMMA_TREATISE_LINE = re.compile(r"^TREATISE ON .*\(QQ?\. \d")
# "(In Ten Articles)", "(TWELVE ARTICLES)" or "(Four Articles)" at the end of a Question's title line.
SUMMA_ARTICLE_COUNT = re.compile(r"\s*\((?:in\s+)?[a-z]+\s+articles?\)$", re.IGNORECASE)


SUMMA_ARTICLE_COUNT_LINE = re.compile(r"^\((?:in\s+)?[a-z]+\s+articles?\)$", re.IGNORECASE)


def summa_title(line):
  return title_case(SUMMA_ARTICLE_COUNT.sub("", line))


def parse_summa(path, treatises):
  """Read a Part of the Summa Theologica (the English Dominican translation): its prologue, then its Questions
  (each with its articles), grouped by treatise. A Question's title is the capitals line after "QUESTION 2".
  The prologue is the one just before Question 1 (Part I also names it in its contents list)."""
  lines = gutenberg_lines(path)
  SUMMA_TREATISES = treatises
  first_question = next(index for index, line in enumerate(lines) if line.strip() == "QUESTION 1")
  prologue_line = max((index for index, line in enumerate(lines[:first_question]) if line.strip() == "PROLOGUE"), default=None)
  sections = ([(0, "Prologue")] if prologue_line is not None else []) + [
    (index + 1, title) for index, (_, title) in enumerate(SUMMA_TREATISES)
  ]
  entries = []
  current = None
  body = []
  awaiting_title = False

  def treatise(question):
    return max(index + 1 for index, (first, _) in enumerate(SUMMA_TREATISES) if first <= question)

  def finish():
    if current is not None:
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(current[0], current[1], 1, current[2], "", text))

  prologues = 0
  after_separator = False
  for index, line in enumerate(lines):
    stripped = line.strip()
    question = SUMMA_QUESTION.match(stripped)
    # One Question (116, "On Fate") has no "QUESTION 116" line: just the separator, then its title in capitals
    # and "(In Four Articles)". Such a title starts the next Question.
    following = lines[index + 1].strip() if index + 1 < len(lines) else ""
    if (not question and after_separator and current is not None and current[0] != 0 and stripped.isupper()
        and following.lower().startswith("(in ") and following.lower().rstrip(")").endswith("articles")):
      finish()
      number = current[1] + 1
      current, body = (treatise(number), number, f"Question {number}: {summa_title(stripped)}"), []
      after_separator = False
      continue
    if stripped:
      after_separator = set(stripped) == {"_"}
    if after_separator or SUMMA_TREATISE_LINE.match(stripped) or SUMMA_ARTICLE_COUNT_LINE.match(stripped):
      continue  # a separator line (only underscores), a treatise heading, or "(In Ten Articles)" under a title
    if awaiting_title:
      if stripped:
        number = current[1]
        current = (current[0], number, f"Question {number}: {summa_title(stripped)}")
        awaiting_title = False
      continue
    if index == prologue_line:
      prologues += 1
      current, body = (0, 1, "Prologue"), []
    elif question and index >= first_question:
      finish()
      number = int(question[1])
      current, body, awaiting_title = (treatise(number), number, ""), [], True
    elif current is not None:
      body.append(line)
  finish()
  if not entries:
    raise DevotionalProblem(f"{path}: no Questions were found.")
  return Parsed(sections, entries)


MACLAREN_LETTERS = {
  "II. CORINTHIANS": "2 Corinthians", "GALATIANS": "Galatians", "PHILIPPIANS": "Philippians",
  "COLOSSIANS": "Colossians", "I. THESSALONIANS": "1 Thessalonians", "II. THESSALONIANS": "2 Thessalonians",
  "I. TIMOTHY": "1 Timothy",
}
MACLAREN_CONTENTS_ENTRY = re.compile(r"^(\S.*?)\s+\((.+?)\)\s+\d+$")


def parse_maclaren_expositions(path):
  """Read a volume of Maclaren's Expositions of Holy Scripture: one sermon per unit, grouped by letter. The
  contents lists (one per original volume) name each sermon, with its text, under its letter; in the body each
  sermon begins with its title alone on a line."""
  lines = gutenberg_lines(path)
  sermons = []  # (letter, title in capitals, reference)
  letter = None
  for line in lines:
    stripped = line.strip()
    if stripped in MACLAREN_LETTERS:
      letter = MACLAREN_LETTERS[stripped]
    entry = MACLAREN_CONTENTS_ENTRY.match(stripped)
    if entry and letter:
      sermons.append((letter, entry[1].strip(), entry[2].strip()))
  letters = list(dict.fromkeys(letter for letter, _, _ in sermons))
  sections = [(index + 1, letter) for index, letter in enumerate(letters)]
  entries = []
  position = 0
  current = None
  body = []
  units = {}

  def finish():
    if current is not None:
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(current[0], current[1], 1, current[2], "", text))

  def comparable(title):
    return re.sub(r"\bTHE\b|[^A-Z]", "", title.upper())

  for line in lines:
    stripped = line.strip()
    if position < len(sermons) and stripped.isupper() and comparable(stripped) == comparable(sermons[position][1]):
      finish()
      letter, title, reference = sermons[position]
      section = letters.index(letter) + 1
      units[section] = units.get(section, 0) + 1
      current, body = (section, units[section], f"{title_case(title.strip(chr(39)))} ({reference})"), []
      position += 1
    elif current is not None:
      if stripped in ("CONTENTS", "_EXPOSITIONS OF HOLY SCRIPTURE_"):
        # The next volume's title page and contents: the last sermon of a volume ends here.
        finish()
        current = None
      elif stripped not in MACLAREN_LETTERS:
        body.append(line)
  finish()
  if position != len(sermons):
    raise DevotionalProblem(f"{path}: found {position} of the {len(sermons)} sermons in the contents.")
  return Parsed(sections, entries)


CENTURY_CHAPTER = re.compile(r"^Chapter (I|II|III|IV|V)$")


def parse_prayers_of_the_early_church(path):
  """Read Prayers of the Early Church (ed. J. Manning Potts): the preface and five chapters, one per century,
  each "Chapter II" with its title ("SECOND CENTURY PRAYERS") on the next line. The index is left out."""
  lines = gutenberg_lines(path)
  sections = [(1, "Preface"), (2, "Chapters")]
  entries = []
  current = None
  body = []
  awaiting_title = False
  in_body = False

  def finish():
    if current is not None:
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(current[0], current[1], 1, current[2], "", text))

  for line in lines:
    stripped = line.strip()
    if awaiting_title:
      if stripped:
        current = (current[0], current[1], title_case(stripped))
        awaiting_title = False
      continue
    chapter = CENTURY_CHAPTER.match(stripped)
    if stripped == "Preface" and current is None:
      current, body = (1, 1, "Preface"), []
    elif stripped == "Contents" and current is not None and current[0] == 1:
      finish()
      current = None
    elif chapter and in_body:
      # The contents list names the chapters too; the body's chapters come after it, with no page numbers.
      finish()
      current, body, awaiting_title = (2, ROMAN_NUMERALS.index(chapter[1]) + 1, ""), [], True
    elif stripped == "INDEX" and current is not None and current[0] == 2:
      finish()
      current = None
      break
    elif current is not None:
      body.append(line)
    if stripped.startswith("FIFTH CENTURY PRAYERS") and stripped[-1].isdigit():
      in_body = True  # the last line of the contents list
  finish()
  if not entries:
    raise DevotionalProblem(f"{path}: no chapters were found.")
  return Parsed(sections, entries)


TABLE_TALK_TOPIC = re.compile(r"^(OF [A-Z][A-Z ’',-]+)\.$")


def parse_table_talk(path):
  """Read the Selections from the Table Talk of Martin Luther (Henry Bell): the introduction and Bell's
  narrative, then the ten topics ("OF GOD’S WORD."), and the edition's footnotes last."""
  lines = [PAGE_MARK.sub("", line) for line in gutenberg_lines(path) if not line.strip().startswith("[Picture")]
  sections = [(1, "Introduction"), (2, "Table Talk")]
  entries = []
  current = None
  body = []
  topics = 0

  def finish():
    if current is not None:
      text = "\n\n".join(paragraphs_of_lines(body))
      if text:
        entries.append(Entry(current[0], current[1], 1, current[2], "", text))

  for line in lines:
    stripped = line.strip()
    topic = TABLE_TALK_TOPIC.match(stripped)
    if stripped == "INTRODUCTION." and current is None:
      current, body = (1, 1, "Introduction"), []
    elif stripped.startswith("CAPTAIN HENRY BELL’S NARRATIVE") and current is not None and current[0] == 1:
      finish()
      current, body = (1, 2, "Captain Henry Bell’s Narrative"), [line]
    elif stripped == "LUTHER’S TABLE-TALK.":
      finish()
      current = None
    elif topic and current is None or (topic and current is not None and current[0] == 2):
      finish()
      topics += 1
      current, body = (2, topics, title_case(topic[1])), []
    elif stripped == "FOOTNOTES" and current is not None:
      finish()
      current, body = (2, topics + 1, "Footnotes"), []
    elif current is not None:
      body.append(line)
  finish()
  if topics == 0:
    raise DevotionalProblem(f"{path}: no topics were found.")
  return Parsed(sections, entries)


PARSERS = {
  "prayers-of-the-early-church": parse_prayers_of_the_early_church,
  "table-talk-of-martin-luther": parse_table_talk,
  "grace-abounding": parse_grace_abounding,
  "summa-theologica-part-1": parse_summa_part_1,
  "summa-theologica-part-2-2": parse_summa_part_2_2,
  "summa-theologica-part-3": parse_summa_part_3,
  "maclaren-expositions-corinthians-to-timothy": parse_maclaren_expositions,
  "pursuit-of-god": parse_pursuit_of_god,
  "jesus-the-christ": parse_jesus_the_christ,
  "orthodoxy": parse_orthodoxy,
  "confessions-of-augustine": parse_confessions,
  "morning-and-evening": parse_ccel_daily,
  "daily-light": parse_ccel_daily,
  "imitation-of-christ": parse_imitation,
  "practice-of-the-presence-of-god": parse_practice,
}


def check_ids(devotional_ids):
  unknown = [devotional_id for devotional_id in devotional_ids if devotional_id not in SOURCES]
  if unknown:
    raise DevotionalProblem(f"Unknown devotional or book: {', '.join(unknown)}. Known: {', '.join(SOURCES)}.")
  return devotional_ids


def file_path(folder, devotional_id):
  return Path(folder) / SOURCES[devotional_id]["file_name"]


def read_devotional(folder, devotional_id):
  """Read one downloaded devotional and check it has all the units it should."""
  path = file_path(folder, devotional_id)
  if not path.exists():
    raise DevotionalProblem(f"{path} is missing. Download the devotionals first.")
  parsed = PARSERS[devotional_id](path)
  found = len({(entry.section, entry.unit) for entry in parsed.entries})
  expected = SOURCES[devotional_id]["units"]
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
      source = SOURCES[devotional_id]
      report(f"{devotional_id}: {source['download_url']}")
      response = client.get(source["download_url"])
      if response.status_code != 200 or len(response.content) < 10_000:
        raise DevotionalProblem(f"Could not download {source['download_url']} (status {response.status_code}).")
      file_path(folder, devotional_id).write_bytes(response.content)
      saved += 1
  return saved


# --- loading -------------------------------------------------------------------------------------------------


def replace_devotional(devotional_id, parsed):
  """Replace one of the known devotionals or books (SOURCES) in the database, in one transaction.

  It keeps its place in the order and, if it was there already, whether it is published.
  """
  return save_devotional(
    devotional_id, SOURCES[devotional_id], parsed,
    publish_if_new=True, position=list(SOURCES).index(devotional_id) + 1,
  )


def save_devotional(devotional_id, details, parsed, publish_if_new, position=None):
  """Replace one devotional, known or uploaded, in one transaction. Returns its entry count.

  details has name, author, kind, source_name, source_url, translator and collection ("devotionals", the
  default, or "books"). A devotional that was there
  already keeps whether it is published; a new one is published only when publish_if_new. With no position
  it keeps its place, or a new one goes last.
  """
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute(
        "INSERT INTO devotionals (id, name, author, kind, position, source_name, source_url, translator, is_published, collection) "
        "VALUES (%s, %s, %s, %s, COALESCE(%s, (SELECT COALESCE(MAX(position), 0) + 1 FROM devotionals)), %s, %s, %s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, "
        "author = EXCLUDED.author, kind = EXCLUDED.kind, position = COALESCE(%s, devotionals.position), "
        "source_name = EXCLUDED.source_name, source_url = EXCLUDED.source_url, translator = EXCLUDED.translator, "
        "collection = EXCLUDED.collection",
        (
          devotional_id, details["name"], details["author"], details["kind"], position,
          details["source_name"], details["source_url"], details.get("translator"), publish_if_new,
          details.get("collection", "devotionals"), position,
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


def list_devotionals(collection="devotionals"):
  """The published devotionals, or with collection "books" the published Other books, in their order."""
  with connect() as connection:
    rows = connection.execute(
      f"SELECT {DESCRIBE_COLUMNS} FROM devotionals WHERE is_published AND collection = %s ORDER BY position", (collection,)
    ).fetchall()
  return [describe(row) for row in rows]


def list_books():
  return list_devotionals("books")


def get_contents(devotional_id):
  """The sections of a devotional with the units in each, for choosing what to read. None if unknown."""
  with connect() as connection:
    row = connection.execute(f"SELECT {DESCRIBE_COLUMNS} FROM devotionals WHERE id = %s AND is_published", (devotional_id,)).fetchone()
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
    row = connection.execute(f"SELECT {DESCRIBE_COLUMNS} FROM devotionals WHERE id = %s AND is_published", (devotional_id,)).fetchone()
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


def search_books(query, match_mode, book_id, page, per_page, sort_by):
  """Search the text of the published Other books (see search_library)."""
  return search_library(query, match_mode, "books", book_id, page, per_page, sort_by)


def search_library(query, match_mode, collection, book_id, page, per_page, sort_by):
  """Search the text of the published devotionals or Other books (collection "devotionals" or "books").

  Matching is the commentary search's (see search_commentaries): words in any form, no word ignored for
  being common; all words, any word, or an exact phrase. Results are the best matches first, or in the
  order of the books and their chapters when sort_by is "order". Each result is one passage (an entry of
  a chapter), with an excerpt around the words found, wrapped in \\u0001 and \\u0002.
  """
  terms = parse_terms(query, match_mode)
  if not terms:
    raise ValueError("Enter at least one word or phrase to search for.")
  joiner = " || " if match_mode == "any" else " && "
  tsquery = joiner.join(["phraseto_tsquery('commentary_english', %s)"] * len(terms))

  with connect() as connection:
    if book_id is not None and connection.execute(
      "SELECT 1 FROM devotionals WHERE id = %s AND is_published AND collection = %s", (book_id, collection)
    ).fetchone() is None:
      raise ValueError(f"Unknown {'book' if collection == 'books' else 'devotional'}: {book_id}")
    if connection.execute(f"SELECT numnode({tsquery})", terms).fetchone()[0] == 0:
      raise ValueError("Enter at least one word or phrase to search for.")

    conditions = f"e.search_vector @@ ({tsquery}) AND d.is_published AND d.collection = %s"
    book_counts = [
      {"book": found_id, "name": name, "count": count}
      for found_id, name, count in connection.execute(
        f"SELECT d.id, d.name, count(*) FROM devotional_entries e JOIN devotionals d ON d.id = e.devotional_id "
        f"WHERE {conditions} GROUP BY d.id, d.name, d.position ORDER BY d.position",
        [*terms, collection],
      ).fetchall()
    ]
    total = sum(entry["count"] for entry in book_counts if book_id is None or entry["book"] == book_id)

    if sort_by == "order":
      order = "d.position, e.section, e.unit, e.part"
    else:
      order = "rank DESC, d.position, e.section, e.unit, e.part"
    # Choose the page first, then build excerpts for just those passages (an excerpt reads the whole text).
    page_rows = connection.execute(
      f"""
      SELECT e.devotional_id, e.section, e.unit, e.part, ts_rank_cd(e.search_vector, ({tsquery}), 1) AS rank
      FROM devotional_entries e
      JOIN devotionals d ON d.id = e.devotional_id
      WHERE {conditions} AND (%s::text IS NULL OR e.devotional_id = %s)
      ORDER BY {order}
      LIMIT %s OFFSET %s
      """,
      [*terms, *terms, collection, book_id, book_id, per_page, (page - 1) * per_page],
    ).fetchall()
    results = []
    for found_id, section, unit, part, _rank in page_rows:
      name, section_title, unit_title, heading, excerpt = connection.execute(
        f"""
        SELECT d.name, s.title, e.unit_title, e.heading, ts_headline('commentary_english', e.text, ({tsquery}), %s)
        FROM devotional_entries e
        JOIN devotionals d ON d.id = e.devotional_id
        JOIN devotional_sections s ON s.devotional_id = e.devotional_id AND s.number = e.section
        WHERE e.devotional_id = %s AND e.section = %s AND e.unit = %s AND e.part = %s
        """,
        [*terms, HEADLINE_OPTIONS, found_id, section, unit, part],
      ).fetchone()
      results.append({
        "book": found_id,
        "book_name": name,
        "section": section,
        "section_title": section_title,
        "unit": unit,
        "unit_title": unit_title,
        "heading": heading,
        "text": excerpt,
      })

  return {
    "query": query,
    "terms": terms,
    "total": total,
    "page": page,
    "per_page": per_page,
    "book_counts": book_counts,
    "results": results,
  }

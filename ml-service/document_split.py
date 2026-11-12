"""Cutting a converted document (document_import.py) into what each upload needs.

  Books and chapter devotionals  by headings: with two levels or more, the top level starts a part and the next
                                 a chapter (deeper headings stay inside the chapter); with one level, each
                                 heading starts a chapter; with none, the whole document is one chapter. Text
                                 before the first heading becomes an "Introduction" chapter.
  Daily devotionals              by headings that are dates ("January 1", "1 January", "Jan. 1"), with an
                                 optional "Morning" or "Evening" in the heading or as a heading of its own.
  Commentaries                   by headings that name a passage: a book ("John"), a chapter ("John 3",
                                 "Chapter 3"), or verses ("John 3:16", "3:16-18", "Verse 16", "Verses 16-18").
                                 Text before a chapter's first verse is the chapter's introduction, and before
                                 a book's first chapter the book's. Without such headings, the whole document is
                                 one note on the passage typed in the upload form.
  Song words                     the whole document.
"""

import re
from dataclasses import dataclass, field

from bible_import.importer import normalize_book_name
from devotionals import MONTHS, Entry
from document_import import Document, Piece, heading_level, heading_text, piece_of, top_blocks

DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MONTH_NAMES = {month.lower(): number for number, month in enumerate(MONTHS, 1)}
MONTH_NAMES.update({month.lower()[:3]: number for number, month in enumerate(MONTHS, 1)})
MONTH_NAMES["sept"] = 9
MONTH_PATTERN = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
DATE = re.compile(
  rf"^(?:(?P<first>morning|evening)[\s,:–—-]+)?(?:(?P<month>{MONTH_PATTERN})\.?\s+(?P<day>\d{{1,2}})|(?P<day2>\d{{1,2}})\s+(?P<month2>{MONTH_PATTERN})\.?)"
  rf"(?:[\s,:–—-]+(?P<last>morning|evening))?\.?$",
  re.IGNORECASE,
)
TIME_OF_DAY = re.compile(r"^(morning|evening)\.?$", re.IGNORECASE)
DASHES = r"\s*(?:[-–—]|to|and|,)\s*"


@dataclass
class Split:
  problems: list = field(default_factory=list)
  warnings: list = field(default_factory=list)


# --- books and chapter devotionals ---------------------------------------------------------------------


def split_chapters(document: Document, default_title: str):
  """(sections [(number, title)], entries [Entry], Split)."""
  split = Split(warnings=list(document.warnings))
  blocks = top_blocks(document.html)
  levels = sorted({level for block in blocks if (level := heading_level(block))})
  part_level = levels[0] if len(levels) >= 2 else None
  chapter_level = levels[1] if len(levels) >= 2 else levels[0] if levels else None
  sections: list[tuple[int, str]] = []
  entries: list[Entry] = []
  current: list = []
  current_title = "Introduction"
  section_title = default_title

  def close_chapter():
    nonlocal current
    piece = piece_of(current, document.footnotes)
    if piece and not entries and current_title == "Introduction" and len(piece.text) < 200 and "<img" not in piece.html and chapter_level is not None:
      split.warnings.append(f"The short text before the first heading (\"{piece.text[:60]}\") was left out, as a title page.")
      piece = None
    if piece:
      if not sections:
        sections.append((1, section_title))
      section = sections[-1][0]
      unit = sum(1 for entry in entries if entry.section == section) + 1
      entries.append(Entry(section, unit, 1, current_title[:200], "", piece.text, piece.html))
    current = []

  for block in blocks:
    level = heading_level(block)
    if part_level is not None and level == part_level:
      close_chapter()
      section_title = heading_text(block)[:200]
      sections.append((len(sections) + 1, section_title))
      current_title = section_title
    elif chapter_level is not None and level == chapter_level:
      close_chapter()
      current_title = heading_text(block)
      if not sections:
        sections.append((1, section_title))
    else:
      current.append(block)
  close_chapter()
  if chapter_level is None and entries:
    entries = [Entry(entry.section, entry.unit, entry.part, default_title[:200], "", entry.text, entry.html) for entry in entries]
  if not entries:
    split.problems.append("No text was found in the document.")
  return sections, entries, split


# --- daily devotionals ---------------------------------------------------------------------------------


def parse_date(text: str):
  """(month, day, "Morning"/"Evening"/"") for a date heading, else None."""
  match = DATE.match(" ".join(text.split()))
  if not match:
    return None
  month = MONTH_NAMES[(match.group("month") or match.group("month2")).lower().rstrip(".")]
  day = int(match.group("day") or match.group("day2"))
  if not 1 <= day <= DAYS_IN_MONTH[month - 1]:
    return None
  time = (match.group("first") or match.group("last") or "").capitalize()
  return month, day, time


def split_daily(document: Document):
  """(sections [(month, name)], entries [Entry], Split) for a devotional with a reading for each day."""
  split = Split(warnings=list(document.warnings))
  readings: dict[tuple[int, int], list] = {}
  order: list[tuple[int, int, str]] = []
  current = None
  current_heading = ""
  before = 0
  for block in top_blocks(document.html):
    level = heading_level(block)
    date = parse_date(heading_text(block)) if level else None
    if date:
      month, day, time = date
      current = (month, day)
      current_heading = time
      order.append((month, day, time))
      readings.setdefault((month, day, time), [])
      continue
    if level and current and TIME_OF_DAY.match(heading_text(block)):
      current_heading = heading_text(block).rstrip(".").capitalize()
      order.append((*current, current_heading))
      readings.setdefault((*current, current_heading), [])
      continue
    if current is None:
      before += 1
      continue
    readings[(*current, current_heading)].append(block)
  if before:
    split.warnings.append("The text before the first date heading was left out.")
  entries = []
  parts: dict[tuple[int, int], int] = {}
  seen = set()
  for month, day, time in order:
    if (month, day, time) in seen:
      continue
    seen.add((month, day, time))
    piece = piece_of(readings[(month, day, time)], document.footnotes)
    if not piece:
      continue
    parts[(month, day)] = parts.get((month, day), 0) + 1
    entries.append(Entry(month, day, parts[(month, day)], f"{MONTHS[month - 1]} {day}", time, piece.text, piece.html))
  if not entries:
    split.problems.append('No date headings were found. Mark each day with a heading such as "January 1" (and "Morning" or "Evening" if it has both).')
  else:
    missing = 366 - len(parts)
    if missing:
      split.warnings.append(f"{missing} of the 366 days have no reading (on those days the email is skipped).")
  sections = sorted({(month, MONTHS[month - 1]) for month, *_ in parts})
  return sections, sorted(entries, key=lambda entry: (entry.section, entry.unit, entry.part)), split


# --- commentaries --------------------------------------------------------------------------------------


def _leading_book(text: str, book_lookup: dict):
  """(book number, the rest of the text) when the text starts with a book's name, else (None, text)."""
  words = text.split()
  for count in range(min(5, len(words)), 0, -1):
    candidate = " ".join(words[:count]).rstrip(".:,")
    book = book_lookup.get(normalize_book_name(candidate))
    if book:
      return book, " ".join(words[count:])
  for prefix in ("the book of ", "the gospel according to ", "the gospel of ", "book of ", "gospel of "):
    if text.lower().startswith(prefix):
      return _leading_book(text[len(prefix):], book_lookup)
  return None, text


def parse_passage_heading(text: str, book_lookup: dict, book: int | None, chapter: int | None):
  """What a heading names: ("book", book), ("chapter", book, chapter), ("verses", book, chapter, verse, end)
  (end None for "to the end of the chapter"), or None when it names no passage."""
  text = " ".join(text.replace(" ", " ").split()).rstrip(".")
  found_book, rest = _leading_book(text, book_lookup)
  book = found_book or book
  if found_book and not rest:
    return ("book", found_book)
  match = re.fullmatch(rf"(?:chapter\s+)?(\d{{1,3}}):(\d{{1,3}})(?:{DASHES}(\d{{1,3}}|end))?", rest, re.IGNORECASE)
  if match and book:
    end = None if (match.group(3) or "").lower() == "end" else int(match.group(3) or match.group(2))
    return ("verses", book, int(match.group(1)), int(match.group(2)), end)
  match = re.fullmatch(r"(?:chapter|ch\.?|psalm)\s*(\d{1,3})|(\d{1,3})", rest, re.IGNORECASE)
  if match and (found_book or rest.lower().startswith(("chapter", "ch", "psalm"))) and book:
    return ("chapter", book, int(match.group(1) or match.group(2)))
  match = re.fullmatch(rf"(?:verses?|vv?\.?)\s*(\d{{1,3}})(?:{DASHES}(\d{{1,3}}|end))?", rest, re.IGNORECASE)
  if match and book and chapter:
    end = None if (match.group(2) or "").lower() == "end" else int(match.group(2) or match.group(1))
    return ("verses", book, chapter, int(match.group(1)), end)
  return None


def split_commentary(document: Document, book_lookup: dict, passage: str = ""):
  """(entries [(book, chapter, verse, end_verse, text, html)], introductions [(book, chapter, text, html)],
  Split)."""
  split = Split(warnings=list(document.warnings))
  entries, introductions = [], []
  book = chapter = None
  target = None  # ("intro", book, chapter) or ("note", book, chapter, verse, end)
  current: list = []
  found_passages = 0

  def close():
    nonlocal current
    if target and current:
      piece = piece_of(current, document.footnotes)
      if piece:
        if target[0] == "note":
          entries.append((target[1], target[2], target[3], target[4], piece.text, piece.html))
        else:
          introductions.append((target[1], target[2], piece.text, piece.html))
    current = []

  leading: list = []
  for block in top_blocks(document.html):
    level = heading_level(block)
    named = parse_passage_heading(heading_text(block), book_lookup, book, chapter) if level else None
    if not named:
      (current if target else leading).append(block)
      continue
    found_passages += 1
    close()
    if named[0] == "book":
      book, chapter = named[1], None
      target = ("intro", book, 0)
    elif named[0] == "chapter":
      book, chapter = named[1], named[2]
      target = ("intro", book, chapter)
    else:
      book, chapter = named[1], named[2]
      target = ("note", book, chapter, named[3], named[4])
  close()
  if not found_passages:
    named = parse_passage_heading(passage, book_lookup, None, None) if passage.strip() else None
    if not named or named[0] != "verses":
      split.problems.append(
        'No headings naming a passage were found. Mark each note with a heading such as "John 3:16" or '
        '"Verses 16-18" (under a heading "John 3"), or type the passage the whole document is about, such as John 3:16-21.'
      )
      return [], [], split
    piece = piece_of(leading, document.footnotes)
    if piece:
      entries.append((named[1], named[2], named[3], named[4], piece.text, piece.html))
  elif leading and any(block.get_text(strip=True) for block in leading):
    split.warnings.append("The text before the first heading naming a passage was left out.")
  # The same verse twice: the notes are joined.
  joined: dict = {}
  for entry in entries:
    key = entry[:3]
    if key in joined:
      old = joined[key]
      joined[key] = (*old[:4], old[4] + "\n\n" + entry[4], old[5] + entry[5])
      split.warnings.append(f"Two notes start at the same verse ({entry[1]}:{entry[2]}); they were joined.")
    else:
      joined[key] = entry
  intros: dict = {}
  for introduction in introductions:
    key = introduction[:2]
    intros[key] = (*key, (intros[key][2] + "\n\n" if key in intros else "") + introduction[2], (intros[key][3] if key in intros else "") + introduction[3])
  if not joined:
    split.problems.append("No notes were found under the passage headings.")
  return list(joined.values()), list(intros.values()), split


# --- song words ----------------------------------------------------------------------------------------


def whole_document(document: Document) -> Piece | None:
  return piece_of(top_blocks(document.html), document.footnotes)

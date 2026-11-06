"""Find scripture references in text, such as "Joh 3:22", "1 Kings 4:32" or "Psa 23:1-3".

The commentaries write books two ways: short codes (Psa, Kg1, Co1, Jo1, Joh) in Matthew Henry,
Adam Clarke, Jamieson-Fausset-Brown and Keil and Delitzsch, and full names (Psalm, 1 Kings) in John
Gill and John Calvin. A book is written as in the list or in capitals. Only a book, a chapter and a verse count (Book 3:16, optionally a range
Book 3:16-18 inside the chapter); lists that leave the book out ("Joh 3:16, 17") and chapter-only
references are not linked. A reference to a verse that does not exist is left alone.
"""

import re
import time

from search import connect

# Each book's names, without the number of a numbered book (that is added below).
BOOK_NAMES = {
  1: ["Genesis", "Gen"],
  2: ["Exodus", "Exod", "Exo", "Ex"],
  3: ["Leviticus", "Lev"],
  4: ["Numbers", "Num"],
  5: ["Deuteronomy", "Deut", "Deu"],
  6: ["Joshua", "Josh", "Jos"],
  7: ["Judges", "Judg", "Jdg"],
  8: ["Ruth", "Rut"],
  15: ["Ezra", "Ezr"],
  16: ["Nehemiah", "Neh"],
  17: ["Esther", "Esth", "Est"],
  18: ["Job"],
  19: ["Psalms", "Psalm", "Psa", "Ps"],
  20: ["Proverbs", "Prov", "Pro"],
  21: ["Ecclesiastes", "Eccles", "Eccl", "Ecc"],
  22: ["Song of Solomon", "Song of Songs", "Canticles", "Song", "Sol", "Cant"],
  23: ["Isaiah", "Isa"],
  24: ["Jeremiah", "Jer"],
  25: ["Lamentations", "Lam"],
  26: ["Ezekiel", "Ezek", "Eze"],
  27: ["Daniel", "Dan"],
  28: ["Hosea", "Hos"],
  29: ["Joel", "Joe"],
  30: ["Amos", "Amo"],
  31: ["Obadiah", "Obad", "Oba"],
  32: ["Jonah", "Jon"],
  33: ["Micah", "Mic"],
  34: ["Nahum", "Nah"],
  35: ["Habakkuk", "Hab"],
  36: ["Zephaniah", "Zeph", "Zep"],
  37: ["Haggai", "Hag"],
  38: ["Zechariah", "Zech", "Zec", "Zac"],
  39: ["Malachi", "Mal"],
  40: ["Matthew", "Matt", "Mat"],
  41: ["Mark", "Mrk", "Mar"],
  42: ["Luke", "Luk"],
  43: ["John", "Jhn", "Joh"],
  44: ["Acts", "Act"],
  45: ["Romans", "Rom"],
  48: ["Galatians", "Gal"],
  49: ["Ephesians", "Eph"],
  50: ["Philippians", "Phil", "Php", "Phi"],
  51: ["Colossians", "Col"],
  56: ["Titus", "Tit"],
  57: ["Philemon", "Phlm", "Phm", "Plm"],
  58: ["Hebrews", "Heb"],
  59: ["James", "Jas", "Jam"],
  65: ["Jude", "Jud", "Jde"],
  66: ["Revelation", "Revelations", "Rev"],
}

# Numbered books: (book number, the number, names after the number, the short code as a CCEL-style
# word with the number last, such as Kg1).
NUMBERED_BOOKS = [
  (9, 1, ["Samuel", "Sam", "Sa"], "Sa1"), (10, 2, ["Samuel", "Sam", "Sa"], "Sa2"),
  (11, 1, ["Kings", "Kgs", "Ki"], "Kg1"), (12, 2, ["Kings", "Kgs", "Ki"], "Kg2"),
  (13, 1, ["Chronicles", "Chron", "Chr", "Ch"], "Ch1"), (14, 2, ["Chronicles", "Chron", "Chr", "Ch"], "Ch2"),
  (46, 1, ["Corinthians", "Cor", "Co"], "Co1"), (47, 2, ["Corinthians", "Cor", "Co"], "Co2"),
  (52, 1, ["Thessalonians", "Thess", "Thes", "Th"], "Th1"), (53, 2, ["Thessalonians", "Thess", "Thes", "Th"], "Th2"),
  (54, 1, ["Timothy", "Tim", "Ti"], "Ti1"), (55, 2, ["Timothy", "Tim", "Ti"], "Ti2"),
  (60, 1, ["Peter", "Pet", "Pe"], "Pe1"), (61, 2, ["Peter", "Pet", "Pe"], "Pe2"),
  (62, 1, ["John", "Jn", "Jo"], "Jo1"), (63, 2, ["John", "Jn", "Jo"], "Jo2"), (64, 3, ["John", "Jn", "Jo"], "Jo3"),
]
ROMAN = {1: "I", 2: "II", 3: "III"}


def normalize(name):
  """The key a written name is looked up by: lower case, without full stops, and without spaces except
  the one after a Roman numeral ("I Sa" is 1 Samuel, but "Isa" is Isaiah)."""
  key = re.sub(r"\s+", " ", name.replace(".", "")).strip().lower()
  roman_numbered = re.match(r"^(i{1,3}) \S", key)
  return key if roman_numbered else key.replace(" ", "")


def build_names():
  """Every way of writing a book, as written -> book number."""
  names = {}
  for book, spellings in BOOK_NAMES.items():
    for spelling in spellings:
      names[spelling] = book
  for book, number, spellings, code in NUMBERED_BOOKS:
    names[code] = book
    for spelling in spellings:
      for prefix in (str(number), ROMAN[number]):
        names[f"{prefix} {spelling}"] = book
        names[f"{prefix}{spelling}"] = book
  return names


NAMES = build_names()
def build_book_by_normalized_name():
  # A plain name wins a clash with a numbered book written without a space ("ISa" would be 1 Samuel,
  # but "Isa" is Isaiah), so register the plain names first.
  book_by_name = {}
  for name, book in sorted(NAMES.items(), key=lambda item: item[1] in {number for number, *_ in NUMBERED_BOOKS}):
    book_by_name.setdefault(normalize(name), book)
  return book_by_name


BOOK_BY_NORMALIZED_NAME = build_book_by_normalized_name()


def build_pattern():
  # Longest names first, so "1 Kings" is not read as "Kings", and "Psalms" not as "Ps".
  alternatives = []
  for name in sorted(NAMES, key=len, reverse=True):
    # Allow a space (or none) after the number of a numbered book, and a full stop after the name.
    alternatives.append(re.escape(name).replace("\\ ", r"\s?"))
  # Matched in any case; find_references then keeps a name written as in NAMES or in capitals (Daily
  # Light writes "PHI. 3:13" and "DEUT. 31:8"), so a lower-case "job 3:4" is not taken for a reference.
  return re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(alternatives) + r")\.?\s+(\d{1,3})\s?:\s?(\d{1,3})"
    r"(?:\s?[-–]\s?(\d{1,3})(?!\s?:))?(?![\d])",
    re.IGNORECASE,
  )


PATTERN = build_pattern()

LIMITS_LIFETIME_SECONDS = 3600
_limits = {"loaded_at": 0.0, "value": {}}


def verse_limits():
  """The last verse of each chapter, {(book, chapter): last verse}, from the Bible with the most verses.

  Kept for an hour. It decides which references name a verse that exists.
  """
  if time.monotonic() - _limits["loaded_at"] > LIMITS_LIFETIME_SECONDS or not _limits["value"]:
    with connect() as connection:
      rows = connection.execute(
        "SELECT book_number, chapter, MAX(verse) FROM verses WHERE translation_id = ("
        "SELECT translation_id FROM verses GROUP BY translation_id ORDER BY COUNT(*) DESC LIMIT 1"
        ") GROUP BY book_number, chapter"
      ).fetchall()
    _limits["value"] = {(book, chapter): last for book, chapter, last in rows}
    _limits["loaded_at"] = time.monotonic()
  return _limits["value"]


def find_references(text, limits=None):
  """The references in a text as [start, end, "book:chapter:verse"], for those naming a real verse.

  start and end are character positions in text. The code is the first verse of a range.
  """
  if limits is None:
    limits = verse_limits()
  references = []
  for match in PATTERN.finditer(text):
    name = match[1]
    if name not in NAMES and not name.isupper():
      continue
    book = BOOK_BY_NORMALIZED_NAME.get(normalize(name))
    chapter, verse = int(match[2]), int(match[3])
    if book is None or verse < 1 or verse > limits.get((book, chapter), 0):
      continue
    references.append([match.start(), match.end(), f"{book}:{chapter}:{verse}"])
  return references

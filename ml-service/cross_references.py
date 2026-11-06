"""Reading and loading the OpenBible.info cross-reference file.

The file is tab separated: "From Verse", "To Verse" (one verse, or a range such as
Prov.8.22-Prov.8.30) and "Votes". Verses are written like Gen.1.1. The first line is a header.
Data: OpenBible.info, CC BY 4.0, based mainly on the Treasury of Scripture Knowledge.
"""

import re
from dataclasses import dataclass

from search import connect

# How OpenBible.info abbreviates each book, and our book number for it.
BOOK_NUMBERS = {
  "Gen": 1, "Exod": 2, "Lev": 3, "Num": 4, "Deut": 5, "Josh": 6, "Judg": 7, "Ruth": 8,
  "1Sam": 9, "2Sam": 10, "1Kgs": 11, "2Kgs": 12, "1Chr": 13, "2Chr": 14, "Ezra": 15, "Neh": 16,
  "Esth": 17, "Job": 18, "Ps": 19, "Prov": 20, "Eccl": 21, "Song": 22, "Isa": 23, "Jer": 24,
  "Lam": 25, "Ezek": 26, "Dan": 27, "Hos": 28, "Joel": 29, "Amos": 30, "Obad": 31, "Jonah": 32,
  "Mic": 33, "Nah": 34, "Hab": 35, "Zeph": 36, "Hag": 37, "Zech": 38, "Mal": 39, "Matt": 40,
  "Mark": 41, "Luke": 42, "John": 43, "Acts": 44, "Rom": 45, "1Cor": 46, "2Cor": 47, "Gal": 48,
  "Eph": 49, "Phil": 50, "Col": 51, "1Thess": 52, "2Thess": 53, "1Tim": 54, "2Tim": 55,
  "Titus": 56, "Phlm": 57, "Heb": 58, "Jas": 59, "1Pet": 60, "2Pet": 61, "1John": 62,
  "2John": 63, "3John": 64, "Jude": 65, "Rev": 66,
}

VERSE = r"(?P<{p}book>[1-3]?[A-Za-z]+)\.(?P<{p}chapter>\d+)\.(?P<{p}verse>\d+)"
LINE_PATTERN = re.compile(
  "^" + VERSE.format(p="from_") + r"\t" + VERSE.format(p="to_")
  + r"(?:-" + VERSE.format(p="end_") + r")?\t(?P<votes>-?\d+)$"
)


class CrossReferenceProblem(ValueError):
  """A line of the file cannot be understood. The message says which line."""


@dataclass(frozen=True)
class CrossReference:
  from_verse: tuple  # (book number, chapter, verse)
  to_verse: tuple
  to_end_verse: tuple | None  # the last verse of a range, or None for a single verse
  votes: int


def book_number(abbreviation, line_number):
  number = BOOK_NUMBERS.get(abbreviation)
  if number is None:
    raise CrossReferenceProblem(f"Line {line_number}: I do not know the book '{abbreviation}'.")
  return number


def parse_line(line, line_number):
  match = LINE_PATTERN.match(line.rstrip("\r\n"))
  if match is None:
    raise CrossReferenceProblem(f"Line {line_number}: this is not a cross reference: {line[:80]!r}")

  def verse(prefix):
    book = match[f"{prefix}book"]
    if book is None:
      return None
    return (book_number(book, line_number), int(match[f"{prefix}chapter"]), int(match[f"{prefix}verse"]))

  return CrossReference(verse("from_"), verse("to_"), verse("end_"), int(match["votes"]))


def read_file(path, minimum_votes=1):
  """Read the file. Returns the references with at least minimum_votes, and how many were skipped.

  Rows with zero or negative votes are skipped: people voted that the connection is weak or wrong.
  """
  references = []
  skipped = 0
  seen = set()
  with open(path, encoding="utf-8-sig") as cross_reference_file:
    next(cross_reference_file, None)  # the header line
    for line_number, line in enumerate(cross_reference_file, start=2):
      if not line.strip():
        continue
      reference = parse_line(line, line_number)
      if reference.votes < minimum_votes:
        skipped += 1
        continue
      key = (reference.from_verse, reference.to_verse)
      if key in seen:
        raise CrossReferenceProblem(f"Line {line_number}: this pair of verses appears more than once.")
      seen.add(key)
      references.append(reference)
  return references, skipped


def replace_all(references):
  """Replace every cross reference in the database with these, in one transaction."""
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute("TRUNCATE cross_references")
      with cursor.copy(
        "COPY cross_references (from_book, from_chapter, from_verse, to_book, to_chapter, to_verse,"
        " to_end_book, to_end_chapter, to_end_verse, votes) FROM STDIN"
      ) as copy:
        for reference in references:
          end = reference.to_end_verse or (None, None, None)
          copy.write_row((*reference.from_verse, *reference.to_verse, *end, reference.votes))
      cursor.execute("SELECT COUNT(*) FROM cross_references")
      return cursor.fetchone()[0]

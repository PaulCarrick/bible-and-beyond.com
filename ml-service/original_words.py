"""Hebrew and Greek words of each verse, and the lexicon that explains them ("Original Words").

Data: STEPBible.org, based on work at Tyndale House Cambridge, licensed CC BY 4.0
(https://github.com/STEPBible/STEPBible-Data). We load it into our own database and do not hand
out the files themselves. The files are:

- TAHOT (Hebrew Old Testament) and TAGNT (Greek New Testament): one row per word.
- TBESH (Hebrew) and TBESG (Greek): the lexicon, one row per Strong's number.

Verses are numbered like the KJV (TAHOT gives that numbering first, with the Hebrew numbering in
brackets). Only the Greek words found in the modern critical text (NA27/28) are loaded, so verses
that only the older Textus Receptus has (such as John 7:53 to 8:11) have no Greek words.
"""

import html
import re
from dataclasses import dataclass, replace

from search import connect, parse_strong_query

# How STEPBible abbreviates each book, and our book number for it.
BOOK_NUMBERS = {
  "Gen": 1, "Exo": 2, "Lev": 3, "Num": 4, "Deu": 5, "Jos": 6, "Jdg": 7, "Rut": 8,
  "1Sa": 9, "2Sa": 10, "1Ki": 11, "2Ki": 12, "1Ch": 13, "2Ch": 14, "Ezr": 15, "Neh": 16,
  "Est": 17, "Job": 18, "Psa": 19, "Pro": 20, "Ecc": 21, "Sng": 22, "Isa": 23, "Jer": 24,
  "Lam": 25, "Ezk": 26, "Dan": 27, "Hos": 28, "Jol": 29, "Amo": 30, "Oba": 31, "Jon": 32,
  "Mic": 33, "Nam": 34, "Hab": 35, "Zep": 36, "Hag": 37, "Zec": 38, "Mal": 39, "Mat": 40,
  "Mrk": 41, "Luk": 42, "Jhn": 43, "Act": 44, "Rom": 45, "1Co": 46, "2Co": 47, "Gal": 48,
  "Eph": 49, "Php": 50, "Col": 51, "1Th": 52, "2Th": 53, "1Ti": 54, "2Ti": 55, "Tit": 56,
  "Phm": 57, "Heb": 58, "Jas": 59, "1Pe": 60, "2Pe": 61, "1Jn": 62, "2Jn": 63, "3Jn": 64,
  "Jud": 65, "Rev": 66,
}

# "Gen.1.1#01=L" or "Mal.4.6(3.24)#15=L" (the bracket holds the Hebrew numbering).
WORD_REFERENCE = re.compile(
  r"^(?P<book>[1-3]?[A-Za-z]{2,3})\.(?P<chapter>\d+)\.(?P<verse>\d+)(?:\([^)]*\))?#(?P<position>\d+)=(?P<kind>\S+)$"
)
STRONG_CODE = re.compile(r"[GH]\d{4}[A-Za-z]?")
BRACED_STRONG_CODE = re.compile(r"\{([GH]\d{4}[A-Za-z]?)")
GREEK_STRONG_CODE = re.compile(r"([GH]\d{4}[A-Za-z]?)=")


class OriginalWordsProblem(ValueError):
  """A line of a file cannot be understood. The message says which line."""


@dataclass(frozen=True)
class OriginalWord:
  verse: tuple  # (book number, chapter, verse)
  position: int
  original: str
  transliteration: str
  english: str
  strong_code: str | None
  grammar: str


@dataclass(frozen=True)
class LexiconEntry:
  strong_code: str
  language: str
  original: str
  transliteration: str
  morphology: str
  gloss: str
  definition: str


# The files keep the punctuation of the printed text with the words. Greek: commas, full stops, the
# Greek question mark and raised dot, paragraph marks and editors' brackets. Hebrew: the verse
# end, paseq, and the maqaf (hyphen) that joins a word to the next. The apostrophe of an elided
# Greek word (ἀλλ᾽) and the "/" between Hebrew prefixes are part of the word and stay.
GREEK_PUNCTUATION = ",.\u00b7;\u037e\u0387\u00b6[]\u00ac"
HEBREW_MARKS = "\u05c3\u05c0\u05c6"  # verse end, paseq, nun hafukha
MAQAF = "\u05be"


def clean_original(text, is_greek):
  """The word without the punctuation that came with it in the file."""
  if is_greek:
    cleaned = text.translate({ord(character): None for character in GREEK_PUNCTUATION})
  else:
    # "X\׃\ \פ": the word, then the verse end and a paragraph letter, each joined with a backslash.
    cleaned = re.split(r"\\[" + HEBREW_MARKS + " ]", text)[0]
    # A backslash before a maqaf joins two words into one (Kedor-laomer); keep the maqaf only.
    cleaned = cleaned.replace("\\" + MAQAF, MAQAF).replace("\\", "")
    cleaned = cleaned.translate({ord(character): None for character in HEBREW_MARKS}).strip(MAQAF)
  return cleaned.strip() or text.strip()


def clean_transliteration(text):
  """The sound of the word without the hyphen that marks a Hebrew maqaf."""
  return text.strip().rstrip("-").strip() or text.strip()


def read_reference(text, line_number):
  """Return ((book, chapter, verse), position, kind) for a word row, or None for any other line."""
  match = WORD_REFERENCE.match(text)
  if match is None:
    return None
  book = BOOK_NUMBERS.get(match["book"])
  if book is None:
    raise OriginalWordsProblem(f"Line {line_number}: I do not know the book '{match['book']}'.")
  return (book, int(match["chapter"]), int(match["verse"])), int(match["position"]), match["kind"]


def parse_hebrew_line(line, line_number):
  """One TAHOT row, or None when the line is not a word of the Leningrad text."""
  columns = line.rstrip("\r\n").split("\t")
  reference = read_reference(columns[0], line_number)
  if reference is None or not reference[2].startswith("L") or len(columns) < 6:
    return None
  verse, position, _kind = reference
  # The main word of a joined form such as "H9003/{H7225G}" is the one in braces.
  braced = BRACED_STRONG_CODE.search(columns[4])
  anywhere = STRONG_CODE.search(columns[4])
  strong_code = braced[1] if braced else (anywhere[0] if anywhere else None)
  return OriginalWord(
    verse, position, clean_original(columns[1], False), clean_transliteration(columns[2]),
    columns[3], strong_code, columns[5],
  )


def parse_greek_line(line, line_number):
  """One TAGNT row, or None when the line is not a word of the modern critical text (NA27/28)."""
  columns = line.rstrip("\r\n").split("\t")
  reference = read_reference(columns[0], line_number)
  if reference is None or reference[2][0] not in "Nn" or len(columns) < 5:
    return None
  verse, position, _kind = reference
  greek, _separator, bracketed = columns[1].rpartition(" (")
  if not greek:
    greek, bracketed = columns[1], ""
  codes = GREEK_STRONG_CODE.findall(columns[3])
  return OriginalWord(
    verse, position, clean_original(greek, True), clean_transliteration(bracketed.rstrip(")")),
    columns[2],
    codes[-1] if codes else None,
    columns[3].partition("=")[2] if "=" in columns[3] else "",
  )


def read_words(paths):
  """Read the TAHOT and TAGNT files. Returns the words in file order."""
  words = []
  for path in paths:
    with open(path, encoding="utf-8-sig") as word_file:
      is_greek = "TAGNT" in word_file.readline()
      word_file.seek(0)
      parse = parse_greek_line if is_greek else parse_hebrew_line
      for line_number, line in enumerate(word_file, start=1):
        word = parse(line, line_number)
        if word is not None:
          words.append(word)
  return words


def clean_definition(text):
  """Turn the lexicon's small HTML into plain text with line breaks."""
  text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
  text = re.sub(r"<[^>]+>", "", text)
  text = html.unescape(text)
  lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
  # The lexicon indents sub-senses with underscores ("__1. Of human affection"); show that as space.
  lines = [re.sub(r"^_+", lambda match: "\u00a0\u00a0" * len(match[0]), line) for line in lines]
  return "\n".join(line for line in lines if line.strip("\u00a0"))


def read_lexicon(paths):
  """Read the TBESH and TBESG files. Returns one entry per Strong's number (the first one wins)."""
  entries = {}
  for path in paths:
    with open(path, encoding="utf-8-sig") as lexicon_file:
      for line in lexicon_file:
        columns = line.rstrip("\r\n").split("\t")
        if len(columns) < 8 or not re.match(r"^[GH]\d{4}", columns[0]):
          continue
        code = columns[1].split()[0] if columns[1].strip() else columns[0]
        if code in entries:
          continue
        entries[code] = LexiconEntry(
          code, "greek" if code.startswith("G") else "hebrew", columns[3], columns[4],
          columns[5], columns[6], clean_definition(columns[7]),
        )
  return entries


def resolve_strong_code(strong_code, entries):
  """The lexicon number that explains a word's number.

  A few word tags carry a sense letter the lexicon does not list (H0430J "gods", G2453 "Jew"
  where the lexicon has G2453G). Those fall back to the "G" entry of the same number, or else the
  first entry with that number. A number with no entry at all is kept as it is.
  """
  if strong_code is None or strong_code in entries:
    return strong_code
  number = strong_code[:5]
  if number + "G" in entries:
    return number + "G"
  same_number = sorted(code for code in entries if code.startswith(number))
  return same_number[0] if same_number else strong_code


def link_words_to_lexicon(words, entries):
  """The same words, with each Strong's number replaced by the lexicon number that explains it."""
  return [replace(word, strong_code=resolve_strong_code(word.strong_code, entries)) for word in words]


def replace_all(words, entries):
  """Replace every word and lexicon entry in the database, in one transaction."""
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute("TRUNCATE original_words RESTART IDENTITY")
      cursor.execute("TRUNCATE lexicon_entries")
      with cursor.copy(
        "COPY lexicon_entries (strong_code, language, original, transliteration, morphology,"
        " gloss, definition) FROM STDIN"
      ) as copy:
        for entry in entries.values():
          copy.write_row((
            entry.strong_code, entry.language, entry.original, entry.transliteration,
            entry.morphology, entry.gloss, entry.definition,
          ))
      with cursor.copy(
        "COPY original_words (book_number, chapter, verse, position, original, transliteration,"
        " english, strong_code, grammar) FROM STDIN"
      ) as copy:
        for word in words:
          copy.write_row((
            *word.verse, word.position, word.original, word.transliteration, word.english,
            word.strong_code, word.grammar,
          ))
      cursor.execute("SELECT COUNT(*) FROM original_words")
      word_count = cursor.fetchone()[0]
      cursor.execute("SELECT COUNT(*) FROM lexicon_entries")
      return word_count, cursor.fetchone()[0]


def get_original_words(book_number, chapter, verse):
  """The Hebrew or Greek words of a verse, each with its lexicon gloss. None if there are none."""
  with connect() as connection:
    book = connection.execute("SELECT name FROM books WHERE number = %s", (book_number,)).fetchone()
    rows = connection.execute(
      """
      SELECT w.position, w.original, w.transliteration, w.english, w.strong_code, w.grammar,
             l.gloss
      FROM original_words w
      LEFT JOIN lexicon_entries l ON l.strong_code = w.strong_code
      WHERE w.book_number = %s AND w.chapter = %s AND w.verse = %s
      ORDER BY w.position, w.id
      """,
      (book_number, chapter, verse),
    ).fetchall()
  if book is None or not rows:
    return None
  return {
    "book_number": book_number,
    "book_name": book[0],
    "chapter": chapter,
    "verse": verse,
    "language": "hebrew" if book_number <= 39 else "greek",
    "words": [
      {
        "original": original, "transliteration": transliteration, "english": english,
        "strong_code": strong_code, "grammar": grammar, "gloss": gloss,
      }
      for _position, original, transliteration, english, strong_code, grammar, gloss in rows
    ],
  }


def get_lexicon_entry(translation_code, strong_code, limit):
  """A lexicon entry with how often the word is used and the first verses that use it.

  A number with a sense letter (H7225G) is that sense only. A number without one (H7225, as in a
  Strong's concordance or a click on an English word) gives the main entry and counts the verses
  of every sense. The verses are listed in Bible order with their text in the Bible searched.
  Returns None when the number is not in the lexicon or the translation is unknown or hidden.
  """
  strong = parse_strong_query(strong_code)
  if strong is None:
    return None
  codes = strong["codes"]
  with connect() as connection:
    entry = connection.execute(
      "SELECT strong_code, language, original, transliteration, morphology, gloss, definition"
      " FROM lexicon_entries WHERE strong_code = ANY(%s)"
      " ORDER BY (strong_code = %s) DESC, (strong_code = %s) DESC, strong_code LIMIT 1",
      (codes, codes[0], codes[0] + "G"),
    ).fetchone()
    translation = connection.execute(
      "SELECT id FROM translations WHERE code = %s AND is_published", (translation_code,)
    ).fetchone()
    if entry is None or translation is None:
      return None
    total = connection.execute(
      "SELECT COUNT(DISTINCT (book_number, chapter, verse)) FROM original_words WHERE strong_code = ANY(%s)",
      (codes,),
    ).fetchone()[0]
    rows = connection.execute(
      """
      SELECT u.book_number, b.name, u.chapter, u.verse, v.text
      FROM (
        SELECT DISTINCT book_number, chapter, verse FROM original_words WHERE strong_code = ANY(%s)
        ORDER BY book_number, chapter, verse LIMIT %s
      ) u
      JOIN books b ON b.number = u.book_number
      LEFT JOIN verses v ON v.translation_id = %s AND v.book_number = u.book_number
        AND v.chapter = u.chapter AND v.verse = u.verse
      ORDER BY u.book_number, u.chapter, u.verse
      """,
      (codes, limit, translation[0]),
    ).fetchall()
  code, language, original, transliteration, morphology, gloss, definition = entry
  return {
    "strong_code": code,
    "language": language,
    "original": original,
    "transliteration": transliteration,
    "morphology": morphology,
    "gloss": gloss,
    "definition": definition,
    "verse_total": total,
    "shown": len(rows),
    "verses": [
      {
        "book_number": book_number, "reference": f"{book_name} {chapter}:{verse}",
        "chapter": chapter, "verse": verse, "text": text,
      }
      for book_number, book_name, chapter, verse, text in rows
    ],
  }

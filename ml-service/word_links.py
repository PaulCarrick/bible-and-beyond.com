"""Link the English words of a verse to the Hebrew or Greek word behind them ("click a word").

Data: the Berean Bible's translation tables (https://bereanbible.com/bsb_tables.tsv), which list
every original word with its Strong's number and the English the Berean Standard Bible uses for
it, in the order of the English text. The Berean texts are in the public domain (since 2023-04-30).

We do not rebuild the verse from the table (its spacing and punctuation differ from our text).
Instead its English words are walked in order and matched to the words of our stored verse text.
A verse is linked only when every English word in the table is found in order in our text, so a
link is never put on the wrong word; a verse that does not line up has no links.
"""

import hashlib
import json
import re

from search import connect

WORD = re.compile(r"[A-Za-z0-9À-ɏ]+(?:['’\-][A-Za-z0-9À-ɏ]+)*")
# The table writes "vvv" where an original word has no English of its own.
PLACEHOLDERS = {"vvv"}
# How far ahead in the verse text a table word may be found. Words the table leaves out (such as
# "the" for an article) make small gaps.
LOOK_AHEAD = 8
VERSE_ID = re.compile(r"^(.+) (\d+):(\d+)$")
BOOK_COUNT = 66


class WordLinksProblem(ValueError):
  """The table cannot be understood."""


def normalize(word):
  return word.lower().replace("’", "'")


def strong_code(language, hebrew_number, greek_number):
  """The Strong's number of a table row as "H7225" or "G1063", or None when it has none."""
  number = greek_number if language == "Greek" else hebrew_number
  if not number.strip().isdigit() or int(number) == 0:
    return None
  return f"{'G' if language == 'Greek' else 'H'}{int(number):04d}"


def read_table(path, expected_books=BOOK_COUNT):
  """Read the table. Returns {(book, chapter, verse): [(english word, Strong's number or None)]},
  with the words in the order of the English text. Books are numbered in the order they appear."""
  verses = {}
  book_numbers = {}
  current = None
  rows = []
  with open(path, encoding="utf-8-sig", newline="") as table_file:
    table_file.readline()  # the header
    for line_number, line in enumerate(table_file, start=2):
      columns = line.rstrip("\r\n").split("\t")
      columns += [""] * (23 - len(columns))
      if columns[12]:
        match = VERSE_ID.match(columns[12])
        if match is None:
          raise WordLinksProblem(f"Line {line_number}: this is not a verse: {columns[12]!r}")
        book = book_numbers.setdefault(match[1], len(book_numbers) + 1)
        current = (book, int(match[2]), int(match[3]))
        rows.append((current, []))
      if current is None:
        raise WordLinksProblem(f"Line {line_number}: a word comes before the first verse.")
      rows[-1][1].append(columns)
  if len(book_numbers) != expected_books:
    raise WordLinksProblem(f"Expected {expected_books} books in the table; found {len(book_numbers)}.")

  for key, columns_list in rows:
    ordered = sorted(columns_list, key=lambda columns: int(columns[2]) if columns[2].isdigit() else 0)
    words = []
    for columns in ordered:
      code = strong_code(columns[4], columns[10], columns[11])
      for match in WORD.finditer(columns[18]):
        if normalize(match[0]) not in PLACEHOLDERS:
          words.append((normalize(match[0]), code))
    verses[key] = words
  return verses


def align_verse(text, words):
  """Match the table's English words to the words of the verse text, in order.

  Returns the links as [start, end, "H7225"] for the words that have a Strong's number, or None
  when any table word cannot be found, or the text has characters a browser counts differently.
  """
  if any(ord(character) > 0xFFFF for character in text):
    return None
  text_words = [(normalize(match[0]), match.start(), match.end()) for match in WORD.finditer(text)]
  links = []
  position = 0
  for word, code in words:
    for index in range(position, min(len(text_words), position + LOOK_AHEAD)):
      if text_words[index][0] == word:
        if code:
          links.append([text_words[index][1], text_words[index][2], code])
        position = index + 1
        break
    else:
      return None
  return links


def hash_text(text):
  return hashlib.md5(text.encode("utf-8")).hexdigest()


def build_links(table, verse_rows):
  """The rows to store: (verse id, text hash, links as JSON) for every verse that lines up.

  verse_rows are (id, book, chapter, verse, text). Returns the rows and a summary.
  """
  rows = []
  summary = {"verses": 0, "linked": 0, "not_in_table": 0, "did_not_line_up": 0, "words": 0}
  for verse_id, book, chapter, verse, text in verse_rows:
    summary["verses"] += 1
    words = table.get((book, chapter, verse))
    if words is None:
      summary["not_in_table"] += 1
      continue
    links = align_verse(text, words)
    if links is None:
      summary["did_not_line_up"] += 1
      continue
    summary["linked"] += 1
    summary["words"] += len(links)
    rows.append((verse_id, hash_text(text), json.dumps(links, separators=(",", ":"))))
  return rows, summary


def load_verse_rows(translation_code):
  with connect() as connection:
    return connection.execute(
      "SELECT v.id, v.book_number, v.chapter, v.verse, v.text FROM verses v "
      "JOIN translations t ON t.id = v.translation_id WHERE t.code = %s ORDER BY v.id",
      (translation_code,),
    ).fetchall()


def replace_links(translation_code, rows):
  """Replace the links of one translation with these rows, in one transaction."""
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute(
        "DELETE FROM verse_word_links WHERE verse_id IN ("
        "SELECT v.id FROM verses v JOIN translations t ON t.id = v.translation_id WHERE t.code = %s)",
        (translation_code,),
      )
      with cursor.copy("COPY verse_word_links (verse_id, text_hash, links) FROM STDIN") as copy:
        for row in rows:
          copy.write_row(row)
      cursor.execute(
        "SELECT COUNT(*) FROM verse_word_links l JOIN verses v ON v.id = l.verse_id "
        "JOIN translations t ON t.id = v.translation_id WHERE t.code = %s",
        (translation_code,),
      )
      return cursor.fetchone()[0]


def attach_links(connection, translation_id, book_number, verses):
  """Add "links" to each verse (a dict with "chapter", "verse" and "text") that has them.

  A verse whose text has changed since the links were made gets none.
  """
  chapters = sorted({verse["chapter"] for verse in verses})
  rows = connection.execute(
    "SELECT v.chapter, v.verse, l.links FROM verse_word_links l JOIN verses v ON v.id = l.verse_id "
    "WHERE v.translation_id = %s AND v.book_number = %s AND v.chapter = ANY(%s) "
    "AND md5(v.text) = l.text_hash",
    (translation_id, book_number, chapters),
  ).fetchall()
  by_verse = {(chapter, verse): links for chapter, verse, links in rows}
  for verse in verses:
    links = by_verse.get((verse["chapter"], verse["verse"]))
    if links:
      verse["links"] = links
  return verses

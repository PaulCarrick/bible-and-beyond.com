"""Notes that a logged-in visitor writes about a Bible verse, a commentary note or a devotional reading.

A user has many notes. Each is about one item (item_type and where it is), has the time it was written
and a body: a little HTML from the editor (Quill), cleaned before it is kept, so it is safe to show.
"""

import re

from commentaries import label_range
from contact import ContactProblem, check_rich_text
from search import connect

ITEM_TYPES = ("bible_verse", "commentary", "devotional")
SCRIPTURE_TYPES = ("bible_verse", "commentary")
NOTE_TEXT_LIMIT = 10000
NOTE_HTML_LIMIT = 60000
SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
LIST_LIMIT = 200
# Enough for any reader; it stops one account from filling the database.
MAX_NOTES_PER_USER = 5000

COLUMNS = "id, item_type, source_code, book_number, chapter, verse, section, unit, body, created_at, updated_at"


class NoteProblem(Exception):
  """The request cannot be done; the text says why and is fit to show the visitor."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


def _row_to_note(row) -> dict:
  return {
    "id": row[0],
    "item_type": row[1],
    "source_code": row[2],
    "book_number": row[3],
    "chapter": row[4],
    "verse": row[5],
    "section": row[6],
    "unit": row[7],
    "body": row[8],
    "created_at": row[9].isoformat(),
    "updated_at": row[10].isoformat(),
  }


def _describe(connection, notes: list[dict]) -> list[dict]:
  """Adds a title to each note that says what it is about, such as "John 3:16" or "Matthew Henry on John 3:16"."""
  books = dict(connection.execute("SELECT number, name FROM books").fetchall())
  commentary_names = dict(connection.execute("SELECT id, short_name FROM commentaries").fetchall())
  devotional_names = dict(connection.execute("SELECT id, name FROM devotionals").fetchall())
  for note in notes:
    if note["item_type"] == "bible_verse":
      note["title"] = f"{books.get(note['book_number'], 'Book ' + str(note['book_number']))} {note['chapter']}:{note['verse']}"
    elif note["item_type"] == "commentary":
      book = books.get(note["book_number"], f"Book {note['book_number']}")
      row = connection.execute(
        "SELECT end_verse FROM commentary_entries WHERE commentary_id = %s AND book_number = %s AND chapter = %s AND verse = %s",
        (note["source_code"], note["book_number"], note["chapter"], note["verse"]),
      ).fetchone()
      covers = label_range(book, note["chapter"], note["verse"], row[0]) if row else f"{book} {note['chapter']}:{note['verse']}"
      note["title"] = f"{covers} ({commentary_names.get(note['source_code'], note['source_code'])})"
    else:
      row = connection.execute(
        "SELECT unit_title FROM devotional_entries WHERE devotional_id = %s AND section = %s AND unit = %s LIMIT 1",
        (note["source_code"], note["section"], note["unit"]),
      ).fetchone()
      name = devotional_names.get(note["source_code"], note["source_code"])
      note["title"] = f"{row[0] if row else 'Reading ' + str(note['unit'])} ({name})"
  return notes


def _check_item(item_type: str, source_code: str | None, book_number, chapter, verse, section, unit) -> dict:
  """The place a note is about, checked. Fields that do not belong to the type must be empty."""
  if item_type not in ITEM_TYPES:
    raise NoteProblem("A note is about a Bible verse, a commentary or a devotional.")
  if item_type in SCRIPTURE_TYPES:
    if not isinstance(book_number, int) or not 1 <= book_number <= 66:
      raise NoteProblem("Please choose a book of the Bible.")
    if not isinstance(chapter, int) or not 1 <= chapter <= 200 or not isinstance(verse, int) or not 1 <= verse <= 200:
      raise NoteProblem("That chapter and verse are not valid.")
    if section is not None or unit is not None:
      raise NoteProblem("A note on a verse has no section or unit.")
  else:
    if not isinstance(section, int) or not 0 <= section <= 1000 or not isinstance(unit, int) or not 1 <= unit <= 1000:
      raise NoteProblem("That day or chapter is not valid.")
    if book_number is not None or chapter is not None or verse is not None:
      raise NoteProblem("A note on a devotional has no verse.")
  if not source_code or not SOURCE_PATTERN.match(source_code):
    raise NoteProblem("Please say which Bible, commentary or devotional the note is about.")
  return {
    "item_type": item_type,
    "source_code": source_code,
    "book_number": book_number,
    "chapter": chapter,
    "verse": verse,
    "section": section,
    "unit": unit,
  }


def create_note(
  user_id: int,
  item_type: str,
  source_code: str | None,
  book_number: int | None,
  chapter: int | None,
  verse: int | None,
  section: int | None,
  unit: int | None,
  body: str,
) -> dict:
  item = _check_item(item_type, source_code, book_number, chapter, verse, section, unit)
  try:
    cleaned = check_rich_text(body, NOTE_HTML_LIMIT, NOTE_TEXT_LIMIT, "note")
  except ContactProblem as problem:
    raise NoteProblem(str(problem))
  with connect() as connection:
    if item_type == "bible_verse" and not connection.execute(
      "SELECT 1 FROM verses WHERE book_number = %s AND chapter = %s AND verse = %s LIMIT 1", (book_number, chapter, verse)
    ).fetchone():
      raise NoteProblem("There is no such verse in the Bible.")
    count = connection.execute("SELECT count(*) FROM notes WHERE user_id = %s", (user_id,)).fetchone()[0]
    if count >= MAX_NOTES_PER_USER:
      raise NoteProblem(f"You have reached the limit of {MAX_NOTES_PER_USER} notes. Please delete some first.")
    row = connection.execute(
      f"""
      INSERT INTO notes (user_id, item_type, source_code, book_number, chapter, verse, section, unit, body)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
      RETURNING {COLUMNS}
      """,
      (
        user_id,
        item["item_type"],
        item["source_code"],
        item["book_number"],
        item["chapter"],
        item["verse"],
        item["section"],
        item["unit"],
        cleaned["html"],
      ),
    ).fetchone()
    return _describe(connection, [_row_to_note(row)])[0]


def list_notes(
  user_id: int,
  item_type: str | None = None,
  source_code: str | None = None,
  book_number: int | None = None,
  chapter: int | None = None,
  verse: int | None = None,
  section: int | None = None,
  unit: int | None = None,
) -> list[dict]:
  """The visitor's own notes, newest first. With item_type, only the notes about that one item: a verse is
  the same item in every Bible (the numbering is the KJV's), and a commentary or devotional note is
  matched by its commentary or devotional as well."""
  conditions = ["user_id = %s"]
  values: list = [user_id]
  if item_type is not None:
    if item_type not in ITEM_TYPES:
      raise NoteProblem("A note is about a Bible verse, a commentary or a devotional.")
    conditions.append("item_type = %s")
    values.append(item_type)
    if item_type in SCRIPTURE_TYPES:
      conditions.append("book_number = %s AND chapter = %s AND verse = %s")
      values.extend([book_number, chapter, verse])
      if item_type == "commentary":
        conditions.append("source_code = %s")
        values.append(source_code)
    else:
      conditions.append("source_code = %s AND section = %s AND unit = %s")
      values.extend([source_code, section, unit])
  with connect() as connection:
    rows = connection.execute(
      f"SELECT {COLUMNS} FROM notes WHERE {' AND '.join(conditions)} ORDER BY created_at DESC, id DESC LIMIT {LIST_LIMIT}",
      values,
    ).fetchall()
    return _describe(connection, [_row_to_note(row) for row in rows])


def update_note(user_id: int, note_id: int, body: str) -> dict:
  """Replaces the text of one of the visitor's own notes. What the note is about does not change."""
  try:
    cleaned = check_rich_text(body, NOTE_HTML_LIMIT, NOTE_TEXT_LIMIT, "note")
  except ContactProblem as problem:
    raise NoteProblem(str(problem))
  with connect() as connection:
    row = connection.execute(
      f"UPDATE notes SET body = %s, updated_at = now() WHERE id = %s AND user_id = %s RETURNING {COLUMNS}",
      (cleaned["html"], note_id, user_id),
    ).fetchone()
    if row is None:
      raise NoteProblem("That note was not found.", 404)
    return _describe(connection, [_row_to_note(row)])[0]


def delete_note(user_id: int, note_id: int) -> None:
  with connect() as connection:
    deleted = connection.execute("DELETE FROM notes WHERE id = %s AND user_id = %s RETURNING id", (note_id, user_id)).fetchone()
  if deleted is None:
    raise NoteProblem("That note was not found.", 404)

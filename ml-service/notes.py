"""Notes that a logged-in visitor writes about a Bible verse, a commentary note or a devotional reading.

The My notes list (list_notes) also shows the visitor's own notes, pins and routes on the maps (map_marks.py): one
entry per map (item_type "map"), listing them, so they can find what they marked on which map; those are changed or
deleted on the map itself.

A user has many notes. Each is about one item (item_type and where it is), has the time it was written
and a body: a little HTML from the editor (Quill), cleaned before it is kept, so it is safe to show.
"""

import html
import re

from commentaries import label_range
from contact import ContactProblem, check_rich_text
from search import connect

ITEM_TYPES = ("bible_verse", "commentary", "devotional")
# What the My notes list can be kept to: the notes, and the visitor's marks on the maps.
LIST_TYPES = (*ITEM_TYPES, "map")
MARK_WORDS = {"note": "Note", "pin": "Pin", "route": "Route"}
SCRIPTURE_TYPES = ("bible_verse", "commentary")
NOTE_TEXT_LIMIT = 10000
NOTE_HTML_LIMIT = 60000
SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
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


def _map_entry(map_id: str, map_title: str, marks: list) -> dict:
  """One map's entry in the My notes list: the member's notes, pins and routes on it, oldest first, as a short list
  (their text is plain, so it is made into safe HTML here, line breaks kept). Dated by the first and the latest
  change. Its id is the first mark's (ids only need to be unique among the entries of one kind)."""
  items = []
  for kind, name, body, _created, _updated, _mark_id in marks:
    label = f"Route “{html.escape(name)}”" if kind == "route" else MARK_WORDS[kind]
    text = html.escape(body).replace("\n", "<br>") if body else "<em>No note.</em>"
    items.append(f"<li><strong>{label}:</strong> {text}</li>")
  return {
    "id": min(entry[5] for entry in marks),
    "item_type": "map",
    "source_code": map_id,
    "book_number": None,
    "chapter": None,
    "verse": None,
    "section": None,
    "unit": None,
    "body": f"<ul>{''.join(items)}</ul>",
    "created_at": min(entry[3] for entry in marks).isoformat(),
    "updated_at": max(entry[4] for entry in marks).isoformat(),
    "title": map_title,
    "mark_count": len(marks),
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
      INSERT INTO notes (user_id, item_type, source_code, book_number, chapter, verse, section, unit, body, body_text)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        cleaned["text"],
      ),
    ).fetchone()
    return _describe(connection, [_row_to_note(row)])[0]


PER_PAGE_LIMIT = 200


def _like_pattern(word: str) -> str:
  """A word as a LIKE pattern that matches it anywhere, with %, _ and the escape itself taken literally."""
  escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
  return f"%{escaped}%"


def list_notes(
  user_id: int,
  item_type: str | None = None,
  source_code: str | None = None,
  book_number: int | None = None,
  chapter: int | None = None,
  verse: int | None = None,
  section: int | None = None,
  unit: int | None = None,
  query: str | None = None,
  page: int = 1,
  per_page: int = PER_PAGE_LIMIT,
) -> dict:
  """The visitor's own notes, newest first, one page of them: {"notes", "total", "page", "per_page"}.

  item_type alone keeps one kind of note. With the place as well (the verse, the commentary and verse, or
  the devotional, section and unit) only the notes about that one item are kept; a verse is the same item in
  every Bible (the numbering is the KJV's). query keeps the notes whose text has every word of it, in any
  case and any part of a word."""
  if item_type is not None and item_type not in LIST_TYPES:
    raise NoteProblem("A note is about a Bible verse, a commentary, a devotional or a map.")
  if page < 1 or not 1 <= per_page <= PER_PAGE_LIMIT:
    raise NoteProblem(f"Pages are from 1 to {PER_PAGE_LIMIT} notes.")
  conditions = ["user_id = %s"]
  values: list = [user_id]
  if item_type is not None:
    conditions.append("item_type = %s")
    values.append(item_type)
  for column, value in (("book_number", book_number), ("chapter", chapter), ("verse", verse), ("section", section), ("unit", unit)):
    if value is not None:
      conditions.append(f"{column} = %s")
      values.append(value)
  if source_code is not None and item_type in ("commentary", "devotional"):
    conditions.append("source_code = %s")
    values.append(source_code)
  words = (query or "").split()
  if len(words) > 10:
    raise NoteProblem("Please search for up to 10 words.")
  for word in words:
    conditions.append("body_text ILIKE %s")
    values.append(_like_pattern(word))
  where = " AND ".join(conditions)
  # The visitor's own marks on published maps join the list (all kinds, or "map") as one entry per map, while the
  # account may still use the maps; never when the list is kept to one item (a notes window). A map is listed when
  # its title, or the note or route name of any of the member's marks on it, has every word searched for.
  with_marks = item_type in (None, "map") and all(
    value is None for value in (book_number, chapter, verse, section, unit)
  )
  with_notes = item_type != "map"
  mark_conditions = ["map_marks.user_id = %s", "maps.is_published", "users.use_maps"]
  mark_values: list = [user_id]
  for word in words:
    mark_conditions.append(
      "EXISTS (SELECT 1 FROM map_marks AS searched WHERE searched.user_id = map_marks.user_id AND "
      "searched.map_id = maps.id AND concat_ws(' ', searched.body, searched.name, maps.title) ILIKE %s)"
    )
    mark_values.append(_like_pattern(word))
  marks_from = (
    "map_marks JOIN maps ON maps.id = map_marks.map_id JOIN users ON users.id = map_marks.user_id "
    f"WHERE {' AND '.join(mark_conditions)}"
  )
  parts, part_values = [], []
  if with_notes:
    parts.append(f"SELECT 'note' AS source, id::text AS key, created_at AS listed_at FROM notes WHERE {where}")
    part_values += values
  if with_marks:
    # A map is placed in the list by the latest change to the member's marks on it.
    parts.append(
      f"SELECT 'map' AS source, map_marks.map_id AS key, max(map_marks.updated_at) AS listed_at FROM {marks_from} "
      "GROUP BY map_marks.map_id"
    )
    part_values += mark_values
  listing = " UNION ALL ".join(parts)
  with connect() as connection:
    total = connection.execute(f"SELECT count(*) FROM ({listing}) AS listed", part_values).fetchone()[0]
    chosen = connection.execute(
      f"SELECT source, key FROM ({listing}) AS listed ORDER BY listed_at DESC, key DESC LIMIT %s OFFSET %s",
      [*part_values, per_page, (page - 1) * per_page],
    ).fetchall()
    note_ids = [int(key) for source, key in chosen if source == "note"]
    map_ids = [key for source, key in chosen if source == "map"]
    found = {}
    if note_ids:
      rows = connection.execute(f"SELECT {COLUMNS} FROM notes WHERE id = ANY(%s)", (note_ids,)).fetchall()
      for note in _describe(connection, [_row_to_note(row) for row in rows]):
        found[("note", str(note["id"]))] = note
    if map_ids:
      rows = connection.execute(
        """
        SELECT maps.id, maps.title, map_marks.kind, map_marks.name, map_marks.body, map_marks.created_at,
          map_marks.updated_at, map_marks.id
        FROM map_marks JOIN maps ON maps.id = map_marks.map_id
        WHERE map_marks.user_id = %s AND map_marks.map_id = ANY(%s)
        ORDER BY map_marks.created_at, map_marks.id
        """,
        (user_id, map_ids),
      ).fetchall()
      grouped: dict[str, tuple[str, list]] = {}
      for map_id, map_title, *mark in rows:
        grouped.setdefault(map_id, (map_title, []))[1].append(tuple(mark))
      for map_id, (map_title, marks) in grouped.items():
        found[("map", map_id)] = _map_entry(map_id, map_title, marks)
  notes = [found[(source, key)] for source, key in chosen if (source, key) in found]
  return {"notes": notes, "total": total, "page": page, "per_page": per_page}


def update_note(user_id: int, note_id: int, body: str) -> dict:
  """Replaces the text of one of the visitor's own notes. What the note is about does not change."""
  try:
    cleaned = check_rich_text(body, NOTE_HTML_LIMIT, NOTE_TEXT_LIMIT, "note")
  except ContactProblem as problem:
    raise NoteProblem(str(problem))
  with connect() as connection:
    row = connection.execute(
      f"UPDATE notes SET body = %s, body_text = %s, updated_at = now() WHERE id = %s AND user_id = %s RETURNING {COLUMNS}",
      (cleaned["html"], cleaned["text"], note_id, user_id),
    ).fetchone()
    if row is None:
      raise NoteProblem("That note was not found.", 404)
    return _describe(connection, [_row_to_note(row)])[0]


def delete_note(user_id: int, note_id: int) -> None:
  with connect() as connection:
    deleted = connection.execute("DELETE FROM notes WHERE id = %s AND user_id = %s RETURNING id", (note_id, user_id)).fetchone()
  if deleted is None:
    raise NoteProblem("That note was not found.", 404)

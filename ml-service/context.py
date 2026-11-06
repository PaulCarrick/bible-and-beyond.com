"""What the result links show: the verses around a verse ("Show in Context"), the whole chapter
of a verse ("Full Chapter"), and the same verse in the other Bibles ("Other Translations")."""

from search import connect


def find_translation_and_book(connection, translation_code, book_number):
  """The id and code of a published translation and the name of the book, or None if either is missing."""
  translation = connection.execute(
    "SELECT id, code FROM translations WHERE code = %s AND is_published", (translation_code,)
  ).fetchone()
  book = connection.execute("SELECT name FROM books WHERE number = %s", (book_number,)).fetchone()
  if translation is None or book is None:
    return None
  return translation[0], translation[1], book[0]


def get_parallel(book_number, chapter, verse):
  """Return the verse as it reads in every published translation that has it.

  Translations that do not have the verse (a Bible with only the New Testament, or one that
  numbers its verses differently) are left out. Returns None when no translation has it.
  """
  with connect() as connection:
    book = connection.execute("SELECT name FROM books WHERE number = %s", (book_number,)).fetchone()
    if book is None:
      return None
    rows = connection.execute(
      """
      SELECT t.code, t.name, t.language, v.text
      FROM verses v
      JOIN translations t ON t.id = v.translation_id
      WHERE t.is_published AND v.book_number = %s AND v.chapter = %s AND v.verse = %s
      ORDER BY t.code
      """,
      (book_number, chapter, verse),
    ).fetchall()

  if not rows:
    return None
  return {
    "book_number": book_number,
    "book_name": book[0],
    "chapter": chapter,
    "verse": verse,
    "translations": [
      {"code": code, "name": name, "language": language, "text": text}
      for code, name, language, text in rows
    ],
  }


def get_chapter(translation_code, book_number, chapter, verse):
  """Return every verse of the chapter that contains the verse, with that verse marked.

  Returns None when the translation is unknown or hidden, or the verse does not exist.
  """
  with connect() as connection:
    found = find_translation_and_book(connection, translation_code, book_number)
    if found is None:
      return None
    translation_id, code, book_name = found
    rows = connection.execute(
      """
      SELECT verse, text FROM verses
      WHERE translation_id = %s AND book_number = %s AND chapter = %s
      ORDER BY verse
      """,
      (translation_id, book_number, chapter),
    ).fetchall()

  if not any(row_verse == verse for row_verse, _text in rows):
    return None
  return {
    "translation": code,
    "book_number": book_number,
    "book_name": book_name,
    "chapter": chapter,
    "verse": verse,
    "verses": [
      {"chapter": chapter, "verse": row_verse, "text": text, "is_target": row_verse == verse}
      for row_verse, text in rows
    ],
  }


def get_context(translation_code, book_number, chapter, verse, before, after):
  """Return the verse with the requested number of verses before and after it.

  The verses run in reading order and cross chapter boundaries, but stop at the edges of the
  book. Returns None when the translation is unknown or hidden, or the verse does not exist.
  """
  with connect() as connection:
    found = find_translation_and_book(connection, translation_code, book_number)
    if found is None:
      return None
    translation_id, code, book_name = found

    rows = connection.execute(
      """
      WITH ordered AS (
        SELECT chapter, verse, text, ROW_NUMBER() OVER (ORDER BY chapter, verse) AS position
        FROM verses
        WHERE translation_id = %(translation_id)s AND book_number = %(book_number)s
      ),
      target AS (
        SELECT position FROM ordered WHERE chapter = %(chapter)s AND verse = %(verse)s
      )
      SELECT chapter, verse, text, position = (SELECT position FROM target) AS is_target
      FROM ordered
      WHERE position BETWEEN (SELECT position FROM target) - %(before)s
                         AND (SELECT position FROM target) + %(after)s
      ORDER BY position
      """,
      {
        "translation_id": translation_id,
        "book_number": book_number,
        "chapter": chapter,
        "verse": verse,
        "before": before,
        "after": after,
      },
    ).fetchall()

  if not rows:
    return None
  return {
    "translation": code,
    "book_number": book_number,
    "book_name": book_name,
    "chapter": chapter,
    "verse": verse,
    "verses_before": before,
    "verses_after": after,
    "verses": [
      {"chapter": row_chapter, "verse": row_verse, "text": text, "is_target": is_target}
      for row_chapter, row_verse, text, is_target in rows
    ],
  }

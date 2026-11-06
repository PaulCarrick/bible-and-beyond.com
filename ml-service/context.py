"""The verses around a verse, for "Show in Context"."""

from search import connect


def get_context(translation_code, book_number, chapter, verse, before, after):
  """Return the verse with the requested number of verses before and after it.

  The verses run in reading order and cross chapter boundaries, but stop at the edges of the
  book. Returns None when the translation is unknown or hidden, or the verse does not exist.
  """
  with connect() as connection:
    translation = connection.execute(
      "SELECT id, code FROM translations WHERE code = %s AND is_published", (translation_code,)
    ).fetchone()
    if translation is None:
      return None
    book = connection.execute("SELECT name FROM books WHERE number = %s", (book_number,)).fetchone()
    if book is None:
      return None

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
        "translation_id": translation[0],
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
    "translation": translation[1],
    "book_number": book_number,
    "book_name": book[0],
    "chapter": chapter,
    "verse": verse,
    "verses_before": before,
    "verses_after": after,
    "verses": [
      {"chapter": row_chapter, "verse": row_verse, "text": text, "is_target": is_target}
      for row_chapter, row_verse, text, is_target in rows
    ],
  }

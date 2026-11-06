"""What the result links show: the verses around a verse ("Show in Context"), the whole chapter
of a verse ("Full Chapter"), the same verse in the other Bibles ("Other Translations"), and the
verses it is cross-referenced with ("Related Verses")."""

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


# A cross reference that is a range of verses is shown as at most this many verses.
MAXIMUM_VERSES_PER_REFERENCE = 15


def label_for_range(book_names, start, end):
  """A readable name for a verse or a range, such as "Romans 5:8" or "1 John 4:9–10"."""
  book, chapter, verse = start
  if end is None or end == start:
    return f"{book_names[book]} {chapter}:{verse}"
  end_book, end_chapter, end_verse = end
  if end_book != book:
    return f"{book_names[book]} {chapter}:{verse} – {book_names[end_book]} {end_chapter}:{end_verse}"
  if end_chapter != chapter:
    return f"{book_names[book]} {chapter}:{verse} – {end_chapter}:{end_verse}"
  return f"{book_names[book]} {chapter}:{verse}–{end_verse}"


# The verses that point AT a verse: a reference that begins at that verse (however far its range
# runs), or a range inside the same chapter that contains it. A range that begins in an earlier
# chapter and runs through this one is not matched; there are very few of them.
POINTING_AT = """
  to_book = %(book)s AND to_chapter = %(chapter)s AND (
    to_verse = %(verse)s
    OR (
      to_verse < %(verse)s
      AND COALESCE(to_end_verse, to_verse) >= %(verse)s
      AND (to_end_chapter IS NULL OR to_end_chapter = to_chapter)
      AND (to_end_book IS NULL OR to_end_book = to_book)
    )
  )
"""


def get_related(translation_code, book_number, chapter, verse, limit, direction="from"):
  """Return the best-voted cross references of a verse, with their text in the given translation.

  direction "from": where the verse points to. Each reference is a verse or a range of verses.
  direction "to": which verses point at it. Each reference is the verse that points at it.
  Either way the answer also says how many there are in the other direction.

  Returns None when the translation is unknown or hidden, or does not have the verse.
  A reference to verses that the translation lacks is still listed, with no verses.
  """
  with connect() as connection:
    found = find_translation_and_book(connection, translation_code, book_number)
    if found is None:
      return None
    translation_id, code, book_name = found
    has_verse = connection.execute(
      "SELECT 1 FROM verses WHERE translation_id = %s AND book_number = %s AND chapter = %s AND verse = %s",
      (translation_id, book_number, chapter, verse),
    ).fetchone()
    if has_verse is None:
      return None

    book_names = dict(connection.execute("SELECT number, name FROM books").fetchall())
    where = {"book": book_number, "chapter": chapter, "verse": verse}
    outgoing_total = connection.execute(
      "SELECT COUNT(*) FROM cross_references WHERE from_book = %(book)s AND from_chapter = %(chapter)s"
      " AND from_verse = %(verse)s",
      where,
    ).fetchone()[0]
    incoming_total = connection.execute(
      f"SELECT COUNT(DISTINCT (from_book, from_chapter, from_verse)) FROM cross_references WHERE {POINTING_AT}",
      where,
    ).fetchone()[0]

    references = []
    if direction == "to":
      rows = connection.execute(
        f"""
        SELECT from_book, from_chapter, from_verse, MAX(votes) AS best
        FROM cross_references
        WHERE {POINTING_AT}
        GROUP BY from_book, from_chapter, from_verse
        ORDER BY best DESC, from_book, from_chapter, from_verse
        LIMIT %(limit)s
        """,
        {**where, "limit": limit},
      ).fetchall()
      spans = [((b, c, v), None, votes) for b, c, v, votes in rows]
    else:
      rows = connection.execute(
        """
        SELECT to_book, to_chapter, to_verse, to_end_book, to_end_chapter, to_end_verse, votes
        FROM cross_references
        WHERE from_book = %s AND from_chapter = %s AND from_verse = %s
        ORDER BY votes DESC, to_book, to_chapter, to_verse
        LIMIT %s
        """,
        (book_number, chapter, verse, limit),
      ).fetchall()
      spans = [
        ((to_book, to_chapter, to_verse), (end_book, end_chapter, end_verse) if end_book is not None else None, votes)
        for to_book, to_chapter, to_verse, end_book, end_chapter, end_verse, votes in rows
      ]

    for start, end, votes in spans:
      last = end or start
      verses = connection.execute(
        """
        SELECT v.book_number, v.chapter, v.verse, v.text
        FROM verses v
        WHERE v.translation_id = %s
          AND (v.book_number, v.chapter, v.verse) >= (%s, %s, %s)
          AND (v.book_number, v.chapter, v.verse) <= (%s, %s, %s)
        ORDER BY v.book_number, v.chapter, v.verse
        LIMIT %s
        """,
        (translation_id, *start, *last, MAXIMUM_VERSES_PER_REFERENCE + 1),
      ).fetchall()
      references.append(
        {
          "votes": votes,
          "reference": label_for_range(book_names, start, end),
          "book_number": start[0],
          "chapter": start[1],
          "verse": start[2],
          "verses": [
            {"book_name": book_names[b], "chapter": c, "verse": v, "text": text}
            for b, c, v, text in verses[:MAXIMUM_VERSES_PER_REFERENCE]
          ],
          "has_more_verses": len(verses) > MAXIMUM_VERSES_PER_REFERENCE,
        }
      )

  return {
    "translation": code,
    "book_number": book_number,
    "book_name": book_name,
    "chapter": chapter,
    "verse": verse,
    "direction": direction,
    "outgoing_total": outgoing_total,
    "incoming_total": incoming_total,
    "total": incoming_total if direction == "to" else outgoing_total,
    "shown": len(references),
    "references": references,
  }

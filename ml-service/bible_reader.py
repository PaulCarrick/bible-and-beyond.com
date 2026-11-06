"""Reading a Bible stored on this site chapter by chapter ("Read the Bible").

Only the Bibles in our own database can be read this way: a Bible licensed through API.Bible is
never stored, so it cannot be read a chapter at a time.
"""

from search import connect
from word_links import attach_links


def find_translation(connection, translation_code):
  """The id, code, name and language of a published translation, or None."""
  row = connection.execute(
    "SELECT id, code, name, language FROM translations WHERE code = %s AND is_published", (translation_code,)
  ).fetchone()
  if row is None:
    return None
  return {"id": row[0], "code": row[1], "name": row[2], "language": row[3]}


def describe(translation):
  return {key: translation[key] for key in ("code", "name", "language")}


def get_contents(translation_code):
  """The books and chapters a Bible has, for choosing what to read. None for an unknown Bible."""
  with connect() as connection:
    translation = find_translation(connection, translation_code)
    if translation is None:
      return None
    rows = connection.execute(
      "SELECT v.book_number, b.name, v.chapter FROM verses v JOIN books b ON b.number = v.book_number "
      "WHERE v.translation_id = %s GROUP BY v.book_number, b.name, v.chapter ORDER BY v.book_number, v.chapter",
      (translation["id"],),
    ).fetchall()
  books = []
  for book_number, book_name, chapter in rows:
    if not books or books[-1]["number"] != book_number:
      books.append({"number": book_number, "name": book_name, "chapters": []})
    books[-1]["chapters"].append(chapter)
  return {"translation": describe(translation), "books": books}


def get_chapter(translation_code, book_number, chapter):
  """Every verse of one chapter of a Bible, with the chapters before and after it.

  A verse has "links" when the English words of that verse are tied to Strong's numbers (the BSB).
  The chapters before and after run across books. Returns None when the Bible or the chapter is not
  there.
  """
  with connect() as connection:
    translation = find_translation(connection, translation_code)
    book = connection.execute("SELECT name FROM books WHERE number = %s", (book_number,)).fetchone()
    if translation is None or book is None:
      return None
    rows = connection.execute(
      "SELECT chapter, verse, text FROM verses WHERE translation_id = %s AND book_number = %s AND chapter = %s "
      "ORDER BY verse",
      (translation["id"], book_number, chapter),
    ).fetchall()
    if not rows:
      return None
    verses = [{"chapter": row_chapter, "verse": verse, "text": text} for row_chapter, verse, text in rows]
    attach_links(connection, translation["id"], book_number, verses)
    chapters = connection.execute(
      "SELECT DISTINCT v.book_number, b.name, v.chapter FROM verses v JOIN books b ON b.number = v.book_number "
      "WHERE v.translation_id = %s ORDER BY v.book_number, v.chapter",
      (translation["id"],),
    ).fetchall()

  position = next(index for index, row in enumerate(chapters) if (row[0], row[2]) == (book_number, chapter))

  def neighbour(index):
    if 0 <= index < len(chapters):
      number, name, chapter_number = chapters[index]
      return {"book_number": number, "book_name": name, "chapter": chapter_number}
    return None

  return {
    "translation": describe(translation),
    "book_number": book_number,
    "book_name": book[0],
    "chapter": chapter,
    "verses": [
      {key: value for key, value in verse.items() if key != "chapter"} for verse in verses
    ],
    "previous": neighbour(position - 1),
    "next": neighbour(position + 1),
  }

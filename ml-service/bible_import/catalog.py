"""List the translations in the search database and change which ones are published."""

from bible_import.errors import ImportProblem
from search import connect

LAST_PUBLISHED_MESSAGE = (
  "At least one Bible has to stay published, or the search page would have nothing to search."
)


def list_translations():
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute(
        """
        SELECT t.code, t.name, t.language, t.license, t.source_url, t.is_published, COUNT(v.id)
        FROM translations t
        LEFT JOIN verses v ON v.translation_id = t.id
        GROUP BY t.id
        ORDER BY t.code
        """
      )
      return [
        {
          "code": code,
          "name": name,
          "language": language,
          "license": license_text,
          "source_url": source_url,
          "is_published": is_published,
          "verse_count": verse_count,
        }
        for code, name, language, license_text, source_url, is_published, verse_count in cursor.fetchall()
      ]


def find_translation(cursor, code):
  cursor.execute("SELECT id, is_published FROM translations WHERE code = %s FOR UPDATE", (code,))
  row = cursor.fetchone()
  if row is None:
    raise ImportProblem(f"There is no Bible with the code {code}.")
  return row


def other_published_count(cursor, translation_id):
  cursor.execute(
    "SELECT COUNT(*) FROM translations WHERE is_published AND id <> %s", (translation_id,)
  )
  return cursor.fetchone()[0]


def set_published(code, published):
  with connect() as connection:
    with connection.cursor() as cursor:
      translation_id, is_published = find_translation(cursor, code)
      if is_published and not published and other_published_count(cursor, translation_id) == 0:
        raise ImportProblem(LAST_PUBLISHED_MESSAGE)
      cursor.execute("UPDATE translations SET is_published = %s WHERE id = %s", (published, translation_id))
  return {"ok": True, "code": code, "is_published": published}


def delete_translation(code):
  with connect() as connection:
    with connection.cursor() as cursor:
      translation_id, is_published = find_translation(cursor, code)
      if is_published and other_published_count(cursor, translation_id) == 0:
        raise ImportProblem(LAST_PUBLISHED_MESSAGE)
      cursor.execute("SELECT COUNT(*) FROM verses WHERE translation_id = %s", (translation_id,))
      verse_count = cursor.fetchone()[0]
      # Deleting the translation also removes its verses and their embeddings (ON DELETE CASCADE).
      cursor.execute("DELETE FROM translations WHERE id = %s", (translation_id,))
  return {"ok": True, "code": code, "deleted_verse_count": verse_count}

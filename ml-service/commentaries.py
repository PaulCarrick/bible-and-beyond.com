"""Public-domain Bible commentaries ("Commentaries" link): download, load and look up.

Data: the Free Use Bible API (https://bible.helloao.org, AO Lab), which serves each commentary as
one JSON file per chapter and marks each Public Domain (https://creativecommons.org/publicdomain/mark/1.0/).
We load six of its commentaries into our own database. (Its seventh, the Tyndale Open Study Notes,
is CC BY-SA, not public domain, and is not used.)

An entry in a file is {"type": "verse", "number": N, "content": ["paragraph", ...]}. Some
commentaries comment on one verse at a time (Gill, Clarke, Jamieson-Fausset-Brown) and skip verses
they have nothing to say about. Others comment on sections: an entry starts at its verse and runs
until the next entry (Matthew Henry, Calvin, Keil and Delitzsch).
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from search import connect

BASE_URL = "https://bible.helloao.org/api"

# id on the Free Use Bible API: (name, short name, whether an entry runs to the next entry).
# The order is the order of the tabs.
COMMENTARIES = {
  "matthew-henry": ("Matthew Henry's Commentary", "Matthew Henry", True),
  "john-gill": ("John Gill's Exposition of the Bible", "John Gill", False),
  "adam-clarke": ("Adam Clarke's Commentary", "Adam Clarke", False),
  "jamieson-fausset-brown": ("Jamieson-Fausset-Brown Commentary", "Jamieson-Fausset-Brown", False),
  "john-calvin": ("John Calvin's Commentaries", "John Calvin", True),
  "keil-delitzsch": ("Keil and Delitzsch's Old Testament Commentary", "Keil and Delitzsch", True),
}
LICENSE_URL = "https://creativecommons.org/publicdomain/mark/1.0/"
# Be polite to the host: a few connections at a time.
DOWNLOAD_WORKERS = 4
ATTEMPTS = 4


class CommentaryProblem(ValueError):
  """A file cannot be understood. The message says which."""


def chapter_path(folder, commentary_id, book_code, chapter):
  return Path(folder) / commentary_id / f"{book_code}_{chapter}.json"


def fetch_json(client, url):
  """The JSON at a URL, retrying a few times. None when the host says there is no such file."""
  for attempt in range(ATTEMPTS):
    try:
      response = client.get(url, timeout=60)
    except httpx.HTTPError:
      response = None
    if response is not None and response.status_code == 200:
      return response.json()
    if response is not None and response.status_code == 404:
      return None
    time.sleep(2 * (attempt + 1))
  raise CommentaryProblem(f"Could not download {url}.")


def download(folder, commentary_ids, report=print):
  """Save every chapter file of these commentaries under folder (existing files are kept).

  Returns the number of files downloaded. Stop it and run it again at any time: it carries on.
  """
  folder = Path(folder)
  downloaded = 0
  with httpx.Client(follow_redirects=True) as client:
    for commentary_id in commentary_ids:
      books = fetch_json(client, f"{BASE_URL}/c/{commentary_id}/books.json")
      if books is None:
        raise CommentaryProblem(f"The host has no commentary '{commentary_id}'.")
      directory = folder / commentary_id
      directory.mkdir(parents=True, exist_ok=True)
      (directory / "books.json").write_text(json.dumps(books["books"], ensure_ascii=False), encoding="utf-8")

      wanted = [
        (book["id"], chapter)
        for book in books["books"]
        for chapter in range(1, book["numberOfChapters"] + 1)
        if not chapter_path(folder, commentary_id, book["id"], chapter).exists()
      ]
      report(f"{commentary_id}: {len(wanted):,} chapter files to download")

      def save(item):
        book_code, chapter = item
        body = fetch_json(client, f"{BASE_URL}/c/{commentary_id}/{book_code}/{chapter}.json")
        if body is not None:
          chapter_path(folder, commentary_id, book_code, chapter).write_text(
            json.dumps(body, ensure_ascii=False), encoding="utf-8"
          )
        return body is not None

      with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        for count, saved in enumerate(pool.map(save, wanted), start=1):
          downloaded += 1 if saved else 0
          if count % 200 == 0:
            report(f"  {commentary_id}: {count:,} of {len(wanted):,}")
  return downloaded


def paragraphs_to_text(content):
  """The paragraphs of an entry as one text, paragraphs separated by a blank line."""
  parts = [part.strip() for part in content if isinstance(part, str) and part.strip()]
  return "\n\n".join(parts)


def read_commentary(folder, commentary_id, book_numbers_by_code):
  """Read one commentary's files. Returns (entries, introductions).

  entries are (book, chapter, verse, end_verse or None, text). introductions are
  (book, chapter, text), chapter 0 being the introduction to the whole book.
  """
  sections = COMMENTARIES[commentary_id][2]
  directory = Path(folder) / commentary_id
  books_file = directory / "books.json"
  if not books_file.exists():
    raise CommentaryProblem(f"{books_file} is missing. Download the commentary first.")
  entries = []
  introductions = []
  for book in json.loads(books_file.read_text(encoding="utf-8")):
    book_number = book_numbers_by_code.get(book["id"])
    if book_number is None:
      raise CommentaryProblem(f"I do not know the book '{book['id']}' in {commentary_id}.")
    introduction = (book.get("introduction") or "").strip()
    if introduction:
      introductions.append((book_number, 0, introduction))
    for chapter in range(1, book["numberOfChapters"] + 1):
      path = chapter_path(folder, commentary_id, book["id"], chapter)
      if not path.exists():
        continue
      body = json.loads(path.read_text(encoding="utf-8"))
      chapter_introduction = (body["chapter"].get("introduction") or "").strip()
      if chapter_introduction:
        introductions.append((book_number, chapter, chapter_introduction))
      items = [
        (int(item["number"]), paragraphs_to_text(item.get("content", [])))
        for item in body["chapter"]["content"]
        if item.get("type") == "verse"
      ]
      items = sorted((number, text) for number, text in items if text)
      for index, (number, text) in enumerate(items):
        if sections:
          end_verse = items[index + 1][0] - 1 if index + 1 < len(items) else None
          end_verse = max(end_verse, number) if end_verse is not None else None
        else:
          end_verse = number
        entries.append((book_number, chapter, number, end_verse, text))
  return entries, introductions


def replace_commentary(commentary_id, entries, introductions):
  """Replace everything of one commentary in the database, in one transaction."""
  name, short_name, _sections = COMMENTARIES[commentary_id]
  position = list(COMMENTARIES).index(commentary_id) + 1
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute(
        "INSERT INTO commentaries (id, name, short_name, position, license_url) VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, short_name = EXCLUDED.short_name, "
        "position = EXCLUDED.position, license_url = EXCLUDED.license_url",
        (commentary_id, name, short_name, position, LICENSE_URL),
      )
      cursor.execute("DELETE FROM commentary_entries WHERE commentary_id = %s", (commentary_id,))
      cursor.execute("DELETE FROM commentary_introductions WHERE commentary_id = %s", (commentary_id,))
      with cursor.copy(
        "COPY commentary_entries (commentary_id, book_number, chapter, verse, end_verse, text) FROM STDIN"
      ) as copy:
        for book, chapter, verse, end_verse, text in entries:
          copy.write_row((commentary_id, book, chapter, verse, end_verse, text))
      with cursor.copy(
        "COPY commentary_introductions (commentary_id, book_number, chapter, text) FROM STDIN"
      ) as copy:
        for book, chapter, text in introductions:
          copy.write_row((commentary_id, book, chapter, text))
      cursor.execute("SELECT COUNT(*) FROM commentary_entries WHERE commentary_id = %s", (commentary_id,))
      return cursor.fetchone()[0]


def book_numbers_by_code():
  with connect() as connection:
    return dict(connection.execute("SELECT code, number FROM books").fetchall())


def label_range(book_name, chapter, verse, end_verse):
  """"John 3:1" or "John 3:1–21"; an open end is shown as "John 3:22 to the end of the chapter"."""
  if end_verse is None:
    return f"{book_name} {chapter}:{verse} to the end of the chapter"
  if end_verse == verse:
    return f"{book_name} {chapter}:{verse}"
  return f"{book_name} {chapter}:{verse}–{end_verse}"


def get_commentaries(book_number, chapter, verse, commentary_id=None):
  """The commentaries that have something to say about a verse, and the text of one of them.

  The one shown is commentary_id, or the first of the list. Returns None when the verse's book is
  unknown, no commentary covers the verse, or the one asked for has nothing on it.
  """
  with connect() as connection:
    book = connection.execute("SELECT name FROM books WHERE number = %s", (book_number,)).fetchone()
    if book is None:
      return None
    rows = connection.execute(
      """
      SELECT c.id, c.name, c.short_name, e.verse, e.end_verse, length(e.text)
      FROM commentary_entries e
      JOIN commentaries c ON c.id = e.commentary_id
      WHERE e.book_number = %s AND e.chapter = %s AND e.verse <= %s
        AND COALESCE(e.end_verse, 2147483647) >= %s
      ORDER BY c.position, e.verse DESC
      """,
      (book_number, chapter, verse, verse),
    ).fetchall()
    available = []
    for code, name, short_name, start, end, length in rows:
      if all(entry["id"] != code for entry in available):  # the closest entry of each commentary
        available.append({
          "id": code, "name": name, "short_name": short_name, "characters": length,
          "covers": label_range(book[0], chapter, start, end),
        })
    if not available:
      return None
    chosen = next((entry for entry in available if entry["id"] == commentary_id or commentary_id is None), None)
    if chosen is None:
      return None
    text, = connection.execute(
      "SELECT text FROM commentary_entries WHERE commentary_id = %s AND book_number = %s AND chapter = %s "
      "AND verse <= %s AND COALESCE(end_verse, 2147483647) >= %s ORDER BY verse DESC LIMIT 1",
      (chosen["id"], book_number, chapter, verse, verse),
    ).fetchone()
    introductions = {
      chapter_number: introduction
      for chapter_number, introduction in connection.execute(
        "SELECT chapter, text FROM commentary_introductions WHERE commentary_id = %s AND book_number = %s "
        "AND chapter IN (0, %s)",
        (chosen["id"], book_number, chapter),
      ).fetchall()
    }
  return {
    "book_number": book_number,
    "book_name": book[0],
    "chapter": chapter,
    "verse": verse,
    "commentaries": available,
    "selected": chosen["id"],
    "covers": chosen["covers"],
    "text": text,
    "chapter_introduction": introductions.get(chapter),
    "book_introduction": introductions.get(0),
  }


def check_ids(commentary_ids):
  unknown = [commentary_id for commentary_id in commentary_ids if commentary_id not in COMMENTARIES]
  if unknown:
    raise CommentaryProblem(f"Unknown commentary: {', '.join(unknown)}. Known: {', '.join(COMMENTARIES)}.")
  return commentary_ids

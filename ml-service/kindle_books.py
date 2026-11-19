"""Kindle books (added 2026-11-19 at the owner's request): books read in Amazon's Kindle web reader, listed with the
Devotionals or with the Other books (collection), beside the ones kept on this site. Only a link is kept (kindle_books, migration 062): the text never
comes here, so they cannot be searched, and each reader opens the book signed in to their own Amazon account, so
it works only for those who have the book in their own Kindle library. The page opens it in its own window (Amazon
refuses to be shown inside another site).

The address must be on amazon.com (read.amazon.com, or a book's page). An optional cover picture (PNG, JPEG, WebP or
GIF, up to 2 MB, checked by its first bytes; no SVG, which could carry script) is kept as a file in
data/kindle-covers/<id><extension>, never in a database, and served at /kindle-book-cover/<id>. The "Kindle books"
part of the Drupal Devotionals and Other books pages runs scripts/manage_kindle_books.py, which calls these.
"""

import base64
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from external_sites import ExternalSiteProblem, check_address
from formatted_text import FormattedTextProblem, one_line
from search import connect
from site_icons import kind_of_picture

TITLE_LIMIT = 300
AUTHOR_LIMIT = 200
MAX_BOOKS = 500
COVER_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
MAX_COVER_BYTES = 2 * 1024 * 1024
# Where a Kindle book is listed: with the Devotionals or with the Other books.
COLLECTIONS = {"devotionals": "Devotionals", "books": "Other books"}
COLUMNS = "id, title, author, address, is_published, cover_type, cover_version, created_by, created_at, updated_at, collection"


class KindleBookProblem(Exception):
  """The book or picture cannot be kept; the text says why and is fit to show the administrator."""


def covers_folder() -> Path:
  return Path(os.environ.get("KINDLE_COVERS_FOLDER", Path(__file__).resolve().parent / "data" / "kindle-covers"))


def _describe(row) -> dict:
  return {
    "id": row[0], "title": row[1], "author": row[2], "address": row[3], "is_published": row[4],
    "cover": f"/kindle-book-cover/{row[0]}?v={row[6]}" if row[5] else None,
    "created_by": row[7], "created_at": row[8].isoformat(), "updated_at": row[9].isoformat(), "collection": row[10],
  }


def check_kindle_address(value) -> str:
  """An https address on amazon.com: the Kindle web reader (read.amazon.com/?asin=...) or the book's Amazon page."""
  try:
    address = check_address(value, "Kindle link")
  except ExternalSiteProblem as problem:
    raise KindleBookProblem(str(problem).replace("such as https://read.amazon.com", "such as https://read.amazon.com/?asin=B00DL10JF6")) from problem
  host = (urlsplit(address).hostname or "").lower()
  if host != "amazon.com" and not host.endswith(".amazon.com"):
    raise KindleBookProblem("The Kindle link must be an amazon.com address, such as https://read.amazon.com/?asin=B00DL10JF6.")
  if urlsplit(address).scheme.lower() != "https":
    address = "https" + address[address.index(":"):]
  return address


def check_collection(value) -> str:
  if value not in COLLECTIONS:
    raise KindleBookProblem("A Kindle book is listed with the Devotionals (devotionals) or the Other books (books).")
  return value


def _check(details) -> tuple[str, str, str, bool]:
  if not isinstance(details, dict):
    raise KindleBookProblem("The book could not be read.")
  try:
    title = one_line(details.get("title"), "title", TITLE_LIMIT)
    author = one_line(details.get("author"), "author", AUTHOR_LIMIT) if str(details.get("author") or "").strip() else ""
  except FormattedTextProblem as problem:
    raise KindleBookProblem(str(problem)) from problem
  published = details.get("is_published", True) not in (False, 0, "0", "", "false")
  return title, author, check_kindle_address(details.get("address")), published


def list_books(collection: str | None = None) -> list[dict]:
  """The Kindle books of a collection (or all), for the admin pages, by title."""
  with connect() as connection:
    if collection is None:
      rows = connection.execute(f"SELECT {COLUMNS} FROM kindle_books ORDER BY lower(title), id").fetchall()
    else:
      rows = connection.execute(
        f"SELECT {COLUMNS} FROM kindle_books WHERE collection = %s ORDER BY lower(title), id", (check_collection(collection),)
      ).fetchall()
  return [_describe(row) for row in rows]


def list_public_books() -> list[dict]:
  """The published Kindle books for Read the devotionals and Read other books: which collection, title, author, link
  and cover only."""
  return [
    {key: book[key] for key in ("id", "collection", "title", "author", "address", "cover")}
    for book in list_books() if book["is_published"]
  ]


def get_book(book_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {COLUMNS} FROM kindle_books WHERE id = %s", (book_id,)).fetchone()
  if row is None:
    raise KindleBookProblem("That Kindle book was not found. It may have been deleted.")
  return _describe(row)


def create_book(details, created_by: str) -> dict:
  title, author, address, published = _check(details)
  collection = check_collection(details.get("collection"))
  with connect() as connection:
    if connection.execute("SELECT count(*) FROM kindle_books").fetchone()[0] >= MAX_BOOKS:
      raise KindleBookProblem(f"There can be up to {MAX_BOOKS} Kindle books. Delete one first.")
    row = connection.execute(
      f"""INSERT INTO kindle_books (collection, title, author, address, is_published, created_by)
      VALUES (%s, %s, %s, %s, %s, %s) RETURNING {COLUMNS}""",
      (collection, title, author, address, published, " ".join((created_by or "").split())[:AUTHOR_LIMIT]),
    ).fetchone()
  return _describe(row)


def update_book(book_id: int, details) -> dict:
  title, author, address, published = _check(details)
  with connect() as connection:
    row = connection.execute(
      f"""UPDATE kindle_books SET title = %s, author = %s, address = %s, is_published = %s, updated_at = now()
      WHERE id = %s RETURNING {COLUMNS}""",
      (title, author, address, published, book_id),
    ).fetchone()
  if row is None:
    raise KindleBookProblem("That Kindle book was not found. It may have been deleted.")
  return _describe(row)


def delete_book(book_id: int) -> dict:
  book = get_book(book_id)
  with connect() as connection:
    connection.execute("DELETE FROM kindle_books WHERE id = %s", (book_id,))
  _remove_files(book_id)
  return book


# --- The cover picture ---------------------------------------------------------------------------------------


def _remove_files(book_id: int) -> None:
  for extension in COVER_TYPES:
    (covers_folder() / f"{book_id}{extension}").unlink(missing_ok=True)


def check_cover(path: Path, original_name: str) -> str:
  """The extension to keep the picture under, after checking its size and what it really is (its first bytes)."""
  extension = Path(original_name).suffix.lower()
  extension = ".jpg" if extension == ".jpeg" else extension
  if extension not in COVER_TYPES:
    raise KindleBookProblem("The picture must be a PNG, JPEG, WebP or GIF file.")
  size = path.stat().st_size
  if size == 0:
    raise KindleBookProblem("The picture file is empty.")
  if size > MAX_COVER_BYTES:
    raise KindleBookProblem(f"The picture is larger than {MAX_COVER_BYTES // (1024 * 1024)} MB.")
  with open(path, "rb") as file:
    actual = kind_of_picture(file.read(4096))
  if actual not in COVER_TYPES:
    raise KindleBookProblem("The file is not a PNG, JPEG, WebP or GIF picture (its contents are not one).")
  return actual


def save_cover(book_id: int, path: Path, original_name: str) -> dict:
  """Replaces the book's picture with the uploaded file (copied under a temporary name, then renamed)."""
  get_book(book_id)
  extension = check_cover(path, original_name)
  folder = covers_folder()
  folder.mkdir(parents=True, exist_ok=True)
  temporary = folder / f".{book_id}{extension}.new"
  shutil.copyfile(path, temporary)
  _remove_files(book_id)
  temporary.replace(folder / f"{book_id}{extension}")
  with connect() as connection:
    connection.execute(
      "UPDATE kindle_books SET cover_type = %s, cover_version = %s, updated_at = now() WHERE id = %s",
      (extension, int((folder / f"{book_id}{extension}").stat().st_mtime), book_id),
    )
  return get_book(book_id)


def remove_cover(book_id: int) -> dict:
  get_book(book_id)
  _remove_files(book_id)
  with connect() as connection:
    connection.execute("UPDATE kindle_books SET cover_type = NULL, updated_at = now() WHERE id = %s", (book_id,))
  return get_book(book_id)


def cover_data_uri(book_id: int) -> str | None:
  """The book's picture as a data: address (published or not), for the admin form's preview; None without one."""
  with connect() as connection:
    row = connection.execute("SELECT cover_type FROM kindle_books WHERE id = %s", (book_id,)).fetchone()
  if row is None or row[0] not in COVER_TYPES:
    return None
  path = covers_folder() / f"{book_id}{row[0]}"
  return f"data:{COVER_TYPES[row[0]]};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}" if path.is_file() else None


def cover_file(book_id: int) -> tuple[Path, str] | None:
  """A published book's picture and its media type, or None."""
  with connect() as connection:
    row = connection.execute("SELECT cover_type FROM kindle_books WHERE id = %s AND is_published", (book_id,)).fetchone()
  if row is None or row[0] not in COVER_TYPES:
    return None
  path = covers_folder() / f"{book_id}{row[0]}"
  return (path, COVER_TYPES[row[0]]) if path.is_file() else None

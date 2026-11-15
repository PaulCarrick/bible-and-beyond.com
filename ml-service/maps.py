"""Maps: pictures of maps with a title, a description, where they came from, keywords and the Bible verses they
go with.

An administrator uploads a map on the Drupal "Maps" page (scripts/manage_maps.py): a PNG, JPEG, WebP, GIF or
TIFF picture, or a PDF (one of its pages is drawn as the map). The file is kept as uploaded in the maps folder
(MAPS_FOLDER, ml-service/data/maps until set), never in the database, with two copies made from it: a WebP of
at most DISPLAY_LONGEST_SIDE pixels on its longer side that the site shows ("<id>-display.webp"), and a small
one for the list ("<id>-thumbnail.webp"). The maps table (migration 039) holds the rest, and map_verses the
verses one by one, so the maps of a verse can be found. A new map is hidden until published; uploading again
with the same id replaces its picture and details and keeps its state.

The verses are typed as references ("Acts 13:4-14; Acts 16:11") and read with the reference finder of the
commentaries (scripture_references.py): each must name a verse that exists, else the map is not saved and the
message says which was not understood.
"""

import os
import re
import shutil
from pathlib import Path

from commentaries import HEADLINE_OPTIONS
from search import connect, parse_terms
from scripture_references import BOOK_BY_NORMALIZED_NAME, PATTERN, normalize, verse_limits

MAX_FILE_BYTES = 1024 * 1024 * 1024  # 1 GB, as for the other uploads
TITLE_LIMIT = 200
DESCRIPTION_LIMIT = 5_000
SOURCE_LIMIT = 500
KEYWORDS_LIMIT = 500
VERSES_LIMIT = 2_000
MAX_VERSES = 100
# The copy shown on the site: large enough to zoom into, small enough to load on a phone.
DISPLAY_LONGEST_SIDE = 5000
THUMBNAIL_WIDTH = 480
# Pillow refuses pictures over about 90 million pixels as a safeguard; a scanned wall map can be larger.
MAX_PIXELS = 600_000_000
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
FILE_TYPES = {
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
  ".tif": "image/tiff", ".tiff": "image/tiff", ".pdf": "application/pdf",
}
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class MapProblem(Exception):
  """A map cannot be saved or changed; the text says why and is fit to show the administrator."""


def maps_folder() -> Path:
  return Path(os.environ.get("MAPS_FOLDER") or Path(__file__).resolve().parent / "data" / "maps")


def display_name(map_id: str) -> str:
  return f"{map_id}-display.webp"


def thumbnail_name(map_id: str) -> str:
  return f"{map_id}-thumbnail.webp"


# --- checking what was typed ---------------------------------------------------------------------------------


def check_id(map_id: str) -> str:
  map_id = str(map_id or "").strip().lower()
  if not ID_PATTERN.match(map_id):
    raise MapProblem("The id must be 3 to 50 lowercase letters, digits and hyphens, such as pauls-first-journey.")
  return map_id


def _one_line(value) -> str:
  return " ".join(str(value or "").split())


def _book_names() -> dict[int, str]:
  with connect() as connection:
    return dict(connection.execute("SELECT number, name FROM books").fetchall())


def parse_verses(text: str) -> list[dict]:
  """The verses typed for a map, one by one: {book_number, chapter, verse, end_verse, label}.

  References are separated by semicolons, commas or new lines ("Acts 13:4-14; Acts 16:11"). Each must name a
  verse that exists (a range stays inside its chapter); anything else raises MapProblem naming it.
  """
  text = CONTROL_CHARACTERS.sub("", str(text or ""))
  if len(text) > VERSES_LIMIT:
    raise MapProblem(f"The verses can be at most {VERSES_LIMIT:,} characters.")
  limits = verse_limits()
  names = _book_names()
  verses, problems, last = [], [], 0
  for match in PATTERN.finditer(text):
    between = text[last:match.start()]
    last = match.end()
    if between.strip(" \t\r\n,;") and not re.fullmatch(r"[\s,;]*(and|&)?[\s,;]*", between):
      problems.append(between.strip(" \t\r\n,;"))
    name = match[1]
    # Typed by an administrator, so any case will do ("acts 13:4").
    book = BOOK_BY_NORMALIZED_NAME.get(normalize(name))
    chapter, verse = int(match[2]), int(match[3])
    end_verse = int(match[4]) if match[4] else None
    last_verse = limits.get((book, chapter), 0) if book else 0
    if book is None or not 1 <= verse <= last_verse or (end_verse is not None and not verse < end_verse <= last_verse):
      problems.append(match[0])
      continue
    label = f"{names.get(book, name)} {chapter}:{verse}" + (f"–{end_verse}" if end_verse else "")
    if not any(found["label"] == label for found in verses):
      verses.append({"book_number": book, "chapter": chapter, "verse": verse, "end_verse": end_verse, "label": label})
  rest = text[last:].strip(" \t\r\n,;.")
  if rest:
    problems.append(rest)
  if problems:
    shown = "; ".join(f"“{problem[:60]}”" for problem in problems[:5])
    raise MapProblem(
      f"These are not verses in the Bibles here: {shown}. Write each as a book, chapter and verse, such as "
      "Acts 13:4 or Acts 13:4-14, separated by semicolons."
    )
  if len(verses) > MAX_VERSES:
    raise MapProblem(f"A map can have at most {MAX_VERSES} verses.")
  return verses


def check_details(details: dict) -> dict:
  """The title, description, source, keywords and verses as typed, cleaned and checked. keywords is None when not
  given (the map's are kept), and so is verses."""
  title = _one_line(details.get("title"))
  source = _one_line(details.get("source"))
  description = CONTROL_CHARACTERS.sub("", str(details.get("description") or "")).replace("\r\n", "\n").replace("\r", "\n")
  description = re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in description.split("\n"))).strip()
  if not title:
    raise MapProblem("Fill in the title.")
  if len(title) > TITLE_LIMIT:
    raise MapProblem(f"The title can be at most {TITLE_LIMIT} characters.")
  if len(description) > DESCRIPTION_LIMIT:
    raise MapProblem(f"The description can be at most {DESCRIPTION_LIMIT:,} characters.")
  if len(source) > SOURCE_LIMIT:
    raise MapProblem(f"Where it came from can be at most {SOURCE_LIMIT} characters.")
  keywords = None if details.get("keywords") is None else _one_line(details.get("keywords"))
  if keywords is not None and len(keywords) > KEYWORDS_LIMIT:
    raise MapProblem(f"The keywords can be at most {KEYWORDS_LIMIT} characters.")
  verses = None if details.get("verses") is None else parse_verses(details.get("verses"))
  return {"title": title, "description": description, "source": source, "keywords": keywords, "verses": verses}


def check_file(path: Path, original_name: str) -> str:
  """The media type of an uploaded map, after checking it is a real picture or PDF of a size the site takes."""
  extension = Path(original_name).suffix.lower()
  if extension not in FILE_TYPES:
    raise MapProblem("The map must be a picture (.png, .jpg, .webp, .gif, .tif) or a PDF (.pdf).")
  size = path.stat().st_size
  if size == 0:
    raise MapProblem("The file is empty.")
  if size > MAX_FILE_BYTES:
    raise MapProblem(f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
  with open(path, "rb") as file:
    start = file.read(12)
  # What the first bytes say it is: a JPEG saved as .png is accepted and kept as what it is.
  found = None
  if start.startswith(b"%PDF-"):
    found = ".pdf"
  elif start.startswith(b"\x89PNG\r\n\x1a\n"):
    found = ".png"
  elif start.startswith(b"\xff\xd8\xff"):
    found = ".jpg"
  elif start[:4] == b"RIFF" and start[8:12] == b"WEBP":
    found = ".webp"
  elif start[:6] in (b"GIF87a", b"GIF89a"):
    found = ".gif"
  elif start[:4] in (b"II*\x00", b"MM\x00*"):
    found = ".tif"
  if found is None:
    raise MapProblem(f"The file is not a real {extension[1:].upper()} file (its contents do not match its name).")
  return found


# --- the pictures --------------------------------------------------------------------------------------------


def _open_picture(path: Path, extension: str, pdf_page: int):
  """The map as a Pillow picture: the file itself, or the page of a PDF drawn at the size shown on the site."""
  from PIL import Image

  Image.MAX_IMAGE_PIXELS = MAX_PIXELS
  if extension == ".pdf":
    import pypdfium2

    try:
      pdf = pypdfium2.PdfDocument(str(path))
    except pypdfium2.PdfiumError as error:
      raise MapProblem("The PDF could not be read (it may be damaged or locked with a password).") from error
    try:
      if not 1 <= pdf_page <= len(pdf):
        raise MapProblem(f"The PDF has {len(pdf)} page{'s' if len(pdf) != 1 else ''}; there is no page {pdf_page}.")
      page = pdf[pdf_page - 1]
      longest = max(page.get_width(), page.get_height()) or 792
      return page.render(scale=DISPLAY_LONGEST_SIDE / longest).to_pil()
    finally:
      pdf.close()
  try:
    picture = Image.open(path)
    picture.load()
  except Image.DecompressionBombError as error:
    raise MapProblem("The picture is too large (over 600 million pixels).") from error
  except (OSError, SyntaxError) as error:
    raise MapProblem("The picture could not be read (it may be damaged).") from error
  return picture


def _make_copies(path: Path, extension: str, map_id: str, pdf_page: int) -> tuple[int, int]:
  """Makes the WebP copy shown on the site and the small one for the list; returns the shown copy's size."""
  from PIL import Image, ImageOps

  picture = _open_picture(path, extension, pdf_page)
  picture = ImageOps.exif_transpose(picture)
  # Transparent parts (a PNG's) on white, as a map is printed.
  if picture.mode in ("RGBA", "LA", "P"):
    picture = picture.convert("RGBA")
    background = Image.new("RGB", picture.size, "white")
    background.paste(picture, mask=picture.getchannel("A"))
    picture = background
  else:
    picture = picture.convert("RGB")
  if max(picture.size) > DISPLAY_LONGEST_SIDE:
    picture.thumbnail((DISPLAY_LONGEST_SIDE, DISPLAY_LONGEST_SIDE), Image.Resampling.LANCZOS)
  folder = maps_folder()
  folder.mkdir(parents=True, exist_ok=True)
  for name, copy, quality in (
    (display_name(map_id), picture, 82),
    (thumbnail_name(map_id), picture.resize((THUMBNAIL_WIDTH, max(1, round(picture.height * THUMBNAIL_WIDTH / picture.width))), Image.Resampling.LANCZOS) if picture.width > THUMBNAIL_WIDTH else picture, 75),
  ):
    temporary = folder / f".{name}.new"
    copy.save(temporary, "WEBP", quality=quality, method=4)
    os.chmod(temporary, 0o644)
    os.replace(temporary, folder / name)
  return picture.width, picture.height


def _store(path: Path, file_name: str) -> None:
  """Copies the uploaded file into the maps folder under a temporary name, then renames it."""
  folder = maps_folder()
  try:
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f".{file_name}.new"
    shutil.copyfile(path, temporary)
    os.chmod(temporary, 0o644)
    os.replace(temporary, folder / file_name)
  except OSError as error:
    raise MapProblem(f"The file could not be saved in the maps folder ({folder}): {error.strerror}.") from error


# --- reading -------------------------------------------------------------------------------------------------

COLUMNS = (
  "id, title, description, source, keywords, verses, file_name, media_type, file_size, pdf_page, width, height, "
  "is_published, created_at, updated_at"
)


def _describe(row, verses: list[dict], for_admin: bool = False) -> dict:
  (map_id, title, description, source, keywords, verses_text, file_name, media_type, file_size, pdf_page, width,
   height, is_published, created_at, updated_at) = row
  found = {
    "id": map_id,
    "title": title,
    "description": description,
    "source": source,
    "keywords": keywords,
    "verses_text": verses_text,
    "verses": verses,
    "kind": "pdf" if media_type == "application/pdf" else "image",
    "file_type": Path(file_name).suffix[1:].upper(),
    "file_size": file_size,
    "pdf_page": pdf_page,
    "width": width,
    "height": height,
    "is_published": is_published,
    "created_at": created_at.isoformat(),
    "updated_at": updated_at.isoformat(),
    # Changes when the picture is replaced, so the page asks for the new one (the copies are cached a month).
    "version": int(updated_at.timestamp()),
  }
  if for_admin:
    folder = maps_folder()
    found["file_name"] = file_name
    found["file_present"] = (folder / file_name).is_file() and (folder / display_name(map_id)).is_file()
  return found


def _verses_of(connection, map_ids: list[str]) -> dict[str, list[dict]]:
  verses: dict[str, list[dict]] = {map_id: [] for map_id in map_ids}
  if not map_ids:
    return verses
  rows = connection.execute(
    "SELECT map_id, book_number, chapter, verse, end_verse, label FROM map_verses WHERE map_id = ANY(%s) ORDER BY map_id, position",
    (map_ids,),
  ).fetchall()
  for map_id, book, chapter, verse, end_verse, label in rows:
    verses[map_id].append({"book_number": book, "chapter": chapter, "verse": verse, "end_verse": end_verse, "label": label})
  return verses


def list_maps(published_only: bool = True, book: int | None = None, chapter: int | None = None, verse: int | None = None) -> list[dict]:
  """The maps by title; for the admin page also the hidden ones. With a verse, only the maps linked to it (a
  verse inside a linked range counts)."""
  conditions, values = [], []
  if published_only:
    conditions.append("is_published")
  if book is not None and chapter is not None and verse is not None:
    conditions.append(
      "EXISTS (SELECT 1 FROM map_verses v WHERE v.map_id = maps.id AND v.book_number = %s AND v.chapter = %s "
      "AND %s BETWEEN v.verse AND COALESCE(v.end_verse, v.verse))"
    )
    values += [book, chapter, verse]
  where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
  with connect() as connection:
    rows = connection.execute(f"SELECT {COLUMNS} FROM maps {where} ORDER BY lower(title), id", values).fetchall()
    verses = _verses_of(connection, [row[0] for row in rows])
  return [_describe(row, verses[row[0]], for_admin=not published_only) for row in rows]


def get_map(map_id: str, published_only: bool = True) -> dict | None:
  condition = "AND is_published" if published_only else ""
  with connect() as connection:
    row = connection.execute(f"SELECT {COLUMNS} FROM maps WHERE id = %s {condition}", (map_id,)).fetchone()
    if row is None:
      return None
    verses = _verses_of(connection, [map_id])[map_id]
  found = _describe(row, verses, for_admin=not published_only)
  if not published_only:
    with connect() as connection:
      found["mark_count"] = connection.execute("SELECT count(*) FROM map_marks WHERE map_id = %s", (map_id,)).fetchone()[0]
  return found


def map_file(map_id: str, which: str) -> tuple[Path, str] | None:
  """A published map's picture: "display" (the WebP shown) or "thumbnail", with its media type; None when the map
  is not published or the file is missing. The file as uploaded is kept but never served."""
  if which not in ("display", "thumbnail"):
    return None
  with connect() as connection:
    row = connection.execute("SELECT 1 FROM maps WHERE id = %s AND is_published", (map_id,)).fetchone()
  if row is None:
    return None
  path = maps_folder() / (display_name(map_id) if which == "display" else thumbnail_name(map_id))
  return (path, "image/webp") if path.is_file() else None


# --- saving --------------------------------------------------------------------------------------------------


def _save_verses(connection, map_id: str, verses: list[dict]) -> None:
  connection.execute("DELETE FROM map_verses WHERE map_id = %s", (map_id,))
  for position, verse in enumerate(verses, start=1):
    connection.execute(
      "INSERT INTO map_verses (map_id, position, book_number, chapter, verse, end_verse, label) VALUES (%s, %s, %s, %s, %s, %s, %s)",
      (map_id, position, verse["book_number"], verse["chapter"], verse["verse"], verse["end_verse"], verse["label"]),
    )


def _verses_text(verses: list[dict]) -> str:
  return "; ".join(verse["label"] for verse in verses)


def upload(path: Path, original_name: str, map_id: str, details: dict, pdf_page: int = 1) -> dict:
  """Saves a map: its file into the maps folder (with the copies made from it) and its details into the table.

  A new map is hidden until published; one already there keeps its state and gets the new file and details.
  The keywords and the verses are kept as they were when not given.
  """
  map_id = check_id(map_id)
  extension = check_file(path, original_name)
  checked = check_details(details)
  if extension != ".pdf":
    pdf_page = None
  elif not isinstance(pdf_page, int) or pdf_page < 1:
    raise MapProblem("The page of the PDF must be a number from 1.")
  width, height = _make_copies(path, extension, map_id, pdf_page or 1)
  file_name = map_id + extension
  _store(path, file_name)
  size = (maps_folder() / file_name).stat().st_size
  verses_text = None if checked["verses"] is None else _verses_text(checked["verses"])
  with connect() as connection:
    old = connection.execute("SELECT file_name FROM maps WHERE id = %s", (map_id,)).fetchone()
    connection.execute(
      """
      INSERT INTO maps (id, title, description, source, keywords, verses, file_name, media_type, file_size, pdf_page, width, height)
      VALUES (%s, %s, %s, %s, COALESCE(%s, ''), COALESCE(%s, ''), %s, %s, %s, %s, %s, %s)
      ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, description = EXCLUDED.description,
        source = EXCLUDED.source, keywords = COALESCE(%s, maps.keywords), verses = COALESCE(%s, maps.verses),
        file_name = EXCLUDED.file_name, media_type = EXCLUDED.media_type, file_size = EXCLUDED.file_size,
        pdf_page = EXCLUDED.pdf_page, width = EXCLUDED.width, height = EXCLUDED.height, updated_at = now()
      """,
      (map_id, checked["title"], checked["description"], checked["source"], checked["keywords"], verses_text,
       file_name, FILE_TYPES[extension], size, pdf_page, width, height, checked["keywords"], verses_text),
    )
    if checked["verses"] is not None:
      _save_verses(connection, map_id, checked["verses"])
  # A PNG replaced by a PDF (or the like) leaves the old file behind; remove it.
  if old and old[0] != file_name:
    (maps_folder() / old[0]).unlink(missing_ok=True)
  return get_map(map_id, published_only=False)


def update_details(map_id: str, details: dict, pdf_page: int | None = None) -> dict:
  """Changes a map's title, description, source, keywords and verses (those given); its picture stays, unless a
  different page of its PDF is chosen, which is drawn again."""
  checked = check_details(details)
  current = get_map(map_id, published_only=False)
  if current is None:
    raise MapProblem("That map does not exist (it may have been deleted).")
  if pdf_page is not None and current["kind"] == "pdf" and pdf_page != current["pdf_page"]:
    width, height = _make_copies(maps_folder() / current["file_name"], ".pdf", map_id, pdf_page)
  else:
    pdf_page, width, height = current["pdf_page"], current["width"], current["height"]
  verses_text = None if checked["verses"] is None else _verses_text(checked["verses"])
  with connect() as connection:
    connection.execute(
      """
      UPDATE maps SET title = %s, description = %s, source = %s, keywords = COALESCE(%s, keywords),
        verses = COALESCE(%s, verses), pdf_page = %s, width = %s, height = %s, updated_at = now()
      WHERE id = %s
      """,
      (checked["title"], checked["description"], checked["source"], checked["keywords"], verses_text, pdf_page,
       width, height, map_id),
    )
    if checked["verses"] is not None:
      _save_verses(connection, map_id, checked["verses"])
  return get_map(map_id, published_only=False)


def set_published(map_id: str, published: bool) -> dict:
  with connect() as connection:
    changed = connection.execute("UPDATE maps SET is_published = %s WHERE id = %s RETURNING id", (published, map_id)).fetchone()
  if changed is None:
    raise MapProblem("That map does not exist (it may have been deleted).")
  return get_map(map_id, published_only=False)


def delete(map_id: str) -> dict:
  """Deletes a map with its files, its verses and every member's notes, pins and routes on it."""
  found = get_map(map_id, published_only=False)
  if found is None:
    raise MapProblem("That map does not exist (it may have been deleted).")
  with connect() as connection:
    connection.execute("DELETE FROM maps WHERE id = %s", (map_id,))
  for name in (found["file_name"], display_name(map_id), thumbnail_name(map_id)):
    (maps_folder() / name).unlink(missing_ok=True)
  return found


# --- searching -----------------------------------------------------------------------------------------------


def search_maps(query: str, match_mode: str, page: int, per_page: int) -> dict:
  """Search the published maps' titles, keywords, descriptions, verses and sources, best match first.

  The same matching as the songs (words in any form, all words, any word or an exact phrase). A query that names a
  verse ("Acts 13:4") also finds the maps linked to that verse, first. Each result has an excerpt of the
  description (or the title), with the words found wrapped in \\u0001 and \\u0002.
  """
  named = parse_query_verses(query)
  terms = parse_terms(query, match_mode)
  if not terms and not named:
    raise ValueError("Enter at least one word or phrase to search for.")
  joiner = " || " if match_mode == "any" else " && "
  tsquery = joiner.join(["phraseto_tsquery('commentary_english', %s)"] * len(terms)) if terms else "''::tsquery"
  verse_match = " OR ".join(
    ["EXISTS (SELECT 1 FROM map_verses v WHERE v.map_id = maps.id AND v.book_number = %s AND v.chapter = %s "
     "AND %s BETWEEN v.verse AND COALESCE(v.end_verse, v.verse))"] * len(named)
  ) or "false"
  verse_values = [value for verse in named for value in verse]
  condition = f"is_published AND ((search_vector @@ ({tsquery})) OR {verse_match})"
  # Maps linked to a verse the query names come first (ORDER BY cannot take a bare false).
  order_by = f"({verse_match}) DESC, " if named else ""
  values = [*terms, *verse_values]
  with connect() as connection:
    total = connection.execute(f"SELECT count(*) FROM maps WHERE {condition}", values).fetchone()[0]
    rows = connection.execute(
      f"""
      SELECT id, title, verses, width, height, updated_at,
        ts_headline('commentary_english', CASE WHEN description = '' THEN title ELSE description END, ({tsquery}), %s)
      FROM maps
      WHERE {condition}
      ORDER BY {order_by}ts_rank_cd(search_vector, ({tsquery}), 1) DESC, lower(title)
      LIMIT %s OFFSET %s
      """,
      [*terms, HEADLINE_OPTIONS, *values, *(verse_values if named else []), *terms, per_page, (page - 1) * per_page],
    ).fetchall()
  return {
    "query": query,
    "terms": terms,
    "total": total,
    "page": page,
    "per_page": per_page,
    "results": [
      {"id": map_id, "title": title, "verses_text": verses_text, "width": width, "height": height,
       "version": int(updated_at.timestamp()), "text": excerpt}
      for map_id, title, verses_text, width, height, updated_at, excerpt in rows
    ],
  }


def parse_query_verses(query: str) -> list[tuple[int, int, int]]:
  """The verses a search names ("Acts 13:4"), as (book, chapter, verse); the first verse of a range."""
  limits = verse_limits()
  found = []
  for match in PATTERN.finditer(query):
    book = BOOK_BY_NORMALIZED_NAME.get(normalize(match[1]))
    chapter, verse = int(match[2]), int(match[3])
    if book and 1 <= verse <= limits.get((book, chapter), 0):
      found.append((book, chapter, verse))
  return found[:10]

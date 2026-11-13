"""The Christian music section: songs with an MP3 or MP4 file, a title, an author and the words.

The words can also be given as a PDF or a picture (a scan of the hymnal page, say), kept beside the song as
"<id>-words.pdf" (or .png, .jpg, .webp, .gif); the music page then shows that file in place of the typed words,
which stay for the search.

The files are kept in the music folder set on the Drupal Site settings screen (service_settings
"music_folder"; ml-service/data/music until it is set), named after the song's id ("amazing-grace.mp4"), and
never in the database; the music_tracks table (migration 023) holds the rest. The site serves the files
itself (GET /music/{id}/file), so the folder can be moved, for example to a bigger volume, by copying the
files there and changing the setting: no server configuration names it.

The Drupal "Christian music" page manages the songs through scripts/manage_music.py: upload (a new song is
hidden until published; uploading again with the same id replaces its file and details and keeps its
state), change the details, publish, hide and delete (which removes the file too).
"""

import os
import re
import shutil
from pathlib import Path

from commentaries import HEADLINE_OPTIONS
from search import connect, parse_terms
from service_settings import get_setting

MAX_FILE_BYTES = 1024 * 1024 * 1024  # 1 GB: a recorded talk on video runs to 600 MB
TITLE_LIMIT = 200
AUTHOR_LIMIT = 200
# Characters of words: a song's, or a sermon's transcript (the owner's Road to Recovery sermons run to 34,000).
LYRICS_LIMIT = 100_000
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
MEDIA_TYPES = {".mp3": "audio/mpeg", ".mp4": "video/mp4"}
MAX_WORDS_BYTES = 20 * 1024 * 1024
# The words file: a PDF or a picture (no SVG: it can carry scripts). .jpeg is kept as .jpg.
WORDS_TYPES = {
  ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".webp": "image/webp", ".gif": "image/gif",
}
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class MusicProblem(Exception):
  """A song cannot be saved or changed; the text says why and is fit to show the administrator."""


def music_folder() -> Path:
  return Path(get_setting("music_folder"))


def file_path(file_name: str) -> Path:
  return music_folder() / file_name


def check_file(path: Path, original_name: str) -> str:
  """The media type of an uploaded file, after checking it is a real MP3 or MP4 of a size the site takes."""
  extension = Path(original_name).suffix.lower()
  if extension not in MEDIA_TYPES:
    raise MusicProblem("The file must be an MP3 (.mp3) or an MP4 (.mp4).")
  size = path.stat().st_size
  if size == 0:
    raise MusicProblem("The file is empty.")
  if size > MAX_FILE_BYTES:
    raise MusicProblem(f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
  with open(path, "rb") as file:
    start = file.read(12)
  if extension == ".mp3":
    # An ID3 tag, or straight into an MPEG audio frame (eleven bits set).
    looks_right = start[:3] == b"ID3" or (len(start) >= 2 and start[0] == 0xFF and start[1] & 0xE0 == 0xE0)
  else:
    looks_right = start[4:8] == b"ftyp"
  if not looks_right:
    raise MusicProblem(f"The file is not a real {extension[1:].upper()} file (its contents do not match its name).")
  return MEDIA_TYPES[extension]


def check_words_file(path: Path, original_name: str) -> tuple[str, str]:
  """(media type, extension) of a words file, after checking it is a real PDF or picture of a size the site takes."""
  extension = Path(original_name).suffix.lower()
  if extension not in WORDS_TYPES:
    raise MusicProblem("The words file must be a PDF (.pdf) or a picture (.png, .jpg, .webp or .gif).")
  size = path.stat().st_size
  if size == 0:
    raise MusicProblem("The words file is empty.")
  if size > MAX_WORDS_BYTES:
    raise MusicProblem(f"The words file is larger than {MAX_WORDS_BYTES // (1024 * 1024)} MB.")
  with open(path, "rb") as file:
    start = file.read(12)
  looks_right = {
    ".pdf": start.startswith(b"%PDF-"),
    ".png": start.startswith(b"\x89PNG\r\n\x1a\n"),
    ".jpg": start.startswith(b"\xff\xd8\xff"),
    ".jpeg": start.startswith(b"\xff\xd8\xff"),
    ".webp": start[:4] == b"RIFF" and start[8:12] == b"WEBP",
    ".gif": start[:6] in (b"GIF87a", b"GIF89a"),
  }[extension]
  if not looks_right:
    raise MusicProblem(f"The words file is not a real {extension[1:].upper()} file (its contents do not match its name).")
  return WORDS_TYPES[extension], ".jpg" if extension == ".jpeg" else extension


def _store(path: Path, file_name: str) -> None:
  """Copies a file into the music folder under a temporary name, then renames it, so a failed copy never
  leaves half a file in place."""
  folder = music_folder()
  try:
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f".{file_name}.new"
    shutil.copyfile(path, temporary)
    os.chmod(temporary, 0o644)
    os.replace(temporary, folder / file_name)
  except OSError as error:
    raise MusicProblem(f"The file could not be saved in the music folder ({folder}): {error.strerror}.") from error


def check_details(details: dict) -> dict:
  """The title, author and words as typed, cleaned; raises MusicProblem when one is wrong."""
  def one_line(value) -> str:
    return " ".join(str(value or "").split())

  title = one_line(details.get("title"))
  author = one_line(details.get("author"))
  lyrics = CONTROL_CHARACTERS.sub("", str(details.get("lyrics") or "")).replace("\r\n", "\n").replace("\r", "\n")
  lyrics = re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in lyrics.split("\n"))).strip()
  if not title:
    raise MusicProblem("Fill in the title.")
  if len(title) > TITLE_LIMIT:
    raise MusicProblem(f"The title can be at most {TITLE_LIMIT} characters.")
  if len(author) > AUTHOR_LIMIT:
    raise MusicProblem(f"The author can be at most {AUTHOR_LIMIT} characters.")
  if len(lyrics) > LYRICS_LIMIT:
    raise MusicProblem(f"The words can be at most {LYRICS_LIMIT:,} characters.")
  return {"title": title, "author": author, "lyrics": lyrics}


def check_id(song_id: str) -> str:
  song_id = str(song_id or "").strip().lower()
  if not ID_PATTERN.match(song_id):
    raise MusicProblem("The id must be 3 to 50 lowercase letters, digits and hyphens, such as amazing-grace.")
  return song_id


COLUMNS = (
  "id, title, author, lyrics, file_name, media_type, file_size, is_published, created_at, updated_at, "
  "words_file_name, words_media_type, lyrics_html"
)


def _describe(row, with_file_check: bool = False) -> dict:
  (song_id, title, author, lyrics, file_name, media_type, file_size, is_published, created_at, updated_at,
   words_file_name, words_media_type, lyrics_html) = row
  song = {
    "id": song_id,
    "title": title,
    "author": author,
    "lyrics": lyrics,
    # The words with their formatting, from a PDF or Word document (set_words_from_document); None otherwise.
    "lyrics_html": lyrics_html,
    "media_type": media_type,
    "kind": "video" if media_type == "video/mp4" else "audio",
    "file_size": file_size,
    "is_published": is_published,
    "created_at": created_at.isoformat(),
    "updated_at": updated_at.isoformat(),
    # Changes when a file is replaced, so the page can ask for the new one (the files are cached for a month).
    "version": int(updated_at.timestamp()),
    # The words as a file: "pdf" or "image", shown in place of the typed words; None when there is none.
    "words_kind": None if words_media_type is None else ("pdf" if words_media_type == "application/pdf" else "image"),
  }
  if with_file_check:
    song["file_name"] = file_name
    song["file_present"] = file_path(file_name).is_file()
    song["words_file_name"] = words_file_name
    song["words_file_present"] = words_file_name is not None and file_path(words_file_name).is_file()
  return song


def list_songs(published_only: bool = True) -> list[dict]:
  """The songs by title; for the admin page also the hidden ones, with whether each file is in the folder."""
  condition = "WHERE is_published" if published_only else ""
  with connect() as connection:
    rows = connection.execute(f"SELECT {COLUMNS} FROM music_tracks {condition} ORDER BY lower(title), id").fetchall()
  return [_describe(row, with_file_check=not published_only) for row in rows]


def get_song(song_id: str, published_only: bool = True) -> dict | None:
  condition = "AND is_published" if published_only else ""
  with connect() as connection:
    row = connection.execute(f"SELECT {COLUMNS} FROM music_tracks WHERE id = %s {condition}", (song_id,)).fetchone()
  return _describe(row, with_file_check=not published_only) if row else None


def song_file(song_id: str) -> tuple[Path, str] | None:
  """The file of a published song and its media type, or None (not published, or the file is missing)."""
  with connect() as connection:
    row = connection.execute(
      "SELECT file_name, media_type FROM music_tracks WHERE id = %s AND is_published", (song_id,)
    ).fetchone()
  if row is None:
    return None
  path = file_path(row[0])
  return (path, row[1]) if path.is_file() else None


def song_words_file(song_id: str) -> tuple[Path, str] | None:
  """The words file (PDF or picture) of a published song and its media type, or None."""
  with connect() as connection:
    row = connection.execute(
      "SELECT words_file_name, words_media_type FROM music_tracks WHERE id = %s AND is_published AND words_file_name IS NOT NULL",
      (song_id,),
    ).fetchone()
  if row is None:
    return None
  path = file_path(row[0])
  return (path, row[1]) if path.is_file() else None


def _change_words(song_id: str, words: tuple[Path, str] | None, remove_words: bool) -> None:
  """Puts a new words file in place of the old one, or removes it. Does nothing when neither is asked."""
  if words is None and not remove_words:
    return
  new_name, new_type = None, None
  if words is not None:
    new_type, extension = check_words_file(*words)
    new_name = f"{song_id}-words{extension}"
    _store(words[0], new_name)
  with connect() as connection:
    old = connection.execute("SELECT words_file_name FROM music_tracks WHERE id = %s", (song_id,)).fetchone()
    connection.execute(
      "UPDATE music_tracks SET words_file_name = %s, words_media_type = %s, updated_at = now() WHERE id = %s",
      (new_name, new_type, song_id),
    )
  if old and old[0] and old[0] != new_name:
    file_path(old[0]).unlink(missing_ok=True)


def upload(path: Path, original_name: str, song_id: str, details: dict, words: tuple[Path, str] | None = None) -> dict:
  """Saves a song: its file into the music folder and its details into the table.

  A new song is hidden until published; one already there keeps its state and gets the new file and details.
  words, when given, is (path, original name) of a PDF or picture of the words (see _change_words); a words
  file already there is kept otherwise.
  """
  song_id = check_id(song_id)
  media_type = check_file(path, original_name)
  checked = check_details(details)
  if words is not None:
    check_words_file(*words)
  file_name = song_id + Path(original_name).suffix.lower()
  _store(path, file_name)
  size = file_path(file_name).stat().st_size
  with connect() as connection:
    old = connection.execute("SELECT file_name FROM music_tracks WHERE id = %s", (song_id,)).fetchone()
    row = connection.execute(
      f"""
      INSERT INTO music_tracks (id, title, author, lyrics, file_name, media_type, file_size)
      VALUES (%s, %s, %s, %s, %s, %s, %s)
      ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, author = EXCLUDED.author, lyrics = EXCLUDED.lyrics,
        file_name = EXCLUDED.file_name, media_type = EXCLUDED.media_type, file_size = EXCLUDED.file_size,
        updated_at = now()
      RETURNING {COLUMNS}
      """,
      (song_id, checked["title"], checked["author"], checked["lyrics"], file_name, media_type, size),
    ).fetchone()
  # An MP3 replaced by an MP4 (or the other way round) leaves the old file behind; remove it.
  if old and old[0] != file_name:
    file_path(old[0]).unlink(missing_ok=True)
  if words is not None:
    _change_words(song_id, words, False)
    return get_song(song_id, published_only=False)
  return _describe(row, with_file_check=True)


def update_details(song_id: str, details: dict, words: tuple[Path, str] | None = None, remove_words: bool = False) -> dict:
  """Changes a song's title, author and words, and its words file when one is given or removed; the song's
  own file stays."""
  checked = check_details(details)
  if words is not None:
    check_words_file(*words)
  with connect() as connection:
    row = connection.execute(
      f"""
      UPDATE music_tracks SET title = %s, author = %s, lyrics = %s, updated_at = now(),
        lyrics_html = CASE WHEN lyrics = %s THEN lyrics_html END
      WHERE id = %s RETURNING {COLUMNS}
      """,
      (checked["title"], checked["author"], checked["lyrics"], checked["lyrics"], song_id),
    ).fetchone()
  if row is None:
    raise MusicProblem("That song does not exist (it may have been deleted).")
  if words is not None or remove_words:
    _change_words(song_id, words, remove_words)
    return get_song(song_id, published_only=False)
  return _describe(row, with_file_check=True)


def set_words_from_document(song_id: str, path: Path, original_name: str) -> dict:
  """Sets a song's words from a PDF or Word document, keeping their formatting (document_import.py); the plain
  text replaces the typed words, so the music search finds them."""
  from document_import import DocumentProblem, convert, save_images
  from document_split import whole_document

  try:
    document = convert(path, original_name)
  except DocumentProblem as problem:
    raise MusicProblem(str(problem)) from problem
  piece = whole_document(document)
  if piece is None:
    raise MusicProblem("No words were found in the document.")
  if len(piece.text) > LYRICS_LIMIT:
    raise MusicProblem(f"The words can be at most {LYRICS_LIMIT:,} characters.")
  save_images(document.images)
  with connect() as connection:
    row = connection.execute(
      f"UPDATE music_tracks SET lyrics = %s, lyrics_html = %s, updated_at = now() WHERE id = %s RETURNING {COLUMNS}",
      (piece.text, piece.html, song_id),
    ).fetchone()
  if row is None:
    raise MusicProblem("That song does not exist (it may have been deleted).")
  return _describe(row, with_file_check=True)


def set_published(song_id: str, published: bool) -> dict:
  with connect() as connection:
    row = connection.execute(
      f"UPDATE music_tracks SET is_published = %s WHERE id = %s RETURNING {COLUMNS}", (published, song_id)
    ).fetchone()
  if row is None:
    raise MusicProblem("That song does not exist (it may have been deleted).")
  return _describe(row, with_file_check=True)


def delete(song_id: str) -> dict:
  """Deletes a song, its file and its words file."""
  with connect() as connection:
    row = connection.execute(f"DELETE FROM music_tracks WHERE id = %s RETURNING {COLUMNS}", (song_id,)).fetchone()
  if row is None:
    raise MusicProblem("That song does not exist (it may have been deleted).")
  song = _describe(row, with_file_check=True)
  file_path(song["file_name"]).unlink(missing_ok=True)
  if song["words_file_name"]:
    file_path(song["words_file_name"]).unlink(missing_ok=True)
  return song


def search_music(query: str, match_mode: str, page: int, per_page: int) -> dict:
  """Search the published songs' titles, authors and words, best match first.

  The same matching as the Other books (words in any form, all words, any word or an exact phrase). Each
  result has an excerpt of the words (or the title, for a song without words), with the words found
  wrapped in \\u0001 and \\u0002.
  """
  terms = parse_terms(query, match_mode)
  if not terms:
    raise ValueError("Enter at least one word or phrase to search for.")
  joiner = " || " if match_mode == "any" else " && "
  tsquery = joiner.join(["phraseto_tsquery('commentary_english', %s)"] * len(terms))
  with connect() as connection:
    if connection.execute(f"SELECT numnode({tsquery})", terms).fetchone()[0] == 0:
      raise ValueError("Enter at least one word or phrase to search for.")
    condition = f"is_published AND search_vector @@ ({tsquery})"
    total = connection.execute(f"SELECT count(*) FROM music_tracks WHERE {condition}", terms).fetchone()[0]
    rows = connection.execute(
      f"""
      SELECT id, title, author, media_type,
        ts_headline('commentary_english', CASE WHEN lyrics = '' THEN title ELSE lyrics END, ({tsquery}), %s)
      FROM music_tracks
      WHERE {condition}
      ORDER BY ts_rank_cd(search_vector, ({tsquery}), 1) DESC, lower(title)
      LIMIT %s OFFSET %s
      """,
      [*terms, HEADLINE_OPTIONS, *terms, *terms, per_page, (page - 1) * per_page],
    ).fetchall()
  return {
    "query": query,
    "terms": terms,
    "total": total,
    "page": page,
    "per_page": per_page,
    "results": [
      {"id": song_id, "title": title, "author": author, "kind": "video" if media_type == "video/mp4" else "audio", "text": excerpt}
      for song_id, title, author, media_type, excerpt in rows
    ],
  }

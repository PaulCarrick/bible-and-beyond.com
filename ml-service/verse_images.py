"""Pictures for the verse a day (added 2026-11-16 at the owner's request).

An administrator uploads pictures on the Drupal "Verse a day pictures" page (scripts/manage_verse_images.py),
one or many at a time. They are not shown on the site. A later "Send Multimedia Messages" choice on the
account will send the verse a day as a picture message with the verse written over one of them, chosen at
random from those in use (random_image).

Each picture is kept as uploaded in the verse images folder (VERSE_IMAGES_FOLDER, ml-service/data/verse-images
until set), never in the database, as "<id><extension>", with a small WebP copy for the admin list
("<id>-thumbnail.webp"). The verse_images table (migration 042) holds the rest. A new picture is in use at once;
"Take out of use" keeps it but leaves it out of the random choice. The file type is what the first bytes say,
so a JPEG saved as .png is accepted and kept as a JPEG.
"""

import base64
import os
import random
import re
import shutil
from pathlib import Path

from search import connect

MAX_FILE_BYTES = 25 * 1024 * 1024
# Pillow's own safeguard is about 90 million pixels; a photograph is far below this.
MAX_PIXELS = 100_000_000
THUMBNAIL_WIDTH = 240
TITLE_LIMIT = 200
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
# The extensions taken, and the media type of each kind found in the file.
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class ImageProblem(Exception):
  """A picture cannot be saved or changed; the text says why and is fit to show the administrator."""


def images_folder() -> Path:
  return Path(os.environ.get("VERSE_IMAGES_FOLDER") or Path(__file__).resolve().parent / "data" / "verse-images")


def thumbnail_name(image_id: str) -> str:
  return f"{image_id}-thumbnail.webp"


def check_id(image_id: str) -> str:
  if not ID_PATTERN.match(image_id or ""):
    raise ImageProblem("The id must be 3 to 50 lower-case letters, digits and hyphens, starting and ending with a letter or digit.")
  return image_id


def check_title(title: str) -> str:
  title = " ".join((title or "").split())
  if not title:
    raise ImageProblem("The picture needs a name.")
  if CONTROL_CHARACTERS.search(title):
    raise ImageProblem("The name must be plain text on one line.")
  return title[:TITLE_LIMIT]


def check_file(path: Path, original_name: str) -> str:
  """The extension the picture really has (.png, .jpg or .webp), after checking its name, size and first bytes."""
  extension = Path(original_name).suffix.lower()
  if extension not in EXTENSIONS:
    raise ImageProblem("The picture must be a PNG, JPEG or WebP file (.png, .jpg, .jpeg, .webp).")
  size = path.stat().st_size
  if size == 0:
    raise ImageProblem("The file is empty.")
  if size > MAX_FILE_BYTES:
    raise ImageProblem(f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
  with open(path, "rb") as file:
    start = file.read(12)
  if start.startswith(b"\x89PNG\r\n\x1a\n"):
    return ".png"
  if start.startswith(b"\xff\xd8\xff"):
    return ".jpg"
  if start[:4] == b"RIFF" and start[8:12] == b"WEBP":
    return ".webp"
  raise ImageProblem(f"The file is not a real {extension[1:].upper()} picture (its contents do not match its name).")


def _replace(folder: Path, name: str, write) -> None:
  """Writes a file under a temporary name, then renames it, so a half-written file is never used."""
  temporary = folder / f".{name}.new"
  write(temporary)
  os.chmod(temporary, 0o644)
  os.replace(temporary, folder / name)


def _store(path: Path, image_id: str, extension: str) -> tuple[int, int]:
  """Copies the picture into the folder and makes its thumbnail. Returns its width and height."""
  from PIL import Image, ImageOps

  Image.MAX_IMAGE_PIXELS = MAX_PIXELS
  try:
    picture = Image.open(path)
    picture.load()
  except Image.DecompressionBombError as error:
    raise ImageProblem("The picture is too large (over 100 million pixels).") from error
  except (OSError, SyntaxError) as error:
    raise ImageProblem("The picture could not be read (it may be damaged).") from error
  # Turned the way the camera says, for the size and the thumbnail (the file itself is kept as uploaded).
  picture = ImageOps.exif_transpose(picture)
  width, height = picture.size
  thumbnail = picture.convert("RGB")
  thumbnail.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 4), Image.Resampling.LANCZOS)
  folder = images_folder()
  try:
    folder.mkdir(parents=True, exist_ok=True)
    _replace(folder, image_id + extension, lambda temporary: shutil.copyfile(path, temporary))
    _replace(folder, thumbnail_name(image_id), lambda temporary: thumbnail.save(temporary, "WEBP", quality=75))
  except OSError as error:
    raise ImageProblem(f"The picture could not be saved in the verse images folder ({folder}): {error.strerror}.") from error
  return width, height


COLUMNS = "id, title, file_name, media_type, file_size, width, height, in_use, created_at"


def _describe(row, with_thumbnail: bool = False) -> dict:
  image = {
    "id": row[0],
    "title": row[1],
    "file_name": row[2],
    "media_type": row[3],
    "file_size": row[4],
    "width": row[5],
    "height": row[6],
    "in_use": row[7],
    "created_at": row[8].isoformat(),
    "file_present": (images_folder() / row[2]).is_file(),
  }
  if with_thumbnail:
    thumbnail = images_folder() / thumbnail_name(row[0])
    image["thumbnail"] = (
      "data:image/webp;base64," + base64.b64encode(thumbnail.read_bytes()).decode() if thumbnail.is_file() else None
    )
  return image


def list_images(with_thumbnails: bool = False) -> list[dict]:
  """Every picture, newest first."""
  with connect() as connection:
    rows = connection.execute(f"SELECT {COLUMNS} FROM verse_images ORDER BY created_at DESC, id").fetchall()
  return [_describe(row, with_thumbnails) for row in rows]


def get_image(image_id: str) -> dict | None:
  with connect() as connection:
    row = connection.execute(f"SELECT {COLUMNS} FROM verse_images WHERE id = %s", (image_id,)).fetchone()
  return _describe(row) if row else None


def upload(path: Path, original_name: str, image_id: str, title: str) -> dict:
  """Saves a new picture, in use at once. An id already in use is refused (delete the old one first)."""
  check_id(image_id)
  title = check_title(title)
  extension = check_file(path, original_name)
  if get_image(image_id) is not None:
    raise ImageProblem(f"There is already a picture with the id “{image_id}”.")
  width, height = _store(path, image_id, extension)
  with connect() as connection:
    connection.execute(
      """
      INSERT INTO verse_images (id, title, file_name, media_type, file_size, width, height)
      VALUES (%s, %s, %s, %s, %s, %s, %s)
      """,
      (image_id, title, image_id + extension, MEDIA_TYPES[extension], path.stat().st_size, width, height),
    )
  return get_image(image_id)


def set_in_use(image_id: str, in_use: bool) -> dict:
  with connect() as connection:
    changed = connection.execute("UPDATE verse_images SET in_use = %s WHERE id = %s RETURNING id", (in_use, image_id)).fetchone()
  if changed is None:
    raise ImageProblem("That picture does not exist (it may have been deleted).")
  return get_image(image_id)


PREVIEW_SIZE = 1600


def preview(image_id: str) -> dict:
  """The picture with a larger copy (at most PREVIEW_SIZE pixels on its longer side, WebP) as a data: address, for
  the enlarged view on the Drupal page. Made from the file each time and never kept or served: the pictures are not
  public."""
  found = get_image(image_id)
  if found is None:
    raise ImageProblem("That picture does not exist (it may have been deleted).")
  path = images_folder() / found["file_name"]
  if not path.is_file():
    raise ImageProblem("The picture's file is missing from the verse images folder.")
  from io import BytesIO

  from PIL import Image, ImageOps

  with Image.open(path) as opened:
    picture = ImageOps.exif_transpose(opened).convert("RGB")
  picture.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE), Image.LANCZOS)
  buffer = BytesIO()
  picture.save(buffer, "WEBP", quality=82)
  found["preview"] = "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode()
  return found


def rename(image_id: str, title: str) -> dict:
  """Changes a picture's name (its title); the id and the files stay as they are."""
  title = check_title(title)
  with connect() as connection:
    changed = connection.execute("UPDATE verse_images SET title = %s WHERE id = %s RETURNING id", (title, image_id)).fetchone()
  if changed is None:
    raise ImageProblem("That picture does not exist (it may have been deleted).")
  return get_image(image_id)


def delete(image_id: str) -> dict:
  """Deletes a picture and its files."""
  found = get_image(image_id)
  if found is None:
    raise ImageProblem("That picture does not exist (it may have been deleted).")
  with connect() as connection:
    connection.execute("DELETE FROM verse_images WHERE id = %s", (image_id,))
  for name in (found["file_name"], thumbnail_name(image_id)):
    (images_folder() / name).unlink(missing_ok=True)
  return found


def random_image(chooser=random) -> tuple[dict, Path] | None:
  """A picture in use, chosen at random, with the path of its file; None when there is none. For the picture
  messages to come: nothing calls it yet."""
  images = [image for image in list_images() if image["in_use"] and image["file_present"]]
  if not images:
    return None
  image = chooser.choice(images)
  return image, images_folder() / image["file_name"]

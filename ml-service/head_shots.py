"""Members' head shots (added 2026-11-23 at the owner's request): a picture uploaded on My account and shown in the
account icon at the top right of the site.

The picture is read with Pillow, turned the way the camera meant (EXIF), cut to a square from its middle, made
SIZE pixels wide and saved as WebP, so nothing of the uploaded file is kept: no EXIF data (a phone's photo can carry
where it was taken), no other format. The page shrinks a large photo before sending it, so the upload fits nginx's
1 MB limit on the API. The file is data/head-shots/<user id>.webp (HEAD_SHOTS_FOLDER overrides the folder), never in
a database; users.head_shot_version (migration 067) is NULL when there is none. Only the member sees it: it is
served to their own session only (GET /account/head-shot).
"""

import io
import os
from pathlib import Path

from search import connect

SIZE = 400
MAX_UPLOAD_BYTES = 1_000_000
MAX_PIXELS = 40_000_000


class HeadShotProblem(Exception):
  """The picture cannot be used; the text says why and is fit to show the member."""


def folder() -> Path:
  return Path(os.environ.get("HEAD_SHOTS_FOLDER", Path(__file__).resolve().parent / "data" / "head-shots"))


def path_for(user_id: int) -> Path:
  return folder() / f"{int(user_id)}.webp"


def address(version: int | None) -> str | None:
  """The address the page shows the picture at (the member's own), or None when they have none."""
  return f"/account/head-shot?v={version}" if version else None


def _square(data: bytes) -> bytes:
  from PIL import Image, ImageOps

  Image.MAX_IMAGE_PIXELS = MAX_PIXELS
  try:
    picture = Image.open(io.BytesIO(data))
    picture.load()
  except Image.DecompressionBombError as error:
    raise HeadShotProblem("That picture is too large.") from error
  except Exception as error:
    raise HeadShotProblem("That file is not a picture this site can read. Please choose a JPEG, PNG or WebP photo.") from error
  if picture.format not in ("JPEG", "PNG", "WEBP", "GIF"):
    raise HeadShotProblem("Please choose a JPEG, PNG or WebP photo.")
  picture = ImageOps.exif_transpose(picture)
  if picture.mode in ("RGBA", "LA", "P"):
    background = Image.new("RGB", picture.size, "white")
    picture = picture.convert("RGBA")
    background.paste(picture, mask=picture.split()[-1])
    picture = background
  else:
    picture = picture.convert("RGB")
  picture = ImageOps.fit(picture, (SIZE, SIZE), Image.Resampling.LANCZOS)
  output = io.BytesIO()
  picture.save(output, "WEBP", quality=85)
  return output.getvalue()


def save(user_id: int, data: bytes) -> int:
  """Keeps the member's new head shot; returns its version."""
  if not data:
    raise HeadShotProblem("Please choose a picture.")
  if len(data) > MAX_UPLOAD_BYTES:
    raise HeadShotProblem("That picture is too large (at most 1 MB).")
  picture = _square(data)
  target = path_for(user_id)
  try:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(picture)
    temporary.replace(target)
  except OSError as error:
    raise HeadShotProblem("The picture could not be saved. Please try again later.") from error
  with connect() as connection:
    return connection.execute(
      "UPDATE users SET head_shot_version = COALESCE(head_shot_version, 0) + 1 WHERE id = %s RETURNING head_shot_version",
      (user_id,),
    ).fetchone()[0]


def remove(user_id: int) -> None:
  """Takes the member's head shot away (the file and the version)."""
  path_for(user_id).unlink(missing_ok=True)
  with connect() as connection:
    connection.execute("UPDATE users SET head_shot_version = NULL WHERE id = %s", (user_id,))

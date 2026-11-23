"""Files attached to a Message a day (added 2026-11-23 at the owner's request; day_messages.py).

Up to MAX_FILES files, MAX_TOTAL_BYTES together: PDF, pictures (JPEG, PNG, GIF, WebP), Word, Excel, PowerPoint
and plain text, each checked by its first bytes, not only its name. They are attached to each email. A text cannot
carry them, so a text gets the first picture as a picture message (a JPEG made small enough for phones) and a link
that downloads the files (the one file, or a .zip of them all).

The files are kept in the message files folder (data/message-files/<key>/; MESSAGE_FILES_FOLDER overrides it;
git- and docker-ignored, not in the backups) under a random key, and served at /message-file/<key> (and
/message-file/<key>/picture.jpg for the MMS) with no login, as the key cannot be guessed. They are deleted after
KEEP_DAYS days (whenever new files are kept).
"""

import io
import os
import re
import secrets
import shutil
import time
import zipfile
from pathlib import Path

from message_cards import site_address
from site_icons import kind_of_picture

MAX_FILES = 5
MAX_TOTAL_BYTES = 10 * 1024 * 1024
KEEP_DAYS = 30
PICTURE_SIZE = 1080
KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22}$")
# What may be attached: extension -> the type it is sent as.
TYPES = {
  ".pdf": "application/pdf",
  ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  ".txt": "text/plain",
}
PICTURES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


class AttachmentProblem(Exception):
  """A file cannot be attached; the text says why and is fit to show the administrator."""


def folder() -> Path:
  return Path(os.environ.get("MESSAGE_FILES_FOLDER", Path(__file__).resolve().parent / "data" / "message-files"))


def _safe_name(name: str) -> str:
  name = Path(str(name or "")).name.replace("\x00", "")
  name = re.sub(r"[^\w .()-]+", "_", name).strip(" .") or "file"
  stem, extension = os.path.splitext(name)
  return stem[:90] + extension.lower()


def _check(path: Path, name: str) -> str:
  """The file's type, or AttachmentProblem when it is not one that may be attached."""
  extension = os.path.splitext(name)[1].lower()
  if extension not in TYPES:
    raise AttachmentProblem(f"“{name}” cannot be attached. Attach a PDF, a picture (JPEG, PNG, GIF, WebP), a Word, Excel or PowerPoint file, or plain text.")
  start = path.read_bytes()[:64]
  if not start:
    raise AttachmentProblem(f"“{name}” is empty.")
  fits = {
    ".pdf": start.startswith(b"%PDF"),
    ".docx": start.startswith(b"PK\x03\x04"), ".xlsx": start.startswith(b"PK\x03\x04"), ".pptx": start.startswith(b"PK\x03\x04"),
  }
  if extension in PICTURES:
    found = kind_of_picture(start)
    ok = found == extension or (found == ".jpg" and extension == ".jpeg")
  elif extension == ".txt":
    try:
      data = path.read_bytes()
      data.decode("utf-8")
      ok = b"\x00" not in data
    except UnicodeDecodeError:
      ok = False
  else:
    ok = fits[extension]
  if not ok:
    raise AttachmentProblem(f"“{name}” is not really a {extension[1:].upper()} file (its contents do not match its name).")
  return TYPES[extension]


def keep(files: list[tuple[str, str]], now: float | None = None) -> dict | None:
  """Checks the uploaded files [(path, name)] and keeps copies under a new key. Returns {key, files: [{name, type,
  path}], picture (the MMS JPEG's path, or None)}, or None when there are no files."""
  if not files:
    return None
  if len(files) > MAX_FILES:
    raise AttachmentProblem(f"Attach at most {MAX_FILES} files.")
  checked = []
  total = 0
  for path, name in files:
    path = Path(path)
    name = _safe_name(name)
    if not path.is_file():
      raise AttachmentProblem(f"“{name}” could not be read.")
    total += path.stat().st_size
    checked.append((path, name, _check(path, name)))
  if total > MAX_TOTAL_BYTES:
    raise AttachmentProblem(f"The files are too large together (at most {MAX_TOTAL_BYTES // (1024 * 1024)} MB).")
  remove_old(now)
  key = secrets.token_urlsafe(16)
  target = folder() / key
  target.mkdir(parents=True, exist_ok=True)
  kept = []
  used = set()
  for path, name, media_type in checked:
    stem, extension = os.path.splitext(name)
    number = 2
    while name.lower() in used:
      name = f"{stem} ({number}){extension}"
      number += 1
    used.add(name.lower())
    shutil.copyfile(path, target / name)
    kept.append({"name": name, "type": media_type, "path": str(target / name)})
  picture = _picture(kept, target)
  return {"key": key, "files": kept, "picture": picture}


def _picture(kept: list[dict], target: Path) -> str | None:
  """The first picture as a JPEG small enough for a picture message (under about 1 MB), or None."""
  from PIL import Image, ImageOps

  for item in kept:
    if item["type"].startswith("image/"):
      try:
        with Image.open(item["path"]) as picture:
          picture = ImageOps.exif_transpose(picture).convert("RGB")
          picture.thumbnail((PICTURE_SIZE, PICTURE_SIZE))
          picture.save(target / "picture.jpg", "JPEG", quality=80)
        return str(target / "picture.jpg")
      except Exception:
        return None
  return None


def download_address(key: str) -> str:
  return site_address(f"/api/message-file/{key}")


def picture_address(key: str) -> str:
  return site_address(f"/api/message-file/{key}/picture.jpg")


def files_of(key: str) -> list[Path]:
  """The kept files of a key (not the MMS picture), by name; [] for a key that is not kept."""
  if not KEY_PATTERN.match(key or ""):
    return []
  place = folder() / key
  if not place.is_dir():
    return []
  return sorted((path for path in place.iterdir() if path.is_file() and path.name != "picture.jpg"), key=lambda path: path.name.lower())


def download(key: str) -> tuple[bytes, str, str] | None:
  """What the link in a text downloads: (data, type, file name): the one file, or a .zip of them all."""
  paths = files_of(key)
  if not paths:
    return None
  if len(paths) == 1:
    path = paths[0]
    return path.read_bytes(), TYPES.get(path.suffix.lower(), "application/octet-stream"), path.name
  buffer = io.BytesIO()
  with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in paths:
      archive.write(path, path.name)
  return buffer.getvalue(), "application/zip", "attachments.zip"


def picture_file(key: str) -> Path | None:
  if not KEY_PATTERN.match(key or ""):
    return None
  path = folder() / key / "picture.jpg"
  return path if path.is_file() else None


def remove_old(now: float | None = None) -> int:
  """Deletes the files kept more than KEEP_DAYS days ago. Returns how many keys went."""
  now = now or time.time()
  place = folder()
  if not place.is_dir():
    return 0
  removed = 0
  for entry in place.iterdir():
    if entry.is_dir() and now - entry.stat().st_mtime > KEEP_DAYS * 86400:
      shutil.rmtree(entry, ignore_errors=True)
      removed += 1
  return removed

"""The site's two icons, which an administrator can replace on the Drupal Site settings screen.

  header  the emblem in the header, beside the site name (frontend/public/logo-icon.svg until replaced)
  tab     the icon on the browser tab (frontend/public/favicon.svg until replaced)

An uploaded icon is kept as a file in data/site-icons/ (header.png, tab.svg ...), never in a database, and
the Python service serves it at /site-icon/<kind>. GET /site-settings tells the page which are replaced
(public_paths), with the file's time as a version so a browser fetches a new icon at once. Drupal runs
scripts/manage_site_icons.py, which calls these functions.
"""

import base64
import os
import shutil
from pathlib import Path

KINDS = {"header": "the header emblem", "tab": "the browser-tab icon"}
TYPES = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".svg": "image/svg+xml",
}
MAX_BYTES = 1024 * 1024


class IconProblem(Exception):
  """The icon cannot be used; the text says why and is fit to show the administrator."""


def icons_folder() -> Path:
  return Path(os.environ.get("SITE_ICONS_FOLDER", Path(__file__).resolve().parent / "data" / "site-icons"))


def _check_kind(kind: str) -> str:
  if kind not in KINDS:
    raise IconProblem("The icon must be the header emblem (header) or the browser-tab icon (tab).")
  return kind


def check_file(path: Path, original_name: str) -> str:
  """The extension to keep the file under, after checking its kind (by its first bytes), and size."""
  extension = Path(original_name).suffix.lower()
  extension = ".jpg" if extension == ".jpeg" else extension
  if extension not in TYPES:
    raise IconProblem("The icon must be a PNG, JPEG, WebP, GIF, ICO or SVG file.")
  size = path.stat().st_size
  if size == 0:
    raise IconProblem("The icon file is empty.")
  if size > MAX_BYTES:
    raise IconProblem(f"The icon is larger than {MAX_BYTES // 1024} KB.")
  with open(path, "rb") as file:
    start = file.read(4096)
  looks_right = {
    ".png": start.startswith(b"\x89PNG\r\n\x1a\n"),
    ".jpg": start.startswith(b"\xff\xd8\xff"),
    ".webp": start[:4] == b"RIFF" and start[8:12] == b"WEBP",
    ".gif": start[:6] in (b"GIF87a", b"GIF89a"),
    ".ico": start[:4] == b"\x00\x00\x01\x00",
    ".svg": b"<svg" in start.lower(),
  }[extension]
  if not looks_right:
    raise IconProblem(f"The file is not really a {extension[1:].upper()} picture.")
  return extension


def current(kind: str) -> tuple[Path, str] | None:
  """The uploaded icon of that kind and its media type, or None while the site's own icon is used."""
  _check_kind(kind)
  for extension, media_type in TYPES.items():
    path = icons_folder() / f"{kind}{extension}"
    if path.is_file():
      return path, media_type
  return None


def save(kind: str, path: Path, original_name: str) -> dict:
  """Replaces the icon of that kind with the uploaded file (copied under a temporary name, then renamed)."""
  _check_kind(kind)
  extension = check_file(path, original_name)
  folder = icons_folder()
  folder.mkdir(parents=True, exist_ok=True)
  temporary = folder / f".{kind}{extension}.new"
  shutil.copyfile(path, temporary)
  remove(kind)
  temporary.replace(folder / f"{kind}{extension}")
  return describe()[kind]


def remove(kind: str) -> None:
  """Goes back to the site's own icon of that kind."""
  _check_kind(kind)
  for extension in TYPES:
    (icons_folder() / f"{kind}{extension}").unlink(missing_ok=True)


def describe(with_data: bool = False) -> dict:
  """Each kind: None for the site's own icon, else its media type, size and version (and, for the admin
  screen's preview, the picture as a data: address)."""
  result = {}
  for kind in KINDS:
    found = current(kind)
    if found is None:
      result[kind] = None
      continue
    path, media_type = found
    stat = path.stat()
    entry = {"media_type": media_type, "size": stat.st_size, "version": int(stat.st_mtime)}
    if with_data:
      entry["data_uri"] = f"data:{media_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
    result[kind] = entry
  return result


def public_paths() -> dict:
  """For GET /site-settings: the address of each replaced icon on the service, or None for the site's own."""
  return {
    f"{kind}_icon": f"/site-icon/{kind}?v={entry['version']}" if entry else None
    for kind, entry in describe().items()
  }

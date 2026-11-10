"""The keys and options of the outside services the site uses (Gemini, API.Bible, reCAPTCHA), and the
folder the Christian music files are kept in.

They are set on the Drupal "Site settings" screen and kept in a private file next to the code
(data/service_settings.json, mode 600, git-ignored), never in a database, so they stay out of the
database backups. Until that file has a value, the one in ml-service/.env is used (and then the default),
so a new server works from its .env alone; the first save on the screen copies every value into the file,
and from then on the screen's values are the ones used.

Secret values (the keys) are never printed by the Drupal tool: it only says whether one is set and where
it comes from.
"""

import json
import math
import os
import re
import threading
from pathlib import Path

# name: (environment variable, is secret, kind, default)
SETTINGS = {
  "gemini_api_key": ("GEMINI_API_KEY", True, "text", ""),
  "gemini_models": ("GEMINI_MODEL", False, "models", ""),
  "api_bible_key": ("API_BIBLE_KEY", True, "text", ""),
  "api_bible_endpoint": ("API_BIBLE_ENDPOINT", False, "url", "https://rest.api.bible"),
  "api_bible_monthly_limit": ("API_BIBLE_MONTHLY_LIMIT", False, "count", "4500"),
  "recaptcha_site_key": ("RECAPTCHA_SITE_KEY", False, "text", ""),
  "recaptcha_secret_key": ("RECAPTCHA_SECRET_KEY", True, "text", ""),
  "recaptcha_minimum_score": ("RECAPTCHA_MINIMUM_SCORE", False, "score", "0.5"),
  # Where the MP3 and MP4 files of the Christian music section are kept (music.py). It can be moved to a
  # bigger volume: copy the files there, then change it.
  "music_folder": ("MUSIC_FOLDER", False, "folder", str(Path(__file__).resolve().parent / "data" / "music")),
}

TEXT_LIMIT = 500
COUNT_LIMIT = 5000
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")

_lock = threading.Lock()
_cache: dict = {"key": None, "values": {}}


class ServiceSettingsProblem(Exception):
  """A value cannot be saved; the text says why and is fit to show the administrator."""


def settings_path() -> Path:
  return Path(os.environ.get("SERVICE_SETTINGS_FILE", Path(__file__).parent / "data" / "service_settings.json"))


def _saved_values() -> dict:
  """The values in the file, read again only when the file changes."""
  path = settings_path()
  try:
    status = path.stat()
  except OSError:
    return {}
  key = (str(path), status.st_mtime_ns, status.st_size)
  with _lock:
    if _cache["key"] != key:
      try:
        values = json.loads(path.read_text())
      except (OSError, ValueError):
        values = {}
      _cache["key"] = key
      _cache["values"] = {name: str(value) for name, value in values.items() if name in SETTINGS} if isinstance(values, dict) else {}
    return dict(_cache["values"])


def _source_and_value(name: str, saved: dict) -> tuple[str, str]:
  environment_variable, _, _, default = SETTINGS[name]
  if name in saved:
    return "saved", saved[name]
  from_environment = os.environ.get(environment_variable, "").strip()
  if from_environment:
    return "env", from_environment
  return "default", default


def get_setting(name: str) -> str:
  """The value to use now: the saved one, else the one in .env, else the default."""
  return _source_and_value(name, _saved_values())[1]


def describe() -> dict:
  """Every setting for the Drupal screen. Secret values are left out; only whether one is set is given."""
  saved = _saved_values()
  described = {}
  for name, (environment_variable, is_secret, kind, default) in SETTINGS.items():
    source, value = _source_and_value(name, saved)
    entry = {"source": source, "is_secret": is_secret, "kind": kind, "environment_variable": environment_variable, "is_set": value != ""}
    if not is_secret:
      entry["value"] = value
      entry["default"] = default
    described[name] = entry
  return {"settings": described, "is_saved": bool(saved), "count_limit": COUNT_LIMIT}


def _checked(name: str, value: str) -> str:
  _, _, kind, _ = SETTINGS[name]
  value = value.strip()
  if len(value) > TEXT_LIMIT or CONTROL_CHARACTERS.search(value):
    raise ServiceSettingsProblem(f"{name}: use one line of at most {TEXT_LIMIT} characters.")
  if kind == "models" and value:
    names = [part.strip() for part in value.split(",")]
    if not all(MODEL_PATTERN.match(part) for part in names):
      raise ServiceSettingsProblem("Gemini models: give model names separated by commas, such as gemini-3.6-flash, gemini-flash-latest.")
    value = ",".join(names)
  if kind == "url" and not re.match(r"^https://[A-Za-z0-9.-]+(:\d+)?(/[^\s]*)?$", value):
    raise ServiceSettingsProblem("The API.Bible address must start with https://, such as https://rest.api.bible.")
  if kind == "count" and (not value.isdigit() or int(value) > COUNT_LIMIT):
    raise ServiceSettingsProblem(f"The API.Bible monthly limit must be a whole number from 0 to {COUNT_LIMIT}.")
  if kind == "folder":
    value = value.rstrip("/") or "/"
    if not value.startswith("/") or "\\" in value:
      raise ServiceSettingsProblem("The music folder must be a full path on the server, starting with /, such as /mnt/music.")
    folder = Path(value)
    try:
      folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
      raise ServiceSettingsProblem(f"The music folder {value} could not be made: {error.strerror}.") from error
    if not folder.is_dir() or not os.access(folder, os.W_OK | os.X_OK):
      raise ServiceSettingsProblem(f"The music folder {value} cannot be written to by the site.")
  if kind == "score":
    try:
      score = float(value)
    except ValueError:
      score = math.nan
    if not 0 <= score <= 1:
      raise ServiceSettingsProblem("The reCAPTCHA minimum score must be a number from 0 to 1, such as 0.5.")
  return value


def save(values: dict, remove: list) -> dict:
  """Saves every setting to the file: the ones given, and the ones in use now for the rest.

  values: name -> new value. An empty secret means "keep the one in use". remove: secrets to clear.
  After this the file holds every value, so .env is no longer consulted for them.
  """
  unknown = [name for name in [*values, *remove] if name not in SETTINGS]
  if unknown:
    raise ServiceSettingsProblem(f"Unknown setting: {', '.join(unknown)}.")
  saved = _saved_values()
  result = {}
  for name, (_, is_secret, _, _) in SETTINGS.items():
    current = _source_and_value(name, saved)[1]
    if is_secret and name in remove:
      result[name] = ""
    elif name in values and not (is_secret and str(values[name]).strip() == ""):
      result[name] = _checked(name, str(values[name]))
    else:
      result[name] = current
  path = settings_path()
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = path.with_name(path.name + ".new")
  descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
  with os.fdopen(descriptor, "w") as file:
    json.dump(result, file, indent=2)
  os.chmod(temporary, 0o600)
  os.replace(temporary, path)
  return describe()

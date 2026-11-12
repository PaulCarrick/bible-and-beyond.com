"""Backing up the whole site into one zip file, and restoring it from one (the Drupal "Backup and restore" page).

The backups are kept on the administrator's own computer, not on the server: the page builds the zip here,
the browser saves it into a folder the administrator picks and then has it deleted here; to restore, the
browser uploads a zip from that folder (in parts), and the restore runs here. So a new server or container
can carry on from a backup of the old one.

Two parts, chosen with the page's two checkboxes (for a backup, and again for a restore):

  Database  database/bible-database.dump     the whole Bible database (pg_dump's custom format): the
                                             Bibles, commentaries, devotionals and books, the songs'
                                             details, accounts, notes, daily emails, FAQ notes and answers,
                                             the site settings
            database/drupal-database.sql.gz  Drupal's database (drush sql:dump; the cache and log tables as
                                             structure only): the administrators, their roles and Drupal's
                                             configuration, the email server included
            database/settings/...            the service keys (Gemini, API.Bible, reCAPTCHA) and the API.Bible
                                             request count
  Files     files/music/...                  the song files and words files of the music folder
            files/drupal/...                 Drupal's public files (sites/default/files), without the
                                             generated css, js and php
            files/icons/...                  the header emblem and browser-tab icon uploaded on the Site
                                             settings screen (site_icons.py), if any

and manifest.json (when it was taken, the note, which parts it holds, a few counts). The zip holds personal
data (accounts, password hashes) and the service keys: keep it private.

The work takes minutes, longer than a web page may wait, so it runs in the background like a library
refresh: start_backup() and start_restore() start scripts/manage_backup.py as a separate process and return;
status() reads its progress from data/backup/status.json. Only one runs at a time. The files in progress live
in data/backup/ (outgoing/ the zip waiting to be saved, incoming/ the uploaded zip, work-* while working).

Restoring the database replaces, in this order:
  1. the Bible database, in one transaction (everything of ours in the public schema is dropped and the
     backup loaded), so if anything fails nothing has changed; then the migrations are applied, so a backup
     from an older version is brought up to date. The extensions (pgvector) are neither dropped nor created:
     this database already has them, and only a superuser may create pgvector;
  2. the service settings, keeping this site's own music folder (a backup may come from another server);
  3. Drupal's database (drush sql:drop, then the backup through drush sql:cli), then drush updatedb and
     cache:rebuild. This logs everyone out of the admin; log in again with an account from the backup.
Restoring the files copies them over the ones here (files that are not in the backup stay).
"""

import gzip
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from psycopg.conninfo import conninfo_to_dict, make_conninfo

import site_icons
from search import connect
from service_settings import get_setting, settings_path

FORMAT = 2
ML_DIRECTORY = Path(__file__).resolve().parent
DRUPAL_DIRECTORY = ML_DIRECTORY.parent / "drupal"
DATA_DIRECTORY = ML_DIRECTORY / "data"
WORK_DIRECTORY = DATA_DIRECTORY / "backup"
NAME_PATTERN = re.compile(r"^bible-and-beyond-\d{4}-\d{2}-\d{2}-\d{6}\.zip$")
BIBLE_DUMP = "database/bible-database.dump"
DRUPAL_DUMP = "database/drupal-database.sql.gz"
SETTINGS = "database/settings/"
MUSIC = "files/music/"
DRUPAL_FILES = "files/drupal/"
ICONS = "files/icons/"
# Small files of ml-service/data that are part of the site (the service settings file itself can live
# elsewhere, see settings_path()).
DATA_FILES = ["api_bible_usage.json"]
# Drupal's generated files, rebuilt by Drupal on demand.
DRUPAL_GENERATED = {"css", "js", "php"}
# Drupal tables saved as structure only (caches and the log).
DRUPAL_STRUCTURE_ONLY = "cache,cache_*,watchdog"
# Kinds of file that are compressed already: stored in the zip as they are.
STORED_SUFFIXES = {".dump", ".gz", ".zip", ".mp3", ".mp4", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
# A job that has said nothing for this long is taken to have died (the server restarted, say).
STALE_SECONDS = 6 * 60 * 60
COUNTED_TABLES = {
  "Bibles": "translations",
  "Commentaries": "commentaries",
  "Devotionals and books": "devotionals",
  "Site users": "users",
  "Notes": "notes",
  "Daily emails": "devotional_subscriptions",
  "Songs": "music_tracks",
  "FAQ notes": "faq_notes",
}


class BackupProblem(Exception):
  """The backup or restore cannot be done; the text says why and is fit to show the administrator."""


def outgoing_directory() -> Path:
  return WORK_DIRECTORY / "outgoing"


def incoming_path() -> Path:
  """Where the page's uploads of a zip to restore are put together (by Drupal, a part at a time)."""
  return WORK_DIRECTORY / "incoming" / "upload.zip"


def _parts(database: bool, files: bool) -> dict:
  if not database and not files:
    raise BackupProblem("Choose Database, Files or both.")
  return {"database": database, "files": files}


# ---------------------------------------------------------------------------------------------- the status

def _status_path() -> Path:
  return WORK_DIRECTORY / "status.json"


def status():
  """The last or current backup or restore started from the page, or None."""
  try:
    current = json.loads(_status_path().read_text())
  except (OSError, ValueError):
    return None
  if current.get("state") in ("starting", "running"):
    updated = datetime.fromisoformat(current["updated_at"])
    if (datetime.now(timezone.utc) - updated).total_seconds() > STALE_SECONDS:
      current = {**current, "state": "failed", "message": "It stopped without finishing (the server may have restarted)."}
  return current


def _write_status(action: str, state: str, message: str, **extra):
  WORK_DIRECTORY.mkdir(parents=True, exist_ok=True)
  previous = status() or {}
  now = datetime.now(timezone.utc).isoformat()
  current = {
    "action": action,
    "state": state,
    "message": message,
    "started_at": now if state == "starting" else previous.get("started_at", now),
    "updated_at": now,
    **extra,
  }
  temporary = _status_path().with_name("status.json.new")
  temporary.write_text(json.dumps(current))
  temporary.replace(_status_path())


def _refuse_while_running():
  current = status()
  if current and current["state"] in ("starting", "running"):
    raise BackupProblem(f"A {current['action']} is running already; wait for it to finish.")


def describe() -> dict:
  """The last job, and the backup waiting to be saved by the browser (if any)."""
  waiting = None
  folder = outgoing_directory()
  if folder.is_dir():
    for path in sorted(folder.glob("*.zip")):
      if NAME_PATTERN.match(path.name):
        waiting = {"name": path.name, "size": path.stat().st_size}
  return {"status": status(), "waiting": waiting}


def clear_status():
  for path in (_status_path(), WORK_DIRECTORY / "job.log"):
    try:
      os.remove(path)
    except OSError:
      pass


def discard_backup():
  """Deletes the backup waiting to be saved (once the browser has saved it, or to give up on it)."""
  shutil.rmtree(outgoing_directory(), ignore_errors=True)
  return {"discarded": True}


def discard_upload():
  shutil.rmtree(incoming_path().parent, ignore_errors=True)
  return {"discarded": True}


# ---------------------------------------------------------------------------------- starting in background

def _start(arguments: list[str], action: str):
  _refuse_while_running()
  _write_status(action, "starting", "Starting ...")
  log = open(WORK_DIRECTORY / "job.log", "w")
  subprocess.Popen(
    [sys.executable, str(ML_DIRECTORY / "scripts" / "manage_backup.py"), *arguments],
    cwd=ML_DIRECTORY, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True,
  )


def _part_arguments(parts: dict) -> list[str]:
  return [*(["--database"] if parts["database"] else []), *(["--files"] if parts["files"] else [])]


def start_backup(database: bool, files: bool, note: str = "") -> dict:
  parts = _parts(database, files)
  _refuse_while_running()
  discard_backup()
  _start(["run-backup", *_part_arguments(parts), f"--note={note[:200]}"], "backup")
  return {"state": "starting"}


def start_restore(database: bool, files: bool) -> dict:
  parts = _parts(database, files)
  _refuse_while_running()
  if not incoming_path().is_file():
    raise BackupProblem("No backup has been uploaded to restore.")
  _start(["run-restore", *_part_arguments(parts)], "restore")
  return {"state": "starting"}


def run_backup_job(database: bool, files: bool, note: str):
  started = time.monotonic()
  try:
    path = take_backup(_parts(database, files), note, report=lambda message: _write_status("backup", "running", message))
    _write_status("backup", "done", f"The backup is ready ({_took(started)}).", name=path.name, size=path.stat().st_size)
  except Exception as error:  # Anything that went wrong is shown on the page; the details go to the log.
    discard_backup()
    _write_status("backup", "failed", _describe_error(error))
    raise


def run_restore_job(database: bool, files: bool):
  started = time.monotonic()
  try:
    restored = restore_backup(incoming_path(), _parts(database, files), report=lambda message: _write_status("restore", "running", message))
    discard_upload()
    _write_status("restore", "done", f"Restored {restored} in {_took(started)}.")
  except Exception as error:
    discard_upload()
    _write_status("restore", "failed", _describe_error(error))
    raise


def _describe_error(error: Exception) -> str:
  text = str(error) if isinstance(error, BackupProblem) else f"{type(error).__name__}: {error}"
  return text[:500]


def _took(started: float) -> str:
  seconds = time.monotonic() - started
  return f"{round(seconds)} seconds" if seconds < 90 else f"{round(seconds / 60, 1)} minutes"


# ------------------------------------------------------------------------------------------------ the tools

def _postgres_tool(name: str) -> str:
  directory = os.environ.get("POSTGRES_BIN_DIRECTORY", "").strip()
  return str(Path(directory) / name) if directory else name


def _postgres_connection() -> tuple[str, dict]:
  """The connection string without its password, and an environment that carries the password, so it never
  shows in the server's process list."""
  parts = conninfo_to_dict(os.environ["DATABASE_URL"])
  password = parts.pop("password", None)
  environment = dict(os.environ)
  if password:
    environment["PGPASSWORD"] = password
  return make_conninfo(**parts), environment


def _drush() -> list[str]:
  return shlex.split(os.environ.get("DRUSH_COMMAND", "")) or [str(DRUPAL_DIRECTORY / "vendor" / "bin" / "drush")]


def _run(command: list[str], what: str, **options):
  try:
    completed = subprocess.run(command, capture_output=True, **options)
  except OSError as error:
    raise BackupProblem(f"{what}: {Path(command[0]).name} could not be run ({error.strerror}).") from error
  if completed.returncode != 0:
    detail = [line for line in completed.stderr.decode("utf-8", "replace").strip().splitlines() if line.strip()]
    raise BackupProblem(f"{what} failed: {detail[-1] if detail else 'exit status ' + str(completed.returncode)}")
  return completed


def _drupal_files_directory() -> Path:
  configured = os.environ.get("DRUPAL_FILES_DIRECTORY", "").strip()
  return Path(configured) if configured else DRUPAL_DIRECTORY / "web" / "sites" / "default" / "files"


def _music_directory() -> Path:
  return Path(get_setting("music_folder"))


def _scratch() -> tempfile.TemporaryDirectory:
  WORK_DIRECTORY.mkdir(parents=True, exist_ok=True)
  return tempfile.TemporaryDirectory(dir=WORK_DIRECTORY, prefix="work-")


def _add(archive: zipfile.ZipFile, source: Path, name: str):
  method = zipfile.ZIP_STORED if source.suffix.lower() in STORED_SUFFIXES else zipfile.ZIP_DEFLATED
  archive.write(source, name, compress_type=method)


def _add_folder(archive: zipfile.ZipFile, folder: Path, prefix: str, skip=frozenset()) -> int:
  count = 0
  if not folder.is_dir():
    return count
  for top in sorted(folder.iterdir()):
    if top.name in skip or top.name.startswith("."):
      continue
    for path in sorted([top, *top.rglob("*")] if top.is_dir() else [top]):
      if path.is_file() and not path.is_symlink():
        _add(archive, path, prefix + path.relative_to(folder).as_posix())
        count += 1
  return count


# ------------------------------------------------------------------------------------------------- backing up

def take_backup(parts: dict, note: str = "", report=lambda message: None) -> Path:
  """Builds a backup zip in the outgoing folder and returns its path."""
  folder = outgoing_directory()
  folder.mkdir(parents=True, exist_ok=True, mode=0o700)
  name = "bible-and-beyond-" + datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S") + ".zip"
  target = folder / name
  # Written under a hidden name and renamed at the end, so a zip that failed half-way is never offered.
  partial = folder / f".{name}.partial"
  manifest = {
    "format": FORMAT,
    "name": name,
    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "note": note,
    "parts": parts,
    "counts": {},
  }
  try:
    with _scratch() as scratch, zipfile.ZipFile(partial, "w", allowZip64=True) as archive:
      os.chmod(partial, 0o600)
      scratch = Path(scratch)
      if parts["database"]:
        report("Saving the Bible database ...")
        connection, environment = _postgres_connection()
        _run(
          [_postgres_tool("pg_dump"), "--format=custom", "--compress=6", "--no-owner", "--no-privileges",
           f"--file={scratch / 'bible.dump'}", f"--dbname={connection}"],
          "Saving the Bible database", env=environment,
        )
        _add(archive, scratch / "bible.dump", BIBLE_DUMP)
        report("Saving Drupal's database ...")
        _dump_drupal(scratch / "drupal.sql.gz")
        _add(archive, scratch / "drupal.sql.gz", DRUPAL_DUMP)
        for path in [settings_path(), *(DATA_DIRECTORY / file_name for file_name in DATA_FILES)]:
          if path.is_file():
            _add(archive, path, SETTINGS + path.name)
        manifest["counts"] = _counts()
      if parts["files"]:
        report("Adding the music files ...")
        manifest["counts"]["Music files"] = _add_folder(archive, _music_directory(), MUSIC)
        report("Adding Drupal's files ...")
        manifest["counts"]["Drupal files"] = _add_folder(archive, _drupal_files_directory(), DRUPAL_FILES, DRUPAL_GENERATED)
        manifest["counts"]["Site icons"] = _add_folder(archive, site_icons.icons_folder(), ICONS)
      archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    partial.rename(target)
  except BaseException:
    partial.unlink(missing_ok=True)
    raise
  return target


def _dump_drupal(target: Path):
  command = [*_drush(), "sql:dump", f"--structure-tables-list={DRUPAL_STRUCTURE_ONLY}"]
  with open(target, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6) as compressed:
    try:
      process = subprocess.Popen(command, cwd=DRUPAL_DIRECTORY, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    except OSError as error:
      raise BackupProblem(f"Saving Drupal's database: drush could not be run ({error.strerror}).") from error
    written = 0
    for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
      compressed.write(block)
      written += len(block)
    errors = process.stderr.read().decode("utf-8", "replace")
    if process.wait() != 0:
      lines = [line for line in errors.strip().splitlines() if line.strip()]
      raise BackupProblem(f"Saving Drupal's database failed: {lines[-1] if lines else 'drush stopped'}")
  if written < 1000:
    raise BackupProblem("Saving Drupal's database gave almost nothing; is Drupal installed here?")


def _counts() -> dict:
  counts = {}
  with connect() as connection:
    for label, table in COUNTED_TABLES.items():
      try:
        counts[label] = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
      except Exception:
        connection.rollback()
  return counts


# ------------------------------------------------------------------------------------------------- restoring

# Drops everything of ours in the public schema (not the extensions' own objects), inside the restore's
# transaction, so the backup loads into an empty schema.
DROP_EVERYTHING_SQL = """
DO $drop$
DECLARE
  statement text;
BEGIN
  FOR statement IN
    SELECT format('DROP %s IF EXISTS %I.%I CASCADE',
      CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' WHEN 'S' THEN 'SEQUENCE'
        WHEN 'f' THEN 'FOREIGN TABLE' ELSE 'TABLE' END, n.nspname, c.relname)
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f') AND NOT c.relispartition
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e')
    UNION ALL
    SELECT format('DROP ROUTINE IF EXISTS %s CASCADE', p.oid::regprocedure)
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e')
    UNION ALL
    SELECT format('DROP TYPE IF EXISTS %I.%I CASCADE', n.nspname, t.typname)
    FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typtype IN ('e', 'd', 'r', 'c')
      AND (t.typtype <> 'c' OR (SELECT relkind FROM pg_class WHERE oid = t.typrelid) = 'c')
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_type'::regclass AND d.objid = t.oid AND d.deptype = 'e')
    UNION ALL
    SELECT format('DROP TEXT SEARCH CONFIGURATION IF EXISTS %I.%I CASCADE', n.nspname, c.cfgname)
    FROM pg_ts_config c JOIN pg_namespace n ON n.oid = c.cfgnamespace
    WHERE n.nspname = 'public'
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_ts_config'::regclass AND d.objid = c.oid AND d.deptype = 'e')
    UNION ALL
    SELECT format('DROP TEXT SEARCH DICTIONARY IF EXISTS %I.%I CASCADE', n.nspname, c.dictname)
    FROM pg_ts_dict c JOIN pg_namespace n ON n.oid = c.dictnamespace
    WHERE n.nspname = 'public'
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_ts_dict'::regclass AND d.objid = c.oid AND d.deptype = 'e')
  LOOP
    EXECUTE statement;
  END LOOP;
END
$drop$;
"""

# Entries of pg_restore's list that are left out: the extensions (kept as they are here) and the public
# schema itself (it exists already).
SKIPPED_ENTRY = re.compile(r"^\d+; \d+ \d+ (EXTENSION - |COMMENT - EXTENSION |SCHEMA - public\b|COMMENT - SCHEMA public\b)")
EXTENSION_ENTRY = re.compile(r"^\d+; \d+ \d+ EXTENSION - (\S+)")


def read_backup(path: Path) -> tuple[zipfile.ZipFile, dict]:
  """Opens a backup zip and reads its manifest, after checking every file in it against its checksum."""
  try:
    archive = zipfile.ZipFile(path)
  except (OSError, zipfile.BadZipFile) as error:
    raise BackupProblem("That file is not a backup zip of this site (or it was damaged on the way).") from error
  try:
    manifest = json.loads(archive.read("manifest.json"))
  except (KeyError, ValueError) as error:
    archive.close()
    raise BackupProblem("That zip has no manifest.json, so it is not a backup of this site.") from error
  if manifest.get("format") != FORMAT:
    archive.close()
    raise BackupProblem("That backup was made by another version of the site and cannot be restored here.")
  for name in archive.namelist():
    if name.startswith("/") or ".." in PurePosixPath(name).parts or "\\" in name:
      archive.close()
      raise BackupProblem(f"The backup holds a file with an unsafe name ({name[:100]}); nothing was restored.")
  damaged = archive.testzip()
  if damaged is not None:
    archive.close()
    raise BackupProblem(f"The backup's file {damaged} is damaged; nothing was restored.")
  return archive, manifest


def restore_backup(path: Path, wanted: dict, report=lambda message: None) -> str:
  """Restores the parts chosen (and present) from a backup zip. Returns what was restored, in words."""
  report("Checking the backup ...")
  archive, manifest = read_backup(path)
  with archive, _scratch() as scratch:
    scratch = Path(scratch)
    names = set(archive.namelist())
    has = manifest.get("parts", {})
    database = bool(wanted["database"] and has.get("database"))
    files = bool(wanted["files"] and has.get("files"))
    if not database and not files:
      held = "only the database" if has.get("database") else "only the files"
      raise BackupProblem(f"That backup does not hold the parts chosen (it holds {held}); nothing was restored.")
    if database and not {BIBLE_DUMP, DRUPAL_DUMP} <= names:
      raise BackupProblem("The backup's database files are missing; nothing was restored.")

    if database:
      report("Restoring the Bible database (a few minutes) ...")
      archive.extract(BIBLE_DUMP, scratch)
      _restore_bible_database(scratch / BIBLE_DUMP)
      report("Bringing the Bible database up to date ...")
      _apply_migrations()
      report("Restoring the service settings ...")
      _restore_settings(archive)

    if files:
      report("Restoring the music files ...")
      _extract_folder(archive, MUSIC, _music_directory())
      report("Restoring Drupal's files ...")
      _extract_folder(archive, DRUPAL_FILES, _drupal_files_directory())
      # The icons as they were in the backup: none in it means the site's own icons.
      for kind in site_icons.KINDS:
        site_icons.remove(kind)
      _extract_folder(archive, ICONS, site_icons.icons_folder())

    if database:
      report("Restoring Drupal's database ...")
      archive.extract(DRUPAL_DUMP, scratch)
      drush = _drush()
      _run([*drush, "sql:drop", "--yes"], "Emptying Drupal's database", cwd=DRUPAL_DIRECTORY, stdin=subprocess.DEVNULL)
      _load_drupal(scratch / DRUPAL_DUMP)
      report("Bringing Drupal up to date ...")
      _run([*drush, "updatedb", "--yes"], "Drupal's database updates", cwd=DRUPAL_DIRECTORY, stdin=subprocess.DEVNULL)
      _run([*drush, "cache:rebuild"], "Rebuilding Drupal's caches", cwd=DRUPAL_DIRECTORY, stdin=subprocess.DEVNULL)
  restored = " and ".join(word for word, chosen in (("the database", database), ("the files", files)) if chosen)
  return f"{restored} from {manifest.get('name', path.name)}"


def _apply_migrations():
  _run([sys.executable, str(ML_DIRECTORY / "scripts" / "apply_migrations.py")], "Applying the migrations", cwd=ML_DIRECTORY)


def _restore_bible_database(dump: Path):
  connection, environment = _postgres_connection()
  listing = _run([_postgres_tool("pg_restore"), "--list", str(dump)], "Reading the Bible database backup").stdout.decode("utf-8", "replace")
  kept, extensions = [], []
  for line in listing.splitlines():
    found = EXTENSION_ENTRY.match(line)
    if found:
      extensions.append(found.group(1))
    if not SKIPPED_ENTRY.match(line):
      kept.append(line)
  list_path = dump.with_name("restore.list")
  list_path.write_text("\n".join(kept) + "\n")
  errors_path = dump.with_name("psql.errors")
  with open(errors_path, "wb") as errors:
    try:
      psql = subprocess.Popen(
        [_postgres_tool("psql"), "--no-psqlrc", "--quiet", "--set=ON_ERROR_STOP=1", f"--dbname={connection}"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors, env=environment,
      )
      script = subprocess.Popen(
        [_postgres_tool("pg_restore"), "--no-owner", "--no-privileges", f"--use-list={list_path}", "--file=-", str(dump)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
      )
    except OSError as error:
      raise BackupProblem(f"Restoring the Bible database: a PostgreSQL tool could not be run ({error.strerror}).") from error
    # Every extension the backup used must be here already (it is not created, see the module's notes).
    checks = "".join(
      f"DO $check$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = '{extension}') THEN "
      f"RAISE EXCEPTION 'The database here lacks the {extension} extension'; END IF; END $check$;\n"
      for extension in extensions if re.match(r"^[a-z0-9_]+$", extension)
    )
    try:
      psql.stdin.write(("BEGIN;\n" + checks + DROP_EVERYTHING_SQL).encode())
      shutil.copyfileobj(script.stdout, psql.stdin, 1024 * 1024)
      psql.stdin.write(b"\nCOMMIT;\n")
      psql.stdin.close()
    except BrokenPipeError:
      pass  # psql stopped at an error; it is reported below
    script_errors = script.stderr.read().decode("utf-8", "replace")
    script_status = script.wait()
    psql_status = psql.wait()
  if psql_status != 0 or script_status != 0:
    lines = [line for line in (errors_path.read_text(errors="replace") + "\n" + script_errors).splitlines() if line.strip()]
    detail = next((line for line in lines if "ERROR" in line or "error" in line), lines[-1] if lines else "")
    raise BackupProblem(f"Restoring the Bible database failed, so it was left as it was: {detail[:300]}")


def _restore_settings(archive: zipfile.ZipFile):
  name = SETTINGS + settings_path().name
  if name in archive.namelist():
    try:
      values = json.loads(archive.read(name))
    except ValueError as error:
      raise BackupProblem("The backup's service settings cannot be read.") from error
    if isinstance(values, dict):
      # The music folder is a path on this server; a backup may come from another one.
      values["music_folder"] = get_setting("music_folder")
      path = settings_path()
      path.parent.mkdir(parents=True, exist_ok=True)
      temporary = path.with_name(path.name + ".new")
      descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
      with os.fdopen(descriptor, "w") as file:
        json.dump(values, file, indent=2)
      os.replace(temporary, path)
  for file_name in DATA_FILES:
    if SETTINGS + file_name in archive.namelist():
      (DATA_DIRECTORY / file_name).write_bytes(archive.read(SETTINGS + file_name))


def _extract_folder(archive: zipfile.ZipFile, prefix: str, target: Path):
  target.mkdir(parents=True, exist_ok=True)
  for info in archive.infolist():
    if not info.filename.startswith(prefix) or info.is_dir():
      continue
    destination = target / info.filename[len(prefix):]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.restoring")
    with archive.open(info) as source, open(temporary, "wb") as output:
      shutil.copyfileobj(source, output, 1024 * 1024)
    temporary.replace(destination)


def _load_drupal(dump: Path):
  try:
    process = subprocess.Popen(
      [*_drush(), "sql:cli"], cwd=DRUPAL_DIRECTORY, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
  except OSError as error:
    raise BackupProblem(f"Restoring Drupal's database: drush could not be run ({error.strerror}).") from error
  try:
    with gzip.open(dump, "rb") as source:
      shutil.copyfileobj(source, process.stdin, 1024 * 1024)
    process.stdin.close()
  except BrokenPipeError:
    pass
  errors = process.stderr.read().decode("utf-8", "replace")
  if process.wait() != 0:
    lines = [line for line in errors.strip().splitlines() if line.strip() and "slow to pass" not in line]
    raise BackupProblem(
      f"Restoring Drupal's database failed: {lines[-1][:300] if lines else 'drush stopped'}. "
      "Drupal's database may be incomplete: restore the backup again."
    )

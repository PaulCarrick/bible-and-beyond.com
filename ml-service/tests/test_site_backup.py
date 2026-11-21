"""Tests for the backup and restore of the whole site (site_backup.py). The PostgreSQL tools and drush are
replaced by small scripts that record what they were given, so no database is dumped or replaced; the folders
(music, Drupal's files, the data and work folders) are temporary ones."""

import json
import os
import shutil
import stat
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

import site_backup
import site_icons

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_backup.py"

FAKE_PG_DUMP = """#!/bin/sh
for argument in "$@"; do case "$argument" in --file=*) printf 'PGDMP fake dump' > "${argument#--file=}";; esac; done
echo "$PGPASSWORD" > "$FAKE_LOG/pg_dump.password"
"""
FAKE_PG_RESTORE = """#!/bin/sh
case "$1" in
  --list) printf '%s\\n' '; Archive' '5; 3079 16385 EXTENSION - vector' '4567; 0 0 COMMENT - EXTENSION vector ' \\
    '219; 1259 16400 TABLE public verses bibleandbeyond' '5000; 0 16400 TABLE DATA public verses bibleandbeyond';;
  *) for argument in "$@"; do case "$argument" in --use-list=*) cp "${argument#--use-list=}" "$FAKE_LOG/restore.list";; esac; done
     echo 'SELECT 1;';;
esac
"""
FAKE_PSQL = """#!/bin/sh
cat > "$FAKE_LOG/psql.input"
"""
FAKE_DRUSH = """#!/bin/sh
echo "$*" >> "$FAKE_LOG/drush.calls"
case "$1" in
  sql:dump) i=0; while [ $i -lt 200 ]; do echo "INSERT INTO users VALUES ($i);"; i=$((i+1)); done;;
  sql:cli) cat > "$FAKE_LOG/drupal.input";;
esac
"""
EVERYTHING = {"database": True, "files": True}


def executable(path: Path, content: str) -> Path:
  path.write_text(content)
  path.chmod(path.stat().st_mode | stat.S_IEXEC)
  return path


@pytest.fixture
def site(tmp_path, monkeypatch):
  """A site whose tools are fakes: returns its folders."""
  tools = tmp_path / "tools"
  tools.mkdir()
  log = tmp_path / "log"
  log.mkdir()
  executable(tools / "pg_dump", FAKE_PG_DUMP)
  executable(tools / "pg_restore", FAKE_PG_RESTORE)
  executable(tools / "psql", FAKE_PSQL)
  drush = executable(tools / "drush", FAKE_DRUSH)
  monkeypatch.setenv("POSTGRES_BIN_DIRECTORY", str(tools))
  monkeypatch.setenv("DRUSH_COMMAND", str(drush))
  monkeypatch.setenv("FAKE_LOG", str(log))
  monkeypatch.setenv("DATABASE_URL", "postgresql://someone:secret-word@localhost:5434/bibleandbeyond")

  folders = {name: tmp_path / name for name in ("music", "files", "data")}
  folders["music"].mkdir()
  (folders["music"] / "amazing-grace.mp4").write_bytes(b"\x00\x00\x00\x18ftypisom" + b"x" * 5000)
  (folders["music"] / "amazing-grace-words.pdf").write_bytes(b"%PDF-1.4 words")
  (folders["files"] / "css").mkdir(parents=True)
  (folders["files"] / "css" / "generated.css").write_text("body{}")
  (folders["files"] / "pictures").mkdir()
  (folders["files"] / "pictures" / "logo.png").write_bytes(b"png")
  folders["data"].mkdir()
  (folders["data"] / "api_bible_usage.json").write_text('{"2026-11": 12}')
  monkeypatch.setenv("MUSIC_FOLDER", str(folders["music"]))
  monkeypatch.setenv("DRUPAL_FILES_DIRECTORY", str(folders["files"]))
  monkeypatch.setattr(site_backup, "DATA_DIRECTORY", folders["data"])
  monkeypatch.setattr(site_backup, "WORK_DIRECTORY", folders["data"] / "backup")
  monkeypatch.setattr(site_backup, "_counts", lambda: {"Site users": 3})
  migrations = []
  monkeypatch.setattr(site_backup, "_apply_migrations", lambda: migrations.append(True))
  folders["log"] = log
  folders["migrations"] = migrations
  return folders


def save_settings(values: dict):
  Path(os.environ["SERVICE_SETTINGS_FILE"]).write_text(json.dumps(values))


def upload(*paths: Path) -> list[Path]:
  """Puts backup zips where the page's upload would."""
  folder = site_backup.incoming_directory()
  shutil.rmtree(folder, ignore_errors=True)
  folder.mkdir(parents=True)
  for index, path in enumerate(paths):
    (folder / f"upload-{index}.zip").write_bytes(path.read_bytes())
  return site_backup.incoming_paths()


def by_part(paths: list[Path]) -> dict:
  return {site_backup.NAME_PATTERN.match(path.name).group(2): path for path in paths}


def names_in(path: Path) -> set:
  with zipfile.ZipFile(path) as archive:
    return set(archive.namelist())


def test_a_backup_is_three_zips_of_one_backup(site):
  save_settings({"gemini_api_key": "the-key", "music_folder": str(site["music"])})
  site_icons.icons_folder().mkdir(parents=True)
  (site_icons.icons_folder() / "tab.png").write_bytes(b"\x89PNG\r\n\x1a\n")
  paths = site_backup.take_backup(EVERYTHING, "Before the move")

  zips = by_part(paths)
  assert list(zips) == ["bible-database", "drupal-database", "files"]
  stems = {site_backup.NAME_PATTERN.match(path.name).group(1) for path in paths}
  assert len(stems) == 1
  for path in paths:
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
  assert names_in(zips["bible-database"]) == {
    "manifest.json", "database/bible-database.dump",
    "database/settings/service_settings.json", "database/settings/api_bible_usage.json",
  }
  assert names_in(zips["drupal-database"]) == {"manifest.json", "database/drupal-database.sql.gz"}
  assert names_in(zips["files"]) == {
    "manifest.json", "files/music/amazing-grace.mp4", "files/music/amazing-grace-words.pdf",
    "files/drupal/pictures/logo.png", "files/icons/tab.png",
  }
  with zipfile.ZipFile(zips["files"]) as archive:
    manifest = json.loads(archive.read("manifest.json"))
    # Media files are stored as they are; text is compressed.
    assert archive.getinfo("files/music/amazing-grace.mp4").compress_type == zipfile.ZIP_STORED
  with zipfile.ZipFile(zips["bible-database"]) as archive:
    assert archive.getinfo("database/settings/service_settings.json").compress_type == zipfile.ZIP_DEFLATED
    assert json.loads(archive.read("manifest.json"))["counts"] == {"Site users": 3}
  assert manifest["part"] == "files"
  assert manifest["backup"] == stems.pop()
  assert manifest["set"] == [path.name for path in paths]
  assert manifest["note"] == "Before the move"
  assert manifest["counts"] == {"Music files": 2, "Drupal files": 1, "Site icons": 1, "Kindle book pictures": 0, "Pictures of uploaded documents": 0, "Original pages of PDFs": 0, "Map files": 0, "Verse a day picture files": 0}
  # The database password went to pg_dump in its environment, not on its command line.
  assert (site["log"] / "pg_dump.password").read_text().strip() == "secret-word"
  assert site_backup.describe()["waiting"] == [{"name": path.name, "size": path.stat().st_size, "part": part} for part, path in zips.items()]
  assert not list(paths[0].parent.glob(".*partial"))


def test_each_zip_is_deleted_once_saved_and_a_new_backup_deletes_the_rest(site, monkeypatch):
  paths = site_backup.take_backup(EVERYTHING)
  # The page saved the two databases; the files, last, failed (a network error) and stays to be saved again.
  site_backup.discard_backup(paths[0].name)
  left = site_backup.discard_backup(paths[1].name)["waiting"]
  assert [file["name"] for file in left] == [paths[2].name]
  with pytest.raises(site_backup.BackupProblem, match="not the name of a backup zip"):
    site_backup.discard_backup("../status.json")
  # Starting a new backup deletes it (the background job itself is not run here).
  started = []
  monkeypatch.setattr(site_backup.subprocess, "Popen", lambda *arguments, **options: started.append(arguments))
  site_backup.start_backup(True, False)
  assert started and site_backup.describe()["waiting"] == []


def test_only_the_parts_chosen_are_backed_up(site):
  paths = site_backup.take_backup({"database": False, "files": True})
  assert list(by_part(paths)) == ["files"]
  assert not (site["log"] / "drush.calls").exists()
  site_backup.discard_backup()
  assert list(by_part(site_backup.take_backup({"database": True, "files": False}))) == ["bible-database", "drupal-database"]
  with pytest.raises(site_backup.BackupProblem, match="Choose Database, Files or both"):
    site_backup.start_backup(False, False)


def test_a_failed_backup_leaves_nothing(site):
  executable(Path(os.environ["DRUSH_COMMAND"]), "#!/bin/sh\necho 'Drupal is not installed' >&2\nexit 1\n")
  with pytest.raises(site_backup.BackupProblem, match="Drupal is not installed"):
    site_backup.take_backup(EVERYTHING)
  assert list(site_backup.outgoing_directory().iterdir()) == []
  assert not list(site_backup.WORK_DIRECTORY.glob("work-*"))


def test_restore_replaces_everything_but_keeps_the_music_folder(site, tmp_path):
  save_settings({"gemini_api_key": "old-key", "music_folder": str(site["music"])})
  paths = site_backup.take_backup(EVERYTHING)
  stem = site_backup.NAME_PATTERN.match(paths[0].name).group(1)

  # The site changes after the backup: another key, another music folder, a lost file.
  new_music = tmp_path / "new-music"
  save_settings({"gemini_api_key": "new-key", "music_folder": str(new_music)})
  (site["files"] / "pictures" / "logo.png").unlink()
  (site["data"] / "api_bible_usage.json").write_text("{}")

  # Chosen in any order.
  restored = site_backup.restore_backup(upload(paths[2], paths[0], paths[1]))
  assert restored == f"the Bible database, Drupal's database and the files from {stem}"

  settings = json.loads(Path(os.environ["SERVICE_SETTINGS_FILE"]).read_text())
  assert settings == {"gemini_api_key": "old-key", "music_folder": str(new_music)}
  assert (new_music / "amazing-grace.mp4").read_bytes().startswith(b"\x00\x00\x00\x18ftyp")
  assert (site["files"] / "pictures" / "logo.png").read_bytes() == b"png"
  assert (site["data"] / "api_bible_usage.json").read_text() == '{"2026-11": 12}'
  assert site["migrations"] == [True]

  # The Bible database: one transaction, everything of ours dropped, the extensions kept and checked.
  script = (site["log"] / "psql.input").read_text()
  assert script.startswith("BEGIN;")
  assert "RAISE EXCEPTION 'The database here lacks the vector extension'" in script
  assert "DROP %s IF EXISTS" in script
  assert script.rstrip().endswith("COMMIT;")
  kept = (site["log"] / "restore.list").read_text()
  assert "EXTENSION" not in kept and "TABLE public verses" in kept

  # Drupal: emptied, loaded with the dump, brought up to date.
  calls = (site["log"] / "drush.calls").read_text().splitlines()
  assert [call.split()[0] for call in calls] == ["sql:dump", "sql:drop", "sql:cli", "updatedb", "cache:rebuild"]
  assert (site["log"] / "drupal.input").read_text().count("INSERT INTO users") == 200


def test_restore_only_the_files_zip(site, tmp_path):
  site_icons.icons_folder().mkdir(parents=True)
  (site_icons.icons_folder() / "header.png").write_bytes(b"\x89PNG\r\n\x1a\n")
  zips = by_part(site_backup.take_backup(EVERYTHING))
  (site["music"] / "amazing-grace.mp4").unlink()
  # An icon changed after the backup is put back as it was in the backup.
  (site_icons.icons_folder() / "header.png").unlink()
  (site_icons.icons_folder() / "header.svg").write_text("<svg></svg>")
  restored = site_backup.restore_backup(upload(zips["files"]))
  assert restored.startswith("the files from ") and "not chosen" in restored
  assert (site["music"] / "amazing-grace.mp4").is_file()
  assert sorted(path.name for path in site_icons.icons_folder().iterdir()) == ["header.png"]
  assert not (site["log"] / "psql.input").exists()
  assert "sql:drop" not in (site["log"] / "drush.calls").read_text()


def test_restore_only_drupals_database(site):
  zips = by_part(site_backup.take_backup({"database": True, "files": False}))
  site_backup.restore_backup(upload(zips["drupal-database"]))
  assert not (site["log"] / "psql.input").exists()
  assert site["migrations"] == []
  assert "sql:cli" in (site["log"] / "drush.calls").read_text()


def test_zips_of_different_backups_or_the_same_part_twice_are_refused(site, tmp_path):
  first = by_part(site_backup.take_backup(EVERYTHING))
  kept = tmp_path / "first-files.zip"
  kept.write_bytes(first["files"].read_bytes())
  time.sleep(1.1)
  site_backup.discard_backup()
  second = by_part(site_backup.take_backup(EVERYTHING))
  with pytest.raises(site_backup.BackupProblem, match="different backups"):
    site_backup.restore_backup(upload(kept, second["bible-database"]))
  with pytest.raises(site_backup.BackupProblem, match="choose each part once"):
    site_backup.restore_backup(upload(second["files"], second["files"]))
  assert not (site["log"] / "psql.input").exists()


def test_a_backup_made_before_the_split_is_restored_whole(site, tmp_path):
  dumps = by_part(site_backup.take_backup(EVERYTHING))
  old = tmp_path / "bible-and-beyond-2026-11-01-120000.zip"
  with zipfile.ZipFile(old, "w") as archive:
    for path in dumps.values():
      with zipfile.ZipFile(path) as part:
        for name in part.namelist():
          if name != "manifest.json":
            archive.writestr(name, part.read(name))
    archive.writestr("manifest.json", json.dumps({"format": 2, "name": old.name, "parts": EVERYTHING}))
  (site["music"] / "amazing-grace.mp4").unlink()
  assert site_backup.restore_backup(upload(old)) == f"the Bible database, Drupal's database and the files from {old.name}"
  assert (site["music"] / "amazing-grace.mp4").is_file()
  assert (site["log"] / "psql.input").exists()
  with pytest.raises(site_backup.BackupProblem, match="restore it alone"):
    site_backup.restore_backup(upload(old, dumps["files"]))


def test_damaged_or_foreign_zips_are_not_restored(site, tmp_path):
  backup = by_part(site_backup.take_backup(EVERYTHING))["files"]
  data = bytearray(backup.read_bytes())
  position = data.find(b"x" * 100)
  data[position:position + 5] = b"yyyyy"
  damaged = tmp_path / "damaged.zip"
  damaged.write_bytes(bytes(data))
  with pytest.raises(site_backup.BackupProblem, match="files/music/amazing-grace.mp4 is damaged"):
    site_backup.restore_backup(upload(damaged))

  foreign = tmp_path / "foreign.zip"
  with zipfile.ZipFile(foreign, "w") as archive:
    archive.writestr("manifest.json", json.dumps({"format": 3, "part": "files", "backup": "x"}))
    archive.writestr("files/music/../../../evil.txt", "x")
  with pytest.raises(site_backup.BackupProblem, match="unsafe name"):
    site_backup.restore_backup(upload(foreign))

  (tmp_path / "not.zip").write_text("hello")
  with pytest.raises(site_backup.BackupProblem, match="not a backup zip"):
    site_backup.restore_backup(upload(tmp_path / "not.zip"))
  assert not (site["log"] / "psql.input").exists()


def test_one_job_at_a_time_and_the_tool(site):
  site_backup._write_status("backup", "running", "Saving ...")
  with pytest.raises(site_backup.BackupProblem, match="A backup is running already"):
    site_backup.start_backup(True, True)
  upload(*site_backup.take_backup(EVERYTHING))
  with pytest.raises(site_backup.BackupProblem, match="A backup is running already"):
    site_backup.start_restore()

  completed = subprocess.run([sys.executable, str(SCRIPT), "backup"], capture_output=True, text=True)
  assert json.loads(completed.stdout) == {"ok": False, "error": "Choose Database, Files or both."}

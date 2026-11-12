"""Back up the whole site into a zip and restore it from one. Used by the Drupal "Backup and restore" page.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0. What a backup holds is described in
site_backup.py. --database and --files choose the parts (at least one).

    manage_backup.py status                                 (the last job and the zip waiting to be saved)
    manage_backup.py backup --database --files [--note=...] (starts a backup in the background)
    manage_backup.py discard                                (deletes the zip waiting to be saved)
    manage_backup.py restore --database --files             (starts restoring the uploaded zip, in the background)
    manage_backup.py discard-upload                         (deletes an uploaded zip)
    manage_backup.py clear-status                           (forgets the last finished job)

The page uploads the zip to restore into data/backup/incoming/upload.zip itself (Drupal writes it a part at
a time). From a shell, run-backup and run-restore do the work in the foreground (what the background
process runs); to restore a zip from a shell, copy it to that path first.
"""

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
# Drupal's PHP-FPM may start this with an empty environment (clear_env): give the tools it runs (pg_dump,
# drush, mariadb-dump) a search path and a home folder.
os.environ.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
os.environ.setdefault("HOME", str(Path.home()))

import site_backup  # noqa: E402


def parse_arguments():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  for name in ("status", "discard", "discard-upload", "clear-status"):
    commands.add_parser(name)
  for name in ("backup", "run-backup", "restore", "run-restore"):
    command = commands.add_parser(name)
    command.add_argument("--database", action="store_true")
    command.add_argument("--files", action="store_true")
    if "backup" in name:
      command.add_argument("--note", default="")
  return parser.parse_args()


def run(arguments) -> dict:
  command = arguments.command
  if command == "status":
    return site_backup.describe()
  if command == "discard":
    return site_backup.discard_backup()
  if command == "discard-upload":
    return site_backup.discard_upload()
  if command == "clear-status":
    site_backup.clear_status()
    return {}
  if command == "backup":
    return site_backup.start_backup(arguments.database, arguments.files, arguments.note)
  if command == "restore":
    return site_backup.start_restore(arguments.database, arguments.files)
  if command == "run-backup":
    site_backup.run_backup_job(arguments.database, arguments.files, arguments.note)
  else:
    site_backup.run_restore_job(arguments.database, arguments.files)
  return site_backup.describe()


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except site_backup.BackupProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps({"ok": True, **result}))


if __name__ == "__main__":
  main()

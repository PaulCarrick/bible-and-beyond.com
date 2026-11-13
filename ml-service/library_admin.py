"""Managing the commentaries and devotionals (the Drupal Commentaries and Devotionals pages).

List them, publish or hide one, delete one, or refresh one of the known ones (KNOWN_COMMENTARIES, DEVOTIONALS, BOOKS)
from its source. A refresh downloads for several minutes, longer than a web page may wait, so it runs in
the background: refresh() starts scripts/manage_library.py run-refresh as a separate process and returns at
once, and list_items() reports its progress from a small status file.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import commentaries
import devotionals
from search import connect

KINDS = {
  "commentary": {
    "table": "commentaries",
    "entries": "commentary_entries",
    "key": "commentary_id",
    "known": commentaries.KNOWN_COMMENTARIES,
  },
  "devotional": {
    "table": "devotionals",
    "entries": "devotional_entries",
    "key": "devotional_id",
    "known": devotionals.DEVOTIONALS,
    "collection": "devotionals",
  },
  # The Other books share the devotionals' tables, marked collection "books" (migration 017).
  "book": {
    "table": "devotionals",
    "entries": "devotional_entries",
    "key": "devotional_id",
    "known": devotionals.BOOKS,
    "collection": "books",
  },
}
DATA_DIRECTORY = Path(__file__).resolve().parent / "data"
# A refresh that has said nothing for this long is taken to have died (the server restarted, say).
REFRESH_STALE_SECONDS = 2 * 60 * 60


class LibraryProblem(ValueError):
  """The change cannot be made; the message is written for the administrator."""


def _kind(kind: str) -> dict:
  if kind not in KINDS:
    raise LibraryProblem("The kind must be commentary, devotional or book.")
  return KINDS[kind]


def _status_path(kind: str, item_id: str) -> Path:
  return DATA_DIRECTORY / "refresh" / f"{kind}-{item_id}.json"


def _write_status(kind: str, item_id: str, state: str, message: str):
  path = _status_path(kind, item_id)
  path.parent.mkdir(parents=True, exist_ok=True)
  previous = _read_status(kind, item_id) or {}
  status = {
    "state": state,
    "message": message,
    "started_at": previous.get("started_at") if state != "starting" else datetime.now(timezone.utc).isoformat(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
  }
  temporary = path.with_name(path.name + ".new")
  temporary.write_text(json.dumps(status))
  temporary.replace(path)


def _read_status(kind: str, item_id: str):
  try:
    status = json.loads(_status_path(kind, item_id).read_text())
  except (OSError, ValueError):
    return None
  if status.get("state") in ("starting", "running"):
    updated = datetime.fromisoformat(status["updated_at"])
    if (datetime.now(timezone.utc) - updated).total_seconds() > REFRESH_STALE_SECONDS:
      status = {**status, "state": "failed", "message": "It stopped without finishing (the server may have restarted)."}
  return status


def list_items(kind: str) -> list[dict]:
  """Every commentary or devotional in the database, then the known ones not loaded, with any refresh state."""
  definition = _kind(kind)
  name_column = "short_name" if kind == "commentary" else "author"
  collection = definition.get("collection")
  # Only the devotionals' table has a collection (devotionals or books); the commentaries' has none.
  where, parameters = ("WHERE t.collection = %s", (collection,)) if collection else ("", ())
  with connect() as connection:
    rows = connection.execute(
      f"""
      SELECT t.id, t.name, t.{name_column}, t.source_name, t.is_published,
             (SELECT count(*) FROM {definition['entries']} e WHERE e.{definition['key']} = t.id)
      FROM {definition['table']} t
      {where}
      ORDER BY t.position
      """,
      parameters,
    ).fetchall()
  items = [
    {
      "id": item_id, "name": name, "detail": detail, "source_name": source_name, "is_published": is_published,
      "count": count, "loaded": True, "refreshable": item_id in definition["known"],
      "refresh": _read_status(kind, item_id),
    }
    for item_id, name, detail, source_name, is_published, count in rows
  ]
  loaded = {item["id"] for item in items}
  for item_id, known in definition["known"].items():
    if item_id not in loaded:
      name = known["name"]
      detail = known["short_name"] if kind == "commentary" else known["author"]
      source_name = known["source_name"]
      items.append({
        "id": item_id, "name": name, "detail": detail, "source_name": source_name, "is_published": False,
        "count": 0, "loaded": False, "refreshable": True, "refresh": _read_status(kind, item_id),
      })
  return items


def _existing_id(connection, kind: str, item_id: str) -> str:
  definition = _kind(kind)
  collection = definition.get("collection")
  if collection:
    row = connection.execute(
      f"SELECT id FROM {definition['table']} WHERE id = %s AND collection = %s", (item_id, collection)
    ).fetchone()
  else:
    row = connection.execute(f"SELECT id FROM {definition['table']} WHERE id = %s", (item_id,)).fetchone()
  if row is None:
    raise LibraryProblem(f"There is no {kind} {item_id}.")
  return row[0]


def set_published(kind: str, item_id: str, published: bool) -> dict:
  definition = _kind(kind)
  with connect() as connection:
    _existing_id(connection, kind, item_id)
    connection.execute(f"UPDATE {definition['table']} SET is_published = %s WHERE id = %s", (published, item_id))
  return {"id": item_id, "is_published": published}


def set_credit(kind: str, item_id: str, credit: str) -> dict:
  """A devotional's or Other book's own credit line, shown instead of "... is in the public domain" (for a
  text that is not an old public-domain edition); an empty one goes back to that usual line."""
  if kind not in ("devotional", "book"):
    raise LibraryProblem("Only a devotional or an Other book has its own credit line.")
  credit = " ".join(credit.split())
  if len(credit) > 500:
    raise LibraryProblem("The credit line can be at most 500 characters.")
  with connect() as connection:
    _existing_id(connection, kind, item_id)
    connection.execute("UPDATE devotionals SET credit = %s WHERE id = %s", (credit or None, item_id))
  return {"id": item_id, "credit": credit}


# The details an administrator may change on the Edit page, by kind (not the id, which is in addresses and
# notes, and not whether a devotional is daily or by chapter, which its readings are laid out for).
EDITABLE = {
  "commentary": ("name", "short_name", "source_name", "source_url", "license_url"),
  "devotional": ("name", "author", "translator", "source_name", "source_url", "credit"),
  "book": ("name", "author", "translator", "source_name", "source_url", "credit"),
}


def get_details(kind: str, item_id: str) -> dict:
  """The details of one commentary, devotional or Other book, for its Edit page."""
  definition = _kind(kind)
  columns = EDITABLE[kind]
  with connect() as connection:
    _existing_id(connection, kind, item_id)
    row = connection.execute(
      f"SELECT {', '.join(columns)}, is_published FROM {definition['table']} WHERE id = %s", (item_id,)
    ).fetchone()
  details = {column: value or "" for column, value in zip(columns, row)}
  return {"id": item_id, **details, "is_published": row[-1], "refreshable": item_id in definition["known"]}


def update_details(kind: str, item_id: str, details: dict) -> dict:
  """Changes the name, author or short name, translator, source and credit line of one item; its text and
  its published state stay as they are. Checked as on the Upload form."""
  from library_upload import PUBLIC_DOMAIN_MARK, URL_PATTERN

  definition = _kind(kind)
  columns = EDITABLE[kind]
  cleaned = {column: " ".join(str(details.get(column) or "").split()) for column in columns}
  required = ("name", "short_name", "source_name") if kind == "commentary" else ("name", "author", "source_name")
  for column in required:
    if not cleaned[column]:
      raise LibraryProblem(f"Fill in the {column.replace('_', ' ')}.")
  for column in ("name", "author", "translator", "source_name", "short_name"):
    if column in cleaned and len(cleaned[column]) > 200:
      raise LibraryProblem(f"The {column.replace('_', ' ')} can be at most 200 characters.")
  if kind == "commentary" and len(cleaned["short_name"]) > 40:
    raise LibraryProblem("The short name can be at most 40 characters (it is used on the tabs).")
  for column in ("source_url", "license_url"):
    if cleaned.get(column) and (len(cleaned[column]) > 500 or not URL_PATTERN.match(cleaned[column])):
      raise LibraryProblem(f"The {column.replace('_', ' ')} must start with https:// or http://.")
  if kind == "commentary":
    cleaned["license_url"] = cleaned["license_url"] or PUBLIC_DOMAIN_MARK
  else:
    if len(cleaned["credit"]) > 500:
      raise LibraryProblem("The credit line can be at most 500 characters.")
    # Empty: no translator named, and the usual "... is in the public domain" line.
    cleaned["translator"] = cleaned["translator"] or None
    cleaned["credit"] = cleaned["credit"] or None
  with connect() as connection:
    _existing_id(connection, kind, item_id)
    connection.execute(
      f"UPDATE {definition['table']} SET {', '.join(f'{column} = %s' for column in columns)} WHERE id = %s",
      (*(cleaned[column] for column in columns), item_id),
    )
  return get_details(kind, item_id)


def delete(kind: str, item_id: str) -> dict:
  """Deletes the text (its notes or readings go with it). Visitors' notes on it stay; a devotional's email
  subscriptions are removed, since there is nothing left to send."""
  definition = _kind(kind)
  with connect() as connection:
    _existing_id(connection, kind, item_id)
    count = connection.execute(
      f"SELECT count(*) FROM {definition['entries']} WHERE {definition['key']} = %s", (item_id,)
    ).fetchone()[0]
    subscriptions = 0
    if kind in ("devotional", "book"):
      subscriptions = connection.execute(
        "DELETE FROM devotional_subscriptions WHERE devotional_id = %s", (item_id,)
      ).rowcount
    connection.execute(f"DELETE FROM {definition['table']} WHERE id = %s", (item_id,))
  return {"id": item_id, "deleted_count": count, "deleted_subscriptions": subscriptions}


def refresh(kind: str, item_id: str) -> dict:
  """Starts reloading a known commentary or devotional from its source, in the background."""
  definition = _kind(kind)
  if item_id not in definition["known"]:
    raise LibraryProblem(f"{item_id} was uploaded, not loaded from a known source: upload its file again instead.")
  status = _read_status(kind, item_id)
  if status and status["state"] in ("starting", "running"):
    raise LibraryProblem(f"{item_id} is being refreshed already.")
  _write_status(kind, item_id, "starting", "Starting ...")
  script = Path(__file__).resolve().parent / "scripts" / "manage_library.py"
  log = open(_status_path(kind, item_id).with_suffix(".log"), "w")
  subprocess.Popen(
    [sys.executable, str(script), "run-refresh", f"--kind={kind}", f"--id={item_id}"],
    cwd=Path(__file__).resolve().parent, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True,
  )
  return {"id": item_id, "state": "starting"}


def run_refresh(kind: str, item_id: str):
  """The background part of refresh(): download, load, tidy up, and record how it went."""
  folder = DATA_DIRECTORY / "refresh" / f"{kind}-{item_id}-download"
  started = time.monotonic()
  try:
    shutil.rmtree(folder, ignore_errors=True)
    if kind == "commentary":
      _write_status(kind, item_id, "running", "Downloading (a few minutes) ...")
      commentaries.download(folder, [item_id], report=lambda message: None)
      _write_status(kind, item_id, "running", "Loading ...")
      entries, introductions = commentaries.read_commentary(folder, item_id, commentaries.book_numbers_by_code())
      count = commentaries.replace_commentary(item_id, entries, introductions)
      message = f"Loaded {count:,} notes"
    else:  # a devotional or a book
      _write_status(kind, item_id, "running", "Downloading ...")
      devotionals.download(folder, [item_id], report=lambda message: None)
      _write_status(kind, item_id, "running", "Loading ...")
      count = devotionals.replace_devotional(item_id, devotionals.read_devotional(folder, item_id))
      message = f"Loaded {count:,} readings"
    seconds = time.monotonic() - started
    took = f"{round(seconds)} seconds" if seconds < 90 else f"{round(seconds / 60, 1)} minutes"
    _write_status(kind, item_id, "done", f"{message} in {took}.")
  except Exception as error:  # Anything that went wrong is shown on the page; the details go to the log.
    _write_status(kind, item_id, "failed", f"{type(error).__name__}: {error}"[:500])
    raise
  finally:
    shutil.rmtree(folder, ignore_errors=True)


def clear_refresh_status(kind: str, item_id: str):
  for path in (_status_path(kind, item_id), _status_path(kind, item_id).with_suffix(".log")):
    try:
      os.remove(path)
    except OSError:
      pass

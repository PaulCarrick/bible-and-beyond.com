"""My lists (added 2026-11-17 at the owner's request): a member ticks results in any search (the Bible, the
commentaries, the devotionals, the other books, the media, the maps, the FAQ in Search everything) and saves them as
a named list, or adds them to one they have. My lists (beside My notes) shows each list with its entries as the
search showed them; the search is never run again. "Copy to notes" makes one note holding the whole list, on the
list's first entry that can carry a note (a verse, a commentary note, a reading or a chapter).

An entry is kept as given: its kind, a title ("John 3:16"), a source ("BSB", a commentary's name, a book's name),
the text the search showed, and where to open it (target). Only Bibles stored on this site may be saved: the
licensed ones (NIV, NASB, The Message) must not have their text kept, so they are refused.
"""

import html
import re
from datetime import datetime, timezone

import psycopg
from psycopg.types.json import Jsonb

from notes import NoteProblem, create_note
from playlists import PlaylistProblem, export_playlists, import_playlists, list_playlists
from search import connect

NAME_LIMIT = 100
TITLE_LIMIT = 300
SOURCE_LIMIT = 200
TEXT_LIMIT = 5000
MAX_LISTS_PER_USER = 200
MAX_ITEMS_PER_LIST = 500
MAX_ITEMS_PER_SAVE = 200
# Plain text only: markup and control characters (the searches' highlight markers among them) are taken out.
TAGS = re.compile(r"<[^>]*>")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# What each kind's target holds, and its type.
TARGETS = {
  "bible": {"translation": str, "book": int, "chapter": int, "verse": int},
  "commentary": {"commentary": str, "book": int, "chapter": int, "verse": int},
  "devotional": {"devotional": str, "section": int, "unit": int},
  "book": {"devotional": str, "section": int, "unit": int},
  "music": {"song": str},
  "map": {"map": str},
  "faq": {"question": str},
}
# The note a list is copied into, kept under the notes' own limit of 10,000 characters of text.
NOTE_TEXT_ROOM = 9000


class ListProblem(Exception):
  """The request cannot be done; the text says why and is fit to show the member."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


def _plain(value, limit: int) -> str:
  text = CONTROL.sub("", TAGS.sub("", str(value or ""))).replace("\r\n", "\n").strip()
  return text[:limit]


def _name(name: str) -> str:
  name = " ".join(_plain(name, NAME_LIMIT * 2).split())
  if not name:
    raise ListProblem("Please give the list a name.")
  return name[:NAME_LIMIT]


def _checked_item(connection, item: dict) -> dict:
  kind = item.get("kind")
  if kind not in TARGETS:
    raise ListProblem("That cannot be saved in a list.")
  given = item.get("target") or {}
  target = {}
  for field, kind_of in TARGETS[kind].items():
    value = given.get(field)
    if kind_of is int:
      if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100000:
        raise ListProblem("An entry could not be read; please search again.")
    else:
      value = _plain(value, 500)
      if not value:
        raise ListProblem("An entry could not be read; please search again.")
    target[field] = value
  if kind == "bible":
    stored = connection.execute(
      "SELECT 1 FROM translations WHERE code = %s AND is_published", (target["translation"],)
    ).fetchone()
    if stored is None:
      raise ListProblem(f"Verses of the {target['translation']} cannot be saved in a list (only the Bibles kept on this site can).")
  key = kind + ":" + ":".join(str(target[field]) for field in TARGETS[kind])
  title = _plain(item.get("title"), TITLE_LIMIT)
  if not title:
    raise ListProblem("An entry could not be read; please search again.")
  return {"kind": kind, "key": key, "title": title, "source": _plain(item.get("source"), SOURCE_LIMIT), "text": _plain(item.get("text"), TEXT_LIMIT), "target": target}


def _describe_list(row) -> dict:
  # shared: on the Public lists page (when the account may share; see share_list).
  return {
    "id": row[0], "name": row[1], "count": row[2], "created_at": row[3].isoformat(), "updated_at": row[4].isoformat(),
    "shared": row[5] is not None,
  }


LIST_COLUMNS = "l.id, l.name, (SELECT count(*) FROM saved_list_items i WHERE i.list_id = l.id), l.created_at, l.updated_at, l.shared_at"


def list_lists(user_id: int) -> list[dict]:
  """The member's lists, most recently changed first."""
  with connect() as connection:
    rows = connection.execute(
      f"SELECT {LIST_COLUMNS} FROM saved_lists l WHERE l.user_id = %s ORDER BY l.updated_at DESC, l.id DESC", (user_id,)
    ).fetchall()
  return [_describe_list(row) for row in rows]


def _owned(connection, user_id: int, list_id: int):
  row = connection.execute(f"SELECT {LIST_COLUMNS} FROM saved_lists l WHERE l.id = %s AND l.user_id = %s", (list_id, user_id)).fetchone()
  if row is None:
    raise ListProblem("That list was not found.", 404)
  return row


def get_list(user_id: int, list_id: int) -> dict:
  """One of the member's lists with its entries, in the order they were added."""
  with connect() as connection:
    found = _describe_list(_owned(connection, user_id, list_id))
    rows = connection.execute(
      "SELECT id, kind, title, source, text, target, added_at FROM saved_list_items WHERE list_id = %s ORDER BY position, id",
      (list_id,),
    ).fetchall()
  found["items"] = [
    {"id": row[0], "kind": row[1], "title": row[2], "source": row[3], "text": row[4], "target": row[5], "added_at": row[6].isoformat()}
    for row in rows
  ]
  return found


def save_items(user_id: int, list_id: int | None, name: str, items: list) -> dict:
  """Saves ticked entries: into a new list called name (list_id None), or added to one of the member's lists. An
  entry the list has already is left as it is. Returns the list and how many were added."""
  if not isinstance(items, list) or not items:
    raise ListProblem("Please tick what to save.")
  if len(items) > MAX_ITEMS_PER_SAVE:
    raise ListProblem(f"At most {MAX_ITEMS_PER_SAVE} entries can be saved at once.")
  with connect() as connection:
    checked = [_checked_item(connection, item if isinstance(item, dict) else {}) for item in items]
    if list_id is None:
      name = _name(name)
      if connection.execute("SELECT count(*) FROM saved_lists WHERE user_id = %s", (user_id,)).fetchone()[0] >= MAX_LISTS_PER_USER:
        raise ListProblem(f"You have reached the limit of {MAX_LISTS_PER_USER} lists. Please delete some first.")
      if connection.execute("SELECT 1 FROM saved_lists WHERE user_id = %s AND lower(name) = lower(%s)", (user_id, name)).fetchone():
        raise ListProblem(f"You already have a list called “{name}”: choose it to add to it, or give the new one another name.")
      list_id = connection.execute("INSERT INTO saved_lists (user_id, name) VALUES (%s, %s) RETURNING id", (user_id, name)).fetchone()[0]
    else:
      _owned(connection, user_id, list_id)
    present, last = connection.execute(
      "SELECT count(*), COALESCE(max(position), 0) FROM saved_list_items WHERE list_id = %s", (list_id,)
    ).fetchone()
    added = 0
    for item in checked:
      if present + added >= MAX_ITEMS_PER_LIST:
        raise ListProblem(f"A list can hold at most {MAX_ITEMS_PER_LIST} entries.")
      row = connection.execute(
        """
        INSERT INTO saved_list_items (list_id, position, kind, item_key, title, source, text, target)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (list_id, item_key) DO NOTHING RETURNING id
        """,
        (list_id, last + added + 1, item["kind"], item["key"], item["title"], item["source"], item["text"], Jsonb(item["target"])),
      ).fetchone()
      added += row is not None
    connection.execute("UPDATE saved_lists SET updated_at = now() WHERE id = %s", (list_id,))
  return {"list": get_list(user_id, list_id), "added": added}


def rename_list(user_id: int, list_id: int, name: str) -> dict:
  name = _name(name)
  with connect() as connection:
    _owned(connection, user_id, list_id)
    try:
      connection.execute("UPDATE saved_lists SET name = %s, updated_at = now() WHERE id = %s", (name, list_id))
    except psycopg.errors.UniqueViolation:
      raise ListProblem(f"You already have a list called “{name}”.")
  return get_list(user_id, list_id)


def delete_list(user_id: int, list_id: int) -> None:
  with connect() as connection:
    _owned(connection, user_id, list_id)
    connection.execute("DELETE FROM saved_lists WHERE id = %s", (list_id,))


def remove_item(user_id: int, list_id: int, item_id: int) -> dict:
  with connect() as connection:
    _owned(connection, user_id, list_id)
    removed = connection.execute("DELETE FROM saved_list_items WHERE id = %s AND list_id = %s RETURNING id", (item_id, list_id)).fetchone()
    if removed is None:
      raise ListProblem("That entry is not in the list.", 404)
    connection.execute("UPDATE saved_lists SET updated_at = now() WHERE id = %s", (list_id,))
  return get_list(user_id, list_id)


# --- Copy to notes -------------------------------------------------------------------------------------------


def _note_place(item: dict) -> tuple | None:
  """Where a note on this entry goes (notes.create_note's item), or None for an entry that cannot carry one."""
  target = item["target"]
  if item["kind"] == "bible":
    return ("bible_verse", target["translation"], target["book"], target["chapter"], target["verse"], None, None)
  if item["kind"] == "commentary":
    return ("commentary", target["commentary"], target["book"], target["chapter"], target["verse"], None, None)
  if item["kind"] in ("devotional", "book"):
    return ("devotional", target["devotional"], None, None, None, target["section"], target["unit"])
  return None


def copy_to_note(user_id: int, list_id: int) -> dict:
  """One note holding the whole list (its name and every entry), on the list's first entry that can carry a note
  (the owner's choice). A very long list is cut to fit a note, saying how many more are in the list."""
  found = get_list(user_id, list_id)
  place = next((_note_place(item) for item in found["items"] if _note_place(item)), None)
  if place is None:
    raise ListProblem("A note needs a verse, a commentary note, a reading or a chapter to go on, and this list has none.")
  parts = [f"<p><strong>My list “{html.escape(found['name'])}”</strong></p>", "<ul>"]
  room = NOTE_TEXT_ROOM - len(found["name"])
  shown = 0
  for item in found["items"]:
    words = f"{item['title']}" + (f" ({item['source']})" if item["source"] else "") + (f": {item['text']}" if item["text"] else "")
    if len(words) > room:
      break
    room -= len(words)
    source = f" ({html.escape(item['source'])})" if item["source"] else ""
    text = f": {html.escape(item['text'])}" if item["text"] else ""
    parts.append(f"<li><strong>{html.escape(item['title'])}</strong>{source}{text}</li>")
    shown += 1
  parts.append("</ul>")
  if shown < len(found["items"]):
    more = len(found["items"]) - shown
    parts.append(f"<p>…and {more} more {'entry' if more == 1 else 'entries'} in the list.</p>")
  try:
    return create_note(user_id, *place, "".join(parts))
  except NoteProblem as problem:
    raise ListProblem(str(problem)) from problem


# --- Sharing: the Public lists page (2026-11-19) -------------------------------------------------------------

# A shared list is on Public lists while its owner may share (users.share_lists, set on Site users) and the account
# is open. Everyone who can use the site sees them; their owner is named by first name and last initial.
PUBLIC_CONDITION = "l.shared_at IS NOT NULL AND u.share_lists AND u.disabled_at IS NULL"


def _owner_name(first_name: str | None, last_name: str | None) -> str:
  first, last = (first_name or "").strip(), (last_name or "").strip()
  if not first and not last:
    return "A member"
  return f"{first} {last[:1]}.".strip() if last else first


def share_list(user: dict, list_id: int, shared: bool) -> dict:
  """Shares one of the member's lists on Public lists, or stops sharing it. Only accounts an administrator allowed."""
  if shared and not user.get("share_lists"):
    raise ListProblem("Your account cannot share lists. The site's administrators can allow it.", 403)
  with connect() as connection:
    _owned(connection, user["id"], list_id)
    connection.execute(
      "UPDATE saved_lists SET shared_at = CASE WHEN %s THEN COALESCE(shared_at, now()) END WHERE id = %s",
      (shared, list_id),
    )
  return get_list(user["id"], list_id)


def list_public_lists() -> list[dict]:
  """Every shared list, most recently changed first, with its owner's name and how many entries it holds."""
  with connect() as connection:
    rows = connection.execute(
      f"""
      SELECT {LIST_COLUMNS}, u.first_name, u.last_name FROM saved_lists l JOIN users u ON u.id = l.user_id
      WHERE {PUBLIC_CONDITION} ORDER BY l.updated_at DESC, l.id DESC
      """
    ).fetchall()
  return [{**_describe_list(row), "owner": _owner_name(row[6], row[7])} for row in rows]


def get_public_list(list_id: int) -> dict:
  """One shared list with its entries."""
  with connect() as connection:
    row = connection.execute(
      f"SELECT l.user_id, u.first_name, u.last_name FROM saved_lists l JOIN users u ON u.id = l.user_id WHERE l.id = %s AND {PUBLIC_CONDITION}",
      (list_id,),
    ).fetchone()
  if row is None:
    raise ListProblem("That list is not shared.", 404)
  return {**get_list(row[0], list_id), "owner": _owner_name(row[1], row[2])}


def _free_name(connection, user_id: int, name: str) -> str:
  """name, or "name (copy)", "name (copy 2)" ... when the member has a list called that already (not "(2)": the
  pages show each list's count in brackets after its name)."""
  taken = {
    row[0] for row in connection.execute("SELECT lower(name) FROM saved_lists WHERE user_id = %s", (user_id,)).fetchall()
  }
  candidate, number = name, 1
  while candidate.lower() in taken:
    suffix = " (copy)" if number == 1 else f" (copy {number})"
    candidate = name[: NAME_LIMIT - len(suffix)] + suffix
    number += 1
  return candidate


def _new_list(connection, user_id: int, name: str, entries: list[dict]) -> tuple[int, int]:
  """Makes a list from entries checked by _checked_item (at most MAX_ITEMS_PER_LIST; the same item once).
  Returns the new list's id and how many entries it holds."""
  if connection.execute("SELECT count(*) FROM saved_lists WHERE user_id = %s", (user_id,)).fetchone()[0] >= MAX_LISTS_PER_USER:
    raise ListProblem(f"You have reached the limit of {MAX_LISTS_PER_USER} lists. Please delete some first.")
  name = _free_name(connection, user_id, _name(name))
  list_id = connection.execute("INSERT INTO saved_lists (user_id, name) VALUES (%s, %s) RETURNING id", (user_id, name)).fetchone()[0]
  added = 0
  for item in entries[:MAX_ITEMS_PER_LIST]:
    row = connection.execute(
      """
      INSERT INTO saved_list_items (list_id, position, kind, item_key, title, source, text, target)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (list_id, item_key) DO NOTHING RETURNING id
      """,
      (list_id, added + 1, item["kind"], item["key"], item["title"], item["source"], item["text"], Jsonb(item["target"])),
    ).fetchone()
    added += row is not None
  return list_id, added


def copy_public_list(user_id: int, list_id: int) -> dict:
  """Copy to My lists: a shared list becomes one of the member's own (renamed "name (copy)" if they have that name)."""
  shared = get_public_list(list_id)
  with connect() as connection:
    entries = [_checked_item(connection, item) for item in shared["items"]]
    new_id, _ = _new_list(connection, user_id, shared["name"], entries)
  return get_list(user_id, new_id)


# --- Export and import (2026-11-19) --------------------------------------------------------------------------

EXPORT_FORMAT = "bible-and-beyond-lists"
EXPORT_VERSION = 1


def export_lists(user_id: int, list_id: int | None = None, playlist_id: int | None = None) -> dict:
  """The member's lists and playlists (or only the one list_id, or the one playlist_id) as a JSON document that
  import_lists reads back, here or on another copy of the site: each list's name and its entries as kept (kind,
  title, source, text and where to open it), and each playlist's name and songs (playlists.export_playlists)."""
  if playlist_id is not None:
    ids = []
  else:
    ids = [list_id] if list_id is not None else [each["id"] for each in reversed(list_lists(user_id))]
  lists = []
  for each in ids:
    found = get_list(user_id, each)
    lists.append({
      "name": found["name"],
      "items": [{key: item[key] for key in ("kind", "title", "source", "text", "target")} for item in found["items"]],
    })
  return {
    "format": EXPORT_FORMAT,
    "version": EXPORT_VERSION,
    "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "lists": lists,
    "playlists": _playlists_call(lambda: export_playlists(user_id, playlist_id)) if list_id is None else [],
  }


def _playlists_call(work):
  try:
    return work()
  except PlaylistProblem as problem:
    raise ListProblem(str(problem), problem.status_code) from problem


def import_lists(user_id: int, document) -> dict:
  """Adds the lists of an exported file as new lists (one called the same is renamed "name (copy)"). An entry that
  cannot be kept here (a Bible this site does not store, an entry that cannot be read) is left out and counted.
  Returns the new lists and how many entries were left out."""
  if not isinstance(document, dict) or document.get("format") != EXPORT_FORMAT:
    raise ListProblem("That is not a lists file exported from this site.")
  if not isinstance(document.get("version"), int) or document["version"] > EXPORT_VERSION:
    raise ListProblem("That lists file is from a newer version of the site and cannot be read here.")
  given = document.get("lists", [])
  given_playlists = document.get("playlists", [])
  if not isinstance(given, list) or not isinstance(given_playlists, list):
    raise ListProblem("That lists file could not be read.")
  if not given and not given_playlists:
    raise ListProblem("That lists file holds no lists or playlists.")
  if len(given) > MAX_LISTS_PER_USER:
    raise ListProblem(f"A lists file can hold at most {MAX_LISTS_PER_USER} lists.")
  made, skipped = [], 0
  with connect() as connection:
    for each in given:
      if not isinstance(each, dict) or not isinstance(each.get("items"), list):
        raise ListProblem("That lists file could not be read.")
      entries = []
      for item in each["items"][:MAX_ITEMS_PER_LIST]:
        try:
          entries.append(_checked_item(connection, item if isinstance(item, dict) else {}))
        except ListProblem:
          skipped += 1
      skipped += max(0, len(each["items"]) - MAX_ITEMS_PER_LIST)
      new_id, _ = _new_list(connection, user_id, str(each.get("name") or "Imported list"), entries)
      made.append(new_id)
    # Playlists (2026-11-21) in the same transaction, so a refused file adds nothing.
    made_playlists, skipped_songs = _playlists_call(lambda: import_playlists(connection, user_id, given_playlists))
  playlists_now = {playlist["id"]: playlist for playlist in list_playlists(user_id)}
  return {
    "lists": [get_list(user_id, each) for each in made],
    "playlists": [playlists_now[each] for each in made_playlists if each in playlists_now],
    "skipped": skipped,
    "skipped_songs": skipped_songs,
  }

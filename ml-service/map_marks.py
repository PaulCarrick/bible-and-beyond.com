"""A member's own notes, pins and routes on a map (maps.py), private or shared with members they choose.

Only accounts an administrator allowed (users.use_maps, set on the Drupal "Site users" page) can add or see them.
A mark is kept as numbers over the shared picture, not as a copy of it: x and y from 0 (left, top) to 1 (right,
bottom), so the map can be shown at any size and the member's marks drawn over it.

  note   a note on the whole map
  pin    a point (x, y) with a note
  route  a line through two or more points, with a name and a colour, and a note if wished

A mark is private to its member unless they share it with chosen members (map_mark_shares, migration 040), named
by their email address: each must be another account allowed the maps, else nothing is saved and the message names
the address. Those members then see it, read-only, with the author's name (first and last, "A member" when the
account has none). Only the author sees who it is shared with, and only the author changes or deletes it. Sharing
stops for anyone who loses the maps flag, and a mark is not shown while its author has lost it. The site never
lists its members: an address that is not a member with map access gets the same message whether or not it has an
account.

A route's points can be changed (moved, added, taken away) like the rest of it; only its kind stays.

The note is plain text (up to NOTE_LIMIT characters, line breaks kept). The verses it names ("Acts 13:4") are
found when it is sent (scripture_references.find_references), so the page links them to the Bible reader.
"""

import json
import re

from scripture_references import find_references
from search import connect

KINDS = ("note", "pin", "route")
NOTE_LIMIT = 5_000
NAME_LIMIT = 100
MAX_POINTS = 2_000
# Enough for any study; it stops one account from filling the database.
MAX_MARKS_PER_USER = 5_000
MAX_SHARES = 50
COLOURS = ("#c0392b", "#1f6fb2", "#2e8540", "#8e44ad", "#d35400", "#111111")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# The mark, whether it is the reader's own (the first %s is the reader's id) and its author's name.
COLUMNS = (
  "map_marks.id, map_marks.map_id, map_marks.kind, map_marks.x, map_marks.y, map_marks.points, map_marks.name, "
  "map_marks.colour, map_marks.body, map_marks.created_at, map_marks.updated_at, map_marks.user_id = %s, "
  "COALESCE(NULLIF(trim(concat_ws(' ', users.first_name, users.last_name)), ''), 'A member')"
)
FROM_MARKS = "map_marks JOIN users ON users.id = map_marks.user_id"
MEMBER_NAME = "COALESCE(NULLIF(trim(concat_ws(' ', first_name, last_name)), ''), 'A member')"


class MarkProblem(Exception):
  """The request cannot be done; the text says why and is fit to show the member."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


def _describe(row, shared_with: list[dict] | None) -> dict:
  mark_id, map_id, kind, x, y, points, name, colour, body, created_at, updated_at, is_mine, author = row
  return {
    "id": mark_id,
    "map_id": map_id,
    "kind": kind,
    "x": x,
    "y": y,
    "points": points,
    "name": name,
    "colour": colour,
    "body": body,
    # is_mine: the logged-in member's own (only those can be changed); author: who wrote it.
    "is_mine": is_mine,
    "author": author,
    # Who it is shared with, [{"email", "name"}], for its author only; [] on someone else's.
    "shared_with": (shared_with or []) if is_mine else [],
    # [start, end, "book:chapter:verse"] over the body, for each verse it names.
    "references": find_references(body) if body else [],
    "created_at": created_at.isoformat(),
    "updated_at": updated_at.isoformat(),
  }


def _shares_of(connection, mark_ids: list[int]) -> dict[int, list[dict]]:
  shares: dict[int, list[dict]] = {mark_id: [] for mark_id in mark_ids}
  if mark_ids:
    rows = connection.execute(
      f"""
      SELECT map_mark_shares.mark_id, users.email, {MEMBER_NAME}
      FROM map_mark_shares JOIN users ON users.id = map_mark_shares.user_id
      WHERE map_mark_shares.mark_id = ANY(%s) ORDER BY lower(users.email)
      """,
      (mark_ids,),
    ).fetchall()
    for mark_id, email, name in rows:
      shares[mark_id].append({"email": email, "name": name})
  return shares


def _coordinate(value, what: str) -> float:
  if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
    raise MarkProblem(f"The {what} must be a number from 0 to 1.")
  return float(value)


def _check(kind: str, mark: dict) -> dict:
  """The columns of a mark from what the page sent, checked for its kind."""
  if kind not in KINDS:
    raise MarkProblem("A mark is a note, a pin or a route.")
  body = CONTROL_CHARACTERS.sub("", str(mark.get("body") or "")).replace("\r\n", "\n").replace("\r", "\n").strip()
  if len(body) > NOTE_LIMIT:
    raise MarkProblem(f"The note can be at most {NOTE_LIMIT:,} characters.")
  name = " ".join(str(mark.get("name") or "").split())
  if len(name) > NAME_LIMIT:
    raise MarkProblem(f"The name can be at most {NAME_LIMIT} characters.")
  checked = {"x": None, "y": None, "points": None, "name": name, "colour": None, "body": body}
  if kind == "note":
    if not body:
      raise MarkProblem("Write something in the note.")
  elif kind == "pin":
    checked["x"] = _coordinate(mark.get("x"), "place across the map")
    checked["y"] = _coordinate(mark.get("y"), "place down the map")
  else:
    points = mark.get("points")
    if not isinstance(points, list) or len(points) < 2:
      raise MarkProblem("A route needs at least two points.")
    if len(points) > MAX_POINTS:
      raise MarkProblem(f"A route can have at most {MAX_POINTS:,} points.")
    if not all(isinstance(point, list) and len(point) == 2 for point in points):
      raise MarkProblem("A route's points could not be read.")
    checked["points"] = json.dumps([[round(_coordinate(x, "point"), 6), round(_coordinate(y, "point"), 6)] for x, y in points])
    colour = str(mark.get("colour") or COLOURS[0]).lower()
    if colour not in COLOURS:
      raise MarkProblem("Choose one of the route colours.")
    checked["colour"] = colour
    if not name:
      checked["name"] = "Route"
  return checked


def _recipients(connection, user_id: int, addresses) -> list[int] | None:
  """The accounts a mark is to be shared with, from their addresses; None when not given (the shares stay)."""
  if addresses is None:
    return None
  if not isinstance(addresses, list):
    raise MarkProblem("The members to share with could not be read.")
  wanted = []
  for address in addresses:
    address = str(address or "").strip().lower()
    if address and address not in wanted:
      wanted.append(address)
  if len(wanted) > MAX_SHARES:
    raise MarkProblem(f"A note, pin or route can be shared with at most {MAX_SHARES} members.")
  found = dict(
    connection.execute(
      "SELECT email, id FROM users WHERE email = ANY(%s) AND use_maps AND id <> %s", (wanted, user_id)
    ).fetchall()
  )
  missing = [address for address in wanted if address not in found]
  if missing:
    # The same words whether or not the address has an account, so nothing about other people is given away.
    raise MarkProblem(
      f"“{missing[0]}” is not another member who can use the maps. Check the address, or ask the site's "
      "administrator to let them use the maps."
    )
  return [found[address] for address in wanted]


def _save_shares(connection, mark_id: int, recipients: list[int] | None) -> None:
  if recipients is None:
    return
  connection.execute("DELETE FROM map_mark_shares WHERE mark_id = %s", (mark_id,))
  for recipient in recipients:
    connection.execute("INSERT INTO map_mark_shares (mark_id, user_id) VALUES (%s, %s)", (mark_id, recipient))


def _require_published(connection, map_id: str) -> None:
  if connection.execute("SELECT 1 FROM maps WHERE id = %s AND is_published", (map_id,)).fetchone() is None:
    raise MarkProblem("That map was not found.", 404)


def _get(connection, user_id: int, mark_id: int) -> dict:
  row = connection.execute(f"SELECT {COLUMNS} FROM {FROM_MARKS} WHERE map_marks.id = %s", (user_id, mark_id)).fetchone()
  return _describe(row, _shares_of(connection, [mark_id])[mark_id])


def list_marks(user_id: int, map_id: str) -> list[dict]:
  """The member's own notes, pins and routes on a published map, oldest first, then those other members shared
  with them (while the author may still use the maps)."""
  with connect() as connection:
    _require_published(connection, map_id)
    rows = connection.execute(
      f"""
      SELECT {COLUMNS} FROM {FROM_MARKS}
      WHERE map_marks.map_id = %s AND (
        map_marks.user_id = %s
        OR (users.use_maps AND EXISTS (
          SELECT 1 FROM map_mark_shares WHERE map_mark_shares.mark_id = map_marks.id AND map_mark_shares.user_id = %s
        ))
      )
      ORDER BY map_marks.user_id <> %s, map_marks.created_at, map_marks.id
      """,
      (user_id, map_id, user_id, user_id, user_id),
    ).fetchall()
    shares = _shares_of(connection, [row[0] for row in rows if row[11]])
  return [_describe(row, shares.get(row[0], [])) for row in rows]


def create_mark(user_id: int, map_id: str, kind: str, mark: dict) -> dict:
  checked = _check(kind, mark)
  with connect() as connection:
    _require_published(connection, map_id)
    recipients = _recipients(connection, user_id, mark.get("shared_with"))
    count = connection.execute("SELECT count(*) FROM map_marks WHERE user_id = %s", (user_id,)).fetchone()[0]
    if count >= MAX_MARKS_PER_USER:
      raise MarkProblem(f"An account can keep at most {MAX_MARKS_PER_USER:,} notes, pins and routes on maps.", 409)
    mark_id = connection.execute(
      """
      INSERT INTO map_marks (user_id, map_id, kind, x, y, points, name, colour, body)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
      """,
      (user_id, map_id, kind, checked["x"], checked["y"], checked["points"], checked["name"], checked["colour"], checked["body"]),
    ).fetchone()[0]
    _save_shares(connection, mark_id, recipients)
    return _get(connection, user_id, mark_id)


def update_mark(user_id: int, mark_id: int, mark: dict) -> dict:
  """Changes one of the member's own marks (its kind stays), and who it is shared with when that is given; another
  member's is "not found", even one shared with them."""
  with connect() as connection:
    found = connection.execute("SELECT kind FROM map_marks WHERE id = %s AND user_id = %s", (mark_id, user_id)).fetchone()
    if found is None:
      raise MarkProblem("That note, pin or route was not found.", 404)
    checked = _check(found[0], mark)
    recipients = _recipients(connection, user_id, mark.get("shared_with"))
    connection.execute(
      """
      UPDATE map_marks SET x = %s, y = %s, points = %s, name = %s, colour = %s, body = %s, updated_at = now()
      WHERE id = %s AND user_id = %s
      """,
      (checked["x"], checked["y"], checked["points"], checked["name"], checked["colour"], checked["body"], mark_id, user_id),
    )
    _save_shares(connection, mark_id, recipients)
    return _get(connection, user_id, mark_id)


def delete_mark(user_id: int, mark_id: int) -> None:
  with connect() as connection:
    deleted = connection.execute("DELETE FROM map_marks WHERE id = %s AND user_id = %s RETURNING id", (mark_id, user_id)).fetchone()
  if deleted is None:
    raise MarkProblem("That note, pin or route was not found.", 404)

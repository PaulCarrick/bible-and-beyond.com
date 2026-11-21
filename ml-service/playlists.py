"""Playlists: a logged-in visitor's own lists of songs from the Christian music section.

A user has many playlists, each a name and its songs in order (migration 025). The music page saves the songs
ticked there under a name and plays a playlist's songs one after another. Saving under a name the visitor
already uses (in any case) replaces that playlist's songs, so a playlist is changed by saving it again. Only
published songs can be put in a playlist, and only the published ones are listed back: a song hidden later
stays in the playlist and comes back when it is published again; a deleted song leaves every playlist.
"""

import re

from search import connect

NAME_LIMIT = 100
# Enough for anyone; they stop one account from filling the database.
MAX_PLAYLISTS_PER_USER = 100
MAX_SONGS_PER_PLAYLIST = 500
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class PlaylistProblem(Exception):
  """The request cannot be done; the text says why and is fit to show the visitor."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


def check_name(name: str) -> str:
  name = " ".join((name or "").split())
  if not name:
    raise PlaylistProblem("Please give the playlist a name.")
  if len(name) > NAME_LIMIT:
    raise PlaylistProblem(f"A playlist name can be at most {NAME_LIMIT} characters.")
  if CONTROL_CHARACTERS.search(name):
    raise PlaylistProblem("A playlist name cannot contain control characters.")
  return name


def _published_songs(connection, playlist_ids: list[int]) -> dict[int, list[str]]:
  """The published songs of each playlist, in order."""
  songs = {playlist_id: [] for playlist_id in playlist_ids}
  if not playlist_ids:
    return songs
  rows = connection.execute(
    """
    SELECT playlist_songs.playlist_id, playlist_songs.song_id
    FROM playlist_songs JOIN music_tracks ON music_tracks.id = playlist_songs.song_id
    WHERE playlist_songs.playlist_id = ANY(%s) AND music_tracks.is_published
    ORDER BY playlist_songs.playlist_id, playlist_songs.position
    """,
    (playlist_ids,),
  ).fetchall()
  for playlist_id, song_id in rows:
    songs[playlist_id].append(song_id)
  return songs


def _describe(row, song_ids: list[str]) -> dict:
  return {
    "id": row[0],
    "name": row[1],
    "song_ids": song_ids,
    "created_at": row[2].isoformat(),
    "updated_at": row[3].isoformat(),
    # On the Public lists page (while the account may share; see share_playlist).
    "shared": row[4] is not None,
  }


PLAYLIST_COLUMNS = "id, name, created_at, updated_at, shared_at"


def list_playlists(user_id: int) -> list[dict]:
  """The visitor's playlists by name, each with its published songs in order."""
  with connect() as connection:
    rows = connection.execute(
      f"SELECT {PLAYLIST_COLUMNS} FROM playlists WHERE user_id = %s ORDER BY lower(name), id",
      (user_id,),
    ).fetchall()
    songs = _published_songs(connection, [row[0] for row in rows])
  return [_describe(row, songs[row[0]]) for row in rows]


def save_playlist(user_id: int, name: str, song_ids: list[str]) -> tuple[dict, bool]:
  """Saves the songs (in the order given; a repeat is dropped) under the name. (playlist, whether an existing
  playlist of that name was replaced)."""
  name = check_name(name)
  ordered = list(dict.fromkeys(song_ids))
  if not ordered:
    raise PlaylistProblem("Please tick at least one song for the playlist.")
  if len(ordered) > MAX_SONGS_PER_PLAYLIST:
    raise PlaylistProblem(f"A playlist can have at most {MAX_SONGS_PER_PLAYLIST} songs.")
  with connect() as connection:
    with connection.transaction():
      published = {
        row[0]
        for row in connection.execute(
          # Spotify items are never in a playlist: the site cannot tell when Spotify's player ends a track.
          "SELECT id FROM music_tracks WHERE id = ANY(%s) AND is_published AND media_type <> 'spotify'", (ordered,)
        ).fetchall()
      }
      if len(published) != len(ordered):
        raise PlaylistProblem("One of those songs is no longer on the site. Please reload the page and try again.")
      # Lock the visitor's playlists, so two saves at once cannot pass the limit or clash on the name.
      existing = connection.execute(
        "SELECT id, lower(name) FROM playlists WHERE user_id = %s FOR UPDATE", (user_id,)
      ).fetchall()
      same_name = [row[0] for row in existing if row[1] == name.lower()]
      if same_name:
        playlist_id = same_name[0]
        connection.execute(
          "UPDATE playlists SET name = %s, updated_at = now() WHERE id = %s", (name, playlist_id)
        )
        connection.execute("DELETE FROM playlist_songs WHERE playlist_id = %s", (playlist_id,))
      else:
        if len(existing) >= MAX_PLAYLISTS_PER_USER:
          raise PlaylistProblem(
            f"You can keep at most {MAX_PLAYLISTS_PER_USER} playlists. Please delete one first.", 409
          )
        playlist_id = connection.execute(
          "INSERT INTO playlists (user_id, name) VALUES (%s, %s) RETURNING id", (user_id, name)
        ).fetchone()[0]
      with connection.cursor() as cursor:
        cursor.executemany(
          "INSERT INTO playlist_songs (playlist_id, position, song_id) VALUES (%s, %s, %s)",
          [(playlist_id, position, song_id) for position, song_id in enumerate(ordered, start=1)],
        )
      row = connection.execute(
        f"SELECT {PLAYLIST_COLUMNS} FROM playlists WHERE id = %s", (playlist_id,)
      ).fetchone()
  return _describe(row, ordered), bool(same_name)


def delete_playlist(user_id: int, playlist_id: int) -> None:
  """Deletes one of the visitor's own playlists; anyone else's is "not found"."""
  with connect() as connection:
    deleted = connection.execute(
      "DELETE FROM playlists WHERE id = %s AND user_id = %s RETURNING id", (playlist_id, user_id)
    ).fetchone()
  if deleted is None:
    raise PlaylistProblem("That playlist was not found.", 404)


# --- Sharing: shared playlists on the Public lists page (2026-11-21) -------------------------------------------

# Like My lists (saved_lists.PUBLIC_CONDITION): a shared playlist is shown while its owner may share
# (users.share_lists, "Can share lists" on Site users) and the account is open. Everyone who can use the site sees
# them, with the owner named by first name and last initial.
PUBLIC_CONDITION = "p.shared_at IS NOT NULL AND u.share_lists AND u.disabled_at IS NULL"


def _owner_name(first_name: str | None, last_name: str | None) -> str:
  first, last = (first_name or "").strip(), (last_name or "").strip()
  if not first and not last:
    return "A member"
  return f"{first} {last[:1]}.".strip() if last else first


def share_playlist(user: dict, playlist_id: int, shared: bool) -> dict:
  """Shares one of the member's playlists on Public lists, or stops sharing it (stopping is always allowed)."""
  if shared and not user.get("share_lists"):
    raise PlaylistProblem("Your account cannot share playlists. The site's administrators can allow it.", 403)
  with connect() as connection:
    row = connection.execute(
      f"""
      UPDATE playlists SET shared_at = CASE WHEN %s THEN COALESCE(shared_at, now()) END
      WHERE id = %s AND user_id = %s RETURNING {PLAYLIST_COLUMNS}
      """,
      (shared, playlist_id, user["id"]),
    ).fetchone()
    if row is None:
      raise PlaylistProblem("That playlist was not found.", 404)
    songs = _published_songs(connection, [playlist_id])
  return _describe(row, songs[playlist_id])


def _song_details(connection, song_ids: list[str]) -> list[dict]:
  """Each song's id, title and author, in the order given."""
  rows = connection.execute("SELECT id, title, author FROM music_tracks WHERE id = ANY(%s)", (song_ids,)).fetchall()
  found = {row[0]: {"id": row[0], "title": row[1], "author": row[2] or ""} for row in rows}
  return [found[song_id] for song_id in song_ids if song_id in found]


def list_public_playlists() -> list[dict]:
  """Every shared playlist, most recently changed first, with its owner's name and its published songs in order."""
  with connect() as connection:
    rows = connection.execute(
      f"""
      SELECT p.id, p.name, p.created_at, p.updated_at, p.shared_at, u.first_name, u.last_name
      FROM playlists p JOIN users u ON u.id = p.user_id
      WHERE {PUBLIC_CONDITION} ORDER BY p.updated_at DESC, p.id DESC
      """
    ).fetchall()
    songs = _published_songs(connection, [row[0] for row in rows])
  return [{**_describe(row, songs[row[0]]), "owner": _owner_name(row[5], row[6])} for row in rows]


def get_public_playlist(playlist_id: int) -> dict:
  """One shared playlist, with its published songs' titles and authors (for the Public lists page)."""
  with connect() as connection:
    row = connection.execute(
      f"""
      SELECT p.id, p.name, p.created_at, p.updated_at, p.shared_at, u.first_name, u.last_name
      FROM playlists p JOIN users u ON u.id = p.user_id WHERE p.id = %s AND {PUBLIC_CONDITION}
      """,
      (playlist_id,),
    ).fetchone()
    if row is None:
      raise PlaylistProblem("That playlist is not shared.", 404)
    song_ids = _published_songs(connection, [playlist_id])[playlist_id]
    songs = _song_details(connection, song_ids)
  return {**_describe(row, song_ids), "owner": _owner_name(row[5], row[6]), "songs": songs}


def _free_name(connection, user_id: int, name: str) -> str:
  """name, or "name (copy)", "name (copy 2)" ... when the visitor has a playlist called that already (a copy never
  replaces one of their own)."""
  taken = {row[0] for row in connection.execute("SELECT lower(name) FROM playlists WHERE user_id = %s", (user_id,)).fetchall()}
  candidate, number = name, 1
  while candidate.lower() in taken:
    suffix = " (copy)" if number == 1 else f" (copy {number})"
    candidate = name[: NAME_LIMIT - len(suffix)] + suffix
    number += 1
  return candidate


def copy_public_playlist(user_id: int, playlist_id: int) -> dict:
  """Copy to my playlists: a shared playlist becomes one of the visitor's own (not shared), under a free name."""
  shared = get_public_playlist(playlist_id)
  playable = [song["id"] for song in shared["songs"]]
  if not playable:
    raise PlaylistProblem("That playlist has no songs on the site now.")
  with connect() as connection:
    name = _free_name(connection, user_id, shared["name"])
  playlist, _ = save_playlist(user_id, name, playable)
  return playlist


# --- Export and import (2026-11-21), through My lists' file (saved_lists.export_lists and import_lists) -------


def export_playlists(user_id: int, playlist_id: int | None = None) -> list[dict]:
  """The visitor's playlists (or the one playlist_id) for the lists file: each name and its published songs in
  order, by id with title and author (so another copy of the site can find a song by its title when the id differs)."""
  if playlist_id is not None:
    with connect() as connection:
      if connection.execute("SELECT 1 FROM playlists WHERE id = %s AND user_id = %s", (playlist_id, user_id)).fetchone() is None:
        raise PlaylistProblem("That playlist was not found.", 404)
  exported = []
  with connect() as connection:
    for playlist in list_playlists(user_id):
      if playlist_id is not None and playlist["id"] != playlist_id:
        continue
      exported.append({"name": playlist["name"], "songs": _song_details(connection, playlist["song_ids"])})
  return exported


def import_playlists(connection, user_id: int, given: list) -> tuple[list[int], int]:
  """Adds the playlists of a lists file as new playlists (a name already used gets "(copy)"), inside the caller's
  transaction. Each song is found by its id, else by its title (in any case); a song that is not published here (or
  is a Spotify item) is left out and counted, and a playlist left with no songs is not made.
  Returns the new playlists' ids and how many songs were left out."""
  if not isinstance(given, list):
    raise PlaylistProblem("That lists file could not be read.")
  playable = connection.execute(
    "SELECT id, lower(title) FROM music_tracks WHERE is_published AND media_type <> 'spotify' ORDER BY id"
  ).fetchall()
  by_id = {row[0] for row in playable}
  by_title = {}
  for song_id, title in playable:
    by_title.setdefault(title, song_id)
  count = connection.execute("SELECT count(*) FROM playlists WHERE user_id = %s", (user_id,)).fetchone()[0]
  made, skipped = [], 0
  for each in given:
    if not isinstance(each, dict) or not isinstance(each.get("songs"), list):
      raise PlaylistProblem("That lists file could not be read.")
    song_ids = []
    for song in each["songs"][:MAX_SONGS_PER_PLAYLIST]:
      song = song if isinstance(song, dict) else {}
      found = song.get("id") if song.get("id") in by_id else by_title.get(str(song.get("title") or "").lower())
      if found is None:
        skipped += 1
      elif found not in song_ids:
        song_ids.append(found)
    skipped += max(0, len(each["songs"]) - MAX_SONGS_PER_PLAYLIST)
    if not song_ids:
      continue
    if count >= MAX_PLAYLISTS_PER_USER:
      raise PlaylistProblem(f"You can keep at most {MAX_PLAYLISTS_PER_USER} playlists. Please delete some first.", 409)
    name = _free_name(connection, user_id, check_name(str(each.get("name") or "Imported playlist")))
    playlist_id = connection.execute(
      "INSERT INTO playlists (user_id, name) VALUES (%s, %s) RETURNING id", (user_id, name)
    ).fetchone()[0]
    with connection.cursor() as cursor:
      cursor.executemany(
        "INSERT INTO playlist_songs (playlist_id, position, song_id) VALUES (%s, %s, %s)",
        [(playlist_id, position, song_id) for position, song_id in enumerate(song_ids, start=1)],
      )
    made.append(playlist_id)
    count += 1
  return made, skipped

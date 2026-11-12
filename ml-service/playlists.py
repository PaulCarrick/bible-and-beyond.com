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
  }


def list_playlists(user_id: int) -> list[dict]:
  """The visitor's playlists by name, each with its published songs in order."""
  with connect() as connection:
    rows = connection.execute(
      "SELECT id, name, created_at, updated_at FROM playlists WHERE user_id = %s ORDER BY lower(name), id",
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
          "SELECT id FROM music_tracks WHERE id = ANY(%s) AND is_published", (ordered,)
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
        "SELECT id, name, created_at, updated_at FROM playlists WHERE id = %s", (playlist_id,)
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

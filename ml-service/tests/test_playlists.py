"""Tests for playlists. They use the real tables with their own songs and users, and remove both after
(deleting the users removes their playlists)."""

import pytest
from fastapi.testclient import TestClient

import accounts
import playlists
from main import app
from search import connect

PASSWORD = "correct horse battery"
client = TestClient(app)
SONGS = ["playlists-test-a", "playlists-test-b", "playlists-test-c"]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)

  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM users WHERE email LIKE '%@playlists-test.example'")
      connection.execute("DELETE FROM music_tracks WHERE id LIKE 'playlists-test-%'")

  clear()
  with connect() as connection:
    for song_id in SONGS:
      connection.execute(
        """
        INSERT INTO music_tracks (id, title, file_name, media_type, file_size, is_published)
        VALUES (%s, %s, %s, 'audio/mpeg', 1, true)
        """,
        (song_id, song_id.title(), f"{song_id}.mp3"),
      )
  client.cookies.clear()
  yield
  clear()


def sign_up(name="ann"):
  client.cookies.clear()
  response = client.post(
    "/account/register",
    json={"email": f"{name}@playlists-test.example", "password": PASSWORD, "password_confirmation": PASSWORD},
  )
  assert response.status_code == 200
  return response.json()["user"]["id"]


def save(name, song_ids):
  return client.post("/playlists", json={"name": name, "song_ids": song_ids})


def test_playlists_need_a_login():
  assert client.get("/playlists").status_code == 401
  assert save("Sunday", SONGS).status_code == 401
  assert client.delete("/playlists/1").status_code == 401


def test_a_playlist_is_saved_with_its_songs_in_order_and_listed():
  sign_up()

  response = save("  Sunday   morning ", ["playlists-test-c", "playlists-test-a", "playlists-test-c"])

  assert response.status_code == 200
  playlist = response.json()["playlist"]
  assert response.json()["replaced"] is False
  assert playlist["name"] == "Sunday morning"
  assert playlist["song_ids"] == ["playlists-test-c", "playlists-test-a"]
  assert client.get("/playlists").json()["playlists"] == [playlist]


def test_saving_under_a_name_already_used_replaces_that_playlist():
  sign_up()
  first = save("Sunday", SONGS).json()["playlist"]

  response = save("SUNDAY", ["playlists-test-b"])

  assert response.json()["replaced"] is True
  listed = client.get("/playlists").json()["playlists"]
  assert [(entry["id"], entry["name"], entry["song_ids"]) for entry in listed] == [(first["id"], "SUNDAY", ["playlists-test-b"])]


def test_bad_names_and_songs_are_refused():
  sign_up()
  with connect() as connection:
    connection.execute("UPDATE music_tracks SET is_published = false WHERE id = 'playlists-test-c'")

  assert save("   ", SONGS[:1]).status_code == 422
  assert save("x" * 101, SONGS[:1]).status_code == 422
  assert save("Empty", []).status_code == 422
  assert save("Unknown", ["playlists-test-none"]).status_code == 422
  assert save("Hidden", ["playlists-test-c"]).status_code == 422
  assert client.get("/playlists").json()["playlists"] == []


def test_a_hidden_song_is_left_out_and_a_deleted_song_leaves_the_playlist():
  sign_up()
  save("All", SONGS)
  with connect() as connection:
    connection.execute("UPDATE music_tracks SET is_published = false WHERE id = 'playlists-test-b'")
    connection.execute("DELETE FROM music_tracks WHERE id = 'playlists-test-c'")

  assert client.get("/playlists").json()["playlists"][0]["song_ids"] == ["playlists-test-a"]

  with connect() as connection:
    connection.execute("UPDATE music_tracks SET is_published = true WHERE id = 'playlists-test-b'")
  assert client.get("/playlists").json()["playlists"][0]["song_ids"] == ["playlists-test-a", "playlists-test-b"]


def test_only_the_owner_sees_or_deletes_a_playlist():
  sign_up("ann")
  playlist = save("Mine", SONGS).json()["playlist"]
  sign_up("bob")

  assert client.get("/playlists").json()["playlists"] == []
  assert client.delete(f"/playlists/{playlist['id']}").status_code == 404

  client.cookies.clear()
  client.post("/account/login", json={"email": "ann@playlists-test.example", "password": PASSWORD})
  assert client.delete(f"/playlists/{playlist['id']}").status_code == 200
  assert client.get("/playlists").json()["playlists"] == []


def test_an_account_can_keep_only_so_many_playlists(monkeypatch):
  monkeypatch.setattr(playlists, "MAX_PLAYLISTS_PER_USER", 2)
  sign_up()
  save("One", SONGS)
  save("Two", SONGS)

  assert save("Three", SONGS).status_code == 409
  # Replacing one is still allowed.
  assert save("two", SONGS[:1]).status_code == 200


def test_deleting_the_user_deletes_their_playlists():
  user_id = sign_up()
  save("Mine", SONGS)

  with connect() as connection:
    connection.execute("DELETE FROM users WHERE id = %s", (user_id,))
    count = connection.execute("SELECT count(*) FROM playlists WHERE user_id = %s", (user_id,)).fetchone()[0]

  assert count == 0


def test_a_spotify_item_cannot_go_in_a_playlist():
  import music

  sign_up()
  music.add_spotify("playlists-test-spotify", "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", {"title": "Spotify list"})
  music.set_published("playlists-test-spotify", True)
  try:
    answer = save("With Spotify", ["playlists-test-spotify"])
    assert answer.status_code == 422
  finally:
    music.delete("playlists-test-spotify")


# --- Sharing on Public lists (2026-11-21) ---


def allow_sharing(user_id, allowed=True):
  with connect() as connection:
    connection.execute("UPDATE users SET share_lists = %s WHERE id = %s", (allowed, user_id))


def test_only_accounts_allowed_to_share_can_share_and_everyone_sees_shared_playlists():
  ann = sign_up("ann")
  playlist_id = save("Sunday", ["playlists-test-b", "playlists-test-a"]).json()["playlist"]["id"]
  assert client.get("/playlists").json()["playlists"][0]["shared"] is False

  refused = client.put(f"/playlists/{playlist_id}/shared", json={"shared": True})
  assert refused.status_code == 403 and "cannot share playlists" in refused.json()["detail"]

  allow_sharing(ann)
  shared = client.put(f"/playlists/{playlist_id}/shared", json={"shared": True})
  assert shared.status_code == 200 and shared.json()["playlist"]["shared"] is True
  assert client.get("/playlists").json()["playlists"][0]["shared"] is True
  # Saving it again (Edit, Change) keeps it shared.
  save("Sunday", ["playlists-test-a"])
  assert client.get("/playlists").json()["playlists"][0]["shared"] is True
  save("Sunday", ["playlists-test-b", "playlists-test-a"])

  # A visitor who is not logged in sees it and its songs, with the owner named by first name and last initial.
  with connect() as connection:
    connection.execute("UPDATE users SET first_name = 'Ann', last_name = 'Lee' WHERE id = %s", (ann,))
  client.cookies.clear()
  public = [each for each in client.get("/public-playlists").json()["playlists"] if each["id"] == playlist_id]
  assert len(public) == 1 and public[0]["owner"] == "Ann L." and public[0]["song_ids"] == ["playlists-test-b", "playlists-test-a"]
  opened = client.get(f"/public-playlists/{playlist_id}").json()["playlist"]
  assert opened["name"] == "Sunday" and [song["title"] for song in opened["songs"]] == ["Playlists-Test-B", "Playlists-Test-A"]
  assert client.post(f"/public-playlists/{playlist_id}/copy").status_code == 401
  assert client.put(f"/playlists/{playlist_id}/shared", json={"shared": False}).status_code == 401

  # Another visitor copies it into their own playlists, renamed when they have one of that name; it is not shared.
  sign_up("bob")
  save("Sunday", ["playlists-test-c"])
  copied = client.post(f"/public-playlists/{playlist_id}/copy").json()["playlist"]
  assert copied["name"] == "Sunday (copy)" and copied["song_ids"] == ["playlists-test-b", "playlists-test-a"]
  assert copied["shared"] is False
  # Bob cannot share or unshare Ann's playlist.
  assert client.put(f"/playlists/{playlist_id}/shared", json={"shared": False}).status_code == 404


def test_a_playlist_leaves_public_lists_when_unshared_or_the_owner_may_no_longer_share():
  ann = sign_up("ann")
  allow_sharing(ann)
  playlist_id = save("Evening", ["playlists-test-a"]).json()["playlist"]["id"]
  client.put(f"/playlists/{playlist_id}/shared", json={"shared": True})
  assert client.get(f"/public-playlists/{playlist_id}").status_code == 200

  allow_sharing(ann, False)
  assert client.get(f"/public-playlists/{playlist_id}").status_code == 404
  assert all(each["id"] != playlist_id for each in client.get("/public-playlists").json()["playlists"])
  # Stopping is always allowed, even without the permission.
  assert client.put(f"/playlists/{playlist_id}/shared", json={"shared": False}).status_code == 200
  allow_sharing(ann)
  assert client.get(f"/public-playlists/{playlist_id}").status_code == 404
  assert client.get("/public-playlists/999999999").status_code == 404

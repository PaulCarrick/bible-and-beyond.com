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

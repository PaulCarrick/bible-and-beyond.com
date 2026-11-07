"""Tests for notes. They use the real tables and remove their own users (and so their notes) after."""

import pytest
from fastapi.testclient import TestClient

import accounts
from main import app
from search import connect

PASSWORD = "correct horse battery"
client = TestClient(app)
VERSE = {"item_type": "bible_verse", "source_code": "BSB", "book_number": 43, "chapter": 3, "verse": 16, "body": "<p>My <strong>note</strong></p>"}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)

  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM users WHERE email LIKE '%@notes-test.example'")

  clear()
  client.cookies.clear()
  yield
  clear()


def sign_up(name="ann"):
  response = client.post(
    "/account/register",
    json={"email": f"{name}@notes-test.example", "password": PASSWORD, "password_confirmation": PASSWORD},
  )
  assert response.status_code == 200
  return response.json()["user"]["id"]


def test_notes_need_a_login():
  assert client.post("/notes", json=VERSE).status_code == 401
  assert client.get("/notes").status_code == 401


def test_a_note_on_a_verse_is_saved_with_the_time_and_listed():
  sign_up()

  response = client.post("/notes", json=VERSE)

  assert response.status_code == 200
  note = response.json()["note"]
  assert note["item_type"] == "bible_verse" and (note["book_number"], note["chapter"], note["verse"]) == (43, 3, 16)
  assert note["body"] == "<p>My <strong>note</strong></p>"
  assert note["created_at"] == note["updated_at"] and "T" in note["created_at"]
  listed = client.get("/notes", params={"item_type": "bible_verse", "book_number": 43, "chapter": 3, "verse": 16}).json()["notes"]
  assert [entry["id"] for entry in listed] == [note["id"]]


def test_the_note_is_cleaned_before_it_is_kept():
  sign_up()

  note = client.post("/notes", json={**VERSE, "body": '<p onclick="x()">Hi<script>alert(1)</script></p><a href="javascript:x">y</a>'}).json()["note"]

  assert "script" not in note["body"] and "onclick" not in note["body"] and "javascript" not in note["body"]
  assert "Hi" in note["body"]


def test_notes_come_newest_first_and_a_verse_matches_whatever_the_bible():
  sign_up()
  first = client.post("/notes", json=VERSE).json()["note"]
  second = client.post("/notes", json={**VERSE, "source_code": "KJV", "body": "<p>Second</p>"}).json()["note"]
  client.post("/notes", json={**VERSE, "verse": 17, "body": "<p>Other verse</p>"})

  everything = client.get("/notes").json()["notes"]
  one_verse = client.get("/notes", params={"item_type": "bible_verse", "book_number": 43, "chapter": 3, "verse": 16}).json()["notes"]

  assert len(everything) == 3
  assert [entry["id"] for entry in one_verse] == [second["id"], first["id"]]


def test_a_visitor_sees_only_their_own_notes():
  sign_up("ann")
  client.post("/notes", json=VERSE)
  client.cookies.clear()
  sign_up("bob")

  assert client.get("/notes").json()["notes"] == []


def test_commentary_and_devotional_notes_are_kept_apart_by_their_source():
  sign_up()
  client.post("/notes", json={**VERSE, "item_type": "commentary", "source_code": "matthew-henry", "body": "<p>On Henry</p>"})
  client.post("/notes", json={"item_type": "devotional", "source_code": "morning-and-evening", "section": 1, "unit": 5, "body": "<p>Devotion</p>"})

  henry = client.get("/notes", params={"item_type": "commentary", "source_code": "matthew-henry", "book_number": 43, "chapter": 3, "verse": 16}).json()["notes"]
  gill = client.get("/notes", params={"item_type": "commentary", "source_code": "gill", "book_number": 43, "chapter": 3, "verse": 16}).json()["notes"]
  devotional = client.get("/notes", params={"item_type": "devotional", "source_code": "morning-and-evening", "section": 1, "unit": 5}).json()["notes"]

  assert len(henry) == 1 and gill == [] and len(devotional) == 1
  assert devotional[0]["book_number"] is None and devotional[0]["section"] == 1


@pytest.mark.parametrize(
  "changes, fragment",
  [
    ({"book_number": 99}, "book"),
    ({"verse": 0}, "chapter and verse"),
    ({"source_code": "not valid!"}, "which Bible"),
    ({"section": 1}, "no section"),
    ({"body": "<p><br></p>"}, "write something"),
    ({"body": "<p>" + "x" * 10001 + "</p>"}, "10000"),
  ],
)
def test_a_bad_note_is_refused_and_nothing_is_saved(changes, fragment):
  sign_up()

  response = client.post("/notes", json={**VERSE, **changes})

  assert response.status_code == 422 and fragment in response.json()["detail"]
  assert client.get("/notes").json()["notes"] == []


def test_the_type_decides_which_fields_belong():
  sign_up()

  assert client.post("/notes", json={"item_type": "devotional", "source_code": "x", "section": 1, "unit": 1, "chapter": 2, "body": "<p>a</p>"}).status_code == 422
  assert client.post("/notes", json={"item_type": "devotional", "source_code": "x", "body": "<p>a</p>"}).status_code == 422
  assert client.post("/notes", json={**VERSE, "item_type": "poem"}).status_code == 422


def test_deleting_a_user_deletes_their_notes():
  user_id = sign_up()
  client.post("/notes", json=VERSE)

  with connect() as connection:
    connection.execute("DELETE FROM users WHERE id = %s", (user_id,))
    assert connection.execute("SELECT count(*) FROM notes WHERE user_id = %s", (user_id,)).fetchone()[0] == 0

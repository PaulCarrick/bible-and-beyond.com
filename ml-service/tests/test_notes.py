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
    json={
      "email": f"{name}@notes-test.example",
      "password": PASSWORD,
      "password_confirmation": PASSWORD,
      "first_name": name.title(),
      "last_name": "Test",
    },
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


def test_a_note_has_a_title_that_says_what_it_is_about():
  sign_up()

  verse = client.post("/notes", json=VERSE).json()["note"]
  commentary = client.post("/notes", json={**VERSE, "item_type": "commentary", "source_code": "matthew-henry"}).json()["note"]
  devotional = client.post("/notes", json={"item_type": "devotional", "source_code": "morning-and-evening", "section": 1, "unit": 5, "body": "<p>a</p>"}).json()["note"]

  assert verse["title"] == "John 3:16"
  assert commentary["title"].startswith("John 3:16") and "(" in commentary["title"]
  assert devotional["title"] and "(" in devotional["title"]
  assert all(entry["title"] for entry in client.get("/notes").json()["notes"])


def test_a_note_can_be_edited_and_the_change_time_moves_on():
  sign_up()
  note = client.post("/notes", json=VERSE).json()["note"]

  response = client.put(f"/notes/{note['id']}", json={"body": "<p>Changed <em>text</em><script>x()</script></p>"})

  assert response.status_code == 200
  changed = response.json()["note"]
  assert changed["id"] == note["id"] and changed["created_at"] == note["created_at"]
  assert changed["updated_at"] > note["updated_at"]
  assert "Changed" in changed["body"] and "script" not in changed["body"] and changed["title"] == "John 3:16"
  assert client.get("/notes").json()["notes"][0]["body"] == changed["body"]


def test_an_edit_must_still_be_a_good_note_and_leaves_the_old_one_alone():
  sign_up()
  note = client.post("/notes", json=VERSE).json()["note"]

  assert client.put(f"/notes/{note['id']}", json={"body": "<p><br></p>"}).status_code == 422
  assert client.put(f"/notes/{note['id']}", json={"body": "<p>" + "x" * 10001 + "</p>"}).status_code == 422
  assert client.get("/notes").json()["notes"][0]["body"] == note["body"]


def test_a_note_can_be_deleted():
  sign_up()
  note = client.post("/notes", json=VERSE).json()["note"]

  assert client.delete(f"/notes/{note['id']}").status_code == 200
  assert client.get("/notes").json()["notes"] == []
  assert client.delete(f"/notes/{note['id']}").status_code == 404


def test_nobody_can_change_or_delete_another_visitors_note():
  sign_up("ann")
  note = client.post("/notes", json=VERSE).json()["note"]
  client.cookies.clear()
  sign_up("bob")

  assert client.put(f"/notes/{note['id']}", json={"body": "<p>Mine now</p>"}).status_code == 404
  assert client.delete(f"/notes/{note['id']}").status_code == 404
  client.cookies.clear()
  client.post("/account/login", json={"email": "ann@notes-test.example", "password": PASSWORD})
  assert client.get("/notes").json()["notes"][0]["body"] == note["body"]


def test_editing_and_deleting_need_a_login():
  assert client.put("/notes/1", json={"body": "<p>a</p>"}).status_code == 401
  assert client.delete("/notes/1").status_code == 401


def test_one_account_cannot_keep_unlimited_notes(monkeypatch):
  import notes

  monkeypatch.setattr(notes, "MAX_NOTES_PER_USER", 2)
  sign_up()
  assert client.post("/notes", json=VERSE).status_code == 200
  assert client.post("/notes", json=VERSE).status_code == 200

  response = client.post("/notes", json=VERSE)

  assert response.status_code == 422 and "limit" in response.json()["detail"]


def test_a_note_on_a_verse_that_does_not_exist_is_refused():
  sign_up()

  response = client.post("/notes", json={**VERSE, "chapter": 3, "verse": 199})

  assert response.status_code == 422 and "no such verse" in response.json()["detail"]


def make_notes(count_bodies):
  sign_up()
  return [
    client.post("/notes", json={**VERSE, "verse": 16 if index % 2 == 0 else 17, "body": f"<p>{text}</p>"}).json()["note"]
    for index, text in enumerate(count_bodies)
  ]


def test_the_list_is_paged_newest_first_with_the_total():
  make_notes([f"Note number {number}" for number in range(7)])

  first = client.get("/notes", params={"per_page": 3, "page": 1}).json()
  third = client.get("/notes", params={"per_page": 3, "page": 3}).json()
  beyond = client.get("/notes", params={"per_page": 3, "page": 9}).json()

  assert first["total"] == third["total"] == 7 and first["page"] == 1 and first["per_page"] == 3
  assert [note["body"] for note in first["notes"]] == ["<p>Note number 6</p>", "<p>Note number 5</p>", "<p>Note number 4</p>"]
  assert [note["body"] for note in third["notes"]] == ["<p>Note number 0</p>"]
  assert beyond["notes"] == [] and beyond["total"] == 7


def test_the_page_numbers_are_checked():
  sign_up()

  assert client.get("/notes", params={"page": 0}).status_code == 422
  assert client.get("/notes", params={"per_page": 0}).status_code == 422
  assert client.get("/notes", params={"per_page": 201}).status_code == 422


def test_a_search_needs_every_word_in_any_case_and_any_part_of_a_word():
  make_notes(["Grace and truth came by Jesus", "Faith without works", "GRACE alone, by faith"])

  both = client.get("/notes", params={"query": "grace faith"}).json()
  part = client.get("/notes", params={"query": "TRUT"}).json()
  none = client.get("/notes", params={"query": "mercy"}).json()

  assert [note["body"] for note in both["notes"]] == ["<p>GRACE alone, by faith</p>"] and both["total"] == 1
  assert part["total"] == 1 and none["total"] == 0 and none["notes"] == []


def test_a_search_looks_at_the_text_not_the_tags_and_takes_wildcards_literally():
  make_notes(["Plain words", "Fifty% done_ right"])
  client.post("/notes", json={**VERSE, "body": '<p>A <a href="https://example.com/strong">link</a> <strong>bold</strong></p>'})

  assert client.get("/notes", params={"query": "href"}).json()["total"] == 0
  assert client.get("/notes", params={"query": "example"}).json()["total"] == 0
  assert client.get("/notes", params={"query": "bold"}).json()["total"] == 1
  assert client.get("/notes", params={"query": "%"}).json()["total"] == 1
  assert client.get("/notes", params={"query": "done_"}).json()["total"] == 1
  assert client.get("/notes", params={"query": "_"}).json()["total"] == 1
  assert client.get("/notes", params={"query": "P%n"}).json()["total"] == 0


def test_an_edit_changes_what_a_search_finds():
  note = make_notes(["Original wording"])[0]

  client.put(f"/notes/{note['id']}", json={"body": "<p>Rewritten wording</p>"})

  assert client.get("/notes", params={"query": "original"}).json()["total"] == 0
  assert client.get("/notes", params={"query": "rewritten"}).json()["total"] == 1


def test_the_kind_and_a_search_and_paging_work_together_and_a_search_is_only_among_ones_own():
  make_notes(["Love one", "Love two", "Other"])
  client.post("/notes", json={"item_type": "devotional", "source_code": "morning-and-evening", "section": 1, "unit": 5, "body": "<p>Love devotional</p>"})

  assert client.get("/notes", params={"item_type": "bible_verse"}).json()["total"] == 3
  assert client.get("/notes", params={"item_type": "devotional"}).json()["total"] == 1
  assert client.get("/notes", params={"item_type": "bible_verse", "query": "love"}).json()["total"] == 2
  assert client.get("/notes", params={"query": "love", "per_page": 2}).json()["total"] == 3
  client.cookies.clear()
  sign_up("bob")
  assert client.get("/notes", params={"query": "love"}).json()["total"] == 0


def test_too_many_search_words_are_refused():
  sign_up()

  assert client.get("/notes", params={"query": "a b c d e f g h i j k"}).status_code == 422


def test_notes_from_before_the_search_text_existed_get_theirs_from_the_migration():
  import pathlib

  make_notes(["Old note"])
  with connect() as connection:
    connection.execute("UPDATE notes SET body = %s, body_text = ''", ("<p>Fish &amp; <strong>chips</strong> &lt;3</p>",))
    migration = (pathlib.Path(__file__).resolve().parent.parent / "database" / "migrations" / "013_add_note_search_text.sql").read_text()
    connection.execute(migration)

  assert client.get("/notes", params={"query": "chips"}).json()["total"] == 1
  assert client.get("/notes", params={"query": "&"}).json()["total"] == 1
  assert client.get("/notes", params={"query": "strong"}).json()["total"] == 0

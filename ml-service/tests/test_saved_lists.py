"""Tests for My lists (saved_lists.py). They use the real tables with their own accounts, and remove them after."""

import pytest
from fastapi.testclient import TestClient

import accounts
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "saved-lists-test.example"
client = TestClient(app)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield
  clear()


def member(name="ann"):
  client.cookies.clear()
  answer = client.post("/account/register", json={"email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD})
  return answer.json()["user"]


def verse(book=43, chapter=3, number=16, translation="BSB", text="For God so loved the world"):
  return {"kind": "bible", "title": f"John {chapter}:{number}", "source": translation, "text": text,
          "target": {"translation": translation, "book": book, "chapter": chapter, "verse": number}}


SONG = {"kind": "music", "title": "Amazing Grace", "source": "John Newton", "text": "Amazing grace! How sweet the sound", "target": {"song": "amazing-grace"}}
NOTE = {"kind": "commentary", "title": "John 3:16", "source": "Matthew Henry", "text": "The love of God", "target": {"commentary": "matthew-henry", "book": 43, "chapter": 3, "verse": 16}}


def test_lists_need_a_login():
  assert client.get("/lists").status_code == 401
  assert client.post("/lists", json={"name": "x", "items": [verse()]}).status_code == 401


def test_save_ticked_results_as_a_list_and_add_more_later():
  member()
  answer = client.post("/lists", json={"name": "  Comfort   verses ", "items": [verse(), SONG]})
  assert answer.status_code == 200, answer.text
  saved = answer.json()
  assert saved["added"] == 2 and saved["list"]["name"] == "Comfort verses"
  entries = saved["list"]["items"]
  assert [entry["title"] for entry in entries] == ["John 3:16", "Amazing Grace"]
  assert entries[0]["target"] == {"translation": "BSB", "book": 43, "chapter": 3, "verse": 16} and entries[0]["text"] == "For God so loved the world"
  list_id = saved["list"]["id"]
  # Adding to it: a new entry goes at the end, one it has already is left alone.
  more = client.post("/lists", json={"list_id": list_id, "items": [verse(number=17, text="For God did not send"), verse()]}).json()
  assert more["added"] == 1 and [entry["title"] for entry in more["list"]["items"]] == ["John 3:16", "Amazing Grace", "John 3:17"]
  assert client.get("/lists").json()["lists"][0]["count"] == 3


def test_the_text_is_kept_as_plain_text_and_the_search_markers_are_removed():
  member()
  item = verse(text="For \u0001God\u0002 so <b>loved</b> the world")
  saved = client.post("/lists", json={"name": "Plain", "items": [item]}).json()
  assert saved["list"]["items"][0]["text"] == "For God so loved the world"


def test_licensed_bibles_and_bad_entries_are_refused():
  member()
  answer = client.post("/lists", json={"name": "NIV", "items": [verse(translation="NIV")]})
  assert answer.status_code == 422 and "cannot be saved" in answer.json()["detail"]
  assert client.post("/lists", json={"name": "Bad", "items": [{"kind": "video", "title": "x", "target": {}}]}).status_code == 422
  assert client.post("/lists", json={"name": "Bad", "items": [{"kind": "bible", "title": "x", "target": {"translation": "BSB"}}]}).status_code == 422
  assert client.post("/lists", json={"name": " ", "items": [verse()]}).status_code == 422
  assert client.post("/lists", json={"name": "Empty", "items": []}).status_code == 422


def test_names_are_one_per_member_and_lists_are_private():
  member("ann")
  list_id = client.post("/lists", json={"name": "Psalms", "items": [verse()]}).json()["list"]["id"]
  again = client.post("/lists", json={"name": "psalms", "items": [verse()]})
  assert again.status_code == 422 and "already have a list" in again.json()["detail"]
  member("bob")
  assert client.get(f"/lists/{list_id}").status_code == 404
  assert client.post("/lists", json={"list_id": list_id, "items": [verse()]}).status_code == 404
  assert client.delete(f"/lists/{list_id}").status_code == 404
  # Bob may use the same name for his own.
  assert client.post("/lists", json={"name": "Psalms", "items": [verse()]}).status_code == 200


def test_rename_remove_an_entry_and_delete():
  member()
  saved = client.post("/lists", json={"name": "First", "items": [verse(), SONG]}).json()["list"]
  renamed = client.put(f"/lists/{saved['id']}", json={"name": "Second"}).json()["list"]
  assert renamed["name"] == "Second"
  after = client.delete(f"/lists/{saved['id']}/items/{saved['items'][1]['id']}").json()["list"]
  assert [entry["title"] for entry in after["items"]] == ["John 3:16"]
  assert client.delete(f"/lists/{saved['id']}").json() == {"deleted": True}
  assert client.get("/lists").json() == {"lists": []}


def test_copy_to_notes_makes_one_note_with_the_whole_list_on_its_first_verse():
  member()
  saved = client.post("/lists", json={"name": "Love", "items": [SONG, NOTE, verse(number=17, text="For God did not send his Son")]}).json()["list"]
  note = client.post(f"/lists/{saved['id']}/note").json()["note"]
  # The song cannot carry a note, so the first that can is the commentary note.
  assert note["item_type"] == "commentary" and note["source_code"] == "matthew-henry"
  assert "My list “Love”" in note["body"] and "Amazing Grace" in note["body"] and "John 3:17" in note["body"]
  assert len(client.get("/notes").json()["notes"]) == 1
  songs_only = client.post("/lists", json={"name": "Songs", "items": [SONG]}).json()["list"]
  answer = client.post(f"/lists/{songs_only['id']}/note")
  assert answer.status_code == 422 and "needs a verse" in answer.json()["detail"]


def test_a_long_list_is_cut_to_fit_a_note():
  member()
  long_text = "word " * 900
  items = [verse(number=number, text=long_text) for number in range(1, 30)]
  saved = client.post("/lists", json={"name": "Long", "items": items}).json()["list"]
  note = client.post(f"/lists/{saved['id']}/note").json()["note"]
  assert "more entries in the list" in note["body"]

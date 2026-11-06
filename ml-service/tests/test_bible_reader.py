"""Tests for reading a Bible chapter by chapter. They use the Bibles loaded in the local database."""

import pytest
from fastapi.testclient import TestClient

from bible_reader import get_chapter, get_contents
from main import app
from search import connect

client = TestClient(app)
JOHN, GENESIS, EXODUS, REVELATION = 43, 1, 2, 66


def test_the_contents_list_every_book_and_chapter_of_a_bible():
  contents = get_contents("KJV")

  assert contents["translation"] == {"code": "KJV", "name": "King James Version", "language": "en"}
  assert len(contents["books"]) == 66
  assert sum(len(book["chapters"]) for book in contents["books"]) == 1189
  john = next(book for book in contents["books"] if book["number"] == JOHN)
  assert john["name"] == "John" and john["chapters"] == list(range(1, 22))


def test_a_chapter_comes_in_verse_order_with_its_text():
  chapter = get_chapter("BSB", JOHN, 3)

  assert (chapter["book_name"], chapter["chapter"]) == ("John", 3)
  assert [verse["verse"] for verse in chapter["verses"]] == list(range(1, 37))
  assert chapter["verses"][15]["text"].startswith("For God so loved the world")
  assert chapter["translation"]["code"] == "BSB"


def test_the_bsb_has_word_links_and_the_other_bibles_do_not():
  bsb = get_chapter("BSB", JOHN, 3)["verses"][15]
  kjv = get_chapter("KJV", JOHN, 3)["verses"]

  start, end, code = bsb["links"][3]
  assert (bsb["text"][start:end], code) == ("loved", "G0025")
  assert all("links" not in verse for verse in kjv)


def test_the_chapters_before_and_after_run_across_books_and_stop_at_the_ends():
  last_of_genesis = get_chapter("KJV", GENESIS, 50)
  first = get_chapter("KJV", GENESIS, 1)
  last = get_chapter("KJV", REVELATION, 22)

  assert last_of_genesis["next"] == {"book_number": EXODUS, "book_name": "Exodus", "chapter": 1}
  assert last_of_genesis["previous"] == {"book_number": GENESIS, "book_name": "Genesis", "chapter": 49}
  assert first["previous"] is None and first["next"]["chapter"] == 2
  assert last["next"] is None and last["previous"]["chapter"] == 21


def test_unknown_things_are_not_found():
  assert get_chapter("NOPE", JOHN, 3) is None
  assert get_chapter("BSB", JOHN, 99) is None
  assert get_chapter("BSB", 999, 1) is None
  assert get_contents("NOPE") is None


def test_a_hidden_bible_cannot_be_read():
  with connect() as connection:
    translation_id = connection.execute(
      "INSERT INTO translations (code, name, language, license, is_published) "
      "VALUES ('ZZHIDDEN', 'Hidden Test Bible', 'en', 'test', FALSE) RETURNING id"
    ).fetchone()[0]
    connection.execute(
      "INSERT INTO verses (translation_id, book_number, chapter, verse, text) VALUES (%s, 43, 3, 16, 'Hidden.')",
      (translation_id,),
    )
  try:
    assert get_chapter("ZZHIDDEN", JOHN, 3) is None
    assert get_contents("ZZHIDDEN") is None
  finally:
    with connect() as connection:
      connection.execute("DELETE FROM translations WHERE code = 'ZZHIDDEN'")


def test_the_api_serves_contents_and_chapters_and_refuses_what_it_cannot():
  assert len(client.get("/bible-contents", params={"translation": "kjv"}).json()["books"]) == 66

  body = client.get("/bible-chapter", params={"translation": "BSB", "book": JOHN, "chapter": 3}).json()
  assert body["verses"][15]["links"] and body["next"]["chapter"] == 4

  assert client.get("/bible-chapter", params={"translation": "NIV", "book": JOHN, "chapter": 3}).status_code == 422
  assert client.get("/bible-contents", params={"translation": "NASB"}).status_code == 422
  assert client.get("/bible-chapter", params={"translation": "NOPE", "book": JOHN, "chapter": 3}).status_code == 404
  assert client.get("/bible-chapter", params={"translation": "BSB", "book": JOHN, "chapter": 99}).status_code == 404
  assert client.get("/bible-chapter", params={"translation": "BSB", "book": 67, "chapter": 1}).status_code == 422

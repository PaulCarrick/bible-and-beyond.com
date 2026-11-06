"""Tests for linking English words to Strong's numbers (click a word) and for what the
context windows return. Database tests work in a throwaway schema that shadows the links table."""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

import context
import word_links
from main import app
from search import connect
from word_links import (
  WordLinksProblem,
  align_verse,
  build_links,
  hash_text,
  read_table,
  replace_links,
  strong_code,
)

client = TestClient(app)
JOHN = 43


def table_row(sort, language, hebrew_number, greek_number, english, verse_id=""):
  columns = [""] * 23
  columns[2] = str(sort)
  columns[4] = language
  columns[10] = hebrew_number
  columns[11] = greek_number
  columns[12] = verse_id
  columns[18] = f" {english} "
  return "\t".join(columns)


HEADER = "\t".join(["Heb Sort", "Greek Sort", "BSB Sort"] + ["x"] * 20)


def write_table(tmp_path, rows):
  path = tmp_path / "bsb_tables.tsv"
  path.write_text("\r\n".join([HEADER, *rows]) + "\r\n", encoding="utf-8")
  return path


# --- Strong's numbers ------------------------------------------------------------------------------


def test_strongs_numbers_are_written_like_the_lexicon():
  assert strong_code("Hebrew", "7225", "") == "H7225"
  assert strong_code("Aramaic", "426", "") == "H0426"
  assert strong_code("Greek", "", "1063") == "G1063"
  assert strong_code("Greek", "", "") is None
  assert strong_code("Hebrew", "0", "") is None


# --- reading the table -----------------------------------------------------------------------------


def test_the_table_is_read_in_english_order_and_placeholders_are_dropped(tmp_path):
  path = write_table(tmp_path, [
    # Original order is "created" then "God"; the English reads "God created".
    table_row(2, "Hebrew", "1254", "", "created", "Genesis 1:1"),
    table_row(1, "Hebrew", "430", "", "God"),
    table_row(3, "Hebrew", "853", "", "vvv"),
    table_row(4, "Hebrew", "", "", "the heavens"),
    table_row(5, "Greek", "", "26", "love", "Exodus 2:3"),
  ])

  table = read_table(path, expected_books=2)

  assert table[(1, 1, 1)] == [("god", "H0430"), ("created", "H1254"), ("the", None), ("heavens", None)]
  assert table[(2, 2, 3)] == [("love", "G0026")]


def test_a_table_with_the_wrong_number_of_books_is_refused(tmp_path):
  path = write_table(tmp_path, [table_row(1, "Hebrew", "430", "", "God", "Genesis 1:1")])

  with pytest.raises(WordLinksProblem, match="Expected 66 books"):
    read_table(path)


def test_a_word_before_the_first_verse_is_refused(tmp_path):
  path = write_table(tmp_path, [table_row(1, "Hebrew", "430", "", "God")])

  with pytest.raises(WordLinksProblem, match="before the first verse"):
    read_table(path, expected_books=1)


# --- matching the table's words to a verse's text ------------------------------------------------------


def test_words_are_matched_in_order_with_their_positions():
  text = "In the beginning God created the heavens."
  words = [("in", "H7225"), ("the", "H7225"), ("beginning", "H7225"), ("god", "H0430"), ("created", "H1254")]

  assert align_verse(text, words) == [[0, 2, "H7225"], [3, 6, "H7225"], [7, 16, "H7225"], [17, 20, "H0430"], [21, 28, "H1254"]]


def test_words_with_no_strongs_number_still_use_up_their_place_in_the_text():
  text = "the sister of Tubal-cain was Naamah"
  words = [("the", None), ("sister", "H0269"), ("of", None), ("tubal-cain", "H8423"), ("was", None), ("naamah", "H5279")]

  links = align_verse(text, words)

  assert [text[start:end] for start, end, _code in links] == ["sister", "Tubal-cain", "Naamah"]


def test_a_repeated_word_takes_the_next_one_not_the_first():
  links = align_verse("God saw that God said", [("god", "H0430"), ("god", "H0430"), ("said", "H0559")])

  assert links == [[0, 3, "H0430"], [13, 16, "H0430"], [17, 21, "H0559"]]


def test_curly_apostrophes_match_straight_ones():
  assert align_verse("Don’t be afraid", [("don't", "G3361"), ("afraid", "G5399")]) == [[0, 5, "G3361"], [9, 15, "G5399"]]


def test_a_verse_that_does_not_line_up_has_no_links_at_all():
  assert align_verse("In the beginning God created", [("in", "H7225"), ("sky", "H8064")]) is None


def test_text_with_characters_a_browser_counts_differently_is_skipped():
  assert align_verse("God 😀 created", [("god", "H0430")]) is None


def test_build_links_reports_what_it_could_do():
  table = {(1, 1, 1): [("god", "H0430")], (1, 1, 2): [("sky", "H8064")]}
  rows, summary = build_links(table, [(10, 1, 1, 1, "God"), (11, 1, 1, 2, "Earth"), (12, 1, 1, 3, "x")])

  assert [row[0] for row in rows] == [10]
  assert rows[0][1] == hash_text("God") and rows[0][2] == "[[0,3,\"H0430\"]]"
  assert summary == {"verses": 3, "linked": 1, "not_in_table": 1, "did_not_line_up": 1, "words": 1}


# --- storing and serving the links, in a throwaway schema ---------------------------------------------


@pytest.fixture
def john_3_16(monkeypatch):
  """The BSB's John 3:16 with a link on "loved", stored in a throwaway links table."""
  with connect() as connection:
    verse_id, text = connection.execute(
      "SELECT v.id, v.text FROM verses v JOIN translations t ON t.id = v.translation_id "
      "WHERE t.code = 'BSB' AND v.book_number = 43 AND v.chapter = 3 AND v.verse = 16"
    ).fetchone()
    connection.execute("DROP SCHEMA IF EXISTS links_test CASCADE")
    connection.execute("CREATE SCHEMA links_test")
    connection.execute(
      "CREATE TABLE links_test.verse_word_links (verse_id INTEGER PRIMARY KEY REFERENCES public.verses (id) ON DELETE CASCADE,"
      " text_hash TEXT NOT NULL, links JSONB NOT NULL)"
    )

  def connect_to_test_schema():
    return psycopg.connect(os.environ["DATABASE_URL"], options="-c search_path=links_test,public")

  monkeypatch.setattr(word_links, "connect", connect_to_test_schema)
  monkeypatch.setattr(context, "connect", connect_to_test_schema)
  start = text.index("loved")
  rows = [(verse_id, hash_text(text), f'[[{start},{start + 5},"G0025"]]')]
  assert replace_links("BSB", rows) == 1
  try:
    yield text, start
  finally:
    with connect() as connection:
      connection.execute("DROP SCHEMA IF EXISTS links_test CASCADE")


def test_the_context_window_carries_the_links_of_each_verse(john_3_16):
  text, start = john_3_16

  body = client.get("/context", params={"translation": "BSB", "book": JOHN, "chapter": 3, "verse": 16}).json()

  target = next(verse for verse in body["verses"] if verse["is_target"])
  assert target["links"] == [[start, start + 5, "G0025"]]
  assert text[start:start + 5] == "loved"
  assert all("links" not in verse for verse in body["verses"] if not verse["is_target"])


def test_the_full_chapter_carries_links_too(john_3_16):
  body = client.get("/chapter", params={"translation": "BSB", "book": JOHN, "chapter": 3, "verse": 1}).json()

  assert [verse["verse"] for verse in body["verses"] if "links" in verse] == [16]


def test_links_are_ignored_when_the_verse_text_has_changed(john_3_16):
  with connect() as connection:
    connection.execute("UPDATE links_test.verse_word_links SET text_hash = 'old text'")

  body = client.get("/context", params={"translation": "BSB", "book": JOHN, "chapter": 3, "verse": 16}).json()

  assert all("links" not in verse for verse in body["verses"])


def test_other_bibles_have_no_links(john_3_16):
  body = client.get("/context", params={"translation": "KJV", "book": JOHN, "chapter": 3, "verse": 16}).json()

  assert all("links" not in verse for verse in body["verses"])


def test_replacing_links_replaces_them_rather_than_adding(john_3_16):
  assert replace_links("BSB", []) == 0

  body = client.get("/context", params={"translation": "BSB", "book": JOHN, "chapter": 3, "verse": 16}).json()
  assert all("links" not in verse for verse in body["verses"])

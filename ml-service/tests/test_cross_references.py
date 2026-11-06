"""Tests for reading and loading cross references, and for the related verses lookup.

The lookup tests add a few rows with very high vote counts, so they always come first whatever
real data is loaded, and remove them afterwards. The loading test works in a throwaway schema.
"""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

import cross_references
import main
from cross_references import BOOK_NUMBERS, CrossReferenceProblem, parse_line, read_file, replace_all
from main import app
from search import connect

client = TestClient(app)
JOHN, GENESIS = 43, 1
TEST_VOTES = 9_000_000  # test rows have far more votes than any real row (the real maximum is 1,317)
REAL_VOTES_CEILING = 1_000_000  # anything above this is a test row


def write(tmp_path, text, name="cross_references.txt"):
  path = tmp_path / name
  path.write_text(text, encoding="utf-8")
  return path


HEADER = "From Verse\tTo Verse\tVotes\t#www.openbible.info CC-BY 2026-11-02\n"


# --- reading the file ----------------------------------------------------------------------------


def test_a_single_verse_reference_is_read():
  reference = parse_line("Gen.1.1\tRev.4.11\t209", 2)

  assert reference.from_verse == (1, 1, 1)
  assert reference.to_verse == (66, 4, 11)
  assert reference.to_end_verse is None and reference.votes == 209


def test_a_range_inside_a_chapter_is_read():
  reference = parse_line("Gen.1.1\tProv.8.22-Prov.8.30\t78", 2)

  assert reference.to_verse == (20, 8, 22) and reference.to_end_verse == (20, 8, 30)


def test_a_range_across_chapters_and_one_across_books_are_read():
  across_chapters = parse_line("Ps.1.1\tPs.23.6-Ps.24.2\t5", 2)
  across_books = parse_line("Ps.1.1\tMal.4.6-Matt.1.1\t5", 2)

  assert across_chapters.to_end_verse == (19, 24, 2)
  assert across_books.to_verse == (39, 4, 6) and across_books.to_end_verse == (40, 1, 1)


def test_numbered_books_and_negative_votes_are_read():
  reference = parse_line("1John.3.18\t2John.1.1-3John.1.15\t-7", 2)

  assert reference.from_verse[0] == 62 and reference.to_verse[0] == 63 and reference.to_end_verse[0] == 64
  assert reference.votes == -7


def test_an_unknown_book_names_the_line():
  with pytest.raises(CrossReferenceProblem, match="Line 7: I do not know the book 'Tobit'"):
    parse_line("Tobit.1.1\tGen.1.1\t3", 7)


@pytest.mark.parametrize("line", ["", "Gen.1.1", "Gen.1.1\tRev.4.11", "Gen 1:1\tRev 4:11\t5", "Gen.1.1\tRev.4.11\tlots"])
def test_a_line_that_is_not_a_cross_reference_names_the_line(line):
  with pytest.raises(CrossReferenceProblem, match="Line 9"):
    parse_line(line, 9)


def test_the_header_and_blank_lines_are_skipped_and_weak_votes_are_left_out(tmp_path):
  path = write(tmp_path, HEADER + "Gen.1.1\tRev.4.11\t209\n\nGen.1.1\tIsa.65.17\t58\nGen.1.1\tExod.31.18\t-40\nGen.1.1\tPs.8.3\t0\n")

  references, skipped = read_file(path)

  assert [reference.votes for reference in references] == [209, 58]
  assert skipped == 2


def test_the_minimum_votes_can_be_raised(tmp_path):
  path = write(tmp_path, HEADER + "Gen.1.1\tRev.4.11\t209\nGen.1.1\tIsa.65.17\t58\nGen.1.1\tPs.8.3\t4\n")

  references, skipped = read_file(path, minimum_votes=50)

  assert len(references) == 2 and skipped == 1


def test_a_pair_listed_twice_is_a_problem(tmp_path):
  path = write(tmp_path, HEADER + "Gen.1.1\tRev.4.11\t209\nGen.1.1\tRev.4.11\t12\n")

  with pytest.raises(CrossReferenceProblem, match="Line 3.*more than once"):
    read_file(path)


def test_the_book_abbreviations_cover_all_66_books_in_the_right_order():
  assert sorted(BOOK_NUMBERS.values()) == list(range(1, 67))
  with connect() as connection:
    codes = dict(connection.execute("SELECT number, code FROM books").fetchall())
  # A few that are easy to get wrong: the numbered books, Psalms, Song of Solomon, Philemon, James.
  expected = {"Ps": "PSA", "Song": "SNG", "Phlm": "PHM", "Jas": "JAS", "1Kgs": "1KI", "1John": "1JN",
             "Obad": "OBA", "Jonah": "JON", "Matt": "MAT", "Rev": "REV", "Gen": "GEN", "Ezek": "EZK"}
  for abbreviation, code in expected.items():
    assert codes[BOOK_NUMBERS[abbreviation]] == code, abbreviation


# --- loading, in a throwaway copy of the table --------------------------------------------------


def test_loading_replaces_everything_and_touches_nothing_else(tmp_path, monkeypatch):
  with connect() as connection:
    real_before = connection.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0]
    connection.execute("DROP SCHEMA IF EXISTS xref_test CASCADE")
    connection.execute("CREATE SCHEMA xref_test")
    connection.execute("CREATE TABLE xref_test.cross_references (LIKE public.cross_references INCLUDING DEFAULTS)")

  def connect_to_test_schema():
    return psycopg.connect(os.environ["DATABASE_URL"], options="-c search_path=xref_test,public")

  monkeypatch.setattr(cross_references, "connect", connect_to_test_schema)
  try:
    first, _ = read_file(write(tmp_path, HEADER + "Gen.1.1\tRev.4.11\t209\nGen.1.1\tIsa.65.17\t58\nGen.1.2\tPs.8.3\t4\n", "first.txt"))
    second, _ = read_file(write(tmp_path, HEADER + "John.3.16\tRom.5.8\t992\nJohn.3.16\t1John.4.9-1John.4.10\t705\n", "second.txt"))

    assert replace_all(first) == 3
    assert replace_all(second) == 2  # replaced, not added to

    with connect() as connection:
      saved = connection.execute(
        "SELECT from_book, to_book, to_end_book, to_end_verse, votes FROM xref_test.cross_references ORDER BY votes DESC"
      ).fetchall()
      real_after = connection.execute("SELECT COUNT(*) FROM public.cross_references").fetchone()[0]
    assert saved == [(43, 45, None, None, 992), (43, 62, 62, 10, 705)]
    assert real_after == real_before
  finally:
    with connect() as connection:
      connection.execute("DROP SCHEMA IF EXISTS xref_test CASCADE")


# --- the related verses lookup ---------------------------------------------------------------------


@pytest.fixture
def source():
  """A KJV verse that has no real cross references, with four test ones that outrank any real one.

  The test rows are removed afterwards. Returns the verse as (book, chapter, verse).
  """
  with connect() as connection:
    verse = connection.execute(
      "SELECT v.book_number, v.chapter, v.verse FROM verses v JOIN translations t ON t.id = v.translation_id"
      " WHERE t.code = 'KJV' AND NOT EXISTS (SELECT 1 FROM cross_references c WHERE c.from_book = v.book_number"
      " AND c.from_chapter = v.chapter AND c.from_verse = v.verse) ORDER BY v.book_number, v.chapter, v.verse LIMIT 1"
    ).fetchone()
  if verse is None:
    pytest.skip("every KJV verse has a cross reference in this database")

  rows = [
    (*verse, 45, 5, 8, None, None, None, TEST_VOTES + 3),  # Romans 5:8
    (*verse, 62, 4, 9, 62, 4, 10, TEST_VOTES + 2),  # 1 John 4:9-10
    (*verse, 19, 23, 6, 19, 24, 2, TEST_VOTES + 1),  # Psalms 23:6 - 24:2, across chapters
    (*verse, 64, 1, 15, None, None, None, TEST_VOTES),  # 3 John 1:15, a verse the KJV does not have
  ]
  with connect() as connection:
    for row in rows:
      connection.execute(
        "INSERT INTO cross_references (from_book, from_chapter, from_verse, to_book, to_chapter, to_verse,"
        " to_end_book, to_end_chapter, to_end_verse, votes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", row
      )
  yield verse
  with connect() as connection:
    connection.execute("DELETE FROM cross_references WHERE votes >= %s", (REAL_VOTES_CEILING,))


def related(verse, translation="KJV"):
  book, chapter, number = verse
  return client.get("/related", params={"translation": translation, "book": book, "chapter": chapter, "verse": number})


def test_the_best_voted_references_come_first_with_their_text(source):
  body = related(source).json()

  assert [entry["reference"] for entry in body["references"][:4]] == [
    "Romans 5:8", "1 John 4:9–10", "Psalms 23:6 – 24:2", "3 John 1:15",
  ]
  assert [entry["votes"] for entry in body["references"][:3]] == [TEST_VOTES + 3, TEST_VOTES + 2, TEST_VOTES + 1]
  assert "But God commendeth his love toward us" in body["references"][0]["verses"][0]["text"]
  assert [(v["chapter"], v["verse"]) for v in body["references"][1]["verses"]] == [(4, 9), (4, 10)]
  assert (body["book_number"], body["chapter"], body["verse"]) == source and body["translation"] == "KJV"


def test_a_range_across_chapters_gives_every_verse_in_between(source):
  verses = related(source).json()["references"][2]["verses"]

  assert (verses[0]["chapter"], verses[0]["verse"]) == (23, 6)
  assert (verses[-1]["chapter"], verses[-1]["verse"]) == (24, 2)
  assert [v["chapter"] for v in verses] == [23] + [24] * (len(verses) - 1)


def test_a_reference_to_a_verse_the_translation_lacks_is_listed_without_text(source):
  entry = related(source).json()["references"][3]

  assert entry["reference"] == "3 John 1:15" and entry["verses"] == []


def test_the_number_shown_follows_the_setting_and_the_total_is_reported(source, monkeypatch):
  monkeypatch.setattr(main, "get_settings", lambda: {"related_verses_limit": 2})

  body = related(source).json()

  assert body["shown"] == 2 and len(body["references"]) == 2
  assert body["total"] == 4


def test_the_default_is_ten_references(source):
  with connect() as connection:
    for target in range(1, 13):  # more than ten, all below the test rows in votes order
      connection.execute(
        "INSERT INTO cross_references VALUES (%s, %s, %s, 40, 1, %s, NULL, NULL, NULL, %s)",
        (*source, target, TEST_VOTES - target),
      )

  body = related(source).json()

  assert body["shown"] == 10 and body["total"] == 16


def test_a_very_long_range_is_cut_short_and_says_so(source):
  with connect() as connection:
    connection.execute(
      "INSERT INTO cross_references VALUES (%s, %s, %s, 19, 119, 1, 19, 119, 176, %s)", (*source, TEST_VOTES + 9)
    )

  entry = related(source).json()["references"][0]

  assert entry["reference"] == "Psalms 119:1–176"
  assert len(entry["verses"]) == 15 and entry["has_more_verses"] is True


def test_the_text_is_in_the_requested_translation(source):
  kjv = related(source, "KJV").json()["references"][0]["verses"][0]["text"]
  bsb = related(source, "bsb").json()["references"][0]["verses"][0]["text"]

  assert kjv != bsb and bsb.startswith("But God proves His love for us")


def test_a_verse_with_no_references_gives_an_empty_list():
  with connect() as connection:
    has_none = connection.execute(
      "SELECT v.book_number, v.chapter, v.verse FROM verses v JOIN translations t ON t.id = v.translation_id"
      " WHERE t.code = 'KJV' AND NOT EXISTS (SELECT 1 FROM cross_references c WHERE c.from_book = v.book_number"
      " AND c.from_chapter = v.chapter AND c.from_verse = v.verse) LIMIT 1"
    ).fetchone()
  if has_none is None:
    pytest.skip("every KJV verse has a cross reference in this database")

  body = related(has_none).json()

  assert body["references"] == [] and body["total"] == 0 and body["shown"] == 0


@pytest.mark.parametrize(
  "parameters, status",
  [
    ({"translation": "NOPE", "book": JOHN, "chapter": 3, "verse": 16}, 404),
    ({"translation": "KJV", "book": JOHN, "chapter": 99, "verse": 1}, 404),
    ({"translation": "KJV", "book": JOHN, "chapter": 3, "verse": 999}, 404),
    ({"translation": "NIV", "book": JOHN, "chapter": 3, "verse": 16}, 422),
    ({"translation": "msg", "book": JOHN, "chapter": 3, "verse": 16}, 422),
    ({"translation": "KJV", "book": 0, "chapter": 3, "verse": 16}, 422),
    ({"translation": "KJV", "book": JOHN, "chapter": 0, "verse": 16}, 422),
    ({"translation": "KJV", "book": JOHN, "chapter": 3}, 422),
  ],
)
def test_related_requests_that_cannot_be_answered_are_refused(parameters, status):
  assert client.get("/related", params=parameters).status_code == status


# --- which verses point at a verse -------------------------------------------------------------------


@pytest.fixture
def pointed_at():
  """John 3:16 with four test verses that point at it, one way or another. Removed afterwards.

  The four pointing verses are KJV verses that have no real cross references of their own, so
  the test rows cannot collide with real ones. Returns (target, [first, second, third, fourth]).
  """
  target = (JOHN, 3, 16)
  with connect() as connection:
    sources = connection.execute(
      "SELECT v.book_number, v.chapter, v.verse FROM verses v JOIN translations t ON t.id = v.translation_id"
      " WHERE t.code = 'KJV' AND NOT EXISTS (SELECT 1 FROM cross_references c WHERE c.from_book = v.book_number"
      " AND c.from_chapter = v.chapter AND c.from_verse = v.verse) ORDER BY v.book_number, v.chapter, v.verse LIMIT 4"
    ).fetchall()
    if len(sources) < 4:
      pytest.skip("not enough KJV verses without cross references in this database")
    first, second, third, fourth = sources
    rows = [
      (*first, *target, None, None, None, TEST_VOTES + 4),  # points straight at John 3:16
      (*second, JOHN, 3, 14, JOHN, 3, 18, TEST_VOTES + 3),  # a range, John 3:14-18, that contains it
      (*first, JOHN, 3, 15, JOHN, 3, 17, TEST_VOTES + 2),  # the first verse again, through another range
      (*third, JOHN, 3, 17, JOHN, 3, 20, TEST_VOTES + 1),  # John 3:17-20 is next to it, not around it
      (*fourth, *target, None, None, None, TEST_VOTES),  # points straight at it, with the fewest votes
    ]
    for row in rows:
      connection.execute(
        "INSERT INTO cross_references (from_book, from_chapter, from_verse, to_book, to_chapter, to_verse,"
        " to_end_book, to_end_chapter, to_end_verse, votes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", row
      )
  yield target, [first, second, third, fourth]
  with connect() as connection:
    connection.execute("DELETE FROM cross_references WHERE votes >= %s", (REAL_VOTES_CEILING,))


def pointing_at(target, translation="KJV", direction="to"):
  book, chapter, number = target
  return client.get(
    "/related",
    params={"translation": translation, "book": book, "chapter": chapter, "verse": number, "direction": direction},
  )


def test_the_verses_that_point_at_a_verse_are_listed_best_voted_first(pointed_at):
  target, (first, second, third, fourth) = pointed_at

  body = pointing_at(target).json()

  sources = [(entry["book_number"], entry["chapter"], entry["verse"]) for entry in body["references"][:3]]
  assert sources == [first, second, fourth]  # the third verse points next to it, not at it
  assert [entry["votes"] for entry in body["references"][:3]] == [TEST_VOTES + 4, TEST_VOTES + 3, TEST_VOTES]
  assert body["direction"] == "to"


def test_each_pointing_verse_appears_once_with_its_best_votes_and_its_own_text(pointed_at):
  target, (first, *_rest) = pointed_at

  body = pointing_at(target).json()

  appearances = [entry for entry in body["references"] if (entry["book_number"], entry["chapter"], entry["verse"]) == first]
  assert len(appearances) == 1 and appearances[0]["votes"] == TEST_VOTES + 4
  assert len(appearances[0]["verses"]) == 1 and appearances[0]["verses"][0]["text"]
  assert appearances[0]["reference"] == f"{appearances[0]['verses'][0]['book_name']} {first[1]}:{first[2]}"


def test_the_counts_for_both_directions_are_reported_whichever_way_you_look(pointed_at):
  target, _sources = pointed_at

  looking_back = pointing_at(target, direction="to").json()
  looking_forward = pointing_at(target, direction="from").json()

  assert looking_back["incoming_total"] == looking_forward["incoming_total"] >= 3
  assert looking_back["outgoing_total"] == looking_forward["outgoing_total"]
  assert looking_back["total"] == looking_back["incoming_total"]
  assert looking_forward["total"] == looking_forward["outgoing_total"] and looking_forward["direction"] == "from"


def test_the_direction_defaults_to_where_the_verse_points(pointed_at):
  target, _sources = pointed_at
  book, chapter, number = target

  body = client.get("/related", params={"translation": "KJV", "book": book, "chapter": chapter, "verse": number}).json()

  assert body["direction"] == "from" and body["total"] == body["outgoing_total"]


def test_the_limit_applies_to_pointing_verses_too(pointed_at, monkeypatch):
  target, _sources = pointed_at
  monkeypatch.setattr(main, "get_settings", lambda: {"related_verses_limit": 2})

  body = pointing_at(target).json()

  assert body["shown"] == 2 and body["total"] > 2


def test_an_unknown_direction_is_refused(pointed_at):
  target, _sources = pointed_at

  assert pointing_at(target, direction="sideways").status_code == 422


def test_a_verse_that_begins_a_range_that_runs_into_the_next_chapter_still_counts(source):
  with connect() as connection:
    connection.execute(
      "INSERT INTO cross_references VALUES (%s, %s, %s, 1, 1, 1, 1, 2, 3, %s)", (*source, TEST_VOTES + 1)
    )

  body = pointing_at((GENESIS, 1, 1)).json()

  assert (source[0], source[1], source[2]) in [(e["book_number"], e["chapter"], e["verse"]) for e in body["references"][:1]]


def test_the_count_for_genesis_1_1_is_at_least_every_verse_that_names_it_directly():
  with connect() as connection:
    naming_it = connection.execute(
      "SELECT COUNT(DISTINCT (from_book, from_chapter, from_verse)) FROM cross_references"
      " WHERE to_book = 1 AND to_chapter = 1 AND to_verse = 1"
    ).fetchone()[0]

  body = pointing_at((GENESIS, 1, 1)).json()

  assert body["incoming_total"] >= naming_it >= 1
  assert body["shown"] == min(10, body["incoming_total"])

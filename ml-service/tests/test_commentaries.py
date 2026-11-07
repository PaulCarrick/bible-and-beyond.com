"""Tests for reading, loading and looking up commentaries. Loading works in a throwaway schema."""

import json
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

import commentaries
from commentaries import (
  COMMENTARIES,
  FILE_COMMENTARIES,
  KNOWN_COMMENTARIES,
  read_gutenberg_commentary,
  read_treasury,
  read_wesley_notes,
  CommentaryProblem,
  check_ids,
  get_chapter_notes,
  get_commentaries,
  get_contents,
  label_range,
  list_commentaries,
  paragraphs_to_text,
  read_commentary,
  replace_commentary,
  search_commentaries,
  START_MARK,
  STOP_MARK,
)
from main import app
from search import connect

client = TestClient(app)
JOHN = 43
BOOKS = {"JHN": 43, "GEN": 1}


def write_commentary(tmp_path, commentary_id, chapters, book_introduction="About John."):
  """Write the files of a small commentary: chapters is {(book code, chapter): [(verse, [paragraphs])]}."""
  directory = tmp_path / commentary_id
  directory.mkdir(parents=True)
  books = {}
  for (code, chapter), items in chapters.items():
    books[code] = max(books.get(code, 0), chapter)
    body = {
      "chapter": {
        "number": chapter,
        "introduction": f"In chapter {chapter}.",
        "content": [{"type": "verse", "number": number, "content": paragraphs} for number, paragraphs in items],
      }
    }
    (directory / f"{code}_{chapter}.json").write_text(json.dumps(body), encoding="utf-8")
  (directory / "books.json").write_text(
    json.dumps([
      {"id": code, "numberOfChapters": count, "introduction": book_introduction} for code, count in books.items()
    ]),
    encoding="utf-8",
  )
  return tmp_path


# --- reading ------------------------------------------------------------------------------------


def test_every_commentary_is_named_and_says_whether_it_comments_on_sections():
  assert list(COMMENTARIES) == [
    "matthew-henry", "john-gill", "adam-clarke", "jamieson-fausset-brown", "john-calvin", "keil-delitzsch",
  ]
  assert {key for key, (_name, _short, sections) in COMMENTARIES.items() if sections} == {
    "matthew-henry", "john-calvin", "keil-delitzsch",
  }


def test_the_file_commentaries_come_after_the_others_and_the_ccel_one_loads_hidden():
  assert list(KNOWN_COMMENTARIES) == list(COMMENTARIES) + list(FILE_COMMENTARIES)
  assert KNOWN_COMMENTARIES["luther-galatians"]["source_name"] == "Project Gutenberg"
  assert KNOWN_COMMENTARIES["treasury-of-david"]["publish"] is True
  assert KNOWN_COMMENTARIES["wesley-notes"]["publish"] is False
  assert KNOWN_COMMENTARIES["matthew-henry"]["publish"] is True


TREASURY_SAMPLE = """Header
*** START OF THE PROJECT GUTENBERG EBOOK TREASURY ***

                                PSALM I.

TITLE.—_The preface Psalm._

                              EXPOSITION.

    Blessed is the man that walketh not in the counsel of the ungodly.

    2 But his delight is in the law of the LORD.

On verses one and two.

    Happy the man whose hopes rely
    On Israel's God.

    4 The ungodly are not so.

On verse four.

                 EXPLANATORY NOTES AND QUAINT SAYINGS.

_Whole Psalm._—The Psalm of Psalms.

_Verse 2._—On delight.

More on delight.

_Verse 5._—On the judgment.

                          HINTS TO PREACHERS.

_Verse 1._—Three steps of sin.

*** END OF THE PROJECT GUTENBERG EBOOK TREASURY ***
"""


def test_the_treasury_of_david_is_read_by_its_verse_groups(tmp_path, monkeypatch):
  monkeypatch.setattr(commentaries, "verse_limits", lambda: {(19, 1): 6})
  path = tmp_path / "pg1.txt"
  path.write_text(TREASURY_SAMPLE, encoding="utf-8")
  entries, introductions = read_treasury([path])

  # Verses 1 and 2 are one note; the quoted hymn stays in the comment; verse 4 runs to the end of the Psalm.
  assert [(book, chapter, verse, end) for book, chapter, verse, end, _text in entries] == [(19, 1, 1, 3), (19, 1, 4, None)]
  first = entries[0][4]
  assert "Happy the man whose hopes rely" in first
  assert "Explanatory Notes and Quaint Sayings\n\nVerse 2.—On delight.\n\nMore on delight." in first
  assert first.endswith("Hints to Preachers\n\nVerse 1.—Three steps of sin.")
  assert "Verse 5.—On the judgment." in entries[1][4]
  assert introductions == [(19, 1, "TITLE.—The preface Psalm.\n\nExplanatory Notes and Quaint Sayings: the whole Psalm\n\nWhole Psalm.—The Psalm of Psalms.")]


def test_wesleys_notes_are_read_by_verse_numbers_in_bible_order(tmp_path, monkeypatch):
  monkeypatch.setattr(commentaries, "verse_limits", lambda: {(40, 1): 25, (19, 1): 6})
  books = []
  for index in range(66):
    chapters = '<div3 title="I"><p>1. Only a note.</p></div3>'
    if index == 0:  # Matthew, the first of the New Testament
      chapters = (
        '<div3 title="Introduction to Matthew"><p>About Matthew.</p></div3>'
        '<div3 title="I"><h3>I</h3><scripCom/><p>The chapter begins.</p><p>1. The book - of the generation.</p>'
        '<p>1. A numbered point inside the note.</p><p>3, 4. And Judas - begat.</p><p>40. Past the chapter.</p></div3>'
      )
    if index == 45:  # Psalms, numbered with figures
      chapters = '<div3 title="1"><div4><p>2. His delight - In the law.</p></div4></div3>'
    books.append(f'<div2 title="NOTES ON BOOK {index}">{chapters}</div2>')
  path = tmp_path / "notes.xml"
  path.write_text(f'<ThML><ThML.body><div1><div2 title="PREFACE"><p>x</p></div2>{"".join(books)}</div1></ThML.body></ThML>', encoding="utf-8")
  entries, introductions = read_wesley_notes([path])

  matthew = [(verse, end, text) for book, chapter, verse, end, text in entries if (book, chapter) == (40, 1)]
  assert [(verse, end) for verse, end, _text in matthew] == [(1, 1), (3, 4)]
  assert matthew[0][2] == "1. The book - of the generation.\n\n1. A numbered point inside the note."
  assert matthew[1][2].endswith("40. Past the chapter.")
  assert (40, 0, "About Matthew.") in introductions and (40, 1, "The chapter begins.") in introductions
  assert (19, 1, 2, 2, "2. His delight - In the law.") in entries
  assert (1, 1, 1, 1, "1. Only a note.") in entries  # Genesis, the first of the Old Testament, comes after Revelation


LUTHER_SAMPLE = """Header
*** START OF THE PROJECT GUTENBERG EBOOK COMMENTARY ***

PREFACE

A preface that
wraps.

CHAPTER 1


  VERSE 1. Paul, an apostle, (not of men, neither by man, but by Jesus
  Christ).

The _argument_ of the epistle.

  VERSE 1. And God the Father.

More on verse 1.

  VERSES 2, 3. Grace be to you.

On verses 2 and 3.

  VERSE 3. And peace.

On verse 3 alone.

  VERSE 6. I marvel.

The last note.

CHAPTER 2

Before the first verse.

  VERSE 1. Then fourteen years after.

Chapter 2.

*** END OF THE PROJECT GUTENBERG EBOOK COMMENTARY ***
License text.
"""


def test_a_gutenberg_commentary_is_read_by_its_verse_headings(tmp_path):
  path = tmp_path / "pg1.txt"
  path.write_text(LUTHER_SAMPLE, encoding="utf-8")
  entries, introductions = read_gutenberg_commentary(path, 48)
  assert [(chapter, verse, end_verse) for _book, chapter, verse, end_verse, _text in entries] == [
    (1, 1, 1), (1, 2, 3), (1, 3, 5), (1, 6, None), (2, 1, None),
  ]
  # The two headings on verse 1 are one note, each heading kept as its own paragraph; italics are dropped.
  assert entries[0][4] == (
    "VERSE 1. Paul, an apostle, (not of men, neither by man, but by Jesus Christ).\n\n"
    "The argument of the epistle.\n\nVERSE 1. And God the Father.\n\nMore on verse 1."
  )
  assert introductions == [(48, 0, "PREFACE\n\nA preface that wraps."), (48, 2, "Before the first verse.")]


def test_a_gutenberg_commentary_that_goes_back_is_refused(tmp_path):
  path = tmp_path / "pg1.txt"
  path.write_text(LUTHER_SAMPLE.replace("  VERSE 6. I marvel.", "  VERSE 2. I marvel."), encoding="utf-8")
  with pytest.raises(CommentaryProblem, match="goes back from verse 3 to 2"):
    read_gutenberg_commentary(path, 48)


def test_paragraphs_are_joined_and_blank_ones_dropped():
  assert paragraphs_to_text(["First.", "  ", "Second.\n"]) == "First.\n\nSecond."


def test_a_verse_by_verse_commentary_covers_only_its_own_verses(tmp_path):
  folder = write_commentary(tmp_path, "john-gill", {("JHN", 3): [(1, ["A man."]), (3, ["Born again."])]})

  entries, introductions = read_commentary(folder, "john-gill", BOOKS)

  assert entries == [(43, 3, 1, 1, "A man."), (43, 3, 3, 3, "Born again.")]
  assert introductions == [(43, 0, "About John."), (43, 3, "In chapter 3.")]


def test_a_section_commentary_runs_each_entry_to_the_next_and_the_last_to_the_chapter_end(tmp_path):
  folder = write_commentary(tmp_path, "matthew-henry", {("JHN", 3): [(22, ["Second."]), (1, ["First."])]})

  entries, _ = read_commentary(folder, "matthew-henry", BOOKS)

  assert entries == [(43, 3, 1, 21, "First."), (43, 3, 22, None, "Second.")]


def test_entries_with_no_text_are_left_out(tmp_path):
  folder = write_commentary(tmp_path, "john-gill", {("JHN", 3): [(1, ["  "]), (2, ["Real."])]})

  entries, _ = read_commentary(folder, "john-gill", BOOKS)

  assert entries == [(43, 3, 2, 2, "Real.")]


def test_a_missing_chapter_file_is_skipped_and_a_missing_books_file_is_reported(tmp_path):
  folder = write_commentary(tmp_path, "john-gill", {("JHN", 3): [(1, ["x"])]})
  (folder / "john-gill" / "JHN_3.json").unlink()
  assert read_commentary(folder, "john-gill", BOOKS)[0] == []

  (folder / "john-gill" / "books.json").unlink()
  with pytest.raises(CommentaryProblem, match="Download the commentary first"):
    read_commentary(folder, "john-gill", BOOKS)


def test_an_unknown_book_is_reported(tmp_path):
  folder = write_commentary(tmp_path, "john-gill", {("JHN", 3): [(1, ["x"])]})

  with pytest.raises(CommentaryProblem, match="'JHN'"):
    read_commentary(folder, "john-gill", {"GEN": 1})


def test_unknown_commentaries_are_refused():
  assert check_ids(["john-gill"]) == ["john-gill"]
  with pytest.raises(CommentaryProblem, match="Unknown commentary: nobody"):
    check_ids(["nobody"])


def test_ranges_are_labelled_readably():
  assert label_range("John", 3, 16, 16) == "John 3:16"
  assert label_range("John", 3, 1, 21) == "John 3:1–21"
  assert label_range("John", 3, 22, None) == "John 3:22 to the end of the chapter"


# --- loading and looking up, in a throwaway schema ----------------------------------------------------


@pytest.fixture
def loaded(tmp_path, monkeypatch):
  """Load a Henry-style and a Gill-style commentary of John 3 into a throwaway schema."""
  with connect() as connection:
    connection.execute("DROP SCHEMA IF EXISTS commentaries_test CASCADE")
    connection.execute("CREATE SCHEMA commentaries_test")
    for table in ("commentaries", "commentary_entries", "commentary_introductions"):
      connection.execute(f"CREATE TABLE commentaries_test.{table} (LIKE public.{table} INCLUDING ALL)")

  def connect_to_test_schema():
    return psycopg.connect(os.environ["DATABASE_URL"], options="-c search_path=commentaries_test,public")

  monkeypatch.setattr(commentaries, "connect", connect_to_test_schema)
  henry = write_commentary(
    tmp_path / "a", "matthew-henry", {("JHN", 3): [(1, ["Nicodemus."]), (22, ["Baptizing."])]}
  )
  gill = write_commentary(
    tmp_path / "b", "john-gill", {("JHN", 3): [(16, ["God so loved."]), (17, ["Not to condemn."])]}
  )
  counts = []
  for folder, commentary_id in ((henry, "matthew-henry"), (gill, "john-gill")):
    entries, introductions = read_commentary(folder, commentary_id, BOOKS)
    counts.append(replace_commentary(commentary_id, entries, introductions))
  try:
    yield counts
  finally:
    with connect() as connection:
      connection.execute("DROP SCHEMA IF EXISTS commentaries_test CASCADE")


def test_loading_replaces_a_commentary_and_leaves_the_real_tables_alone(loaded, tmp_path):
  with connect() as connection:
    real_before = connection.execute("SELECT COUNT(*) FROM public.commentary_entries").fetchone()[0]

  assert loaded == [2, 2]
  folder = write_commentary(tmp_path / "c", "john-gill", {("JHN", 3): [(1, ["Only one."])]})
  entries, introductions = read_commentary(folder, "john-gill", BOOKS)
  assert replace_commentary("john-gill", entries, introductions) == 1  # replaced, not added to

  with connect() as connection:
    assert connection.execute("SELECT COUNT(*) FROM public.commentary_entries").fetchone()[0] == real_before


def test_a_verse_gets_the_section_that_contains_it_and_the_verse_note_that_matches(loaded):
  result = get_commentaries(JOHN, 3, 16)

  assert [entry["short_name"] for entry in result["commentaries"]] == ["Matthew Henry", "John Gill"]
  assert result["selected"] == "matthew-henry" and result["covers"] == "John 3:1–21"
  assert result["text"] == "Nicodemus."
  assert result["commentaries"][1]["covers"] == "John 3:16"
  # A visitor's notes on a commentary note are kept under the verse the note begins at, however it was reached.
  assert result["note_verse"] == 1 and [entry["start_verse"] for entry in result["commentaries"]] == [1, 16]


def test_the_commentary_asked_for_is_the_one_shown(loaded):
  result = get_commentaries(JOHN, 3, 16, "john-gill")

  assert result["selected"] == "john-gill" and result["text"] == "God so loved."
  assert [entry["id"] for entry in result["commentaries"]] == ["matthew-henry", "john-gill"]


def test_introductions_come_with_the_text(loaded):
  result = get_commentaries(JOHN, 3, 16)

  assert result["chapter_introduction"] == "In chapter 3." and result["book_introduction"] == "About John."


def test_the_last_section_runs_to_the_end_of_the_chapter(loaded):
  result = get_commentaries(JOHN, 3, 30)

  assert [entry["id"] for entry in result["commentaries"]] == ["matthew-henry"]
  assert result["covers"] == "John 3:22 to the end of the chapter"


def test_a_verse_nobody_comments_on_is_not_found(loaded):
  assert get_commentaries(JOHN, 4, 1) is None
  assert get_commentaries(JOHN, 3, 16, "adam-clarke") is None  # asked for, but has nothing here
  assert get_commentaries(999, 1, 1) is None


def test_the_api_serves_commentaries_and_refuses_what_it_does_not_have(loaded):
  body = client.get("/commentaries", params={"book": JOHN, "chapter": 3, "verse": 17, "commentary": "john-gill"}).json()

  assert body["text"] == "Not to condemn." and body["covers"] == "John 3:17"
  assert client.get("/commentaries", params={"book": JOHN, "chapter": 9, "verse": 9}).status_code == 404
  assert client.get("/commentaries", params={"book": 67, "chapter": 1, "verse": 1}).status_code == 422


# --- searching the text of the commentaries --------------------------------------------------------------


@pytest.fixture
def searchable(tmp_path, monkeypatch):
  """A few short notes in a throwaway schema, to search."""
  with connect() as connection:
    connection.execute("DROP SCHEMA IF EXISTS commentaries_search_test CASCADE")
    connection.execute("CREATE SCHEMA commentaries_search_test")
    for table in ("commentaries", "commentary_entries", "commentary_introductions"):
      connection.execute(f"CREATE TABLE commentaries_search_test.{table} (LIKE public.{table} INCLUDING ALL)")

  def connect_to_test_schema():
    return psycopg.connect(os.environ["DATABASE_URL"], options="-c search_path=commentaries_search_test,public")

  monkeypatch.setattr(commentaries, "connect", connect_to_test_schema)
  henry = write_commentary(tmp_path / "a", "matthew-henry", {
    ("JHN", 3): [(1, ["You must be born again, said Jesus to Nicodemus."]), (22, ["John was baptizing in Enon."])],
  })
  gill = write_commentary(tmp_path / "b", "john-gill", {
    ("JHN", 3): [(16, ["God so loved the world, and gave his Son. Love is the cause."]), (17, ["Not to condemn."])],
    ("GEN", 1): [(1, ["In the beginning God created. A son was born; he left, and came again."])],
  })
  for folder, commentary_id in ((henry, "matthew-henry"), (gill, "john-gill")):
    entries, introductions = read_commentary(folder, commentary_id, BOOKS)
    replace_commentary(commentary_id, entries, introductions)
  try:
    yield
  finally:
    with connect() as connection:
      connection.execute("DROP SCHEMA IF EXISTS commentaries_search_test CASCADE")


def find(query, match_mode="all", commentary=None, book_start=1, book_end=66, book=None, page=1, per_page=25,
         sort_by=None, sort_direction="asc"):
  return search_commentaries(query, match_mode, commentary, book_start, book_end, book, page, per_page, sort_by, sort_direction)


def references(result):
  return [(entry["commentary_id"], entry["reference"]) for entry in result["results"]]


def test_the_commentaries_are_listed_in_tab_order(searchable):
  assert [entry["short_name"] for entry in list_commentaries()] == ["Matthew Henry", "John Gill"]


def test_word_forms_match_and_the_excerpt_marks_the_words_found(searchable):
  result = find("love")

  assert result["source"] == "commentary" and result["total"] == 1
  entry = result["results"][0]
  assert (entry["commentary_id"], entry["commentary_name"], entry["reference"]) == ("john-gill", "John Gill", "John 3:16")
  assert f"{START_MARK}loved{STOP_MARK}" in entry["text"] and f"{START_MARK}Love{STOP_MARK}" in entry["text"]
  assert entry["translation"] == "john-gill" and entry["end_verse"] == 16


def test_common_words_are_not_ignored_so_phrases_are_exact(searchable):
  # "again" is a common word, but it still counts: only John 3:1 has "born again" side by side.
  assert references(find("born again", "phrase")) == [("matthew-henry", "John 3:1–21")]
  # Matching all the words in any places also finds Genesis, which has "born" and "again" apart.
  assert sorted(references(find("born again", "all"))) == [("john-gill", "Genesis 1:1"), ("matthew-henry", "John 3:1–21")]
  assert references(find("so loved the world", "phrase")) == [("john-gill", "John 3:16")]


def test_all_words_any_word_and_quoted_phrases(searchable):
  assert find("god world")["total"] == 1
  assert find("baptizing son")["total"] == 0
  assert find("baptizing son", "any")["total"] == 3
  assert references(find('"so loved" cause')) == [("john-gill", "John 3:16")]
  assert find('"loved so" cause')["total"] == 0


def test_a_section_note_is_found_and_labelled_with_the_verses_it_covers(searchable):
  result = find("enon")

  assert references(result) == [("matthew-henry", "John 3:22 to the end of the chapter")]


def test_the_search_can_be_limited_to_one_commentary_and_to_books(searchable):
  assert find("god", commentary="matthew-henry")["total"] == 0
  assert find("god", commentary="john-gill")["total"] == 2
  assert find("god", book_start=43, book_end=66)["total"] == 1
  assert find("god", book=1)["total"] == 1
  assert find("god")["book_counts"] == [{"book_number": 1, "count": 1}, {"book_number": 43, "count": 1}]


def test_results_are_in_bible_order_when_asked_and_paged(searchable):
  every = find("the", sort_by="verse")
  assert [entry["reference"] for entry in every["results"]] == ["Genesis 1:1", "John 3:16"]
  assert [entry["reference"] for entry in find("the", sort_by="verse", sort_direction="desc")["results"]] == ["John 3:16", "Genesis 1:1"]

  second_page = find("the", sort_by="verse", page=2, per_page=1)
  assert second_page["total"] == 2 and [entry["reference"] for entry in second_page["results"]] == ["John 3:16"]


def test_the_best_match_comes_first_by_default(searchable):
  result = find("love world god", "any")

  assert result["results"][0]["reference"] == "John 3:16"


def test_unusable_searches_are_refused(searchable):
  with pytest.raises(ValueError, match="at least one word"):
    find("   ")
  with pytest.raises(ValueError, match="Unknown commentary: nobody"):
    find("god", commentary="nobody")


def test_the_api_lists_and_searches_commentaries(searchable):
  assert [entry["id"] for entry in client.get("/commentary-list").json()] == ["matthew-henry", "john-gill"]

  body = client.get("/search-commentaries", params={"query": "Nicodemus"}).json()
  assert body["total"] == 1 and body["results"][0]["reference"] == "John 3:1–21"

  refused = client.get("/search-commentaries", params={"query": "god", "commentary": "nobody"})
  assert refused.status_code == 422 and "nobody" in refused.json()["detail"]
  assert client.get("/search-commentaries", params={"query": "god", "book_start": 50, "book_end": 40}).status_code == 422
  assert client.get("/search-commentaries", params={"query": "god", "sort_by": "text"}).status_code == 422


def test_the_note_comes_with_the_references_inside_it(tmp_path, monkeypatch):
  with connect() as connection:
    connection.execute("DROP SCHEMA IF EXISTS commentaries_refs_test CASCADE")
    connection.execute("CREATE SCHEMA commentaries_refs_test")
    for table in ("commentaries", "commentary_entries", "commentary_introductions"):
      connection.execute(f"CREATE TABLE commentaries_refs_test.{table} (LIKE public.{table} INCLUDING ALL)")

  def connect_to_test_schema():
    return psycopg.connect(os.environ["DATABASE_URL"], options="-c search_path=commentaries_refs_test,public")

  monkeypatch.setattr(commentaries, "connect", connect_to_test_schema)
  folder = write_commentary(
    tmp_path, "john-gill",
    {("JHN", 3): [(16, ["God so loved, Rom 5:8 says. And Joh 3:99 is no verse."])]},
    book_introduction="This book, like Gen 1:1, begins.",
  )
  entries, introductions = read_commentary(folder, "john-gill", BOOKS)
  try:
    replace_commentary("john-gill", entries, introductions)
    result = get_commentaries(JOHN, 3, 16)
  finally:
    with connect() as connection:
      connection.execute("DROP SCHEMA IF EXISTS commentaries_refs_test CASCADE")

  text = result["text"]
  assert [(text[start:end], code) for start, end, code in result["references"]] == [("Rom 5:8", "45:5:8")]
  intro = result["book_introduction"]
  assert [(intro[start:end], code) for start, end, code in result["book_introduction_references"]] == [("Gen 1:1", "1:1:1")]
  assert result["chapter_introduction"] == "In chapter 3." and result["chapter_introduction_references"] == []


# --- browsing a commentary -------------------------------------------------------------------------------


@pytest.fixture
def browsable(tmp_path, monkeypatch):
  """A Gill-style commentary on Genesis 1 and John 3 and 4, and a Henry-style one on John 3."""
  with connect() as connection:
    connection.execute("DROP SCHEMA IF EXISTS commentaries_browse_test CASCADE")
    connection.execute("CREATE SCHEMA commentaries_browse_test")
    for table in ("commentaries", "commentary_entries", "commentary_introductions"):
      connection.execute(f"CREATE TABLE commentaries_browse_test.{table} (LIKE public.{table} INCLUDING ALL)")

  def connect_to_test_schema():
    return psycopg.connect(os.environ["DATABASE_URL"], options="-c search_path=commentaries_browse_test,public")

  monkeypatch.setattr(commentaries, "connect", connect_to_test_schema)
  gill = write_commentary(tmp_path / "a", "john-gill", {
    ("GEN", 1): [(1, ["In the beginning, see Joh 1:1."])],
    ("JHN", 3): [(17, ["Not to condemn."]), (16, ["God so loved."])],
    ("JHN", 4): [(1, ["The Pharisees heard."])],
  })
  henry = write_commentary(tmp_path / "b", "matthew-henry", {("JHN", 3): [(1, ["Nicodemus."]), (22, ["Baptizing."])]})
  for folder, commentary_id in ((gill, "john-gill"), (henry, "matthew-henry")):
    entries, introductions = read_commentary(folder, commentary_id, BOOKS)
    replace_commentary(commentary_id, entries, introductions)
  try:
    yield
  finally:
    with connect() as connection:
      connection.execute("DROP SCHEMA IF EXISTS commentaries_browse_test CASCADE")


def test_the_contents_list_the_books_and_chapters_a_commentary_has_notes_on(browsable):
  result = get_contents("john-gill")

  assert result["commentary"] == {"id": "john-gill", "name": COMMENTARIES["john-gill"][0], "short_name": "John Gill"}
  assert result["books"] == [
    {"number": 1, "name": "Genesis", "chapters": [1]},
    {"number": 43, "name": "John", "chapters": [3, 4]},
  ]
  assert get_contents("matthew-henry")["books"] == [{"number": 43, "name": "John", "chapters": [3]}]
  assert get_contents("nobody") is None


def test_a_chapter_comes_in_verse_order_with_what_each_note_covers(browsable):
  result = get_chapter_notes("john-gill", JOHN, 3)

  assert (result["book_name"], result["chapter"]) == ("John", 3)
  assert [(entry["verse"], entry["covers"], entry["text"]) for entry in result["entries"]] == [
    (16, "John 3:16", "God so loved."), (17, "John 3:17", "Not to condemn."),
  ]
  assert result["chapter_introduction"] == "In chapter 3." and result["book_introduction"] == "About John."


def test_a_section_commentary_shows_the_verses_each_section_covers(browsable):
  entries = get_chapter_notes("matthew-henry", JOHN, 3)["entries"]

  assert [entry["covers"] for entry in entries] == ["John 3:1–21", "John 3:22 to the end of the chapter"]


def test_the_references_in_each_note_are_found(browsable):
  genesis = get_chapter_notes("john-gill", 1, 1)["entries"][0]

  assert [(genesis["text"][start:end], code) for start, end, code in genesis["references"]] == [("Joh 1:1", "43:1:1")]


def test_previous_and_next_chapters_run_across_books_and_stop_at_the_ends(browsable):
  first = get_chapter_notes("john-gill", 1, 1)
  middle = get_chapter_notes("john-gill", JOHN, 3)
  last = get_chapter_notes("john-gill", JOHN, 4)

  assert first["previous"] is None and first["next"] == {"book_number": 43, "book_name": "John", "chapter": 3}
  assert middle["previous"] == {"book_number": 1, "book_name": "Genesis", "chapter": 1}
  assert middle["next"] == {"book_number": 43, "book_name": "John", "chapter": 4}
  assert last["next"] is None


def test_a_chapter_without_notes_is_not_found(browsable):
  assert get_chapter_notes("john-gill", JOHN, 9) is None
  assert get_chapter_notes("matthew-henry", 1, 1) is None
  assert get_chapter_notes("nobody", JOHN, 3) is None
  assert get_chapter_notes("john-gill", 999, 1) is None


def test_the_api_serves_contents_and_chapters(browsable):
  assert client.get("/commentary-contents", params={"commentary": "john-gill"}).json()["books"][0]["name"] == "Genesis"
  assert client.get("/commentary-contents", params={"commentary": "nobody"}).status_code == 404

  body = client.get("/commentary-chapter", params={"commentary": "john-gill", "book": JOHN, "chapter": 4}).json()
  assert body["entries"][0]["covers"] == "John 4:1" and body["previous"]["chapter"] == 3
  assert client.get("/commentary-chapter", params={"commentary": "john-gill", "book": JOHN, "chapter": 9}).status_code == 404
  assert client.get("/commentary-chapter", params={"commentary": "john-gill", "book": 67, "chapter": 1}).status_code == 422

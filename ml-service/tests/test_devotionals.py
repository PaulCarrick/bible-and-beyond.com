"""Tests for reading, loading and looking up the devotionals. The files used are small imitations of
the real ones; loading works in a throwaway schema."""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

import devotionals
from devotionals import (
  DEVOTIONALS,
  DevotionalProblem,
  Entry,
  Parsed,
  check_ids,
  get_contents,
  get_unit,
  list_devotionals,
  paragraphs_of_lines,
  parse_ccel_daily,
  parse_imitation,
  parse_practice,
  read_devotional,
  replace_devotional,
  title_case,
)
from main import app
from search import connect

client = TestClient(app)

DAILY_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ThML PUBLIC "-//CCEL/DTD Theological Markup Language//EN" "http://www.ccel.org/dtd/ThML10.dtd">
<ThML><ThML.head><title>Sample</title></ThML.head><ThML.body>
<div1 title="Title Page" id="i"><h2>Sample</h2></div1>
<div1 title="January" id="january"><h1>January</h1>
<div2 title="Morning, January 1" id="d0101am">
<h2>Morning, January 1</h2>
<p class="crossref"><a href="#d0101pm">Go To Evening Reading</a></p>
<p class="passage"><i>“They did eat of the fruit.”</i></p>
<h3 class="scripPassage"><scripRef passage="Jos 5:12">Joshua 5:12</scripRef></h3>
<p class="normal">Israel’s weary wanderings were all over,
and the promised rest was attained.</p>
<p class="normal">A second paragraph.</p>
</div2>
<div2 title="Evening, January 1" id="d0101pm">
<h2>Evening, January 1</h2>
<p class="passage"><i>“We will be glad.”</i></p>
<p class="normal">Evening words.</p>
</div2>
<div2 title="Morning, January 2" id="d0102am"><p class="normal">Second morning.</p></div2>
</div1>
<div1 title="February" id="february">
<div2 title="Morning, February 29" id="d0229am"><p class="normal">Leap day.</p></div2>
<div2 title="Index of Scripture References" id="index"><p>Gen 1:1</p></div2>
</div1></ThML.body></ThML>
"""

DAILY_LIGHT_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<ThML><ThML.head><title>Sample</title></ThML.head><ThML.body>
<div1 title="January"><div2 title="Morning, January 1" id="d0101am">
<p id="a"></p>
<p><b>JANUARY 1</b><span class="timeOfDay">MORNING</span></p>
<p><b><i><span>This one thing I do.</span></i></b>—<scripRef passage="PHI. 3:13,14.">PHI. 3:13,14.</scripRef></p>
<p>Father, I will that they be with me.</p>
<p><span><scripRef passage="John 17:24">John 17:24</scripRef>.  -<scripRef passage="II Tim. 1:12">II Tim. 1:12</scripRef>.<scripRef passage="I Cor. 9:24-25">I Cor. 9:24,25</scripRef>.</span></p>
</div2></div1></ThML.body></ThML>
"""

IMITATION_SAMPLE = """Header of the Project Gutenberg book
*** START OF THE PROJECT GUTENBERG EBOOK THE IMITATION OF CHRIST ***

The Imitation of Christ

Contents

 THE FIRST BOOK
 CHAPTER I Of the imitation of Christ
 THE SECOND BOOK


THE IMITATION OF CHRIST




THE FIRST BOOK
ADMONITIONS PROFITABLE FOR THE SPIRITUAL LIFE




CHAPTER I

Of the imitation of Christ, and of contempt of the world and all its
vanities


_He that followeth me shall not walk in darkness_,(1) saith the Lord.
These are the words of Christ.

2. His teaching surpasseth all teaching of holy men.

(1) John viii. 12.


CHAPTER II

Of thinking humbly of oneself

Every man naturally desireth to know.



THE SECOND BOOK
ADMONITIONS CONCERNING THE INNER LIFE


CHAPTER I

Of the inward life

The Kingdom of God is within you.
*** END OF THE PROJECT GUTENBERG EBOOK THE IMITATION OF CHRIST ***
License text that must not be read.
"""

PRACTICE_SAMPLE = """Header
*** START OF THE PROJECT GUTENBERG EBOOK THE PRACTICE ***
THE PRACTICE OF THE PRESENCE
BROTHER LAWRENCE.
FLEMING H. REVELL COMPANY,


PREFACE.


This book consists of notes of several conversations
had with, and letters written by Nicholas Herman.


CONVERSATIONS.


FIRST CONVERSATION.


The first time I saw _Brother Lawrence_, was upon the 3d of August.

SECOND CONVERSATION.

The second talk.

FIRST LETTER.

_To a Reverend Mother_.

GOD knoweth best what is needful for us.

SECOND LETTER.

More words.
*** END OF THE PROJECT GUTENBERG EBOOK THE PRACTICE ***
"""


def write(tmp_path, name, text):
  path = tmp_path / name
  path.write_text(text, encoding="utf-8")
  return path


# --- reading the daily devotionals -------------------------------------------------------------------------


def test_each_reading_is_a_heading_and_its_paragraphs(tmp_path):
  parsed = parse_ccel_daily(write(tmp_path, "daily.xml", DAILY_SAMPLE))

  morning = parsed.entries[0]
  assert (morning.section, morning.unit, morning.part, morning.heading) == (1, 1, 1, "Morning")
  assert morning.unit_title == "January 1"
  assert morning.text == (
    "“They did eat of the fruit.”\n\nJoshua 5:12\n\n"
    "Israel’s weary wanderings were all over, and the promised rest was attained.\n\nA second paragraph."
  )


def test_a_days_morning_comes_before_its_evening_and_days_are_in_order(tmp_path):
  parsed = parse_ccel_daily(write(tmp_path, "daily.xml", DAILY_SAMPLE))

  assert [(entry.section, entry.unit, entry.heading) for entry in parsed.entries] == [
    (1, 1, "Morning"), (1, 1, "Evening"), (1, 2, "Morning"), (2, 29, "Morning"),
  ]
  assert [entry.part for entry in parsed.entries] == [1, 2, 1, 1]
  assert parsed.sections[0] == (1, "January") and len(parsed.sections) == 12


def test_the_title_page_the_index_and_the_navigation_line_are_left_out(tmp_path):
  parsed = parse_ccel_daily(write(tmp_path, "daily.xml", DAILY_SAMPLE))

  everything = "\n".join(entry.text for entry in parsed.entries)
  assert "Go To Evening Reading" not in everything and "Gen 1:1" not in everything


def test_daily_light_lines_of_references_become_groups(tmp_path):
  parsed = parse_ccel_daily(write(tmp_path, "light.xml", DAILY_LIGHT_SAMPLE))

  assert parsed.entries[0].text == (
    "This one thing I do.—PHI. 3:13,14.\n\nFather, I will that they be with me.\n\n"
    "John 17:24; II Tim. 1:12\n\nI Cor. 9:24,25"
  )
  assert "JANUARY 1" not in parsed.entries[0].text


def test_a_reading_with_no_text_is_refused(tmp_path):
  empty = DAILY_SAMPLE.replace('<p class="normal">Second morning.</p>', "")

  with pytest.raises(DevotionalProblem, match="morning reading of January 2 is empty"):
    parse_ccel_daily(write(tmp_path, "daily.xml", empty))


def test_a_file_with_a_doctype_that_defines_entities_is_refused(tmp_path):
  hostile = DAILY_SAMPLE.replace("<ThML>", '<!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><ThML>', 1).replace(
    '<!DOCTYPE ThML PUBLIC "-//CCEL/DTD Theological Markup Language//EN" "http://www.ccel.org/dtd/ThML10.dtd">', ""
  )

  with pytest.raises(Exception, match="(?i)entit|forbidden"):
    parse_ccel_daily(write(tmp_path, "hostile.xml", hostile))


# --- reading the Gutenberg books -------------------------------------------------------------------------


def test_hard_wrapped_lines_become_paragraphs_and_italic_marks_go():
  assert paragraphs_of_lines(["_He that_ follows", "me shall not walk", "", "Second.", "", "", "Third."]) == [
    "He that follows me shall not walk", "Second.", "Third.",
  ]


def test_the_imitation_is_read_by_book_and_chapter_after_its_contents(tmp_path):
  parsed = parse_imitation(write(tmp_path, "imitation.txt", IMITATION_SAMPLE))

  assert parsed.sections == [
    (1, "The First Book: Admonitions Profitable for the Spiritual Life"),
    (2, "The Second Book: Admonitions Concerning the Inner Life"),
  ]
  assert [(entry.section, entry.unit, entry.unit_title) for entry in parsed.entries] == [
    (1, 1, "Chapter I. Of the imitation of Christ, and of contempt of the world and all its vanities"),
    (1, 2, "Chapter II. Of thinking humbly of oneself"),
    (2, 1, "Chapter I. Of the inward life"),
  ]
  assert parsed.entries[0].text.startswith("He that followeth me shall not walk in darkness,(1) saith the Lord.")
  assert "(1) John viii. 12." in parsed.entries[0].text
  assert "License text" not in parsed.entries[2].text and parsed.entries[0].heading == ""


def test_the_practice_has_a_preface_conversations_and_letters(tmp_path):
  parsed = parse_practice(write(tmp_path, "practice.txt", PRACTICE_SAMPLE))

  assert parsed.sections == [(1, "Preface"), (2, "Conversations"), (3, "Letters")]
  assert [(entry.section, entry.unit, entry.unit_title) for entry in parsed.entries] == [
    (1, 1, "Preface"), (2, 1, "First Conversation"), (2, 2, "Second Conversation"),
    (3, 1, "First Letter"), (3, 2, "Second Letter"),
  ]
  assert parsed.entries[1].text == "The first time I saw Brother Lawrence, was upon the 3d of August."
  assert parsed.entries[3].text.startswith("To a Reverend Mother.\n\nGOD knoweth best")


def test_a_text_without_the_gutenberg_notices_is_refused(tmp_path):
  with pytest.raises(DevotionalProblem, match="not a Project Gutenberg text"):
    parse_imitation(write(tmp_path, "plain.txt", "Just some text."))


def test_headings_are_given_capital_letters_like_titles():
  assert title_case("ADMONITIONS PROFITABLE FOR THE SPIRITUAL LIFE") == "Admonitions Profitable for the Spiritual Life"
  assert title_case("FIRST CONVERSATION") == "First Conversation"


def test_a_file_that_has_the_wrong_number_of_days_or_chapters_is_refused(tmp_path):
  write(tmp_path, DEVOTIONALS["imitation-of-christ"]["file_name"], IMITATION_SAMPLE)

  with pytest.raises(DevotionalProblem, match="expected 114 days or chapters; found 3"):
    read_devotional(tmp_path, "imitation-of-christ")
  with pytest.raises(DevotionalProblem, match="is missing"):
    read_devotional(tmp_path, "daily-light")


def test_unknown_devotionals_are_refused():
  assert check_ids(["daily-light"]) == ["daily-light"]
  with pytest.raises(DevotionalProblem, match="Unknown devotional or book: nobody"):
    check_ids(["nobody"])


# --- loading and looking up, in a throwaway schema -----------------------------------------------------------


@pytest.fixture
def loaded(monkeypatch):
  """A small Morning and Evening and a small Imitation, in a throwaway schema."""
  with connect() as connection:
    connection.execute("DROP SCHEMA IF EXISTS devotionals_test CASCADE")
    connection.execute("CREATE SCHEMA devotionals_test")
    for table in ("devotionals", "devotional_sections", "devotional_entries"):
      connection.execute(f"CREATE TABLE devotionals_test.{table} (LIKE public.{table} INCLUDING ALL)")

  def connect_to_test_schema():
    return psycopg.connect(os.environ["DATABASE_URL"], options="-c search_path=devotionals_test,public")

  monkeypatch.setattr(devotionals, "connect", connect_to_test_schema)
  daily = Parsed(
    [(1, "January"), (2, "February")],
    [
      Entry(1, 1, 1, "January 1", "Morning", "Joshua 5:12\n\nSee Joh 3:16 and ISA. 53:5."),
      Entry(1, 1, 2, "January 1", "Evening", "Evening words."),
      Entry(1, 2, 1, "January 2", "Morning", "Second day."),
      Entry(2, 1, 1, "February 1", "Morning", "A new month."),
    ],
  )
  chapters = Parsed(
    [(1, "The First Book: Admonitions")],
    [Entry(1, 1, 1, "Chapter I. Of the imitation", "", "He that followeth me."), Entry(1, 2, 1, "Chapter II. Of humility", "", "Every man.")],
  )
  counts = (replace_devotional("morning-and-evening", daily), replace_devotional("imitation-of-christ", chapters))
  try:
    yield counts
  finally:
    with connect() as connection:
      connection.execute("DROP SCHEMA IF EXISTS devotionals_test CASCADE")


def test_loading_replaces_a_devotional_and_leaves_the_real_tables_alone(loaded):
  with connect() as connection:
    real_before = connection.execute("SELECT COUNT(*) FROM public.devotional_entries").fetchone()[0]

  assert loaded == (4, 2)
  assert replace_devotional("imitation-of-christ", Parsed([(1, "Only")], [Entry(1, 1, 1, "One", "", "x")])) == 1

  with connect() as connection:
    assert connection.execute("SELECT COUNT(*) FROM public.devotional_entries").fetchone()[0] == real_before


def test_the_devotionals_are_listed_in_order_with_their_sources(loaded):
  listed = list_devotionals()

  assert [entry["id"] for entry in listed] == ["morning-and-evening", "imitation-of-christ"]
  assert listed[0] == {
    "id": "morning-and-evening", "name": "Morning and Evening", "author": "Charles H. Spurgeon", "kind": "daily",
    "source_name": "Christian Classics Ethereal Library", "source_url": "https://ccel.org/ccel/spurgeon/morneve",
    "translator": None,
  }
  assert listed[1]["translator"] == "translated by William Benham, 1886" and listed[1]["kind"] == "chapters"


def test_the_contents_list_the_sections_and_their_days_or_chapters(loaded):
  daily = get_contents("morning-and-evening")
  chapters = get_contents("imitation-of-christ")

  assert [(section["number"], section["title"], [unit["number"] for unit in section["units"]]) for section in daily["sections"]] == [
    (1, "January", [1, 2]), (2, "February", [1]),
  ]
  assert daily["sections"][0]["units"][0] == {"number": 1, "title": "January 1"}
  assert chapters["sections"][0]["units"][1]["title"] == "Chapter II. Of humility"
  assert get_contents("nobody") is None


def test_a_day_has_its_morning_then_its_evening_and_the_references_in_them(loaded):
  day = get_unit("morning-and-evening", 1, 1)

  assert (day["title"], day["section_title"]) == ("January 1", "January")
  assert [(entry["heading"], entry["text"][:11]) for entry in day["entries"]] == [("Morning", "Joshua 5:12"), ("Evening", "Evening wor")]
  morning = day["entries"][0]
  assert [(morning["text"][start:end], code) for start, end, code in morning["references"]] == [
    ("Joshua 5:12", "6:5:12"), ("Joh 3:16", "43:3:16"), ("ISA. 53:5", "23:53:5"),
  ]


def test_the_day_before_and_after_run_across_months_and_stop_at_the_ends(loaded):
  last_of_january = get_unit("morning-and-evening", 1, 2)
  first = get_unit("morning-and-evening", 1, 1)
  last = get_unit("morning-and-evening", 2, 1)

  assert first["previous"] is None and first["next"] == {"section": 1, "unit": 2, "title": "January 2", "section_title": "January"}
  assert last_of_january["next"] == {"section": 2, "unit": 1, "title": "February 1", "section_title": "February"}
  assert last["next"] is None and last["previous"]["unit"] == 2


def test_a_day_or_chapter_that_is_not_there_is_not_found(loaded):
  assert get_unit("morning-and-evening", 1, 9) is None
  assert get_unit("nobody", 1, 1) is None


def test_the_api_serves_the_list_the_contents_and_a_day(loaded):
  assert [entry["id"] for entry in client.get("/devotionals").json()] == ["morning-and-evening", "imitation-of-christ"]
  assert client.get("/devotional-contents", params={"devotional": "imitation-of-christ"}).json()["sections"][0]["title"].startswith("The First Book")

  body = client.get("/devotional-unit", params={"devotional": "morning-and-evening", "section": 1, "unit": 1}).json()
  assert body["title"] == "January 1" and body["next"]["unit"] == 2

  assert client.get("/devotional-contents", params={"devotional": "nobody"}).status_code == 404
  assert client.get("/devotional-unit", params={"devotional": "morning-and-evening", "section": 1, "unit": 99}).status_code == 404
  assert client.get("/devotional-unit", params={"devotional": "morning-and-evening", "section": 0, "unit": 1}).status_code == 422


def gutenberg(body: str) -> str:
  return "Header\n*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\n" + body + "\n*** END OF THE PROJECT GUTENBERG EBOOK TEST ***\nLicence\n"


def test_orthodoxy_is_read_as_a_preface_and_chapters_titled_from_the_contents(tmp_path):
  from devotionals import parse_orthodoxy

  path = tmp_path / "orthodoxy.txt"
  path.write_text(gutenberg(
    "ORTHODOXY\n\nPREFACE\n\n     This book is meant\nto be a companion.\n\nCONTENTS\n\n   I.  Introduction in Defence of Everything Else\n"
    "  II.  The Maniac\n\nORTHODOXY\n\nI INTRODUCTION IN DEFENCE OF EVERYTHING ELSE\n\nThe only excuse.\n\nII THE MANIAC\n\nThoroughly worldly people.\n"
  ))
  parsed = parse_orthodoxy(path)

  assert parsed.sections == [(1, "Preface"), (2, "Chapters")]
  assert [(entry.section, entry.unit, entry.unit_title, entry.text) for entry in parsed.entries] == [
    (1, 1, "Preface", "This book is meant to be a companion."),
    (2, 1, "Introduction in Defence of Everything Else", "The only excuse."),
    (2, 2, "The Maniac", "Thoroughly worldly people."),
  ]


def test_the_summa_reads_its_questions_by_treatise_even_one_without_its_heading(tmp_path):
  from devotionals import SUMMA_TREATISES, parse_summa

  path = tmp_path / "summa.txt"
  path.write_text(gutenberg(
    "CONTENTS\n\nPROLOGUE\n\nPROLOGUE\n\nBecause the Master.\n\nQUESTION 1\n\nTHE NATURE OF SACRED DOCTRINE\n(In Ten Articles)\n\nTo place our purpose.\n"
    "_______________________\n\nON FATE\n(In Four Articles)\n\nWe now consider fate.\n\nQUESTION 3\n\nOF THE SIMPLICITY OF GOD\n(In Eight Articles)\n\nWhen the existence.\n"
  ))
  parsed = parse_summa(path, SUMMA_TREATISES)

  assert [(entry.section, entry.unit, entry.unit_title) for entry in parsed.entries] == [
    (0, 1, "Prologue"),
    (1, 1, "Question 1: The Nature of Sacred Doctrine"),
    (2, 2, "Question 2: On Fate"),
    (2, 3, "Question 3: Of the Simplicity of God"),
  ]

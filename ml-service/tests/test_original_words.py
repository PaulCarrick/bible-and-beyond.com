"""Tests for reading and loading the Hebrew and Greek words, and for the word study lookups.

The loading and lookup tests work in a throwaway schema (words_test) that shadows the two real
tables, so they never touch the loaded data.
"""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

import original_words
import search
from original_words import (
  BOOK_NUMBERS,
  OriginalWordsProblem,
  clean_definition,
  clean_original,
  clean_transliteration,
  link_words_to_lexicon,
  parse_greek_line,
  parse_hebrew_line,
  read_lexicon,
  read_words,
  replace_all,
  resolve_strong_code,
)
from main import app
from search import connect, find_strong_entry, parse_strong_query

client = TestClient(app)
GENESIS, JOHN = 1, 43

HEBREW_HEADER = "TAHOT Gen-Deu - Translators Amalgamated Hebrew OT - STEPBible.org CC BY\n"
GREEK_HEADER = "TAGNT Mat-Jhn - Translators Amalgamated Greek NT -  STEPBible.org CC BY 4.0\n"

HEBREW_FIRST = "Gen.1.1#01=L\tבְּ/רֵאשִׁ֖ית\tbe./re.Shit\tin/ beginning\tH9003/{H7225G}\tHR/Ncfsa\t\t\tH7225G\t\t\n"
HEBREW_SECOND = "Gen.1.1#02=L\tבָּרָ֣א\tba.Ra'\the created\t{H1254A}\tHVqp3ms\t\t\tH1254A\t\t\n"
HEBREW_RENUMBERED = "Mal.4.6(3.24)#15=L\tחֵֽרֶם\tChe.rem\ttotal destruction\t{H2764A}\\H9016\tHNcmsa\t\t\tH2764A\t\t\n"
GREEK_LOVED = "Jhn.3.16#03=NKO\tἠγάπησεν (ēgapēsen)\tloved\tG0025=V-AAI-3S\tἀγαπάω=to love\tNA28+NA27\t\t\tAmó\tloved\t#03\tG0025\t\n"
GREEK_LOVED_AGAIN = "Jhn.3.17#05=NKO\tἠγάπησεν (ēgapēsen)\tloved\tG0025=V-AAI-3S\tἀγαπάω=to love\tNA28\t\t\t\t\t#05\tG0025\t\n"
GREEK_OLDER_ONLY = "Jhn.3.16#11=K(O)\tαὐτοῦ (autou)\this\tG0846=P-GSM\tαὐτός=he\tTR+Byz\t\t\t\t\t#11\tG0846\t\n"
GREEK_JOINED_NAME = "Mat.1.6#07=NKO\tΔαυὶδ (Dauid)\tDavid\tH1732|G1138«G1138=N-NSM-P\tΔαυίδ=David\tNA28\t\t\t\t\t#07\tG1138\t\n"

GREEK_LEXICON_ROW = (
  "G0025\tG0025 =\tG0025\tἀγαπάω\tagapaō\tG:V\tto love\t"
  " <b>ἀγαπάω</b>, -ῶ,<BR />to love, to prize. <ref='Mat.5.43'>Mat.5:43</ref> &amp; more<br>2) second line\n"
)
HEBREW_LEXICON_ROW = "H7225\tH7225G =\tH7225G\tרֵאשִׁית\tre.shit\tH:N-F\tfirst: beginning\t: beginning<br>1) first, beginning\n"
OTHER_MEANING_ROW = "H7225\tH7225H = a Meaning of\tH7225G\tרֵאשִׁית\tre.shit\tH:N-F\tfirst: best\t: best\n"


def write(tmp_path, name, text):
  path = tmp_path / name
  path.write_text(text, encoding="utf-8")
  return path


# --- reading the words -----------------------------------------------------------------------------


def test_every_book_has_a_number():
  assert sorted(BOOK_NUMBERS.values()) == list(range(1, 67))


def test_a_hebrew_word_keeps_its_main_strongs_number_and_not_the_prefix():
  word = parse_hebrew_line(HEBREW_FIRST, 1)

  assert word.verse == (GENESIS, 1, 1) and word.position == 1
  assert word.original == "בְּ/רֵאשִׁ֖ית" and word.transliteration == "be./re.Shit"
  assert word.english == "in/ beginning" and word.strong_code == "H7225G" and word.grammar == "HR/Ncfsa"


def test_punctuation_that_came_with_the_words_is_stripped():
  assert clean_original("εὐδόκησα.¶", True) == "εὐδόκησα"
  assert clean_original("κόσμον,", True) == "κόσμον"
  assert clean_original("τίς;", True) == "τίς"
  assert clean_original("ἀλλ᾽", True) == "ἀλλ᾽"  # the apostrophe of an elided word stays
  assert clean_original("הָאָֽרֶץ׃", False) == "הָאָֽרֶץ"
  assert clean_original("בֶן\\־", False) == "בֶן"
  assert clean_original("אֶחָֽד\\׃\\ \\פ", False) == "אֶחָֽד"  # verse end and paragraph letter
  assert clean_original("כְּדָרְ\\־לָעֹ֔מֶר", False) == "כְּדָרְ־לָעֹ֔מֶר"  # two words joined as one name
  assert clean_original("בְּ/רֵאשִׁ֖ית", False) == "בְּ/רֵאשִׁ֖ית"  # prefixes stay joined
  assert clean_original("׆", False) == "׆"  # never leave a word empty
  assert clean_transliteration("ven-") == "ven"
  assert clean_transliteration("be./re.Shit") == "be./re.Shit"


def test_the_english_verse_number_is_used_when_the_hebrew_numbering_differs():
  word = parse_hebrew_line(HEBREW_RENUMBERED, 1)

  assert word.verse == (39, 4, 6) and word.position == 15


def test_lines_that_are_not_words_are_ignored():
  assert parse_hebrew_line("# Gen.1.1\tבְּרֵאשִׁ֖ית\n", 1) is None
  assert parse_hebrew_line("\n", 1) is None
  assert parse_hebrew_line("Gen.1.1#01=K\tx\ty\tz\t{H1111}\tHN\n", 1) is None  # not the Leningrad reading
  assert parse_greek_line("Word & Type\tGreek\tEnglish translation\n", 1) is None


def test_an_unknown_book_is_reported_with_its_line_number():
  with pytest.raises(OriginalWordsProblem, match="Line 7: I do not know the book 'Xyz'"):
    parse_hebrew_line("Xyz.1.1#01=L\ta\tb\tc\t{H0001}\tg\n", 7)


def test_a_greek_word_is_split_into_greek_and_transliteration():
  word = parse_greek_line(GREEK_LOVED, 1)

  assert word.verse == (JOHN, 3, 16) and word.position == 3
  assert (word.original, word.transliteration, word.english) == ("ἠγάπησεν", "ēgapēsen", "loved")
  assert word.strong_code == "G0025" and word.grammar == "V-AAI-3S"


def test_greek_words_only_in_the_older_text_are_left_out():
  assert parse_greek_line(GREEK_OLDER_ONLY, 1) is None


def test_a_greek_name_takes_the_greek_number_not_the_hebrew_one():
  word = parse_greek_line(GREEK_JOINED_NAME, 1)

  assert word.strong_code == "G1138" and word.grammar == "N-NSM-P"


def test_read_words_chooses_the_format_from_the_file_header(tmp_path):
  hebrew = write(tmp_path, "tahot1.txt", HEBREW_HEADER + HEBREW_FIRST + HEBREW_SECOND)
  greek = write(tmp_path, "tagnt1.txt", GREEK_HEADER + GREEK_LOVED + GREEK_OLDER_ONLY)

  words = read_words([hebrew, greek])

  assert [word.strong_code for word in words] == ["H7225G", "H1254A", "G0025"]


# --- reading the lexicon -----------------------------------------------------------------------------


def test_definitions_become_plain_text():
  text = clean_definition(" <b>ἀγαπάω</b>, -ῶ,<BR />to love <ref='Mat.5.43'>Mat.5:43</ref> &amp; more<br>2) next")

  assert text == "ἀγαπάω, -ῶ,\nto love Mat.5:43 & more\n2) next"


def test_the_lexicons_underscore_indentation_becomes_space():
  text = clean_definition("to love<br>__1. Of human affection<br>____(a) God's love")

  assert text == "to love\n\u00a0\u00a0\u00a0\u00a01. Of human affection\n" + "\u00a0\u00a0" * 4 + "(a) God's love"


def test_the_lexicon_is_read_by_strongs_number(tmp_path):
  path = write(tmp_path, "tbesg.txt", "Some heading\n" + GREEK_LEXICON_ROW + "\n")

  entries = read_lexicon([path])

  entry = entries["G0025"]
  assert entry.language == "greek" and entry.original == "ἀγαπάω" and entry.gloss == "to love"
  assert "<" not in entry.definition and "Mat.5:43" in entry.definition


def test_the_first_entry_wins_when_a_number_repeats_and_hebrew_is_labelled(tmp_path):
  path = write(tmp_path, "tbesh.txt", HEBREW_LEXICON_ROW + HEBREW_LEXICON_ROW.replace("first: beginning", "duplicate"))

  entries = read_lexicon([path])

  assert entries["H7225G"].language == "hebrew" and entries["H7225G"].gloss == "first: beginning"


def test_a_number_with_a_sense_letter_the_lexicon_lacks_falls_back_to_the_main_entry(tmp_path):
  path = write(tmp_path, "tbesh.txt", HEBREW_LEXICON_ROW + OTHER_MEANING_ROW)
  entries = read_lexicon([path])

  assert resolve_strong_code("H7225G", entries) == "H7225G"  # already listed
  assert resolve_strong_code("H7225J", entries) == "H7225G"  # falls back to the "G" entry
  assert resolve_strong_code("H9999", entries) == "H9999"  # nothing to fall back to
  assert resolve_strong_code(None, entries) is None
  words = link_words_to_lexicon([parse_hebrew_line(HEBREW_FIRST.replace("H7225G", "H7225J"), 1)], entries)
  assert words[0].strong_code == "H7225G"


# --- loading and looking up, in a throwaway schema -------------------------------------------------


@pytest.fixture
def loaded(tmp_path, monkeypatch):
  """Load a few words and entries into a throwaway schema that shadows the real tables."""
  with connect() as connection:
    connection.execute("DROP SCHEMA IF EXISTS words_test CASCADE")
    connection.execute("CREATE SCHEMA words_test")
    for table in ("original_words", "lexicon_entries"):
      connection.execute(f"CREATE TABLE words_test.{table} (LIKE public.{table} INCLUDING DEFAULTS)")

  def connect_to_test_schema():
    return psycopg.connect(os.environ["DATABASE_URL"], options="-c search_path=words_test,public")

  monkeypatch.setattr(original_words, "connect", connect_to_test_schema)
  monkeypatch.setattr(search, "connect", connect_to_test_schema)
  hebrew = write(tmp_path, "tahot1.txt", HEBREW_HEADER + HEBREW_SECOND + HEBREW_FIRST)
  greek = write(tmp_path, "tagnt1.txt", GREEK_HEADER + GREEK_LOVED + GREEK_LOVED_AGAIN)
  lexicon = write(tmp_path, "tbesg.txt", GREEK_LEXICON_ROW + HEBREW_LEXICON_ROW)
  entries = read_lexicon([lexicon])
  counts = replace_all(link_words_to_lexicon(read_words([hebrew, greek]), entries), entries)
  try:
    yield counts
  finally:
    with connect() as connection:
      connection.execute("DROP SCHEMA IF EXISTS words_test CASCADE")


def test_loading_replaces_everything_and_leaves_the_real_tables_alone(loaded):
  with connect() as connection:
    real_before = connection.execute("SELECT COUNT(*) FROM public.original_words").fetchone()[0]

  assert loaded == (4, 2)
  assert replace_all([], {}) == (0, 0)  # loading again replaces rather than adds

  with connect() as connection:
    real_after = connection.execute("SELECT COUNT(*) FROM public.original_words").fetchone()[0]
  assert real_after == real_before


def test_a_verses_words_come_in_reading_order_with_their_lexicon_gloss(loaded):
  result = client.get("/original-words", params={"book": GENESIS, "chapter": 1, "verse": 1}).json()

  assert result["language"] == "hebrew" and result["book_name"] == "Genesis"
  assert [word["transliteration"] for word in result["words"]] == ["be./re.Shit", "ba.Ra'"]
  assert result["words"][0]["gloss"] == "first: beginning"
  assert result["words"][1]["gloss"] is None  # H1254A is not in the test lexicon


def test_greek_words_are_marked_greek(loaded):
  result = client.get("/original-words", params={"book": JOHN, "chapter": 3, "verse": 16}).json()

  assert result["language"] == "greek"
  assert result["words"][0]["strong_code"] == "G0025" and result["words"][0]["gloss"] == "to love"


def test_a_verse_without_words_is_not_found(loaded):
  response = client.get("/original-words", params={"book": GENESIS, "chapter": 1, "verse": 2})

  assert response.status_code == 404


def test_a_lexicon_entry_lists_the_verses_that_use_the_word(loaded):
  result = client.get("/lexicon", params={"translation": "BSB", "strong_code": "g0025"}).json()

  assert result["strong_code"] == "G0025" and result["gloss"] == "to love"
  assert result["verse_total"] == 2 and result["shown"] == 2
  assert result["verses"][0]["reference"] == "John 3:16"
  assert result["verses"][0]["text"].startswith("For God so loved the world")


def test_lexicon_refusals(loaded):
  assert client.get("/lexicon", params={"translation": "NIV", "strong_code": "G0025"}).status_code == 422
  assert client.get("/lexicon", params={"translation": "BSB", "strong_code": "banana"}).status_code == 422
  assert client.get("/lexicon", params={"translation": "BSB", "strong_code": "G9999"}).status_code == 404
  assert client.get("/lexicon", params={"translation": "NOPE", "strong_code": "G0025"}).status_code == 404


def test_the_lexicon_verse_list_is_capped_but_the_total_is_not(loaded):
  entry = original_words.get_lexicon_entry("BSB", "G0025", 1)

  assert entry["verse_total"] == 2 and entry["shown"] == 1
  assert entry["verses"][0]["reference"] == "John 3:16"


# --- searching by Strong's number ----------------------------------------------------------------


@pytest.mark.parametrize(
  "query, expected_code, expected_codes",
  [
    ("G0025", "G0025", ["G0025", *("G0025" + letter for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ")]),
    (" g25 ", "G0025", None),
    ("H 7225g", "H7225G", ["H7225G"]),
    ("h0430", "H0430", None),
  ],
)
def test_a_strongs_number_is_recognised_however_it_is_typed(query, expected_code, expected_codes):
  strong = parse_strong_query(query)

  assert strong["code"] == expected_code
  if expected_codes:
    assert strong["codes"] == expected_codes


@pytest.mark.parametrize("query", ["love", "G", "G12345", "G25 love", "Genesis", "1 John", "H7225GG", '"G0025"'])
def test_other_queries_are_not_strongs_numbers(query):
  assert parse_strong_query(query) is None


def search_for(query, **extra):
  return client.get("/search", params={"query": query, "translations": "BSB", **extra})


def test_searching_a_number_finds_the_verses_with_that_word(loaded):
  body = search_for("G0025").json()

  assert body["total"] == 2 and body["terms"] == []
  assert [result["reference"] for result in body["results"]] == ["John 3:16", "John 3:17"]
  assert body["strong"] == {
    "code": "G0025", "language": "greek", "original": "ἀγαπάω",
    "transliteration": "agapaō", "gloss": "to love",
  }
  assert body["book_counts"] == [{"book_number": JOHN, "count": 2}]


def test_a_number_without_a_letter_also_finds_its_senses_and_a_letter_narrows_it(loaded):
  assert search_for("H7225").json()["total"] == 1
  assert search_for("H7225G").json()["total"] == 1
  assert search_for("H7225H").status_code == 422  # no such sense in the lexicon


def test_the_usual_search_options_still_apply(loaded):
  assert search_for("G0025", book=JOHN, per_page=1, page=2).json()["results"][0]["reference"] == "John 3:17"
  assert search_for("G0025", book_start=1, book_end=39).json()["total"] == 0
  newest_first = search_for("G0025", sort_direction="desc").json()["results"]
  assert newest_first[0]["reference"] == "John 3:17"


def test_a_number_not_in_the_lexicon_is_refused_clearly(loaded):
  response = search_for("G9999")

  assert response.status_code == 422 and "G9999" in response.json()["detail"]


def test_the_licensed_bibles_cannot_be_searched_by_number(loaded):
  response = client.get("/search", params={"query": "G0025", "translations": "NIV"})

  assert response.status_code == 422 and "Strong" in response.json()["detail"]


def test_the_entry_chosen_for_a_bare_number_prefers_the_main_sense(loaded):
  with connect() as connection:
    entry = find_strong_entry(connection, parse_strong_query("H7225"))

  assert entry["code"] == "H7225G"

"""Tests for finding scripture references in commentary text."""

import pytest

import scripture_references
from collections import defaultdict

from scripture_references import BOOK_BY_NORMALIZED_NAME, NAMES, find_references, normalize, verse_limits

LIMITS = {
  (43, 3): 36, (43, 1): 51, (11, 4): 34, (19, 23): 6, (62, 4): 21, (9, 1): 28, (22, 2): 17, (40, 5): 48,
  (1, 1): 31, (65, 1): 25, (57, 1): 25, (2, 3): 22,
  (23, 53): 12, (23, 9): 21, (23, 1): 31, (23, 40): 31, (23, 42): 25, (9, 3): 21, (9, 2): 36, (10, 7): 29, (46, 13): 13, (50, 3): 21, (5, 31): 30,
}


def found(text):
  return [(text[start:end], code) for start, end, code in find_references(text, LIMITS)]


def test_every_one_of_the_66_books_can_be_named():
  assert sorted(set(BOOK_BY_NORMALIZED_NAME.values())) == list(range(1, 67))


def test_the_short_codes_of_henry_clarke_and_jfb_are_found():
  assert found("as in Joh 3:22 and Kg1 4:32, see Psa 23:1") == [
    ("Joh 3:22", "43:3:22"), ("Kg1 4:32", "11:4:32"), ("Psa 23:1", "19:23:1"),
  ]


def test_the_full_names_of_gill_and_calvin_are_found():
  assert found("(1 Kings 4:32) and (Psalm 23:1) in John 3:16") == [
    ("1 Kings 4:32", "11:4:32"), ("Psalm 23:1", "19:23:1"), ("John 3:16", "43:3:16"),
  ]


def test_other_ways_of_writing_a_numbered_book():
  assert [code for _text, code in found("1John 4:9, I John 4:9, 1Jo 4:9, Jo1 4:9, 1 Sam. 1:1, 1Sa. 1:1, I Samuel 1:1")] == [
    "62:4:9", "62:4:9", "62:4:9", "62:4:9", "9:1:1", "9:1:1", "9:1:1",
  ]


def test_a_range_is_one_link_to_its_first_verse():
  assert found("see Mat 5:3-12 and Mat 5:3–12.") == [("Mat 5:3-12", "40:5:3"), ("Mat 5:3–12", "40:5:3")]


def test_a_full_stop_after_the_book_is_allowed_and_part_of_the_link():
  assert found("Gen. 1:1; Ex. 3:2; Jde 1:3; Plm 1:2") == [
    ("Gen. 1:1", "1:1:1"), ("Ex. 3:2", "2:3:2"), ("Jde 1:3", "65:1:3"), ("Plm 1:2", "57:1:2"),
  ]


def test_the_longest_name_wins():
  assert found("Song of Solomon 2:1 and Sol 2:1") == [("Song of Solomon 2:1", "22:2:1"), ("Sol 2:1", "22:2:1")]


def test_a_verse_that_does_not_exist_is_not_linked():
  assert found("Joh 3:99 and Joh 9:1 and Joh 3:0") == []


def test_things_that_are_not_references_are_left_alone():
  assert found("Chapter 3:4 and Johnson 3:16 and 2 Macc. 3:4 and Wisdom 3:4 and John 3 and verse 3:16") == []


def test_a_name_inside_a_longer_word_is_not_a_book():
  assert found("Dan 3:16 versus Jordan 3:16 and Jobs 3:16") == []


def test_references_are_found_with_their_positions():
  text = "See (Joh 3:16) now."

  assert find_references(text, LIMITS) == [[5, 13, "43:3:16"]]
  assert text[5:13] == "Joh 3:16"


def test_a_chapter_and_verse_after_a_range_is_not_swallowed():
  # "Joh 3:16-4:2" runs over a chapter: the link covers the first verse only, not "4".
  assert found("Joh 3:16-4:2") == [("Joh 3:16", "43:3:16")]


def test_the_real_chapter_lengths_are_known_for_every_chapter():
  limits = verse_limits()

  assert len(limits) == 1189
  assert limits[(43, 3)] == 36 and limits[(19, 119)] == 176 and limits[(1, 1)] == 31


def test_the_limits_are_kept_between_calls(monkeypatch):
  verse_limits()

  def fail():
    raise AssertionError("the database was asked again")

  monkeypatch.setattr(scripture_references, "connect", fail)
  assert verse_limits()[(43, 3)] == 36


def test_isaiah_is_not_taken_for_first_samuel():
  # "Isa" is Isaiah; "I Sa" and "1Sa" are 1 Samuel. They once clashed, which linked Isaiah to 1 Samuel.
  assert found("Isa 53:5, Isa. 9:6, ISA. 42:10, Isa 1:1, Isaiah 40:1") == [
    ("Isa 53:5", "23:53:5"), ("Isa. 9:6", "23:9:6"), ("ISA. 42:10", "23:42:10"), ("Isa 1:1", "23:1:1"),
    ("Isaiah 40:1", "23:40:1"),
  ]
  assert found("I Sa 3:4, 1Sa 2:2, 1 Sa 3:4, II Sa 7:1") == [
    ("I Sa 3:4", "9:3:4"), ("1Sa 2:2", "9:2:2"), ("1 Sa 3:4", "9:3:4"), ("II Sa 7:1", "10:7:1"),
  ]


def test_no_two_books_share_a_name():
  owners = defaultdict(set)
  for name, book in NAMES.items():
    owners[normalize(name)].add(book)
  clashes = {key: books for key, books in owners.items() if len(books) > 1}

  # A clash is allowed only where the plain name wins, and then it must be the plain name's book.
  for key, books in clashes.items():
    assert BOOK_BY_NORMALIZED_NAME[key] in books
  assert BOOK_BY_NORMALIZED_NAME["isa"] == 23 and BOOK_BY_NORMALIZED_NAME["i sa"] == 9


def test_capital_letters_are_accepted_as_daily_light_writes_them():
  assert found("Father, I will.—PHI. 3:13,14. and the Lord.—DEUT. 31:8.") == [
    ("PHI. 3:13", "50:3:13"), ("DEUT. 31:8", "5:31:8"),
  ]


def test_a_lower_case_name_is_not_a_book():
  assert found("a job 3:4 and a phi 3:4 and deut 31:8") == []

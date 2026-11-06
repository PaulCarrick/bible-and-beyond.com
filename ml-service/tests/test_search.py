"""Search tests. The HTTP tests read the imported Bible text from the local database
(docker compose up -d, then import BSB and KJV)."""

from fastapi.testclient import TestClient

from main import app
from search import build_pattern, parse_terms

client = TestClient(app)


def test_parse_terms_all_words():
  assert parse_terms("Jesus  love", "all") == ["Jesus", "love"]


def test_parse_terms_keeps_quoted_phrase_together():
  assert parse_terms('"Jesus wept" love', "any") == ["Jesus wept", "love"]


def test_parse_terms_phrase_mode_treats_whole_query_as_one_phrase():
  assert parse_terms('Jesus   wept', "phrase") == ["Jesus wept"]


def test_parse_terms_ignores_stray_quotes():
  assert parse_terms('" "', "all") == []


def test_build_pattern_escapes_special_characters_and_adds_word_boundaries():
  assert build_pattern("a.b", False) == r"a\.b"
  assert build_pattern("love", True) == r"\ylove\y"


def test_search_finds_phrase():
  response = client.get(
    "/search", params={"query": "Jesus wept", "match_mode": "phrase", "translations": "KJV"}
  )

  assert response.status_code == 200
  body = response.json()
  assert body["total"] == 1
  first = body["results"][0]
  assert (first["book_name"], first["chapter"], first["verse"]) == ("John", 11, 35)


def test_search_book_counts_add_up_to_total():
  body = client.get("/search", params={"query": "love"}).json()

  assert body["total"] > 100
  assert sum(entry["count"] for entry in body["book_counts"]) == body["total"]


def test_whole_words_excludes_longer_words():
  partial = client.get("/search", params={"query": "love"}).json()["total"]
  whole = client.get("/search", params={"query": "love", "whole_words": "true"}).json()["total"]

  assert whole < partial


def test_match_any_returns_at_least_as_many_as_match_all():
  match_all = client.get("/search", params={"query": "faith hope love"}).json()["total"]
  match_any = client.get(
    "/search", params={"query": "faith hope love", "match_mode": "any"}
  ).json()["total"]

  assert match_any > match_all


def test_book_range_limits_results():
  body = client.get("/search", params={"query": "love", "book_start": 40, "book_end": 66}).json()

  assert body["total"] > 0
  assert all(result["book_number"] >= 40 for result in body["results"])


def test_book_filter_narrows_results_but_keeps_book_counts():
  everything = client.get("/search", params={"query": "love"}).json()
  psalms = client.get("/search", params={"query": "love", "book": 19}).json()

  assert psalms["book_counts"] == everything["book_counts"]
  assert 0 < psalms["total"] < everything["total"]
  assert {result["book_number"] for result in psalms["results"]} == {19}


def test_pagination_returns_different_pages():
  first = client.get("/search", params={"query": "love", "per_page": 5, "page": 1}).json()
  second = client.get("/search", params={"query": "love", "per_page": 5, "page": 2}).json()

  assert len(first["results"]) == 5
  assert first["results"] != second["results"]
  assert first["total"] == second["total"]


def test_searching_multiple_translations_returns_each_translation():
  body = client.get(
    "/search",
    params={"query": "Jesus wept", "match_mode": "phrase", "translations": ["KJV", "BSB"]},
  ).json()

  assert {result["translation"] for result in body["results"]} == {"KJV", "BSB"}


def test_unknown_translation_is_rejected():
  response = client.get("/search", params={"query": "love", "translations": "NOPE"})

  assert response.status_code == 422


def test_blank_query_is_rejected():
  assert client.get("/search", params={"query": ""}).status_code == 422
  assert client.get("/search", params={"query": '" "'}).status_code == 422


def test_reversed_book_range_is_rejected():
  response = client.get("/search", params={"query": "love", "book_start": 50, "book_end": 10})

  assert response.status_code == 422


def test_translations_and_books_lists():
  codes = {entry["code"] for entry in client.get("/translations").json()}
  books = client.get("/books").json()

  assert {"BSB", "KJV"} <= codes
  assert len(books) == 66
  assert books[0]["name"] == "Genesis"


def test_sorting_by_verse_can_be_reversed_across_all_results():
  ascending = client.get(
    "/search", params={"query": "love", "per_page": 3, "sort_by": "verse", "sort_direction": "asc"}
  ).json()
  descending = client.get(
    "/search", params={"query": "love", "per_page": 3, "sort_by": "verse", "sort_direction": "desc"}
  ).json()

  assert ascending["results"][0]["book_name"] == "Genesis"
  assert descending["results"][0]["book_name"] == "Revelation"
  assert ascending["total"] == descending["total"]


def test_sorting_by_text_orders_alphabetically_ignoring_leading_quotes():
  body = client.get(
    "/search", params={"query": "love", "per_page": 50, "sort_by": "text", "sort_direction": "asc"}
  ).json()
  texts = [result["text"].lstrip("“”‘’\"' ").lower() for result in body["results"]]

  assert texts == sorted(texts)


def test_sorting_by_text_descending_reverses_the_order():
  ascending = client.get(
    "/search", params={"query": "love", "sort_by": "text", "sort_direction": "asc"}
  ).json()
  descending = client.get(
    "/search", params={"query": "love", "sort_by": "text", "sort_direction": "desc"}
  ).json()

  assert ascending["results"][0]["text"] != descending["results"][0]["text"]


def test_unknown_sort_field_is_rejected():
  assert client.get("/search", params={"query": "love", "sort_by": "bogus"}).status_code == 422

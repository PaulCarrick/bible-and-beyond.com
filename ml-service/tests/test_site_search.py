"""The search on the welcome page: one call that runs the existing searches and returns their hits in groups.

The searches themselves are tested in their own files; here they are faked, so these tests need no data.
"""

import pytest
from fastapi.testclient import TestClient

import site_search
from main import app

client = TestClient(app)


@pytest.fixture
def fake_searches(monkeypatch):
  calls = []

  def verses(query, match_mode, whole_words, codes, book_start, book_end, book, page, per_page):
    calls.append(("bible", match_mode, whole_words, codes, page, per_page))
    return {"total": 2, "terms": ["grace"], "results": [{"reference": "John 1:14"}]}

  def commentaries(query, match_mode, commentary, book_start, book_end, book, page, per_page, sort_by, direction):
    calls.append(("commentary", match_mode, page, per_page))
    return {"total": 0, "results": []}

  def library(query, match_mode, collection, item, page, per_page, sort_by):
    calls.append((collection, match_mode, page, per_page))
    return {"total": 3 if collection == "books" else 1, "results": [{"book": collection}]}

  monkeypatch.setattr(site_search, "search_verses", verses)
  monkeypatch.setattr(site_search, "search_commentaries", commentaries)
  monkeypatch.setattr(site_search, "search_library", library)
  monkeypatch.setattr(site_search, "choose_bible", lambda: "BSB")
  return calls


def test_every_kind_is_searched_and_empty_groups_are_left_out(fake_searches):
  body = client.get("/search-everything", params={"query": "grace", "match_mode": "phrase"}).json()

  assert [(group["kind"], group["total"]) for group in body["groups"]] == [("bible", 2), ("devotional", 1), ("book", 3)]
  assert body["groups"][0]["translation"] == "BSB" and body["groups"][0]["terms"] == ["grace"]
  # The Bible is one Bible, searched for whole words; five of each by default.
  assert fake_searches[0] == ("bible", "phrase", True, ["BSB"], 1, 5)
  assert ("devotionals", "phrase", 1, 5) in fake_searches and ("books", "phrase", 1, 5) in fake_searches


def test_show_more_asks_for_one_group_only(fake_searches):
  body = client.get("/search-everything", params={"query": "grace", "kind": "book", "page": 2}).json()

  assert [group["kind"] for group in body["groups"]] == ["book"] and body["groups"][0]["page"] == 2
  assert fake_searches == [("books", "all", 2, 5)]


def test_a_query_that_cannot_be_searched_is_refused(fake_searches):
  assert client.get("/search-everything", params={"query": "   "}).status_code == 422
  assert client.get("/search-everything", params={"query": "grace", "kind": "song"}).status_code == 422
  assert client.get("/search-everything", params={"query": "grace", "per_page": 26}).status_code == 422

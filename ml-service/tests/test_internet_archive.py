"""Tests for the Internet Archive search (internet_archive.py). The Archive is faked: no request leaves the machine."""

import pytest
from fastapi.testclient import TestClient

import internet_archive
from internet_archive import ArchiveProblem, access_of, search_archive, snippet
from main import app

client = TestClient(app)

LENDING_HIT = {
  "_id": "bookofpoorinspir0000taul|9ff4",
  "highlight": {"text": ["truly {{{poor in spirit}}} unless God\nmakes him", "second", "third"]},
  "fields": {
    "meta_title": ["The book of the poor in spirit"], "meta_creator": ["Tauler, Johannes"], "meta_year": [1954],
    "meta_collection": ["internetarchivebooks", "printdisabled", "inlibrary"],
  },
}
FREE_HIT = {
  "_id": "beatitudesorsome00mcca|7e46",
  "highlight": {"text": ["Blessed are the {{{poor in spirit}}}"]},
  "fields": {"meta_title": ["The Beatitudes"], "meta_date": ["1913-01-01T00:00:00Z"], "meta_collection": ["americana"]},
}


class FakeResponse:
  def __init__(self, body):
    self.body = body

  def raise_for_status(self):
    pass

  def json(self):
    return self.body


@pytest.fixture(autouse=True)
def fake_archive(monkeypatch):
  internet_archive.clear_cache()
  sent = []

  class FakeSession:
    def post(self, address, json, timeout):
      sent.append(json)
      return FakeResponse({"hits": {"total": 2, "hits": [LENDING_HIT, FREE_HIT]}})

  monkeypatch.setattr(internet_archive, "_session", lambda: FakeSession())
  yield sent
  internet_archive.clear_cache()


def test_how_an_item_is_read():
  assert access_of(["printdisabled", "inlibrary"]) == "borrow"
  assert access_of(["printdisabled"]) == "print_disabled"
  assert access_of(["americana"]) == "free"


def test_snippets_are_marked_like_the_sites_excerpts():
  assert snippet("the {{{poor in\nspirit}}} go") == "the \u0001poor in spirit\u0002 go"
  long = snippet("word " * 100 + "{{{late}}}")
  assert long.endswith(" …") and "\u0001" not in long and len(long) < 310


def test_books_are_found_inside_their_text(fake_archive):
  found = search_archive('  "poor in   spirit" ', "texts", 2, 10)
  assert fake_archive == [{"q": '"poor in spirit"', "size": 10, "from": 10, "scroll": False}]
  assert found["total"] == 2 and found["last_page"] == 1
  first, second = found["results"]
  assert first["access"] == "borrow" and first["year"] == 1954 and first["creator"] == "Tauler, Johannes"
  assert first["snippets"] == ["truly \u0001poor in spirit\u0002 unless God makes him", "second"]
  assert first["url"] == "https://archive.org/details/bookofpoorinspir0000taul?q=%22poor%20in%20spirit%22"
  assert second["access"] == "free" and second["year"] == 1913 and second["creator"] == ""

  # The same page again comes from memory.
  search_archive('"poor in spirit"', "texts", 2, 10)
  assert len(fake_archive) == 1


def test_a_failing_archive_or_a_bad_query_gives_a_message(monkeypatch):
  with pytest.raises(ArchiveProblem, match="under 300"):
    search_archive("x" * 301)
  with pytest.raises(ArchiveProblem, match="Enter the words"):
    search_archive("   ")

  def broken(*arguments):
    raise ConnectionError("no route")

  monkeypatch.setattr(internet_archive, "_search_books", broken)
  with pytest.raises(ArchiveProblem, match="did not answer") as problem:
    search_archive("grace")
  assert problem.value.status_code == 503


def test_recordings_come_from_the_catalogue(monkeypatch):
  rows = [{"identifier": "amazing-grace-1", "title": "Amazing Grace", "creator": ["A", "B"], "year": "1930", "collection": "oldtimeradio"}]

  class FakeSearch(list):
    num_found = 1

  asked = []

  def fake_search_items(query, **options):
    asked.append((query, options["params"]))
    return FakeSearch(rows)

  import internetarchive
  monkeypatch.setattr(internetarchive, "search_items", fake_search_items)
  found = search_archive("amazing grace", "audio", 1, 5)
  assert asked == [("(amazing grace) AND mediatype:(audio) AND -collection:(podcasts_mirror)", {"rows": 5, "page": 1})]
  assert found["results"] == [{
    "identifier": "amazing-grace-1", "title": "Amazing Grace", "creator": "A, B", "year": 1930, "access": "free",
    "snippets": [], "url": "https://archive.org/details/amazing-grace-1",
  }]


def test_anyone_can_search_the_archive_without_logging_in():
  client.cookies.clear()
  response = client.get("/search-internet-archive", params={"query": "poor in spirit"})
  assert response.status_code == 200
  assert response.json()["source"] == "internet_archive"
  assert client.get("/search-internet-archive", params={"query": "x", "kind": "video"}).status_code == 422

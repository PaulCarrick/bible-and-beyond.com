"""API.Bible tests. The network is faked, so these never use the monthly request allowance."""

import pytest
from fastapi.testclient import TestClient

import api_bible
from main import app

client = TestClient(app)

FAKE_METADATA = {
  "data": {
    "name": "New International Version 2011",
    "abbreviation": "NIV11",
    "copyright": "The Holy Bible, New International Version. Used by Permission of Biblica, Inc.",
    "info": '<h3>About Biblica</h3> <p><a href="https://www.biblica.com">Biblica</a></p>',
  }
}

FAKE_SEARCH = {
  "data": {
    "total": 750,
    "verses": [
      {
        "id": "GEN.4.1",
        "bookId": "GEN",
        "chapterId": "GEN.4",
        "reference": "Gen. 4:1",
        "text": "  Adam made love to his wife Eve.  ",
      },
      {
        "id": "SNG.7.9-SNG.7.12",
        "bookId": "SNG",
        "chapterId": "SNG.7",
        "reference": "Song of Songs 7:9b-12",
        "text": "Yes, and yours are, too.",
      },
    ],
  },
  "meta": {"fumsToken": "token-123"},
}


@pytest.fixture(autouse=True)
def usage_file(monkeypatch, tmp_path):
  """Keep the request counter away from the real one."""
  path = tmp_path / "api_bible_usage.json"
  monkeypatch.setenv("API_BIBLE_USAGE_FILE", str(path))
  api_bible._cache.clear()
  return path


@pytest.fixture
def calls(monkeypatch):
  recorded = []

  def fake_request_json(path, parameters, cache_seconds):
    recorded.append((path, parameters))
    return FAKE_SEARCH if path.endswith("/search") else FAKE_METADATA

  monkeypatch.setattr(api_bible, "request_json", fake_request_json)
  return recorded


def search_parameters_sent(calls):
  return next(parameters for path, parameters in calls if path.endswith("/search"))


def test_search_maps_results_and_pages_with_an_offset(calls):
  response = client.get(
    "/search", params={"query": "love", "translations": "NIV", "page": 3, "per_page": 10}
  )

  assert response.status_code == 200
  body = response.json()
  assert body["source"] == "api_bible"
  assert body["total"] == 750
  assert body["fums_token"] == "token-123"
  assert body["book_counts"] == []
  assert body["copyright"].startswith("The Holy Bible, New International Version")
  assert body["results"][0] == {
    "translation": "NIV",
    "book_number": 1,
    "book_name": "Genesis",
    "chapter": 4,
    "verse": 1,
    "reference": "Genesis 4:1",
    "text": "Adam made love to his wife Eve.",
  }
  # A passage such as 7:9b-12 keeps its range, with the full book name.
  assert body["results"][1]["reference"] == "Song of Solomon 7:9b-12"

  sent = search_parameters_sent(calls)
  assert sent["offset"] == 20
  assert sent["limit"] == 10
  assert sent["fuzziness"] == 0
  assert sent["fums-version"] == 3
  assert sent["sort"] == "canonical"
  assert "range" not in sent


def test_descending_verse_sort_uses_reverse_canonical_order(calls):
  client.get(
    "/search",
    params={"query": "love", "translations": "NASB", "sort_by": "verse", "sort_direction": "desc"},
  )

  assert search_parameters_sent(calls)["sort"] == "reverse-canonical"


def test_book_range_becomes_a_passage_range(calls):
  client.get(
    "/search", params={"query": "love", "translations": "MSG", "book_start": 40, "book_end": 66}
  )

  assert search_parameters_sent(calls)["range"] == "MAT.1.1-REV.22.21"


@pytest.mark.parametrize(
  "extra_parameters",
  [
    {"match_mode": "any"},
    {"match_mode": "phrase"},
    {"whole_words": "true"},
    {"sort_by": "text"},
    {"book": 1},
  ],
)
def test_options_api_bible_cannot_honor_are_rejected(calls, extra_parameters):
  response = client.get(
    "/search", params={"query": "love", "translations": "NIV", **extra_parameters}
  )

  assert response.status_code == 422
  assert calls == []


def test_api_bible_cannot_be_combined_with_other_bibles(calls):
  response = client.get("/search", params={"query": "love", "translations": ["NIV", "KJV"]})

  assert response.status_code == 422
  assert calls == []


def test_missing_key_gives_a_clear_error(monkeypatch):
  monkeypatch.delenv("API_BIBLE_KEY", raising=False)

  response = client.get("/search", params={"query": "love", "translations": "NIV"})

  assert response.status_code == 503
  assert "API_BIBLE_KEY" in response.json()["detail"]


def test_copyrights_include_rights_holder_links(calls):
  body = client.get("/copyrights").json()

  assert [entry["code"] for entry in body] == ["NIV", "NASB", "MSG"]
  assert body[0]["copyright"].startswith("The Holy Bible")
  assert body[0]["rights_holder_url"] == "https://www.biblica.com"


def test_translations_list_marks_where_each_bible_comes_from():
  body = client.get("/translations").json()
  sources = {entry["code"]: entry["source"] for entry in body}

  assert sources["KJV"] == "local"
  assert sources["NIV"] == sources["NASB"] == sources["MSG"] == "api_bible"


class FakeResponse:
  def __init__(self, status_code, body=None):
    self.status_code = status_code
    self._body = body or {}

  def json(self):
    return self._body


def test_repeated_requests_are_cached(monkeypatch):
  monkeypatch.setenv("API_BIBLE_KEY", "test-key")
  api_bible._cache.clear()
  sent = []

  def fake_get(url, headers, params, timeout):
    sent.append((url, headers["api-key"]))
    return FakeResponse(200, {"data": {}})

  monkeypatch.setattr(api_bible.httpx, "get", fake_get)

  api_bible.request_json("/bibles/x", {"query": "love"}, cache_seconds=60)
  api_bible.request_json("/bibles/x", {"query": "love"}, cache_seconds=60)

  assert len(sent) == 1
  assert sent[0][1] == "test-key"
  api_bible._cache.clear()


def test_usage_limit_is_reported_clearly(monkeypatch):
  monkeypatch.setenv("API_BIBLE_KEY", "test-key")
  api_bible._cache.clear()
  monkeypatch.setattr(api_bible.httpx, "get", lambda *args, **kwargs: FakeResponse(429))

  with pytest.raises(api_bible.ApiBibleError, match="usage limit"):
    api_bible.request_json("/bibles/x", {}, cache_seconds=60)


def test_only_real_requests_count_and_the_monthly_limit_is_enforced(monkeypatch):
  monkeypatch.setenv("API_BIBLE_KEY", "test-key")
  monkeypatch.setenv("API_BIBLE_MONTHLY_LIMIT", "2")
  sent = []

  def fake_get(url, headers, params, timeout):
    sent.append(url)
    return FakeResponse(200, {"data": {}})

  monkeypatch.setattr(api_bible.httpx, "get", fake_get)

  api_bible.request_json("/bibles/x", {"query": "one"}, cache_seconds=60)
  api_bible.request_json("/bibles/x", {"query": "one"}, cache_seconds=60)  # cached, not counted
  api_bible.request_json("/bibles/x", {"query": "two"}, cache_seconds=60)
  assert api_bible.requests_used_this_month() == 2

  with pytest.raises(api_bible.ApiBibleError, match="usage limit"):
    api_bible.request_json("/bibles/x", {"query": "three"}, cache_seconds=60)
  assert len(sent) == 2


def test_reaching_the_limit_gives_a_friendly_error_from_the_api(monkeypatch):
  monkeypatch.setenv("API_BIBLE_KEY", "test-key")
  monkeypatch.setenv("API_BIBLE_MONTHLY_LIMIT", "0")

  response = client.get("/search", params={"query": "love", "translations": "NIV"})

  assert response.status_code == 503
  assert "available again next month" in response.json()["detail"]


def test_the_count_starts_over_each_month(usage_file):
  usage_file.write_text('{"month": "2000-01", "requests": 4499}')

  assert api_bible.requests_used_this_month() == 0

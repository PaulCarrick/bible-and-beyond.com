"""Search and display for the copyrighted Bibles served by API.Bible (NIV, NASB, The Message).

These texts are never stored in our database. They are fetched when needed and kept in memory
for a short time. API.Bible's terms require a copyright notice with the text, usage reporting
(FUMS), and non-commercial use on the free plan.
"""

import os
import re
import time

import httpx

import search
from search import connect, parse_terms

API_BIBLES = {
  "NIV": {"id": "78a9f6124f344018-01", "name": "New International Version (2011)"},
  "NASB": {"id": "a761ca71e0b3ddcf-01", "name": "New American Standard Bible (2020)"},
  "MSG": {"id": "6f11a7de016f942e-01", "name": "The Message"},
}

SEARCH_CACHE_SECONDS = 10 * 60
METADATA_CACHE_SECONDS = 24 * 60 * 60
MAXIMUM_CACHE_ENTRIES = 500

_cache: dict = {}


class ApiBibleError(Exception):
  """API.Bible could not be reached, is not configured, or refused the request."""


def request_json(path: str, parameters: dict, cache_seconds: int) -> dict:
  api_key = os.environ.get("API_BIBLE_KEY")
  if not api_key:
    raise ApiBibleError("API.Bible is not configured. Add API_BIBLE_KEY to ml-service/.env.")
  endpoint = os.environ.get("API_BIBLE_ENDPOINT", "https://rest.api.bible").rstrip("/")

  cache_key = (path, tuple(sorted(parameters.items())))
  cached = _cache.get(cache_key)
  if cached is not None and time.monotonic() - cached[0] < cache_seconds:
    return cached[1]

  try:
    response = httpx.get(
      f"{endpoint}{path}", headers={"api-key": api_key}, params=parameters, timeout=30
    )
  except httpx.HTTPError as error:
    raise ApiBibleError("Could not reach API.Bible.") from error
  if response.status_code == 429:
    raise ApiBibleError("The API.Bible usage limit has been reached. Try again later.")
  if response.status_code != 200:
    raise ApiBibleError(f"API.Bible returned status {response.status_code}.")

  body = response.json()
  if len(_cache) >= MAXIMUM_CACHE_ENTRIES:
    _cache.clear()
  _cache[cache_key] = (time.monotonic(), body)
  return body


def _books_by_code() -> dict:
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute("SELECT code, number, name FROM books")
      return {code: {"number": number, "name": name} for code, number, name in cursor.fetchall()}


def _passage_range(book_start: int, book_end: int) -> str | None:
  """API.Bible limits a search with a range such as MAT.1.1-REV.22.21."""
  if book_start == search.FIRST_BOOK_NUMBER and book_end == search.LAST_BOOK_NUMBER:
    return None
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute("SELECT code FROM books WHERE number = %s", (book_start,))
      first_code = cursor.fetchone()[0]
      cursor.execute("SELECT code FROM books WHERE number = %s", (book_end,))
      last_code = cursor.fetchone()[0]
      cursor.execute(
        "SELECT v.chapter, v.verse FROM verses v JOIN translations t ON t.id = v.translation_id "
        "WHERE t.code = 'BSB' AND v.book_number = %s ORDER BY v.chapter DESC, v.verse DESC LIMIT 1",
        (book_end,),
      )
      last_chapter, last_verse = cursor.fetchone()
  return f"{first_code}.1.1-{last_code}.{last_chapter}.{last_verse}"


def _map_verse(verse: dict, code: str, books_by_code: dict) -> dict:
  book = books_by_code.get(verse["bookId"])
  book_name = book["name"] if book else verse["reference"]
  chapter = int(verse["chapterId"].split(".")[1])
  verse_match = re.match(r"^[A-Za-z0-9]+\.\d+\.(\d+)", verse["id"])
  verse_number = int(verse_match.group(1)) if verse_match else 0

  # Passages such as 7:9b-12 keep the part of API.Bible's own reference after the book name.
  if "-" in verse["id"]:
    passage = re.search(rf"{chapter}:.*$", verse["reference"])
    reference = f"{book_name} {passage.group(0)}" if passage else verse["reference"]
  else:
    reference = f"{book_name} {chapter}:{verse_number}"

  return {
    "translation": code,
    "book_number": book["number"] if book else 0,
    "book_name": book_name,
    "chapter": chapter,
    "verse": verse_number,
    "reference": reference,
    "text": verse["text"].strip(),
  }


def search_api_bible(
  code: str,
  query: str,
  match_mode: str,
  whole_words: bool,
  book_start: int,
  book_end: int,
  book: int | None,
  page: int,
  per_page: int,
  sort_by: str,
  sort_direction: str,
) -> dict:
  if match_mode != "all" or whole_words or book is not None or sort_by == "text":
    raise ValueError(
      f"{code} searches only match all of the words, in Bible order or reverse Bible order."
    )
  terms = parse_terms(query, "all")
  if not terms:
    raise ValueError("Enter at least one word or phrase to search for.")

  bible = API_BIBLES[code]
  parameters = {
    "query": " ".join(terms),
    "limit": per_page,
    "offset": (page - 1) * per_page,
    "sort": "reverse-canonical" if sort_direction == "desc" else "canonical",
    "fuzziness": 0,
    "fums-version": 3,
  }
  passage_range = _passage_range(book_start, book_end)
  if passage_range:
    parameters["range"] = passage_range

  body = request_json(f"/bibles/{bible['id']}/search", parameters, SEARCH_CACHE_SECONDS)
  data = body["data"]
  books_by_code = _books_by_code()

  return {
    "source": "api_bible",
    "query": query,
    "terms": terms,
    "total": data.get("total", 0),
    "page": page,
    "per_page": per_page,
    "book_counts": [],
    "results": [_map_verse(verse, code, books_by_code) for verse in data.get("verses", [])],
    "fums_token": body.get("meta", {}).get("fumsToken"),
    "copyright": get_copyright(code)["copyright"],
  }


def get_copyright(code: str) -> dict:
  bible = API_BIBLES[code]
  body = request_json(f"/bibles/{bible['id']}", {}, METADATA_CACHE_SECONDS)
  data = body["data"]
  link = re.search(r'href="(https?://[^"]+)"', data.get("info") or "")
  return {
    "code": code,
    "name": data["name"],
    "abbreviation": data["abbreviation"],
    "copyright": data["copyright"],
    "rights_holder_url": link.group(1) if link else None,
  }


def list_copyrights() -> list[dict]:
  return [get_copyright(code) for code in API_BIBLES]

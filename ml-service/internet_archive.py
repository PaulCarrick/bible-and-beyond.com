"""Search the Internet Archive (archive.org) from the site's search pages, with its Python package internetarchive.

Open to every visitor (no account needed). Books are found by the Archive's search inside their text (full-text
search), which covers its lending library of books still under copyright as well as public-domain ones; each result
has a few lines of the text around the words found. Recordings (the music search) are found by their catalogue
entries. Nothing is copied to this site: each result links to the item on archive.org, where a lending book is
borrowed for an hour by the visitor, signed in with their own free Archive account (the Archive ties every loan to
its reader, so a site cannot borrow for its visitors).

Whether a book is a lending book is read from its collections ("inlibrary"); the Archive's page says whether it can
be borrowed at once or has a waiting list (asking for every result's status would add seconds to each search).
Each answer is kept in memory for 10 minutes, so paging back costs no request.
"""

import logging
import re
import threading
import time
from urllib.parse import quote

ITEM_ADDRESS = "https://archive.org/details/"
# The Archive's own lending collection; "printdisabled" alone means only readers with print disabilities may borrow.
LENDING_COLLECTION = "inlibrary"
PRINT_DISABLED_COLLECTION = "printdisabled"
# Leave out mirrored podcasts, which crowd the recordings found for most words.
RECORDING_FILTER = "mediatype:(audio) AND -collection:(podcasts_mirror)"
QUERY_LIMIT = 300
MOST_SNIPPETS = 2
SNIPPET_CHARACTERS = 300
REQUEST_SECONDS = 15
KEEP_SECONDS = 10 * 60
KEEP_ANSWERS = 500
# The Archive's search cannot page far (it refuses deep pages).
LAST_PAGE = 40


class ArchiveProblem(Exception):
  """A search that cannot be made, or an Archive that does not answer; the message is shown to the visitor."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


_lock = threading.Lock()
_kept: dict[tuple, tuple[float, dict]] = {}


def _session():
  import internetarchive

  return internetarchive.get_session()


def access_of(collections: list[str]) -> str:
  """How a visitor reads an item: "borrow" (a lending book, an hour at a time, with an Archive account),
  "print_disabled" (only for readers with print disabilities) or "free" (open to anyone)."""
  if LENDING_COLLECTION in collections:
    return "borrow"
  if PRINT_DISABLED_COLLECTION in collections:
    return "print_disabled"
  return "free"


def snippet(text: str) -> str:
  """One of the Archive's highlights: the words found ({{{...}}}) marked with \\u0001 and \\u0002 like the site's own
  excerpts, the lines of the scan joined, and kept short."""
  text = " ".join(text.split())
  if len(text) > SNIPPET_CHARACTERS:
    cut = text.rfind(" ", 0, SNIPPET_CHARACTERS)
    text = text[: cut if cut > 0 else SNIPPET_CHARACTERS] + " …"
  marked = text.replace("{{{", "\u0001").replace("}}}", "\u0002")
  # A mark cut off at the end, or left from the start, is dropped.
  if marked.count("\u0001") != marked.count("\u0002"):
    marked = marked.replace("\u0001", "").replace("\u0002", "")
  return marked


def _first(fields: dict, name: str):
  value = fields.get(name)
  if isinstance(value, list):
    return value[0] if value else None
  return value


def _year(value) -> int | None:
  if isinstance(value, int):
    return value
  match = re.match(r"(\d{4})", str(value or ""))
  return int(match.group(1)) if match else None


def _book(hit: dict, query: str) -> dict:
  fields = hit.get("fields", {})
  identifier = hit["_id"].split("|")[0]
  collections = fields.get("meta_collection") or []
  return {
    "identifier": identifier,
    "title": _first(fields, "meta_title") or identifier,
    "creator": _first(fields, "meta_creator") or "",
    "year": _year(_first(fields, "meta_year") or _first(fields, "meta_date")),
    "access": access_of(collections),
    "snippets": [snippet(text) for text in (hit.get("highlight", {}).get("text") or [])[:MOST_SNIPPETS]],
    # Opens the book with the Archive's reader searching for the same words.
    "url": f"{ITEM_ADDRESS}{quote(identifier)}?q={quote(query)}",
  }


def _recording(row: dict) -> dict:
  identifier = row["identifier"]
  collections = row.get("collection") or []
  if isinstance(collections, str):
    collections = [collections]
  creator = row.get("creator") or ""
  return {
    "identifier": identifier,
    "title": row.get("title") or identifier,
    "creator": creator if isinstance(creator, str) else ", ".join(creator),
    "year": _year(row.get("year") or row.get("date")),
    "access": access_of(collections),
    "snippets": [],
    "url": f"{ITEM_ADDRESS}{quote(identifier)}",
  }


def _search_books(query: str, page: int, per_page: int) -> tuple[int, list[dict]]:
  import internetarchive

  address = internetarchive.search_items("", full_text_search=True).fts_url
  response = _session().post(
    address,
    json={"q": query, "size": per_page, "from": (page - 1) * per_page, "scroll": False},
    timeout=REQUEST_SECONDS,
  )
  response.raise_for_status()
  hits = response.json().get("hits", {})
  total = hits.get("total") or 0
  if isinstance(total, dict):
    total = total.get("value", 0)
  return total, [_book(hit, query) for hit in hits.get("hits", [])]


def _search_recordings(query: str, page: int, per_page: int) -> tuple[int, list[dict]]:
  import internetarchive

  found = internetarchive.search_items(
    f"({query}) AND {RECORDING_FILTER}",
    fields=["identifier", "title", "creator", "year", "date", "collection"],
    params={"rows": per_page, "page": page},
    archive_session=_session(),
    request_kwargs={"timeout": REQUEST_SECONDS},
    max_retries=1,
  )
  rows = []
  for row in found:
    rows.append(_recording(row))
    if len(rows) == per_page:
      break
  return found.num_found, rows


def search_archive(query: str, kind: str = "texts", page: int = 1, per_page: int = 10) -> dict:
  """One page of Internet Archive items: books found inside their text (kind "texts") or recordings ("audio")."""
  text = " ".join(query.split())
  if not text:
    raise ArchiveProblem("Enter the words to search for.")
  if len(text) > QUERY_LIMIT:
    raise ArchiveProblem(f"Please keep an Internet Archive search under {QUERY_LIMIT} characters.")
  if kind not in ("texts", "audio"):
    raise ArchiveProblem("Unknown kind of search.")
  page = min(page, LAST_PAGE)
  key = (kind, text.lower(), page, per_page)
  now = time.monotonic()
  with _lock:
    kept = _kept.get(key)
    if kept is not None and now - kept[0] < KEEP_SECONDS:
      return kept[1]

  try:
    if kind == "texts":
      total, results = _search_books(text, page, per_page)
    else:
      total, results = _search_recordings(text, page, per_page)
  except Exception as error:  # The package and the network raise many kinds of errors; all mean no answer.
    logging.getLogger("internet_archive").warning(
      "Internet Archive search (%s, %s characters) failed: %s: %s", kind, len(text), type(error).__name__, str(error)[:200],
    )
    raise ArchiveProblem("The Internet Archive did not answer just now. Please try again in a minute.", 503) from error

  answer = {
    "source": "internet_archive", "kind": kind, "query": text, "total": total, "page": page, "per_page": per_page,
    "last_page": min(LAST_PAGE, max(1, -(-total // per_page))), "results": results,
  }
  with _lock:
    if len(_kept) >= KEEP_ANSWERS:
      for old_key in sorted(_kept, key=lambda entry: _kept[entry][0])[: len(_kept) - KEEP_ANSWERS + 1]:
        del _kept[old_key]
    _kept[key] = (now, answer)
  return answer


def clear_cache() -> None:
  with _lock:
    _kept.clear()

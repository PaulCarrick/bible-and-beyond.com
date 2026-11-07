"""One search over everything on the site (the search form on the welcome page).

It runs the searches that already exist, a few results from each, and returns them in groups: the Bible
(one Bible, the BSB when it is published, so a verse appears once rather than once per translation), the
commentaries, the devotionals and the other books. In the Bible it matches whole words. A group with nothing found is left out. With kind, it
returns one group only, for "Show more" (the next page of that group).
"""

from commentaries import search_commentaries
from devotionals import search_library
from search import connect, search_verses

FIRST_BOOK = 1
LAST_BOOK = 66
KINDS = ("bible", "commentary", "devotional", "book")
PREFERRED_BIBLE = "BSB"


def choose_bible():
  """The Bible searched: the BSB when published, else the first published Bible stored here; None if none."""
  with connect() as connection:
    rows = connection.execute("SELECT code FROM translations WHERE is_published ORDER BY id").fetchall()
  codes = [code for (code,) in rows]
  if PREFERRED_BIBLE in codes:
    return PREFERRED_BIBLE
  return codes[0] if codes else None


def search_group(kind, query, match_mode, page, per_page):
  """One group: {kind, total, page, per_page, results, ...}. Raises ValueError for a query that cannot be searched."""
  if kind == "bible":
    bible = choose_bible()
    if bible is None:
      return {"kind": kind, "total": 0, "page": page, "per_page": per_page, "results": [], "terms": []}
    # Whole words, so "again" does not list every "against" (the Bible search page offers both).
    found = search_verses(query, match_mode, True, [bible], FIRST_BOOK, LAST_BOOK, None, page, per_page)
    return {
      "kind": kind, "translation": bible, "total": found["total"], "page": page, "per_page": per_page,
      "results": found["results"], "terms": found["terms"],
    }
  if kind == "commentary":
    found = search_commentaries(query, match_mode, None, FIRST_BOOK, LAST_BOOK, None, page, per_page, None, "asc")
  else:
    found = search_library(query, match_mode, "devotionals" if kind == "devotional" else "books", None, page, per_page, None)
  return {"kind": kind, "total": found["total"], "page": page, "per_page": per_page, "results": found["results"]}


def search_everything(query, match_mode="all", kind=None, page=1, per_page=5):
  """The groups found for a query, in the order of KINDS (or the one group asked for)."""
  if not query.strip():
    raise ValueError("Enter at least one word or phrase to search for.")
  if kind is not None:
    return {"query": query, "groups": [search_group(kind, query, match_mode, page, per_page)]}
  groups = [search_group(each, query, match_mode, page, per_page) for each in KINDS]
  return {"query": query, "groups": [group for group in groups if group["total"] > 0]}

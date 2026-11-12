"""One search over everything on the site (the search form on the welcome page).

It runs the searches that already exist, a few results from each, and returns them in groups: the Bible
(one Bible, the BSB when it is published, so a verse appears once rather than once per translation), the
commentaries, the devotionals, the other books and the Christian music. In the Bible it matches whole words. A group with nothing found is left out. With kind, it
returns one group only, for "Show more" (the next page of that group).

search_everything_with_ai is the same search by meaning, for an account allowed AI searches: Gemini suggests the
verses (ai_search.py, as on the Bible search page) and the rest are the passages nearest in meaning
(passage_embeddings.py).
"""

import logging

import passage_embeddings
from ai_search import find_verses
from commentaries import search_commentaries
from devotionals import search_library
from faq import FaqUnavailable
from music import search_music
from search import connect, search_verses

FIRST_BOOK = 1
LAST_BOOK = 66
KINDS = ("bible", "commentary", "devotional", "book", "music")
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
  if kind == "music":
    found = search_music(query, match_mode, page, per_page)
  elif kind == "commentary":
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


def search_group_with_ai(kind, user_id, query, page, per_page):
  """One group of the search by meaning. The Bible's verses come from Gemini; if it cannot answer, the Bible group
  is empty rather than the whole search failing."""
  if kind == "bible":
    bible = choose_bible()
    empty = {"kind": kind, "total": 0, "page": page, "per_page": per_page, "results": [], "terms": []}
    if bible is None:
      return empty
    try:
      references = find_verses(user_id, query)
    except FaqUnavailable:
      logging.getLogger("site_search").warning("The Bible part of an AI search was left out: Gemini did not answer.")
      return {**empty, "unavailable": True}
    # All of them (at most 30), put in Gemini's order, most relevant first, since only a few are shown at a time.
    found = search_verses(query, "all", False, [bible], FIRST_BOOK, LAST_BOOK, None, 1, 100, references=references)
    rank = {verse: number for number, verse in enumerate(references)}
    ordered = sorted(found["results"], key=lambda result: rank.get((result["book_number"], result["chapter"], result["verse"]), len(rank)))
    return {
      "kind": kind, "translation": bible, "total": found["total"], "page": page, "per_page": per_page,
      "results": ordered[(page - 1) * per_page: page * per_page], "terms": [],
    }
  vector = passage_embeddings.query_vector(user_id, query)
  if kind == "commentary":
    found = passage_embeddings.search_commentaries(vector, None, None, page, per_page)
  elif kind == "music":
    found = passage_embeddings.search_music(vector, page, per_page)
  else:
    found = passage_embeddings.search_library(vector, "devotionals" if kind == "devotional" else "books", None, page, per_page)
  return {"kind": kind, "total": found["total"], "page": page, "per_page": per_page, "results": found["results"]}


def search_everything_with_ai(user_id, query, kind=None, page=1, per_page=5):
  """The groups found by meaning, in the order of KINDS (or the one group asked for). Raises
  ai_search.AiSearchProblem or passage_embeddings.PassageSearchProblem for a search that cannot be made."""
  if kind is not None:
    return {"query": query, "ai": True, "groups": [search_group_with_ai(kind, user_id, query, page, per_page)]}
  groups = [search_group_with_ai(each, user_id, query, page, per_page) for each in KINDS]
  # bible_unavailable: Gemini did not answer, so the page can say why there are no verses.
  return {
    "query": query, "ai": True, "bible_unavailable": any(group.get("unavailable") for group in groups),
    "groups": [group for group in groups if group["total"] > 0],
  }

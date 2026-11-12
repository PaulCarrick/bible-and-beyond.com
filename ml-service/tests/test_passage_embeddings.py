"""Tests for the AI search of the commentaries, devotionals, other books and songs (passage_embeddings.py).

Google's embeddings are faked: a text gets a vector pointing one way for each topic word it holds, so "nearest in
meaning" is easy to predict. The tests add their own commentary and devotional (ids starting ai-test-) and their
own accounts, and remove only those.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import ai_search
import faq
import passage_embeddings
from main import app
from passage_embeddings import DIMENSIONS, PassageSearchProblem, cut_into_pieces, query_vector, update_embeddings
from search import connect
from site_users import create_user

PASSWORD = "a long enough password"
DOMAIN = "passage-search-test.example"
COMMENTARY = "ai-test-commentary"
DEVOTIONAL = "ai-test-devotional"
TOPICS = ["blessed", "abraham", "shepherd"]
client = TestClient(app)


def fake_vector(text):
  """One direction per topic word in the text (the last dimension when there is none)."""
  values = [0.0] * DIMENSIONS
  for number, word in enumerate(TOPICS):
    if word in text.lower():
      values[number] = 1.0
  if not any(values):
    values[-1] = 1.0
  return values


def fake_embed(texts):
  return [fake_vector(text) for text in texts]


def remove_test_rows():
  with connect() as connection:
    connection.execute("DELETE FROM passage_embeddings WHERE source_id IN (%s, %s)", (COMMENTARY, DEVOTIONAL))
    connection.execute("DELETE FROM commentaries WHERE id = %s", (COMMENTARY,))
    connection.execute("DELETE FROM devotionals WHERE id = %s", (DEVOTIONAL,))
    connection.execute("DELETE FROM users WHERE email LIKE %s", (f"%@{DOMAIN}",))


@pytest.fixture(autouse=True)
def setup(monkeypatch):
  remove_test_rows()
  passage_embeddings.clear_cache()
  ai_search.clear_cache()
  client.cookies.clear()
  with connect() as connection:
    connection.execute(
      "INSERT INTO commentaries (id, name, short_name, position, license_url) VALUES (%s, 'AI Test', 'AI Test', 999, '')",
      (COMMENTARY,),
    )
    connection.execute(
      """
      INSERT INTO commentary_entries (commentary_id, book_number, chapter, verse, end_verse, text) VALUES
        (%s, 40, 5, 3, 12, 'Blessed are the poor in spirit. The happiness of the godly.'),
        (%s, 1, 12, 1, 3, 'Abraham is called out of his country.')
      """,
      (COMMENTARY, COMMENTARY),
    )
    connection.execute(
      "INSERT INTO devotionals (id, name, author, kind, position, source_name, source_url) "
      "VALUES (%s, 'AI Test Readings', 'Someone', 'chapters', 999, '', '')",
      (DEVOTIONAL,),
    )
    connection.execute("INSERT INTO devotional_sections (devotional_id, number, title) VALUES (%s, 1, 'Part one')", (DEVOTIONAL,))
    connection.execute(
      """
      INSERT INTO devotional_entries (devotional_id, section, unit, part, unit_title, heading, text) VALUES
        (%s, 1, 1, 1, 'The Good Shepherd', '', 'The Lord is my shepherd; I shall not want.'),
        (%s, 1, 2, 1, 'Faith', '', 'By faith {{Abraham obeyed|Hebrews 11:8}} and went out.')
      """,
      (DEVOTIONAL, DEVOTIONAL),
    )
  embedded = []

  def counting_embed(texts, task_type, client=None, tries=1, timeout_seconds=10):
    embedded.append((task_type, list(texts)))
    return fake_embed(texts)

  monkeypatch.setattr(passage_embeddings, "embed_texts", counting_embed)
  monkeypatch.setattr(faq, "ask_gemini", lambda *arguments, **options: "Matthew 5:4\nPsalm 1:1\n")
  yield embedded
  remove_test_rows()
  passage_embeddings.clear_cache()
  ai_search.clear_cache()


def embed_test_texts():
  update_embeddings("commentary", [COMMENTARY], embed=fake_embed)
  return update_embeddings("devotional", [DEVOTIONAL], embed=fake_embed)


def log_in_as(open_ai_queries):
  create_user(f"ann@{DOMAIN}", PASSWORD, True, open_ai_queries)
  assert client.post("/account/login", json={"email": f"ann@{DOMAIN}", "password": PASSWORD}).status_code == 200


def test_texts_are_cut_at_paragraphs_and_sentences():
  text = "First paragraph.\n\nSecond one.\n" + "A long sentence goes on. " * 200
  pieces = cut_into_pieces(text)
  assert pieces[0][0] == 0
  assert all(end - start <= passage_embeddings.PIECE_CHARACTERS for start, end in pieces)
  # Nothing is lost and nothing repeated: the pieces cover the text in order.
  assert "".join(text[start:end] for start, end in pieces).replace("\n", "") == text.replace("\n", "")
  # Short paragraphs share a piece; a long paragraph is cut after a sentence.
  assert text[pieces[0][0]:pieces[0][1]] == "First paragraph.\n\nSecond one."
  assert text[pieces[1][1] - 1] == "."
  assert cut_into_pieces("") == [] and cut_into_pieces("\n\n") == []


def test_only_new_or_changed_text_is_embedded():
  first = embed_test_texts()
  assert (first["pieces"], first["to_embed"]) == (2, 2)
  again = update_embeddings("devotional", [DEVOTIONAL], embed=fake_embed)
  assert (again["already_embedded"], again["to_embed"], again["removed"]) == (2, 0, 0)

  with connect() as connection:
    connection.execute(
      "UPDATE devotional_entries SET text = 'Green pastures.' WHERE devotional_id = %s AND unit = 1", (DEVOTIONAL,)
    )
    connection.execute("DELETE FROM devotional_entries WHERE devotional_id = %s AND unit = 2", (DEVOTIONAL,))
  changed = update_embeddings("devotional", [DEVOTIONAL], embed=fake_embed)
  assert (changed["to_embed"], changed["removed"]) == (1, 1)
  # A dry run sends nothing.
  assert update_embeddings("commentary", [COMMENTARY], dry_run=True, embed=lambda texts: pytest.fail("sent"))["to_embed"] == 0


def test_the_label_and_plain_words_are_what_is_embedded():
  sent = []
  update_embeddings("devotional", [DEVOTIONAL], embed=lambda texts: sent.extend(texts) or fake_embed(texts))
  assert "AI Test Readings, Part one, Faith\nBy faith Abraham obeyed and went out." in sent


def test_the_nearest_passages_are_found_first():
  embed_test_texts()
  found = passage_embeddings.search_commentaries(fake_vector("blessed"), COMMENTARY)
  assert [result["reference"] for result in found["results"]] == ["Matthew 5:3–12", "Genesis 12:1–3"]
  assert found["ai"] is True and found["terms"] == []
  assert found["results"][0]["text"].startswith("Blessed are the poor")

  in_order = passage_embeddings.search_commentaries(fake_vector("blessed"), COMMENTARY, sort_by="verse")
  assert in_order["results"][0]["book_number"] == 1

  readings = passage_embeddings.search_library(fake_vector("shepherd"), "devotionals", DEVOTIONAL)
  assert readings["results"][0]["unit_title"] == "The Good Shepherd"
  # The statement-link markup is not shown.
  assert any(result["text"] == "By faith Abraham obeyed and went out." for result in readings["results"])
  # A devotional is not an Other book.
  assert passage_embeddings.search_library(fake_vector("shepherd"), "books", DEVOTIONAL)["total"] == 0

  with connect() as connection:
    connection.execute("UPDATE devotionals SET is_published = false WHERE id = %s", (DEVOTIONAL,))
  assert passage_embeddings.search_library(fake_vector("shepherd"), "devotionals", DEVOTIONAL)["total"] == 0


def test_a_query_is_embedded_once_a_day_within_the_limit(setup):
  first = query_vector(1, "  The   Beatitudes ")
  assert query_vector(1, "the beatitudes") == first
  assert setup == [("RETRIEVAL_QUERY", ["The Beatitudes"])]
  for number in range(passage_embeddings.SEARCHES_PER_DAY - 1):
    query_vector(1, f"query {number}", date(2026, 11, 12))
  with pytest.raises(PassageSearchProblem, match="AI searches today") as problem:
    query_vector(1, "one too many", date(2026, 11, 12))
  assert problem.value.status_code == 429
  with pytest.raises(PassageSearchProblem, match="under 300"):
    query_vector(1, "x" * 301)


def test_only_an_account_with_the_setting_can_search_by_meaning():
  addresses = [
    ("/search-commentaries", {}), ("/search-other-books", {}), ("/search-music", {}), ("/search-everything", {}),
  ]
  for address, parameters in addresses:
    assert client.get(address, params={"query": "blessed", "match_mode": "ai", **parameters}).status_code == 401
  log_in_as(False)
  for address, parameters in addresses:
    assert client.get(address, params={"query": "blessed", "match_mode": "ai", **parameters}).status_code == 403


def test_the_searches_by_meaning(setup):
  embed_test_texts()
  log_in_as(True)

  notes = client.get("/search-commentaries", params={"query": "blessed", "match_mode": "ai", "commentary": COMMENTARY})
  assert notes.status_code == 200
  assert notes.json()["results"][0]["reference"] == "Matthew 5:3–12"

  everything = client.get("/search-everything", params={"query": "blessed", "match_mode": "ai"})
  assert everything.status_code == 200
  groups = {group["kind"]: group for group in everything.json()["groups"]}
  # The Bible's verses are the ones Gemini named; the rest come from the embeddings (one query embedding for all).
  # In Gemini's order (most relevant first), not Bible order.
  assert [result["reference"] for result in groups["bible"]["results"]] == ["Matthew 5:4", "Psalms 1:1"]
  assert any(result["commentary_id"] == COMMENTARY for result in groups["commentary"]["results"])
  assert [task for task, _texts in setup] == ["RETRIEVAL_QUERY"]

  more = client.get("/search-everything", params={"query": "blessed", "match_mode": "ai", "kind": "devotional", "page": 1})
  assert more.status_code == 200 and len(more.json()["groups"]) == 1

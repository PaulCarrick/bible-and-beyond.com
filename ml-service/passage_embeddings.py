"""AI search of the commentaries, devotionals, other books and songs: search by meaning, with Google's embeddings.

Each passage (a commentary note, a devotional or book entry, a song's words) is cut into pieces of about
PIECE_CHARACTERS, and each piece is turned once into an embedding (a list of numbers standing for what it is
about) by Google's gemini-embedding-001 model. They are kept in the passage_embeddings table (migration 026).
A search turns only the visitor's words into numbers and asks the database for the pieces closest in meaning,
so "beatitudes" finds notes on "Blessed are the poor in spirit" that never use the word.

Only these public-domain texts (and the songs' words) are sent to Google, never a licensed Bible.
scripts/embed_passages.py makes the embeddings, and should be run again after a text is reloaded or a song
added; a search only finds what has been embedded. The search itself is for the same accounts as the Bible's
AI search (open_ai_queries); main.py checks that.
"""

import hashlib
import logging
import threading
import time
from datetime import date

import ai_cache
from commentaries import label_range
from devotionals import STATEMENT_LINK_PIECES
from search import connect

MODEL = "gemini-embedding-001"
# The first 256 of the model's numbers: a third of the space of 768, with much the same results (checked
# 2026-11-12: the same notes came first for three test searches).
DIMENSIONS = 256
KINDS = ("commentary", "devotional", "music")
# A piece is about this long; a longer paragraph is cut at a sentence end (the model reads 2,048 tokens).
PIECE_CHARACTERS = 2000
# Pieces sent to Google in one request, and the most characters in one request.
BATCH_PIECES = 100
BATCH_CHARACTERS = 120_000
# Google's price for gemini-embedding-001, US dollars per million tokens, for the estimate the script prints.
DOLLARS_PER_MILLION_TOKENS = 0.15
CHARACTERS_PER_TOKEN = 4
# The pieces read from the index for one search, and the most passages listed from them.
NEAREST_PIECES = 300
MOST_RESULTS = 50
# How much of the piece a result shows.
EXCERPT_CHARACTERS = 400
# New searches each account may make in a day (a query already asked today does not count).
SEARCHES_PER_DAY = 100
KEEP_SECONDS = 24 * 60 * 60
KEEP_QUERIES = 1000
QUERY_LIMIT = 300


class PassageSearchProblem(Exception):
  """A search that cannot be made; the message is shown to the visitor."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


# Making the embeddings.

def cut_into_pieces(text: str) -> list[tuple[int, int]]:
  """The pieces of a text as (start, end) offsets: whole paragraphs where they fit, about PIECE_CHARACTERS each."""
  segments = []
  position = 0
  for line in text.split("\n"):
    start, end = position, position + len(line)
    position = end + 1
    while end - start > PIECE_CHARACTERS:
      limit = start + PIECE_CHARACTERS
      cut = max(text.rfind(". ", start, limit), text.rfind("; ", start, limit))
      if cut <= start + PIECE_CHARACTERS // 2:
        cut = text.rfind(" ", start, limit)
      cut = limit if cut <= start else cut + 1
      segments.append((start, cut))
      start = cut
    if text[start:end].strip():
      segments.append((start, end))

  pieces = []
  for start, end in segments:
    if pieces and end - pieces[-1][0] <= PIECE_CHARACTERS:
      pieces[-1] = (pieces[-1][0], end)
    else:
      pieces.append((start, end))
  return pieces


def _passages(connection, kind, source_ids=None, books=None):
  """The passages of one kind to embed: dicts with their place, a label and their text."""
  if kind == "commentary":
    rows = connection.execute(
      """
      SELECT e.id, e.commentary_id, c.short_name, b.name, e.chapter, e.verse, e.end_verse, e.text
      FROM commentary_entries e
      JOIN commentaries c ON c.id = e.commentary_id
      JOIN books b ON b.number = e.book_number
      WHERE (%s::text[] IS NULL OR e.commentary_id = ANY(%s)) AND (%s::int[] IS NULL OR e.book_number = ANY(%s))
      ORDER BY e.id
      """,
      [source_ids, source_ids, books, books],
    )
    for entry_id, commentary_id, short_name, book_name, chapter, verse, end_verse, text in rows:
      yield {
        "source_id": commentary_id, "entry_id": entry_id, "section": 0, "unit": 0, "part": 0,
        "label": f"{short_name} on {label_range(book_name, chapter, verse, end_verse)}", "text": text,
      }
  elif kind == "devotional":
    rows = connection.execute(
      """
      SELECT e.devotional_id, e.section, e.unit, e.part, d.name, s.title, e.unit_title, e.heading, e.text
      FROM devotional_entries e
      JOIN devotionals d ON d.id = e.devotional_id
      JOIN devotional_sections s ON s.devotional_id = e.devotional_id AND s.number = e.section
      WHERE %s::text[] IS NULL OR e.devotional_id = ANY(%s)
      ORDER BY e.devotional_id, e.section, e.unit, e.part
      """,
      [source_ids, source_ids],
    )
    for devotional_id, section, unit, part, name, section_title, unit_title, heading, text in rows:
      label = ", ".join(piece for piece in (name, section_title, unit_title, heading) if piece)
      yield {
        "source_id": devotional_id, "entry_id": 0, "section": section, "unit": unit, "part": part,
        "label": label, "text": text,
      }
  else:
    rows = connection.execute(
      "SELECT id, title, author, lyrics FROM music_tracks WHERE %s::text[] IS NULL OR id = ANY(%s) ORDER BY id",
      [source_ids, source_ids],
    )
    for song_id, title, author, lyrics in rows:
      yield {
        "source_id": song_id, "entry_id": 0, "section": 0, "unit": 0, "part": 0,
        "label": f"{title}, {author}" if author else title, "text": lyrics or title,
      }


def _client(timeout_seconds=60):
  from google import genai
  from google.genai import types
  from service_settings import get_setting

  api_key = get_setting("gemini_api_key").strip()
  if not api_key:
    raise PassageSearchProblem("Gemini is not set up (no Gemini key on the Site settings screen or in .env).", 503)
  return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_seconds * 1000))


def embed_texts(texts: list[str], task_type: str, client=None, tries=1, timeout_seconds=10) -> list[list[float]]:
  """Google's embeddings of some texts, in order. With tries, a busy or rate-limited service (or one that does not
  answer in time) is tried again after a minute; the quotas are counted by the minute."""
  from google.genai import types

  client = client or _client(timeout_seconds)
  config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=DIMENSIONS)
  for attempt in range(tries):
    try:
      response = client.models.embed_content(model=MODEL, contents=texts, config=config)
      return [embedding.values for embedding in response.embeddings]
    except Exception as error:  # The SDK raises several kinds of errors.
      retry = getattr(error, "code", None) in (429, 500, 503) or "timed out" in str(error).lower()
      if not retry or attempt == tries - 1:
        raise
      logging.getLogger("passage_embeddings").warning("Embedding try %s failed (%s); waiting a minute.", attempt + 1, str(error)[:120])
      time.sleep(60)
  raise AssertionError("not reached")


def _vector(values) -> str:
  return "[" + ",".join(f"{value:.6f}" for value in values) + "]"


KEY_COLUMNS = ("source_id", "entry_id", "section", "unit", "part", "piece")


def update_embeddings(kind, source_ids=None, books=None, dry_run=False, report=print, embed=None, pieces_per_minute=None):
  """Embeds the passages of one kind that have no embedding yet, or whose text changed, and removes the rows of
  pieces that are gone. source_ids and books (commentaries only) narrow it. pieces_per_minute keeps under a quota
  (Google's free tier allows 100 a minute; each piece counts as one request). Returns what was done (or, with
  dry_run, what would be): pieces, already embedded, embedded now, characters sent, an estimated cost."""
  if kind not in KINDS:
    raise ValueError(f"Unknown kind: {kind}")
  if embed is None:
    client = _client(120)
    embed = lambda texts: embed_texts(texts, "RETRIEVAL_DOCUMENT", client, tries=10)  # noqa: E731
  batch_pieces = min(BATCH_PIECES, pieces_per_minute or BATCH_PIECES)
  with connect() as connection:
    connection.execute("SET statement_timeout = 0")
    wanted = {}
    for passage in _passages(connection, kind, source_ids, books):
      for number, (start, end) in enumerate(cut_into_pieces(passage["text"])):
        words = passage["text"][start:end]
        if kind == "devotional":
          words = STATEMENT_LINK_PIECES.sub("", words)
        text = f"{passage['label']}\n{words.strip()}"
        key = (passage["source_id"], passage["entry_id"], passage["section"], passage["unit"], passage["part"], number)
        wanted[key] = (start, end, hashlib.md5(text.encode("utf-8")).hexdigest(), text)

    existing = {
      tuple(row[:6]): row[6]
      for row in connection.execute(
        "SELECT source_id, entry_id, section, unit, part, piece, text_hash FROM passage_embeddings "
        "WHERE kind = %s AND (%s::text[] IS NULL OR source_id = ANY(%s))",
        [kind, source_ids, source_ids],
      )
    }
    to_embed = [key for key, value in wanted.items() if existing.get(key) != value[2]]
    # Only a run over whole sources can tell that a piece is gone (a run over some books cannot).
    stale = [key for key in existing if key not in wanted] if books is None else []
    characters = sum(len(wanted[key][3]) for key in to_embed)
    summary = {
      "kind": kind, "pieces": len(wanted), "already_embedded": len(wanted) - len(to_embed),
      "to_embed": len(to_embed), "removed": len(stale), "characters": characters,
      "estimated_dollars": round(characters / CHARACTERS_PER_TOKEN / 1_000_000 * DOLLARS_PER_MILLION_TOKENS, 2),
    }
    if dry_run:
      return summary

    for key in stale:
      connection.execute(
        "DELETE FROM passage_embeddings WHERE kind = %s AND "
        + " AND ".join(f"{column} = %s" for column in KEY_COLUMNS),
        [kind, *key],
      )
    connection.commit()

    done = 0
    batch = []
    batch_characters = 0

    def send():
      nonlocal done
      started = time.monotonic()
      vectors = embed([wanted[key][3] for key in batch])
      with connection.transaction():
        for key, values in zip(batch, vectors):
          start, end, text_hash, _text = wanted[key]
          connection.execute(
            """
            INSERT INTO passage_embeddings
              (kind, source_id, entry_id, section, unit, part, piece, start_offset, end_offset, text_hash, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::halfvec)
            ON CONFLICT (kind, source_id, entry_id, section, unit, part, piece) DO UPDATE SET
              start_offset = EXCLUDED.start_offset, end_offset = EXCLUDED.end_offset,
              text_hash = EXCLUDED.text_hash, embedding = EXCLUDED.embedding
            """,
            [kind, *key, start, end, text_hash, _vector(values)],
          )
      done += len(batch)
      report(f"{kind}: {done:,} of {len(to_embed):,} pieces embedded")
      if pieces_per_minute:
        time.sleep(max(0, len(batch) / pieces_per_minute * 60 - (time.monotonic() - started)))

    for key in to_embed:
      size = len(wanted[key][3])
      if batch and (len(batch) == batch_pieces or batch_characters + size > BATCH_CHARACTERS):
        send()
        batch, batch_characters = [], 0
      batch.append(key)
      batch_characters += size
    if batch:
      send()
  return summary


# Searching.

_lock = threading.Lock()
_kept: dict[str, tuple[float, list[float]]] = {}
_counts: dict[tuple[int, date], int] = {}


def query_vector(user_id: int, query: str, today: date | None = None, embed=None) -> list[float]:
  """The embedding of the visitor's words, kept for a day. The query itself is never logged."""
  text = " ".join(query.split())
  if not text:
    raise PassageSearchProblem("Enter what you would like to find.")
  if len(text) > QUERY_LIMIT:
    raise PassageSearchProblem(f"Please keep an AI search under {QUERY_LIMIT} characters.")
  key = text.lower()
  now = time.monotonic()
  version = f"{MODEL}:{DIMENSIONS}"
  with _lock:
    kept = _kept.get(key)
    if kept is not None and now - kept[0] < KEEP_SECONDS:
      return kept[1]
  # Kept in the database for 30 days (ai_cache.py): free, quick, and not counted.
  stored = ai_cache.load("embedding", text, version)
  if stored is not None:
    with _lock:
      _kept[key] = (now, stored)
    return stored
  with _lock:
    count_key = (user_id, today or date.today())
    if _counts.get(count_key, 0) >= SEARCHES_PER_DAY:
      raise PassageSearchProblem(
        f"You have made {SEARCHES_PER_DAY} AI searches today, the most for one day. Please try again tomorrow.", 429,
      )
  try:
    values = (embed or (lambda texts: embed_texts(texts, "RETRIEVAL_QUERY")))([text])[0]
  except PassageSearchProblem:
    raise
  except Exception as error:
    logging.getLogger("passage_search").error(
      "AI search for account %s (%s characters) failed: %s: %s", user_id, len(text), type(error).__name__, str(error)[:200],
    )
    raise PassageSearchProblem("The AI search is not available just now. Please try again in a minute.", 503) from error
  with _lock:
    for old in [entry for entry in _counts if entry[1] != count_key[1]]:
      del _counts[old]
    _counts[count_key] = _counts.get(count_key, 0) + 1
    if len(_kept) >= KEEP_QUERIES:
      for old_key in sorted(_kept, key=lambda entry: _kept[entry][0])[: len(_kept) - KEEP_QUERIES + 1]:
        del _kept[old_key]
    _kept[key] = (now, values)
  ai_cache.store("embedding", text, version, list(values))
  return values


def clear_cache() -> None:
  with _lock:
    _kept.clear()
    _counts.clear()


def excerpt(text: str) -> str:
  """The start of a piece, cut at a word, with … when there is more."""
  text = " ".join(text.split())
  if len(text) <= EXCERPT_CHARACTERS:
    return text
  cut = text.rfind(" ", 0, EXCERPT_CHARACTERS)
  return text[: cut if cut > 0 else EXCERPT_CHARACTERS] + " …"


def _nearest(connection, kind: str, vector: list[float]) -> str:
  """SQL for the pieces of one kind nearest to the vector (the first parameter), nearest first."""
  # The kind is written into the SQL (it is one of KINDS), so the planner uses that kind's own index.
  connection.execute(f"SET LOCAL hnsw.ef_search = {NEAREST_PIECES}")
  connection.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
  return f"""
    SELECT source_id, entry_id, section, unit, part, start_offset, end_offset, embedding <=> %(vector)s::halfvec AS distance
    FROM passage_embeddings WHERE kind = '{kind}'
    ORDER BY embedding <=> %(vector)s::halfvec LIMIT {NEAREST_PIECES}
  """


def search_commentaries(vector, commentary_id=None, book=None, page=1, per_page=25, sort_by=None, sort_direction="asc"):
  """The commentary notes nearest in meaning, best first (or in Bible order when sort_by is "verse"), in the shape
  of commentaries.search_commentaries."""
  with connect() as connection, connection.transaction():
    nearest = _nearest(connection, "commentary", vector)
    rows = connection.execute(
      f"""
      WITH nearest AS MATERIALIZED ({nearest}),
      best AS (
        SELECT DISTINCT ON (n.entry_id) n.entry_id, n.start_offset, n.end_offset, n.distance
        FROM nearest n ORDER BY n.entry_id, n.distance
      )
      SELECT e.commentary_id, c.short_name, e.book_number, b.name, e.chapter, e.verse, e.end_verse,
             substr(e.text, best.start_offset + 1, best.end_offset - best.start_offset)
      FROM best
      JOIN commentary_entries e ON e.id = best.entry_id
      JOIN commentaries c ON c.id = e.commentary_id AND c.is_published
      JOIN books b ON b.number = e.book_number
      WHERE %(commentary)s::text IS NULL OR e.commentary_id = %(commentary)s
      ORDER BY best.distance
      LIMIT {MOST_RESULTS}
      """,
      {"vector": _vector(vector), "commentary": commentary_id},
    ).fetchall()
  counts = {}
  for row in rows:
    counts[row[2]] = counts.get(row[2], 0) + 1
  chosen = [row for row in rows if book is None or row[2] == book]
  if sort_by == "verse":
    chosen.sort(key=lambda row: (row[2], row[4], row[5]), reverse=sort_direction == "desc")
  results = [
    {
      "translation": commentary, "commentary_id": commentary, "commentary_name": short_name,
      "book_number": book_number, "book_name": book_name, "chapter": chapter, "verse": verse,
      "end_verse": end_verse, "reference": label_range(book_name, chapter, verse, end_verse), "text": excerpt(text),
    }
    for commentary, short_name, book_number, book_name, chapter, verse, end_verse, text
    in chosen[(page - 1) * per_page: page * per_page]
  ]
  return {
    "source": "commentary", "ai": True, "terms": [], "total": len(chosen), "page": page, "per_page": per_page,
    "book_counts": [{"book_number": number, "count": counts[number]} for number in sorted(counts)],
    "results": results,
  }


def search_library(vector, collection, book_id=None, page=1, per_page=25):
  """The devotional or Other book passages nearest in meaning, best first, in the shape of devotionals.search_library."""
  with connect() as connection, connection.transaction():
    nearest = _nearest(connection, "devotional", vector)
    rows = connection.execute(
      f"""
      WITH nearest AS MATERIALIZED ({nearest}),
      best AS (
        SELECT DISTINCT ON (n.source_id, n.section, n.unit, n.part) n.*
        FROM nearest n ORDER BY n.source_id, n.section, n.unit, n.part, n.distance
      )
      SELECT d.id, d.name, s.title, e.section, e.unit, e.unit_title, e.heading,
             substr(e.text, best.start_offset + 1, best.end_offset - best.start_offset)
      FROM best
      JOIN devotional_entries e ON e.devotional_id = best.source_id AND e.section = best.section
        AND e.unit = best.unit AND e.part = best.part
      JOIN devotionals d ON d.id = e.devotional_id AND d.is_published AND d.collection = %(collection)s
      JOIN devotional_sections s ON s.devotional_id = e.devotional_id AND s.number = e.section
      ORDER BY best.distance
      LIMIT {MOST_RESULTS}
      """,
      {"vector": _vector(vector), "collection": collection},
    ).fetchall()
  counts = {}
  for row in rows:
    counts.setdefault(row[0], [row[1], 0])[1] += 1
  chosen = [row for row in rows if book_id is None or row[0] == book_id]
  results = [
    {
      "book": found_id, "book_name": name, "section": section, "section_title": section_title, "unit": unit,
      "unit_title": unit_title, "heading": heading, "text": excerpt(STATEMENT_LINK_PIECES.sub("", text)),
    }
    for found_id, name, section_title, section, unit, unit_title, heading, text
    in chosen[(page - 1) * per_page: page * per_page]
  ]
  return {
    "ai": True, "terms": [], "total": len(chosen), "page": page, "per_page": per_page,
    "book_counts": [{"book": found_id, "name": name, "count": count} for found_id, (name, count) in counts.items()],
    "results": results,
  }


def search_music(vector, page=1, per_page=25):
  """The published songs nearest in meaning, best first, in the shape of music.search_music."""
  with connect() as connection, connection.transaction():
    nearest = _nearest(connection, "music", vector)
    rows = connection.execute(
      f"""
      WITH nearest AS MATERIALIZED ({nearest}),
      best AS (SELECT DISTINCT ON (n.source_id) n.* FROM nearest n ORDER BY n.source_id, n.distance)
      SELECT m.id, m.title, m.author, m.media_type,
             substr(coalesce(m.lyrics, ''), best.start_offset + 1, best.end_offset - best.start_offset)
      FROM best JOIN music_tracks m ON m.id = best.source_id AND m.is_published
      ORDER BY best.distance
      LIMIT {MOST_RESULTS}
      """,
      {"vector": _vector(vector)},
    ).fetchall()
  return {
    "ai": True, "terms": [], "total": len(rows), "page": page, "per_page": per_page,
    "results": [
      {"id": song_id, "title": title, "author": author, "kind": "video" if media_type == "video/mp4" else "audio", "text": excerpt(text)}
      for song_id, title, author, media_type, text in rows[(page - 1) * per_page: page * per_page]
    ],
  }

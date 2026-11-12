"""The answers of the AI searches, kept in the database (table ai_search_cache, migration 027).

The same rules as the FAQ's stored answers: an answer is used while it is less than KEEP_DAYS old and was made with
the same instructions (its version), else a new one is asked for and kept. A kept answer costs no AI call, does not
count towards an account's daily allowance, and outlives restarts and deploys. The query is stored only as a SHA-256
of its normalized words. A database problem never stops a search: it is logged and the AI is asked.
"""

import hashlib
import json
import logging

from search import connect

KEEP_DAYS = 30


def normalize(query: str) -> str:
  return " ".join(query.split()).lower()


def query_hash(query: str) -> str:
  return hashlib.sha256(normalize(query).encode("utf-8")).hexdigest()


def load(kind: str, query: str, version: str):
  """The kept answer for a query, or None when there is none, it is too old, or it was made another way."""
  try:
    with connect() as connection:
      row = connection.execute(
        "SELECT result FROM ai_search_cache WHERE kind = %s AND query_hash = %s AND version = %s "
        "AND created_at > now() - make_interval(days => %s)",
        (kind, query_hash(query), version, KEEP_DAYS),
      ).fetchone()
  except Exception as error:  # A database problem should not stop the search.
    logging.getLogger("ai_cache").warning("Kept AI answer not read: %s", error)
    return None
  return row[0] if row else None


def store(kind: str, query: str, version: str, result) -> None:
  """Keeps an answer, replacing an earlier one for the same query, and removes answers past KEEP_DAYS."""
  try:
    with connect() as connection:
      connection.execute(
        """
        INSERT INTO ai_search_cache (kind, query_hash, version, result) VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (kind, query_hash) DO UPDATE
          SET version = EXCLUDED.version, result = EXCLUDED.result, created_at = now()
        """,
        (kind, query_hash(query), version, json.dumps(result)),
      )
      connection.execute(
        "DELETE FROM ai_search_cache WHERE created_at < now() - make_interval(days => %s)", (KEEP_DAYS,)
      )
  except Exception as error:
    logging.getLogger("ai_cache").warning("AI answer not kept: %s", error)


def forget(kind: str, query: str) -> None:
  """Removes one kept answer (for the tests)."""
  with connect() as connection:
    connection.execute("DELETE FROM ai_search_cache WHERE kind = %s AND query_hash = %s", (kind, query_hash(query)))

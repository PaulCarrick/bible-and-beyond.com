import os
import re

import psycopg
from dotenv import load_dotenv

load_dotenv()

FIRST_BOOK_NUMBER = 1
LAST_BOOK_NUMBER = 66

# Text sorting ignores leading punctuation such as opening quotation marks, and uses plain
# character order so the result does not depend on the database's locale.
TEXT_SORT_EXPRESSION = "lower(regexp_replace(v.text, '^[^[:alnum:]]+', '')) COLLATE \"C\""


def build_order_by(sort_by: str, sort_direction: str) -> str:
  direction = "DESC" if sort_direction == "desc" else "ASC"
  reference = f"v.book_number {direction}, v.chapter {direction}, v.verse {direction}, t.code ASC"
  if sort_by == "text":
    return f"{TEXT_SORT_EXPRESSION} {direction}, {reference}"
  return reference


def connect():
  return psycopg.connect(os.environ["DATABASE_URL"])


def parse_terms(query: str, match_mode: str) -> list[str]:
  """Split a query into search terms. Quoted text stays together as one phrase."""
  if match_mode == "phrase":
    phrase = " ".join(query.replace('"', " ").split())
    return [phrase] if phrase else []

  terms = []
  for quoted_phrase, word in re.findall(r'"([^"]+)"|(\S+)', query):
    term = " ".join((quoted_phrase or word).replace('"', " ").split())
    if term:
      terms.append(term)
  return terms


def build_pattern(term: str, whole_words: bool) -> str:
  pattern = re.escape(term)
  if whole_words:
    pattern = rf"\y{pattern}\y"
  return pattern


def search_verses(
  query: str,
  match_mode: str,
  whole_words: bool,
  translation_codes: list[str],
  book_start: int,
  book_end: int,
  book: int | None,
  page: int,
  per_page: int,
  sort_by: str = "verse",
  sort_direction: str = "asc",
) -> dict:
  terms = parse_terms(query, match_mode)
  if not terms:
    raise ValueError("Enter at least one word or phrase to search for.")

  joiner = " OR " if match_mode == "any" else " AND "
  text_condition = joiner.join(["v.text ~* %s"] * len(terms))
  patterns = [build_pattern(term, whole_words) for term in terms]

  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute(
        "SELECT id, code FROM translations WHERE code = ANY(%s)",
        (translation_codes,),
      )
      translation_rows = cursor.fetchall()
      known_codes = {code for _, code in translation_rows}
      unknown_codes = [code for code in translation_codes if code not in known_codes]
      if unknown_codes:
        raise ValueError(f"Unknown translation: {', '.join(unknown_codes)}")
      translation_ids = [translation_id for translation_id, _ in translation_rows]

      base_conditions = (
        f"v.translation_id = ANY(%s) AND v.book_number BETWEEN %s AND %s AND ({text_condition})"
      )
      base_parameters = [translation_ids, book_start, book_end, *patterns]

      cursor.execute(
        f"SELECT v.book_number, count(*) FROM verses v WHERE {base_conditions} "
        "GROUP BY v.book_number ORDER BY v.book_number",
        base_parameters,
      )
      book_counts = [
        {"book_number": book_number, "count": count}
        for book_number, count in cursor.fetchall()
      ]

      if book is None:
        total = sum(entry["count"] for entry in book_counts)
        book_condition = ""
        result_parameters = base_parameters
      else:
        total = sum(entry["count"] for entry in book_counts if entry["book_number"] == book)
        book_condition = " AND v.book_number = %s"
        result_parameters = [*base_parameters, book]

      cursor.execute(
        "SELECT t.code, v.book_number, b.name, v.chapter, v.verse, v.text "
        "FROM verses v "
        "JOIN translations t ON t.id = v.translation_id "
        "JOIN books b ON b.number = v.book_number "
        f"WHERE {base_conditions}{book_condition} "
        f"ORDER BY {build_order_by(sort_by, sort_direction)} "
        "LIMIT %s OFFSET %s",
        [*result_parameters, per_page, (page - 1) * per_page],
      )
      results = [
        {
          "translation": translation_code,
          "book_number": book_number,
          "book_name": book_name,
          "chapter": chapter,
          "verse": verse,
          "reference": f"{book_name} {chapter}:{verse}",
          "text": text,
        }
        for translation_code, book_number, book_name, chapter, verse, text in cursor.fetchall()
      ]

  return {
    "source": "local",
    "query": query,
    "terms": terms,
    "total": total,
    "page": page,
    "per_page": per_page,
    "book_counts": book_counts,
    "results": results,
  }


def list_translations() -> list[dict]:
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute("SELECT code, name FROM translations ORDER BY code")
      return [{"code": code, "name": name, "source": "local"} for code, name in cursor.fetchall()]


def list_books() -> list[dict]:
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute("SELECT number, name, testament FROM books ORDER BY number")
      return [
        {"number": number, "name": name, "testament": testament}
        for number, name, testament in cursor.fetchall()
      ]

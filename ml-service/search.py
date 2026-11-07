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


# The longest a query may run, in milliseconds. main.py sets it for the web service, so one costly search
# cannot keep the database busy; the import scripts and the tools Drupal runs leave it unset (no limit).
STATEMENT_TIMEOUT_MILLISECONDS: int | None = None


def connect():
  if STATEMENT_TIMEOUT_MILLISECONDS:
    return psycopg.connect(os.environ["DATABASE_URL"], options=f"-c statement_timeout={STATEMENT_TIMEOUT_MILLISECONDS}")
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


# A query that is only a Strong's number (G25, g0025, H7225, H7225G) searches by that Hebrew or
# Greek word instead of by English words. A number without a letter also matches its senses.
STRONG_QUERY = re.compile(r"^\s*([GgHh])\s*0*(\d{1,4})([A-Za-z])?\s*$")
SENSE_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def parse_strong_query(query: str) -> dict | None:
  """The Strong's number a query asks for, or None for an ordinary query.

  Returns {"code": "G0025", "codes": [...]}: the number as typed and every word tag it matches.
  """
  match = STRONG_QUERY.match(query)
  if match is None:
    return None
  base = f"{match[1].upper()}{int(match[2]):04d}"
  if match[3]:
    code = base + match[3].upper()
    return {"code": code, "codes": [code]}
  return {"code": base, "codes": [base, *(base + letter for letter in SENSE_LETTERS)]}


def find_strong_entry(connection, strong: dict) -> dict | None:
  """The lexicon entry that describes a Strong's number: the number itself, else its "G" sense,
  else the first sense. None when the lexicon has no such number."""
  base = strong["codes"][0]
  row = connection.execute(
    "SELECT strong_code, language, original, transliteration, gloss FROM lexicon_entries "
    "WHERE strong_code = ANY(%s) ORDER BY (strong_code = %s) DESC, (strong_code = %s) DESC, strong_code "
    "LIMIT 1",
    (strong["codes"], base, base + "G"),
  ).fetchone()
  if row is None:
    return None
  code, language, original, transliteration, gloss = row
  return {
    "code": code, "language": language, "original": original,
    "transliteration": transliteration, "gloss": gloss,
  }


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
  strong = parse_strong_query(query)
  if strong:
    # Verses that contain a Hebrew or Greek word with this number; nothing to highlight.
    terms = []
    text_condition = (
      "(v.book_number, v.chapter, v.verse) IN (SELECT book_number, chapter, verse "
      "FROM original_words WHERE strong_code = ANY(%s))"
    )
    patterns = [strong["codes"]]
  else:
    terms = parse_terms(query, match_mode)
    if not terms:
      raise ValueError("Enter at least one word or phrase to search for.")
    joiner = " OR " if match_mode == "any" else " AND "
    text_condition = joiner.join(["v.text ~* %s"] * len(terms))
    patterns = [build_pattern(term, whole_words) for term in terms]

  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute(
        "SELECT id, code FROM translations WHERE code = ANY(%s) AND is_published",
        (translation_codes,),
      )
      translation_rows = cursor.fetchall()
      known_codes = {code for _, code in translation_rows}
      unknown_codes = [code for code in translation_codes if code not in known_codes]
      if unknown_codes:
        raise ValueError(f"Unknown translation: {', '.join(unknown_codes)}")
      translation_ids = [translation_id for translation_id, _ in translation_rows]
      strong_entry = None
      if strong:
        strong_entry = find_strong_entry(connection, strong)
        if strong_entry is None:
          raise ValueError(f"No Hebrew or Greek word has the Strong's number {strong['code']}.")

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

  response = {
    "source": "local",
    "query": query,
    "terms": terms,
    "total": total,
    "page": page,
    "per_page": per_page,
    "book_counts": book_counts,
    "results": results,
  }
  if strong_entry:
    response["strong"] = strong_entry
  return response


def list_translations() -> list[dict]:
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute("SELECT code, name FROM translations WHERE is_published ORDER BY code")
      return [{"code": code, "name": name, "source": "local"} for code, name in cursor.fetchall()]


def list_books() -> list[dict]:
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute("SELECT number, name, testament FROM books ORDER BY number")
      return [
        {"number": number, "name": name, "testament": testament}
        for number, name, testament in cursor.fetchall()
      ]

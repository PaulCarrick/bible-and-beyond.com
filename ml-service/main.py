import json
import logging
import os
import time
from datetime import date
from typing import Literal

import psycopg
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from accounts import (
  AccountProblem,
  SESSION_DAYS,
  change_password,
  create_account,
  close_account,
  confirm_phone,
  log_in,
  log_out,
  reset_password,
  send_goodbye_email,
  send_phone_code,
  send_reset_text,
  send_reset_email,
  send_verification_email,
  start_password_reset,
  start_phone_code,
  start_verification,
  update_phone,
  user_for_token,
  verify_email,
)
import day_cards
import message_cards
import saved_lists
import sms
import verse_a_day
from api_bible import API_BIBLES, ApiBibleError, list_copyrights, search_api_bible
from bible_reader import get_chapter as get_bible_chapter
from bible_reader import get_contents as get_bible_contents
from devotionals import get_contents as get_devotional_contents
from devotionals import get_unit as get_devotional_unit
from devotionals import list_books as list_other_books
from devotionals import search_books
from site_search import search_everything, search_everything_with_ai
from devotionals import list_devotionals
from commentaries import (
  get_chapter_notes,
  get_commentaries,
  get_contents,
  list_commentaries,
  search_commentaries,
)
from contact import (
  ContactProblem,
  MailUnavailable,
  administrator_address,
  check_message,
  get_recaptcha_site_key,
  send_contact_message,
  verify_recaptcha,
)
from faq import FaqProblem, FaqUnavailable, UnknownQuestion, ask_open_question, get_answer, list_questions
from ai_search import AiSearchProblem, find_verses
import passage_embeddings
from passage_embeddings import PassageSearchProblem
from faq_notes import owner_note_or_nothing
from internet_archive import ArchiveProblem, search_archive
from music import list_songs, search_music, song_file, song_words_file
from maps import list_maps, map_file, search_maps
import external_sites
from map_marks import MarkProblem, create_mark, delete_mark, list_marks, update_mark
from context import get_chapter, get_context, get_parallel, get_related
from subscriptions import (
  SubscriptionProblem,
  check_timezone,
  parse_time,
  delete_subscription,
  list_subscriptions,
  save_subscription,
  unsubscribe,
)
import prayer_list
from conversations import (
  ConversationProblem,
  create_post,
  create_reply,
  delete_post,
  delete_reply,
  list_posts,
  my_groups,
  send_new_post_emails,
  send_new_reply_emails,
  send_reply_email,
  send_shared_request,
  set_answered,
  share_is_due,
  update_post,
  update_reply,
)
from notes import NoteProblem, create_note, delete_note, list_notes, update_note
from playlists import (
  PlaylistProblem,
  copy_public_playlist,
  delete_playlist,
  get_public_playlist,
  list_playlists,
  list_public_playlists,
  save_playlist,
  share_playlist,
)
from original_words import get_lexicon_entry, get_original_words
import search
from search import (
  FIRST_BOOK_NUMBER,
  LAST_BOOK_NUMBER,
  list_books,
  list_translations,
  parse_strong_query,
  search_verses,
)
import document_import
import direct_posts
import head_shots
import message_files
import kindle_books
import site_icons
from site_settings import get_public_settings, get_settings, is_login_required

# Comma-separated list. The live site calls /api on its own domain, so it needs no entry.
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app = FastAPI(title="Bible and Beyond ML Service")

# No query of the web service may run longer than this (a search for nothing but very common words is the
# slowest, about 3 s on the server); one that does is stopped and the visitor asked to narrow it.
search.STATEMENT_TIMEOUT_MILLISECONDS = 10_000


@app.exception_handler(psycopg.errors.QueryCanceled)
def query_took_too_long(_request: Request, _error: psycopg.errors.QueryCanceled):
  return JSONResponse(
    status_code=503,
    content={"detail": "That took too long. Please try more specific words, or try again in a moment."},
  )

# "Login required" (Site settings): while it is on, only these work for a visitor who is not logged in: the
# sign-in and account pages, what the page frame needs (the title, the icons), the links in our emails and
# Telnyx's webhook. Everything else answers 401. The setting is read at most every few seconds.
OPEN_WITHOUT_LOGIN = {"/health", "/site-settings", "/contact-settings", "/subscriptions/unsubscribe", "/sms/webhook", "/message-request"}
OPEN_PREFIXES_WITHOUT_LOGIN = ("/account/", "/site-icon/", "/message-file/")
LOGIN_SETTING_SECONDS = 5
_login_setting = {"value": False, "read_at": None}


def login_is_required():
  now = time.monotonic()
  if _login_setting["read_at"] is None or now - _login_setting["read_at"] > LOGIN_SETTING_SECONDS:
    try:
      _login_setting["value"] = is_login_required()
    except Exception:  # The database being down must not open a closed site; keep the last answer.
      if _login_setting["read_at"] is None:
        raise
    _login_setting["read_at"] = now
  return _login_setting["value"]


def is_open_without_login(path):
  return path in OPEN_WITHOUT_LOGIN or path.startswith(OPEN_PREFIXES_WITHOUT_LOGIN)


@app.middleware("http")
async def require_login(request: Request, call_next):
  if request.method == "OPTIONS" or is_open_without_login(request.url.path):
    return await call_next(request)
  if await run_in_threadpool(login_is_required) and await run_in_threadpool(
    user_for_token, request.cookies.get(SESSION_COOKIE)
  ) is None:
    return JSONResponse(status_code=401, content={"detail": "Please log in to use this site.", "login_required": True})
  return await call_next(request)


app.add_middleware(
  CORSMiddleware,
  allow_origins=ALLOWED_ORIGINS,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)


@app.get("/health")
def health():
  return {"status": "ok"}


class FaqAnswerRequest(BaseModel):
  question_id: int


@app.get("/faq")
def faq_questions():
  """The FAQ questions grouped by heading, and whether answers can be had (a Gemini key is set)."""
  return list_questions()


@app.post("/faq/answer")
def faq_answer(request: FaqAnswerRequest):
  """Gemini's answer to one of the listed questions (by number only, never free text), kept for a month, with
  the site owner's note on that question (cleaned HTML, '' when it has none)."""
  try:
    answer = get_answer(request.question_id)
  except UnknownQuestion as problem:
    raise HTTPException(status_code=404, detail=str(problem)) from problem
  except FaqUnavailable as problem:
    raise HTTPException(
      status_code=503,
      detail="The FAQ answers are not available right now. Please try again later.",
    ) from problem
  return {**answer, "owner_note": owner_note_or_nothing(answer["question"])}


class OpenQuestionRequest(BaseModel):
  # What the visitor wrote, as the editor (Quill) makes it: a little HTML. Only its plain text is sent to Gemini.
  question: str


@app.post("/faq/ask")
def faq_ask(body: OpenQuestionRequest, request: Request):
  """Gemini's answer to the visitor's own question. Only for a logged-in account an administrator allowed."""
  user = user_for_token(request.cookies.get(SESSION_COOKIE))
  if user is None:
    raise HTTPException(status_code=401, detail="Please log in to ask your own question.")
  if not user["open_ai_queries"]:
    raise HTTPException(status_code=403, detail="Your account cannot ask its own questions.")
  try:
    return ask_open_question(user["id"], body.question)
  except FaqProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem)) from problem
  except FaqUnavailable as problem:
    raise HTTPException(
      status_code=503,
      detail="The answer could not be written just now. Please try again in a minute.",
    ) from problem


@app.get("/translations")
def translations():
  api_bibles = [
    {"code": code, "name": bible["name"], "source": "api_bible"}
    for code, bible in API_BIBLES.items()
  ]
  return [*list_translations(), *api_bibles]


@app.get("/copyrights")
def copyrights():
  try:
    return list_copyrights()
  except ApiBibleError as error:
    raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/books")
def books():
  return list_books()


@app.get("/search")
def search(
  request: Request,
  query: str = Query(min_length=1),
  # "ai": Gemini suggests the verses (only for an account an administrator allowed, as for the FAQ's own questions).
  match_mode: Literal["all", "any", "phrase", "ai"] = "all",
  whole_words: bool = False,
  translations: list[str] = Query(default=["BSB"]),
  book_start: int = Query(default=FIRST_BOOK_NUMBER, ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  book_end: int = Query(default=LAST_BOOK_NUMBER, ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  book: int | None = Query(default=None, ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  page: int = Query(default=1, ge=1),
  per_page: int = Query(default=25, ge=1, le=100),
  sort_by: Literal["verse", "text"] = "verse",
  sort_direction: Literal["asc", "desc"] = "asc",
):
  if book_start > book_end:
    raise HTTPException(status_code=422, detail="book_start must not come after book_end.")
  api_codes = [code for code in translations if code in API_BIBLES]
  if match_mode == "ai":
    return search_with_ai(
      request, query, translations, api_codes, book_start, book_end, book, page, per_page, sort_by, sort_direction,
    )
  if api_codes and parse_strong_query(query):
    raise HTTPException(
      status_code=422,
      detail=f"Searching by Strong's number is not available for {', '.join(api_codes)}.",
    )
  if api_codes:
    if len(translations) > 1:
      raise HTTPException(
        status_code=422,
        detail=f"{', '.join(api_codes)} can only be searched on its own, not with other Bibles.",
      )
    try:
      return search_api_bible(
        code=api_codes[0],
        query=query,
        match_mode=match_mode,
        whole_words=whole_words,
        book_start=book_start,
        book_end=book_end,
        book=book,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_direction=sort_direction,
      )
    except ValueError as error:
      raise HTTPException(status_code=422, detail=str(error)) from error
    except ApiBibleError as error:
      raise HTTPException(status_code=503, detail=str(error)) from error

  try:
    return search_verses(
      query=query,
      match_mode=match_mode,
      whole_words=whole_words,
      translation_codes=translations,
      book_start=book_start,
      book_end=book_end,
      book=book,
      page=page,
      per_page=per_page,
      sort_by=sort_by,
      sort_direction=sort_direction,
    )
  except ValueError as error:
    raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/context")
def context(
  translation: str = Query(min_length=1),
  book: int = Query(ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  chapter: int = Query(ge=1),
  verse: int = Query(ge=1),
):
  code = translation.upper()
  if code in API_BIBLES:
    raise HTTPException(status_code=422, detail=f"Show in Context is not available for {code}.")
  settings = get_settings()
  result = get_context(
    code, book, chapter, verse, settings["context_verses_before"], settings["context_verses_after"]
  )
  if result is None:
    raise HTTPException(status_code=404, detail="That verse was not found.")
  return result


@app.get("/chapter")
def chapter_of_verse(
  translation: str = Query(min_length=1),
  book: int = Query(ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  chapter: int = Query(ge=1),
  verse: int = Query(ge=1),
):
  code = translation.upper()
  if code in API_BIBLES:
    raise HTTPException(status_code=422, detail=f"Full Chapter is not available for {code}.")
  result = get_chapter(code, book, chapter, verse)
  if result is None:
    raise HTTPException(status_code=404, detail="That verse was not found.")
  return result


@app.get("/parallel")
def parallel(
  book: int = Query(ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  chapter: int = Query(ge=1),
  verse: int = Query(ge=1),
):
  result = get_parallel(book, chapter, verse)
  if result is None:
    raise HTTPException(status_code=404, detail="That verse was not found.")
  return result


@app.get("/related")
def related(
  translation: str = Query(min_length=1),
  book: int = Query(ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  chapter: int = Query(ge=1),
  verse: int = Query(ge=1),
  direction: Literal["from", "to"] = "from",
):
  code = translation.upper()
  if code in API_BIBLES:
    raise HTTPException(status_code=422, detail=f"Related Verses is not available for {code}.")
  result = get_related(code, book, chapter, verse, get_settings()["related_verses_limit"], direction)
  if result is None:
    raise HTTPException(status_code=404, detail="That verse was not found.")
  return result


@app.get("/original-words")
def original_words(
  book: int = Query(ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  chapter: int = Query(ge=1),
  verse: int = Query(ge=1),
):
  result = get_original_words(book, chapter, verse)
  if result is None:
    raise HTTPException(status_code=404, detail="No Hebrew or Greek words were found for that verse.")
  return result


MAXIMUM_LEXICON_VERSES = 30


@app.get("/lexicon")
def lexicon(
  translation: str = Query(min_length=1),
  strong_code: str = Query(pattern=r"^[GHgh]\d{4}[A-Za-z]?$"),
):
  code = translation.upper()
  if code in API_BIBLES:
    raise HTTPException(status_code=422, detail=f"Word studies are not available for {code}.")
  normalized = strong_code.upper()
  result = get_lexicon_entry(code, normalized, MAXIMUM_LEXICON_VERSES)
  if result is None:
    raise HTTPException(status_code=404, detail="That word was not found.")
  return result


@app.get("/commentaries")
def commentaries(
  book: int = Query(ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  chapter: int = Query(ge=1),
  verse: int = Query(ge=1),
  commentary: str | None = Query(default=None, max_length=60),
):
  result = get_commentaries(book, chapter, verse, commentary)
  if result is None:
    raise HTTPException(status_code=404, detail="No commentary has notes on that verse.")
  return result


@app.get("/commentary-list")
def commentary_list():
  return list_commentaries()


def ai_search_account(request: Request) -> dict:
  """The logged-in account, if an administrator allowed it AI searches (open_ai_queries); else 401 or 403."""
  user = user_for_token(request.cookies.get(SESSION_COOKIE))
  if user is None:
    raise HTTPException(status_code=401, detail="Please log in to search with AI.")
  if not user["open_ai_queries"]:
    raise HTTPException(status_code=403, detail="Your account cannot search with AI.")
  return user


def ai_query_vector(request: Request, query: str) -> list[float]:
  """The embedding of the query for a search by meaning (passage_embeddings.py), for an allowed account."""
  user = ai_search_account(request)
  try:
    return passage_embeddings.query_vector(user["id"], query)
  except PassageSearchProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem)) from problem


def search_with_ai(
  request: Request,
  query: str,
  translations: list[str],
  api_codes: list[str],
  book_start: int,
  book_end: int,
  book: int | None,
  page: int,
  per_page: int,
  sort_by: str,
  sort_direction: str,
) -> dict:
  """The verses Gemini suggests for the query, listed from the chosen Bibles on this site like any search."""
  user = ai_search_account(request)
  if api_codes:
    # Their text may never go near an AI, and they cannot be listed by verse anyway.
    raise HTTPException(
      status_code=422,
      detail=f"AI search uses only the Bibles on this site, not {', '.join(api_codes)}.",
    )
  try:
    references = find_verses(user["id"], query)
  except AiSearchProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem)) from problem
  except FaqUnavailable as problem:
    raise HTTPException(
      status_code=503,
      detail="The AI search is not available just now. Please try again in a minute.",
    ) from problem
  try:
    response = search_verses(
      query=query,
      match_mode="all",
      whole_words=False,
      translation_codes=translations,
      book_start=book_start,
      book_end=book_end,
      book=book,
      page=page,
      per_page=per_page,
      sort_by=sort_by,
      sort_direction=sort_direction,
      references=references,
    )
  except ValueError as error:
    raise HTTPException(status_code=422, detail=str(error)) from error
  # How many verses the AI named (some may be outside the books chosen).
  return {**response, "ai": True, "ai_verse_count": len(references)}


@app.get("/search-commentaries")
def search_commentary_text(
  request: Request,
  query: str = Query(min_length=1),
  # "ai": the notes nearest in meaning (only for an account allowed AI searches).
  match_mode: Literal["all", "any", "phrase", "ai"] = "all",
  commentary: str | None = Query(default=None, max_length=60),
  book_start: int = Query(default=FIRST_BOOK_NUMBER, ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  book_end: int = Query(default=LAST_BOOK_NUMBER, ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  book: int | None = Query(default=None, ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  page: int = Query(default=1, ge=1),
  per_page: int = Query(default=25, ge=1, le=100),
  sort_by: Literal["verse"] | None = None,
  sort_direction: Literal["asc", "desc"] = "asc",
):
  if book_start > book_end:
    raise HTTPException(status_code=422, detail="book_start must not come after book_end.")
  if match_mode == "ai":
    vector = ai_query_vector(request, query)
    return passage_embeddings.search_commentaries(vector, commentary, book, page, per_page, sort_by, sort_direction)
  try:
    return search_commentaries(
      query, match_mode, commentary, book_start, book_end, book, page, per_page, sort_by, sort_direction
    )
  except ValueError as error:
    raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/search-other-books")
def search_other_books(
  request: Request,
  query: str = Query(min_length=1, max_length=500),
  match_mode: Literal["all", "any", "phrase", "ai"] = "all",
  book: str | None = Query(default=None, max_length=60),
  page: int = Query(default=1, ge=1, le=1000),
  per_page: int = Query(default=25, ge=1, le=100),
  sort_by: Literal["order"] | None = None,
):
  if match_mode == "ai":
    return passage_embeddings.search_library(ai_query_vector(request, query), "books", book, page, per_page)
  try:
    return search_books(query, match_mode, book, page, per_page, sort_by)
  except ValueError as error:
    raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/search-internet-archive")
def search_the_internet_archive(
  query: str = Query(min_length=1, max_length=500),
  # "texts": books, found inside their text (lending books too); "audio": recordings.
  kind: Literal["texts", "audio"] = "texts",
  page: int = Query(default=1, ge=1, le=1000),
  per_page: int = Query(default=10, ge=1, le=50),
):
  try:
    return search_archive(query, kind, page, per_page)
  except ArchiveProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem)) from problem


@app.get("/search-everything")
def search_everything_on_the_site(
  request: Request,
  query: str = Query(min_length=1, max_length=500),
  match_mode: Literal["all", "any", "phrase", "ai"] = "all",
  kind: Literal["bible", "commentary", "devotional", "book", "music", "map", "faq"] | None = None,
  page: int = Query(default=1, ge=1, le=1000),
  per_page: int = Query(default=5, ge=1, le=25),
):
  if match_mode == "ai":
    user = ai_search_account(request)
    try:
      return search_everything_with_ai(user["id"], query, kind, page, per_page)
    except (AiSearchProblem, PassageSearchProblem) as problem:
      raise HTTPException(status_code=problem.status_code, detail=str(problem)) from problem
  try:
    return search_everything(query, match_mode, kind, page, per_page)
  except ValueError as error:
    raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/commentary-contents")
def commentary_contents(commentary: str = Query(min_length=1, max_length=60)):
  result = get_contents(commentary)
  if result is None:
    raise HTTPException(status_code=404, detail="That commentary was not found.")
  return result


@app.get("/commentary-chapter")
def commentary_chapter(
  commentary: str = Query(min_length=1, max_length=60),
  book: int = Query(ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  chapter: int = Query(ge=1),
):
  result = get_chapter_notes(commentary, book, chapter)
  if result is None:
    raise HTTPException(status_code=404, detail="That commentary has no notes on that chapter.")
  return result


@app.get("/bible-contents")
def bible_contents(translation: str = Query(min_length=1, max_length=20)):
  code = translation.upper()
  if code in API_BIBLES:
    raise HTTPException(status_code=422, detail=f"{code} cannot be read a chapter at a time.")
  result = get_bible_contents(code)
  if result is None:
    raise HTTPException(status_code=404, detail="That Bible was not found.")
  return result


@app.get("/bible-chapter")
def bible_chapter(
  translation: str = Query(min_length=1, max_length=20),
  book: int = Query(ge=FIRST_BOOK_NUMBER, le=LAST_BOOK_NUMBER),
  chapter: int = Query(ge=1),
):
  code = translation.upper()
  if code in API_BIBLES:
    raise HTTPException(status_code=422, detail=f"{code} cannot be read a chapter at a time.")
  result = get_bible_chapter(code, book, chapter)
  if result is None:
    raise HTTPException(status_code=404, detail="That chapter was not found.")
  return result


@app.get("/devotionals")
def devotionals():
  return list_devotionals()


@app.get("/other-books")
def other_books():
  """The published Other books (read a chapter at a time). Their chapters come from /devotional-contents and
  /devotional-unit, like a devotional's."""
  return list_other_books()


@app.get("/music")
def music():
  """The published songs of the Christian music section, by title, with their words."""
  return list_songs()


@app.get("/music/{song_id}/file")
def music_file(song_id: str):
  """A published song's MP3 or MP4. The player asks for parts of it (Range requests), so it can seek.
  Cached for a month: the page adds ?v= with the song's version, which changes when the file is replaced."""
  found = song_file(song_id)
  if found is None:
    raise HTTPException(status_code=404, detail="That song was not found.")
  path, media_type = found
  return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=2592000"})


@app.get("/music/{song_id}/words")
def music_words_file(song_id: str):
  """A published song's words as a PDF or picture, shown on the music page in place of the typed words."""
  found = song_words_file(song_id)
  if found is None:
    raise HTTPException(status_code=404, detail="That song has no words file.")
  path, media_type = found
  return FileResponse(
    path, media_type=media_type,
    headers={"Cache-Control": "public, max-age=2592000", "X-Content-Type-Options": "nosniff"},
  )


@app.get("/search-music")
def search_the_music(
  request: Request,
  query: str = Query(min_length=1, max_length=500),
  match_mode: Literal["all", "any", "phrase", "ai"] = "all",
  page: int = Query(default=1, ge=1, le=1000),
  per_page: int = Query(default=25, ge=1, le=100),
):
  if match_mode == "ai":
    return passage_embeddings.search_music(ai_query_vector(request, query), page, per_page)
  try:
    return search_music(query, match_mode, page, per_page)
  except ValueError as error:
    raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/external-sites")
def external_sites_list():
  """The external sites the administrators chose to show in the sidebar (name, address and host only); the sidebar's
  "External sites" group appears only when there are some."""
  return {"sites": external_sites.list_public_sites()}


@app.get("/maps")
def maps_list(
  book: int | None = Query(default=None, ge=1, le=66),
  chapter: int | None = Query(default=None, ge=1, le=200),
  verse: int | None = Query(default=None, ge=1, le=200),
):
  """The published maps by title, with their verses; with a verse, only the maps linked to it."""
  return {"maps": list_maps(book=book, chapter=chapter, verse=verse)}


@app.get("/map-file/{map_id}/{which}")
def maps_file(map_id: str, which: Literal["display", "thumbnail"]):
  """A published map's picture: the WebP shown on the site ("display") or the small one for the list
  ("thumbnail"). The file as uploaded is never served (the owner's choice, for the maps' licences). Cached for a
  month: the page adds ?v= with the map's version, which changes when the picture is replaced."""
  found = map_file(map_id, which)
  if found is None:
    raise HTTPException(status_code=404, detail="That map was not found.")
  path, media_type = found
  headers = {"Cache-Control": "public, max-age=2592000", "X-Content-Type-Options": "nosniff"}
  return FileResponse(path, media_type=media_type, headers=headers)


@app.get("/message-file/{key}/picture.jpg")
def message_file_picture(key: str):
  """The picture of a Message a day's text message (MMS; message_files.py): fetched by the text service."""
  path = message_files.picture_file(key)
  if path is None:
    raise HTTPException(status_code=404, detail="This file is no longer here.")
  return FileResponse(path, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex"})


@app.get("/message-file/{key}")
def message_file_download(key: str):
  """The files of a Message a day, from the link in its text: the one file, or a .zip of them all. Kept 30 days."""
  found = message_files.download(key)
  if found is None:
    raise HTTPException(status_code=404, detail="These files are no longer here (they are kept for 30 days).")
  data, media_type, name = found
  return Response(
    data, media_type=media_type,
    headers={
      "Content-Disposition": f'attachment; filename="{name}"', "X-Content-Type-Options": "nosniff",
      "X-Robots-Tag": "noindex", "Cache-Control": "private, max-age=3600",
    },
  )


@app.get("/message-card/{name}")
def message_card(name: str):
  """A picture message card (message_cards.py): the verse or reading over a picture, under a random name that
  only its message carries. Telnyx fetches it to send an MMS. Kept KEEP_DAYS days, then deleted."""
  path = message_cards.card_file(name)
  if path is None:
    raise HTTPException(status_code=404, detail="That picture was not found.")
  headers = {
    "Cache-Control": "public, max-age=604800", "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex",
  }
  return FileResponse(path, media_type="image/jpeg", headers=headers)


@app.get("/day-card/verse")
def day_card_verse(
  translation: str | None = Query(default=None, max_length=20),
  book: int | None = Query(default=None, ge=1, le=66),
  chapter: int | None = Query(default=None, ge=1, le=150),
  verse: int | None = Query(default=None, ge=1, le=176),
):
  """Verse of the day: a random well-known verse as a picture (day_cards.py), made anew each time, inline. With
  translation, book, chapter and verse, that verse instead ("Download Card" under a search result)."""
  try:
    if translation and book and chapter and verse:
      return day_cards.chosen_verse_card(translation, book, chapter, verse)
    return day_cards.verse_card()
  except day_cards.DayCardProblem as problem:
    raise HTTPException(status_code=404, detail=str(problem))


@app.get("/day-card/devotional")
def day_card_devotional(
  day: date = Query(description="The visitor's own date, YYYY-MM-DD."),
  hour: int = Query(default=8, ge=0, le=23, description="The visitor's own hour: the evening reading from 17."),
):
  """Devotional of the day: today's reading of a daily devotional as a picture (day_cards.py), inline."""
  # The visitor's date is at most a day either side of the server's (time zones).
  if abs((day - date.today()).days) > 1:
    raise HTTPException(status_code=422, detail="That is not today's date.")
  try:
    return day_cards.devotional_card(day, hour)
  except day_cards.DayCardProblem as problem:
    raise HTTPException(status_code=404, detail=str(problem))


@app.get("/search-maps")
def search_the_maps(
  query: str = Query(min_length=1, max_length=500),
  match_mode: Literal["all", "any", "phrase"] = "all",
  page: int = Query(default=1, ge=1, le=1000),
  per_page: int = Query(default=25, ge=1, le=100),
):
  try:
    return search_maps(query, match_mode, page, per_page)
  except ValueError as error:
    raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/devotional-contents")
def devotional_contents(devotional: str = Query(min_length=1, max_length=60)):
  result = get_devotional_contents(devotional)
  if result is None:
    raise HTTPException(status_code=404, detail="That devotional was not found.")
  return result


@app.get("/devotional-unit")
def devotional_unit(
  devotional: str = Query(min_length=1, max_length=60),
  # Section 0 is a preface or prologue (the Summa's, or an uploaded book's).
  section: int = Query(ge=0, le=99),
  unit: int = Query(ge=1, le=999),
):
  result = get_devotional_unit(devotional, section, unit)
  if result is None:
    raise HTTPException(status_code=404, detail="That day or chapter was not found.")
  return result


@app.get("/site-settings")
def site_settings():
  """The site title and copyright line that the pages show, and the address of each icon an administrator
  replaced (header_icon, tab_icon; null for the site's own). Nothing private is ever in this answer."""
  return {**get_public_settings(), **site_icons.public_paths()}


@app.get("/library-image/{name}")
def library_image(name: str):
  """A picture from a PDF or Word upload (document_import.py). Its name comes from its contents, so it never
  changes and can be cached for a year."""
  found = document_import.image_file(name)
  if found is None:
    raise HTTPException(status_code=404, detail="There is no such picture.")
  path, media_type = found
  return FileResponse(
    path, media_type=media_type,
    headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"},
  )


@app.get("/library-page/{document}/{page}.webp")
def library_page(document: str, page: str):
  """A page of a PDF kept with "Preserve original pages" (document_import.py). Its folder is named from the PDF's
  contents, so a page never changes and can be cached for a year."""
  path = document_import.page_image_file(document, page)
  if path is None:
    raise HTTPException(status_code=404, detail="There is no such page.")
  return FileResponse(
    path, media_type="image/webp",
    headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"},
  )


@app.get("/kindle-books")
def kindle_books_index():
  """The published Kindle books (Read other books): title, author, the Kindle link and the cover's address."""
  return {"books": kindle_books.list_public_books()}


@app.get("/kindle-book-cover/{book_id}")
def kindle_book_cover(book_id: int):
  """A published Kindle book's picture (PNG, JPEG, WebP or GIF only). Cached for a month: the page adds ?v=, which
  changes when the picture is replaced."""
  found = kindle_books.cover_file(book_id)
  if found is None:
    raise HTTPException(status_code=404, detail="That book has no picture.")
  path, media_type = found
  return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=2592000", "X-Content-Type-Options": "nosniff"})


@app.get("/site-icon/{kind}")
def site_icon(kind: str):
  """An icon uploaded on the Site settings screen. Cached for a month: the page adds ?v= with its version,
  which changes when it is replaced. An SVG opened on its own cannot run anything (the sandbox policy)."""
  if kind not in site_icons.KINDS:
    raise HTTPException(status_code=404, detail="There is no such icon.")
  found = site_icons.current(kind)
  if found is None:
    raise HTTPException(status_code=404, detail="That icon has not been replaced.")
  path, media_type = found
  return FileResponse(
    path,
    media_type=media_type,
    headers={
      "Cache-Control": "public, max-age=2592000",
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    },
  )


@app.get("/contact-settings")
def contact_settings():
  """What the contact form needs to show itself: the public reCAPTCHA site key (empty when not set up)."""
  return {"recaptcha_site_key": get_recaptcha_site_key()}


class ContactRequest(BaseModel):
  name: str
  email: str
  phone: str = ""
  # The message as the editor (Quill) writes it: a little HTML, cleaned before use.
  message: str
  recaptcha_token: str = ""


@app.post("/contact")
def contact(request: ContactRequest, http_request: Request):
  """Checks the visitor and the message, then emails it with the server settings kept in Drupal."""
  forwarded = http_request.headers.get("x-forwarded-for", "").split(",")[0].strip()
  remote_address = forwarded or (http_request.client.host if http_request.client else None)
  try:
    values = check_message(request.name, request.email, request.phone, request.message)
    verify_recaptcha(request.recaptcha_token, remote_address)
    send_contact_message(values)
  except ContactProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  except MailUnavailable as problem:
    logging.getLogger("contact").error("Contact message not sent: %s", problem)
    raise HTTPException(
      status_code=502,
      detail="Your message could not be sent right now. Please try again later.",
    )
  return {"sent": True}


SESSION_COOKIE = "session"


class RegisterRequest(BaseModel):
  # An email address, or "" to set up the account with a cell phone number instead (phone; 2026-11-17).
  email: str = ""
  password: str
  password_confirmation: str
  first_name: str = ""
  last_name: str = ""
  phone: str = ""
  # The phone is a cell number (sms.py). How notices reach the member: "Send via Email", "Send via SMS" (one or
  # both; texts need a cell number, and ticking SMS is the consent to texts).
  phone_is_cell: bool = False
  send_via_email: bool = True
  send_via_sms: bool = False
  # Send Multimedia Messages: the verse a day and the devotionals as a picture (message_cards.py).
  send_multimedia: bool = False
  # A verse a day (verse_a_day.py): its time of day in the visitor's own time zone (an IANA name).
  verse_a_day: bool = False
  verse_time: str = "07:00"
  timezone: str = "UTC"


class LoginRequest(BaseModel):
  # What was typed in the login box: an email address, or the phone number of an account that logs in with it.
  email: str
  password: str


def start_session(response: Response, request: Request, token: str):
  """Puts the session token in a cookie that scripts cannot read (Secure when the visit is over HTTPS)."""
  is_secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
  response.set_cookie(
    SESSION_COOKIE,
    token,
    max_age=SESSION_DAYS * 24 * 60 * 60,
    httponly=True,
    secure=is_secure,
    samesite="lax",
    path="/",
  )


# The administrator's address for account requests, read from Drupal at most every 10 minutes (drush is slow).
ADDRESS_SECONDS = 600
_request_address = {"value": "", "read_at": None}


@app.get("/account/request-address")
def account_request_address():
  """While "Login required" is on (and so visitors cannot set up accounts), the address the log-in page offers for
  asking for one: the Contact email to address of the Site settings screen. Empty otherwise, or when none is set."""
  if not login_is_required():
    return {"email": ""}
  now = time.monotonic()
  if _request_address["read_at"] is None or now - _request_address["read_at"] > ADDRESS_SECONDS:
    _request_address["value"] = administrator_address()
    _request_address["read_at"] = now
  return {"email": _request_address["value"]}


@app.post("/account/register")
def account_register(body: RegisterRequest, request: Request, response: Response, background: BackgroundTasks):
  """Makes an account, emails a link to confirm the address (or, for an account set up with a phone number, texts a
  code to confirm it), and logs the visitor in. Refused while "Login required" is on: then only an administrator sets
  up accounts (Drupal Site users)."""
  if login_is_required():
    raise HTTPException(status_code=403, detail="New accounts are set up by the site's administrators. Please ask them for one.")
  if body.verse_a_day:
    # Checked before the account is made, so a bad time or zone does not leave half a sign-up.
    try:
      parse_time(body.verse_time)
      check_timezone(body.timezone)
    except SubscriptionProblem as problem:
      raise HTTPException(status_code=problem.status_code, detail=str(problem))
  try:
    created = create_account(
      body.email, body.password, body.password_confirmation, body.first_name, body.last_name, body.phone,
      body.phone_is_cell, body.send_via_sms, body.send_via_email, body.send_multimedia,
    )
    user, token = log_in(body.email if created["email"] else body.phone, body.password)
  except AccountProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  verification = start_verification(created["id"])
  if verification:
    background.add_task(send_verification_email, *verification)
  phone_code = start_phone_code(created["id"])
  if phone_code:
    background.add_task(send_phone_code, *phone_code)
  # A phone-only account gets its welcome text once its number is confirmed (account_confirm_phone).
  if created["sms_opt_in"] and created["email"]:
    background.add_task(sms.welcome_text, sms.texting_number(body.phone))
  if body.verse_a_day:
    verse_a_day.save_subscription(created["id"], body.verse_time, body.timezone)
  start_session(response, request, token)
  return {"user": user}


class PhoneCodeRequest(BaseModel):
  code: str = Field(default="", max_length=20)


@app.post("/account/confirm-phone")
def account_confirm_phone(body: PhoneCodeRequest, request: Request, background: BackgroundTasks):
  """The logged-in member types the code texted to the phone their account logs in with. Wrong codes are counted
  (accounts.PHONE_CODE_ATTEMPTS). Once confirmed, texts can go to it (and the welcome text does, if they chose
  texts)."""
  user = require_user(request, "Please log in first.")
  try:
    confirmed = confirm_phone(user["id"], body.code)
  except AccountProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  if confirmed["sms_opt_in"]:
    background.add_task(sms.welcome_text, sms.texting_number(confirmed["phone"]))
  return {"user": confirmed}


@app.post("/account/resend-phone-code")
def account_resend_phone_code(request: Request, background: BackgroundTasks):
  """Texts the logged-in member a new code for their phone (not more than one a minute)."""
  user = require_user(request, "Please log in first.")
  phone_code = start_phone_code(user["id"])
  if phone_code:
    background.add_task(send_phone_code, *phone_code)
  return {"sent": True}


class PhoneRequest(BaseModel):
  phone: str = Field(default="", max_length=200)
  phone_is_cell: bool = False
  send_via_email: bool = True
  send_via_sms: bool = False
  # Send Multimedia Messages; left as it is when not sent.
  send_multimedia: bool | None = None


@app.put("/account/phone")
def account_phone(body: PhoneRequest, request: Request, background: BackgroundTasks):
  """Changes the logged-in member's phone number and how their notices reach them, by email, text or both (the
  My account page). Turning texts on sends a welcome text that says how to stop."""
  user = require_user(request, "Please log in to change your account.")
  try:
    changed, welcome_number = update_phone(
      user["id"], body.phone, body.phone_is_cell, body.send_via_sms, body.send_via_email, body.send_multimedia
    )
  except AccountProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  if changed["logs_in_with_phone"] and not changed["phone_verified"]:
    # A new login number: confirmed again by a texted code; the welcome text waits for it.
    phone_code = start_phone_code(changed["id"])
    if phone_code:
      background.add_task(send_phone_code, *phone_code)
  elif welcome_number:
    background.add_task(sms.welcome_text, welcome_number)
  return {"user": changed}


class VerseSubscriptionRequest(BaseModel):
  # The time of day, such as "07:00", in the visitor's own time zone (an IANA name such as America/Chicago).
  send_time: str
  timezone: str


@app.get("/verse-subscription")
def verse_subscription_get(request: Request):
  """Whether the logged-in member gets a verse a day, and when (null when not)."""
  user = require_user(request, "Please log in to change your account.")
  return {"subscription": verse_a_day.get_subscription(user["id"])}


@app.put("/verse-subscription")
def verse_subscription_save(body: VerseSubscriptionRequest, request: Request):
  """Starts the verse a day, or changes its time."""
  user = require_user(request, "Please log in to change your account.")
  try:
    return {"subscription": verse_a_day.save_subscription(user["id"], body.send_time, body.timezone)}
  except SubscriptionProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.delete("/verse-subscription")
def verse_subscription_delete(request: Request):
  user = require_user(request, "Please log in to change your account.")
  verse_a_day.delete_subscription(user["id"])
  return {"deleted": True}


@app.post("/sms/webhook")
async def sms_webhook(request: Request):
  """Telnyx calls this when someone replies to one of the site's texts: STOP turns their texts off, START back on,
  HELP gets an answer. Only webhooks signed by Telnyx are acted on."""
  body = await request.body()
  if not sms.verify_signature(body, request.headers.get("telnyx-signature-ed25519", ""), request.headers.get("telnyx-timestamp", "")):
    raise HTTPException(status_code=401, detail="Not signed by Telnyx.")
  # The database work is ordinary blocking code: run it off the event loop.
  return {"done": await run_in_threadpool(sms.handle_webhook, body)}


@app.post("/account/login")
def account_login(body: LoginRequest, request: Request, response: Response):
  try:
    user, token = log_in(body.email, body.password)
  except AccountProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  start_session(response, request, token)
  return {"user": user}


@app.post("/account/logout")
def account_logout(request: Request, response: Response):
  log_out(request.cookies.get(SESSION_COOKIE))
  response.delete_cookie(SESSION_COOKIE, path="/")
  return {"user": None}


@app.get("/account/me")
def account_me(request: Request):
  """Who is logged in, or null. Logging in is never required; this only tells the page what to show."""
  return {"user": user_for_token(request.cookies.get(SESSION_COOKIE))}


@app.get("/account/head-shot")
def account_head_shot(request: Request):
  """The logged-in member's own head shot (head_shots.py). Nobody else is ever sent it."""
  user = require_user(request, "Please log in.")
  path = head_shots.path_for(user["id"])
  if not user.get("head_shot") or not path.is_file():
    raise HTTPException(status_code=404, detail="You have no picture.")
  # The address carries the version, so the browser may keep it; private, as it is one member's.
  return FileResponse(
    path, media_type="image/webp",
    headers={"Cache-Control": "private, max-age=31536000", "X-Content-Type-Options": "nosniff"},
  )


@app.put("/account/head-shot")
async def account_head_shot_save(request: Request):
  """A new head shot: the request body is the picture (the page shrinks it first, so it is under 1 MB)."""
  user = await run_in_threadpool(require_user, request, "Please log in.")
  body = await request.body()
  try:
    await run_in_threadpool(head_shots.save, user["id"], body)
  except head_shots.HeadShotProblem as problem:
    raise HTTPException(status_code=422, detail=str(problem))
  return {"user": await run_in_threadpool(user_for_token, request.cookies.get(SESSION_COOKIE))}


@app.delete("/account/head-shot")
def account_head_shot_remove(request: Request):
  """Takes the member's head shot away."""
  user = require_user(request, "Please log in.")
  head_shots.remove(user["id"])
  return {"user": user_for_token(request.cookies.get(SESSION_COOKIE))}


class PasswordChangeRequest(BaseModel):
  # No max_length here: a refused value would be echoed back in the error. change_password checks the lengths.
  current_password: str
  password: str
  password_confirmation: str


@app.post("/account/password")
def account_password(body: PasswordChangeRequest, request: Request):
  """The logged-in member changes their password (the My account page). Other devices are logged out; this
  one stays logged in. No password is logged or returned."""
  user = require_user(request, "Please log in to change your password.")
  try:
    change_password(
      user["id"],
      request.cookies.get(SESSION_COOKIE),
      body.current_password,
      body.password,
      body.password_confirmation,
    )
  except AccountProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"changed": True}


class CloseAccountRequest(BaseModel):
  # No max_length here: a refused value would be echoed back in the error. close_account checks the length.
  password: str


@app.post("/account/close")
def account_close(body: CloseAccountRequest, request: Request, response: Response, background: BackgroundTasks):
  """The logged-in member closes their own account (the My account page), after typing their password. Nothing is
  deleted: the account can no longer log in and gets no emails or texts. Every device is logged out (its sessions
  are removed) and this one's cookie is cleared. One short email says it was closed, and nothing is sent after."""
  user = require_user(request, "Please log in to close your account.")
  try:
    address = close_account(user["id"], body.password)
  except AccountProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  response.delete_cookie(SESSION_COOKIE, path="/")
  if address:
    background.add_task(send_goodbye_email, address)
  return {"closed": True, "user": None}


class TokenRequest(BaseModel):
  token: str


class ForgotRequest(BaseModel):
  email: str


class ResetRequest(BaseModel):
  token: str
  password: str
  password_confirmation: str


@app.post("/account/verify")
def account_verify(body: TokenRequest):
  """The link in the verification email."""
  try:
    verify_email(body.token)
  except AccountProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"verified": True}


@app.post("/account/resend-verification")
def account_resend_verification(request: Request, background: BackgroundTasks):
  """Sends the logged-in visitor another link (not more than one a minute)."""
  user = user_for_token(request.cookies.get(SESSION_COOKIE))
  if user is None:
    raise HTTPException(status_code=401, detail="Please log in first.")
  verification = start_verification(user["id"])
  if verification:
    background.add_task(send_verification_email, *verification)
  return {"sent": True}


@app.post("/account/forgot-password")
def account_forgot_password(body: ForgotRequest, background: BackgroundTasks):
  """Emails a reset link if the address has an account. The answer is the same either way, and the email is
  sent after answering, so neither the words nor the time say whether the address has an account."""
  reset = start_password_reset(body.email)
  if reset:
    kind, target, token = reset
    # By email, or by text for an account that logs in with its phone.
    background.add_task(send_reset_email if kind == "email" else send_reset_text, target, token)
  return {"sent": True}


@app.post("/account/reset-password")
def account_reset_password(body: ResetRequest):
  try:
    reset_password(body.token, body.password, body.password_confirmation)
  except AccountProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"reset": True}


class NoteRequest(BaseModel):
  item_type: Literal["bible_verse", "commentary", "devotional"]
  source_code: str
  book_number: int | None = None
  chapter: int | None = None
  verse: int | None = None
  section: int | None = None
  unit: int | None = None
  # What the visitor wrote, as the editor (Quill) makes it: a little HTML, cleaned before it is kept.
  body: str


def require_user(request: Request, detail: str = "Please log in to use notes.") -> dict:
  user = user_for_token(request.cookies.get(SESSION_COOKIE))
  if user is None:
    raise HTTPException(status_code=401, detail=detail)
  return user


@app.post("/notes")
def notes_create(body: NoteRequest, request: Request):
  """Saves a note for the logged-in visitor."""
  user = require_user(request)
  try:
    return {"note": create_note(user["id"], **body.model_dump())}
  except NoteProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.get("/notes")
def notes_list(
  request: Request,
  item_type: Literal["bible_verse", "commentary", "devotional", "map"] | None = None,
  source_code: str | None = None,
  book_number: int | None = None,
  chapter: int | None = None,
  verse: int | None = None,
  section: int | None = None,
  unit: int | None = None,
  query: str | None = Query(default=None, max_length=200),
  page: int = 1,
  per_page: int = 200,
):
  """One page of the logged-in visitor's own notes, newest first, with the total that match. Narrow it by
  kind (item_type), by item (the place as well) and by words in the text (query)."""
  user = require_user(request)
  try:
    return list_notes(user["id"], item_type, source_code, book_number, chapter, verse, section, unit, query, page, per_page)
  except NoteProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


class NoteTextRequest(BaseModel):
  body: str


@app.put("/notes/{note_id}")
def notes_update(note_id: int, body: NoteTextRequest, request: Request):
  """Changes the text of one of the logged-in visitor's own notes."""
  user = require_user(request)
  try:
    return {"note": update_note(user["id"], note_id, body.body)}
  except NoteProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.delete("/notes/{note_id}")
def notes_delete(note_id: int, request: Request):
  user = require_user(request)
  try:
    delete_note(user["id"], note_id)
  except NoteProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"deleted": True}


def maps_account(request: Request) -> dict:
  """The logged-in account, if an administrator allowed it notes, pins and routes on the maps (use_maps); else
  401 or 403."""
  user = require_user(request, "Please log in to add notes, pins and routes to maps.")
  if not user["use_maps"]:
    raise HTTPException(status_code=403, detail="Your account cannot add notes, pins and routes to maps.")
  return user


class MapMarkRequest(BaseModel):
  # note, pin or route (only when adding one: a change keeps the kind).
  kind: Literal["note", "pin", "route"] = "note"
  # A pin's place, from 0 to 1 across and down the map.
  x: float | None = None
  y: float | None = None
  # A route's points, [[x, y], ...], each from 0 to 1.
  points: list[list[float]] | None = Field(default=None, max_length=2000)
  name: str = Field(default="", max_length=1000)
  colour: str | None = Field(default=None, max_length=20)
  body: str = Field(default="", max_length=20000)
  # The email addresses of the members it is shared with (each another member allowed the maps); they see it
  # read-only with the author's name. Left out (null), a change keeps who it is shared with.
  shared_with: list[str] | None = Field(default=None, max_length=50)


@app.get("/maps/{map_id}/marks")
def map_marks_list(map_id: str, request: Request):
  """The logged-in member's own notes, pins and routes on a map, then those other members shared with them
  (read-only, with their names). Only members allowed the maps get any."""
  user = maps_account(request)
  try:
    return {"marks": list_marks(user["id"], map_id)}
  except MarkProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.post("/maps/{map_id}/marks")
def map_marks_create(map_id: str, body: MapMarkRequest, request: Request):
  user = maps_account(request)
  try:
    return {"mark": create_mark(user["id"], map_id, body.kind, body.model_dump())}
  except MarkProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.put("/map-marks/{mark_id}")
def map_marks_update(mark_id: int, body: MapMarkRequest, request: Request):
  """Changes one of the member's own marks; another member's is 404."""
  user = maps_account(request)
  try:
    return {"mark": update_mark(user["id"], mark_id, body.model_dump())}
  except MarkProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.delete("/map-marks/{mark_id}")
def map_marks_delete(mark_id: int, request: Request):
  user = maps_account(request)
  try:
    delete_mark(user["id"], mark_id)
  except MarkProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"deleted": True}


class ConversationPostRequest(BaseModel):
  title: str = Field(max_length=1000)
  # Which board the new post goes on (a post never moves, so a change ignores it).
  board: str = Field(default="conversations", max_length=40)
  # What the member wrote, as the editor (Quill) makes it: a little HTML, cleaned before it is kept.
  body: str
  # The Prayer Wall choices (refused on Conversations): no name shown; only the author sees it; email it to the
  # prayer list (not with private).
  is_anonymous: bool = False
  is_private: bool = False
  email_to_prayer_list: bool = False
  # Conversations only (refused on the Prayer Wall): email each new reply by someone else to the author.
  email_replies: bool = False
  # Prayer Wall: "Email <group>" ("group") or "Email <group> leader" ("leader") for a group the member is in; sent
  # at once and makes the request private.
  share_with: str | None = Field(default=None, max_length=10)
  share_group_id: int | None = None
  # Conversations: a post to one member (direct_posts.py) instead of everyone; ignored on a change (it never moves).
  recipient_id: int | None = None


def conversations_account(request: Request) -> dict:
  """The logged-in account, if an administrator allowed it Conversations (use_conversations); else 401 or 403."""
  user = require_user(request, "Please log in to use Conversations.")
  if not user["use_conversations"]:
    raise HTTPException(status_code=403, detail="Your account cannot use Conversations.")
  return user


@app.get("/conversations/members")
def conversations_members(request: Request):
  """Who the member may send a post to (by name only): the others allowed to use Conversations."""
  user = conversations_account(request)
  return {"members": direct_posts.members(user["id"])}


def _direct_call(action):
  try:
    return action()
  except direct_posts.DirectPostProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


class MessageAnswerRequest(BaseModel):
  accept: bool


class MessageTokenAnswerRequest(BaseModel):
  token: str = Field(max_length=200)
  accept: bool


@app.get("/message-requests")
def message_requests(request: Request):
  """The logged-in member's waiting requests from people who would like to send them posts."""
  user = require_user(request, "Please log in.")
  return {"requests": direct_posts.requests_for(user["id"])}


@app.get("/message-permissions")
def message_permissions(request: Request):
  """Everyone who has asked to send the member posts, with the member's answer (My account)."""
  user = require_user(request, "Please log in.")
  return {"permissions": direct_posts.permissions_for(user["id"])}


@app.put("/message-permissions/{sender_id}")
def message_permission_answer(sender_id: int, body: MessageAnswerRequest, request: Request):
  """Accepts or declines posts from one sender, or changes the answer."""
  user = require_user(request, "Please log in.")
  return {"permission": _direct_call(lambda: direct_posts.answer(user["id"], sender_id, body.accept))}


@app.get("/message-request")
def message_request_by_link(token: str = ""):
  """The request a link in an email or text answers (no login needed: the link is the member's)."""
  return {"request": _direct_call(lambda: direct_posts.request_by_token(token))}


@app.post("/message-request")
def message_request_answer_by_link(body: MessageTokenAnswerRequest):
  return {"permission": _direct_call(lambda: direct_posts.answer_by_token(body.token, body.accept))}


@app.get("/conversations")
def conversations_list(
  request: Request,
  query: str | None = Query(default=None, max_length=200),
  mine: bool = False,
  page: int = 1,
  per_page: int = 10,
  board: str = Query(default="conversations", max_length=40),
):
  """One page of every member's posts on one board ("conversations", or "prayer" for the Prayer Wall), newest
  first, with the total that match; a post shows only on its own board. query keeps the posts with every word in the title, the text or
  the author's name; mine keeps the member's own.

  Anyone may read, with no login (the owner's choice, 2026-11-14); only a logged-in account with
  use_conversations may write, and only it sees its own posts as is_mine. can_post tells the page which."""
  user = user_for_token(request.cookies.get(SESSION_COOKIE))
  member = user if user is not None and user["use_conversations"] else None
  if mine and member is None:
    # "My posts" means nothing to a reader who cannot post.
    conversations_account(request)
  try:
    result = list_posts(member["id"] if member else 0, query, mine, page, per_page, board)
  except ConversationProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {**result, "can_post": member is not None}


@app.get("/my-groups")
def my_groups_list(request: Request):
  """The groups the logged-in member is in, for the Prayer Wall's "Email <group>" choices."""
  user = require_user(request, "Please log in.")
  return {"groups": my_groups(user["id"])}


@app.post("/conversations")
def conversations_create(body: ConversationPostRequest, request: Request, background: BackgroundTasks):
  user = conversations_account(request)
  try:
    post = create_post(
      user["id"], body.title, body.body, body.board, body.is_anonymous, body.is_private, body.email_to_prayer_list,
      body.email_replies, body.share_with, body.share_group_id, body.recipient_id,
    )
  except ConversationProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  # A request for a group or its leader goes at once, after the answer (the page never waits for the mail server).
  if share_is_due(post["id"]):
    background.add_task(send_shared_request, post["id"])
  if post["recipient"]:
    # A post to one member: the first time, their request to accept or decline; once accepted, a note it came.
    background.add_task(direct_posts.notify_post, post["id"])
  else:
    # Accounts with Get Conversation Posts are emailed a new Conversations post (never a Prayer Wall one).
    background.add_task(send_new_post_emails, post["id"])
  return {"post": post}


@app.put("/conversations/{post_id}")
def conversations_update(post_id: int, body: ConversationPostRequest, request: Request, background: BackgroundTasks):
  """Changes one of the member's own posts; anyone else's is "not found". Choosing a group or its leader that it
  was not emailed to before emails it."""
  user = conversations_account(request)
  try:
    post = update_post(
      user["id"], post_id, body.title, body.body, body.is_anonymous, body.is_private, body.email_to_prayer_list,
      body.email_replies, body.share_with, body.share_group_id,
    )
  except ConversationProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  if share_is_due(post["id"]):
    background.add_task(send_shared_request, post["id"])
  return {"post": post}


class AnsweredRequest(BaseModel):
  answered: bool


@app.put("/conversations/{post_id}/answered")
def conversations_answered(post_id: int, body: AnsweredRequest, request: Request):
  """Marks one of the member's own Prayer Wall requests answered or not (a checkbox on the post, no editing)."""
  user = conversations_account(request)
  try:
    return {"post": set_answered(user["id"], post_id, body.answered)}
  except ConversationProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.delete("/conversations/{post_id}")
def conversations_delete(post_id: int, request: Request):
  user = conversations_account(request)
  try:
    delete_post(user["id"], post_id)
  except ConversationProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"deleted": True}


class ConversationReplyRequest(BaseModel):
  # What the member wrote, as the editor (Quill) makes it: a little HTML, cleaned before it is kept.
  body: str


@app.post("/conversations/{post_id}/replies")
def conversations_reply(post_id: int, body: ConversationReplyRequest, request: Request, background: BackgroundTasks):
  """Adds the member's reply to any post. If the post's author asked for replies by email, it is sent after
  answering (so a slow mail server never holds up the page)."""
  user = conversations_account(request)
  try:
    reply = create_reply(user["id"], post_id, body.body)
  except ConversationProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  background.add_task(send_reply_email, reply["id"])
  background.add_task(send_new_reply_emails, reply["id"])
  # On a post to one member, the other of the two is told (direct_posts.py).
  background.add_task(direct_posts.notify_reply, reply["id"])
  return {"reply": reply}


@app.put("/conversations/replies/{reply_id}")
def conversations_update_reply(reply_id: int, body: ConversationReplyRequest, request: Request):
  """Changes one of the member's own replies; anyone else's is "not found"."""
  user = conversations_account(request)
  try:
    return {"reply": update_reply(user["id"], reply_id, body.body)}
  except ConversationProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.delete("/conversations/replies/{reply_id}")
def conversations_delete_reply(reply_id: int, request: Request):
  user = conversations_account(request)
  try:
    delete_reply(user["id"], reply_id)
  except ConversationProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"deleted": True}


class PlaylistRequest(BaseModel):
  name: str = Field(max_length=1000)
  # The songs in the order they play, by id.
  song_ids: list[str] = Field(max_length=1000)


class ListSaveRequest(BaseModel):
  # A new list's name (when list_id is not given), or the list to add to.
  name: str = Field(default="", max_length=500)
  list_id: int | None = None
  # The ticked entries as the search showed them: kind, title, source, text and target (where to open it).
  items: list[dict] = Field(default_factory=list, max_length=200)


class ListRenameRequest(BaseModel):
  name: str = Field(max_length=500)


def _lists_call(work):
  try:
    return work()
  except saved_lists.ListProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.get("/lists")
def lists_index(request: Request):
  """The logged-in member's lists (My lists), most recently changed first, with how many entries each holds."""
  user = require_user(request, "Please log in to use lists.")
  return {"lists": saved_lists.list_lists(user["id"])}


# Export, import and sharing of My lists (2026-11-19). These come before /lists/{list_id}, whose number would not
# match "export".
IMPORT_BYTES = 20_000_000  # the owner's choice; nginx allows the same for this address (deploy/nginx)


class ListShareRequest(BaseModel):
  shared: bool


@app.get("/lists/export")
def lists_export(request: Request, list_id: int | None = None, playlist_id: int | None = None):
  """The member's lists and playlists (or one list, list_id, or one playlist, playlist_id) as a JSON file to download;
  Import on My lists reads it back."""
  user = require_user(request, "Please log in to use lists.")
  document = _lists_call(lambda: saved_lists.export_lists(user["id"], list_id, playlist_id))
  name = f"my-{'playlist' if playlist_id is not None else 'lists'}-{date.today().isoformat()}.json"
  return JSONResponse(document, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/lists/import")
async def lists_import(request: Request):
  """Adds the lists of an exported file (the request body is the file's JSON) as new lists."""
  user = await run_in_threadpool(require_user, request, "Please log in to use lists.")
  body = await request.body()
  if len(body) > IMPORT_BYTES:
    raise HTTPException(status_code=413, detail="That file is too large to import (at most 20 MB). Export fewer lists at a time.")
  try:
    document = json.loads(body)
  except ValueError:
    raise HTTPException(status_code=422, detail="That is not a lists file exported from this site.")
  return await run_in_threadpool(_lists_call, lambda: saved_lists.import_lists(user["id"], document))


@app.put("/lists/{list_id}/shared")
def lists_share(list_id: int, body: ListShareRequest, request: Request):
  """Shares one of the member's lists on Public lists, or stops (only accounts allowed share_lists may share)."""
  user = require_user(request, "Please log in to use lists.")
  return {"list": _lists_call(lambda: saved_lists.share_list(user, list_id, body.shared))}


@app.get("/public-lists")
def public_lists_index():
  """Every shared list (Public lists under Members): anyone who can use the site may read them."""
  return {"lists": saved_lists.list_public_lists()}


@app.get("/public-lists/{list_id}")
def public_lists_get(list_id: int):
  return {"list": _lists_call(lambda: saved_lists.get_public_list(list_id))}


@app.post("/public-lists/{list_id}/copy")
def public_lists_copy(list_id: int, request: Request):
  """Copy to My lists: the shared list becomes one of the logged-in member's own."""
  user = require_user(request, "Please log in to copy lists.")
  return {"list": _lists_call(lambda: saved_lists.copy_public_list(user["id"], list_id))}


@app.get("/lists/{list_id}")
def lists_get(list_id: int, request: Request):
  user = require_user(request, "Please log in to use lists.")
  return {"list": _lists_call(lambda: saved_lists.get_list(user["id"], list_id))}


@app.post("/lists")
def lists_save(body: ListSaveRequest, request: Request):
  """Saves ticked search results into a new list, or adds them to one of the member's lists."""
  user = require_user(request, "Please log in to use lists.")
  return _lists_call(lambda: saved_lists.save_items(user["id"], body.list_id, body.name, body.items))


@app.put("/lists/{list_id}")
def lists_rename(list_id: int, body: ListRenameRequest, request: Request):
  user = require_user(request, "Please log in to use lists.")
  return {"list": _lists_call(lambda: saved_lists.rename_list(user["id"], list_id, body.name))}


@app.delete("/lists/{list_id}")
def lists_delete(list_id: int, request: Request):
  user = require_user(request, "Please log in to use lists.")
  _lists_call(lambda: saved_lists.delete_list(user["id"], list_id))
  return {"deleted": True}


@app.delete("/lists/{list_id}/items/{item_id}")
def lists_remove_item(list_id: int, item_id: int, request: Request):
  user = require_user(request, "Please log in to use lists.")
  return {"list": _lists_call(lambda: saved_lists.remove_item(user["id"], list_id, item_id))}


@app.post("/lists/{list_id}/note")
def lists_copy_to_note(list_id: int, request: Request):
  """Copy to notes: one note holding the whole list, on its first verse (or other entry that can carry a note)."""
  user = require_user(request, "Please log in to use lists.")
  return {"note": _lists_call(lambda: saved_lists.copy_to_note(user["id"], list_id))}


@app.get("/playlists")
def playlists_list(request: Request):
  """The logged-in visitor's own playlists by name, each with its published songs in order."""
  user = require_user(request, "Please log in to use playlists.")
  return {"playlists": list_playlists(user["id"])}


@app.post("/playlists")
def playlists_save(body: PlaylistRequest, request: Request):
  """Saves songs as a playlist of the logged-in visitor; a name already used (in any case) is replaced."""
  user = require_user(request, "Please log in to use playlists.")
  try:
    playlist, replaced = save_playlist(user["id"], body.name, body.song_ids)
  except PlaylistProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"playlist": playlist, "replaced": replaced}


@app.delete("/playlists/{playlist_id}")
def playlists_delete(playlist_id: int, request: Request):
  user = require_user(request, "Please log in to use playlists.")
  try:
    delete_playlist(user["id"], playlist_id)
  except PlaylistProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"deleted": True}


def _playlists_call(work):
  try:
    return work()
  except PlaylistProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.put("/playlists/{playlist_id}/shared")
def playlists_share(playlist_id: int, body: ListShareRequest, request: Request):
  """Shares one of the visitor's playlists on Public lists, or stops (only accounts allowed share_lists may share)."""
  user = require_user(request, "Please log in to use playlists.")
  return {"playlist": _playlists_call(lambda: share_playlist(user, playlist_id, body.shared))}


@app.get("/public-playlists")
def public_playlists_index():
  """Every shared playlist (on Public lists under Members): anyone who can use the site may see and play them."""
  return {"playlists": list_public_playlists()}


@app.get("/public-playlists/{playlist_id}")
def public_playlists_get(playlist_id: int):
  return {"playlist": _playlists_call(lambda: get_public_playlist(playlist_id))}


@app.post("/public-playlists/{playlist_id}/copy")
def public_playlists_copy(playlist_id: int, request: Request):
  """Copy to my playlists: the shared playlist becomes one of the logged-in visitor's own."""
  user = require_user(request, "Please log in to copy playlists.")
  return {"playlist": _playlists_call(lambda: copy_public_playlist(user["id"], playlist_id))}


class SubscriptionRequest(BaseModel):
  # The time of day, such as "07:00", in the visitor's own time zone (an IANA name such as America/Chicago).
  send_time: str
  timezone: str
  # For a devotional with chapters: the chapter to start with (the first when not given).
  start_section: int | None = None
  start_unit: int | None = None


@app.get("/devotional-subscriptions")
def subscriptions_list(request: Request):
  """The devotionals the logged-in visitor gets by email each day."""
  user = require_user(request)
  return {"subscriptions": list_subscriptions(user["id"])}


@app.put("/devotional-subscriptions/{devotional_id}")
def subscriptions_save(devotional_id: str, body: SubscriptionRequest, request: Request):
  """Starts the daily email of a devotional, or changes its time (needs a confirmed email address)."""
  user = require_user(request)
  try:
    return {
      "subscription": save_subscription(
        user["id"], devotional_id, body.send_time, body.timezone, body.start_section, body.start_unit
      )
    }
  except SubscriptionProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.delete("/devotional-subscriptions/{devotional_id}")
def subscriptions_delete(devotional_id: str, request: Request):
  user = require_user(request)
  try:
    delete_subscription(user["id"], devotional_id)
  except SubscriptionProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"deleted": True}


class PrayerListSubscriptionRequest(BaseModel):
  # The day of the week (0 Monday to 6 Sunday) and time of day, such as "07:00", in the visitor's own time zone
  # (an IANA name such as America/Chicago).
  send_weekday: int = 0
  send_time: str
  timezone: str


@app.get("/prayer-list-subscription")
def prayer_list_get(request: Request):
  """Whether the logged-in visitor gets the weekly prayer list email, and when (null when not)."""
  user = require_user(request, "Please log in to get the prayer list by email.")
  return {"subscription": prayer_list.get_subscription(user["id"])}


@app.put("/prayer-list-subscription")
def prayer_list_save(body: PrayerListSubscriptionRequest, request: Request):
  """Starts the weekly prayer list email, or changes its day and time (needs a confirmed email address)."""
  user = require_user(request, "Please log in to get the prayer list by email.")
  try:
    return {"subscription": prayer_list.save_subscription(user["id"], body.send_weekday, body.send_time, body.timezone)}
  except SubscriptionProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.delete("/prayer-list-subscription")
def prayer_list_delete(request: Request):
  user = require_user(request, "Please log in to get the prayer list by email.")
  try:
    prayer_list.delete_subscription(user["id"])
  except SubscriptionProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  return {"deleted": True}


@app.post("/subscriptions/unsubscribe")
def subscriptions_unsubscribe(token: str = Query(max_length=100)):
  """The link in every devotional email: stops that one subscription, with no login. Mail programs call it
  too (one-click unsubscribe), which is why the token is in the address."""
  try:
    stopped = unsubscribe(token)
    # devotional: what was stopped (its name); message: the sentence the stop page shows.
    return {"devotional": stopped["name"], "message": stopped["message"]}
  except SubscriptionProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))

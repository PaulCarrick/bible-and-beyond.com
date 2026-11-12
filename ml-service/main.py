import logging
import os
from typing import Literal

import psycopg
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from accounts import (
  AccountProblem,
  SESSION_DAYS,
  create_account,
  log_in,
  log_out,
  reset_password,
  send_reset_email,
  send_verification_email,
  start_password_reset,
  start_verification,
  user_for_token,
  verify_email,
)
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
from context import get_chapter, get_context, get_parallel, get_related
from subscriptions import (
  SubscriptionProblem,
  delete_subscription,
  list_subscriptions,
  save_subscription,
  unsubscribe_with_token,
)
from conversations import ConversationProblem, create_post, delete_post, list_posts, update_post
from notes import NoteProblem, create_note, delete_note, list_notes, update_note
from playlists import PlaylistProblem, delete_playlist, list_playlists, save_playlist
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
from site_settings import get_public_settings, get_settings

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
  kind: Literal["bible", "commentary", "devotional", "book", "music"] | None = None,
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
  """The site title and copyright line that the pages show. Nothing private is ever in this answer."""
  return get_public_settings()


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
  email: str
  password: str
  password_confirmation: str
  first_name: str = ""
  last_name: str = ""
  phone: str = ""


class LoginRequest(BaseModel):
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


@app.post("/account/register")
def account_register(body: RegisterRequest, request: Request, response: Response, background: BackgroundTasks):
  """Makes an account, emails a link to confirm the address, and logs the visitor in."""
  try:
    created = create_account(
      body.email, body.password, body.password_confirmation, body.first_name, body.last_name, body.phone
    )
    user, token = log_in(body.email, body.password)
  except AccountProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))
  verification = start_verification(created["id"])
  if verification:
    background.add_task(send_verification_email, *verification)
  start_session(response, request, token)
  return {"user": user}


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
    background.add_task(send_reset_email, *reset)
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
  item_type: Literal["bible_verse", "commentary", "devotional"] | None = None,
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


class ConversationPostRequest(BaseModel):
  title: str = Field(max_length=1000)
  # What the member wrote, as the editor (Quill) makes it: a little HTML, cleaned before it is kept.
  body: str


def conversations_account(request: Request) -> dict:
  """The logged-in account, if an administrator allowed it Conversations (use_conversations); else 401 or 403."""
  user = require_user(request, "Please log in to use Conversations.")
  if not user["use_conversations"]:
    raise HTTPException(status_code=403, detail="Your account cannot use Conversations.")
  return user


@app.get("/conversations")
def conversations_list(
  request: Request,
  query: str | None = Query(default=None, max_length=200),
  mine: bool = False,
  page: int = 1,
  per_page: int = 10,
):
  """One page of every member's posts, newest first, with the total that match. query keeps the posts with
  every word in the title, the text or the author's name; mine keeps the member's own."""
  user = conversations_account(request)
  try:
    return list_posts(user["id"], query, mine, page, per_page)
  except ConversationProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.post("/conversations")
def conversations_create(body: ConversationPostRequest, request: Request):
  user = conversations_account(request)
  try:
    return {"post": create_post(user["id"], body.title, body.body)}
  except ConversationProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))


@app.put("/conversations/{post_id}")
def conversations_update(post_id: int, body: ConversationPostRequest, request: Request):
  """Changes one of the member's own posts; anyone else's is "not found"."""
  user = conversations_account(request)
  try:
    return {"post": update_post(user["id"], post_id, body.title, body.body)}
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


class PlaylistRequest(BaseModel):
  name: str = Field(max_length=1000)
  # The songs in the order they play, by id.
  song_ids: list[str] = Field(max_length=1000)


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


@app.post("/subscriptions/unsubscribe")
def subscriptions_unsubscribe(token: str = Query(max_length=100)):
  """The link in every devotional email: stops that one subscription, with no login. Mail programs call it
  too (one-click unsubscribe), which is why the token is in the address."""
  try:
    return {"devotional": unsubscribe_with_token(token)}
  except SubscriptionProblem as problem:
    raise HTTPException(status_code=problem.status_code, detail=str(problem))

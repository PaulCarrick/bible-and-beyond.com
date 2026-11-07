import logging
import os
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
from context import get_chapter, get_context, get_parallel, get_related
from notes import NoteProblem, create_note, delete_note, list_notes, update_note
from original_words import get_lexicon_entry, get_original_words
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

app.add_middleware(
  CORSMiddleware,
  allow_origins=ALLOWED_ORIGINS,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)


class QuestionRequest(BaseModel):
  question: str


class AnswerResponse(BaseModel):
  question: str
  answer: str


@app.get("/health")
def health():
  return {"status": "ok"}


@app.post("/ask", response_model=AnswerResponse)
def ask(request: QuestionRequest):
  return AnswerResponse(
    question=request.question,
    answer="This is a placeholder answer. Real answers are coming soon.",
  )


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
  query: str = Query(min_length=1),
  match_mode: Literal["all", "any", "phrase"] = "all",
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


@app.get("/search-commentaries")
def search_commentary_text(
  query: str = Query(min_length=1),
  match_mode: Literal["all", "any", "phrase"] = "all",
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
  try:
    return search_commentaries(
      query, match_mode, commentary, book_start, book_end, book, page, per_page, sort_by, sort_direction
    )
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


@app.get("/devotional-contents")
def devotional_contents(devotional: str = Query(min_length=1, max_length=60)):
  result = get_devotional_contents(devotional)
  if result is None:
    raise HTTPException(status_code=404, detail="That devotional was not found.")
  return result


@app.get("/devotional-unit")
def devotional_unit(
  devotional: str = Query(min_length=1, max_length=60),
  section: int = Query(ge=1, le=99),
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
    created = create_account(body.email, body.password, body.password_confirmation)
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


def require_user(request: Request) -> dict:
  user = user_for_token(request.cookies.get(SESSION_COOKIE))
  if user is None:
    raise HTTPException(status_code=401, detail="Please log in to use notes.")
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

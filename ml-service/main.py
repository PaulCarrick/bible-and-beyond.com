import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api_bible import API_BIBLES, ApiBibleError, list_copyrights, search_api_bible
from search import FIRST_BOOK_NUMBER, LAST_BOOK_NUMBER, list_books, list_translations, search_verses

# Comma-separated list. The live site calls /api on its own domain, so it needs no entry.
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app = FastAPI(title="Bible and Beyond ML Service")

app.add_middleware(
  CORSMiddleware,
  allow_origins=ALLOWED_ORIGINS,
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

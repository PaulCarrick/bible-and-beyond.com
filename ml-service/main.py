from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from search import FIRST_BOOK_NUMBER, LAST_BOOK_NUMBER, list_books, list_translations, search_verses

app = FastAPI(title="BibleAnswers ML Service")

app.add_middleware(
  CORSMiddleware,
  allow_origins=["http://localhost:5173"],
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
  return list_translations()


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

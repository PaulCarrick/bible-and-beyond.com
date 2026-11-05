from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

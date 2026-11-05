from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_ok():
  response = client.get("/health")

  assert response.status_code == 200
  assert response.json() == {"status": "ok"}


def test_ask_returns_placeholder_answer():
  response = client.post("/ask", json={"question": "Who was Moses?"})

  assert response.status_code == 200
  body = response.json()
  assert body["question"] == "Who was Moses?"
  assert body["answer"] == "This is a placeholder answer. Real answers are coming soon."


def test_ask_without_question_is_rejected():
  response = client.post("/ask", json={})

  assert response.status_code == 422


def test_ask_with_non_string_question_is_rejected():
  response = client.post("/ask", json={"question": 123})

  assert response.status_code == 422

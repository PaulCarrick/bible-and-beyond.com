from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_ok():
  response = client.get("/health")

  assert response.status_code == 200
  assert response.json() == {"status": "ok"}


def test_the_old_placeholder_ask_is_gone():
  assert client.post("/ask", json={"question": "Who was Moses?"}).status_code == 404


def test_a_query_that_runs_too_long_is_stopped_with_a_message(monkeypatch):
  import search

  # A limit of 1 ms stops even a small search.
  monkeypatch.setattr(search, "STATEMENT_TIMEOUT_MILLISECONDS", 1)
  response = client.get("/search-everything", params={"query": "the of and"})
  assert response.status_code == 503
  assert "too long" in response.json()["detail"]

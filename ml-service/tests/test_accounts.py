"""Tests for accounts on the main site. They use the real users tables and empty them before and after."""

import pytest
from fastapi.testclient import TestClient

from accounts import hash_password, password_matches
from main import app
from search import connect

PASSWORD = "correct horse battery"
client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_accounts():
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM user_sessions")
      connection.execute("DELETE FROM users WHERE email LIKE '%@accounts-test.example'")

  clear()
  client.cookies.clear()
  yield
  clear()


def register(email="Ann@Accounts-Test.example", password=PASSWORD, confirmation=PASSWORD):
  return client.post(
    "/account/register", json={"email": email, "password": password, "password_confirmation": confirmation}
  )


def test_a_password_is_hashed_and_checked():
  stored = hash_password(PASSWORD)

  assert PASSWORD not in stored and stored.startswith("scrypt$")
  assert stored != hash_password(PASSWORD)  # a new salt each time
  assert password_matches(PASSWORD, stored)
  assert not password_matches("wrong password!", stored)
  assert not password_matches(PASSWORD, "garbage")


def test_setting_up_an_account_logs_the_visitor_in():
  response = register()

  assert response.status_code == 200
  assert response.json()["user"]["email"] == "ann@accounts-test.example"
  cookie = response.headers["set-cookie"]
  assert "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
  assert client.get("/account/me").json()["user"]["email"] == "ann@accounts-test.example"


def test_the_password_is_not_stored_and_not_returned():
  response = register()

  with connect() as connection:
    stored = connection.execute("SELECT password_hash FROM users WHERE email = 'ann@accounts-test.example'").fetchone()[0]
  assert PASSWORD not in stored and PASSWORD not in response.text


def test_the_session_token_is_stored_only_as_a_hash():
  register()
  token = client.cookies.get("session")

  with connect() as connection:
    hashes = [row[0] for row in connection.execute("SELECT token_hash FROM user_sessions").fetchall()]
  assert token and token not in hashes and len(hashes) == 1


@pytest.mark.parametrize(
  "email, password, confirmation, fragment",
  [
    ("not an email", PASSWORD, PASSWORD, "valid email"),
    ("a@accounts-test.example", "short", "short", "at least 10"),
    ("a@accounts-test.example", "x" * 129, "x" * 129, "at most 128"),
    ("a@accounts-test.example", PASSWORD, PASSWORD + "!", "not the same"),
  ],
)
def test_a_bad_sign_up_is_refused(email, password, confirmation, fragment):
  response = register(email, password, confirmation)

  assert response.status_code == 422 and fragment in response.json()["detail"]
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM users WHERE email LIKE '%@accounts-test.example'").fetchone()[0] == 0


def test_one_address_cannot_have_two_accounts_whatever_its_case():
  assert register("ann@accounts-test.example").status_code == 200

  response = register("ANN@accounts-test.example")

  assert response.status_code == 409 and "already exists" in response.json()["detail"]


def test_logging_in_and_out():
  register()
  client.cookies.clear()
  assert client.get("/account/me").json() == {"user": None}

  assert client.post("/account/login", json={"email": " ANN@accounts-test.example ", "password": PASSWORD}).status_code == 200
  assert client.get("/account/me").json()["user"]["email"] == "ann@accounts-test.example"

  with connect() as connection:
    before = connection.execute("SELECT count(*) FROM user_sessions").fetchone()[0]
  client.post("/account/logout")
  assert client.get("/account/me").json() == {"user": None}
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM user_sessions").fetchone()[0] == before - 1


def test_a_wrong_password_and_an_unknown_address_look_the_same():
  register()
  client.cookies.clear()

  wrong = client.post("/account/login", json={"email": "ann@accounts-test.example", "password": "not the password"})
  unknown = client.post("/account/login", json={"email": "nobody@accounts-test.example", "password": PASSWORD})

  assert wrong.status_code == unknown.status_code == 401
  assert wrong.json() == unknown.json()
  assert client.get("/account/me").json() == {"user": None}


def test_an_expired_session_is_not_accepted():
  register()
  with connect() as connection:
    connection.execute("UPDATE user_sessions SET expires_at = now() - interval '1 minute'")

  assert client.get("/account/me").json() == {"user": None}


def test_a_made_up_cookie_is_not_accepted():
  client.cookies.set("session", "made-up-token")

  assert client.get("/account/me").json() == {"user": None}

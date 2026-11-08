"""Tests for accounts on the main site. They use the real users tables and empty them before and after."""

import re

import pytest
from fastapi.testclient import TestClient

import accounts
from accounts import hash_password, password_matches
from main import app
from search import connect

PASSWORD = "correct horse battery"
client = TestClient(app)


@pytest.fixture(autouse=True)
def sent_mail(monkeypatch):
  """Nothing is emailed: each message that would be sent is collected as (address, subject, text)."""
  messages = []
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: messages.append((address, subject, text)))
  monkeypatch.setenv("SITE_URL", "https://site.example")
  return messages


def link_token(message, name):
  return re.search(rf"\?{name}=([\w-]+)", message[2]).group(1)


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


def test_setting_up_an_account_emails_a_link_and_the_address_starts_unverified(sent_mail):
  response = register()

  assert response.json()["user"]["email_verified"] is False
  assert len(sent_mail) == 1 and sent_mail[0][0] == "ann@accounts-test.example"
  assert "https://site.example/?verify=" in sent_mail[0][2] and PASSWORD not in sent_mail[0][2]


def test_following_the_link_verifies_the_address_once(sent_mail):
  register()
  token = link_token(sent_mail[0], "verify")

  assert client.post("/account/verify", json={"token": token}).status_code == 200
  assert client.get("/account/me").json()["user"]["email_verified"] is True
  again = client.post("/account/verify", json={"token": token})
  assert again.status_code == 400 and "expired or has already been used" in again.json()["detail"]
  assert client.post("/account/verify", json={"token": "made-up"}).status_code == 400


def test_an_old_verification_link_does_not_work(sent_mail):
  register()
  token = link_token(sent_mail[0], "verify")
  with connect() as connection:
    connection.execute("UPDATE account_tokens SET expires_at = now() - interval '1 minute'")

  assert client.post("/account/verify", json={"token": token}).status_code == 400
  assert client.get("/account/me").json()["user"]["email_verified"] is False


def test_another_verification_email_can_be_asked_for_but_not_in_quick_succession(sent_mail):
  register()
  client.post("/account/resend-verification")
  assert len(sent_mail) == 1  # one was sent a moment ago

  with connect() as connection:
    connection.execute("UPDATE account_tokens SET created_at = now() - interval '2 minutes'")
  old_token = link_token(sent_mail[0], "verify")
  client.post("/account/resend-verification")

  assert len(sent_mail) == 2
  assert client.post("/account/verify", json={"token": old_token}).status_code == 400  # the newer link replaced it
  assert client.post("/account/verify", json={"token": link_token(sent_mail[1], "verify")}).status_code == 200


def test_resending_needs_a_login_and_does_nothing_once_verified(sent_mail):
  client.cookies.clear()
  assert client.post("/account/resend-verification").status_code == 401

  register()
  client.post("/account/verify", json={"token": link_token(sent_mail[0], "verify")})
  client.post("/account/resend-verification")
  assert len(sent_mail) == 1


def test_forgotten_password_gives_the_same_answer_whether_or_not_there_is_an_account(sent_mail):
  register()
  sent_mail.clear()

  known = client.post("/account/forgot-password", json={"email": "ANN@accounts-test.example"})
  unknown = client.post("/account/forgot-password", json={"email": "nobody@accounts-test.example"})

  assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
  assert len(sent_mail) == 1 and sent_mail[0][0] == "ann@accounts-test.example"
  assert "reset=" in sent_mail[0][2]


def test_a_new_password_can_be_chosen_with_the_link_and_it_logs_everyone_out(sent_mail):
  register()
  sent_mail.clear()
  client.post("/account/forgot-password", json={"email": "ann@accounts-test.example"})
  token = link_token(sent_mail[0], "reset")

  response = client.post(
    "/account/reset-password",
    json={"token": token, "password": "a brand new password", "password_confirmation": "a brand new password"},
  )

  assert response.status_code == 200
  assert client.get("/account/me").json() == {"user": None}  # the old session is gone
  assert client.post("/account/login", json={"email": "ann@accounts-test.example", "password": PASSWORD}).status_code == 401
  login = client.post("/account/login", json={"email": "ann@accounts-test.example", "password": "a brand new password"})
  assert login.status_code == 200 and login.json()["user"]["email_verified"] is True  # the link proved the address
  assert client.post("/account/reset-password", json={"token": token, "password": "another new password", "password_confirmation": "another new password"}).status_code == 400


def test_a_bad_new_password_does_not_use_up_the_link(sent_mail):
  register()
  sent_mail.clear()
  client.post("/account/forgot-password", json={"email": "ann@accounts-test.example"})
  token = link_token(sent_mail[0], "reset")

  short = client.post("/account/reset-password", json={"token": token, "password": "short", "password_confirmation": "short"})
  mismatch = client.post("/account/reset-password", json={"token": token, "password": "a brand new password", "password_confirmation": "different one here"})

  assert short.status_code == mismatch.status_code == 422
  good = client.post("/account/reset-password", json={"token": token, "password": "a brand new password", "password_confirmation": "a brand new password"})
  assert good.status_code == 200


def test_reset_links_are_short_lived_and_not_interchangeable_with_verify_links(sent_mail):
  register()
  verify_token = link_token(sent_mail[0], "verify")
  sent_mail.clear()
  client.post("/account/forgot-password", json={"email": "ann@accounts-test.example"})
  reset_token = link_token(sent_mail[0], "reset")
  password = {"password": "a brand new password", "password_confirmation": "a brand new password"}

  assert client.post("/account/reset-password", json={"token": verify_token, **password}).status_code == 400
  assert client.post("/account/verify", json={"token": reset_token}).status_code == 400
  with connect() as connection:
    connection.execute("UPDATE account_tokens SET expires_at = now() - interval '1 minute' WHERE purpose = 'reset'")
  assert client.post("/account/reset-password", json={"token": reset_token, **password}).status_code == 400


def test_the_links_are_stored_only_as_hashes(sent_mail):
  register()
  token = link_token(sent_mail[0], "verify")

  # Only this test's account: other accounts in a development database may have links of their own.
  with connect() as connection:
    stored = [
      row[0]
      for row in connection.execute(
        "SELECT t.token_hash FROM account_tokens t JOIN users u ON u.id = t.user_id WHERE u.email = %s",
        ("ann@accounts-test.example",),
      ).fetchall()
    ]
  assert token not in stored and len(stored) == 1


def test_a_failure_to_send_does_not_stop_sign_up(monkeypatch):
  def fail(address, subject, text):
    raise accounts.MailUnavailable("mail server down")

  monkeypatch.setattr(accounts, "send_plain_message", fail)

  assert register().status_code == 200

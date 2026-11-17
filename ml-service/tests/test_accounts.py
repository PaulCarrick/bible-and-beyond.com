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
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text, **options: messages.append((address, subject, text)))
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


def register(email="Ann@Accounts-Test.example", password=PASSWORD, confirmation=PASSWORD, **profile):
  details = {"first_name": "Ann", "last_name": "Lee", **profile}
  return client.post(
    "/account/register",
    json={"email": email, "password": password, "password_confirmation": confirmation, **details},
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
    ("a@accounts-test.example", "short", "short", "at least 8"),
    ("a@accounts-test.example", "x" * 129, "x" * 129, "at most 128"),
    ("a@accounts-test.example", PASSWORD, PASSWORD + "!", "not the same"),
  ],
)
def test_a_bad_sign_up_is_refused(email, password, confirmation, fragment):
  response = register(email, password, confirmation)

  assert response.status_code == 422 and fragment in response.json()["detail"]
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM users WHERE email LIKE '%@accounts-test.example'").fetchone()[0] == 0


def test_the_names_and_phone_are_stored_and_returned():
  response = register(first_name="  Ann ", last_name=" Lee", phone=" +1 (555) 010-0199 ")

  expected = {"first_name": "Ann", "last_name": "Lee", "phone": "+1 (555) 010-0199"}
  assert response.status_code == 200
  assert {key: response.json()["user"][key] for key in expected} == expected
  me = client.get("/account/me").json()["user"]
  assert {key: me[key] for key in expected} == expected
  client.cookies.clear()
  login = client.post("/account/login", json={"email": "ann@accounts-test.example", "password": PASSWORD}).json()["user"]
  assert {key: login[key] for key in expected} == expected


def test_the_phone_is_optional_and_stored_as_empty():
  response = register()

  assert response.status_code == 200 and response.json()["user"]["phone"] == ""
  with connect() as connection:
    assert connection.execute("SELECT phone FROM users WHERE email = 'ann@accounts-test.example'").fetchone()[0] is None


def test_an_older_account_without_names_still_logs_in():
  with connect() as connection:
    connection.execute(
      "INSERT INTO users (email, password_hash) VALUES ('old@accounts-test.example', %s)", (hash_password(PASSWORD),)
    )

  response = client.post("/account/login", json={"email": "old@accounts-test.example", "password": PASSWORD})

  assert response.status_code == 200
  user = response.json()["user"]
  assert (user["first_name"], user["last_name"], user["phone"]) == ("", "", "")


def test_eight_characters_are_enough():
  assert register("seven@accounts-test.example", "1234567", "1234567").status_code == 422
  assert register("eight@accounts-test.example", "12345678", "12345678").status_code == 200


def test_only_the_email_and_password_are_needed():
  response = client.post(
    "/account/register",
    json={"email": "bare@accounts-test.example", "password": PASSWORD, "password_confirmation": PASSWORD, "first_name": "  "},
  )

  assert response.status_code == 200
  user = response.json()["user"]
  assert (user["first_name"], user["last_name"], user["phone"]) == ("", "", "")
  with connect() as connection:
    stored = connection.execute(
      "SELECT first_name, last_name, phone FROM users WHERE email = 'bare@accounts-test.example'"
    ).fetchone()
  assert stored == (None, None, None)


@pytest.mark.parametrize(
  "profile, fragment",
  [
    ({"first_name": "A" * 101}, "at most 100"),
    ({"last_name": "Lee\nBcc: someone"}, "on one line"),
    ({"phone": "5" * 41}, "at most 40"),
    ({"phone": "555\t0199"}, "on one line"),
  ],
)
def test_bad_names_or_phone_are_refused(profile, fragment):
  response = register(**profile)

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


def change_password(current=PASSWORD, password="a brand new password", confirmation="a brand new password", http=client):
  return http.post(
    "/account/password",
    json={"current_password": current, "password": password, "password_confirmation": confirmation},
  )


def test_changing_the_password_needs_a_login():
  register()
  client.cookies.clear()
  assert change_password().status_code == 401


def test_a_wrong_current_password_is_refused_and_nothing_changes():
  register()
  response = change_password(current="not the password")
  assert response.status_code == 422
  assert "current password" in response.json()["detail"]
  assert "not the password" not in response.text and "a brand new password" not in response.text
  client.cookies.clear()
  assert client.post("/account/login", json={"email": "ann@accounts-test.example", "password": PASSWORD}).status_code == 200


@pytest.mark.parametrize(
  "password, confirmation, fragment",
  [("short", "short", "at least 8"), ("a brand new password", "a different password", "not the same")],
)
def test_a_bad_new_password_is_refused(password, confirmation, fragment):
  register()
  response = change_password(password=password, confirmation=confirmation)
  assert response.status_code == 422
  assert fragment in response.json()["detail"]
  client.cookies.clear()
  assert client.post("/account/login", json={"email": "ann@accounts-test.example", "password": PASSWORD}).status_code == 200


def test_the_new_password_works_and_the_old_one_does_not():
  register()
  assert change_password().json() == {"changed": True}
  client.cookies.clear()
  assert client.post("/account/login", json={"email": "ann@accounts-test.example", "password": PASSWORD}).status_code == 401
  assert client.post("/account/login", json={"email": "ann@accounts-test.example", "password": "a brand new password"}).status_code == 200


def test_changing_the_password_logs_out_other_devices_but_not_this_one(sent_mail):
  register()
  other_device = TestClient(app)
  other_device.post("/account/login", json={"email": "ann@accounts-test.example", "password": PASSWORD})
  assert other_device.get("/account/me").json()["user"] is not None
  sent_mail.clear()
  client.post("/account/forgot-password", json={"email": "ann@accounts-test.example"})
  reset_token = link_token(sent_mail[0], "reset")

  assert change_password().status_code == 200

  assert client.get("/account/me").json()["user"]["email"] == "ann@accounts-test.example"
  assert other_device.get("/account/me").json() == {"user": None}
  cancelled = client.post(
    "/account/reset-password",
    json={"token": reset_token, "password": "another new password", "password_confirmation": "another new password"},
  )
  assert cancelled.status_code == 400


# --- closing your own account (the My account page; added 2026-11-17) ----------------------------------------
# First built as a delete; the owner then asked for a flag instead: nothing is deleted, the account cannot log in
# or do anything, and after one goodbye email nothing is emailed or texted to it.


def close_account(password=PASSWORD, browser=None):
  return (browser or client).post("/account/close", json={"password": password})


def test_closing_the_account_needs_a_login():
  register()
  client.cookies.clear()
  assert close_account().status_code == 401
  with connect() as connection:
    assert connection.execute("SELECT disabled_at FROM users WHERE email = 'ann@accounts-test.example'").fetchone()[0] is None


def test_a_wrong_password_closes_nothing():
  register()
  for wrong in ("not the password", "", "x" * 500):
    response = close_account(wrong)
    assert response.status_code == 422 and "password is not right" in response.json()["detail"]
    assert "not the password" not in response.text
  assert client.get("/account/me").json()["user"]["email"] == "ann@accounts-test.example"


def test_a_closed_account_keeps_its_data_but_cannot_log_in_and_gets_one_goodbye_email(sent_mail):
  user = register().json()["user"]
  other_device = TestClient(app)
  other_device.post("/account/login", json={"email": "ann@accounts-test.example", "password": PASSWORD})
  with connect() as connection:
    connection.execute(
      "INSERT INTO verse_subscriptions (user_id, send_time, timezone, unsubscribe_token) VALUES (%s, '07:00', 'UTC', 'goodbye-test-token')",
      (user["id"],),
    )
  sent_mail.clear()

  response = close_account()
  assert response.status_code == 200 and response.json() == {"closed": True, "user": None}
  # This browser's cookie is cleared and every device is logged out.
  assert "session=" in response.headers.get("set-cookie", "") and client.get("/account/me").json() == {"user": None}
  assert other_device.get("/account/me").json() == {"user": None}
  # Nothing is deleted: the account and what goes with it are still there, marked closed.
  with connect() as connection:
    assert connection.execute("SELECT disabled_at IS NOT NULL FROM users WHERE id = %s", (user["id"],)).fetchone()[0] is True
    assert connection.execute("SELECT count(*) FROM verse_subscriptions WHERE user_id = %s", (user["id"],)).fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM user_sessions WHERE user_id = %s", (user["id"],)).fetchone()[0] == 0
  # One goodbye email, and none after it.
  assert len(sent_mail) == 1 and sent_mail[0][0] == "ann@accounts-test.example" and "account was closed" in sent_mail[0][1]
  assert "last email" in sent_mail[0][2] and "/contact" in sent_mail[0][2]
  # Logging in: the right password says it is closed; a wrong one says what it always says.
  answer = client.post("/account/login", json={"email": "ann@accounts-test.example", "password": PASSWORD})
  assert answer.status_code == 403 and "closed" in answer.json()["detail"]
  answer = client.post("/account/login", json={"email": "ann@accounts-test.example", "password": "wrong password"})
  assert answer.status_code == 401 and "closed" not in answer.text
  # No reset link, no verification, no account actions.
  sent_mail.clear()
  assert client.post("/account/forgot-password", json={"email": "ann@accounts-test.example"}).status_code == 200
  assert sent_mail == []
  assert client.post("/account/resend-verification").status_code == 401
  assert close_account().status_code == 401


def test_no_email_or_text_goes_to_a_closed_account(monkeypatch):
  import contact
  import sms

  user = register(phone="555 234 5678", phone_is_cell=True, send_via_sms=True).json()["user"]
  register(email="Bob@Accounts-Test.example")
  with connect() as connection:
    connection.execute("UPDATE users SET disabled_at = now() WHERE id = %s", (user["id"],))
    number = connection.execute("SELECT sms_number FROM users WHERE id = %s", (user["id"],)).fetchone()[0]
  delivered = []

  class FakeServer:
    def __init__(self, *arguments, **keywords):
      pass

    def __enter__(self):
      return self

    def __exit__(self, *arguments):
      return False

    def ehlo(self):
      pass

    def has_extn(self, name):
      return False

    def send_message(self, email, to_addrs=None):
      delivered.append(list(to_addrs) if to_addrs else [email["To"]])

  monkeypatch.setattr(contact.smtplib, "SMTP", FakeServer)
  settings = {"smtp_host": "mail.example", "smtp_port": 25, "smtp_authentication": "none", "from_address": "site@site.example"}

  def email(to):
    message = contact.EmailMessage()
    message["To"] = to
    message["Subject"] = "Hello"
    message.set_content("Hi")
    return message

  # Whichever way it is addressed, the closed account is left out; others still get theirs.
  contact.send_email(settings, email("ann@accounts-test.example"))
  contact.send_email(settings, email("Ann <ANN@accounts-test.example>"))
  contact.send_email(settings, email("leader@site.example"), ["ann@accounts-test.example"])
  contact.send_email(settings, email("leader@site.example"), ["ann@accounts-test.example", "bob@accounts-test.example"])
  assert delivered == [["bob@accounts-test.example"]]
  # Only the goodbye email may pass.
  contact.send_email(settings, email("ann@accounts-test.example"), even_if_closed=True)
  assert delivered[-1] == ["ann@accounts-test.example"]

  # No text either.
  posted = []
  monkeypatch.setattr(sms, "is_configured", lambda: True)
  monkeypatch.setattr(sms, "get_setting", lambda name: "x")
  monkeypatch.setattr(sms.httpx, "post", lambda *arguments, **keywords: posted.append(keywords) or type("R", (), {"status_code": 200})())
  assert number and sms.send_text(number, "Hello") is False and posted == []
  assert sms.send_text("+15550001111", "Hello") is True and len(posted) == 1


# --- accounts that log in with a phone number (added 2026-11-17) ----------------------------------------------
# The phone numbers are 555 test numbers; their accounts are removed by the fixture below.

PHONE = "555 234 5678"


@pytest.fixture
def texts(monkeypatch):
  """Nothing is texted: each text that would be sent is collected as (number, text)."""
  import sms

  sent = []
  monkeypatch.setattr(sms, "is_configured", lambda: True)
  monkeypatch.setattr(sms, "send_text", lambda number, text, media_url=None: sent.append((number, text)) or True)
  yield sent
  with connect() as connection:
    connection.execute("DELETE FROM users WHERE login_phone LIKE '+1555%' AND email IS NULL")


def register_by_phone(phone=PHONE, **profile):
  details = {"first_name": "Pat", "last_name": "Lee", "phone": phone, **profile}
  return client.post("/account/register", json={"email": "", "password": PASSWORD, "password_confirmation": PASSWORD, **details})


def code_in(text):
  return re.search(r"code is (\d{6})", text).group(1)


def test_an_account_can_be_set_up_and_log_in_with_a_phone_number_only(texts):
  response = register_by_phone()
  assert response.status_code == 200
  user = response.json()["user"]
  assert user["email"] is None and user["logs_in_with_phone"] is True and user["phone_verified"] is False
  assert user["phone"] == "+1 (555) 234-5678" and user["send_via_email"] is False
  # The code is texted (and nothing is emailed).
  assert [number for number, _ in texts] == ["+15552345678"] and code_in(texts[0][1])
  client.cookies.clear()
  # The login box takes the number however it is written.
  for typed in ("(555) 234-5678", "5552345678", "+1 555 234 5678", "1-555-234-5678"):
    client.cookies.clear()
    answer = client.post("/account/login", json={"email": typed, "password": PASSWORD})
    assert answer.status_code == 200 and answer.json()["user"]["id"] == user["id"]
  client.cookies.clear()
  wrong = client.post("/account/login", json={"email": PHONE, "password": "not the password"})
  assert wrong.status_code == 401 and wrong.json()["detail"] == "The email address or phone number, or the password, is not right."


@pytest.mark.parametrize(
  "phone, fragment",
  [("", "email address, or a US or Canadian cell phone number"), ("+44 20 7946 0958", "US or Canadian"), ("123", "US or Canadian")],
)
def test_without_an_email_a_us_cell_number_is_needed(texts, phone, fragment):
  response = register_by_phone(phone)
  assert response.status_code == 422 and fragment in response.json()["detail"]


def test_one_account_per_phone_number(texts):
  register_by_phone()
  client.cookies.clear()
  again = register_by_phone("(555) 234-5678")
  assert again.status_code == 409 and "phone number already exists" in again.json()["detail"]


def test_the_texted_code_confirms_the_phone_and_wrong_codes_are_limited(texts):
  user = register_by_phone(send_via_sms=True, phone_is_cell=True).json()["user"]
  code = code_in(texts[0][1])
  texts.clear()
  wrong = str((int(code) + 1) % 1_000_000).zfill(6)
  for _ in range(4):
    answer = client.post("/account/confirm-phone", json={"code": wrong})
    assert answer.status_code == 400 and "not right" in answer.json()["detail"]
  confirmed = client.post("/account/confirm-phone", json={"code": code})
  assert confirmed.status_code == 200 and confirmed.json()["user"]["phone_verified"] is True
  # Texts were chosen at sign-up: the welcome text waits for the confirmed number.
  assert len(texts) == 1 and "texts" in texts[0][1].lower()
  assert client.get("/account/me").json()["user"]["phone_verified"] is True
  with connect() as connection:
    import sms

    assert sms.number_for_user(connection, user["id"]) == "+15552345678"
    # Never by email: the account has no address.
    assert sms.delivery_for_user(connection, user["id"]) == (False, "+15552345678")


def test_five_wrong_codes_end_the_code(texts):
  register_by_phone()
  code = code_in(texts[0][1])
  wrong = str((int(code) + 1) % 1_000_000).zfill(6)
  for _ in range(4):
    client.post("/account/confirm-phone", json={"code": wrong})
  last = client.post("/account/confirm-phone", json={"code": wrong})
  assert "too many times" in last.json()["detail"]
  assert "expired" in client.post("/account/confirm-phone", json={"code": code}).json()["detail"]
  # A new code (a minute after the last; the test moves the old one back) works.
  with connect() as connection:
    connection.execute("UPDATE account_tokens SET created_at = now() - interval '2 minutes' WHERE purpose = 'phone'")
  texts.clear()
  assert client.post("/account/resend-phone-code").status_code == 200
  assert client.post("/account/confirm-phone", json={"code": code_in(texts[0][1])}).json()["user"]["phone_verified"] is True


def test_a_forgotten_password_is_reset_by_a_texted_link(texts, sent_mail):
  user = register_by_phone().json()["user"]
  client.cookies.clear()
  texts.clear()
  assert client.post("/account/forgot-password", json={"email": "555-234-5678"}).json() == {"sent": True}
  assert sent_mail == [] and len(texts) == 1 and texts[0][0] == "+15552345678"
  token = re.search(r"\?reset=([\w-]+)", texts[0][1]).group(1)
  reset = client.post("/account/reset-password", json={"token": token, "password": "a brand new password", "password_confirmation": "a brand new password"})
  assert reset.status_code == 200
  answer = client.post("/account/login", json={"email": PHONE, "password": "a brand new password"})
  assert answer.status_code == 200 and answer.json()["user"]["phone_verified"] is True  # the text proved the number
  # A number nobody logs in with gets nothing, and the answer is the same.
  texts.clear()
  assert client.post("/account/forgot-password", json={"email": "555 999 0000"}).json() == {"sent": True} and texts == []


def test_a_phone_only_account_has_no_email_features_but_the_others_work(texts):
  import subscriptions

  user = register_by_phone().json()["user"]
  with pytest.raises(subscriptions.SubscriptionProblem, match="no email address"):
    subscriptions.save_subscription(user["id"], "spurgeon-morning-evening", "07:00", "UTC")
  # No verification email is asked for, and closing the account sends no goodbye email.
  assert accounts.start_verification(user["id"]) is None
  # A new number on My account is the new login, confirmed again by a new code.
  with connect() as connection:
    connection.execute("UPDATE account_tokens SET created_at = now() - interval '2 minutes' WHERE purpose = 'phone'")
  texts.clear()
  changed = client.put("/account/phone", json={"phone": "555 234 9999", "send_via_email": True}).json()["user"]
  assert changed["phone"] == "+1 (555) 234-9999" and changed["send_via_email"] is False and changed["phone_verified"] is False
  assert [number for number, _ in texts] == ["+15552349999"]
  client.cookies.clear()
  assert client.post("/account/login", json={"email": "555 234 9999", "password": PASSWORD}).status_code == 200
  assert client.post("/account/login", json={"email": PHONE, "password": PASSWORD}).status_code == 401


def test_email_accounts_still_log_in_and_reset_by_email(texts, sent_mail):
  register(phone=PHONE)
  client.cookies.clear()
  # Their phone is not a login.
  assert client.post("/account/login", json={"email": PHONE, "password": PASSWORD}).status_code == 401
  assert client.post("/account/login", json={"email": "ANN@accounts-test.example", "password": PASSWORD}).status_code == 200
  sent_mail.clear()
  client.post("/account/forgot-password", json={"email": "ann@accounts-test.example"})
  assert len(sent_mail) == 1 and texts == []

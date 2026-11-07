"""Tests for the contact form. The email server, Google and drush are faked: nothing is sent."""

import pytest
from fastapi.testclient import TestClient

import contact
from contact import ContactProblem, build_email, check_message, clean_message_html, message_to_text
from main import app

client = TestClient(app)
SETTINGS = {
  "smtp_host": "mail.example.test",
  "smtp_port": 587,
  "smtp_username": "user@example.test",
  "smtp_password": "secret",
  "smtp_authentication": "login",
  "default_domain": "example.test",
  "from_address": "site@example.test",
  "to_address": "owner@example.test",
  "subject": "Contact request",
}
BODY = {"name": "Ann Lee", "email": "ann@example.com", "phone": "", "message": "<p>Hello <strong>there</strong></p>", "recaptcha_token": "token"}


def test_scripts_and_unsafe_links_are_removed_but_formatting_stays():
  cleaned = clean_message_html(
    '<p onclick="x()">Hi <script>alert(1)</script><a href="javascript:alert(1)">bad</a> '
    '<a href="https://example.com/?a=1&b=2">good</a> <em>it</em> <img src=x onerror=y></p>'
  )

  assert "script" not in cleaned and "alert" not in cleaned and "onclick" not in cleaned and "img" not in cleaned
  assert "javascript" not in cleaned
  assert '<a href="https://example.com/?a=1&amp;b=2" rel="noopener noreferrer">good</a>' in cleaned
  assert "<em>it</em>" in cleaned and "bad" in cleaned


def test_plain_text_keeps_lists_and_paragraphs():
  text = message_to_text("<p>One</p><ol><li>a</li><li>b</li></ol><ul><li>c</li></ul><blockquote>q</blockquote>")

  assert text.splitlines()[0] == "One"
  assert "1. a" in text and "2. b" in text and "- c" in text and "q" in text


def test_the_message_is_checked():
  good = check_message(" Ann Lee ", "ann@example.com", " 555 ", "<p>Hi</p>")
  assert good["name"] == "Ann Lee" and good["phone"] == "555" and good["text"] == "Hi"

  for name, email, phone, message, fragment in [
    ("", "ann@example.com", "", "<p>Hi</p>", "full name"),
    ("Ann", "not an email", "", "<p>Hi</p>", "valid email"),
    ("Ann", "ann@example.com\nBcc: x@example.com", "", "<p>Hi</p>", "one line"),
    ("Ann\r\nBcc: x@example.com", "ann@example.com", "", "<p>Hi</p>", "one line"),
    ("Ann", "ann@example.com", "1" * 41, "<p>Hi</p>", "phone"),
    ("Ann", "ann@example.com", "", "<p><br></p>", "enter a message"),
    ("Ann", "ann@example.com", "", "<p>" + "x" * 5001 + "</p>", "5000"),
  ]:
    with pytest.raises(ContactProblem, match=fragment):
      check_message(name, email, phone, message)


def test_the_email_goes_to_the_owner_and_replies_to_the_visitor():
  values = check_message("Ann Lee", "ann@example.com", "555", "<p>Hello</p>")
  email = build_email(SETTINGS, values)

  assert email["To"] == "owner@example.test" and email["From"] == "site@example.test"
  assert email["Subject"] == "Contact request"
  assert "ann@example.com" in email["Reply-To"]
  body = email.get_body(("plain",)).get_content()
  assert "Name: Ann Lee" in body and "Phone: 555" in body and "Hello" in body


@pytest.fixture
def fakes(monkeypatch):
  sent = []
  monkeypatch.setenv("RECAPTCHA_SITE_KEY", "site")
  monkeypatch.setenv("RECAPTCHA_SECRET_KEY", "secret")
  monkeypatch.setattr(contact, "load_mail_settings", lambda: SETTINGS)
  monkeypatch.setattr(contact, "send_email", lambda settings, email: sent.append(email))

  class Response:
    def __init__(self, state):
      self.state = state

    def raise_for_status(self):
      pass

    def json(self):
      return self.state

  state = {"success": True, "action": "contact", "score": 0.9}
  monkeypatch.setattr(contact.httpx, "post", lambda url, data, timeout: Response(state))
  return sent, state


def test_a_good_message_is_sent(fakes):
  sent, _ = fakes

  response = client.post("/contact", json=BODY)

  assert response.status_code == 200 and response.json() == {"sent": True}
  assert len(sent) == 1


def test_nothing_is_sent_when_the_robot_check_fails_or_is_missing(fakes):
  sent, state = fakes

  assert client.post("/contact", json={**BODY, "recaptcha_token": ""}).status_code == 400
  for change in ({"success": False}, {"score": 0.1}, {"action": "login"}, {"score": None}):
    state.update({"success": True, "action": "contact", "score": 0.9})
    state.update(change)
    assert client.post("/contact", json=BODY).status_code == 400
  assert sent == []


def test_the_lowest_score_that_passes_can_be_set(fakes, monkeypatch):
  sent, state = fakes
  state["score"] = 0.3

  assert client.post("/contact", json=BODY).status_code == 400
  monkeypatch.setenv("RECAPTCHA_MINIMUM_SCORE", "0.2")
  assert client.post("/contact", json=BODY).status_code == 200
  assert len(sent) == 1


def test_a_bad_message_is_refused_before_google_is_asked(fakes, monkeypatch):
  def fail(*arguments, **keywords):
    raise AssertionError("Google should not be asked")

  monkeypatch.setattr(contact.httpx, "post", fail)

  assert client.post("/contact", json={**BODY, "email": "nope"}).status_code == 422


def test_the_form_is_unavailable_without_keys(monkeypatch):
  monkeypatch.delenv("RECAPTCHA_SITE_KEY", raising=False)
  monkeypatch.delenv("RECAPTCHA_SECRET_KEY", raising=False)

  assert client.get("/contact-settings").json() == {"recaptcha_site_key": ""}
  assert client.post("/contact", json=BODY).status_code == 503


def test_a_mail_failure_tells_the_visitor_nothing_private(fakes, monkeypatch):
  def fail(settings, email):
    raise contact.MailUnavailable("the message could not be sent: SMTPAuthenticationError")

  monkeypatch.setattr(contact, "send_email", fail)

  response = client.post("/contact", json=BODY)

  assert response.status_code == 502
  assert "SMTP" not in response.text and "secret" not in response.text


def test_the_email_is_sent_over_a_secure_connection_with_the_chosen_sign_in(monkeypatch):
  calls = []

  class FakeConnection:
    def __init__(self, host, port, timeout=None, context=None):
      calls.append(("connect", host, port))
      self.esmtp_features = {}

    def __enter__(self):
      return self

    def __exit__(self, *arguments):
      return False

    def ehlo(self):
      pass

    def has_extn(self, name):
      return name == "starttls"

    def starttls(self, context=None):
      calls.append(("starttls",))

    def login(self, username, password):
      calls.append(("login", username, password, self.esmtp_features.get("auth")))

    def send_message(self, email):
      calls.append(("send", email["To"]))

  monkeypatch.setattr(contact.smtplib, "SMTP", FakeConnection)
  values = check_message("Ann", "ann@example.com", "", "<p>Hi</p>")

  contact.send_email(SETTINGS, build_email(SETTINGS, values))

  assert calls == [
    ("connect", "mail.example.test", 587),
    ("starttls",),
    ("login", "user@example.test", "secret", "LOGIN"),
    ("send", "owner@example.test"),
  ]


def test_no_sign_in_is_tried_when_the_server_needs_none(monkeypatch):
  calls = []

  class FakeConnection:
    def __init__(self, *arguments, **keywords):
      self.esmtp_features = {}

    def __enter__(self):
      return self

    def __exit__(self, *arguments):
      return False

    def ehlo(self):
      pass

    def has_extn(self, name):
      return False

    def login(self, *arguments):
      calls.append("login")

    def send_message(self, email):
      calls.append("send")

  monkeypatch.setattr(contact.smtplib, "SMTP", FakeConnection)
  values = check_message("Ann", "ann@example.com", "", "<p>Hi</p>")

  contact.send_email({**SETTINGS, "smtp_authentication": "none"}, build_email(SETTINGS, values))

  assert calls == ["send"]

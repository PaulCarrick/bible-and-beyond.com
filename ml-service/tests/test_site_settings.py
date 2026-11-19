"""Tests for the site title and the copyright line, which an administrator sets in Drupal.

These use the real site_settings table, like the number settings in test_context.py, and empty it
before and after each test.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from search import connect
import main
from site_settings import DEFAULTS, SettingsProblem, get_public_settings, get_settings, save_settings

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_settings.py"
CURRENT_COPYRIGHT = "Copyright © 2026 by Paul Carrick. All Rights Reserved."


@pytest.fixture(autouse=True)
def clean_settings():
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM site_settings")

  clear()
  # The API keeps the Login required answer for a few seconds; each test starts without it.
  main._login_setting["read_at"] = None
  yield
  clear()
  main._login_setting["read_at"] = None


def test_the_defaults_are_what_the_site_showed_before_they_could_be_changed():
  settings = get_settings()

  assert settings["site_title"] == "Bible and Beyond"
  assert settings["copyright_text"] == CURRENT_COPYRIGHT
  assert DEFAULTS["site_title"] == "Bible and Beyond" and DEFAULTS["copyright_text"] == CURRENT_COPYRIGHT


def test_a_saved_title_and_copyright_line_are_used_and_trimmed():
  saved = save_settings({"site_title": "  Scripture & More  ", "copyright_text": " © 2027 Someone Else. Café “quoted”. "})

  assert saved["site_title"] == "Scripture & More"
  assert saved["copyright_text"] == "© 2027 Someone Else. Café “quoted”."
  assert get_settings() == saved


def test_the_copyright_line_can_be_empty_but_the_title_cannot():
  assert save_settings({"copyright_text": ""})["copyright_text"] == ""
  assert save_settings({"copyright_text": "   "})["copyright_text"] == ""

  with pytest.raises(SettingsProblem, match="site title must be from 1 to 60 characters"):
    save_settings({"site_title": "   "})


def test_values_that_are_too_long_or_have_line_breaks_are_refused():
  with pytest.raises(SettingsProblem, match="site title must be from 1 to 60"):
    save_settings({"site_title": "x" * 61})
  with pytest.raises(SettingsProblem, match="copyright text can be at most 300"):
    save_settings({"copyright_text": "x" * 301})
  with pytest.raises(SettingsProblem, match="copyright text must be one line"):
    save_settings({"copyright_text": "first\nsecond"})
  with pytest.raises(SettingsProblem, match="site title must be one line"):
    save_settings({"site_title": "Bible\tand Beyond"})
  assert save_settings({"site_title": "x" * 60})["site_title"] == "x" * 60  # the limit itself is allowed


def test_a_text_that_is_not_text_is_refused():
  for bad in (5, None, ["a"], True):
    with pytest.raises(SettingsProblem, match="site title"):
      save_settings({"site_title": bad})


def test_nothing_is_saved_when_one_value_is_refused():
  save_settings({"site_title": "First", "context_verses_before": 3})

  with pytest.raises(SettingsProblem):
    save_settings({"site_title": "Second", "copyright_text": "x" * 301, "context_verses_before": 9})

  settings = get_settings()
  assert settings["site_title"] == "First" and settings["context_verses_before"] == 3


def test_changing_the_texts_leaves_the_numbers_alone_and_the_other_way_round():
  save_settings({"context_verses_before": 7, "related_verses_limit": 20})
  save_settings({"site_title": "Renamed"})
  save_settings({"context_verses_after": 4})

  settings = get_settings()
  assert (settings["context_verses_before"], settings["context_verses_after"], settings["related_verses_limit"]) == (7, 4, 20)
  assert settings["site_title"] == "Renamed" and settings["copyright_text"] == CURRENT_COPYRIGHT


def test_a_stored_value_that_is_not_allowed_falls_back_to_the_default():
  with connect() as connection:
    connection.execute("INSERT INTO site_settings (key, value) VALUES ('site_title', to_jsonb(''::text))")
    connection.execute("INSERT INTO site_settings (key, value) VALUES ('copyright_text', to_jsonb(42))")

  settings = get_settings()

  assert settings["site_title"] == "Bible and Beyond" and settings["copyright_text"] == CURRENT_COPYRIGHT


def test_the_public_answer_has_the_title_and_the_copyright_line_and_nothing_else():
  save_settings({"site_title": "Shown", "copyright_text": "Mine", "context_verses_before": 9})

  public = {"title": "Shown", "copyright": "Mine", "welcome_html": DEFAULTS["welcome_text"], "login_required": False}
  assert get_public_settings() == public
  # The API adds only the addresses of the uploaded icons (none here).
  assert client.get("/site-settings").json() == {**public, "header_icon": None, "tab_icon": None}


def test_the_api_serves_the_current_values_when_nothing_has_been_saved():
  assert client.get("/site-settings").json() == {
    "title": "Bible and Beyond", "copyright": CURRENT_COPYRIGHT, "welcome_html": DEFAULTS["welcome_text"],
    "login_required": False, "header_icon": None, "tab_icon": None,
  }


def test_the_settings_tool_sets_and_reads_the_texts():
  def run(*arguments):
    completed = subprocess.run([sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True, check=False)
    return completed.returncode, json.loads(completed.stdout)

  status, result = run("set", "--site-title=Daily Bread", "--copyright-text=© 2026 Paul “the author”. All rights reserved.")
  assert status == 0
  assert result["settings"]["site_title"] == "Daily Bread"
  assert result["settings"]["copyright_text"] == "© 2026 Paul “the author”. All rights reserved."
  assert result["text_limits"] == {"site_title": {"min": 1, "max": 60}, "copyright_text": {"min": 0, "max": 300}}

  status, result = run("set", "--copyright-text=")
  assert status == 0 and result["settings"]["copyright_text"] == "" and result["settings"]["site_title"] == "Daily Bread"

  status, result = run("set", "--site-title=")
  assert status == 1 and result["ok"] is False and "from 1 to 60" in result["error"]
  assert run("get")[1]["settings"]["site_title"] == "Daily Bread"


def test_the_stored_value_is_a_json_string():
  save_settings({"site_title": "Stored"})

  with connect() as connection:
    value = connection.execute("SELECT value FROM site_settings WHERE key = 'site_title'").fetchone()[0]

  assert value == "Stored"


def test_the_welcome_paragraph_is_formatted_and_can_have_links():
  assert get_settings()["welcome_text"].startswith("<p>Bible and Beyond is a free, non-commercial site")

  saved = save_settings({"welcome_text": {"html": '<p>Read <a href="https://example.com/guide">the guide</a>.</p><script>alert(1)</script>'}})

  assert 'href="https://example.com/guide"' in saved["welcome_text"]
  assert "<script" not in saved["welcome_text"] and "alert" not in saved["welcome_text"]
  # From the plain box (no editor): paragraphs.
  assert save_settings({"welcome_text": {"text": "One.\n\nTwo <b>"}})["welcome_text"] == "<p>One.</p><p>Two &lt;b&gt;</p>"
  with pytest.raises(SettingsProblem, match="Please write something in the welcome paragraph"):
    save_settings({"welcome_text": {"html": "<p> </p>"}})


def test_a_welcome_paragraph_saved_as_plain_text_before_the_editor_is_shown_as_a_paragraph():
  with connect() as connection:
    connection.execute("INSERT INTO site_settings (key, value) VALUES ('welcome_text', to_jsonb('Old & plain'::text))")

  assert get_settings()["welcome_text"] == "<p>Old &amp; plain</p>"


def test_login_required_is_off_unless_turned_on():
  assert get_settings()["login_required"] is False

  assert save_settings({"login_required": True})["login_required"] is True
  assert save_settings({"login_required": False})["login_required"] is False
  with pytest.raises(SettingsProblem, match="must be on or off"):
    save_settings({"login_required": 1})


def test_while_login_is_required_a_visitor_gets_only_the_sign_in_pages(monkeypatch):
  # Off: anyone may use the site.
  assert client.get("/books").status_code == 200

  save_settings({"login_required": True})
  main._login_setting["read_at"] = None

  refused = client.get("/books")
  assert refused.status_code == 401
  assert refused.json() == {"detail": "Please log in to use this site.", "login_required": True}
  assert client.get("/music").status_code == 401
  # What the sign-in pages and the page frame need still works.
  assert client.get("/site-settings").json()["login_required"] is True
  assert client.get("/health").status_code == 200
  assert client.get("/account/me").json() == {"user": None}
  assert client.options("/books", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}).status_code != 401

  # A logged-in visitor uses the site as before.
  monkeypatch.setattr(main, "user_for_token", lambda token: {"id": 1} if token == "good" else None)
  assert client.get("/books", cookies={"session": "good"}).status_code == 200
  assert client.get("/books", cookies={"session": "stale"}).status_code == 401


def test_the_settings_tool_sets_login_required_and_the_welcome_text():
  completed = subprocess.run(
    [sys.executable, str(SCRIPT), "set", "--login-required=yes", '--welcome-html=<p>Hello <a href="https://example.com">there</a>.</p>'],
    capture_output=True, text=True, check=False,
  )
  result = json.loads(completed.stdout)

  assert completed.returncode == 0 and result["settings"]["login_required"] is True
  assert 'Hello <a href="https://example.com"' in result["settings"]["welcome_text"]


def test_while_login_is_required_visitors_cannot_set_up_accounts():
  save_settings({"login_required": True})
  main._login_setting["read_at"] = None

  refused = client.post("/account/register", json={"email": "newcomer@settings-test.example", "password": "a-long-password-1", "password_confirmation": "a-long-password-1"})

  assert refused.status_code == 403
  assert refused.json()["detail"] == "New accounts are set up by the site's administrators. Please ask them for one."
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM users WHERE lower(email) = 'newcomer@settings-test.example'").fetchone()[0] == 0


def test_the_log_in_page_gets_the_administrators_address_only_while_login_is_required(monkeypatch):
  monkeypatch.setattr(main, "administrator_address", lambda: "admin@settings-test.example")
  main._request_address["read_at"] = None
  assert client.get("/account/request-address").json() == {"email": ""}

  save_settings({"login_required": True})
  main._login_setting["read_at"] = None

  assert client.get("/account/request-address").json() == {"email": "admin@settings-test.example"}
  main._request_address["read_at"] = None

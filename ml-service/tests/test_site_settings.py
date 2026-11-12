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
  yield
  clear()


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

  assert get_public_settings() == {"title": "Shown", "copyright": "Mine"}
  # The API adds only the addresses of the uploaded icons (none here).
  assert client.get("/site-settings").json() == {"title": "Shown", "copyright": "Mine", "header_icon": None, "tab_icon": None}


def test_the_api_serves_the_current_values_when_nothing_has_been_saved():
  assert client.get("/site-settings").json() == {
    "title": "Bible and Beyond", "copyright": CURRENT_COPYRIGHT, "header_icon": None, "tab_icon": None,
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

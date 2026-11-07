"""Tests for the keys and options of the outside services, set on the Drupal Site settings screen.

Each test uses its own settings file (tests/conftest.py), never the real one.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import contact
import faq
from service_settings import ServiceSettingsProblem, describe, get_setting, save, settings_path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_service_settings.py"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
  for variable in ("GEMINI_API_KEY", "GEMINI_MODEL", "API_BIBLE_KEY", "API_BIBLE_ENDPOINT", "API_BIBLE_MONTHLY_LIMIT",
                   "RECAPTCHA_SITE_KEY", "RECAPTCHA_SECRET_KEY", "RECAPTCHA_MINIMUM_SCORE"):
    monkeypatch.delenv(variable, raising=False)
  monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret-from-env")
  monkeypatch.setenv("RECAPTCHA_SITE_KEY", "site-key-from-env")


def test_before_anything_is_saved_the_env_values_and_defaults_are_used():
  assert get_setting("gemini_api_key") == "gemini-secret-from-env"
  assert get_setting("api_bible_endpoint") == "https://rest.api.bible"
  assert get_setting("recaptcha_minimum_score") == "0.5"

  described = describe()
  assert described["is_saved"] is False
  gemini = described["settings"]["gemini_api_key"]
  assert gemini == {"source": "env", "is_secret": True, "kind": "text", "environment_variable": "GEMINI_API_KEY", "is_set": True}
  assert "gemini-secret-from-env" not in json.dumps(described)
  assert described["settings"]["recaptcha_site_key"]["value"] == "site-key-from-env"
  assert described["settings"]["api_bible_key"]["is_set"] is False


def test_the_first_save_copies_everything_and_then_the_saved_values_win(monkeypatch):
  save({"gemini_models": " gemini-3.6-flash , gemini-flash-latest ", "recaptcha_minimum_score": "0.7", "gemini_api_key": ""}, [])

  assert get_setting("gemini_api_key") == "gemini-secret-from-env"  # an empty key kept the one in use, now saved
  assert get_setting("gemini_models") == "gemini-3.6-flash,gemini-flash-latest"
  assert get_setting("recaptcha_minimum_score") == "0.7"
  assert describe()["settings"]["gemini_api_key"]["source"] == "saved"

  monkeypatch.setenv("GEMINI_API_KEY", "changed-in-env")
  assert get_setting("gemini_api_key") == "gemini-secret-from-env"  # .env no longer counts

  save({"gemini_api_key": "typed-on-the-screen"}, [])
  assert get_setting("gemini_api_key") == "typed-on-the-screen"
  assert faq.is_configured() and contact.get_recaptcha_site_key() == "site-key-from-env"


def test_a_key_can_be_removed():
  save({}, ["gemini_api_key"])

  assert get_setting("gemini_api_key") == ""
  assert faq.is_configured() is False


def test_the_file_is_private():
  save({}, [])

  assert stat.S_IMODE(os.stat(settings_path()).st_mode) == 0o600


@pytest.mark.parametrize(
  "name, value, fragment",
  [
    ("gemini_models", "gemini 3; rm -rf", "model names"),
    ("api_bible_endpoint", "http://rest.api.bible", "https://"),
    ("api_bible_monthly_limit", "9000", "0 to 5000"),
    ("api_bible_monthly_limit", "-1", "0 to 5000"),
    ("recaptcha_minimum_score", "1.5", "0 to 1"),
    ("recaptcha_minimum_score", "nan", "0 to 1"),
    ("recaptcha_site_key", "two\nlines", "one line"),
    ("not_a_setting", "x", "Unknown"),
  ],
)
def test_bad_values_are_refused_and_nothing_is_saved(name, value, fragment):
  with pytest.raises(ServiceSettingsProblem, match=fragment):
    save({name: value}, [])
  assert not settings_path().exists()


def tool_environment():
  """The tool loads ml-service/.env, but never over a variable that is already set: so every key is set
  (empty when the test has none), and the real keys in .env are never read."""
  environment = os.environ.copy()
  for environment_variable in ("GEMINI_API_KEY", "GEMINI_MODEL", "API_BIBLE_KEY", "API_BIBLE_ENDPOINT", "API_BIBLE_MONTHLY_LIMIT",
                               "RECAPTCHA_SITE_KEY", "RECAPTCHA_SECRET_KEY", "RECAPTCHA_MINIMUM_SCORE", "DATABASE_URL"):
    environment.setdefault(environment_variable, "")
  return environment


def run_tool(command, request=None):
  completed = subprocess.run(
    [sys.executable, str(SCRIPT), command],
    input=json.dumps(request) if request is not None else "",
    capture_output=True,
    text=True,
    check=False,
    env=tool_environment(),
  )
  return completed.returncode, json.loads(completed.stdout)


def test_the_tool_never_prints_a_key():
  status, answer = run_tool("set", {"values": {"api_bible_key": "secret-api-bible-key", "api_bible_monthly_limit": "4000"}, "remove": []})
  assert status == 0 and answer["ok"] and answer["settings"]["api_bible_key"] == {
    "source": "saved", "is_secret": True, "kind": "text", "environment_variable": "API_BIBLE_KEY", "is_set": True,
  }
  assert "secret-api-bible-key" not in json.dumps(answer)

  status, answer = run_tool("get")
  assert status == 0 and answer["settings"]["api_bible_monthly_limit"]["value"] == "4000"
  assert "secret-api-bible-key" not in json.dumps(answer) and "gemini-secret-from-env" not in json.dumps(answer)

  status, answer = run_tool("set", {"values": {"recaptcha_minimum_score": "2"}})
  assert status == 1 and "0 to 1" in answer["error"]

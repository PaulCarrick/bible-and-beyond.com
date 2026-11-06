"""Tests for "Show in Context" and the settings behind it. They read the real KJV text in the local database."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from main import app
from search import connect
from site_settings import CONTEXT_LIMIT, DEFAULTS, SettingsProblem, get_settings, save_settings

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_settings.py"

GENESIS, JOHN, REVELATION = 1, 43, 66


@pytest.fixture(autouse=True)
def clean_settings():
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM site_settings")

  clear()
  yield
  clear()


def context(book, chapter, verse, translation="KJV"):
  return client.get(
    "/context", params={"translation": translation, "book": book, "chapter": chapter, "verse": verse}
  )


def references(body):
  return [(entry["chapter"], entry["verse"]) for entry in body["verses"]]


# --- the settings -----------------------------------------------------------------------------


def test_the_defaults_are_five_before_and_ten_after():
  assert get_settings() == {"context_verses_before": 5, "context_verses_after": 10}
  assert DEFAULTS == get_settings()


def test_saved_settings_are_used():
  saved = save_settings({"context_verses_before": 2, "context_verses_after": 7})

  assert saved == {"context_verses_before": 2, "context_verses_after": 7}
  assert get_settings() == saved


def test_changing_one_setting_keeps_the_other():
  save_settings({"context_verses_before": 3, "context_verses_after": 4})

  save_settings({"context_verses_before": 9})

  assert get_settings() == {"context_verses_before": 9, "context_verses_after": 4}


@pytest.mark.parametrize("bad_value", [-1, CONTEXT_LIMIT + 1, "5", 2.5, True, None])
def test_values_that_are_not_allowed_are_rejected_and_nothing_is_saved(bad_value):
  save_settings({"context_verses_before": 3, "context_verses_after": 4})

  with pytest.raises(SettingsProblem, match="whole number"):
    save_settings({"context_verses_before": 8, "context_verses_after": bad_value})

  assert get_settings() == {"context_verses_before": 3, "context_verses_after": 4}


def test_an_unknown_setting_is_rejected():
  with pytest.raises(SettingsProblem, match="Unknown setting"):
    save_settings({"favorite_color": 1})


def test_a_damaged_stored_value_falls_back_to_the_default():
  with connect() as connection:
    connection.execute("INSERT INTO site_settings (key, value) VALUES ('context_verses_before', '\"lots\"')")

  assert get_settings()["context_verses_before"] == DEFAULTS["context_verses_before"]


def test_the_settings_tool_reads_and_writes_json():
  def run(*arguments):
    completed = subprocess.run(
      [sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True, check=False
    )
    return completed.returncode, json.loads(completed.stdout)

  status, result = run("get")
  assert status == 0 and result["settings"] == DEFAULTS and result["context_limit"] == CONTEXT_LIMIT

  status, result = run("set", "--context-verses-before", "6", "--context-verses-after", "12")
  assert status == 0 and result["settings"] == {"context_verses_before": 6, "context_verses_after": 12}

  status, result = run("set", "--context-verses-before", "6", "--context-verses-after", "999")
  assert status == 1 and result["ok"] is False and "0 to 50" in result["error"]
  assert run("get")[1]["settings"]["context_verses_after"] == 12


# --- the context ------------------------------------------------------------------------------


def test_the_verse_sits_in_the_middle_with_the_default_five_before_and_ten_after():
  response = context(JOHN, 3, 16)

  body = response.json()
  assert response.status_code == 200
  assert body["book_name"] == "John" and body["translation"] == "KJV"
  assert references(body) == [(3, number) for number in range(11, 27)]  # 5 before, the verse, 10 after
  targets = [entry for entry in body["verses"] if entry["is_target"]]
  assert [(entry["chapter"], entry["verse"]) for entry in targets] == [(3, 16)]
  assert "God so loved the world" in targets[0]["text"]
  assert (body["verses_before"], body["verses_after"]) == (5, 10)


def test_the_configured_numbers_are_used(monkeypatch):
  monkeypatch.setattr(main, "get_settings", lambda: {"context_verses_before": 1, "context_verses_after": 2})

  body = context(JOHN, 3, 16).json()

  assert references(body) == [(3, 15), (3, 16), (3, 17), (3, 18)]


def test_zero_before_and_after_gives_just_the_verse(monkeypatch):
  monkeypatch.setattr(main, "get_settings", lambda: {"context_verses_before": 0, "context_verses_after": 0})

  assert references(context(JOHN, 3, 16).json()) == [(3, 16)]


def test_the_start_of_a_book_has_nothing_before_it():
  body = context(GENESIS, 1, 1).json()

  assert references(body)[0] == (1, 1)
  assert references(body) == [(1, number) for number in range(1, 12)]  # the verse and 10 after


def test_the_end_of_a_book_has_nothing_after_it_and_does_not_run_into_another_book():
  body = context(REVELATION, 22, 21).json()

  assert references(body) == [(22, number) for number in range(16, 22)]  # 5 before, then the verse
  assert {entry["chapter"] for entry in body["verses"]} == {22}


def test_the_context_crosses_into_the_previous_chapter():
  body = context(GENESIS, 2, 1).json()

  assert references(body)[:6] == [(1, 27), (1, 28), (1, 29), (1, 30), (1, 31), (2, 1)]


def test_the_context_crosses_into_the_next_chapter():
  body = context(GENESIS, 1, 30).json()

  assert (1, 31) in references(body) and (2, 1) in references(body)
  assert references(body)[-1] == (2, 9)  # 1:30 plus 10 more: 1:31 and 2:1 to 2:9


def test_the_translation_code_is_not_case_sensitive():
  assert client.get("/context", params={"translation": "kjv", "book": JOHN, "chapter": 3, "verse": 16}).status_code == 200


def test_another_translation_gives_its_own_text():
  kjv = context(JOHN, 3, 16, "KJV").json()["verses"][5]["text"]
  bsb = context(JOHN, 3, 16, "BSB").json()["verses"][5]["text"]

  assert kjv != bsb


@pytest.mark.parametrize(
  "parameters, status",
  [
    ({"translation": "NOPE", "book": JOHN, "chapter": 3, "verse": 16}, 404),
    ({"translation": "KJV", "book": JOHN, "chapter": 99, "verse": 1}, 404),
    ({"translation": "KJV", "book": JOHN, "chapter": 3, "verse": 999}, 404),
    ({"translation": "NIV", "book": JOHN, "chapter": 3, "verse": 16}, 422),
    ({"translation": "msg", "book": JOHN, "chapter": 3, "verse": 16}, 422),
    ({"translation": "KJV", "book": 0, "chapter": 3, "verse": 16}, 422),
    ({"translation": "KJV", "book": 67, "chapter": 3, "verse": 16}, 422),
    ({"translation": "KJV", "book": JOHN, "chapter": 0, "verse": 16}, 422),
    ({"translation": "KJV", "book": JOHN, "chapter": 3}, 422),
    ({"book": JOHN, "chapter": 3, "verse": 16}, 422),
  ],
)
def test_requests_that_cannot_be_answered_are_refused(parameters, status):
  assert client.get("/context", params=parameters).status_code == status


def test_a_hidden_bible_has_no_context(tmp_path):
  from bible_import.importer import TranslationDetails, import_file
  from bible_import import catalog

  path = tmp_path / "hidden.txt"
  path.write_text("John 3:16\tFor God so loved the world.\n", encoding="utf-8")
  import_file(path, TranslationDetails(code="ZZCTX", name="Hidden Test", license="Public domain"))

  try:
    assert context(JOHN, 3, 16, "ZZCTX").status_code == 404
    catalog.set_published("ZZCTX", True)
    assert context(JOHN, 3, 16, "ZZCTX").status_code == 200
  finally:
    with connect() as connection:
      connection.execute("DELETE FROM translations WHERE code = 'ZZCTX'")


# --- the full chapter -------------------------------------------------------------------------


def chapter(book, chapter_number, verse, translation="KJV"):
  return client.get(
    "/chapter", params={"translation": translation, "book": book, "chapter": chapter_number, "verse": verse}
  )


def test_the_full_chapter_has_every_verse_with_the_chosen_one_marked():
  response = chapter(JOHN, 3, 16)

  body = response.json()
  assert response.status_code == 200
  assert body["book_name"] == "John" and body["translation"] == "KJV"
  assert references(body) == [(3, number) for number in range(1, 37)]  # John 3 has 36 verses
  assert [entry["verse"] for entry in body["verses"] if entry["is_target"]] == [16]
  assert "God so loved the world" in body["verses"][15]["text"]


def test_the_full_chapter_does_not_depend_on_the_context_numbers(monkeypatch):
  monkeypatch.setattr(main, "get_settings", lambda: {"context_verses_before": 0, "context_verses_after": 0})

  assert len(chapter(JOHN, 3, 16).json()["verses"]) == 36


def test_the_chosen_verse_can_be_the_first_or_the_last_of_the_chapter():
  first = chapter(GENESIS, 1, 1).json()
  last = chapter(REVELATION, 22, 21).json()

  assert len(first["verses"]) == 31 and first["verses"][0]["is_target"]
  assert len(last["verses"]) == 21 and last["verses"][-1]["is_target"]


def test_a_very_long_chapter_comes_back_whole():
  assert len(chapter(19, 119, 1).json()["verses"]) == 176  # Psalm 119


def test_the_full_chapter_uses_the_requested_translation():
  kjv = chapter(JOHN, 3, 16, "KJV").json()["verses"][15]["text"]
  bsb = chapter(JOHN, 3, 16, "bsb").json()["verses"][15]["text"]

  assert kjv != bsb and "For God so loved the world" in bsb


@pytest.mark.parametrize(
  "parameters, status",
  [
    ({"translation": "NOPE", "book": JOHN, "chapter": 3, "verse": 16}, 404),
    ({"translation": "KJV", "book": JOHN, "chapter": 99, "verse": 1}, 404),
    ({"translation": "KJV", "book": JOHN, "chapter": 3, "verse": 999}, 404),
    ({"translation": "NIV", "book": JOHN, "chapter": 3, "verse": 16}, 422),
    ({"translation": "nasb", "book": JOHN, "chapter": 3, "verse": 16}, 422),
    ({"translation": "KJV", "book": 0, "chapter": 3, "verse": 16}, 422),
    ({"translation": "KJV", "book": JOHN, "chapter": 0, "verse": 16}, 422),
    ({"translation": "KJV", "book": JOHN, "chapter": 3}, 422),
  ],
)
def test_chapter_requests_that_cannot_be_answered_are_refused(parameters, status):
  assert client.get("/chapter", params=parameters).status_code == status


def test_a_hidden_bible_has_no_full_chapter(tmp_path):
  from bible_import.importer import TranslationDetails, import_file
  from bible_import import catalog

  path = tmp_path / "hidden.txt"
  path.write_text("John 3:16\tFor God so loved the world.\n", encoding="utf-8")
  import_file(path, TranslationDetails(code="ZZCHAP", name="Hidden Test", license="Public domain"))

  try:
    assert chapter(JOHN, 3, 16, "ZZCHAP").status_code == 404
    catalog.set_published("ZZCHAP", True)
    assert chapter(JOHN, 3, 16, "ZZCHAP").status_code == 200
  finally:
    with connect() as connection:
      connection.execute("DELETE FROM translations WHERE code = 'ZZCHAP'")

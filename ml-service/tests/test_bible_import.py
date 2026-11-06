"""Tests for reading, previewing, importing, publishing and deleting Bible translations.

The import tests use the local database and the code ZZTEST, which is removed afterwards.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bible_import import catalog, formats
from bible_import.errors import ImportProblem
from bible_import.formats import RawVerse, ReadResult, detect_reader
from bible_import.importer import (
  TranslationDetails,
  import_file,
  preview_file,
  validate_details,
)
from main import app
from search import connect

client = TestClient(app)
TEST_CODE = "ZZTEST"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_bibles.py"

TAB_TEXT = (
  "Genesis 1:1\tIn the beginning God created the heavens and the earth.\n"
  "Genesis 1:2\tNow the earth was formless and void.\n"
  "John 3:16\tFor God so loved the world.\n"
  "Revelation 22:21\tThe grace of the Lord Jesus be with all.\n"
)
VPL_TEXT = (
  "GEN 1:1 In the beginning God created the heavens and the earth.\n"
  "GEN 1:2 Now the earth was formless and void.\n"
  "JHN 3:16 For God so loved the world.\n"
  "REV 22:21 The grace of the Lord Jesus be with all.\n"
)


def details(code=TEST_CODE, **changes):
  values = {"code": code, "name": "Test Bible", "language": "en", "license": "Public domain"}
  values.update(changes)
  return TranslationDetails(**values)


def write(tmp_path, text, name="bible.txt"):
  path = tmp_path / name
  path.write_text(text, encoding="utf-8")
  return path


@pytest.fixture(autouse=True)
def remove_test_translation():
  yield
  with connect() as connection:
    connection.execute("DELETE FROM translations WHERE code = %s", (TEST_CODE,))


def verse_count(code=TEST_CODE):
  with connect() as connection:
    row = connection.execute(
      "SELECT COUNT(*) FROM verses v JOIN translations t ON t.id = v.translation_id WHERE t.code = %s",
      (code,),
    ).fetchone()
  return row[0]


# --- reading formats -----------------------------------------------------------------------


def test_tab_format_is_detected_and_read(tmp_path):
  path = write(tmp_path, TAB_TEXT)

  reader = detect_reader(path)
  result = reader.read(path)

  assert reader.id == "tab"
  assert [verse.book for verse in result.verses] == ["Genesis", "Genesis", "John", "Revelation"]
  assert result.verses[2] == RawVerse("John", 3, 16, "For God so loved the world.")


def test_book_code_format_is_detected_and_read(tmp_path):
  path = write(tmp_path, VPL_TEXT)

  reader = detect_reader(path)

  assert reader.id == "vpl"
  assert reader.read(path).verses[0].book == "GEN"


def test_headers_and_blank_lines_are_not_verses(tmp_path):
  path = write(tmp_path, "My Bible, version 2\n\n" + TAB_TEXT + "\nEnd of file\n")

  result = detect_reader(path).read(path)

  assert len(result.verses) == 4
  assert result.skipped_count == 2
  assert result.skipped_samples == ["My Bible, version 2", "End of file"]


def test_a_byte_order_mark_is_accepted(tmp_path):
  path = tmp_path / "bom.txt"
  path.write_bytes(b"\xef\xbb\xbf" + TAB_TEXT.encode("utf-8"))

  assert detect_reader(path).read(path).verses[0].book == "Genesis"


def test_an_unrecognized_file_is_rejected_and_the_supported_formats_are_listed(tmp_path):
  path = write(tmp_path, "This is just a letter, not a Bible.\n")

  with pytest.raises(ImportProblem, match="Supported formats"):
    detect_reader(path)


def test_a_file_that_is_not_utf8_is_rejected(tmp_path):
  path = tmp_path / "latin.txt"
  path.write_bytes("Genesis 1:1\tIn the beginning caf\xe9\n".encode("latin-1"))

  with pytest.raises(ImportProblem, match="UTF-8"):
    detect_reader(path)


def test_a_new_format_can_be_added_to_the_registry(tmp_path, monkeypatch):
  class PipeSeparatedReader:
    id = "pipe"
    name = "Reference|text"
    description = "Gen.1.1|In the beginning..."

    def score(self, sample_lines):
      return sum(1 for line in sample_lines if re.match(r"^\w+\.\d+\.\d+\|", line))

    def read(self, path):
      result = ReadResult()
      for line in Path(path).read_text().splitlines():
        book, chapter, rest = line.split(".", 2)
        verse, text = rest.split("|", 1)
        result.verses.append(RawVerse(book, int(chapter), int(verse), text))
      return result

  monkeypatch.setattr(formats, "READERS", [*formats.READERS, PipeSeparatedReader()])
  path = write(tmp_path, "Gen.1.1|In the beginning.\nGen.1.2|And the earth was void.\n")

  preview = preview_file(path, details())

  assert preview["format"]["id"] == "pipe"
  assert preview["verse_count"] == 2
  assert preview["can_import"]


# --- checking what an administrator typed --------------------------------------------------


def test_the_code_is_uppercased_and_the_details_are_trimmed():
  cleaned = validate_details(details(code=" nasb95 ", name="  Spaced  ", license=" Public domain "))

  assert (cleaned.code, cleaned.name, cleaned.license) == ("NASB95", "Spaced", "Public domain")


@pytest.mark.parametrize(
  "changes, message",
  [
    ({"code": "A"}, "2 to 10"),
    ({"code": "has space"}, "2 to 10"),
    ({"code": "TOOLONGCODE1"}, "2 to 10"),
    ({"code": "NIV"}, "API.Bible"),
    ({"code": "msg"}, "API.Bible"),
    ({"name": ""}, "name is required"),
    ({"license": " "}, "license is required"),
    ({"language": "english"}, "language"),
    ({"source_url": "ftp://example.com"}, "http"),
  ],
)
def test_bad_details_are_rejected(changes, message):
  with pytest.raises(ImportProblem, match=message):
    validate_details(details(**changes))


# --- the preview -----------------------------------------------------------------------------


def test_the_preview_describes_the_file_and_saves_nothing(tmp_path):
  path = write(tmp_path, TAB_TEXT)

  preview = preview_file(path, details())

  assert preview["can_import"]
  assert (preview["verse_count"], preview["book_count"]) == (4, 3)
  assert [book["name"] for book in preview["books"]] == ["Genesis", "John", "Revelation"]
  assert "Exodus" in preview["missing_books"] and "Genesis" not in preview["missing_books"]
  assert [sample["reference"] for sample in preview["samples"]] == [
    "Genesis 1:1",
    "John 3:16",
    "Revelation 22:21",
  ]
  assert any("3 of the 66 books" in warning for warning in preview["warnings"])
  assert verse_count() == 0


def test_the_preview_says_when_an_import_would_replace_a_bible(tmp_path):
  path = write(tmp_path, TAB_TEXT)

  preview = preview_file(path, details(code="KJV"))

  assert preview["existing"]["is_published"] is True
  assert preview["existing"]["verse_count"] > 30000
  assert any("already exists" in warning for warning in preview["warnings"])


def test_duplicate_verses_block_the_import(tmp_path):
  path = write(tmp_path, TAB_TEXT + "Genesis 1:1\tIn the beginning again.\n")

  preview = preview_file(path, details())

  assert not preview["can_import"]
  assert "appear more than once" in preview["blocking_errors"][0]
  assert "Genesis 1:1" in preview["blocking_errors"][0]


def test_unrecognized_books_block_the_import_unless_skipped(tmp_path):
  path = write(tmp_path, TAB_TEXT + "Tobit 1:1\tThe book of the words of Tobit.\n")

  blocked = preview_file(path, details())
  skipped = preview_file(path, details(), skip_unmatched_books=True)

  assert not blocked["can_import"] and "Tobit" in blocked["blocking_errors"][0]
  assert skipped["can_import"] and skipped["verse_count"] == 4
  assert any("left out" in warning for warning in skipped["warnings"])


def test_brackets_and_pilcrows_are_cleaned_only_when_asked(tmp_path):
  path = write(tmp_path, "Genesis 1:1\t¶ In the [beginning] God\n")

  plain = preview_file(path, details())
  stripped = preview_file(path, details(), strip_brackets=True)

  assert plain["samples"][0]["text"] == "In the [beginning] God"
  assert stripped["samples"][0]["text"] == "In the beginning God"


# --- importing, publishing and deleting ----------------------------------------------------


def test_a_new_bible_is_hidden_until_it_is_published(tmp_path):
  path = write(tmp_path, TAB_TEXT)

  result = import_file(path, details())

  assert result["verse_count"] == 4 and result["is_published"] is False and result["replaced"] is False
  assert TEST_CODE not in [entry["code"] for entry in client.get("/translations").json()]
  hidden_search = client.get("/search", params={"query": "loved the world", "translations": TEST_CODE})
  assert hidden_search.status_code == 422

  catalog.set_published(TEST_CODE, True)

  assert TEST_CODE in [entry["code"] for entry in client.get("/translations").json()]
  found = client.get("/search", params={"query": "loved the world", "translations": TEST_CODE}).json()
  assert found["total"] == 1 and found["results"][0]["reference"] == "John 3:16"


def test_importing_again_replaces_the_text_and_keeps_the_published_state(tmp_path):
  import_file(write(tmp_path, TAB_TEXT, "first.txt"), details())
  catalog.set_published(TEST_CODE, True)

  second = import_file(write(tmp_path, "Genesis 1:1\tOnly one verse now.\n", "second.txt"), details(name="Renamed"))

  assert second["replaced"] is True and second["is_published"] is True and second["verse_count"] == 1
  assert verse_count() == 1
  listed = {entry["code"]: entry for entry in catalog.list_translations()}
  assert listed[TEST_CODE]["name"] == "Renamed" and listed[TEST_CODE]["is_published"] is True


def test_a_blocked_import_changes_nothing(tmp_path):
  path = write(tmp_path, TAB_TEXT + "Genesis 1:1\tDuplicate.\n")

  with pytest.raises(ImportProblem, match="more than once"):
    import_file(path, details())

  assert verse_count() == 0
  assert TEST_CODE not in [entry["code"] for entry in catalog.list_translations()]


def test_unpublishing_hides_a_bible_again(tmp_path):
  import_file(write(tmp_path, TAB_TEXT), details())
  catalog.set_published(TEST_CODE, True)

  catalog.set_published(TEST_CODE, False)

  assert TEST_CODE not in [entry["code"] for entry in client.get("/translations").json()]


def test_deleting_removes_the_translation_and_its_verses(tmp_path):
  import_file(write(tmp_path, TAB_TEXT), details())

  result = catalog.delete_translation(TEST_CODE)

  assert result["deleted_verse_count"] == 4
  assert verse_count() == 0
  with pytest.raises(ImportProblem, match="no Bible"):
    catalog.delete_translation(TEST_CODE)


def test_the_last_published_bible_cannot_be_hidden_or_deleted(tmp_path, monkeypatch):
  import_file(write(tmp_path, TAB_TEXT), details())
  catalog.set_published(TEST_CODE, True)
  monkeypatch.setattr(catalog, "other_published_count", lambda cursor, translation_id: 0)

  with pytest.raises(ImportProblem, match="At least one Bible"):
    catalog.set_published(TEST_CODE, False)
  with pytest.raises(ImportProblem, match="At least one Bible"):
    catalog.delete_translation(TEST_CODE)


def test_the_list_includes_hidden_bibles_with_verse_counts(tmp_path):
  import_file(write(tmp_path, TAB_TEXT), details())

  listed = {entry["code"]: entry for entry in catalog.list_translations()}

  assert listed[TEST_CODE]["is_published"] is False and listed[TEST_CODE]["verse_count"] == 4
  assert listed["KJV"]["is_published"] is True and listed["KJV"]["verse_count"] > 30000


# --- the command-line tool the Drupal page uses ---------------------------------------------


def run_tool(*arguments):
  completed = subprocess.run(
    [sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True, check=False
  )
  return completed.returncode, json.loads(completed.stdout)


def test_the_tool_reports_success_as_json(tmp_path):
  path = write(tmp_path, TAB_TEXT)

  status, preview = run_tool(
    "preview", str(path), "--code", TEST_CODE, "--name", "Test Bible", "--license", "Public domain"
  )
  assert status == 0 and preview["ok"] and preview["verse_count"] == 4

  status, imported = run_tool(
    "import", str(path), "--code", TEST_CODE, "--name", "Test Bible", "--license", "Public domain"
  )
  assert status == 0 and imported["is_published"] is False

  status, listed = run_tool("list")
  assert status == 0 and TEST_CODE in [entry["code"] for entry in listed["translations"]]

  assert run_tool("publish", "zztest")[1]["is_published"] is True
  assert run_tool("delete", TEST_CODE)[1]["deleted_verse_count"] == 4


def test_the_tool_reports_problems_as_json_with_a_failing_status(tmp_path):
  path = write(tmp_path, "not a bible\n")

  status, result = run_tool(
    "preview", str(path), "--code", TEST_CODE, "--name", "Test Bible", "--license", "Public domain"
  )

  assert status == 1 and result["ok"] is False and "recognize" in result["error"]
  assert run_tool("publish", "NOSUCHCODE")[0] == 1

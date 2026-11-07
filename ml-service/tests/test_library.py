"""Tests for hiding, showing, deleting and uploading commentaries and devotionals (the admin's Commentaries and
Devotionals pages). They use the real database and remove only their own items (ids starting test-upload-)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import library_admin
from commentaries import get_chapter_notes, get_commentaries, get_contents, list_commentaries, search_commentaries
from devotionals import get_unit, list_devotionals
from library_upload import UploadProblem, check_details, import_file, preview, read_commentary_file
from main import app
from search import connect
from site_users import create_user
from subscriptions import SubscriptionProblem, save_subscription

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_library.py"
COMMENTARY = {"id": "test-upload-poole", "name": "Matthew Poole's Commentary", "short_name": "Matthew Poole", "source_name": "A test source", "source_url": "https://example.org/poole"}
DEVOTIONAL = {"id": "test-upload-daily", "name": "Test Daily Readings", "author": "A. Writer", "kind": "daily", "source_name": "A test source"}
CHAPTERS = {"id": "test-upload-chapters", "name": "Test Chapters", "author": "B. Writer", "kind": "chapters", "source_name": "A test source"}

COMMENTARY_FILE = (
  "book\tchapter\tverse\tend_verse\ttext\n"
  "John\t3\t16\t\tGod so loved the world: the zebrafinch word.\\n\\nA second paragraph.\n"
  "JHN\t3\t17\t21\tThe Son was sent to save.\n"
  "43\t3\t22\tend\tAfter these things.\n"
  "John\t0\t\t\tAn introduction to John.\n"
  "John\t3\t\t\tAn introduction to chapter 3.\n"
)


@pytest.fixture(autouse=True)
def clean():
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM commentaries WHERE id LIKE 'test-upload-%'")
      connection.execute("DELETE FROM devotional_subscriptions WHERE devotional_id LIKE 'test-upload-%'")
      connection.execute("DELETE FROM devotionals WHERE id LIKE 'test-upload-%'")
      connection.execute("DELETE FROM users WHERE email LIKE '%@library-test.example'")

  clear()
  yield
  clear()


def write(tmp_path, text, name="upload.txt"):
  path = tmp_path / name
  path.write_text(text, encoding="utf-8")
  return path


def test_a_commentary_file_is_read_with_ranges_introductions_and_paragraphs(tmp_path):
  entries, introductions, result, _ = read_commentary_file(write(tmp_path, COMMENTARY_FILE))

  assert result.problems == [] and result.warnings == []
  assert entries[0] == (43, 3, 16, 16, "God so loved the world: the zebrafinch word.\n\nA second paragraph.")
  assert entries[1][:4] == (43, 3, 17, 21) and entries[2][:4] == (43, 3, 22, None)
  assert sorted(introductions) == [(43, 0, "An introduction to John."), (43, 3, "An introduction to chapter 3.")]


def test_mistakes_in_a_commentary_file_are_reported_by_line(tmp_path):
  text = (
    "book\tchapter\tverse\tend_verse\ttext\n"
    "Hezekiah\t1\t1\t\tNo such book.\n"
    "John\t3\t16\t\tFine.\n"
    "John\t3\t16\t\tTwice.\n"
    "John\t3\t17\t2\tEnds before it starts.\n"
    "John\t3\t18\n"
    "John\t99\t1\t\tA chapter John does not have.\n"
  )
  _, _, result, _ = read_commentary_file(write(tmp_path, text))

  assert any("Line 2" in problem and "Hezekiah" in problem for problem in result.problems)
  assert any("Line 4" in problem and "already has a note" in problem for problem in result.problems)
  assert any("Line 5" in problem and "end_verse" in problem for problem in result.problems)
  assert any("Line 6" in problem and "columns" in problem for problem in result.problems)
  assert any("Line 7" in problem and "never be shown" in warning for warning in result.warnings for problem in [warning])


def test_the_header_and_the_details_are_checked(tmp_path):
  with pytest.raises(UploadProblem, match="first row"):
    preview("commentary", write(tmp_path, "book,chapter,verse\nJohn,3,16\n"), COMMENTARY)
  with pytest.raises(UploadProblem, match="Refresh"):
    check_details("commentary", {**COMMENTARY, "id": "matthew-henry"})
  with pytest.raises(UploadProblem, match="lowercase"):
    check_details("commentary", {**COMMENTARY, "id": "Bad Id"})
  with pytest.raises(UploadProblem, match="daily or by chapter"):
    check_details("devotional", {**DEVOTIONAL, "kind": "weekly"})


def test_an_uploaded_commentary_is_hidden_until_published_and_then_everywhere(tmp_path):
  path = write(tmp_path, COMMENTARY_FILE)
  shown = preview("commentary", path, COMMENTARY)
  assert shown["can_import"] and shown["summary"]["notes"] == 3 and shown["summary"]["books"] == ["John"] and shown["existing"] is None

  result = import_file("commentary", path, COMMENTARY)
  assert result == {"id": "test-upload-poole", "name": "Matthew Poole's Commentary", "count": 3, "is_published": False}
  assert all(entry["id"] != "test-upload-poole" for entry in list_commentaries())
  assert get_contents("test-upload-poole") is None and get_chapter_notes("test-upload-poole", 43, 3) is None
  assert all(entry["id"] != "test-upload-poole" for entry in get_commentaries(43, 3, 16)["commentaries"])
  assert search_commentaries("zebrafinch", "all", None, 1, 66, None, 1, 25, "rank", "asc")["total"] == 0

  library_admin.set_published("commentary", "test-upload-poole", True)
  listed = next(entry for entry in list_commentaries() if entry["id"] == "test-upload-poole")
  assert listed["source_name"] == "A test source" and listed["license_url"].endswith("publicdomain/mark/1.0/")
  assert get_contents("test-upload-poole")["books"] == [{"number": 43, "name": "John", "chapters": [3]}]
  assert get_chapter_notes("test-upload-poole", 43, 3)["chapter_introduction"] == "An introduction to chapter 3."
  assert search_commentaries("zebrafinch", "all", None, 1, 66, None, 1, 25, "rank", "asc")["total"] == 1

  # Uploading it again replaces the text and keeps it published.
  import_file("commentary", write(tmp_path, COMMENTARY_FILE.replace("zebrafinch", "zorbleplank"), "again.txt"), COMMENTARY)
  assert search_commentaries("zorbleplank", "all", None, 1, 66, None, 1, 25, "rank", "asc")["total"] == 1
  assert preview("commentary", path, COMMENTARY)["existing"] == {"is_published": True, "count": 3}

  library_admin.set_published("commentary", "test-upload-poole", False)
  assert search_commentaries("zorbleplank", "all", None, 1, 66, None, 1, 25, "rank", "asc")["total"] == 0
  assert library_admin.delete("commentary", "test-upload-poole")["deleted_count"] == 3
  assert all(item["id"] != "test-upload-poole" for item in library_admin.list_items("commentary"))


def daily_file():
  lines = ["section\tsection_title\tunit\tunit_title\theading\ttext"]
  lines.append("1\t\t1\t\tMorning\tA new year begins.")
  lines.append("1\t\t1\t\tEvening\tThe first evening.")
  lines.append("2\t\t29\t\tMorning\tA leap day.")
  return "\n".join(lines) + "\n"


def test_a_daily_devotional_fills_in_month_and_day_titles_and_keeps_parts(tmp_path):
  shown = preview("devotional", write(tmp_path, daily_file()), DEVOTIONAL)

  assert shown["can_import"] and shown["summary"]["units"] == 2 and shown["summary"]["readings"] == 3
  assert shown["summary"]["sections"] == ["January", "February"]
  assert shown["summary"]["samples"][0]["place"] == "January 1 (Morning)"
  assert any("364 of the 366 days" in warning for warning in shown["warnings"])

  bad = daily_file() + "2\t\t30\t\tMorning\tNo such day.\n"
  assert any("not a date" in problem for problem in preview("devotional", write(tmp_path, bad, "bad.txt"), DEVOTIONAL)["problems"])


def test_a_chapter_devotional_needs_its_titles(tmp_path):
  text = (
    "section\tsection_title\tunit\tunit_title\theading\ttext\n"
    "1\tThe First Book\t1\tOf Beginnings\t\tChapter one.\n"
    "1\t\t2\tOf Going On\t\tChapter two.\n"
    "2\t\t1\tOf Ending\t\tNo section title.\n"
  )
  shown = preview("devotional", write(tmp_path, text), CHAPTERS)
  assert any("Line 4" in problem and "section_title" in problem for problem in shown["problems"])
  assert shown["can_import"] is False


def test_a_hidden_devotional_disappears_stops_new_subscriptions_and_deleting_removes_them(tmp_path):
  import_file("devotional", write(tmp_path, daily_file()), DEVOTIONAL)
  assert all(entry["id"] != "test-upload-daily" for entry in list_devotionals())
  assert get_unit("test-upload-daily", 1, 1) is None

  user = create_user("reader@library-test.example", "a long enough password", True, False)
  with pytest.raises(SubscriptionProblem, match="not found"):
    save_subscription(user["id"], "test-upload-daily", "07:00", "UTC")

  library_admin.set_published("devotional", "test-upload-daily", True)
  assert [entry["heading"] for entry in get_unit("test-upload-daily", 1, 1)["entries"]] == ["Morning", "Evening"]
  save_subscription(user["id"], "test-upload-daily", "07:00", "UTC")

  library_admin.set_published("devotional", "test-upload-daily", False)
  # Still listed for the visitor, so they can see and stop it.
  assert client.get("/devotionals").json() == [entry for entry in client.get("/devotionals").json() if entry["id"] != "test-upload-daily"]

  removed = library_admin.delete("devotional", "test-upload-daily")
  assert removed["deleted_count"] == 3 and removed["deleted_subscriptions"] == 1


def test_only_the_known_ones_can_be_refreshed():
  with pytest.raises(library_admin.LibraryProblem, match="upload its file again"):
    library_admin.refresh("commentary", "test-upload-poole")
  assert any(item["id"] == "matthew-henry" and item["refreshable"] for item in library_admin.list_items("commentary"))


def test_the_tool_answers_in_json(tmp_path):
  path = write(tmp_path, COMMENTARY_FILE)
  arguments = [f"--kind=commentary", f"--id={COMMENTARY['id']}", f"--name={COMMENTARY['name']}", f"--short-name={COMMENTARY['short_name']}", f"--source-name={COMMENTARY['source_name']}"]
  completed = subprocess.run([sys.executable, str(SCRIPT), "import", str(path), *arguments], capture_output=True, text=True, check=False)
  assert completed.returncode == 0 and json.loads(completed.stdout)["is_published"] is False

  completed = subprocess.run([sys.executable, str(SCRIPT), "publish", "--kind=commentary", "--id=test-upload-poole"], capture_output=True, text=True, check=False)
  assert json.loads(completed.stdout) == {"ok": True, "id": "test-upload-poole", "is_published": True}

  completed = subprocess.run([sys.executable, str(SCRIPT), "delete", "--kind=devotional", "--id=test-upload-none"], capture_output=True, text=True, check=False)
  assert completed.returncode == 1 and "There is no devotional" in json.loads(completed.stdout)["error"]


BOOK = {"id": "test-upload-book", "name": "Test Book", "author": "C. Writer", "source_name": "A test source"}
BOOK_FILE = (
  "section\tsection_title\tunit\tunit_title\theading\ttext\n"
  "1\tThe Book\t1\tThe First Chapter\t\tChapter one.\n"
  "1\t\t2\tThe Second Chapter\t\tChapter two.\n"
)


def test_an_other_book_is_kept_apart_from_the_devotionals_and_has_no_emails(tmp_path):
  from devotionals import list_books

  result = import_file("book", write(tmp_path, BOOK_FILE), BOOK)
  assert result["is_published"] is False and result["count"] == 2
  assert all(item["id"] != "test-upload-book" for item in library_admin.list_items("devotional"))
  assert any(item["id"] == "test-upload-book" for item in library_admin.list_items("book"))

  library_admin.set_published("book", "test-upload-book", True)
  assert any(entry["id"] == "test-upload-book" for entry in list_books())
  assert all(entry["id"] != "test-upload-book" for entry in list_devotionals())
  assert any(entry["id"] == "test-upload-book" for entry in client.get("/other-books").json())
  assert get_unit("test-upload-book", 1, 2)["entries"][0]["text"] == "Chapter two."

  user = create_user("book-reader@library-test.example", "a long enough password", True, False)
  with pytest.raises(SubscriptionProblem, match="not found"):
    save_subscription(user["id"], "test-upload-book", "07:00", "UTC")

  # A book is not a devotional to the devotionals' page, and its id cannot be taken by a devotional.
  with pytest.raises(library_admin.LibraryProblem, match="no devotional"):
    library_admin.set_published("devotional", "test-upload-book", False)
  with pytest.raises(UploadProblem, match="already an Other book"):
    check_details("devotional", {**CHAPTERS, "id": "test-upload-book"})
  assert library_admin.delete("book", "test-upload-book")["deleted_count"] == 2


def test_the_known_books_can_be_loaded_from_the_admin():
  items = {item["id"]: item for item in library_admin.list_items("book")}
  assert {"orthodoxy", "confessions-of-augustine", "summa-theologica-part-1"} <= set(items)
  assert all(item["refreshable"] for item in items.values() if item["id"] in ("orthodoxy", "pursuit-of-god"))

"""Tests for the Kindle books (kindle_books.py). They use the real table with their own rows (titles starting
"Kindle test"), removed after; conftest.py points the pictures at a temporary folder."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import kindle_books
from kindle_books import KindleBookProblem
from main import app
from search import connect

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_kindle_books.py"
LINK = "https://read.amazon.com/?asin=B00DL10JF6&ref_=kwl_kr_iv_aut_19"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def clean():
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM kindle_books WHERE title LIKE 'Kindle test%'")

  clear()
  yield
  clear()


def book(collection="devotionals", **details):
  return kindle_books.create_book({"collection": collection, "title": "Kindle test devotional", "author": "A. Writer", "address": LINK, **details}, "admin")


def test_a_kindle_book_keeps_its_link_and_collection_and_is_listed_for_the_public():
  made = book()
  assert made["address"] == LINK and made["collection"] == "devotionals" and made["cover"] is None
  other = book("books", title="Kindle test other book", author="")
  public = [each for each in client.get("/kindle-books").json()["books"] if each["title"].startswith("Kindle test")]
  assert {each["title"]: each["collection"] for each in public} == {"Kindle test devotional": "devotionals", "Kindle test other book": "books"}
  assert set(public[0]) == {"id", "collection", "title", "author", "address", "cover"}
  assert [each["id"] for each in kindle_books.list_books("books") if each["title"].startswith("Kindle test")] == [other["id"]]

  # Hidden (unpublished) books are not listed; changing keeps the collection.
  changed = kindle_books.update_book(made["id"], {"title": "Kindle test devotional", "address": LINK, "is_published": False})
  assert changed["collection"] == "devotionals" and changed["is_published"] is False
  assert all(each["id"] != made["id"] for each in client.get("/kindle-books").json()["books"])


def test_only_amazon_links_and_a_known_collection_are_kept():
  assert book(address="read.amazon.com/?asin=B00DL10JF6")["address"] == "https://read.amazon.com/?asin=B00DL10JF6"
  assert book(address="http://www.amazon.com/dp/B00DL10JF6")["address"] == "https://www.amazon.com/dp/B00DL10JF6"
  for bad in ("https://evil.example/read.amazon.com", "javascript:alert(1)", "https://amazon.com.evil.example/", ""):
    with pytest.raises(KindleBookProblem):
      book(address=bad)
  with pytest.raises(KindleBookProblem, match="Devotionals"):
    book(collection="music")
  with pytest.raises(KindleBookProblem, match="title"):
    book(title=" ")


def test_a_picture_is_kept_checked_and_served_then_removed_with_the_book(tmp_path):
  made = book()
  picture = tmp_path / "cover.png"
  picture.write_bytes(PNG)
  with_cover = kindle_books.save_cover(made["id"], picture, "cover.png")
  assert with_cover["cover"].startswith(f"/kindle-book-cover/{made['id']}?v=")
  served = client.get(with_cover["cover"])
  assert served.status_code == 200 and served.headers["content-type"] == "image/png" and served.content == PNG

  svg = tmp_path / "cover.svg"
  svg.write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>")
  with pytest.raises(KindleBookProblem, match="PNG, JPEG, WebP or GIF"):
    kindle_books.save_cover(made["id"], svg, "cover.svg")
  fake = tmp_path / "fake.png"
  fake.write_bytes(b"not a picture")
  with pytest.raises(KindleBookProblem, match="not a PNG"):
    kindle_books.save_cover(made["id"], fake, "fake.png")

  assert kindle_books.remove_cover(made["id"])["cover"] is None
  assert client.get(f"/kindle-book-cover/{made['id']}").status_code == 404
  kindle_books.save_cover(made["id"], picture, "cover.png")
  kindle_books.delete_book(made["id"])
  assert not any(kindle_books.covers_folder().glob(f"{made['id']}.*"))


def test_the_admin_tool_adds_lists_and_sets_a_picture(tmp_path):
  def run(*arguments, details=None):
    completed = subprocess.run(
      [sys.executable, str(SCRIPT), *arguments], input=json.dumps(details) if details else "", capture_output=True, text=True, check=False,
    )
    return completed.returncode, json.loads(completed.stdout)

  status, result = run("create", details={"collection": "books", "title": "Kindle test tool", "address": LINK, "created_by": "admin"})
  assert status == 0 and result["book"]["collection"] == "books"
  status, listed = run("list", "--collection=books")
  assert status == 0 and any(each["id"] == result["book"]["id"] for each in listed["books"])
  picture = tmp_path / "c.jpg"
  picture.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
  status, covered = run("cover", f"--id={result['book']['id']}", f"--file={picture}", "--name=c.jpg")
  assert status == 0 and covered["book"]["cover"] is not None
  status, refused = run("create", details={"collection": "books", "title": "Kindle test tool", "address": "https://example.com"})
  assert status == 1 and "amazon.com" in refused["error"]

"""Tests for PDF, Word and EPUB uploads (document_import.py, document_split.py, their use in library_upload.py and
music.py). The documents are made by tests/sample_documents.py; the uploads use the real database and remove
only their own items (ids starting test-document-). conftest.py gives each test its own pictures folder."""

import shutil

import pytest
from fastapi.testclient import TestClient

import document_import
from document_import import Document, DocumentProblem, clean_library_html, convert, html_to_text
from document_split import parse_passage_heading, split_chapters, split_commentary, split_daily
from library_upload import import_file, preview
from main import app
from scripture_references import formatted_html
from search import connect
from bible_import.importer import load_books
from sample_documents import make_docx, make_docx_headings, make_epub, make_pdf, make_scanned_pdf

client = TestClient(app)
BOOK = {"id": "test-document-book", "name": "A Sample Book", "author": "A. Writer", "source_name": "A test source"}
COMMENTARY = {"id": "test-document-notes", "name": "Test Notes", "short_name": "Test Notes", "source_name": "A test source"}


@pytest.fixture(autouse=True)
def clean():
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM commentaries WHERE id LIKE 'test-document-%'")
      connection.execute("DELETE FROM devotionals WHERE id LIKE 'test-document-%'")
      connection.execute("DELETE FROM music_tracks WHERE id LIKE 'test-document-%'")

  clear()
  yield
  clear()


def book_lookup():
  with connect() as connection:
    with connection.cursor() as cursor:
      return load_books(cursor)[1]


def test_a_word_book_keeps_its_formatting_and_is_cut_into_parts_and_chapters(tmp_path):
  document = convert(make_docx(tmp_path / "book.docx"), "book.docx")
  sections, entries, split = split_chapters(document, "A Sample Book")

  assert sections == [(1, "Part One"), (2, "Part Two")]
  assert [(entry.section, entry.unit, entry.unit_title) for entry in entries] == [(1, 1, "Chapter 1"), (1, 2, "Chapter 2"), (2, 1, "Chapter 3")]
  first = entries[0].html
  assert "<strong>grace</strong>" in first and "<em>mercy</em>" in first
  assert "<ul><li>First point</li>" in first and "<blockquote>" in first and "<table>" in first
  assert '<img src="/library-image/' in entries[-1].html and len(document.images) == 1
  assert "Word Meaning" in entries[0].text and "<" not in entries[0].text
  assert any("title page" in warning for warning in split.warnings)


def test_a_pdf_keeps_headings_bold_italic_tables_and_pictures(tmp_path):
  path = make_pdf(
    tmp_path / "book.pdf",
    [("h1", "Part One"), ("h2", "Chapter 1"), ("p", "In the beginning was the Word. " * 4), ("bold", "Grace"), ("italic", "mercy"),
     ("h2", "Chapter 2"), ("p", "Second chapter, as in John 3:16.")],
    picture=True, table=True,
  )
  document = convert(path, "book.pdf")

  assert "<h1>Part One</h1>" in document.html and "<h2>Chapter 1</h2>" in document.html
  assert "<p><strong>Grace</strong> and then plain words follow here.</p>" in document.html
  assert "<em>mercy</em>" in document.html
  assert "<th>Word</th>" in document.html and "<td>agape</td>" in document.html
  assert len(document.images) == 1
  sections, entries, _ = split_chapters(document, "Book")
  assert [entry.unit_title for entry in entries] == ["Chapter 1", "Chapter 2"]


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_a_scanned_pdf_is_read_by_text_recognition(tmp_path):
  path = make_scanned_pdf(tmp_path / "scan.pdf", ["The Lord is my shepherd; I shall not want.", "He maketh me to lie down in green pastures."])
  document = convert(path, "scan.pdf")
  assert document.ocr_pages == 1 and any("text recognition" in warning for warning in document.warnings)
  assert "shepherd" in document.html and "pastures" in document.html


def test_wrong_documents_are_refused(tmp_path):
  fake = tmp_path / "fake.pdf"
  fake.write_bytes(b"not a pdf at all")
  with pytest.raises(DocumentProblem, match="not really a PDF"):
    convert(fake, "fake.pdf")
  old = tmp_path / "old.doc"
  old.write_bytes(b"\xd0\xcf\x11\xe0")
  with pytest.raises(DocumentProblem, match="PDF \\(.pdf\\), a Word document"):
    convert(old, "old.doc")


def test_footnotes_go_to_the_end_of_the_chapter_that_cites_them():
  document = Document(
    '<h2>One</h2><p>Text<sup data-footnote="1">[1]</sup></p><h2>Two</h2><p>More<sup data-footnote="2">[2]</sup></p>',
    footnotes={"1": "<p>First note.</p>", "2": "<p>Second note.</p>"},
  )
  _, entries, _ = split_chapters(document, "Book")
  assert "First note." in entries[0].html and "Second note." not in entries[0].html
  assert entries[1].html.endswith("<p><sup>[2]</sup> Second note.</p>")


def test_cleaning_keeps_formatting_and_drops_anything_unsafe():
  cleaned = clean_library_html(
    '<h2 onclick="x()">Title</h2><p><b>bold</b> <i>it</i><script>alert(1)</script></p>'
    '<table><tr><td colspan="2" style="x">a</td></tr></table><img src="https://evil.example/a.png">'
    '<img src="/library-image/0123456789abcdef0123.png" alt="A picture"><a href="javascript:x">y</a><p></p>'
  )
  assert cleaned == (
    '<h2>Title</h2><p><strong>bold</strong> <em>it</em></p><table><tr><td colspan="2">a</td></tr></table>'
    '<img src="/library-image/0123456789abcdef0123.png" alt="A picture">y'
  )
  assert html_to_text("<p>One</p><ul><li>A</li></ul><table><tr><td><p>x</p></td><td>y</td></tr></table>") == "One\n\n• A\n\nx y"


def test_references_become_buttons_but_not_inside_links():
  html = formatted_html('<p>See <em>John 3:16</em> and <a href="https://example.org">Rom 8:28</a>.</p>')
  assert 'data-verse="43:3:16"' in html and 'class="reference-link"' in html
  assert "45:8:28" not in html


def test_a_daily_devotional_is_cut_by_date_headings(tmp_path):
  path = make_docx_headings(tmp_path / "daily.docx", [
    (1, "Daily Readings"), (0, "A title page."),
    (2, "January 1"), (3, "Morning"), (0, "Morning words."), (3, "Evening"), (0, "Evening words."),
    (2, "Jan. 2"), (0, "Second day."),
  ])
  sections, entries, split = split_daily(convert(path, "daily.docx"))
  assert sections == [(1, "January")]
  assert [(entry.section, entry.unit, entry.part, entry.heading, entry.text) for entry in entries] == [
    (1, 1, 1, "Morning", "Morning words."), (1, 1, 2, "Evening", "Evening words."), (1, 2, 1, "", "Second day."),
  ]
  assert any("364 of the 366 days" in warning for warning in split.warnings)


def test_passage_headings_are_understood():
  lookup = book_lookup()
  assert parse_passage_heading("John 3:16-18", lookup, None, None) == ("verses", 43, 3, 16, 18)
  assert parse_passage_heading("The Gospel of John", lookup, None, None) == ("book", 43)
  assert parse_passage_heading("Chapter 4", lookup, 43, 3) == ("chapter", 43, 4)
  assert parse_passage_heading("Verses 5–7", lookup, 43, 4) == ("verses", 43, 4, 5, 7)
  assert parse_passage_heading("Verse 9", lookup, 43, 4) == ("verses", 43, 4, 9, 9)
  assert parse_passage_heading("4:1-end", lookup, 43, 3) == ("verses", 43, 4, 1, None)
  assert parse_passage_heading("A Word of Prayer", lookup, 43, 3) is None


def test_a_commentary_is_cut_by_passage_headings(tmp_path):
  path = make_docx_headings(tmp_path / "notes.docx", [
    (1, "John"), (0, "About the Gospel of John."),
    (2, "John 3"), (0, "The chapter of the new birth."),
    (3, "Verse 16"), (0, "God so loved the world."), (4, "A Word of Prayer"), (0, "Lord, help us believe."),
    (3, "Verses 17-18"), (0, "Not to condemn."),
  ])
  entries, introductions, split = split_commentary(convert(path, "notes.docx"), book_lookup())
  assert not split.problems
  assert [entry[:5] for entry in entries] == [
    (43, 3, 16, 16, "God so loved the world.\n\nA Word of Prayer\n\nLord, help us believe."),
    (43, 3, 17, 18, "Not to condemn."),
  ]
  assert "<h4>A Word of Prayer</h4>" in entries[0][5]
  assert [introduction[:3] for introduction in introductions] == [(43, 0, "About the Gospel of John."), (43, 3, "The chapter of the new birth.")]


def test_a_commentary_without_headings_is_one_note_on_the_passage_typed(tmp_path):
  path = make_docx_headings(tmp_path / "one.docx", [(0, "A single note."), (0, "Its second paragraph.")])
  document = convert(path, "one.docx")
  entries, _, split = split_commentary(document, book_lookup())
  assert entries == [] and "No headings naming a passage" in split.problems[0]
  entries, _, split = split_commentary(document, book_lookup(), "Romans 8:28-30")
  assert [entry[:5] for entry in entries] == [(45, 8, 28, 30, "A single note.\n\nIts second paragraph.")]


def test_a_word_book_is_previewed_imported_with_its_pictures_and_served(tmp_path):
  path = make_docx(tmp_path / "book.docx")
  shown = preview("book", path, BOOK)
  assert shown["can_import"] and shown["summary"]["formatted"] and shown["summary"]["pictures"] == 1
  assert shown["summary"]["units"] == 3 and shown["summary"]["sections"] == ["Part One", "Part Two"]

  result = import_file("book", path, BOOK)
  assert result["count"] == 3 and result["is_published"] is False
  with connect() as connection:
    connection.execute("UPDATE devotionals SET is_published = true WHERE id = 'test-document-book'")
  unit = client.get("/devotional-unit", params={"devotional": "test-document-book", "section": 2, "unit": 1}).json()
  html = unit["entries"][0]["html"]
  assert 'data-verse="43:3:16"' in html and "<table>" in html
  picture = html.split('src="')[1].split('"')[0]
  response = client.get(picture)
  assert response.status_code == 200 and response.headers["content-type"] == "image/png"
  assert "immutable" in response.headers["cache-control"]
  assert client.get("/library-image/../../main.py").status_code == 404
  found = client.get("/search-other-books", params={"query": "agape", "match_mode": "all", "book": "test-document-book"}).json()
  assert found["total"] == 3


def test_a_commentary_document_is_imported_and_shown_with_its_formatting(tmp_path):
  path = make_docx_headings(tmp_path / "notes.docx", [(2, "John 3"), (0, "Intro."), (3, "Verse 16"), (0, "God so loved the world, as Romans 5:8 says.")])
  result = import_file("commentary", path, COMMENTARY)
  assert result["count"] == 1
  with connect() as connection:
    connection.execute("UPDATE commentaries SET is_published = true WHERE id = 'test-document-notes'")
  chapter = client.get("/commentary-chapter", params={"commentary": "test-document-notes", "book": 43, "chapter": 3}).json()
  assert 'data-verse="45:5:8"' in chapter["entries"][0]["html"]
  assert chapter["chapter_introduction_html"] == "<p>Intro.</p>"


def test_song_words_come_from_a_document_and_typing_new_words_drops_the_formatting(tmp_path):
  import music

  song = tmp_path / "song.mp3"
  song.write_bytes(b"ID3" + b"\x00" * 200)
  music.upload(song, "song.mp3", "test-document-song", {"title": "Test Song", "author": "", "lyrics": ""})
  words = make_docx_headings(tmp_path / "words.docx", [(2, "Verse 1"), (0, "Amazing grace, how sweet the sound.")])
  updated = music.set_words_from_document("test-document-song", words, "words.docx")
  assert updated["lyrics"] == "Verse 1\n\nAmazing grace, how sweet the sound."
  assert updated["lyrics_html"] == "<h2>Verse 1</h2><p>Amazing grace, how sweet the sound.</p>"
  kept = music.update_details("test-document-song", {"title": "Test Song", "author": "", "lyrics": updated["lyrics"]})
  assert kept["lyrics_html"] is not None
  changed = music.update_details("test-document-song", {"title": "Test Song", "author": "", "lyrics": "New words."})
  assert changed["lyrics_html"] is None
  music.delete("test-document-song")


def test_a_document_can_be_kept_whole_as_one_chapter(tmp_path):
  path = make_docx(tmp_path / "book.docx")
  shown = preview("book", path, {**BOOK, "whole": True})
  assert shown["can_import"] and shown["summary"]["units"] == 1 and shown["summary"]["sections"] == ["A Sample Book"]
  assert shown["details"]["whole"] is True and not any("title page" in warning for warning in shown["warnings"])

  assert import_file("book", path, {**BOOK, "whole": True})["count"] == 1
  with connect() as connection:
    title, html = connection.execute(
      "SELECT unit_title, html FROM devotional_entries WHERE devotional_id = 'test-document-book'"
    ).fetchone()
  # Every heading stays inside the one chapter, and so does the short text before the first one.
  assert title == "A Sample Book" and "Part Two" in html and "Chapter 3" in html and "<table>" in html

  # A daily devotional is still read by its dates; a commentary ignores it.
  daily = preview("devotional", path, {**BOOK, "id": "test-document-daily", "kind": "daily", "whole": True})
  assert not daily["can_import"] and daily["details"]["whole"] is True
  assert preview("commentary", path, {**COMMENTARY, "whole": True})["details"]["whole"] is False


def test_control_characters_from_a_pdf_are_dropped():
  # A PDF once gave NUL for a hyphen it had no character for; PostgreSQL refuses NUL in text.
  cleaned = clean_library_html("<p>Soft\x00cover\x07 and\ttabs</p>")
  assert cleaned == "<p>Softcover and\ttabs</p>" and "\x00" not in html_to_text(cleaned)


@pytest.mark.parametrize("version", [3, 2])
def test_an_ebook_is_cut_by_its_table_of_contents_and_keeps_its_formatting(tmp_path, version):
  document = convert(make_epub(tmp_path / "book.epub", version=version), "book.epub")
  sections, entries, split = split_chapters(document, "A Sample Ebook")

  assert sections == [(1, "Part One"), (2, "Part Two")]
  assert [(entry.section, entry.unit, entry.unit_title) for entry in entries] == [(1, 1, "Chapter 1"), (1, 2, "Chapter 2"), (2, 1, "Chapter 3")]
  first = entries[0].html
  assert "<strong>grace</strong>" in first and "<em>mercy</em>" in first and "<ul><li>First point</li>" in first
  # A heading the contents does not name stays inside its chapter; the note link keeps only its number.
  assert "<h3>A heading inside the chapter</h3>" in first and "notes.xhtml" not in first and "color" not in first
  # The cover (an <image> inside an <svg>) and the picture in the page are one file, kept once.
  assert len(document.images) == 1 and '<img src="/library-image/' in entries[1].html
  assert "The second chapter has no heading of its own." in entries[1].text
  # The cover page (a picture only) before the contents is left out, with a warning, rather than kept as a chapter.
  assert any("cover page" in warning for warning in split.warnings)


def test_a_locked_ebook_and_kindle_files_are_refused_with_a_reason(tmp_path):
  with pytest.raises(DocumentProblem, match="locked"):
    convert(make_epub(tmp_path / "locked.epub", locked=True), "locked.epub")
  # Hiding a font is not a lock on the text.
  assert "grace" in convert(make_epub(tmp_path / "font.epub", font_obfuscation=True), "font.epub").html
  kindle = tmp_path / "book.azw3"
  kindle.write_bytes(b"BOOKMOBI" + b"\x00" * 100)
  with pytest.raises(DocumentProblem, match="Calibre"):
    convert(kindle, "book.azw3")
  not_epub = tmp_path / "fake.epub"
  not_epub.write_bytes(b"%PDF-1.4 not an ebook")
  with pytest.raises(DocumentProblem, match="not really an EPUB"):
    convert(not_epub, "fake.epub")


def test_an_ebook_is_previewed_and_imported_as_an_other_book(tmp_path):
  path = make_epub(tmp_path / "upload.epub")
  details = {**BOOK, "id": "test-document-ebook", "name": "A Sample Ebook"}
  shown = preview("book", path, details)
  assert shown["can_import"] and shown["summary"]["units"] == 3 and shown["summary"]["pictures"] == 1
  assert shown["summary"]["sections"] == ["Part One", "Part Two"]
  import_file("book", path, details)
  with connect() as connection:
    rows = connection.execute(
      "SELECT section, unit, unit_title FROM devotional_entries WHERE devotional_id = 'test-document-ebook' ORDER BY section, unit"
    ).fetchall()
  assert [tuple(row) for row in rows] == [(1, 1, "Chapter 1"), (1, 2, "Chapter 2"), (2, 1, "Chapter 3")]

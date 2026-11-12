"""Small PDF and Word documents for the tests of document_import.py and document_split.py, made when a test
runs (python-docx and reportlab are test dependencies)."""

import io
from pathlib import Path

from PIL import Image, ImageDraw


def picture_bytes(colour=(46, 125, 50)) -> bytes:
  picture = Image.new("RGB", (120, 80), colour)
  ImageDraw.Draw(picture).rectangle((10, 10, 110, 70), outline=(255, 255, 255), width=4)
  buffer = io.BytesIO()
  picture.save(buffer, "PNG")
  return buffer.getvalue()


def make_docx(path: Path, chapters=(("Part One", ["Chapter 1", "Chapter 2"]), ("Part Two", ["Chapter 3"]))) -> Path:
  """A book: parts (Heading 1) and chapters (Heading 2), with bold, italic, a list, a quotation, a table, a
  picture, a footnote marker and a Scripture reference."""
  from docx import Document

  document = Document()
  document.add_paragraph("A Sample Book", style="Title")
  for part, chapter_titles in chapters:
    document.add_heading(part, level=1)
    for title in chapter_titles:
      document.add_heading(title, level=2)
      paragraph = document.add_paragraph("The words of ")
      paragraph.add_run("grace").bold = True
      paragraph.add_run(" and ")
      paragraph.add_run("mercy").italic = True
      paragraph.add_run(f" in {title}, as in John 3:16.")
      document.add_paragraph("First point", style="List Bullet")
      document.add_paragraph("Second point", style="List Bullet")
      document.add_paragraph("Be still, and know that I am God.", style="Quote")
      table = document.add_table(rows=2, cols=2)
      table.cell(0, 0).text, table.cell(0, 1).text = "Word", "Meaning"
      table.cell(1, 0).text, table.cell(1, 1).text = "agape", "love"
  document.add_picture(io.BytesIO(picture_bytes()))
  document.save(path)
  return path


def make_docx_headings(path: Path, headings_and_text: list[tuple[int, str]]) -> Path:
  """A Word document of headings (level 1 to 3) and paragraphs (level 0)."""
  from docx import Document

  document = Document()
  for level, text in headings_and_text:
    if level:
      document.add_heading(text, level=level)
    else:
      document.add_paragraph(text)
  document.save(path)
  return path


def make_pdf(path: Path, lines: list[tuple[str, str]], picture=False, table=False) -> Path:
  """A text PDF: (style, text) lines where style is "h1", "h2", "p", "bold" or "italic"."""
  from reportlab.lib.pagesizes import letter
  from reportlab.lib.styles import getSampleStyleSheet
  from reportlab.platypus import Image as FlowImage, Paragraph, SimpleDocTemplate, Spacer, Table

  styles = getSampleStyleSheet()
  story = []
  for style, text in lines:
    if style == "h1":
      story.append(Paragraph(text, styles["Heading1"]))
    elif style == "h2":
      story.append(Paragraph(text, styles["Heading2"]))
    elif style == "bold":
      story.append(Paragraph(f"<b>{text}</b> and then plain words follow here.", styles["BodyText"]))
    elif style == "italic":
      story.append(Paragraph(f"Some words in <i>{text}</i> and the rest plain.", styles["BodyText"]))
    else:
      story.append(Paragraph(text, styles["BodyText"]))
    story.append(Spacer(1, 6))
  if table:
    story.append(Table([["Word", "Meaning"], ["agape", "love"], ["charis", "grace"]], style=[("GRID", (0, 0), (-1, -1), 0.5, "black")]))
  if picture:
    story.append(FlowImage(io.BytesIO(picture_bytes()), width=120, height=80))
  SimpleDocTemplate(str(path), pagesize=letter).build(story)
  return path


def make_scanned_pdf(path: Path, lines: list[str]) -> Path:
  """A PDF of a picture of a page (no text in it), as a scanner makes."""
  from PIL import ImageFont

  page = Image.new("RGB", (1700, 2200), "white")
  draw = ImageDraw.Draw(page)
  try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Times New Roman.ttf", 44)
  except OSError:
    font = ImageFont.load_default(size=44)
  for index, line in enumerate(lines):
    draw.text((150, 200 + index * 80), line, fill="black", font=font)
  page.save(path, "PDF", resolution=200)
  return path

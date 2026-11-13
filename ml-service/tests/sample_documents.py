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


def make_epub(path: Path, version: int = 3, locked: bool = False, font_obfuscation: bool = False) -> Path:
  """An ebook: two parts with chapters in three pages, a cover picture inside an <svg>, a note link, a heading
  the contents does not name, and its table of contents as nav.xhtml (version 3) or toc.ncx (version 2). The
  second chapter's page has no heading of its own: the contents gives it one. locked adds an encryption file
  as a DRM lock does; font_obfuscation adds one that only hides a font (not a lock)."""
  import zipfile

  page = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>x</title>
<style>p {{ color: red }}</style></head><body>{body}</body></html>"""
  cover = page.format(body='<div><svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
                           '<image xlink:href="../images/cover.png"/></svg></div>')
  one = page.format(body='<section><h1 id="part-1">Part One</h1><h2 id="chapter-1">Chapter 1</h2>'
                         '<p>The words of <b>grace</b> and <i>mercy</i>, as in John 3:16.<a epub:type="noteref" href="notes.xhtml#n1">1</a></p>'
                         '<h2>A heading inside the chapter</h2><p>More of the first chapter.</p>'
                         '<ul><li>First point</li><li>Second point</li></ul></section>')
  two = page.format(body='<div class="chapter"><p>The second chapter has no heading of its own.</p>'
                         '<p><img src="../images/cover.png" alt="A green picture"/></p></div>')
  three = page.format(body='<h1 id="part-2">Part Two</h1><h2 id="chapter-3">Chapter 3</h2><p>The third chapter.</p>')
  nav = page.format(body='<nav epub:type="toc"><ol>'
                         '<li><a href="text/one.xhtml#part-1">Part One</a><ol>'
                         '<li><a href="text/one.xhtml#chapter-1">Chapter 1</a></li><li><a href="text/two.xhtml">Chapter 2</a></li></ol></li>'
                         '<li><a href="text/three.xhtml#part-2">Part Two</a><ol><li><a href="text/three.xhtml#chapter-3">Chapter 3</a></li></ol></li>'
                         '</ol></nav>')
  ncx = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><navMap>
<navPoint id="p1"><navLabel><text>Part One</text></navLabel><content src="text/one.xhtml#part-1"/>
  <navPoint id="c1"><navLabel><text>Chapter 1</text></navLabel><content src="text/one.xhtml#chapter-1"/></navPoint>
  <navPoint id="c2"><navLabel><text>Chapter 2</text></navLabel><content src="text/two.xhtml"/></navPoint></navPoint>
<navPoint id="p2"><navLabel><text>Part Two</text></navLabel><content src="text/three.xhtml#part-2"/>
  <navPoint id="c3"><navLabel><text>Chapter 3</text></navLabel><content src="text/three.xhtml#chapter-3"/></navPoint></navPoint>
</navMap></ncx>"""
  nav_item = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>' if version == 3 else ""
  ncx_item = '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>' if version == 2 else ""
  package = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{version}.0" unique-identifier="id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>A Sample Ebook</dc:title></metadata>
<manifest>{nav_item}{ncx_item}
<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>
<item id="one" href="text/one.xhtml" media-type="application/xhtml+xml"/>
<item id="two" href="text/two.xhtml" media-type="application/xhtml+xml"/>
<item id="three" href="text/three.xhtml" media-type="application/xhtml+xml"/>
<item id="picture" href="images/cover.png" media-type="image/png"/>
</manifest>
<spine{' toc="ncx"' if version == 2 else ''}><itemref idref="cover"/><itemref idref="one"/><itemref idref="two"/><itemref idref="three"/></spine>
</package>"""
  with zipfile.ZipFile(path, "w") as archive:
    archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    archive.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""")
    archive.writestr("OEBPS/content.opf", package)
    archive.writestr("OEBPS/text/cover.xhtml", cover)
    archive.writestr("OEBPS/text/one.xhtml", one)
    archive.writestr("OEBPS/text/two.xhtml", two)
    archive.writestr("OEBPS/text/three.xhtml", three)
    archive.writestr("OEBPS/images/cover.png", picture_bytes())
    if version == 3:
      archive.writestr("OEBPS/nav.xhtml", nav)
    else:
      archive.writestr("OEBPS/toc.ncx", ncx)
    algorithm = "http://www.idpf.org/2008/embedding" if font_obfuscation else "http://www.w3.org/2001/04/xmlenc#aes128-cbc"
    if locked or font_obfuscation:
      archive.writestr("META-INF/encryption.xml", f"""<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
<enc:EncryptedData><enc:EncryptionMethod Algorithm="{algorithm}"/><enc:CipherData><enc:CipherReference URI="OEBPS/text/one.xhtml"/></enc:CipherData></enc:EncryptedData>
</encryption>""")
  return path

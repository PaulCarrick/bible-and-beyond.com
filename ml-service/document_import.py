"""Reading PDF, Word (.docx) and EPUB files for the uploads of commentaries, devotionals, Other books and song words,
keeping as much of their formatting as the site can show.

A document becomes HTML: paragraphs, headings, bold, italic, underline, superscript and subscript, lists,
quotations, tables, pictures and footnotes. Fonts, colours, columns and page layout are not kept.

  Word   through mammoth (styles become headings, lists, tables, footnotes and pictures).
  EPUB   an ebook: a zip of web pages, read in the order of its spine; its table of contents (nav.xhtml or
         toc.ncx) says which headings are parts and chapters, and its pictures are kept. A locked (DRM) ebook is
         refused. Kindle files (.mobi, .azw, .azw3, .kfx) are not read: an unlocked one can be converted to
         EPUB with Calibre first.
  PDF    through pdfplumber: the fonts and sizes of the words give bold, italic, superscript and headings; its
         tables, its pictures (drawn with pypdfium2) and its bookmarks (pypdf) are kept. A page with no text (a
         scan) is read by Tesseract OCR, which gives the words and paragraphs only, and a warning is shown.

The HTML is cleaned with an allowlist (LibraryCleaner) when it is kept, and its plain text (html_to_text) is
what the search index reads. Pictures are saved as files in data/library-images/ (named by their content) and
served at /library-image/<name>. split_document cuts a document into the parts the uploads need: chapters,
days, or commentary notes (see library_upload.py).
"""

import hashlib
import io
import os
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from contact import DROPPED_WITH_CONTENT, SAFE_LINK, _Cleaner, clean_message_html

DOCUMENT_TYPES = (".pdf", ".docx", ".epub")
KINDLE_TYPES = (".mobi", ".azw", ".azw3", ".kfx", ".prc")
KINDLE_ADVICE = (
  "Kindle files (.mobi, .azw, .azw3, .kfx) cannot be read here. If the book is not locked (one you made or a "
  "free one), convert it to EPUB with the free Calibre app and upload the .epub. Books bought from Amazon are "
  "locked and cannot be used."
)
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
MAX_PAGES = 2000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
OCR_RESOLUTION = 300
IMAGE_NAME = re.compile(r"^[0-9a-f]{20}\.(png|jpg|gif|webp)$")
IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
IMAGE_MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "blockquote", "pre", "img", "hr", "div")


class DocumentProblem(ValueError):
  """The document cannot be read; the text says why and is fit to show the administrator."""


@dataclass
class Document:
  html: str  # the whole document, not yet cleaned (headings h1 to h6 mark its parts)
  images: dict = field(default_factory=dict)  # file name -> bytes, saved when the document is imported
  footnotes: dict = field(default_factory=dict)  # Word footnote number -> its HTML, put at the end of its chapter
  warnings: list = field(default_factory=list)
  ocr_pages: int = 0


# --- where pictures are kept ---------------------------------------------------------------------------


def images_folder() -> Path:
  return Path(os.environ.get("LIBRARY_IMAGES_FOLDER") or Path(__file__).resolve().parent / "data" / "library-images")


def image_name(data: bytes, extension: str) -> str:
  return f"{hashlib.sha256(data).hexdigest()[:20]}.{extension}"


def save_images(images: dict) -> None:
  folder = images_folder()
  folder.mkdir(parents=True, exist_ok=True)
  for name, data in images.items():
    target = folder / name
    if not target.exists():
      temporary = folder / f".{name}.new"
      temporary.write_bytes(data)
      temporary.replace(target)


def image_file(name: str) -> tuple[Path, str] | None:
  """The picture of that name and its media type, or None."""
  if not IMAGE_NAME.match(name):
    return None
  path = images_folder() / name
  return (path, IMAGE_MEDIA_TYPES[name.rsplit(".", 1)[1]]) if path.is_file() else None


def _picture(data: bytes, media_type: str, images: dict, warnings: list) -> str | None:
  """Adds a picture to the document's pictures and gives its address, or None when it cannot be kept."""
  extension = IMAGE_TYPES.get(media_type)
  if extension is None:
    try:
      from PIL import Image

      with Image.open(io.BytesIO(data)) as picture:
        converted = io.BytesIO()
        picture.convert("RGBA" if picture.mode in ("RGBA", "LA", "P") else "RGB").save(converted, "PNG")
      data, extension = converted.getvalue(), "png"
    except Exception:
      warnings.append(f"A picture of type {media_type or 'unknown'} could not be kept.")
      return None
  if len(data) > MAX_IMAGE_BYTES:
    warnings.append("A picture larger than 8 MB was left out.")
    return None
  name = image_name(data, extension)
  images[name] = data
  return f"/library-image/{name}"


# --- Word ----------------------------------------------------------------------------------------------

DOCX_STYLES = """
u => u
strike => s
p[style-name='Title'] => p.title:fresh
p[style-name='Subtitle'] => p.subtitle:fresh
p[style-name='Quote'] => blockquote > p:fresh
p[style-name='Intense Quote'] => blockquote > p:fresh
p[style-name='Block Text'] => blockquote > p:fresh
"""


def convert_docx(path: Path) -> Document:
  import mammoth

  document = Document("")

  def keep_image(image):
    with image.open() as stream:
      data = stream.read()
    address = _picture(data, image.content_type or "", document.images, document.warnings)
    return {"src": address, "alt": image.alt_text or ""} if address else {}

  try:
    with open(path, "rb") as file:
      result = mammoth.convert_to_html(file, style_map=DOCX_STYLES, convert_image=mammoth.images.img_element(keep_image))
  except Exception as error:
    raise DocumentProblem("The Word file could not be read. Save it again as a .docx file.") from error
  soup = BeautifulSoup(result.value, "html.parser")
  # Footnotes: mammoth puts them in a list at the end; each is moved to the end of the chapter that cites it.
  for item in soup.select('li[id^="footnote-"], li[id^="endnote-"]'):
    number = item["id"].split("-", 1)[1]
    for back_link in item.select('a[href^="#footnote-ref-"], a[href^="#endnote-ref-"]'):
      back_link.decompose()
    content = "".join(str(child) for child in item.contents).strip()
    document.footnotes[number] = content
    parent = item.parent
    item.decompose()
    if parent and parent.name == "ol" and not parent.find("li"):
      parent.decompose()
  for reference in soup.select('a[href^="#footnote-"], a[href^="#endnote-"]'):
    number = reference["href"].split("-", 1)[1]
    marker = soup.new_tag("sup")
    marker["data-footnote"] = number
    marker.string = f"[{number}]"
    holder = reference.parent if reference.parent and reference.parent.name == "sup" else reference
    holder.replace_with(marker)
  document.html = str(soup)
  return document


# --- PDF -----------------------------------------------------------------------------------------------


def _style_of(fontname: str) -> tuple[bool, bool]:
  name = (fontname or "").split("+")[-1].lower()
  bold = any(word in name for word in ("bold", "black", "heavy", "semibold", "demi"))
  italic = any(word in name for word in ("italic", "oblique"))
  return bold, italic


@dataclass
class _Line:
  top: float
  bottom: float
  x0: float
  x1: float
  size: float
  words: list  # (text, bold, italic, superscript)
  page: int

  @property
  def text(self):
    return " ".join(word[0] for word in self.words)

  @property
  def all_bold(self):
    return all(word[1] for word in self.words if word[0].strip())


def _lines_of(words: list, page_number: int) -> list[_Line]:
  """Words (from pdfplumber or OCR) grouped into lines, in reading order (one column)."""
  lines: list[_Line] = []
  if words and "line_key" in words[0]:
    groups: dict = {}
    for word in words:
      groups.setdefault(word["line_key"], []).append(word)
    for group in groups.values():
      lines.append(_Line(min(word["top"] for word in group), max(word["bottom"] for word in group), min(word["x0"] for word in group),
                         max(word["x1"] for word in group), 0, group, page_number))
  else:
    for word in sorted(words, key=lambda word: (word["top"], word["x0"])):
      height = max(word["bottom"] - word["top"], 0.1)
      for line in reversed(lines[-4:]):
        overlap = min(line.bottom, word["bottom"]) - max(line.top, word["top"])
        if overlap >= 0.5 * min(height, line.bottom - line.top):
          line.top, line.bottom = min(line.top, word["top"]), max(line.bottom, word["bottom"])
          line.x0, line.x1 = min(line.x0, word["x0"]), max(line.x1, word["x1"])
          line.words.append(word)
          break
      else:
        lines.append(_Line(word["top"], word["bottom"], word["x0"], word["x1"], 0, [word], page_number))
  lines.sort(key=lambda line: (line.top, line.x0))
  for line in lines:
    sizes = Counter(round(word.get("size") or (word["bottom"] - word["top"]), 1) for word in line.words)
    line.size = sizes.most_common(1)[0][0]
    styled = []
    for word in sorted(line.words, key=lambda word: word["x0"]):
      bold, italic = _style_of(word.get("fontname", ""))
      size = word.get("size") or (word["bottom"] - word["top"])
      superscript = size < line.size * 0.8 and word["bottom"] < line.bottom - size * 0.25
      styled.append((word["text"], bold, italic, superscript))
    line.words = styled
  return lines


def _inline_html(words: list) -> str:
  """A run of styled words as HTML, joining words of the same style."""
  pieces = []
  for index, (text, bold, italic, superscript) in enumerate(words):
    piece = escape(text)
    if superscript:
      piece = f"<sup>{piece}</sup>"
    if italic:
      piece = f"<em>{piece}</em>"
    if bold:
      piece = f"<strong>{piece}</strong>"
    pieces.append(("" if index == 0 else " ") + piece)
  html = "".join(pieces).strip()
  # Neighbouring tags of the same kind join up ("<strong>a</strong> <strong>b</strong>").
  for tag in ("strong", "em"):
    html = html.replace(f"</{tag}> <{tag}>", " ")
  return html


def _paragraphs(lines: list[_Line], body_size: float, heading_sizes: list[float]) -> list[str]:
  """Lines grouped into paragraphs and headings, as HTML blocks."""
  blocks = []
  current: list[_Line] = []

  def flush():
    if not current:
      return
    words = []
    for index, line in enumerate(current):
      line_words = list(line.words)
      # A word broken across lines with a hyphen is joined again.
      if words and words[-1][0].endswith("-") and line_words and line_words[0][0][:1].islower():
        last = words.pop()
        line_words[0] = (last[0][:-1] + line_words[0][0], *line_words[0][1:])
      words.extend(line_words)
    blocks.append(f"<p>{_inline_html(words)}</p>")
    current.clear()

  gaps = [following.top - line.bottom for line, following in zip(lines, lines[1:]) if following.page == line.page and following.top > line.bottom]
  usual_gap = max(sorted(gaps)[len(gaps) // 10], body_size * 0.15) if gaps else body_size * 0.4
  left = Counter(round(line.x0) for line in lines).most_common(1)[0][0] if lines else 0
  width = max((line.x1 for line in lines), default=0) - left
  for index, line in enumerate(lines):
    text = line.text.strip()
    if not text:
      continue
    level = next((rank + 1 for rank, size in enumerate(heading_sizes) if abs(line.size - size) < 0.6), None)
    if level is None and line.all_bold and len(text) < 90 and not text.endswith((".", ",", ";")):
      previous_gap = line.top - lines[index - 1].bottom if index else 99
      following_gap = lines[index + 1].top - line.bottom if index + 1 < len(lines) else 99
      if previous_gap > usual_gap * 1.5 and following_gap > usual_gap * 1.2:
        level = len(heading_sizes) + 1
    if level is not None:
      flush()
      blocks.append(f"<h{min(level, 4)}>{escape(text)}</h{min(level, 4)}>")
      continue
    if current:
      previous = current[-1]
      gap = line.top - previous.bottom if line.page == previous.page else usual_gap
      indented = line.x0 - left > body_size * 1.2
      short_before = width and previous.x1 - left < width * 0.75
      if gap > usual_gap * 1.5 + 1 or indented or short_before:
        flush()
    current.append(line)
  flush()
  return blocks


def _repeated_margins(pages_lines: list[list[_Line]], page_heights: list[float]) -> set:
  """Running heads and page numbers: short lines near the top or bottom that repeat on many pages."""
  counts = Counter()
  for lines, height in zip(pages_lines, page_heights):
    seen = set()
    for line in lines:
      if line.top < height * 0.08 or line.bottom > height * 0.92:
        key = re.sub(r"\d+", "#", line.text.strip().lower())
        if key not in seen:
          seen.add(key)
          counts[key] += 1
  limit = max(3, len(pages_lines) // 3)
  return {key for key, count in counts.items() if count >= limit or re.fullmatch(r"[#ivxlc\s.\-–]*", key)}


def _ocr_words(page) -> list[dict]:
  import pytesseract

  picture = page.to_image(resolution=OCR_RESOLUTION).original
  data = pytesseract.image_to_data(picture, output_type=pytesseract.Output.DICT)
  scale = 72 / OCR_RESOLUTION
  words = []
  for index, text in enumerate(data["text"]):
    if not text.strip() or float(data["conf"][index]) < 30:
      continue
    left, top, width, height = (data[key][index] * scale for key in ("left", "top", "width", "height"))
    key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
    words.append({"text": text, "x0": left, "x1": left + width, "top": top, "bottom": top + height, "size": height, "fontname": "", "line_key": key})
  # A line's size is the middle of its words' heights (single letters are taller or shorter than words).
  by_line: dict = {}
  for word in words:
    by_line.setdefault(word["line_key"], []).append(word["size"])
  for word in words:
    sizes = sorted(by_line[word["line_key"]])
    word["size"] = round(sizes[len(sizes) // 2] * 2) / 2
  return words


def ocr_available() -> bool:
  return shutil.which("tesseract") is not None


def convert_pdf(path: Path) -> Document:
  import pdfplumber
  from pypdf import PdfReader

  document = Document("")
  try:
    pdf = pdfplumber.open(path)
  except Exception as error:
    raise DocumentProblem("The PDF could not be read. It may be damaged or protected by a password.") from error
  with pdf:
    if len(pdf.pages) > MAX_PAGES:
      raise DocumentProblem(f"The PDF has more than {MAX_PAGES} pages.")
    pages_lines, page_heights, page_tables, page_images = [], [], [], []
    for number, page in enumerate(pdf.pages):
      page_heights.append(page.height)
      tables = []
      try:
        tables = [table for table in page.find_tables() if table.bbox[3] - table.bbox[1] > 10]
      except Exception:
        tables = []
      def outside_tables(word):
        return not any(box[0] - 1 <= word["x0"] and word["x1"] <= box[2] + 1 and box[1] - 1 <= word["top"] and word["bottom"] <= box[3] + 1 for box in (table.bbox for table in tables))
      words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False, use_text_flow=True)
      if not words and page.images:
        if not ocr_available():
          raise DocumentProblem("This PDF is a scan (pictures of pages, with no text), and text recognition (Tesseract) is not installed on this server.")
        words = _ocr_words(page)
        document.ocr_pages += 1
        page_images.append([])
      else:
        pictures = []
        for image in page.images:
          box = (max(image["x0"], 0), max(image["top"], 0), min(image["x1"], page.width), min(image["bottom"], page.height))
          if box[2] - box[0] < 40 or box[3] - box[1] < 40:
            continue
          try:
            rendered = page.crop(box).to_image(resolution=150).original
            buffer = io.BytesIO()
            rendered.save(buffer, "PNG")
            address = _picture(buffer.getvalue(), "image/png", document.images, document.warnings)
          except Exception:
            address = None
          if address:
            pictures.append((box[1], f'<p><img src="{address}" alt=""></p>'))
        page_images.append(pictures)
      page_tables.append([(table.bbox[1], _table_html(table)) for table in tables])
      pages_lines.append(_lines_of([word for word in words if outside_tables(word)], number))
    repeated = _repeated_margins(pages_lines, page_heights)
    all_lines = [
      line for lines, height in zip(pages_lines, page_heights) for line in lines
      if not ((line.top < height * 0.08 or line.bottom > height * 0.92) and re.sub(r"\d+", "#", line.text.strip().lower()) in repeated)
    ]
    if not all_lines and not any(page_tables):
      raise DocumentProblem("No text was found in the PDF.")
    sizes = Counter()
    for line in all_lines:
      sizes[line.size] += len(line.text)
    body_size = sizes.most_common(1)[0][0] if sizes else 11
    bigger = sorted({size for size in sizes if size >= body_size * 1.15 and sizes[size] < sum(sizes.values()) * 0.2}, reverse=True)
    heading_sizes = bigger[:3]
    # Blocks page by page, with the tables and pictures placed where they are on the page.
    blocks = []
    for number in range(len(pages_lines)):
      lines = [line for line in all_lines if line.page == number]
      placed = [(line.top, "line", line) for line in lines]
      placed += [(top, "html", html) for top, html in page_tables[number] + page_images[number]]
      placed.sort(key=lambda item: item[0])
      run: list[_Line] = []
      for _top, kind, value in placed:
        if kind == "line":
          run.append(value)
        else:
          blocks += _paragraphs(run, body_size, heading_sizes) if run else []
          run = []
          blocks.append(value)
      blocks += _paragraphs(run, body_size, heading_sizes) if run else []
    blocks = _join_across_pages(blocks)
    document.html = "\n".join(blocks)
  if document.ocr_pages:
    document.warnings.append(f"{document.ocr_pages} page(s) were scans read by text recognition: check the text for mistakes. Their bold and italics are not kept.")
  # Bookmarks: when the PDF has them, they mark the parts and chapters.
  try:
    outline = _outline(PdfReader(str(path)))
  except Exception:
    outline = []
  if outline:
    document.html = _apply_outline(document.html, outline)
  return document


def _join_across_pages(blocks: list[str]) -> list[str]:
  """A paragraph cut by a page break (one that ends without a stop and a next that starts in lower case) is
  joined again."""
  joined = []
  for block in blocks:
    if joined and joined[-1].startswith("<p>") and block.startswith("<p>") and "<img" not in block and "<img" not in joined[-1]:
      previous_text = re.sub(r"<[^>]+>", "", joined[-1][3:-4]).rstrip()
      next_text = re.sub(r"<[^>]+>", "", block[3:-4]).lstrip()
      if previous_text and next_text and previous_text[-1] not in ".!?:;”\"’)" and next_text[:1].islower():
        joined[-1] = joined[-1][:-4] + " " + block[3:]
        continue
    joined.append(block)
  return joined


def _table_html(table) -> str:
  rows = table.extract() or []
  html = ["<table>"]
  for index, row in enumerate(rows):
    cell_tag = "th" if index == 0 and len(rows) > 1 else "td"
    cells = "".join(f"<{cell_tag}>{escape(' '.join((cell or '').split()))}</{cell_tag}>" for cell in row)
    html.append(f"<tr>{cells}</tr>")
  html.append("</table>")
  return "".join(html)


def _outline(reader) -> list[tuple[int, str]]:
  """The PDF's bookmarks as (level from 1, title), in order."""
  found = []

  def walk(items, level):
    for item in items:
      if isinstance(item, list):
        walk(item, level + 1)
      else:
        title = " ".join(str(getattr(item, "title", "") or "").split())
        if title:
          found.append((level, title))

  walk(reader.outline, 1)
  return found


def _normal(text: str) -> str:
  return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _apply_outline(html: str, outline: list[tuple[int, str]]) -> str:
  """Makes the blocks that carry a bookmark's title headings of the bookmark's level (and other headings found
  from the fonts one level deeper), when most of the bookmarks are found in the text."""
  soup = BeautifulSoup(html, "html.parser")
  blocks = [block for block in soup.children if isinstance(block, Tag)]
  marked = 0
  position = 0
  for level, title in outline:
    wanted = _normal(title)
    for index in range(position, len(blocks)):
      if _normal(blocks[index].get_text(" ")) == wanted:
        heading = soup.new_tag(f"h{min(level, 4)}")
        heading.string = blocks[index].get_text(" ").strip()
        heading["data-bookmark"] = "1"
        blocks[index].replace_with(heading)
        blocks[index] = heading
        position = index + 1
        marked += 1
        break
  if marked < max(1, len(outline) // 2):
    return html
  deepest = max(level for level, _ in outline)
  for block in blocks:
    if re.fullmatch(r"h[1-6]", block.name or "") and not block.get("data-bookmark"):
      block.name = f"h{min(deepest + 1, 4)}"
  for block in blocks:
    if block.get("data-bookmark"):
      del block["data-bookmark"]
  return str(soup)


# --- EPUB ----------------------------------------------------------------------------------------------

# Font obfuscation (EPUB's own and Adobe's) is not a lock on the text; any other encryption is.
FONT_OBFUSCATION = {"http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC"}
EPUB_PAGE_TYPES = {"application/xhtml+xml", "text/html"}
EPUB_IMAGE_TYPES = {
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
  ".svg": "image/svg+xml",
}
EPUB_LOCKED = (
  "This ebook is locked (copy protection, DRM), so its text cannot be read. Only unlocked ebooks can be "
  "uploaded: ones you made, free ones, or ones sold without DRM."
)


def _local_name(tag: str) -> str:
  return tag.rsplit("}", 1)[-1]


def _epub_path(base: str, href: str) -> str:
  """The archive path of a link found in the file at base (links are relative and may be %-encoded)."""
  import posixpath
  from urllib.parse import unquote

  return posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(href.split("#", 1)[0]))).lstrip("/")


def _epub_toc(archive, names: set, package_path: str, package, manifest: dict) -> list[tuple[int, str, str, str]]:
  """The table of contents: (level from 1, title, archive path, fragment), from nav.xhtml (EPUB 3) or toc.ncx
  (EPUB 2). Empty when there is none."""
  from defusedxml import ElementTree

  entries = []
  navigation = next((item for item in manifest.values() if "nav" in item["properties"].split()), None)
  if navigation and navigation["path"] in names:
    soup = BeautifulSoup(archive.read(navigation["path"]), "html.parser")
    nav = next(
      (element for element in soup.find_all("nav") if "toc" in (element.get("epub:type") or element.get("role") or "")),
      soup.find("nav"),
    )

    def walk(listing, level):
      for item in listing.find_all("li", recursive=False):
        link = item.find("a", recursive=False) or item.find("a")
        if link and link.get("href"):
          entries.append((level, " ".join(link.get_text(" ").split()), _epub_path(navigation["path"], link["href"]),
                          link["href"].split("#", 1)[1] if "#" in link["href"] else ""))
        inner = item.find("ol", recursive=False)
        if inner:
          walk(inner, level + 1)

    if nav and nav.find("ol"):
      walk(nav.find("ol"), 1)
  if entries:
    return entries
  spine = next((element for element in package.iter() if _local_name(element.tag) == "spine"), None)
  ncx = manifest.get(spine.get("toc")) if spine is not None and spine.get("toc") else None
  ncx = ncx or next((item for item in manifest.values() if item["media_type"] == "application/x-dtbncx+xml"), None)
  if ncx and ncx["path"] in names:
    root = ElementTree.fromstring(archive.read(ncx["path"]))

    def walk_points(element, level):
      for point in element:
        if _local_name(point.tag) != "navPoint":
          continue
        label = next((node for node in point.iter() if _local_name(node.tag) == "text"), None)
        content = next((node for node in point if _local_name(node.tag) == "content"), None)
        if content is not None and content.get("src"):
          source = content.get("src")
          entries.append((level, " ".join((label.text or "").split()) if label is not None else "",
                          _epub_path(ncx["path"], source), source.split("#", 1)[1] if "#" in source else ""))
        walk_points(point, level + 1)

    navigation_map = next((node for node in root.iter() if _local_name(node.tag) == "navMap"), None)
    if navigation_map is not None:
      walk_points(navigation_map, 1)
  return entries


def convert_epub(path: Path) -> Document:
  import zipfile

  from defusedxml import ElementTree

  document = Document("")
  try:
    archive = zipfile.ZipFile(path)
  except zipfile.BadZipFile as error:
    raise DocumentProblem("The EPUB file could not be read (it is not a complete ebook).") from error
  with archive:
    names = set(archive.namelist())
    # A lock: Adobe's rights file, or encryption other than font obfuscation.
    if "META-INF/rights.xml" in names:
      raise DocumentProblem(EPUB_LOCKED)
    if "META-INF/encryption.xml" in names:
      try:
        encryption = ElementTree.fromstring(archive.read("META-INF/encryption.xml"))
      except Exception as error:
        raise DocumentProblem(EPUB_LOCKED) from error
      methods = {element.get("Algorithm") for element in encryption.iter() if _local_name(element.tag) == "EncryptionMethod"}
      if methods - FONT_OBFUSCATION:
        raise DocumentProblem(EPUB_LOCKED)
    try:
      container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
      package_path = next(element.get("full-path") for element in container.iter() if _local_name(element.tag) == "rootfile")
      package = ElementTree.fromstring(archive.read(package_path))
    except Exception as error:
      raise DocumentProblem("The EPUB file could not be read (its list of contents is missing or damaged).") from error

    manifest = {}
    for element in package.iter():
      if _local_name(element.tag) == "item" and element.get("id") and element.get("href"):
        manifest[element.get("id")] = {
          "path": _epub_path(package_path, element.get("href")),
          "media_type": element.get("media-type") or "",
          "properties": element.get("properties") or "",
        }
    pages = []
    for element in package.iter():
      if _local_name(element.tag) == "itemref" and element.get("linear") != "no":
        item = manifest.get(element.get("idref"))
        if item and item["media_type"] in EPUB_PAGE_TYPES and item["path"] in names:
          pages.append(item["path"])
    if not pages:
      raise DocumentProblem("The EPUB file has no pages to read.")
    media_types = {item["path"]: item["media_type"] for item in manifest.values()}

    # The table of contents decides the parts and chapters: (path, fragment) -> (level, title).
    toc = {}
    for level, title, target, fragment in _epub_toc(archive, names, package_path, package, manifest):
      toc.setdefault((target, fragment), (min(level, 4), title))

    pieces = []
    named_pages = {target for target, _fragment in toc}
    reached_contents = not named_pages
    for page in pages:
      soup = BeautifulSoup(archive.read(page), "html.parser")
      body = soup.body or soup
      # Pages before the first one the contents names that hold no words (a cover) are left out.
      reached_contents = reached_contents or page in named_pages
      if not reached_contents and not body.get_text(strip=True):
        document.warnings.append("A cover page (a picture with no words) before the contents was left out.")
        continue
      for element in body.find_all(["script", "style", "head", "title", "link", "meta"]):
        element.decompose()
      # Pictures, including the <image> inside an <svg> (a cover, say), become the site's own pictures.
      for element in body.find_all(["img", "image"]):
        source = element.get("src") or element.get("xlink:href") or element.get("href") or ""
        picture_path = _epub_path(page, source) if source and not source.startswith("data:") else ""
        address = None
        if picture_path in names:
          media_type = media_types.get(picture_path) or EPUB_IMAGE_TYPES.get(Path(picture_path).suffix.lower(), "")
          if media_type != "image/svg+xml":
            address = _picture(archive.read(picture_path), media_type, document.images, document.warnings)
        holder = element.find_parent("svg") if element.name == "image" else None
        if address:
          picture = soup.new_tag("img", src=address, alt=element.get("alt") or "")
          (holder or element).replace_with(picture)
        else:
          (holder or element).decompose()
      for element in body.find_all("svg"):
        element.decompose()
      # Links inside the book (notes, the contents) are not addresses on this site: their words stay.
      for link in body.find_all("a"):
        if not SAFE_LINK.match(link.get("href") or ""):
          link.unwrap()

      if toc:
        # Headings the contents names get its level; the others stay inside their chapter (h3, h4).
        marked = set()
        for heading in body.find_all(re.compile(r"^h[1-6]$")):
          entry = toc.get((page, heading.get("id") or ""))
          if entry is None:
            entry = next((value for (target, fragment), value in toc.items()
                          if target == page and fragment == "" and _normal(value[1]) == _normal(heading.get_text(" "))), None)
          if entry:
            heading.name = f"h{entry[0]}"
            marked.add(entry)
          else:
            heading.name = "h3" if int(heading.name[1]) <= 3 else "h4"
        # An entry that points at something other than a heading (or at the page itself) gets a heading there.
        for (target, fragment), (level, title) in toc.items():
          if target != page or (level, title) in marked or not title:
            continue
          anchor = body.find(id=fragment) if fragment else None
          if fragment and anchor is None:
            continue
          heading = soup.new_tag(f"h{level}")
          heading.string = title
          if anchor is not None:
            anchor.insert_before(heading)
          else:
            body.insert(0, heading)
          marked.add((level, title))
      pieces.append("".join(str(child) for child in body.contents))
  document.html = "\n".join(pieces)
  return document


# --- reading any document ------------------------------------------------------------------------------


def convert(path: Path, original_name: str) -> Document:
  extension = Path(original_name).suffix.lower()
  if extension in KINDLE_TYPES:
    raise DocumentProblem(KINDLE_ADVICE)
  if extension not in DOCUMENT_TYPES:
    raise DocumentProblem("The document must be a PDF (.pdf), a Word document (.docx) or an ebook (.epub).")
  size = path.stat().st_size
  if size == 0:
    raise DocumentProblem("The file is empty.")
  if size > MAX_DOCUMENT_BYTES:
    raise DocumentProblem(f"The file is larger than {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB.")
  with open(path, "rb") as file:
    start = file.read(8)
  if extension == ".pdf" and not start.startswith(b"%PDF"):
    raise DocumentProblem("The file is not really a PDF.")
  if extension == ".docx" and not start.startswith(b"PK"):
    raise DocumentProblem("The file is not really a Word document (.docx). An old .doc file must be saved again as .docx.")
  if extension == ".epub" and not start.startswith(b"PK"):
    raise DocumentProblem("The file is not really an EPUB ebook.")
  if extension == ".epub":
    return convert_epub(path)
  return convert_pdf(path) if extension == ".pdf" else convert_docx(path)


# --- cleaning and plain text ---------------------------------------------------------------------------

LIBRARY_TAGS = {
  "p", "br", "strong", "b", "em", "i", "s", "u", "a", "blockquote", "pre", "code", "ul", "ol", "li",
  "h1", "h2", "h3", "h4", "sup", "sub", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
  "img", "hr", "cite",
}
VOID_TAGS = {"img", "hr"}
SPAN = re.compile(r"^[1-9][0-9]?$")


class LibraryCleaner(_Cleaner):
  """The formatting a document may keep: the editor's, plus headings, superscript, tables and the site's own
  pictures (an address /library-image/<name>; any other picture is dropped)."""

  allowed_tags = LIBRARY_TAGS

  def handle_starttag(self, tag, attributes):
    if tag in VOID_TAGS:
      if not self.skip_depth and tag in self.allowed_tags:
        opening = self.opening(tag, dict(attributes))
        if opening:
          self.parts.append(opening)
      return
    super().handle_starttag(tag, attributes)

  def opening(self, tag, attributes):
    if tag == "img":
      source = (attributes.get("src") or "").strip()
      if not source.startswith("/library-image/") or not IMAGE_NAME.match(source.rsplit("/", 1)[1]):
        return None
      return f'<img src="{escape(source, quote=True)}" alt="{escape(attributes.get("alt") or "", quote=True)}">'
    if tag in ("td", "th"):
      spans = "".join(
        f' {name}="{attributes[name]}"' for name in ("colspan", "rowspan") if SPAN.match(attributes.get(name) or "")
      )
      return f"<{tag}{spans}>"
    if tag == "b":
      return "<strong>"
    if tag == "i":
      return "<em>"
    return super().opening(tag, attributes)

  def handle_endtag(self, tag):
    super().handle_endtag(tag)


# Control characters (all but tab, line feed and carriage return): a PDF can give NUL for a glyph it has no
# character for (a hyphen in one of the owner's PDFs), and PostgreSQL refuses NUL in text.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_library_html(html: str) -> str:
  cleaned = clean_message_html(CONTROL_CHARACTERS.sub("", html), LibraryCleaner)
  # <b> and <i> open as <strong> and <em>; close them the same way.
  cleaned = cleaned.replace("</b>", "</strong>").replace("</i>", "</em>")
  # Empty paragraphs (blank lines) are dropped.
  return re.sub(r"<p>\s*(<br>\s*)*</p>", "", cleaned).strip()


TEXT_BLOCKS = {"p", "h1", "h2", "h3", "h4", "li", "tr", "blockquote", "pre", "caption", "hr", "br"}


def html_to_text(html: str) -> str:
  """The plain text of cleaned HTML, a paragraph (or list point, table row, heading) to a line, with a blank
  line between them: what the search reads and the daily emails send."""
  soup = BeautifulSoup(html, "html.parser")
  # A table row is one line: the paragraphs inside its cells are not lines of their own.
  for cell in soup.find_all(["td", "th"]):
    for paragraph in cell.find_all("p"):
      paragraph.append(" ")
      paragraph.unwrap()
    cell.append(" ")
  for block in soup.find_all(TEXT_BLOCKS):
    block.append("\n\n")
  for item in soup.find_all("li"):
    item.insert(0, "• ")
  text = soup.get_text()
  lines = [" ".join(line.split()) for line in text.split("\n")]
  return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# --- cutting a document into parts ---------------------------------------------------------------------


def top_blocks(html: str) -> list[Tag]:
  """The document's top-level blocks (text loose at the top level becomes a paragraph)."""
  soup = BeautifulSoup(html, "html.parser")
  blocks = []
  for child in list(soup.children):
    if isinstance(child, NavigableString):
      if str(child).strip():
        paragraph = soup.new_tag("p")
        paragraph.string = str(child).strip()
        blocks.append(paragraph)
    elif isinstance(child, Tag):
      if child.name in ("div", "section", "article", "body", "html"):
        blocks += top_blocks("".join(str(grandchild) for grandchild in child.children))
      else:
        blocks.append(child)
  return blocks


def heading_level(block: Tag) -> int | None:
  return int(block.name[1]) if re.fullmatch(r"h[1-6]", block.name or "") and block.get_text(strip=True) else None


def blocks_html(blocks: list[Tag], footnotes: dict) -> str:
  """Blocks joined as HTML, with the footnotes they cite added at the end."""
  html = "".join(str(block) for block in blocks)
  cited = []
  for block in blocks:
    for marker in block.select("sup[data-footnote]"):
      if marker["data-footnote"] in footnotes and marker["data-footnote"] not in cited:
        cited.append(marker["data-footnote"])
  if cited:
    html += "<hr>" + "".join(f"<p><sup>[{number}]</sup> {_inline_footnote(footnotes[number])}</p>" for number in cited)
  return html


def _inline_footnote(html: str) -> str:
  """A footnote's HTML on one line (its own paragraphs run together)."""
  soup = BeautifulSoup(html, "html.parser")
  for paragraph in soup.find_all("p"):
    paragraph.unwrap()
  return str(soup).strip()


@dataclass
class Piece:
  """Part of a document: its place (set by the splitting) and its cleaned HTML and text."""
  html: str
  text: str
  title: str = ""


def piece_of(blocks: list[Tag], footnotes: dict, title: str = "") -> Piece | None:
  html = clean_library_html(blocks_html(blocks, footnotes))
  text = html_to_text(html)
  if not text and "<img" not in html and "<table" not in html:
    return None
  return Piece(html, text, title)


def heading_text(block: Tag) -> str:
  return " ".join(block.get_text(" ").split())

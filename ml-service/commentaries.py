"""Public-domain Bible commentaries ("Commentaries" link): download, load and look up.

Data: the Free Use Bible API (https://bible.helloao.org, AO Lab), which serves each commentary as
one JSON file per chapter and marks each Public Domain (https://creativecommons.org/publicdomain/mark/1.0/).
We load six of its commentaries into our own database. (Its seventh, the Tyndale Open Study Notes,
is CC BY-SA, not public domain, and is not used.)

More come as whole files from elsewhere (FILE_COMMENTARIES), each read by a reader of its own: Luther on
Galatians and Spurgeon's Treasury of David (Project Gutenberg plain text), and Wesley's Notes on the Bible (a
CCEL ThML file, loaded hidden until CCEL agrees to its edition being shown).

An entry in a file is {"type": "verse", "number": N, "content": ["paragraph", ...]}. Some
commentaries comment on one verse at a time (Gill, Clarke, Jamieson-Fausset-Brown) and skip verses
they have nothing to say about. Others comment on sections: an entry starts at its verse and runs
until the next entry (Matthew Henry, Calvin, Keil and Delitzsch).
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from defusedxml import ElementTree

from scripture_references import find_references, verse_limits
from search import connect, parse_terms

BASE_URL = "https://bible.helloao.org/api"

# id on the Free Use Bible API: (name, short name, whether an entry runs to the next entry).
# The order is the order of the tabs.
COMMENTARIES = {
  "matthew-henry": ("Matthew Henry's Commentary", "Matthew Henry", True),
  "john-gill": ("John Gill's Exposition of the Bible", "John Gill", False),
  "adam-clarke": ("Adam Clarke's Commentary", "Adam Clarke", False),
  "jamieson-fausset-brown": ("Jamieson-Fausset-Brown Commentary", "Jamieson-Fausset-Brown", False),
  "john-calvin": ("John Calvin's Commentaries", "John Calvin", True),
  "keil-delitzsch": ("Keil and Delitzsch's Old Testament Commentary", "Keil and Delitzsch", True),
}
# Commentaries that come as whole files, each read by its own reader (FILE_READERS). They come after the six
# above in the order of the tabs. The files are saved in a folder named after the id, under their own names.
# "publish": False loads one hidden (a CCEL edition, until CCEL agrees).
FILE_COMMENTARIES = {
  "luther-galatians": {
    "name": "Martin Luther's Commentary on Galatians",
    "short_name": "Martin Luther",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/1549",
    "download_urls": ["https://www.gutenberg.org/cache/epub/1549/pg1549.txt"],
    "reader": "luther",
  },
  "treasury-of-david": {
    "name": "Spurgeon's Treasury of David (Psalms 1–57)",
    "short_name": "C. H. Spurgeon",
    "source_name": "Project Gutenberg",
    "source_url": "https://www.gutenberg.org/ebooks/79723",
    # Volumes 1 and 2 of 6 (Psalms 1-26 and 27-57), the ones on Project Gutenberg so far.
    "download_urls": [
      "https://www.gutenberg.org/cache/epub/79723/pg79723.txt",
      "https://www.gutenberg.org/cache/epub/79727/pg79727.txt",
    ],
    "reader": "treasury",
  },
  "wesley-notes": {
    "name": "John Wesley's Notes on the Bible",
    "short_name": "John Wesley",
    "source_name": "Christian Classics Ethereal Library",
    "source_url": "https://ccel.org/ccel/wesley/notes",
    "download_urls": ["https://www.ccel.org/ccel/w/wesley/notes.xml"],
    "reader": "wesley_notes",
    # CCEL asks to be contacted before its editions are republished: loaded hidden until it agrees.
    "publish": False,
  },
}
LICENSE_URL = "https://creativecommons.org/publicdomain/mark/1.0/"
SOURCE_NAME = "Free Use Bible API"
SOURCE_URL = "https://bible.helloao.org"


def known_commentaries():
  """Every commentary that can be loaded from its source: id -> name, short name, where it comes from."""
  known = {
    commentary_id: {"name": name, "short_name": short_name, "source_name": SOURCE_NAME, "source_url": SOURCE_URL}
    for commentary_id, (name, short_name, _sections) in COMMENTARIES.items()
  }
  for details in known.values():
    details["publish"] = True
  for commentary_id, details in FILE_COMMENTARIES.items():
    known[commentary_id] = {
      "name": details["name"], "short_name": details["short_name"], "source_name": details["source_name"],
      "source_url": details["source_url"], "publish": details.get("publish", True),
    }
  return known


KNOWN_COMMENTARIES = known_commentaries()
# Be polite to the host: a few connections at a time.
DOWNLOAD_WORKERS = 4
ATTEMPTS = 4


class CommentaryProblem(ValueError):
  """A file cannot be understood. The message says which."""


def chapter_path(folder, commentary_id, book_code, chapter):
  return Path(folder) / commentary_id / f"{book_code}_{chapter}.json"


def fetch_json(client, url):
  """The JSON at a URL, retrying a few times. None when the host says there is no such file."""
  for attempt in range(ATTEMPTS):
    try:
      response = client.get(url, timeout=60)
    except httpx.HTTPError:
      response = None
    if response is not None and response.status_code == 200:
      return response.json()
    if response is not None and response.status_code == 404:
      return None
    time.sleep(2 * (attempt + 1))
  raise CommentaryProblem(f"Could not download {url}.")


def download(folder, commentary_ids, report=print):
  """Save every chapter file of these commentaries under folder (existing files are kept).

  Returns the number of files downloaded. Stop it and run it again at any time: it carries on.
  """
  folder = Path(folder)
  downloaded = 0
  with httpx.Client(follow_redirects=True) as client:
    for commentary_id in commentary_ids:
      if commentary_id in FILE_COMMENTARIES:
        downloaded += download_files(client, folder, commentary_id, report)
        continue
      books = fetch_json(client, f"{BASE_URL}/c/{commentary_id}/books.json")
      if books is None:
        raise CommentaryProblem(f"The host has no commentary '{commentary_id}'.")
      directory = folder / commentary_id
      directory.mkdir(parents=True, exist_ok=True)
      (directory / "books.json").write_text(json.dumps(books["books"], ensure_ascii=False), encoding="utf-8")

      wanted = [
        (book["id"], chapter)
        for book in books["books"]
        for chapter in range(1, book["numberOfChapters"] + 1)
        if not chapter_path(folder, commentary_id, book["id"], chapter).exists()
      ]
      report(f"{commentary_id}: {len(wanted):,} chapter files to download")

      def save(item):
        book_code, chapter = item
        body = fetch_json(client, f"{BASE_URL}/c/{commentary_id}/{book_code}/{chapter}.json")
        if body is not None:
          chapter_path(folder, commentary_id, book_code, chapter).write_text(
            json.dumps(body, ensure_ascii=False), encoding="utf-8"
          )
        return body is not None

      with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        for count, saved in enumerate(pool.map(save, wanted), start=1):
          downloaded += 1 if saved else 0
          if count % 200 == 0:
            report(f"  {commentary_id}: {count:,} of {len(wanted):,}")
  return downloaded


def file_paths(folder, commentary_id):
  """Where the files of one of the FILE_COMMENTARIES are saved: folder/<id>/<the file's own name>."""
  return [Path(folder) / commentary_id / url.rsplit("/", 1)[-1] for url in FILE_COMMENTARIES[commentary_id]["download_urls"]]


def download_files(client, folder, commentary_id, report):
  """Save the files of one of the FILE_COMMENTARIES. Returns how many were saved."""
  for url, path in zip(FILE_COMMENTARIES[commentary_id]["download_urls"], file_paths(folder, commentary_id)):
    report(f"{commentary_id}: {url}")
    response = client.get(url, timeout=300)
    if response.status_code != 200 or len(response.content) < 10_000:
      raise CommentaryProblem(f"Could not download {url} (status {response.status_code}).")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
  return len(FILE_COMMENTARIES[commentary_id]["download_urls"])


GUTENBERG_CHAPTER = re.compile(r"^CHAPTER (\d+)$")
# "  VERSE 6. I marvel." or "  VERSES 11, 12. But I certify you ..." (indented; may wrap onto more lines).
GUTENBERG_VERSE = re.compile(r"^\s+VERSES? (\d+(?:\s*(?:,|and|-|to)\s*\d+)*)\.\s")


def gutenberg_paragraphs(lines):
  """The paragraphs of hard-wrapped lines (a blank line ends one), with Gutenberg's _italic_ marks dropped."""
  paragraphs = []
  current = []
  for line in lines + [""]:
    if line.strip():
      current.append(line.strip())
    elif current:
      paragraphs.append(re.sub(r"_([^_\n]+)_", r"\1", " ".join(current)))
      current = []
  return paragraphs


def read_gutenberg_commentary(path, book_number):
  """Read a Gutenberg commentary on one book. Returns (entries, introductions) like read_commentary.

  What comes before CHAPTER 1 (the preface) is the introduction to the book, and what comes between a
  chapter heading and its first verse heading the introduction to that chapter. A verse heading starts a
  note, which runs until the next note begins; headings that name the same verse again in a row (the
  commentary takes a verse a phrase at a time) are joined into one note, each heading kept as a line.
  """
  text = Path(path).read_text(encoding="utf-8-sig").replace("\r", "")
  start = text.find("*** START OF")
  end = text.find("*** END OF")
  if start < 0 or end < 0:
    raise CommentaryProblem(f"{path} is not a Project Gutenberg text (no start and end notices).")
  lines = text[text.index("\n", start) + 1:end].split("\n")

  preface = []
  chapters = []  # [chapter number, introduction lines, [[start, end, lines], ...]]
  for line in lines:
    chapter_match = GUTENBERG_CHAPTER.match(line)
    verse_match = GUTENBERG_VERSE.match(line)
    if chapter_match:
      number = int(chapter_match.group(1))
      if number != len(chapters) + 1:
        raise CommentaryProblem(f"{path}: chapter {number} comes after chapter {len(chapters)}.")
      chapters.append([number, [], []])
    elif not chapters:
      preface.append(line)
    elif verse_match:
      numbers = [int(number) for number in re.findall(r"\d+", verse_match.group(1))]
      notes = chapters[-1][2]
      first, last = min(numbers), max(numbers)
      if notes and notes[-1][0] == first:
        notes[-1][1] = max(notes[-1][1], last)
        notes[-1][2].extend(["", line])
      else:
        if notes and first < notes[-1][0]:
          raise CommentaryProblem(f"{path}: chapter {chapters[-1][0]} goes back from verse {notes[-1][0]} to {first}.")
        notes.append([first, last, [line]])
    elif chapters[-1][2]:
      chapters[-1][2][-1][2].append(line)
    else:
      chapters[-1][1].append(line)

  if not chapters or not any(notes for _number, _introduction, notes in chapters):
    raise CommentaryProblem(f"{path}: no chapters or verse headings were found.")
  entries = []
  introductions = []
  book_introduction = "\n\n".join(gutenberg_paragraphs(preface))
  if book_introduction:
    introductions.append((book_number, 0, book_introduction))
  for chapter, introduction_lines, notes in chapters:
    introduction = "\n\n".join(gutenberg_paragraphs(introduction_lines))
    if introduction:
      introductions.append((book_number, chapter, introduction))
    for index, (first, last, note_lines) in enumerate(notes):
      if index + 1 < len(notes):
        end_verse = max(last, notes[index + 1][0] - 1)
      else:
        end_verse = None if last == first else last
      entries.append((book_number, chapter, first, end_verse, "\n\n".join(gutenberg_paragraphs(note_lines))))
  return entries, introductions


def gutenberg_body(path):
  """The lines of a Project Gutenberg text between its start and end notices."""
  text = Path(path).read_text(encoding="utf-8-sig").replace("\r", "")
  start = text.find("*** START OF")
  end = text.find("*** END OF")
  if start < 0 or end < 0:
    raise CommentaryProblem(f"{path} is not a Project Gutenberg text (no start and end notices).")
  return text[text.index("\n", start) + 1:end].split("\n")


def read_luther(paths):
  return read_gutenberg_commentary(paths[0], 48)


TREASURY_PSALM = re.compile(r"^\s+PSALM ([IVXLC]+)\.?\s*$")
TREASURY_PARTS = {
  "EXPOSITION.": "exposition",
  "EXPLANATORY NOTES AND QUAINT SAYINGS.": "notes",
  "HINTS TO PREACHERS.": "hints",
  "HINTS TO THE VILLAGE PREACHER.": "hints",
}
# "_Verse 1._—", "_Verses 1, 2._—", "_Verse 1.—“The scornful.”_" at the start of a note or a hint.
TREASURY_VERSE_MARK = re.compile(r"^_?Verses? (\d+)(?:\s*(?:,|-|–|to|and)\s*(\d+))*\.?")
TREASURY_WHOLE_PSALM = re.compile(r"^_?Whole Psalm\.?", re.IGNORECASE)


def roman_to_number(text):
  values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
  total = 0
  for index, letter in enumerate(text):
    value = values[letter]
    total += -value if index + 1 < len(text) and values[text[index + 1]] > value else value
  return total


def treasury_blocks(lines):
  """Paragraphs of hard-wrapped lines, each with whether it is indented (a verse of the Psalm) or not."""
  blocks = []
  current = []
  for line in lines + [""]:
    if line.strip():
      current.append(line)
    elif current:
      indented = all(line.startswith("    ") for line in current)
      text = re.sub(r"_([^_\n]+)_", r"\1", " ".join(line.strip() for line in current))
      blocks.append((indented, text))
      current = []
  return blocks


def read_treasury(paths):
  """Read Spurgeon's Treasury of David (Project Gutenberg volumes): one chapter of Psalms per Psalm.

  A Psalm has its title notes, then its Exposition: groups of verses of the Psalm (indented; a verse after
  the first begins with its number) each followed by Spurgeon's comment. Each group and its comment is a note
  on those verses. The Explanatory Notes and Quaint Sayings and the Hints to Preachers that name a verse
  ("Verse 3.") are added to the note on that verse, under their own heading; those on the whole Psalm, with
  the title notes, are the Psalm's introduction.
  """
  entries = []
  introductions = []
  limits = verse_limits()
  for path in paths:
    lines = gutenberg_body(path)
    starts = [(index, roman_to_number(match[1])) for index, line in enumerate(lines) if (match := TREASURY_PSALM.match(line))]
    for position, (start, psalm) in enumerate(starts):
      stop = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
      parts = {"title": [], "exposition": [], "notes": [], "hints": []}
      part = "title"
      for line in lines[start + 1:stop]:
        name = TREASURY_PARTS.get(line.strip())
        if name is not None:
          part = name
        else:
          parts[part].append(line)
      if not parts["exposition"]:
        raise CommentaryProblem(f"{path}: Psalm {psalm} has no exposition.")

      # The exposition: verse groups and the comments after them. Verses next to each other are one group. An
      # indented paragraph is a verse when it is the Psalm's first (verse 1 has no number) or begins with the
      # number of a later verse that the Psalm has; any other (a hymn quoted in a comment) is part of the comment.
      groups = []  # [first verse, last verse, [paragraphs]]
      previous_was_verse = False
      last_verse = limits.get((19, psalm), 999)
      for indented, text in treasury_blocks(parts["exposition"]):
        leading = re.match(r"^(\d{1,3})\s", text)
        number = int(leading[1]) if leading else None
        is_verse = indented and (
          (not groups and number is None) or (number is not None and number > (groups[-1][1] if groups else 0) and number <= last_verse)
        )
        if is_verse:
          first = number or 1
          if previous_was_verse and groups:
            groups[-1][1] = max(groups[-1][1], first)
            groups[-1][2].append(text)
          else:
            groups.append([first, first, [text]])
          previous_was_verse = True
        else:
          if not groups:
            groups.append([1, 1, []])
          groups[-1][2].append(text)
          previous_was_verse = False

      # The notes and hints, by the verse they name.
      extra = {"notes": {}, "hints": {}}
      whole = {"notes": [], "hints": []}
      for name in ("notes", "hints"):
        current = None
        for _indented, text in treasury_blocks(parts[name]):
          plain = text.lstrip("_ ")
          mark = TREASURY_VERSE_MARK.match(text) or TREASURY_VERSE_MARK.match(plain)
          if mark:
            current = int(mark[1])
          elif TREASURY_WHOLE_PSALM.match(text) or TREASURY_WHOLE_PSALM.match(plain):
            current = None
          if current is None:
            whole[name].append(text)
          else:
            extra[name].setdefault(current, []).append(text)

      def group_for(verse):
        for index, (first, last, _paragraphs) in enumerate(groups):
          if first <= verse <= last:
            return index
        earlier = [index for index, (first, _last, _paragraphs) in enumerate(groups) if first <= verse]
        return earlier[-1] if earlier else 0

      additions = {index: {"notes": [], "hints": []} for index in range(len(groups))}
      for name in ("notes", "hints"):
        for verse in sorted(extra[name]):
          additions[group_for(verse)][name].extend(extra[name][verse])

      for index, (first, last, paragraphs) in enumerate(groups):
        last = max(last, groups[index + 1][0] - 1) if index + 1 < len(groups) else None
        text = list(paragraphs)
        if additions[index]["notes"]:
          text += ["Explanatory Notes and Quaint Sayings", *additions[index]["notes"]]
        if additions[index]["hints"]:
          text += ["Hints to Preachers", *additions[index]["hints"]]
        entries.append((19, psalm, first, last, "\n\n".join(text)))

      introduction = [text for _indented, text in treasury_blocks(parts["title"])]
      if whole["notes"]:
        introduction += ["Explanatory Notes and Quaint Sayings: the whole Psalm", *whole["notes"]]
      if whole["hints"]:
        introduction += ["Hints to Preachers: the whole Psalm", *whole["hints"]]
      if introduction:
        introductions.append((19, psalm, "\n\n".join(introduction)))
  if not entries:
    raise CommentaryProblem("No Psalms were found in the Treasury of David files.")
  return entries, introductions


# "3. Jesus answered - ...", "4-6. ...", "11, 12. ..." at the start of a note in Wesley's Notes.
WESLEY_NOTE_VERSES = re.compile(r"^(\d{1,3})((?:\s*[-–,&]\s*\d{1,3})*)\.\s")


def ccel_plain(element):
  """The text of a CCEL element in one line, its footnotes left out."""
  parts = [element.text or ""]
  for child in element:
    if child.tag != "note":
      parts.append(ccel_plain(child))
    parts.append(child.tail or "")
  return " ".join("".join(parts).split())


def read_wesley_notes(paths):
  """Read Wesley's Notes on the Bible (CCEL ThML): the New Testament, then the Old, a division per book in
  Bible order and one per chapter inside it ("Introduction to John", "I", "II" ...). A paragraph that starts
  with verse numbers ("3.", "4-6.", "11, 12.") starts a note on those verses; the paragraphs before the first
  one are the chapter's introduction, and a book's introduction is its book introduction (chapter 0)."""
  body = ElementTree.parse(paths[0]).getroot().find("ThML.body")
  if body is None:
    raise CommentaryProblem(f"{paths[0]} has no text.")
  books = [division for division in body.iter("div2") if (division.get("title") or "").upper().startswith("NOTES ON")]
  if len(books) != 66:
    raise CommentaryProblem(f"{paths[0]}: expected 66 books of notes, found {len(books)}.")
  book_numbers = list(range(40, 67)) + list(range(1, 40))
  limits = verse_limits()
  entries = []
  introductions = []
  for book_number, book in zip(book_numbers, books):
    for chapter_division in book.iter("div3"):
      title = (chapter_division.get("title") or "").strip()
      blocks = []
      for child in chapter_division:
        if child.tag == "p":
          blocks.append(ccel_plain(child))
        elif child.tag == "div4":
          inner = [ccel_plain(paragraph) for paragraph in child.iter("p")]
          blocks.extend(inner if inner else [ccel_plain(child)])
      blocks = [block for block in blocks if block]
      if title.lower().startswith("introduction"):
        if blocks:
          introductions.append((book_number, 0, "\n\n".join(blocks)))
        continue
      # Chapters are "I", "II" ... (the Psalms "1", "2" ...); a one-chapter book may be "Commentary on Obadiah".
      if re.fullmatch(r"[IVXLC]+", title):
        chapter = roman_to_number(title)
      elif title.isdigit():
        chapter = int(title)
      elif title.lower().startswith("commentary on"):
        chapter = 1
      else:
        continue
      notes = []
      introduction = []
      last_verse = limits.get((book_number, chapter), 999)
      for block in blocks:
        match = WESLEY_NOTE_VERSES.match(block)
        numbers = [int(match[1]), *(int(found) for found in re.findall(r"\d+", match[2]))] if match else []
        # A note starts at a later verse that the chapter has; a numbered point inside a note ("2. ...") does not.
        if numbers and min(numbers) > (notes[-1][0] if notes else 0) and min(numbers) <= last_verse:
          notes.append([min(numbers), min(max(numbers), last_verse), [block]])
        elif notes:
          notes[-1][2].append(block)
        else:
          introduction.append(block)
      if introduction:
        introductions.append((book_number, chapter, "\n\n".join(introduction)))
      for first, last, paragraphs in notes:
        entries.append((book_number, chapter, first, last, "\n\n".join(paragraphs)))
  return entries, introductions


FILE_READERS = {"luther": read_luther, "treasury": read_treasury, "wesley_notes": read_wesley_notes}


def paragraphs_to_text(content):
  """The paragraphs of an entry as one text, paragraphs separated by a blank line."""
  parts = [part.strip() for part in content if isinstance(part, str) and part.strip()]
  return "\n\n".join(parts)


def read_commentary(folder, commentary_id, book_numbers_by_code):
  """Read one commentary's files. Returns (entries, introductions).

  entries are (book, chapter, verse, end_verse or None, text). introductions are
  (book, chapter, text), chapter 0 being the introduction to the whole book.
  """
  if commentary_id in FILE_COMMENTARIES:
    paths = file_paths(folder, commentary_id)
    for path in paths:
      if not path.exists():
        raise CommentaryProblem(f"{path} is missing. Download the commentary first.")
    return FILE_READERS[FILE_COMMENTARIES[commentary_id]["reader"]](paths)
  sections = COMMENTARIES[commentary_id][2]
  directory = Path(folder) / commentary_id
  books_file = directory / "books.json"
  if not books_file.exists():
    raise CommentaryProblem(f"{books_file} is missing. Download the commentary first.")
  entries = []
  introductions = []
  for book in json.loads(books_file.read_text(encoding="utf-8")):
    book_number = book_numbers_by_code.get(book["id"])
    if book_number is None:
      raise CommentaryProblem(f"I do not know the book '{book['id']}' in {commentary_id}.")
    introduction = (book.get("introduction") or "").strip()
    if introduction:
      introductions.append((book_number, 0, introduction))
    for chapter in range(1, book["numberOfChapters"] + 1):
      path = chapter_path(folder, commentary_id, book["id"], chapter)
      if not path.exists():
        continue
      body = json.loads(path.read_text(encoding="utf-8"))
      chapter_introduction = (body["chapter"].get("introduction") or "").strip()
      if chapter_introduction:
        introductions.append((book_number, chapter, chapter_introduction))
      items = [
        (int(item["number"]), paragraphs_to_text(item.get("content", [])))
        for item in body["chapter"]["content"]
        if item.get("type") == "verse"
      ]
      items = sorted((number, text) for number, text in items if text)
      for index, (number, text) in enumerate(items):
        if sections:
          end_verse = items[index + 1][0] - 1 if index + 1 < len(items) else None
          end_verse = max(end_verse, number) if end_verse is not None else None
        else:
          end_verse = number
        entries.append((book_number, chapter, number, end_verse, text))
  return entries, introductions


def replace_commentary(commentary_id, entries, introductions):
  """Replace everything of one of the known commentaries (KNOWN_COMMENTARIES) in the database, in one transaction.

  It keeps its place in the order and, if it was there already, whether it is published. A new one marked
  "publish": False is loaded hidden.
  """
  details = KNOWN_COMMENTARIES[commentary_id]
  return save_commentary(
    commentary_id, details["name"], details["short_name"], details["source_name"], details["source_url"], LICENSE_URL,
    entries, introductions, publish_if_new=details["publish"], position=list(KNOWN_COMMENTARIES).index(commentary_id) + 1,
  )


def save_commentary(
  commentary_id, name, short_name, source_name, source_url, license_url, entries, introductions,
  publish_if_new, position=None,
):
  """Replace everything of one commentary, known or uploaded, in one transaction. Returns its note count.

  A commentary that was there already keeps whether it is published; a new one is published only when
  publish_if_new. With no position it keeps its place, or a new one goes last.
  """
  with connect() as connection:
    with connection.cursor() as cursor:
      cursor.execute(
        "INSERT INTO commentaries (id, name, short_name, position, license_url, source_name, source_url, is_published) "
        "VALUES (%s, %s, %s, COALESCE(%s, (SELECT COALESCE(MAX(position), 0) + 1 FROM commentaries)), %s, %s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, short_name = EXCLUDED.short_name, "
        "position = COALESCE(%s, commentaries.position), license_url = EXCLUDED.license_url, "
        "source_name = EXCLUDED.source_name, source_url = EXCLUDED.source_url",
        (commentary_id, name, short_name, position, license_url, source_name, source_url, publish_if_new, position),
      )
      cursor.execute("DELETE FROM commentary_entries WHERE commentary_id = %s", (commentary_id,))
      cursor.execute("DELETE FROM commentary_introductions WHERE commentary_id = %s", (commentary_id,))
      with cursor.copy(
        "COPY commentary_entries (commentary_id, book_number, chapter, verse, end_verse, text) FROM STDIN"
      ) as copy:
        for book, chapter, verse, end_verse, text in entries:
          copy.write_row((commentary_id, book, chapter, verse, end_verse, text))
      with cursor.copy(
        "COPY commentary_introductions (commentary_id, book_number, chapter, text) FROM STDIN"
      ) as copy:
        for book, chapter, text in introductions:
          copy.write_row((commentary_id, book, chapter, text))
      cursor.execute("SELECT COUNT(*) FROM commentary_entries WHERE commentary_id = %s", (commentary_id,))
      return cursor.fetchone()[0]


def book_numbers_by_code():
  with connect() as connection:
    return dict(connection.execute("SELECT code, number FROM books").fetchall())


def label_range(book_name, chapter, verse, end_verse):
  """"John 3:1" or "John 3:1–21"; an open end is shown as "John 3:22 to the end of the chapter"."""
  if end_verse is None:
    return f"{book_name} {chapter}:{verse} to the end of the chapter"
  if end_verse == verse:
    return f"{book_name} {chapter}:{verse}"
  return f"{book_name} {chapter}:{verse}–{end_verse}"


def get_commentaries(book_number, chapter, verse, commentary_id=None):
  """The commentaries that have something to say about a verse, and the text of one of them.

  The one shown is commentary_id, or the first of the list. Returns None when the verse's book is
  unknown, no commentary covers the verse, or the one asked for has nothing on it.
  """
  with connect() as connection:
    book = connection.execute("SELECT name FROM books WHERE number = %s", (book_number,)).fetchone()
    if book is None:
      return None
    rows = connection.execute(
      """
      SELECT c.id, c.name, c.short_name, e.verse, e.end_verse, length(e.text), c.source_name, c.source_url, c.license_url
      FROM commentary_entries e
      JOIN commentaries c ON c.id = e.commentary_id AND c.is_published
      WHERE e.book_number = %s AND e.chapter = %s AND e.verse <= %s
        AND COALESCE(e.end_verse, 2147483647) >= %s
      ORDER BY c.position, e.verse DESC
      """,
      (book_number, chapter, verse, verse),
    ).fetchall()
    available = []
    for code, name, short_name, start, end, length, source_name, source_url, license_url in rows:
      if all(entry["id"] != code for entry in available):  # the closest entry of each commentary
        available.append({
          "id": code, "name": name, "short_name": short_name, "characters": length,
          # Where its text came from and its licence, for the credit under the note.
          "source_name": source_name, "source_url": source_url, "license_url": license_url,
          "covers": label_range(book[0], chapter, start, end),
          # The verse the note begins at: the place a visitor's own notes on this note are kept under.
          "start_verse": start,
        })
    if not available:
      return None
    chosen = next((entry for entry in available if entry["id"] == commentary_id or commentary_id is None), None)
    if chosen is None:
      return None
    text, = connection.execute(
      "SELECT text FROM commentary_entries WHERE commentary_id = %s AND book_number = %s AND chapter = %s "
      "AND verse <= %s AND COALESCE(end_verse, 2147483647) >= %s ORDER BY verse DESC LIMIT 1",
      (chosen["id"], book_number, chapter, verse, verse),
    ).fetchone()
    introductions = {
      chapter_number: introduction
      for chapter_number, introduction in connection.execute(
        "SELECT chapter, text FROM commentary_introductions WHERE commentary_id = %s AND book_number = %s "
        "AND chapter IN (0, %s)",
        (chosen["id"], book_number, chapter),
      ).fetchall()
    }
  return {
    "book_number": book_number,
    "book_name": book[0],
    "chapter": chapter,
    "verse": verse,
    "commentaries": available,
    "selected": chosen["id"],
    "covers": chosen["covers"],
    "note_verse": chosen["start_verse"],
    "text": text,
    "chapter_introduction": introductions.get(chapter),
    "book_introduction": introductions.get(0),
    # Scripture references inside each text, as [start, end, "book:chapter:verse"] over that text.
    "references": find_references(text),
    "chapter_introduction_references": find_references(introductions.get(chapter) or ""),
    "book_introduction_references": find_references(introductions.get(0) or ""),
  }


def check_ids(commentary_ids):
  unknown = [commentary_id for commentary_id in commentary_ids if commentary_id not in KNOWN_COMMENTARIES]
  if unknown:
    raise CommentaryProblem(f"Unknown commentary: {', '.join(unknown)}. Known: {', '.join(KNOWN_COMMENTARIES)}.")
  return commentary_ids


# --- browsing a commentary -----------------------------------------------------------------------------


def get_contents(commentary_id):
  """The books and chapters a commentary has notes on, for choosing what to read.

  Returns None for an unknown commentary.
  """
  with connect() as connection:
    commentary = connection.execute(
      "SELECT id, name, short_name FROM commentaries WHERE id = %s AND is_published", (commentary_id,)
    ).fetchone()
    if commentary is None:
      return None
    rows = connection.execute(
      "SELECT e.book_number, b.name, e.chapter FROM commentary_entries e JOIN books b ON b.number = e.book_number "
      "WHERE e.commentary_id = %s GROUP BY e.book_number, b.name, e.chapter ORDER BY e.book_number, e.chapter",
      (commentary_id,),
    ).fetchall()
  books = []
  for book_number, book_name, chapter in rows:
    if not books or books[-1]["number"] != book_number:
      books.append({"number": book_number, "name": book_name, "chapters": []})
    books[-1]["chapters"].append(chapter)
  return {
    "commentary": {"id": commentary[0], "name": commentary[1], "short_name": commentary[2]},
    "books": books,
  }


def get_chapter_notes(commentary_id, book_number, chapter):
  """Every note of one chapter of a commentary, in order, with its introductions.

  Also names the chapters before and after (across books) that the commentary has notes on, so a
  reader can turn the page. Returns None when there are no notes on that chapter.
  """
  with connect() as connection:
    commentary = connection.execute(
      "SELECT id, name, short_name FROM commentaries WHERE id = %s AND is_published", (commentary_id,)
    ).fetchone()
    book = connection.execute("SELECT name FROM books WHERE number = %s", (book_number,)).fetchone()
    if commentary is None or book is None:
      return None
    entries = connection.execute(
      "SELECT verse, end_verse, text FROM commentary_entries "
      "WHERE commentary_id = %s AND book_number = %s AND chapter = %s ORDER BY verse",
      (commentary_id, book_number, chapter),
    ).fetchall()
    if not entries:
      return None
    introductions = dict(
      connection.execute(
        "SELECT chapter, text FROM commentary_introductions WHERE commentary_id = %s AND book_number = %s "
        "AND chapter IN (0, %s)",
        (commentary_id, book_number, chapter),
      ).fetchall()
    )
    chapters = connection.execute(
      "SELECT DISTINCT e.book_number, b.name, e.chapter FROM commentary_entries e JOIN books b ON b.number = e.book_number "
      "WHERE e.commentary_id = %s ORDER BY e.book_number, e.chapter",
      (commentary_id,),
    ).fetchall()

  position = next(index for index, row in enumerate(chapters) if (row[0], row[2]) == (book_number, chapter))

  def neighbour(index):
    if 0 <= index < len(chapters):
      number, name, chapter_number = chapters[index]
      return {"book_number": number, "book_name": name, "chapter": chapter_number}
    return None

  chapter_introduction = introductions.get(chapter)
  book_introduction = introductions.get(0)
  return {
    "commentary": {"id": commentary[0], "name": commentary[1], "short_name": commentary[2]},
    "book_number": book_number,
    "book_name": book[0],
    "chapter": chapter,
    "chapter_introduction": chapter_introduction,
    "chapter_introduction_references": find_references(chapter_introduction or ""),
    "book_introduction": book_introduction,
    "book_introduction_references": find_references(book_introduction or ""),
    "entries": [
      {
        "verse": verse,
        "end_verse": end_verse,
        "covers": label_range(book[0], chapter, verse, end_verse),
        "text": text,
        "references": find_references(text),
      }
      for verse, end_verse, text in entries
    ],
    "previous": neighbour(position - 1),
    "next": neighbour(position + 1),
  }


# --- searching inside the commentaries ---------------------------------------------------------------

# ts_headline marks the matched words in an excerpt with these two control characters, which never
# occur in the texts. The page turns them into bold type.
START_MARK = "\u0001"
STOP_MARK = "\u0002"
HEADLINE_OPTIONS = (
  f"StartSel={START_MARK}, StopSel={STOP_MARK}, MaxWords=32, MinWords=16, MaxFragments=2, "
  "FragmentDelimiter= \u2026 "
)


def list_commentaries():
  """The published commentaries, in their order, with where each one's text came from."""
  with connect() as connection:
    return [
      {"id": commentary_id, "name": name, "short_name": short_name, "source_name": source_name, "source_url": source_url, "license_url": license_url}
      for commentary_id, name, short_name, source_name, source_url, license_url in connection.execute(
        "SELECT id, name, short_name, source_name, source_url, license_url FROM commentaries WHERE is_published ORDER BY position"
      ).fetchall()
    ]


def search_commentaries(
  query, match_mode, commentary_id, book_start, book_end, book, page, per_page, sort_by, sort_direction
):
  """Search the text of the commentaries.

  Words match in any form (love finds loved) and no word is ignored for being common (see
  migration 008). Match all words, any word, or an exact phrase; a quoted phrase inside the query is
  kept together. Results are the best matches first, or in Bible
  order when sort_by is "verse". Each result is a whole note, with an excerpt around the words found.
  """
  terms = parse_terms(query, match_mode)
  if not terms:
    raise ValueError("Enter at least one word or phrase to search for.")
  joiner = " || " if match_mode == "any" else " && "
  tsquery = joiner.join(["phraseto_tsquery('commentary_english', %s)"] * len(terms))

  with connect() as connection:
    if commentary_id is not None and connection.execute(
      "SELECT 1 FROM commentaries WHERE id = %s AND is_published", (commentary_id,)
    ).fetchone() is None:
      raise ValueError(f"Unknown commentary: {commentary_id}")
    if connection.execute(f"SELECT numnode({tsquery})", terms).fetchone()[0] == 0:
      raise ValueError("Enter at least one word or phrase to search for.")

    conditions = (
      f"e.search_vector @@ ({tsquery}) AND e.book_number BETWEEN %s AND %s "
      "AND (%s::text IS NULL OR e.commentary_id = %s) "
      "AND e.commentary_id IN (SELECT id FROM commentaries WHERE is_published)"
    )
    base_parameters = [*terms, book_start, book_end, commentary_id, commentary_id]

    book_counts = [
      {"book_number": book_number, "count": count}
      for book_number, count in connection.execute(
        f"SELECT e.book_number, count(*) FROM commentary_entries e WHERE {conditions} "
        "GROUP BY e.book_number ORDER BY e.book_number",
        base_parameters,
      ).fetchall()
    ]
    if book is None:
      total = sum(entry["count"] for entry in book_counts)
      book_condition, result_parameters = "", base_parameters
    else:
      total = sum(entry["count"] for entry in book_counts if entry["book_number"] == book)
      book_condition, result_parameters = " AND e.book_number = %s", [*base_parameters, book]

    direction = "DESC" if sort_direction == "desc" else "ASC"
    if sort_by == "verse":
      order = f"e.book_number {direction}, e.chapter {direction}, e.verse {direction}, c.position"
    else:
      order = "rank DESC, e.book_number, e.chapter, e.verse, c.position"

    # Choose the page first, then build excerpts for just those notes: an excerpt reads the whole
    # note, which is slow for the long ones.
    page_rows = connection.execute(
      f"""
      SELECT e.id, ts_rank_cd(e.search_vector, ({tsquery}), 1) AS rank
      FROM commentary_entries e
      JOIN commentaries c ON c.id = e.commentary_id
      WHERE {conditions}{book_condition}
      ORDER BY {order}
      LIMIT %s OFFSET %s
      """,
      [*terms, *result_parameters, per_page, (page - 1) * per_page],
    ).fetchall()
    results = []
    if page_rows:
      ranked_ids = [row[0] for row in page_rows]
      by_id = {
        row[0]: row[1:]
        for row in connection.execute(
          f"""
          SELECT e.id, e.commentary_id, c.short_name, e.book_number, b.name, e.chapter, e.verse, e.end_verse,
                 ts_headline('commentary_english', e.text, ({tsquery}), %s)
          FROM commentary_entries e
          JOIN commentaries c ON c.id = e.commentary_id
          JOIN books b ON b.number = e.book_number
          WHERE e.id = ANY(%s)
          """,
          [*terms, HEADLINE_OPTIONS, ranked_ids],
        ).fetchall()
      }
      for entry_id in ranked_ids:
        commentary, short_name, book_number, book_name, chapter, verse, end_verse, excerpt = by_id[entry_id]
        results.append({
          "translation": commentary,
          "commentary_id": commentary,
          "commentary_name": short_name,
          "book_number": book_number,
          "book_name": book_name,
          "chapter": chapter,
          "verse": verse,
          "end_verse": end_verse,
          "reference": label_range(book_name, chapter, verse, end_verse),
          "text": excerpt,
        })

  return {
    "source": "commentary",
    "query": query,
    "terms": terms,
    "total": total,
    "page": page,
    "per_page": per_page,
    "book_counts": book_counts,
    "results": results,
  }

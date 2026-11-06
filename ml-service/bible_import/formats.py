"""Readers for the text formats a Bible can be uploaded in.

To support a new format, write a class with the same four members as the readers below
(id, name, description, score, read) and add an instance to READERS. Nothing else needs
to change: format detection, the preview and the import all work through this list.
A reader gets the path of the uploaded file. Today that is always one text file, but a
reader for a format made of several files could take a folder or a zip file instead.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from bible_import.errors import ImportProblem

# How many non-blank lines are looked at to decide which format a file is in.
SAMPLE_LINE_COUNT = 2000
SKIPPED_SAMPLE_COUNT = 10


@dataclass(frozen=True)
class RawVerse:
  """One verse as it appears in the file: the book is still a name or code from the file."""

  book: str
  chapter: int
  verse: int
  text: str


@dataclass
class ReadResult:
  verses: list[RawVerse] = field(default_factory=list)
  skipped_count: int = 0  # non-blank lines that were not verses, such as headers and notes
  skipped_samples: list[str] = field(default_factory=list)


class LineFormatReader:
  """A format with one verse per line, recognized by a regular expression."""

  id = ""
  name = ""
  description = ""
  pattern = re.compile("")

  def score(self, sample_lines):
    """How many of the sample lines this format can read; the best score wins."""
    return sum(1 for line in sample_lines if self.pattern.match(line))

  def read(self, path):
    result = ReadResult()
    try:
      with open(path, encoding="utf-8-sig") as bible_file:
        for line in bible_file:
          line = line.rstrip("\r\n")
          if not line.strip():
            continue
          match = self.pattern.match(line)
          if match:
            result.verses.append(
              RawVerse(match["book"].strip(), int(match["chapter"]), int(match["verse"]), match["text"])
            )
          else:
            result.skipped_count += 1
            if len(result.skipped_samples) < SKIPPED_SAMPLE_COUNT:
              result.skipped_samples.append(line[:120])
    except UnicodeDecodeError as error:
      raise ImportProblem("The file is not UTF-8 text. Save it as UTF-8 and upload it again.") from error
    return result


class TabSeparatedReader(LineFormatReader):
  id = "tab"
  name = "Reference, tab, text"
  description = "Genesis 1:1<TAB>In the beginning... (the Berean Bible's bsb.txt)"
  pattern = re.compile(r"^(?P<book>.+?) (?P<chapter>\d+):(?P<verse>\d+)\t(?P<text>.+)$")


class BookCodeReader(LineFormatReader):
  id = "vpl"
  name = "Book code, reference, text"
  description = "GEN 1:1 In the beginning... (eBible.org *_vpl.txt files)"
  pattern = re.compile(r"^(?P<book>[1-4]?[A-Z]{2,3}) (?P<chapter>\d+):(?P<verse>\d+) (?P<text>.+)$")


READERS = [TabSeparatedReader(), BookCodeReader()]


def reader_by_id(identifier):
  for reader in READERS:
    if reader.id == identifier:
      return reader
  raise ImportProblem(f"Unknown file format: {identifier}")


def read_sample_lines(path):
  sample_lines = []
  try:
    with open(path, encoding="utf-8-sig") as bible_file:
      for line in bible_file:
        line = line.rstrip("\r\n")
        if line.strip():
          sample_lines.append(line)
          if len(sample_lines) >= SAMPLE_LINE_COUNT:
            break
  except UnicodeDecodeError as error:
    raise ImportProblem("The file is not UTF-8 text. Save it as UTF-8 and upload it again.") from error
  return sample_lines


def detect_reader(path):
  """Pick the format that can read the most lines of the file."""
  sample_lines = read_sample_lines(path)
  best_reader = max(READERS, key=lambda reader: reader.score(sample_lines))
  if best_reader.score(sample_lines) == 0:
    supported = "; ".join(f"{reader.name} ({reader.description})" for reader in READERS)
    raise ImportProblem(f"I could not recognize the file's format. Supported formats: {supported}.")
  return best_reader

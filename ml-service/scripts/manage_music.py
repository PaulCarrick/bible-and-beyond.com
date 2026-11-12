"""Upload, change, publish, hide and delete the songs of the Christian music section. Used by the Drupal
"Christian music" page.

Every command prints one JSON object. On success it has "ok": true. On failure it has "ok": false and an
"error" written for the administrator, and the exit status is not 0.

    manage_music.py list                                  every song, hidden ones too
    manage_music.py get --id=amazing-grace
    manage_music.py upload FILE --name=Amazing.mp4 --id=amazing-grace
                                                          reads {"title", "author", "lyrics"} as JSON on the input
    manage_music.py update --id=amazing-grace             the same details, without a new file
    manage_music.py publish|unpublish|delete --id=amazing-grace

upload and update also take --words=FILE --words-name=words.pdf (the words as a PDF or picture, shown in place
of the typed words), and update takes --remove-words. Both also take --words-document=FILE
--words-document-name=hymn.docx: a PDF or Word document whose text becomes the song's words, with its formatting
(the typed words are replaced).

--name is the file's name as uploaded (its .mp3 or .mp4 says what it is). The details are sent on the
standard input rather than as arguments, because the words can be long.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from music import (  # noqa: E402
  MusicProblem,
  delete,
  get_song,
  list_songs,
  set_published,
  set_words_from_document,
  update_details,
  upload,
)


def parse_arguments():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("list")
  for name in ("get", "publish", "unpublish", "delete"):
    commands.add_parser(name).add_argument("--id", required=True)
  updating = commands.add_parser("update")
  updating.add_argument("--id", required=True)
  updating.add_argument("--remove-words", action="store_true")
  uploading = commands.add_parser("upload")
  uploading.add_argument("file")
  uploading.add_argument("--name", required=True)
  uploading.add_argument("--id", required=True)
  for command in (updating, uploading):
    command.add_argument("--words", default=None)
    command.add_argument("--words-name", default=None)
    command.add_argument("--words-document", default=None)
    command.add_argument("--words-document-name", default=None)
  return parser.parse_args()


def words_file(arguments):
  """(path, original name) of the words file given, or None."""
  if not arguments.words:
    return None
  path = Path(arguments.words)
  if not path.is_file():
    raise MusicProblem("The uploaded words file was not found.")
  return path, arguments.words_name or path.name


def read_details() -> dict:
  try:
    details = json.loads(sys.stdin.read())
  except json.JSONDecodeError as error:
    raise MusicProblem("The details could not be read.") from error
  if not isinstance(details, dict):
    raise MusicProblem("The details could not be read.")
  return details


def run(arguments) -> dict:
  if arguments.command == "list":
    return {"ok": True, "songs": list_songs(published_only=False)}
  if arguments.command == "get":
    song = get_song(arguments.id, published_only=False)
    if song is None:
      raise MusicProblem("That song does not exist (it may have been deleted).")
    return {"ok": True, "song": song}
  if arguments.command in ("publish", "unpublish"):
    return {"ok": True, "song": set_published(arguments.id, arguments.command == "publish")}
  if arguments.command == "delete":
    return {"ok": True, "song": delete(arguments.id)}
  if arguments.command == "update":
    song = update_details(arguments.id, read_details(), words_file(arguments), arguments.remove_words)
  else:
    path = Path(arguments.file)
    if not path.is_file():
      raise MusicProblem("The uploaded file was not found.")
    song = upload(path, arguments.name, arguments.id, read_details(), words_file(arguments))
  if arguments.words_document:
    document = Path(arguments.words_document)
    if not document.is_file():
      raise MusicProblem("The uploaded words document was not found.")
    song = set_words_from_document(song["id"], document, arguments.words_document_name or document.name)
  return {"ok": True, "song": song}


def main():
  arguments = parse_arguments()
  try:
    result = run(arguments)
  except MusicProblem as problem:
    print(json.dumps({"ok": False, "error": str(problem)}))
    sys.exit(1)
  except Exception as error:  # Never leak a stack trace to the web page; keep it in the log.
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({"ok": False, "error": f"Unexpected error: {type(error).__name__}"}))
    sys.exit(2)
  print(json.dumps(result))


if __name__ == "__main__":
  main()

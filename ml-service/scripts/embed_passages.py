"""Make the embeddings for the AI search of the commentaries, devotionals, other books and songs.

Sends each piece of text to Google's gemini-embedding-001 once and keeps the result in passage_embeddings
(see passage_embeddings.py). Pieces already embedded from the same text are skipped, so it can be stopped
and run again, and should be run again after a text is reloaded or a song added or changed. It uses the
Gemini key of the Site settings screen (or GEMINI_API_KEY in .env) and costs money: run --dry-run first to see
how much would be sent and an estimate of the price.

    embed_passages.py --dry-run                         (every kind: what would be sent)
    embed_passages.py devotional                        (the devotionals and the Other books)
    embed_passages.py commentary --source=matthew-henry --book=40
    embed_passages.py music
    embed_passages.py devotional --pieces-per-minute=90   (on Google's free tier, which allows 100 a minute)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import passage_embeddings  # noqa: E402


def main():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("kinds", nargs="*", help=f"{', '.join(passage_embeddings.KINDS)} (default: every kind)")
  parser.add_argument("--source", action="append", help="a commentary, devotional, book or song id (repeatable)")
  parser.add_argument("--book", action="append", type=int, help="commentaries only: a Bible book number, 1 to 66 (repeatable)")
  parser.add_argument("--dry-run", action="store_true", help="count what would be sent; send nothing")
  parser.add_argument("--pieces-per-minute", type=int, help="keep under a quota (Google's free tier: use 90)")
  arguments = parser.parse_args()
  unknown = [kind for kind in arguments.kinds if kind not in passage_embeddings.KINDS]
  if unknown:
    parser.error(f"unknown kind: {', '.join(unknown)}")

  for kind in arguments.kinds or passage_embeddings.KINDS:
    books = arguments.book if kind == "commentary" else None
    summary = passage_embeddings.update_embeddings(
      kind, arguments.source, books, arguments.dry_run, report=lambda line: print(line, flush=True),
      pieces_per_minute=arguments.pieces_per_minute,
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
  main()

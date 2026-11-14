"""Fetch and store the FAQ answers that are missing or out of date, so that Search everything can find every
answer (an answer is otherwise stored only when a visitor first opens its question).

    ml-service/.venv/bin/python ml-service/scripts/fill_faq_answers.py [--pause=SECONDS]

Each question goes through faq.get_answer, as when a visitor opens it: a stored answer that is fresh (under
30 days old and written with the instructions in use now) costs nothing; any other is asked of Gemini and
stored. One question at a time, with a pause between Gemini calls. Prints one line per question and a summary.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import faq  # noqa: E402


def main():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--pause", type=float, default=3.0, help="seconds to wait after each answer fetched from Gemini")
  arguments = parser.parse_args()
  if not faq.is_configured():
    print("Gemini is not set up (no key on the Site settings screen or in .env); nothing was fetched.")
    sys.exit(1)
  kept, fetched, failed = 0, 0, 0
  for question_id, question in sorted(faq.QUESTIONS.items()):
    before = faq.load_stored_answer(question)
    try:
      faq.get_answer(question_id)
    except faq.FaqUnavailable as problem:
      failed += 1
      print(f"{question_id:2}. not answered ({problem}): {question}")
      continue
    after = faq.load_stored_answer(question)
    if before and after and before["fetched_at"] == after["fetched_at"]:
      kept += 1
      print(f"{question_id:2}. already stored: {question}")
    else:
      fetched += 1
      print(f"{question_id:2}. fetched: {question}")
      time.sleep(arguments.pause)
  print(f"{kept} already stored, {fetched} fetched, {failed} not answered (run again later for those).")
  sys.exit(1 if failed else 0)


if __name__ == "__main__":
  main()

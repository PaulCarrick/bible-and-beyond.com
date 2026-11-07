"""Send the daily devotional emails that are due. A systemd timer runs this every few minutes.

    .venv/bin/python scripts/send_devotional_emails.py

It sends what is due now (a visitor's chosen time, in their own time zone, has come and today's email has not
gone yet), prints how many it sent, and exits. It is safe to run at any time and more than once.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from subscriptions import send_due  # noqa: E402


def main() -> int:
  logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
  result = send_due()
  print(f"sent {result['sent']}, failed {result['failed']}, skipped {result['skipped']}" + (" (another run was sending)" if result["already_running"] else ""))
  return 1 if result["failed"] else 0


if __name__ == "__main__":
  sys.exit(main())

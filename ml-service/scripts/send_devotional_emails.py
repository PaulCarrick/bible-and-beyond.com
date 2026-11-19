"""Send the daily devotional emails, the prayer list emails, the verses a day, the groups' scheduled messages
(group_schedules.py) and the task reminders (scheduled_tasks.py) that are due. A systemd timer runs this every few minutes.

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

import group_schedules  # noqa: E402
import prayer_list  # noqa: E402
import scheduled_tasks  # noqa: E402
import verse_a_day  # noqa: E402
from subscriptions import send_due  # noqa: E402


def main() -> int:
  logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
  result = send_due()
  print(f"devotionals: sent {result['sent']}, failed {result['failed']}, skipped {result['skipped']}" + (" (another run was sending)" if result["already_running"] else ""))
  prayers = prayer_list.send_due()
  print(f"prayer list: sent {prayers['sent']}, failed {prayers['failed']}, nothing new {prayers['empty']}" + (" (another run was sending)" if prayers["already_running"] else ""))
  verses = verse_a_day.send_due()
  print(f"verse a day: sent {verses['sent']}, failed {verses['failed']}" + (" (another run was sending)" if verses["already_running"] else ""))
  scheduled = group_schedules.send_due()
  print(f"group schedules: sent {scheduled['sent']}, failed {scheduled['failed']}, too late {scheduled['late']}" + (" (another run was sending)" if scheduled["already_running"] else ""))
  reminders = scheduled_tasks.send_due()
  print(f"task reminders: sent {reminders['sent']}, failed {reminders['failed']}, skipped {reminders['skipped']}" + (" (another run was sending)" if reminders["already_running"] else ""))
  return 1 if result["failed"] or prayers["failed"] or verses["failed"] or scheduled["failed"] or reminders["failed"] else 0


if __name__ == "__main__":
  sys.exit(main())

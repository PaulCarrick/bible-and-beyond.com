"""Tasks (added 2026-11-19 at the owner's request): a name, a formatted description, how often the task comes round,
and the words of a first and a second notification, each sent so many days before a scheduled date (first_notice_days,
second_notice_days; migration 056), kept in admin_tasks (migration 054). The reminders are emailed to the site user a
task is scheduled for (scheduled_tasks.send_due) at 8:00 AM in the task's time zone (the owner's when they saved it).

How often (repeat):
  weekly     every week on a weekday (weekday: 0 Monday to 6 Sunday)
  biweekly   every two weeks, starting on a first date (first_date; its weekday is the task's day)
  monthly    every month on a day (day_of_month 1 to 31; 29 to 31 mean the last day in shorter months)

Each belongs to the Drupal user who made it (owner_uid); Drupal decides who may see which (the owner only, or
anyone with "administer all signatures and tasks"). The Drupal "Tasks" page runs scripts/manage_tasks.py.
"""

import calendar
from datetime import date, timedelta

from subscriptions import SubscriptionProblem, check_timezone

from formatted_text import FormattedTextProblem, clean, one_line
from search import connect

NAME_LIMIT = 200
PREVIEW_LENGTH = 160
MAX_PER_OWNER = 200
MAX_NOTICE_DAYS = 90
REPEATS = ("weekly", "biweekly", "monthly")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

COLUMNS = """
  id, name, description_html, description_text, repeat, weekday, first_date, day_of_month,
  first_notification_html, first_notification_text, second_notification_html, second_notification_text,
  owner_uid, owner_name, created_at, updated_at, first_notice_days, second_notice_days, timezone, owner_email
"""


class TaskProblem(FormattedTextProblem):
  """A task cannot be kept; the text says why and is fit to show the administrator."""


def _preview(text: str) -> str:
  text = " ".join(text.split())
  return text if len(text) <= PREVIEW_LENGTH else text[: PREVIEW_LENGTH - 1].rstrip() + "…"


def _ordinal(number: int) -> str:
  suffix = "th" if 11 <= number <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
  return f"{number}{suffix}"


def _day_in_month(year: int, month: int, day_of_month: int) -> date:
  return date(year, month, min(day_of_month, calendar.monthrange(year, month)[1]))


def next_date(task: dict, today: date) -> date:
  """The first day on or after `today` that the task falls on."""
  if task["repeat"] == "weekly":
    return today + timedelta(days=(task["weekday"] - today.weekday()) % 7)
  if task["repeat"] == "biweekly":
    first = task["first_date"]
    if today <= first:
      return first
    return today + timedelta(days=(first - today).days % 14)
  this_month = _day_in_month(today.year, today.month, task["day_of_month"])
  if this_month >= today:
    return this_month
  year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
  return _day_in_month(year, month, task["day_of_month"])


def next_dates(task: dict, today: date, count: int) -> list[date]:
  """The task's next `count` days, the first on or after `today`."""
  days = [next_date(task, today)]
  while len(days) < count:
    days.append(next_date(task, days[-1] + timedelta(days=1)))
  return days


def describe(task: dict) -> str:
  """How often, in words, such as "Every two weeks on Thursday, from November 20, 2026"."""
  if task["repeat"] == "weekly":
    return f"Every week on {WEEKDAYS[task['weekday']]}"
  if task["repeat"] == "biweekly":
    first = task["first_date"]
    return f"Every two weeks on {WEEKDAYS[first.weekday()]}, from {first.strftime('%B')} {first.day}, {first.year}"
  day = task["day_of_month"]
  note = " (the last day in shorter months)" if day > 28 else ""
  return f"Every month on the {_ordinal(day)}{note}"


def _describe(row, today: date | None = None) -> dict:
  task = {
    "id": row[0], "name": row[1], "description_html": row[2], "description_text": row[3], "repeat": row[4],
    "weekday": row[5], "first_date": row[6], "day_of_month": row[7],
    "first_notification_html": row[8], "first_notification_text": row[9],
    "second_notification_html": row[10], "second_notification_text": row[11],
    "owner_uid": row[12], "owner_name": row[13], "created_at": row[14].isoformat(), "updated_at": row[15].isoformat(),
    "first_notice_days": row[16], "second_notice_days": row[17], "timezone": row[18], "owner_email": row[19],
  }
  task["how_often"] = describe(task)
  task["next_date"] = next_date(task, today or date.today()).isoformat()
  task["preview"] = _preview(task["description_text"])
  task["first_date"] = task["first_date"].isoformat() if task["first_date"] else None
  return task


def _integer(value, low: int, high: int) -> int | None:
  if isinstance(value, bool):
    return None
  if isinstance(value, str) and value.strip().isdigit():
    value = int(value.strip())
  return value if isinstance(value, int) and low <= value <= high else None


def _check(details: dict) -> dict:
  """The values to keep, checked. Only the field the repeat uses is kept; the others are NULL."""
  if not isinstance(details, dict):
    raise TaskProblem("The task could not be read.")
  try:
    values = {
      "name": one_line(details.get("name"), "name", NAME_LIMIT),
      "description": clean(details.get("description"), "description", required=False),
      "first_notification": clean(details.get("first_notification"), "first notification", required=False),
      "second_notification": clean(details.get("second_notification"), "second notification", required=False),
    }
  except FormattedTextProblem as problem:
    raise TaskProblem(str(problem)) from problem
  repeat = details.get("repeat")
  if repeat not in REPEATS:
    raise TaskProblem("Choose how often the task comes round: every week, every two weeks or every month.")
  values.update({"repeat": repeat, "weekday": None, "first_date": None, "day_of_month": None})
  if repeat == "weekly":
    values["weekday"] = _integer(details.get("weekday"), 0, 6)
    if values["weekday"] is None:
      raise TaskProblem("Choose the day of the week.")
  elif repeat == "biweekly":
    try:
      values["first_date"] = date.fromisoformat(str(details.get("first_date") or ""))
    except ValueError as error:
      raise TaskProblem("Choose the first date (every two weeks counts from it).") from error
  else:
    values["day_of_month"] = _integer(details.get("day_of_month"), 1, 31)
    if values["day_of_month"] is None:
      raise TaskProblem("Choose a day of the month from 1 to 31.")
  for which in ("first", "second"):
    days = details.get(f"{which}_notice_days")
    if days is None or days == "":
      values[f"{which}_notice_days"] = None
      continue
    values[f"{which}_notice_days"] = _integer(days, 0, MAX_NOTICE_DAYS)
    if values[f"{which}_notice_days"] is None:
      raise TaskProblem(f"The days before for the {which} notice must be a whole number from 0 to {MAX_NOTICE_DAYS}.")
    if not values[f"{which}_notification"]["text"]:
      raise TaskProblem(f"Write the {which} notification, or leave its days before empty.")
  first, second = values["first_notice_days"], values["second_notice_days"]
  if first is not None and second is not None and second >= first:
    raise TaskProblem("The second notice comes after the first, so it needs fewer days before the date.")
  values["timezone"] = None
  if details.get("timezone"):
    try:
      check_timezone(str(details["timezone"]))
    except SubscriptionProblem as problem:
      raise TaskProblem(str(problem)) from problem
    values["timezone"] = str(details["timezone"])
  values["owner_email"] = None if details.get("owner_email") is None else str(details["owner_email"]).strip()[:320]
  return values


def _parameters(values: dict) -> tuple:
  return (
    values["name"], values["description"]["html"], values["description"]["text"], values["repeat"], values["weekday"],
    values["first_date"], values["day_of_month"],
    values["first_notification"]["html"], values["first_notification"]["text"],
    values["second_notification"]["html"], values["second_notification"]["text"],
    values["first_notice_days"], values["second_notice_days"],
  )


def list_tasks(owner_uid: int | None = None) -> list[dict]:
  """The tasks by name: one person's (owner_uid), or everyone's."""
  with connect() as connection:
    rows = connection.execute(
      f"SELECT {COLUMNS} FROM admin_tasks WHERE %(owner)s::int IS NULL OR owner_uid = %(owner)s ORDER BY lower(name), id",
      {"owner": owner_uid},
    ).fetchall()
  return [_describe(row) for row in rows]


def get_task(task_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {COLUMNS} FROM admin_tasks WHERE id = %s", (task_id,)).fetchone()
  if row is None:
    raise TaskProblem("That task was not found. It may have been deleted.")
  return _describe(row)


def create_task(details: dict, owner_uid: int, owner_name: str) -> dict:
  values = _check(details)
  with connect() as connection:
    count = connection.execute("SELECT count(*) FROM admin_tasks WHERE owner_uid = %s", (owner_uid,)).fetchone()[0]
    if count >= MAX_PER_OWNER:
      raise TaskProblem(f"You can keep up to {MAX_PER_OWNER} tasks. Delete one first.")
    row = connection.execute(
      f"""INSERT INTO admin_tasks (
        name, description_html, description_text, repeat, weekday, first_date, day_of_month,
        first_notification_html, first_notification_text, second_notification_html, second_notification_text,
        first_notice_days, second_notice_days, owner_uid, owner_name, timezone, owner_email
      ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING {COLUMNS}""",
      (*_parameters(values), owner_uid, " ".join((owner_name or "").split())[:NAME_LIMIT], values["timezone"] or "UTC", values["owner_email"] or ""),
    ).fetchone()
  return _describe(row)


def update_task(task_id: int, details: dict) -> dict:
  values = _check(details)
  with connect() as connection:
    row = connection.execute(
      f"""UPDATE admin_tasks SET
        name = %s, description_html = %s, description_text = %s, repeat = %s, weekday = %s, first_date = %s,
        day_of_month = %s, first_notification_html = %s, first_notification_text = %s,
        second_notification_html = %s, second_notification_text = %s, first_notice_days = %s,
        second_notice_days = %s, timezone = COALESCE(%s, timezone), owner_email = COALESCE(%s, owner_email),
        updated_at = now()
      WHERE id = %s RETURNING {COLUMNS}""",
      (*_parameters(values), values["timezone"], values["owner_email"], task_id),
    ).fetchone()
  if row is None:
    raise TaskProblem("That task was not found. It may have been deleted.")
  return _describe(row)


def delete_task(task_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"DELETE FROM admin_tasks WHERE id = %s RETURNING {COLUMNS}", (task_id,)).fetchone()
  if row is None:
    raise TaskProblem("That task was not found. It may have been deleted.")
  return _describe(row)

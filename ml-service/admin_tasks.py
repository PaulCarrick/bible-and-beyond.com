"""Tasks (added 2026-11-19 at the owner's request): a name, a formatted description, how often the task comes round,
and the words of a first and a second notification, each sent so many days before a scheduled date (first_notice_days,
second_notice_days; migration 056), kept in admin_tasks (migration 054). The reminders are emailed to the site user a
task is scheduled for (scheduled_tasks.send_due) at 8:00 AM in the task's time zone (the owner's when they saved it).

How often (repeat; migration 058, the owner's request: "the first .. of the ...", "It's not just the month"):
  weekly           every interval_count weeks (1 to 8) on the weekdays (0 Monday to 6 Sunday)
  monthly_day      every interval_count months (1, 2, 3, 4, 6 or 12; 12 is once a year) on day_of_month (1 to 31;
                   29 to 31 mean the last day in shorter months)
  monthly_weekday  every interval_count months on the weeks_of_month (1 to 4 the first to the fourth, 5 the last) of
                   the weekdays: the first Sunday, the first and third Sunday, the last Thursday of November
first_date is the start: no date comes before it, and every few weeks or months counts from its week or month (so a
once-a-year task falls in its month). Older input (biweekly with a first date, monthly) is still taken.

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
REPEATS = ("weekly", "monthly_day", "monthly_weekday")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "last"}
MAX_WEEKS_APART = 8
MONTHS_APART = (1, 2, 3, 4, 6, 12)
NUMBERS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 12: "twelve"}
# How far ahead next_date looks (a once-a-year task on the 31st of a month falls within this).
LOOK_AHEAD_DAYS = 800

COLUMNS = """
  id, name, description_html, description_text, repeat, weekday, first_date, day_of_month,
  first_notification_html, first_notification_text, second_notification_html, second_notification_text,
  owner_uid, owner_name, created_at, updated_at, first_notice_days, second_notice_days, timezone, owner_email,
  interval_count, weekdays, weeks_of_month, signature_id
"""


class TaskProblem(FormattedTextProblem):
  """A task cannot be kept; the text says why and is fit to show the administrator."""


def _preview(text: str) -> str:
  text = " ".join(text.split())
  return text if len(text) <= PREVIEW_LENGTH else text[: PREVIEW_LENGTH - 1].rstrip() + "…"


def _ordinal(number: int) -> str:
  suffix = "th" if 11 <= number <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
  return f"{number}{suffix}"


def _months_between(start: date, day: date) -> int:
  return (day.year - start.year) * 12 + day.month - start.month


def _last_day(day: date) -> int:
  return calendar.monthrange(day.year, day.month)[1]


def occurs_on(task: dict, day: date) -> bool:
  """Whether the task falls on that day (task: repeat, interval_count, weekdays, weeks_of_month, day_of_month and
  first_date as a date)."""
  start = task["first_date"]
  if day < start:
    return False
  every = task.get("interval_count") or 1
  if task["repeat"] == "weekly":
    weeks = ((day - timedelta(days=day.weekday())) - (start - timedelta(days=start.weekday()))).days // 7
    return day.weekday() in task["weekdays"] and weeks % every == 0
  if _months_between(start, day) % every != 0:
    return False
  if task["repeat"] == "monthly_day":
    return day.day == min(task["day_of_month"], _last_day(day))
  if day.weekday() not in task["weekdays"]:
    return False
  week = (day.day - 1) // 7 + 1
  last = day.day + 7 > _last_day(day)
  return week in task["weeks_of_month"] or (last and 5 in task["weeks_of_month"])


def next_date(task: dict, today: date) -> date:
  """The first day on or after `today` (and its start) that the task falls on."""
  day = max(today, task["first_date"])
  for _ in range(LOOK_AHEAD_DAYS):
    if occurs_on(task, day):
      return day
    day += timedelta(days=1)
  raise TaskProblem("That task has no date in the next two years.")


def next_dates(task: dict, today: date, count: int) -> list[date]:
  """The task's next `count` days, the first on or after `today`."""
  days = [next_date(task, today)]
  while len(days) < count:
    days.append(next_date(task, days[-1] + timedelta(days=1)))
  return days


def _and(words: list[str]) -> str:
  return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def describe(task: dict) -> str:
  """How often, in words, such as "Every month on the first Sunday" or "Every three months on the 1st, from
  January 2027"."""
  every = task.get("interval_count") or 1
  start = task["first_date"]
  weekdays = sorted(task.get("weekdays") or [])
  days = _and([WEEKDAYS[weekday] for weekday in weekdays]) if weekdays else ""
  if task["repeat"] == "weekly":
    if every == 1:
      return f"Every week on {days}"
    return f"Every {NUMBERS.get(every, every)} weeks on {days}, from {start.strftime('%B')} {start.day}, {start.year}"
  if task["repeat"] == "monthly_day":
    day = task["day_of_month"]
    on = f"the {_ordinal(day)}" + (" (the last day in shorter months)" if day > 28 else "")
  else:
    on = "the " + _and([WEEKS[week] for week in sorted(task["weeks_of_month"])]) + " " + days
  if every == 12:
    return f"Every year in {start.strftime('%B')} on {on}"
  if every == 1:
    return f"Every month on {on}"
  return f"Every {NUMBERS.get(every, every)} months on {on}, from {start.strftime('%B %Y')}"


def _describe(row, today: date | None = None) -> dict:
  task = {
    "id": row[0], "name": row[1], "description_html": row[2], "description_text": row[3], "repeat": row[4],
    "weekday": row[5], "first_date": row[6], "day_of_month": row[7],
    "first_notification_html": row[8], "first_notification_text": row[9],
    "second_notification_html": row[10], "second_notification_text": row[11],
    "owner_uid": row[12], "owner_name": row[13], "created_at": row[14].isoformat(), "updated_at": row[15].isoformat(),
    "first_notice_days": row[16], "second_notice_days": row[17], "timezone": row[18], "owner_email": row[19],
    "interval_count": row[20], "weekdays": list(row[21] or []), "weeks_of_month": list(row[22] or []),
    # The owner's signature at the foot of the reminder emails (migration 068), or None.
    "signature_id": row[23],
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
  values.update(_check_repeat(details))
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


def _integers(value, low: int, high: int) -> list[int] | None:
  """A list of whole numbers in range (one is taken as a list of one), sorted without repeats; None if any is not."""
  if value is None or value == "":
    return []
  items = value if isinstance(value, list) else [value]
  numbers = [_integer(item, low, high) for item in items]
  return None if any(number is None for number in numbers) else sorted(set(numbers))


def _check_repeat(details: dict) -> dict:
  """How often, checked: repeat, interval_count, weekdays, weeks_of_month, day_of_month, first_date (the start) and
  weekday (the first of the weekdays). Only the fields the repeat uses are kept; the others are empty."""
  repeat = details.get("repeat")
  every = details.get("interval_count") or 1
  # Older input: every two weeks from a first date, or monthly on a day.
  if repeat == "biweekly":
    repeat, every = "weekly", 2
  elif repeat == "monthly":
    repeat = "monthly_day"
  if repeat not in REPEATS:
    raise TaskProblem("Choose how often the task comes round: weekly, monthly on a day, or monthly on a weekday.")
  try:
    start = date.fromisoformat(str(details.get("first_date") or "")) if details.get("first_date") else date.today()
  except ValueError as error:
    raise TaskProblem("Choose the date the task starts from.") from error
  values = {"repeat": repeat, "first_date": start, "weekdays": [], "weeks_of_month": [], "day_of_month": None}
  if repeat == "weekly":
    values["interval_count"] = _integer(every, 1, MAX_WEEKS_APART)
    if values["interval_count"] is None:
      raise TaskProblem(f"Choose every 1 to {MAX_WEEKS_APART} weeks.")
  else:
    values["interval_count"] = _integer(every, 1, 12)
    if values["interval_count"] not in MONTHS_APART:
      raise TaskProblem("Choose every month, every 2, 3, 4 or 6 months, or once a year.")
  if repeat in ("weekly", "monthly_weekday"):
    weekdays = details.get("weekdays")
    if details.get("repeat") == "biweekly":
      weekdays = [start.weekday()]  # older input: every two weeks on the first date's weekday
    elif weekdays in (None, "", []) and details.get("weekday") not in (None, ""):
      weekdays = [details.get("weekday")]
    values["weekdays"] = _integers(weekdays, 0, 6)
    if not values["weekdays"]:
      raise TaskProblem("Choose the day of the week." if repeat == "weekly" else "Choose the day of the week (such as Sunday).")
  if repeat == "monthly_weekday":
    values["weeks_of_month"] = _integers(details.get("weeks_of_month"), 1, 5)
    if not values["weeks_of_month"]:
      raise TaskProblem("Choose which one in the month: the first, second, third, fourth or last.")
  if repeat == "monthly_day":
    values["day_of_month"] = _integer(details.get("day_of_month"), 1, 31)
    if values["day_of_month"] is None:
      raise TaskProblem("Choose a day of the month from 1 to 31.")
  values["weekday"] = values["weekdays"][0] if values["weekdays"] else None
  return values


def _parameters(values: dict) -> tuple:
  return (
    values["name"], values["description"]["html"], values["description"]["text"], values["repeat"], values["weekday"],
    values["first_date"], values["day_of_month"],
    values["first_notification"]["html"], values["first_notification"]["text"],
    values["second_notification"]["html"], values["second_notification"]["text"],
    values["first_notice_days"], values["second_notice_days"],
    values["interval_count"], values["weekdays"] or None, values["weeks_of_month"] or None,
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


def _signature(value, owner_uid: int) -> int | None:
  """The signature chosen for the reminder emails (details["signature_id"]), checked to be one of the task owner's;
  None (or "") for none."""
  if value is None or value == "":
    return None
  if isinstance(value, str) and value.strip().isdigit():
    value = int(value.strip())
  if not isinstance(value, int) or isinstance(value, bool):
    raise TaskProblem("Choose one of the task owner's signatures, or no signature.")
  with connect() as connection:
    found = connection.execute("SELECT 1 FROM admin_signatures WHERE id = %s AND owner_uid = %s", (value, owner_uid)).fetchone()
  if found is None:
    raise TaskProblem("That signature is not one of the task owner's (it may have been deleted).")
  return value


def create_task(details: dict, owner_uid: int, owner_name: str) -> dict:
  values = _check(details)
  signature_id = _signature(details.get("signature_id"), owner_uid)
  with connect() as connection:
    count = connection.execute("SELECT count(*) FROM admin_tasks WHERE owner_uid = %s", (owner_uid,)).fetchone()[0]
    if count >= MAX_PER_OWNER:
      raise TaskProblem(f"You can keep up to {MAX_PER_OWNER} tasks. Delete one first.")
    row = connection.execute(
      f"""INSERT INTO admin_tasks (
        name, description_html, description_text, repeat, weekday, first_date, day_of_month,
        first_notification_html, first_notification_text, second_notification_html, second_notification_text,
        first_notice_days, second_notice_days, interval_count, weekdays, weeks_of_month,
        owner_uid, owner_name, timezone, owner_email, signature_id
      ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING {COLUMNS}""",
      (*_parameters(values), owner_uid, " ".join((owner_name or "").split())[:NAME_LIMIT], values["timezone"] or "UTC", values["owner_email"] or "", signature_id),
    ).fetchone()
  return _describe(row)


def update_task(task_id: int, details: dict) -> dict:
  """Changes the task; without a "signature_id" in the details its signature stays. With new_owner_uid (an
  administrator's Owner choice; 2026-11-23) it moves to that person, with their name, address (owner_email) and
  time zone as given; a signature that is not theirs is dropped rather than refused."""
  values = _check(details)
  task = get_task(task_id)
  new_owner = details.get("new_owner_uid")
  owner_uid = int(new_owner) if new_owner is not None else task["owner_uid"]
  wanted = details.get("signature_id") if "signature_id" in details else task["signature_id"]
  try:
    signature_id = _signature(wanted, owner_uid)
  except TaskProblem:
    if new_owner is None:
      raise
    signature_id = None
  with connect() as connection:
    if new_owner is not None and owner_uid != task["owner_uid"]:
      count = connection.execute("SELECT count(*) FROM admin_tasks WHERE owner_uid = %s", (owner_uid,)).fetchone()[0]
      if count >= MAX_PER_OWNER:
        raise TaskProblem(f"That person already has {MAX_PER_OWNER} tasks.")
      connection.execute(
        "UPDATE admin_tasks SET owner_uid = %s, owner_name = %s WHERE id = %s",
        (owner_uid, " ".join(str(details.get("new_owner_name") or "").split())[:NAME_LIMIT], task_id),
      )
    row = connection.execute(
      f"""UPDATE admin_tasks SET
        name = %s, description_html = %s, description_text = %s, repeat = %s, weekday = %s, first_date = %s,
        day_of_month = %s, first_notification_html = %s, first_notification_text = %s,
        second_notification_html = %s, second_notification_text = %s, first_notice_days = %s,
        second_notice_days = %s, interval_count = %s, weekdays = %s, weeks_of_month = %s,
        timezone = COALESCE(%s, timezone), owner_email = COALESCE(%s, owner_email), signature_id = %s,
        updated_at = now()
      WHERE id = %s RETURNING {COLUMNS}""",
      (*_parameters(values), values["timezone"], values["owner_email"], signature_id, task_id),
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

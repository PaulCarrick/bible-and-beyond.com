"""Scheduled tasks (added 2026-11-19 at the owner's request): a task (admin_tasks.py) given to a site account on one
of the task's dates, kept in admin_scheduled_tasks (migration 055).

The date is chosen from the task's next OCCURRENCES dates, the first on or after today (a weekly Sunday task offers
the next four Sundays). Changing a scheduled task may keep its own date even when that is no longer among them.

A scheduled task belongs with its task: Drupal lets whoever may see the task see and change it (owner_uid is the
task's owner). The Drupal "Scheduled tasks" page and Schedule beside each task run scripts/manage_tasks.py.
"""

from datetime import date

import admin_tasks
from admin_tasks import TaskProblem
from search import connect

OCCURRENCES = 4
NAME_LIMIT = 200

COLUMNS = """
  s.id, s.task_id, t.name, t.owner_uid, t.owner_name, s.user_id,
  COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), ''), COALESCE(u.email, u.phone, ''),
  s.on_date, s.created_by_name, s.created_at, s.updated_at
"""
FROM = "admin_scheduled_tasks s JOIN admin_tasks t ON t.id = s.task_id JOIN users u ON u.id = s.user_id"


def _describe(row, today: date) -> dict:
  return {
    "id": row[0], "task_id": row[1], "task_name": row[2], "owner_uid": row[3], "owner_name": row[4],
    "user_id": row[5], "user_name": row[6], "user_email": row[7], "user_label": _user_label(row[6], row[7]),
    "on_date": row[8].isoformat(), "past": row[8] < today, "created_by_name": row[9],
    "created_at": row[10].isoformat(), "updated_at": row[11].isoformat(),
  }


def _user_label(name: str, address: str) -> str:
  if name and address:
    return f"{name} ({address})"
  return name or address


def _rule(task: dict) -> dict:
  """The task's repeat fields as next_date takes them (get_task gives the first date as text)."""
  return {
    "repeat": task["repeat"], "weekday": task["weekday"], "day_of_month": task["day_of_month"],
    "first_date": date.fromisoformat(task["first_date"]) if task["first_date"] else None,
  }


def date_label(day: date) -> str:
  return f"{day.strftime('%A, %B')} {day.day}, {day.year}"


def list_users() -> list[dict]:
  """The site's open accounts by name, for the Site user select."""
  with connect() as connection:
    rows = connection.execute(
      """
      SELECT u.id, COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), ''), COALESCE(u.email, u.phone, '')
      FROM users u
      WHERE u.disabled_at IS NULL
      ORDER BY lower(COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), u.email, u.phone)), u.id
      """
    ).fetchall()
  return [{"id": row[0], "label": _user_label(row[1], row[2])} for row in rows]


def options(task_id: int, today: date | None = None) -> dict:
  """What the Schedule form offers: the task, its next OCCURRENCES dates ({value, label}) and the site users."""
  task = admin_tasks.get_task(task_id)
  days = admin_tasks.next_dates(_rule(task), today or date.today(), OCCURRENCES)
  return {
    "task": task,
    "dates": [{"value": day.isoformat(), "label": date_label(day)} for day in days],
    "users": list_users(),
  }


def list_scheduled(owner_uid: int | None = None, today: date | None = None) -> list[dict]:
  """The scheduled tasks by date (then task and person): of one person's tasks (owner_uid), or of all."""
  with connect() as connection:
    rows = connection.execute(
      f"""SELECT {COLUMNS} FROM {FROM}
      WHERE %(owner)s::int IS NULL OR t.owner_uid = %(owner)s
      ORDER BY s.on_date, lower(t.name), s.id""",
      {"owner": owner_uid},
    ).fetchall()
  return [_describe(row, today or date.today()) for row in rows]


def get_scheduled(scheduled_id: int, today: date | None = None) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {COLUMNS} FROM {FROM} WHERE s.id = %s", (scheduled_id,)).fetchone()
  if row is None:
    raise TaskProblem("That scheduled task was not found. It may have been removed.")
  return _describe(row, today or date.today())


def _check(connection, task: dict, details: dict, today: date, current: date | None = None) -> tuple[int, date]:
  """The account and the date, checked: an open account, and one of the task's next dates (or the current one)."""
  if not isinstance(details, dict):
    raise TaskProblem("The scheduled task could not be read.")
  user_id = details.get("user_id")
  if isinstance(user_id, str) and user_id.strip().isdigit():
    user_id = int(user_id.strip())
  if not isinstance(user_id, int) or isinstance(user_id, bool):
    raise TaskProblem("Choose the site user.")
  if not connection.execute("SELECT 1 FROM users WHERE id = %s AND disabled_at IS NULL", (user_id,)).fetchone():
    raise TaskProblem("That site user was not found, or their account is closed.")
  try:
    day = date.fromisoformat(str(details.get("on_date") or ""))
  except ValueError as error:
    raise TaskProblem("Choose the date.") from error
  allowed = admin_tasks.next_dates(_rule(task), today, OCCURRENCES)
  if day not in allowed and day != current:
    raise TaskProblem(f"Choose one of the task's next {OCCURRENCES} dates.")
  return user_id, day


def _taken(connection, task_id: int, user_id: int, day: date, other_than: int | None = None) -> bool:
  return connection.execute(
    "SELECT 1 FROM admin_scheduled_tasks WHERE task_id = %s AND user_id = %s AND on_date = %s AND id <> %s",
    (task_id, user_id, day, other_than or 0),
  ).fetchone() is not None


def add_scheduled(task_id: int, details: dict, created_by_uid: int, created_by_name: str, today: date | None = None) -> dict:
  today = today or date.today()
  task = admin_tasks.get_task(task_id)
  with connect() as connection:
    user_id, day = _check(connection, task, details, today)
    if _taken(connection, task_id, user_id, day):
      raise TaskProblem("That person already has this task on that date.")
    scheduled_id = connection.execute(
      """INSERT INTO admin_scheduled_tasks (task_id, user_id, on_date, created_by_uid, created_by_name)
      VALUES (%s, %s, %s, %s, %s) RETURNING id""",
      (task_id, user_id, day, created_by_uid, " ".join((created_by_name or "").split())[:NAME_LIMIT]),
    ).fetchone()[0]
  return get_scheduled(scheduled_id, today)


def update_scheduled(scheduled_id: int, details: dict, today: date | None = None) -> dict:
  """Changes the person or the date (the task stays). Its own date may be kept even if no longer offered."""
  today = today or date.today()
  scheduled = get_scheduled(scheduled_id, today)
  task = admin_tasks.get_task(scheduled["task_id"])
  with connect() as connection:
    user_id, day = _check(connection, task, details, today, date.fromisoformat(scheduled["on_date"]))
    if _taken(connection, task["id"], user_id, day, scheduled_id):
      raise TaskProblem("That person already has this task on that date.")
    connection.execute(
      "UPDATE admin_scheduled_tasks SET user_id = %s, on_date = %s, updated_at = now() WHERE id = %s",
      (user_id, day, scheduled_id),
    )
  return get_scheduled(scheduled_id, today)


def remove_scheduled(scheduled_id: int) -> dict:
  scheduled = get_scheduled(scheduled_id)
  with connect() as connection:
    connection.execute("DELETE FROM admin_scheduled_tasks WHERE id = %s", (scheduled_id,))
  return scheduled

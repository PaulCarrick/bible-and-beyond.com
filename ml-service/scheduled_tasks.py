"""Scheduled tasks (added 2026-11-19 at the owner's request): a task (admin_tasks.py) given to a site account on one
of the task's dates, kept in admin_scheduled_tasks (migration 055).

The date is chosen from the task's next OCCURRENCES dates, the first on or after today (a weekly Sunday task offers
the next four Sundays). Changing a scheduled task may keep its own date even when that is no longer among them.

A scheduled task belongs with its task: Drupal lets whoever may see the task see and change it (owner_uid is the
task's owner). The Drupal "Scheduled tasks" page and Schedule beside each task run scripts/manage_tasks.py.

Reminders (send_due, run by the five-minute job; the owner's request, 2026-11-19): the task's first notification is
emailed to the site user first_notice_days before the date, and its second second_notice_days before, at SEND_HOUR in
the task's time zone (a notice whose days are not set is not sent). Each is claimed before it is sent, so it goes
once. One that falls due late (the date was scheduled after its day, or the job was not running) goes at the next
run; when the second is due too, only the second goes and the first is marked skipped. Nothing goes once the date
has passed. Changing the date of a scheduled task lets its reminders go again for the new date. A task sends at
most one reminder a day: a late first reminder on the second's own day (before its 8:00) is skipped for the second.

Each reminder follows the site user's own delivery choice (Send via Email / Send via SMS on My account,
sms.delivery_for_user; the owner's request, 2026-11-22): an email to a confirmed address, a text when they chose
texts and can be texted, or both. A scheduled task may carry a note (note_html, note_text; migration 066), added under
the notification. [FIRST_NAME], [LAST_NAME] and [FULL_NAME] (any case) in the notification, the note and the task's
name are replaced with the site user's name (fill_names); a missing first or full name reads "friend".
"""

import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from email.message import EmailMessage
from html import escape
from zoneinfo import ZoneInfo

import admin_tasks
import sms
from admin_tasks import TaskProblem
from contact import MailUnavailable, load_mail_settings, send_email
from formatted_text import FormattedTextProblem, clean
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger(__name__)

OCCURRENCES = 4
SEND_HOUR = 8
LOCK_NUMBER = 7281005
NOTICES = ("first", "second")
NAME_LIMIT = 200

COLUMNS = """
  s.id, s.task_id, t.name, t.owner_uid, t.owner_name, s.user_id,
  COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), ''), COALESCE(u.email, u.phone, ''),
  s.on_date, s.created_by_name, s.created_at, s.updated_at,
  s.first_notice_at, s.first_notice_result, s.second_notice_at, s.second_notice_result,
  t.first_notice_days, t.second_notice_days, s.note_html, s.note_text, COALESCE(u.email, ''), COALESCE(u.phone, ''), s.confirmed
"""
FROM = "admin_scheduled_tasks s JOIN admin_tasks t ON t.id = s.task_id JOIN users u ON u.id = s.user_id"


def _describe(row, today: date) -> dict:
  return {
    "id": row[0], "task_id": row[1], "task_name": row[2], "owner_uid": row[3], "owner_name": row[4],
    "user_id": row[5], "user_name": row[6], "user_email": row[7], "user_label": _user_label(row[6], row[7]),
    "on_date": row[8].isoformat(), "past": row[8] < today, "created_by_name": row[9],
    "created_at": row[10].isoformat(), "updated_at": row[11].isoformat(),
    "first_notice_at": row[12].isoformat() if row[12] else None, "first_notice_result": row[13],
    "second_notice_at": row[14].isoformat() if row[14] else None, "second_notice_result": row[15],
    "first_notice_date": (row[8] - timedelta(days=row[16])).isoformat() if row[16] is not None else None,
    "second_notice_date": (row[8] - timedelta(days=row[17])).isoformat() if row[17] is not None else None,
    "note_html": row[18], "note_text": row[19],
    # The site user's address and phone, each '' when none (the Scheduled task report shows both).
    "email": row[20], "phone": row[21],
    # False for a new scheduled task; those that existed when the flag came were set true (migration 073).
    "confirmed": row[22],
  }


def _user_label(name: str, address: str) -> str:
  if name and address:
    return f"{name} ({address})"
  return name or address


def _rule(task: dict) -> dict:
  """The task's repeat fields as next_date takes them (get_task gives the first date as text)."""
  return {
    "repeat": task["repeat"], "interval_count": task["interval_count"], "weekdays": task["weekdays"],
    "weeks_of_month": task["weeks_of_month"], "day_of_month": task["day_of_month"],
    "first_date": date.fromisoformat(task["first_date"]),
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


def _note(details: dict) -> dict:
  """The optional note, {"html", "text"} cleaned ('' for both when empty), from {"html"} or {"text"}."""
  try:
    return clean(details.get("note"), "note", required=False)
  except FormattedTextProblem as problem:
    raise TaskProblem(str(problem)) from problem


NAME_FIELD = re.compile(r"\[(FIRST_NAME|LAST_NAME|FULL_NAME)\]", re.IGNORECASE)


def fill_names(words: str, first_name: str | None, last_name: str | None, html: bool = False) -> str:
  """[FIRST_NAME], [LAST_NAME] and [FULL_NAME] (any case) replaced with the site user's name. Without a first name
  [FIRST_NAME] reads "friend"; without any name [FULL_NAME] does too; [LAST_NAME] is then empty."""
  first = " ".join((first_name or "").split())
  last = " ".join((last_name or "").split())
  names = {
    "FIRST_NAME": first or "friend",
    "LAST_NAME": last,
    "FULL_NAME": " ".join(part for part in (first, last) if part) or "friend",
  }
  return NAME_FIELD.sub(lambda match: escape(names[match.group(1).upper()]) if html else names[match.group(1).upper()], words)


# How far back a member's own list goes (member_tasks), and so whether the menu offers it (accounts.py).
MEMBER_PAST_DAYS = 60


def member_tasks(user_id: int, today: date | None = None) -> dict:
  """A logged-in member's own scheduled tasks for "My scheduled tasks" on the site (the owner's request, 2026-11-27):
  "upcoming" (today and later, soonest first) and "past" (the last MEMBER_PAST_DAYS days, latest first). Each has id,
  task_name, on_date, confirmed, owner_name (who set the task), description_html (the task's description) and
  note_html (the note for them on that date), with the name fields filled in with the member's name."""
  today = today or date.today()
  with connect() as connection:
    rows = connection.execute(
      """SELECT s.id, t.name, s.on_date, s.confirmed, t.owner_name, t.description_html, s.note_html,
                u.first_name, u.last_name
      FROM admin_scheduled_tasks s JOIN admin_tasks t ON t.id = s.task_id JOIN users u ON u.id = s.user_id
      WHERE s.user_id = %s AND s.on_date >= %s
      ORDER BY s.on_date, lower(t.name), s.id""",
      (user_id, today - timedelta(days=MEMBER_PAST_DAYS)),
    ).fetchall()
  tasks = [
    {
      "id": row[0],
      "task_name": fill_names(row[1], row[7], row[8]),
      "on_date": row[2].isoformat(),
      "confirmed": row[3],
      "owner_name": row[4],
      "description_html": fill_names(row[5] or "", row[7], row[8], html=True),
      "note_html": fill_names(row[6] or "", row[7], row[8], html=True),
    }
    for row in rows
  ]
  upcoming = [task for task in tasks if task["on_date"] >= today.isoformat()]
  past = [task for task in tasks if task["on_date"] < today.isoformat()]
  past.reverse()
  return {"upcoming": upcoming, "past": past}


def _taken(connection, task_id: int, user_id: int, day: date, other_than: int | None = None) -> bool:
  return connection.execute(
    "SELECT 1 FROM admin_scheduled_tasks WHERE task_id = %s AND user_id = %s AND on_date = %s AND id <> %s",
    (task_id, user_id, day, other_than or 0),
  ).fetchone() is not None


def _confirmed(value) -> bool:
  """The confirmed flag from the details: true for True, 1 or "1", "yes", "true"; anything else false."""
  if isinstance(value, str):
    return value.strip().lower() in ("1", "yes", "true", "on")
  return value is True or value == 1


def add_scheduled(task_id: int, details: dict, created_by_uid: int, created_by_name: str, today: date | None = None) -> dict:
  today = today or date.today()
  task = admin_tasks.get_task(task_id)
  with connect() as connection:
    user_id, day = _check(connection, task, details, today)
    note = _note(details)
    if _taken(connection, task_id, user_id, day):
      raise TaskProblem("That person already has this task on that date.")
    scheduled_id = connection.execute(
      """INSERT INTO admin_scheduled_tasks
        (task_id, user_id, on_date, created_by_uid, created_by_name, note_html, note_text, confirmed)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
      (task_id, user_id, day, created_by_uid, " ".join((created_by_name or "").split())[:NAME_LIMIT], note["html"], note["text"],
       _confirmed(details.get("confirmed"))),
    ).fetchone()[0]
  return get_scheduled(scheduled_id, today)


def update_scheduled(scheduled_id: int, details: dict, today: date | None = None) -> dict:
  """Changes the person, the date or the note (the task stays). Its own date may be kept even if no longer offered.
  Without a "note" in the details the note stays, and without "confirmed" the confirmed flag stays."""
  today = today or date.today()
  scheduled = get_scheduled(scheduled_id, today)
  task = admin_tasks.get_task(scheduled["task_id"])
  with connect() as connection:
    user_id, day = _check(connection, task, details, today, date.fromisoformat(scheduled["on_date"]))
    note = _note(details) if "note" in details else {"html": scheduled["note_html"], "text": scheduled["note_text"]}
    confirmed = _confirmed(details["confirmed"]) if "confirmed" in details else scheduled["confirmed"]
    if _taken(connection, task["id"], user_id, day, scheduled_id):
      raise TaskProblem("That person already has this task on that date.")
    # A new person or date: the reminders go again (to them, for that date).
    changed = user_id != scheduled["user_id"] or day.isoformat() != scheduled["on_date"]
    connection.execute(
      """UPDATE admin_scheduled_tasks SET user_id = %s, on_date = %s, note_html = %s, note_text = %s, confirmed = %s,
        updated_at = now(),
        first_notice_at = CASE WHEN %s THEN NULL ELSE first_notice_at END,
        first_notice_result = CASE WHEN %s THEN '' ELSE first_notice_result END,
        second_notice_at = CASE WHEN %s THEN NULL ELSE second_notice_at END,
        second_notice_result = CASE WHEN %s THEN '' ELSE second_notice_result END
      WHERE id = %s""",
      (user_id, day, note["html"], note["text"], confirmed, changed, changed, changed, changed, scheduled_id),
    )
  return get_scheduled(scheduled_id, today)


def day_options(on_date: date, owner_uid: int | None = None, today: date | None = None) -> dict:
  """What "Schedule tasks" offers for one date (2026-11-23): the tasks (of one owner, or all) that fall on it among
  their next OCCURRENCES dates, each with who already has it that day, and the site users."""
  today = today or date.today()
  tasks = []
  for task in admin_tasks.list_tasks(owner_uid):
    if on_date in admin_tasks.next_dates(_rule(task), today, OCCURRENCES):
      tasks.append({"id": task["id"], "name": task["name"], "owner_uid": task["owner_uid"], "owner_name": task["owner_name"]})
  taken: dict[int, list[str]] = {}
  if tasks:
    with connect() as connection:
      for task_id, name, address in connection.execute(
        """SELECT s.task_id, COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), ''), COALESCE(u.email, u.phone, '')
        FROM admin_scheduled_tasks s JOIN users u ON u.id = s.user_id
        WHERE s.on_date = %s AND s.task_id = ANY(%s) ORDER BY s.id""",
        (on_date, [task["id"] for task in tasks]),
      ).fetchall():
        taken.setdefault(task_id, []).append(_user_label(name, address))
  for task in tasks:
    task["scheduled_for"] = taken.get(task["id"], [])
  return {"on_date": on_date.isoformat(), "label": date_label(on_date), "tasks": tasks, "users": list_users()}


def add_many(details: dict, created_by_uid: int, created_by_name: str, owner_uid: int | None = None, today: date | None = None) -> list[dict]:
  """Schedules several tasks on one date at once ("Schedule tasks"; 2026-11-23): details {on_date, items: [{task_id,
  user_id, note}]}. All or none: a problem with any one (named by its task) saves nothing. owner_uid, when given,
  limits it to that owner's tasks."""
  today = today or date.today()
  if not isinstance(details, dict) or not isinstance(details.get("items"), list) or not details["items"]:
    raise TaskProblem("Choose at least one task, and a site user for each.")
  if len(details["items"]) > 100:
    raise TaskProblem("Schedule at most 100 tasks at a time.")
  on_date = str(details.get("on_date") or "")
  by_name = " ".join((created_by_name or "").split())[:NAME_LIMIT]
  added_ids = []
  seen = set()
  with connect() as connection:
    for item in details["items"]:
      if not isinstance(item, dict):
        raise TaskProblem("A task could not be read.")
      try:
        task = admin_tasks.get_task(int(item.get("task_id")))
      except (TypeError, ValueError) as error:
        raise TaskProblem("A task could not be read.") from error
      if owner_uid is not None and task["owner_uid"] != owner_uid:
        raise TaskProblem(f"“{task['name']}” is not one of your tasks.")
      try:
        user_id, day = _check(connection, task, {"user_id": item.get("user_id"), "on_date": on_date}, today)
        note = _note(item)
      except TaskProblem as problem:
        raise TaskProblem(f"{task['name']}: {problem}") from problem
      if (task["id"], user_id) in seen or _taken(connection, task["id"], user_id, day):
        raise TaskProblem(f"{task['name']}: that person already has this task on that date.")
      seen.add((task["id"], user_id))
      added_ids.append(connection.execute(
        """INSERT INTO admin_scheduled_tasks (task_id, user_id, on_date, created_by_uid, created_by_name, note_html, note_text)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (task["id"], user_id, day, created_by_uid, by_name, note["html"], note["text"]),
      ).fetchone()[0])
  return [get_scheduled(scheduled_id, today) for scheduled_id in added_ids]


def remove_scheduled(scheduled_id: int) -> dict:
  scheduled = get_scheduled(scheduled_id)
  with connect() as connection:
    connection.execute("DELETE FROM admin_scheduled_tasks WHERE id = %s", (scheduled_id,))
  return scheduled


# --- reminders ---------------------------------------------------------------------------------------------


def _due_moment(on_date: date, days: int, zone: ZoneInfo) -> datetime:
  return datetime.combine(on_date - timedelta(days=days), time(SEND_HOUR), tzinfo=zone).astimezone(timezone.utc)


def reminder_words(reminder: dict) -> dict:
  """The task's name, the notification and the note with the site user's name filled in: {task_name, html, text}."""
  first, last = reminder.get("first_name"), reminder.get("last_name")
  html = fill_names(reminder["html"] or "", first, last, html=True)
  text = fill_names(reminder["text"] or "", first, last)
  if reminder.get("note_text"):
    html += fill_names(reminder.get("note_html") or "", first, last, html=True)
    text = f"{text}\n\n{fill_names(reminder['note_text'], first, last)}" if text else fill_names(reminder["note_text"], first, last)
  return {"task_name": fill_names(reminder["task_name"], first, last), "html": html, "text": text}


def compose_reminder(settings: dict, reminder: dict) -> EmailMessage:
  """The reminder email: To the site user, Reply-To the task's owner, the notification's words, the note and a short
  foot."""
  title = get_public_settings()["title"]
  day = date_label(reminder["on_date"])
  words = reminder_words(reminder)
  reminder = {**reminder, **words}
  email = EmailMessage()
  email["Subject"] = f"Reminder: {reminder['task_name']} on {day}"
  email["From"] = settings["from_address"]
  email["To"] = reminder["address"]
  if reminder["owner_email"]:
    email["Reply-To"] = reminder["owner_email"]
  sender = reminder["owner_name"] or title
  foot = f"A reminder of “{reminder['task_name']}” on {day}, from {sender} through {title}."
  # The task's signature (2026-11-23), after the words and before the foot; emails only, never texts.
  has_signature = bool(reminder.get("signature_text"))
  signature_text = f"\n\n{reminder['signature_text']}" if has_signature else ""
  signature_html = (reminder.get("signature_html") or "") if has_signature else ""
  # "Add the “Sent by …” line" on the task (2026-11-23): unticked, the email ends with the words and signature.
  if reminder.get("show_sent_by", True):
    email.set_content(f"{reminder['text']}{signature_text}\n\n--\n{foot}\n")
    email.add_alternative(f"<html><body>{reminder['html']}{signature_html}<hr><p>{escape(foot)}</p></body></html>", subtype="html")
  else:
    email.set_content(f"{reminder['text']}{signature_text}\n")
    email.add_alternative(f"<html><body>{reminder['html']}{signature_html}</body></html>", subtype="html")
  return email


def compose_reminder_text(reminder: dict) -> str:
  """The reminder as a text (sms.compose adds the site's name and how to stop, and cuts it to fit)."""
  words = reminder_words(reminder)
  return sms.compose(f"Reminder: {words['task_name']} on {date_label(reminder['on_date'])}. {words['text']}")


def _ways(user_id: int, address: str | None, confirmed: bool, closed: bool) -> tuple[bool, str | None, str | None]:
  """How this reminder reaches the site user, by their delivery choice: (email it?, the number to text, or the
  reason it cannot go at all). Email only to a confirmed address."""
  if closed:
    return False, None, "Not sent: the site user closed their account."
  with connect() as connection:
    by_email, number = sms.delivery_for_user(connection, user_id)
  email_ok = by_email and bool(address) and confirmed
  if email_ok or number:
    return email_ok, number, None
  if not address:
    return False, None, "Not sent: the site user's account has no email address, and they cannot be texted."
  if not confirmed:
    return False, None, "Not sent: the site user has not confirmed their email address yet."
  return False, None, "Not sent: the site user cannot be reached the way they chose."


def _finish(scheduled_id: int, which: str, result: str) -> None:
  with connect() as connection:
    connection.execute(f"UPDATE admin_scheduled_tasks SET {which}_notice_result = %s WHERE id = %s", (result, scheduled_id))


def _claim(scheduled_id: int, which: str, now: datetime, result: str = "Sending") -> bool:
  """Marks a reminder as taken (sent or given up) unless another run took it first."""
  with connect() as connection:
    return connection.execute(
      f"""UPDATE admin_scheduled_tasks SET {which}_notice_at = %s, {which}_notice_result = %s
      WHERE id = %s AND {which}_notice_at IS NULL RETURNING id""",
      (now, result, scheduled_id),
    ).fetchone() is not None


def send_due(now: datetime | None = None) -> dict:
  """Emails every task reminder that is due. Returns how many were sent, skipped and failed."""
  now = now or datetime.now(timezone.utc)
  result = {"sent": 0, "skipped": 0, "failed": 0, "already_running": False}
  settings = None
  with connect() as lock_connection:
    if not lock_connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_NUMBER,)).fetchone()[0]:
      result["already_running"] = True
      return result
    with connect() as connection:
      rows = connection.execute(
        """
        SELECT s.id, s.on_date, s.first_notice_at IS NULL, s.second_notice_at IS NULL,
               t.name, t.timezone, t.owner_name, t.owner_email, t.first_notice_days, t.second_notice_days,
               t.first_notification_html, t.first_notification_text, t.second_notification_html, t.second_notification_text,
               u.email, (u.email_verified_at IS NOT NULL), u.disabled_at IS NOT NULL,
               s.user_id, u.first_name, u.last_name, s.note_html, s.note_text, sg.html, sg.text, t.show_sent_by
        FROM admin_scheduled_tasks s JOIN admin_tasks t ON t.id = s.task_id JOIN users u ON u.id = s.user_id
        LEFT JOIN admin_signatures sg ON sg.id = t.signature_id
        WHERE s.on_date >= %s
          AND ((s.first_notice_at IS NULL AND t.first_notice_days IS NOT NULL)
            OR (s.second_notice_at IS NULL AND t.second_notice_days IS NOT NULL))
        ORDER BY s.on_date, s.id
        """,
        ((now - timedelta(days=2)).date(),),
      ).fetchall()
    for row in rows:
      (scheduled_id, on_date, first_open, second_open, task_name, zone_name, owner_name, owner_email,
       first_days, second_days, first_html, first_text, second_html, second_text, address, confirmed, closed,
       user_id, first_name, last_name, note_html, note_text, signature_html, signature_text, show_sent_by) = row
      zone = ZoneInfo(zone_name or "UTC")
      notices = {
        "first": {"open": first_open, "days": first_days, "html": first_html, "text": first_text},
        "second": {"open": second_open, "days": second_days, "html": second_html, "text": second_text},
      }
      for notice in notices.values():
        notice["due"] = notice["open"] and notice["days"] is not None and _due_moment(on_date, notice["days"], zone) <= now
      local_today = now.astimezone(zone).date()
      if on_date < local_today:
        for which, notice in notices.items():
          if notice["open"] and notice["days"] is not None and _claim(scheduled_id, which, now, "Skipped: the date passed before it was sent."):
            result["skipped"] += 1
        continue
      if notices["second"]["due"]:
        which = "second"
        if notices["first"]["due"] and _claim(scheduled_id, "first", now, "Skipped: it was due late, so only the second reminder went."):
          result["skipped"] += 1
      elif notices["first"]["due"]:
        if not second_open:
          # The second already went (the first's days were added later): the first would come after it.
          if _claim(scheduled_id, "first", now, "Skipped: the second reminder had already gone."):
            result["skipped"] += 1
          continue
        second_days = notices["second"]["days"]
        if second_days is not None and on_date - timedelta(days=second_days) <= local_today:
          # A late first reminder before 8:00 on the second's own day: one reminder a day per task, so only the
          # second goes, at 8:00 (the owner's rule, 2026-11-23).
          if _claim(scheduled_id, "first", now, "Skipped: the second reminder goes later the same day."):
            result["skipped"] += 1
          continue
        which = "first"
      else:
        continue
      notice = notices[which]
      if not _claim(scheduled_id, which, now):
        continue
      by_email, number, problem = _ways(user_id, address, confirmed, closed)
      if problem is None and not notice["text"] and not note_text:
        problem = "Not sent: the notification has no words."
      if problem is not None:
        _finish(scheduled_id, which, problem)
        result["skipped"] += 1
        continue
      reminder = {
        "task_name": task_name, "on_date": on_date, "address": address, "owner_name": owner_name,
        "owner_email": owner_email, "html": notice["html"], "text": notice["text"],
        "first_name": first_name, "last_name": last_name, "note_html": note_html, "note_text": note_text,
        "signature_html": signature_html, "signature_text": signature_text, "show_sent_by": show_sent_by,
      }
      went, failures = [], []

      def email_it() -> str | None:
        """Sends the email; None when it went, else why not (for the Reminders column)."""
        nonlocal settings
        try:
          settings = settings or load_mail_settings()
          send_email(settings, compose_reminder(settings, reminder))
          return None
        except MailUnavailable as failure:
          return f"the email: {failure}"
        except Exception as failure:  # never stop the run
          logger.error("Task reminder %s (%s) not emailed: %s", scheduled_id, which, type(failure).__name__)
          return "the email (the details are in the server's log)"

      if by_email:
        problem = email_it()
        if problem is None:
          went.append("email")
        else:
          failures.append(problem)
      if number:
        try:
          if sms.send_text(number, compose_reminder_text(reminder)):
            went.append("text")
          else:
            failures.append("the text")
        except Exception as failure:  # never stop the run
          logger.error("Task reminder %s (%s) not texted: %s", scheduled_id, which, type(failure).__name__)
          failures.append("the text (the details are in the server's log)")
        # A member who chose texts only: when the text fails, the reminder goes by email instead, if they have a
        # confirmed address (the owner's request, 2026-11-23; a reminder is never tried again).
        if "text" not in went and not by_email and address and confirmed:
          problem = email_it()
          if problem is None:
            _finish(scheduled_id, which, "Sent by email (the text could not be sent).")
            result["sent"] += 1
            continue
          failures.append(problem)
      if went:
        outcome = "Sent by " + " and ".join(went)
        if failures:
          outcome += "; not sent: " + "; ".join(failures)
        _finish(scheduled_id, which, outcome + ".")
        result["sent"] += 1
      else:
        _finish(scheduled_id, which, "Not sent: " + "; ".join(failures) + ".")
        result["failed"] += 1
  return result

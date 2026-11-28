"""Members asking for a task, and taking themselves off one, from My scheduled tasks on the site (the owner's
request, 2026-11-27), and the emails that go with it.

- offered(): the tasks a member may ask for (those of the groups they are in: admin_tasks.group_id) with their dates in
  the next two months that the member does not already have and that do not already have as many people as the task
  expects (expected_occurrences).
- request_task(): adds the member to a task on one of those dates, NOT confirmed. Their group leader is emailed.
- withdraw(): takes the member off one of their own coming tasks (confirmed or not). Their group leader is emailed.
- tell_confirmed(): when a leader ticks Confirmed on the Drupal page (scheduled_tasks.update_scheduled), the member
  is told, by email (or by text when that is the only way they chose and can be reached).

"The leader" is the leader of the task's group (member_groups.owner_name, owner_email); for a task with no group
(one an administrator scheduled them for), the leader of each group the member is in.
"""

import logging
from datetime import date, timedelta
from email.message import EmailMessage
from html import escape

import admin_tasks
import scheduled_tasks
import sms
from admin_tasks import TaskProblem
from contact import MailUnavailable, load_mail_settings, send_email
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger(__name__)

# The dates offered: from today to the same day two months on.
MONTHS_AHEAD = 2
# At most this many coming tasks a member may have asked for that are not confirmed yet.
MAX_WAITING_REQUESTS = 20


class RequestProblem(Exception):
  """A request the site refuses, with words for the member; status_code is the HTTP answer."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


def _months_on(day: date, months: int) -> date:
  return scheduled_tasks.months_on(day, months)


def _member(connection, user_id: int) -> dict:
  row = connection.execute(
    """SELECT first_name, last_name, email, email_verified_at IS NOT NULL, COALESCE(phone, ''), disabled_at IS NOT NULL
    FROM users WHERE id = %s""",
    (user_id,),
  ).fetchone()
  if row is None:
    raise RequestProblem("Please log in again.", 401)
  name = " ".join(part for part in (row[0] or "", row[1] or "") if part).strip()
  return {"id": user_id, "first_name": row[0], "last_name": row[1], "name": name or (row[2] or row[4] or "A member"),
          "email": row[2], "email_verified": row[3], "phone": row[4], "closed": row[5]}


def _groups(connection, user_id: int) -> list[dict]:
  """The member's groups with their leaders (only as a site account)."""
  rows = connection.execute(
    """SELECT DISTINCT g.id, g.name, g.owner_uid, g.owner_name, g.owner_email
    FROM member_groups g JOIN group_members m ON m.group_id = g.id WHERE m.user_id = %s ORDER BY g.id""",
    (user_id,),
  ).fetchall()
  return [{"id": row[0], "name": row[1], "owner_uid": row[2], "owner_name": row[3], "owner_email": row[4]} for row in rows]


def _leaders(groups: list[dict], task_group_id: int | None) -> list[dict]:
  """Who to tell about a task: the leader of the task's group, else (a task with no group, or of a group the member
  is not in) every leader of their groups. One entry per address (a leader of two groups is told once); leaders
  without an address are left out."""
  chosen = [group for group in groups if group["id"] == task_group_id] or groups
  leaders, seen = [], set()
  for group in chosen:
    address = (group["owner_email"] or "").strip()
    if address and address.lower() not in seen:
      seen.add(address.lower())
      leaders.append({"name": group["owner_name"], "email": address, "group": group["name"]})
  return leaders


def _taken_days(connection, user_id: int, task_id: int) -> set[date]:
  rows = connection.execute(
    "SELECT on_date FROM admin_scheduled_tasks WHERE user_id = %s AND task_id = %s", (user_id, task_id)
  ).fetchall()
  return {row[0] for row in rows}


def _full_days(connection, task: dict, start: date, end: date) -> set[date]:
  """The days on which the task already has as many people as it expects (expected_occurrences; migration 074)."""
  rows = connection.execute(
    """SELECT on_date FROM admin_scheduled_tasks WHERE task_id = %s AND on_date BETWEEN %s AND %s
    GROUP BY on_date HAVING count(*) >= %s""",
    (task["id"], start, end, task.get("expected_occurrences") or 1),
  ).fetchall()
  return {row[0] for row in rows}


def _dates(task: dict, today: date, taken: set[date]) -> list[date]:
  """The task's dates from today to two months on, leaving out `taken` (the member's own and the full ones)."""
  end = _months_on(today, MONTHS_AHEAD)
  rule = scheduled_tasks._rule(task)
  days, day = [], today
  while True:
    try:
      day = admin_tasks.next_date(rule, day)
    except TaskProblem:
      break
    if day > end:
      break
    if day not in taken:
      days.append(day)
    day += timedelta(days=1)
  return days


def _offered_tasks(connection, user_id: int, groups: list[dict]) -> list[dict]:
  """The tasks of the member's groups (admin_tasks.group_id); a task with no group is offered to nobody."""
  group_ids = {group["id"] for group in groups}
  if not group_ids:
    return []
  return [task for task in admin_tasks.list_tasks() if task["group_id"] in group_ids]


def offered(user_id: int, today: date | None = None) -> dict:
  """The tasks this member may ask for, each with its dates in the next two months they do not have yet:
  {"tasks": [{id, name, description_html, dates: [{value, label}]}]}. Tasks with no free date are left out."""
  today = today or date.today()
  with connect() as connection:
    member = _member(connection, user_id)
    groups = _groups(connection, user_id)
    tasks = _offered_tasks(connection, user_id, groups)
    answer = []
    for task in tasks:
      days = _dates(task, today, _taken_days(connection, user_id, task["id"]) | _full_days(connection, task, today, _months_on(today, MONTHS_AHEAD)))
      if days:
        answer.append({
          "id": task["id"],
          "name": scheduled_tasks.fill_names(task["name"], member["first_name"], member["last_name"]),
          "dates": [{"value": day.isoformat(), "label": scheduled_tasks.date_label(day)} for day in days],
        })
  return {"tasks": answer}


def request_task(user_id: int, task_id: int, on_date: str, today: date | None = None) -> dict:
  """Adds the member to the task on that date, not confirmed. Answers {"scheduled": {...}, "notice": {...}} where
  notice is what tell_leaders sends (after the answer)."""
  today = today or date.today()
  try:
    day = date.fromisoformat(str(on_date))
  except ValueError:
    raise RequestProblem("Choose a date.")
  with connect() as connection:
    member = _member(connection, user_id)
    groups = _groups(connection, user_id)
    if not groups:
      raise RequestProblem("Only members of a group can ask for tasks.", 403)
    task = next((each for each in _offered_tasks(connection, user_id, groups) if each["id"] == task_id), None)
    if task is None:
      raise RequestProblem("That task is not one you can ask for.")
    if day not in _dates(task, today, _taken_days(connection, user_id, task_id) | _full_days(connection, task, today, _months_on(today, MONTHS_AHEAD))):
      raise RequestProblem("That date is not offered for this task (it may have been taken already). Choose another.")
    waiting = connection.execute(
      "SELECT count(*) FROM admin_scheduled_tasks WHERE user_id = %s AND NOT confirmed AND on_date >= %s",
      (user_id, today),
    ).fetchone()[0]
    if waiting >= MAX_WAITING_REQUESTS:
      raise RequestProblem(f"You have {waiting} tasks waiting to be confirmed. Please wait for those first.", 429)
    scheduled_id = connection.execute(
      """INSERT INTO admin_scheduled_tasks (task_id, user_id, on_date, created_by_uid, created_by_name, confirmed)
      VALUES (%s, %s, %s, 0, %s, false) RETURNING id""",
      (task_id, user_id, day, f"{member['name']} (on the site)"[:200]),
    ).fetchone()[0]
  return {
    "scheduled": scheduled_tasks.get_scheduled(scheduled_id, today),
    "notice": {"kind": "request", "member": member, "task_name": task["name"], "on_date": day.isoformat(),
               "leaders": _leaders(groups, task["group_id"])},
  }


def withdraw(user_id: int, scheduled_id: int, today: date | None = None) -> dict:
  """Takes the member off one of their own coming tasks. Answers {"notice": {...}} for tell_leaders."""
  today = today or date.today()
  with connect() as connection:
    member = _member(connection, user_id)
    row = connection.execute(
      """SELECT s.on_date, s.confirmed, t.name, t.group_id FROM admin_scheduled_tasks s JOIN admin_tasks t ON t.id = s.task_id
      WHERE s.id = %s AND s.user_id = %s""",
      (scheduled_id, user_id),
    ).fetchone()
    if row is None:
      raise RequestProblem("That task was not found. It may have been removed already.", 404)
    if row[0] < today:
      raise RequestProblem("A task that has already happened cannot be removed.")
    groups = _groups(connection, user_id)
    connection.execute("DELETE FROM admin_scheduled_tasks WHERE id = %s AND user_id = %s", (scheduled_id, user_id))
  return {"notice": {"kind": "withdraw", "member": member, "task_name": row[2], "on_date": row[0].isoformat(),
                     "was_confirmed": row[1], "leaders": _leaders(groups, row[3])}}


def compose_leader_email(settings: dict, notice: dict, leader: dict) -> EmailMessage:
  """To a group leader: a member asked for a task, or took themselves off one. Reply-To the member."""
  title = get_public_settings()["title"]
  member = notice["member"]
  task_name = scheduled_tasks.fill_names(notice["task_name"], member["first_name"], member["last_name"])
  day = scheduled_tasks.date_label(date.fromisoformat(notice["on_date"]))
  contact = ", ".join(part for part in (member["email"] or "", member["phone"]) if part)
  who = f"{member['name']} ({contact})" if contact and contact != member["name"] else member["name"]
  if notice["kind"] == "request":
    subject = f"Task request: {member['name']} for {task_name} on {day}"
    lines = [
      f"{who} asked on {title} to be scheduled for “{task_name}” on {day}.",
      "It is not confirmed yet. To confirm it, open Scheduled tasks on the admin site, choose Edit beside it and tick "
      "Confirmed; they will be told by email. To turn it down, Remove it there and let them know.",
    ]
  else:
    subject = f"Task removed: {member['name']} is off {task_name} on {day}"
    lines = [
      f"{who} took themselves off “{task_name}” on {day} on {title}"
      + (" (it was confirmed)." if notice.get("was_confirmed") else " (it was not confirmed yet)."),
      "You may want to find someone else for that date.",
    ]
  foot = f"You get this as the leader of the group “{leader['group']}” on {title}."
  email = EmailMessage()
  email["Subject"] = subject
  email["From"] = settings["from_address"]
  email["To"] = leader["email"]
  if member["email"]:
    email["Reply-To"] = member["email"]
  text = "\n\n".join(lines)
  email.set_content(f"Hello {leader['name'] or 'there'},\n\n{text}\n\n--\n{foot}\n")
  email.add_alternative(
    "<html><body>" + f"<p>Hello {escape(leader['name'] or 'there')},</p>"
    + "".join(f"<p>{escape(line)}</p>" for line in lines) + f"<hr><p>{escape(foot)}</p></body></html>",
    subtype="html",
  )
  return email


def tell_leaders(notice: dict) -> int:
  """Emails each leader of the notice (run after the member's answer). Failures are logged, never raised. Returns
  how many emails went."""
  if not notice.get("leaders"):
    logger.warning("No group leader with an address to tell about a task %s (member %s).", notice["kind"], notice["member"]["id"])
    return 0
  try:
    settings = load_mail_settings()
  except MailUnavailable as problem:
    logger.warning("Task %s email not sent: %s", notice["kind"], problem)
    return 0
  sent = 0
  for leader in notice["leaders"]:
    try:
      send_email(settings, compose_leader_email(settings, notice, leader))
      sent += 1
    except Exception:  # A mail failure never undoes the member's change.
      logger.exception("Task %s email to a group leader failed (member %s).", notice["kind"], notice["member"]["id"])
  return sent


def tell_confirmed(scheduled_id: int) -> str:
  """Tells the member their task is confirmed (a leader ticked Confirmed): by email to a confirmed address, else by
  text when they chose texts. Returns what happened, for the log; never raises."""
  try:
    scheduled = scheduled_tasks.get_scheduled(scheduled_id)
    task = admin_tasks.get_task(scheduled["task_id"])
    with connect() as connection:
      member = _member(connection, scheduled["user_id"])
    by_email, number, reason = scheduled_tasks._ways(member["id"], member["email"], member["email_verified"], member["closed"])
    if reason:
      return reason.replace("Not sent:", "Not told:")
    title = get_public_settings()["title"]
    task_name = scheduled_tasks.fill_names(task["name"], member["first_name"], member["last_name"])
    day = scheduled_tasks.date_label(date.fromisoformat(scheduled["on_date"]))
    words = f"You are confirmed for “{task_name}” on {day}."
    leader = task["owner_name"] or "the leader"
    done = []
    if by_email:
      settings = load_mail_settings()
      email = EmailMessage()
      email["Subject"] = f"Confirmed: {task_name} on {day}"
      email["From"] = settings["from_address"]
      email["To"] = member["email"]
      if task.get("owner_email"):
        email["Reply-To"] = task["owner_email"]
      greeting = f"Hello {member['first_name']}," if member["first_name"] else "Hello,"
      more = f"If you can no longer do it, let {leader} know or remove it on My scheduled tasks on {title}."
      email.set_content(f"{greeting}\n\n{words}\n\n{more}\n\n--\nSent by {title}.\n")
      email.add_alternative(
        f"<html><body><p>{escape(greeting)}</p><p>{escape(words)}</p><p>{escape(more)}</p><hr>"
        f"<p>Sent by {escape(title)}.</p></body></html>",
        subtype="html",
      )
      send_email(settings, email)
      done.append("email")
    if number and not by_email:
      if sms.send_text(number, sms.compose(words)):
        done.append("text")
    return "Told by " + " and ".join(done) if done else "Not told."
  except MailUnavailable as problem:
    return f"Not told: {problem}"
  except Exception:
    logger.exception("Telling a member their task %s is confirmed failed.", scheduled_id)
    return "Not told (an error)."

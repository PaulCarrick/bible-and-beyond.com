"""Scheduled group messages (added 2026-11-16 at the owner's request: "Add a scheduled email" on a group's page,
"at a specific day of the month or a date like the first Monday of the month ... a time as well ... the message
to be set ... edited or removed").

A schedule sends one of the group's three kinds (groups.py) to the whole group: a message (subject and words),
a verse card (a new random verse each time) or a picture message (the leader's words on a new random picture
each time), by email and text as each member chose. When:

- once: on a date;
- weekly: every week on a weekday;
- monthly_day: every month on a day (1 to 31; a day the month does not have means its last day);
- monthly_weekday: every month on the first, second, third, fourth or last (5) of a weekday;

at a time of day in a time zone (the leader's own Drupal time zone to start). next_run_at keeps the next time in
UTC. The five-minute job (scripts/send_devotional_emails.py) sends what is due: each schedule is claimed (its
next time moved on) before it is sent, so nothing goes twice; a run missed by more than LATE_LIMIT (the job was
not running) is skipped, not sent late. What was sent is recorded in group_messages like a send from the page.
"""

import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import groups
from groups import GroupProblem
from search import connect
from subscriptions import SubscriptionProblem, check_timezone, parse_time

logger = logging.getLogger("group_schedules")

REPEATS = ("once", "weekly", "monthly_day", "monthly_weekday")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "last"}
LATE_LIMIT = timedelta(hours=6)
LOCK_NUMBER = 7281004
MAX_SCHEDULES_PER_GROUP = 50


# --- when ----------------------------------------------------------------------------------------------------


def _day_in_month(year: int, month: int, schedule: dict) -> int:
  """The day of the month a monthly schedule falls on in that month."""
  last = calendar.monthrange(year, month)[1]
  if schedule["repeat"] == "monthly_day":
    return min(schedule["day_of_month"], last)
  weekday, week = schedule["weekday"], schedule["week_of_month"]
  if week == 5:
    day = last
    while date(year, month, day).weekday() != weekday:
      day -= 1
    return day
  first = date(year, month, 1).weekday()
  return 1 + (weekday - first) % 7 + 7 * (week - 1)


def next_occurrence(schedule: dict, after: datetime) -> datetime | None:
  """The first time the schedule falls strictly after `after` (UTC), or None when a one-time message's time has
  passed."""
  zone = ZoneInfo(schedule["timezone"])
  send_time = schedule["send_time"]
  local_after = after.astimezone(zone)

  def at(day: date) -> datetime:
    return datetime.combine(day, send_time, tzinfo=zone).astimezone(timezone.utc)

  if schedule["repeat"] == "once":
    moment = at(schedule["on_date"])
    return moment if moment > after else None
  if schedule["repeat"] == "weekly":
    day = local_after.date() + timedelta(days=(schedule["weekday"] - local_after.weekday()) % 7)
    while at(day) <= after:
      day += timedelta(days=7)
    return at(day)
  year, month = local_after.year, local_after.month
  for _ in range(14):
    moment = at(date(year, month, _day_in_month(year, month, schedule)))
    if moment > after:
      return moment
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
  return None


def describe(schedule: dict) -> str:
  """The schedule in words, such as "Every month on the first Monday at 9:00 AM (America/Chicago)"."""
  clock = schedule["send_time"].strftime("%I:%M %p").lstrip("0")
  zone = f"({schedule['timezone']})"
  if schedule["repeat"] == "once":
    return f"Once, on {schedule['on_date'].strftime('%A, %B %-d, %Y')} at {clock} {zone}"
  if schedule["repeat"] == "weekly":
    return f"Every {WEEKDAYS[schedule['weekday']]} at {clock} {zone}"
  if schedule["repeat"] == "monthly_day":
    day = schedule["day_of_month"]
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    note = " (the last day in shorter months)" if day > 28 else ""
    return f"Every month on the {day}{suffix}{note} at {clock} {zone}"
  return f"Every month on the {WEEKS[schedule['week_of_month']]} {WEEKDAYS[schedule['weekday']]} at {clock} {zone}"


# --- keeping them --------------------------------------------------------------------------------------------

COLUMNS = (
  "id, group_id, kind, subject, text, repeat, on_date, day_of_month, weekday, week_of_month, send_time, timezone, "
  "next_run_at, last_run_at, last_result, created_by, html, member_id, signature_id, show_sent_by, saved_card_id, "
  "card_user_id"
)


def _row(row) -> dict:
  schedule = dict(zip([name.strip() for name in COLUMNS.split(",")], row))
  return schedule


def _public(schedule: dict) -> dict:
  """A schedule as the tool answers it (dates as text, the words for the page)."""
  return {
    "id": schedule["id"],
    "group_id": schedule["group_id"],
    "kind": schedule["kind"],
    "subject": schedule["subject"],
    "text": schedule["text"],
    "repeat": schedule["repeat"],
    "on_date": schedule["on_date"].isoformat() if schedule["on_date"] else None,
    "day_of_month": schedule["day_of_month"],
    "weekday": schedule["weekday"],
    "week_of_month": schedule["week_of_month"],
    "send_time": schedule["send_time"].strftime("%H:%M"),
    "timezone": schedule["timezone"],
    "description": describe(schedule),
    "next_run_at": schedule["next_run_at"].isoformat() if schedule["next_run_at"] else None,
    "next_run_local": schedule["next_run_at"].astimezone(ZoneInfo(schedule["timezone"])).strftime("%a %b %-d, %Y %-I:%M %p") if schedule["next_run_at"] else None,
    "last_run_at": schedule["last_run_at"].isoformat() if schedule["last_run_at"] else None,
    "last_result": schedule["last_result"],
    "created_by": schedule["created_by"],
    # A message written in the editor (migration 050); None for a picture, a verse card or an older message.
    "html": schedule["html"],
    # A message to one member (migration 052): that member's id; None for the group's own scheduled emails.
    "member_id": schedule["member_id"],
    # The signature chosen for it (migration 057), or None.
    "signature_id": schedule["signature_id"],
    # Whether its emails end with the "Sent by …" line (migration 070).
    "show_sent_by": schedule["show_sent_by"],
    # A message's saved verse card (migration 072), or None (none chosen, or deleted since).
    "saved_card_id": schedule["saved_card_id"],
  }


def label(schedule: dict) -> str:
  """A scheduled email in a few words, for its stop link ("the verse card", or its subject)."""
  return "the verse card" if schedule["kind"] == "verse" else f"“{schedule['subject']}”"


def list_schedules(group_id: int) -> list[dict]:
  """The group's schedules, each with how many members stopped it: itself, or all the group's scheduled emails
  (stopped_count)."""
  with connect() as connection:
    rows = connection.execute(
      f"SELECT {COLUMNS} FROM group_schedules WHERE group_id = %s ORDER BY next_run_at NULLS LAST, id", (group_id,)
    ).fetchall()
    stopped = dict(connection.execute(
      """
      SELECT s.id, count(m.id) FROM group_schedules s
      JOIN group_members m ON m.group_id = s.group_id AND m.stopped_at IS NULL
        AND (m.schedules_stopped_at IS NOT NULL OR EXISTS (SELECT 1 FROM group_schedule_stops t WHERE t.schedule_id = s.id AND t.member_id = m.id))
      WHERE s.group_id = %s AND s.member_id IS NULL GROUP BY s.id
      """,
      (group_id,),
    ).fetchall())
    names = dict(connection.execute(
      """
      SELECT m.id, COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), NULLIF(m.name, ''), COALESCE(u.email, m.email), '')
      FROM group_members m LEFT JOIN users u ON u.id = m.user_id WHERE m.group_id = %s
      """,
      (group_id,),
    ).fetchall())
    signature_names = dict(connection.execute(
      "SELECT a.id, a.name FROM admin_signatures a JOIN group_schedules s ON s.signature_id = a.id WHERE s.group_id = %s", (group_id,)
    ).fetchall())
  return [
    _public(schedule) | {
      "stopped_count": stopped.get(schedule["id"], 0),
      "member_name": names.get(schedule["member_id"]) if schedule["member_id"] else None,
      "signature_name": signature_names.get(schedule["signature_id"]),
    }
    for schedule in map(_row, rows)
  ]


def _get(schedule_id: int, group_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {COLUMNS} FROM group_schedules WHERE id = %s AND group_id = %s", (schedule_id, group_id)).fetchone()
  if row is None:
    raise GroupProblem("That scheduled message is not in this group (it may have been removed).")
  return _row(row)


def _int(details: dict, name: str, low: int, high: int, label: str) -> int:
  try:
    value = int(details.get(name))
  except (TypeError, ValueError):
    raise GroupProblem(f"Please choose the {label}.")
  if not low <= value <= high:
    raise GroupProblem(f"Please choose the {label}.")
  return value


def check(details: dict, now: datetime) -> dict:
  """The schedule's fields, checked, with its next time; raises GroupProblem with a message for the leader."""
  kind = details.get("kind")
  if kind not in groups.KINDS:
    raise GroupProblem("Please choose what to send.")
  repeat = details.get("repeat")
  if repeat not in REPEATS:
    raise GroupProblem("Please choose when it goes.")
  try:
    send_time = parse_time(str(details.get("send_time", "")))
    check_timezone(str(details.get("timezone", "")))
  except SubscriptionProblem as problem:
    raise GroupProblem(str(problem)) from problem
  schedule = {
    "kind": kind, "subject": "", "text": "", "html": None, "repeat": repeat, "on_date": None, "day_of_month": None, "weekday": None,
    "week_of_month": None, "send_time": send_time, "timezone": str(details["timezone"]),
  }
  if kind == "message":
    schedule["subject"] = groups._one_line(details.get("subject", ""), "subject", groups.SUBJECT_LIMIT)
    if details.get("html") is not None:
      # Written in the editor: cleaned, with its plain-text copy in text (for texts).
      schedule["html"], schedule["text"] = groups.message_html(str(details["html"]))
    else:
      schedule["text"] = groups._text(details.get("text", ""), "message", groups.MESSAGE_LIMIT)
  elif kind == "picture":
    schedule["subject"] = groups._one_line(details.get("subject", ""), "subject", groups.SUBJECT_LIMIT)
    schedule["text"] = groups._text(details.get("text", ""), "words for the picture", groups.PICTURE_TEXT_LIMIT)
  if repeat == "once":
    try:
      schedule["on_date"] = date.fromisoformat(str(details.get("on_date", "")))
    except ValueError:
      raise GroupProblem("Please choose the date.")
  elif repeat == "weekly":
    schedule["weekday"] = _int(details, "weekday", 0, 6, "day of the week")
  elif repeat == "monthly_day":
    schedule["day_of_month"] = _int(details, "day_of_month", 1, 31, "day of the month")
  else:
    schedule["weekday"] = _int(details, "weekday", 0, 6, "day of the week")
    schedule["week_of_month"] = _int(details, "week_of_month", 1, 5, "week of the month")
  schedule["next_run_at"] = next_occurrence(schedule, now)
  if schedule["next_run_at"] is None:
    raise GroupProblem("That date and time have already passed.")
  return schedule


FIELDS = (
  "kind", "subject", "text", "html", "repeat", "on_date", "day_of_month", "weekday", "week_of_month", "send_time", "timezone", "next_run_at",
  "signature_id", "show_sent_by", "saved_card_id", "card_user_id",
)


def _card(schedule: dict, details: dict) -> None:
  """The saved verse card chosen for a message (details["saved_card"]; groups.card_owner checks it is the sender's
  own), kept with the site account it belongs to; none for a verse card or a picture."""
  owner = groups.card_owner(details) if schedule["kind"] == "message" else None
  schedule["card_user_id"], schedule["saved_card_id"] = owner if owner else (None, None)


def add_schedule(group_id: int, details: dict, created_by: str, now: datetime | None = None) -> dict:
  group = groups.get_group(group_id)
  schedule = check(details, now or datetime.now(timezone.utc))
  schedule["signature_id"] = groups.leader_signature(group, details.get("signature_id"))
  schedule["show_sent_by"] = details.get("show_sent_by", True) is not False
  _card(schedule, details)
  with connect() as connection:
    if connection.execute("SELECT count(*) FROM group_schedules WHERE group_id = %s", (group_id,)).fetchone()[0] >= MAX_SCHEDULES_PER_GROUP:
      raise GroupProblem(f"A group can have at most {MAX_SCHEDULES_PER_GROUP} scheduled messages.")
    schedule_id = connection.execute(
      f"INSERT INTO group_schedules (group_id, created_by, {', '.join(FIELDS)}) VALUES (%s, %s, {', '.join(['%s'] * len(FIELDS))}) RETURNING id",
      (group_id, created_by, *[schedule[name] for name in FIELDS]),
    ).fetchone()[0]
  return _public(_get(schedule_id, group_id))


def update_schedule(group_id: int, schedule_id: int, details: dict, now: datetime | None = None) -> dict:
  """Replaces a schedule's message and timing; its next time is worked out again from now. The card it already has
  is kept when it is chosen again, even by someone other than whoever set it up."""
  existing = _get(schedule_id, group_id)
  if existing["member_id"] is not None:
    raise GroupProblem("A message to one member cannot be changed: remove it and write it again.")
  schedule = check(details, now or datetime.now(timezone.utc))
  schedule["signature_id"] = groups.leader_signature(groups.get_group(group_id), details.get("signature_id"))
  schedule["show_sent_by"] = details.get("show_sent_by", True) is not False
  if schedule["kind"] == "message" and existing["saved_card_id"] and str(details.get("saved_card") or "") == str(existing["saved_card_id"]):
    schedule["saved_card_id"], schedule["card_user_id"] = existing["saved_card_id"], existing["card_user_id"]
  else:
    _card(schedule, details)
  with connect() as connection:
    connection.execute(
      f"UPDATE group_schedules SET {', '.join(f'{name} = %s' for name in FIELDS)}, updated_at = now() WHERE id = %s",
      (*[schedule[name] for name in FIELDS], schedule_id),
    )
  return _public(_get(schedule_id, group_id))


def schedule_member_email(group_id: int, member_id: int, details: dict, created_by: str, now: datetime | None = None) -> dict:
  """A message to one member sent later ("Send at" on a member's Email box; added 2026-11-18 at the owner's
  request): a one-time scheduled email with member_id set, on details' on_date at send_time in timezone, holding
  the message (html from the editor, or text). The member is checked now, and again when it goes (they may stop
  the group's messages or be removed meanwhile; removing them removes it). Returns the schedule."""
  group = groups.get_group(group_id)
  if not any(member["id"] == member_id for member in group["members"]):
    raise GroupProblem("That member is not in the group (they may have been removed).")
  groups.member_recipient(group_id, member_id)
  html = details.get("html")
  text, html = groups.member_message(str(details.get("text", "")), str(html) if html is not None else None)
  try:
    send_time = parse_time(str(details.get("send_time", "")))
    check_timezone(str(details.get("timezone", "")))
    on_date = date.fromisoformat(str(details.get("on_date", "")))
  except (SubscriptionProblem, ValueError):
    raise GroupProblem("Please choose the date and time to send it.")
  schedule = {
    "kind": "message", "subject": groups.member_subject(group, str(details.get("subject") or "")), "text": text, "html": html, "repeat": "once",
    "on_date": on_date, "day_of_month": None, "weekday": None, "week_of_month": None, "send_time": send_time,
    "timezone": str(details["timezone"]), "signature_id": groups.leader_signature(group, details.get("signature_id")),
    # An email to one member has no foot at all (groups.compose_email, personal).
    "show_sent_by": True,
  }
  _card(schedule, details)
  schedule["next_run_at"] = next_occurrence(schedule, now or datetime.now(timezone.utc))
  if schedule["next_run_at"] is None:
    raise GroupProblem("That date and time have already passed.")
  with connect() as connection:
    if connection.execute("SELECT count(*) FROM group_schedules WHERE group_id = %s", (group_id,)).fetchone()[0] >= MAX_SCHEDULES_PER_GROUP:
      raise GroupProblem(f"A group can have at most {MAX_SCHEDULES_PER_GROUP} scheduled messages.")
    schedule_id = connection.execute(
      f"INSERT INTO group_schedules (group_id, created_by, member_id, {', '.join(FIELDS)}) VALUES (%s, %s, %s, {', '.join(['%s'] * len(FIELDS))}) RETURNING id",
      (group_id, created_by, member_id, *[schedule[name] for name in FIELDS]),
    ).fetchone()[0]
  return _public(_get(schedule_id, group_id))


def remove_schedule(group_id: int, schedule_id: int) -> dict:
  schedule = _public(_get(schedule_id, group_id))
  with connect() as connection:
    connection.execute("DELETE FROM group_schedules WHERE id = %s", (schedule_id,))
  return schedule


def get_schedule(group_id: int, schedule_id: int) -> dict:
  return _public(_get(schedule_id, group_id))


# --- sending -------------------------------------------------------------------------------------------------


def _details_for(schedule: dict) -> dict:
  details = _details_of_kind(schedule)
  # Whether its emails end with the "Sent by …" line (migration 070).
  details["show_sent_by"] = schedule.get("show_sent_by", True) is not False
  return details


def _details_of_kind(schedule: dict) -> dict:
  """What groups.send needs, made at send time: a new random verse card, or the words on a new random picture."""
  if schedule["kind"] == "verse":
    preview = groups.preview_verse()
    return {"card": preview["card"], "verse": preview["verse"]}
  if schedule["kind"] == "picture":
    preview = groups.preview_picture(schedule["text"])
    return {"subject": schedule["subject"], "text": schedule["text"], "card": preview["card"]}
  details = {"subject": schedule["subject"], "html": schedule["html"]} if schedule.get("html") else {"subject": schedule["subject"], "text": schedule["text"]}
  if schedule.get("saved_card_id") and schedule.get("card_user_id"):
    # The saved verse card chosen, from the account of whoever set it up (migration 072).
    details["saved_card"] = schedule["saved_card_id"]
    details["card_user_id"] = schedule["card_user_id"]
  return details


def send_test(group_id: int, schedule_id: int) -> dict:
  """"Send a test" on a scheduled email: what it would send now (a verse card or picture made afresh, as at its
  time), to the group's leader only, exactly as a member gets it, stop links included (groups.send_test). The schedule is not changed: its next time, last time and
  result stay. Returns {"to": the leader's address, "schedule": the schedule}."""
  schedule = _get(schedule_id, group_id)
  sent = groups.send_test(group_id, schedule["kind"], _details_for(schedule), schedule={"id": schedule["id"], "label": label(schedule), "signature": groups.signature_words(schedule["signature_id"])})
  return {"to": sent["to"], "schedule": _public(schedule)}


def send_due(now: datetime | None = None, pause: float = groups.PAUSE_BETWEEN_MEMBERS) -> dict:
  """Sends every scheduled message that is due. Returns how many were sent, skipped (too late) and failed."""
  now = now or datetime.now(timezone.utc)
  result = {"sent": 0, "late": 0, "failed": 0, "already_running": False}
  with connect() as lock_connection:
    if not lock_connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_NUMBER,)).fetchone()[0]:
      result["already_running"] = True
      return result
    with connect() as connection:
      rows = connection.execute(
        f"SELECT {COLUMNS} FROM group_schedules WHERE next_run_at IS NOT NULL AND next_run_at <= %s ORDER BY next_run_at, id", (now,)
      ).fetchall()
    for row in rows:
      schedule = _row(row)
      due = schedule["next_run_at"]
      following = next_occurrence(schedule, max(now, due))
      # Claim it first (its next time moved on), so no other run sends it again.
      with connect() as connection:
        claimed = connection.execute(
          "UPDATE group_schedules SET next_run_at = %s, last_run_at = %s WHERE id = %s AND next_run_at = %s RETURNING id",
          (following, now, schedule["id"], due),
        ).fetchone()
      if claimed is None:
        continue
      if now - due > LATE_LIMIT:
        outcome = f"Skipped: it was due {due:%Y-%m-%d %H:%M} UTC but the sender was not running then."
        result["late"] += 1
      else:
        try:
          if schedule["member_id"] is not None:
            # A message to one member: the same email as Send on their box (groups.email_member).
            member = groups.email_member(
              schedule["group_id"], schedule["member_id"], schedule["text"], f"schedule ({schedule['created_by']})",
              html=schedule["html"], subject=schedule["subject"], signature=groups.signature_words(schedule["signature_id"]),
              card=groups._saved_card(_details_of_kind(schedule)),
            )
            outcome = f"Emailed to {member['name'] or 'the member'}"
            result["sent"] += 1
            with connect() as connection:
              connection.execute("UPDATE group_schedules SET last_result = %s WHERE id = %s", (outcome, schedule["id"]))
            continue
          counts = groups.send(
            schedule["group_id"], schedule["kind"], _details_for(schedule), f"schedule ({schedule['created_by']})", pause=pause,
            schedule={"id": schedule["id"], "label": label(schedule), "signature": groups.signature_words(schedule["signature_id"])},
          )
          outcome = f"{counts['emailed']} emailed, {counts['texted']} texted" + (f", {counts['skipped']} skipped" if counts["skipped"] else "") + (f", {counts['failed']} failed" if counts["failed"] else "")
          result["sent"] += 1
        except Exception as problem:  # never stop the run
          logger.error("Scheduled message %s not sent: %s", schedule["id"], type(problem).__name__)
          outcome = f"Not sent: {problem}" if isinstance(problem, GroupProblem) else "Not sent (the details are in the server's log)."
          result["failed"] += 1
      with connect() as connection:
        connection.execute("UPDATE group_schedules SET last_result = %s WHERE id = %s", (outcome, schedule["id"]))
    lock_connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_NUMBER,))
  return result

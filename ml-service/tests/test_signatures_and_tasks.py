"""Tests for the signatures (signatures.py) and tasks (admin_tasks.py) of the Drupal admin. They use the real
tables: their rows are set aside before each test and put back afterwards."""

import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import admin_tasks
import scheduled_tasks
import signatures
from admin_tasks import TaskProblem, next_date
from search import connect
from signatures import SignatureProblem

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
OWNER = 990001
OTHER_OWNER = 990002


@pytest.fixture(autouse=True)
def empty_tables():
  """Sets the stored signatures and tasks aside and puts them back, with their ids, after the test."""
  saved = {}
  with connect() as connection:
    for table in ("admin_signatures", "admin_tasks", "admin_scheduled_tasks"):
      cursor = connection.execute(f"SELECT * FROM {table}")
      saved[table] = ([column.name for column in cursor.description], cursor.fetchall())
    connection.execute("DELETE FROM admin_scheduled_tasks")
    connection.execute("DELETE FROM admin_signatures")
    connection.execute("DELETE FROM admin_tasks")
  yield
  with connect() as connection:
    connection.execute("DELETE FROM admin_scheduled_tasks")
    for table, (columns, rows) in saved.items():
      connection.execute(f"DELETE FROM {table}")
      for row in rows:
        connection.execute(
          f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})", row
        )
      connection.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), GREATEST((SELECT max(id) FROM {table}), 1))")


def run_tool(script: str, arguments: list[str], details: dict | None = None) -> tuple[int, dict]:
  completed = subprocess.run(
    [sys.executable, str(SCRIPTS / script), *arguments],
    input=json.dumps(details) if details is not None else "",
    capture_output=True, text=True, check=False,
  )
  return completed.returncode, json.loads(completed.stdout)


# --- signatures --------------------------------------------------------------------------------------------


def test_a_signature_is_cleaned_and_kept_with_a_text_copy():
  signature = signatures.create_signature(
    {"name": "  Ministry   email ", "signature": {"html": '<p onclick="x()"><strong>Paul</strong><br>Leader</p><script>bad()</script>'}},
    OWNER, "Paul",
  )
  assert signature["name"] == "Ministry email"
  assert signature["html"] == "<p><strong>Paul</strong><br>Leader</p>"
  assert "Paul" in signature["text"] and "bad" not in signature["text"]
  assert signature["owner_uid"] == OWNER and signature["owner_name"] == "Paul"
  assert signatures.get_signature(signature["id"])["html"] == signature["html"]


def test_plain_text_from_the_plain_box_becomes_paragraphs():
  signature = signatures.create_signature({"name": "Plain", "signature": {"text": "Paul <Leader>\nCelebrate Recovery\n\nGod bless"}}, OWNER, "Paul")
  assert signature["html"] == "<p>Paul &lt;Leader&gt;<br>Celebrate Recovery</p><p>God bless</p>"


def test_a_signature_needs_a_name_and_words():
  with pytest.raises(SignatureProblem, match="name is needed"):
    signatures.create_signature({"name": " ", "signature": {"html": "<p>x</p>"}}, OWNER, "Paul")
  with pytest.raises(SignatureProblem, match="Please write something"):
    signatures.create_signature({"name": "Empty", "signature": {"html": "<p> </p>"}}, OWNER, "Paul")


def test_signatures_are_listed_per_owner_changed_and_deleted():
  mine = signatures.create_signature({"name": "b mine", "signature": {"text": "One"}}, OWNER, "Paul")
  signatures.create_signature({"name": "A theirs", "signature": {"text": "Two"}}, OTHER_OWNER, "Ruth")
  assert [item["name"] for item in signatures.list_signatures(OWNER)] == ["b mine"]
  assert [item["name"] for item in signatures.list_signatures()] == ["A theirs", "b mine"]
  changed = signatures.update_signature(mine["id"], {"name": "Changed", "signature": {"html": "<p>New words</p>"}})
  assert changed["name"] == "Changed" and changed["text"] == "New words" and changed["owner_uid"] == OWNER
  signatures.delete_signature(mine["id"])
  with pytest.raises(SignatureProblem, match="not found"):
    signatures.get_signature(mine["id"])


def test_the_signatures_tool():
  status, answer = run_tool("manage_signatures.py", ["create", f"--owner={OWNER}"], {"name": "Tool", "signature": {"html": "<p>Hi</p>"}, "owner_name": "Paul"})
  assert status == 0 and answer["signature"]["owner_name"] == "Paul"
  status, answer = run_tool("manage_signatures.py", ["list", f"--owner={OWNER}"])
  assert status == 0 and [item["name"] for item in answer["signatures"]] == ["Tool"]
  status, answer = run_tool("manage_signatures.py", ["update", "--id=999999999"], {"name": "x", "signature": {"text": "y"}})
  assert status == 1 and not answer["ok"] and "not found" in answer["error"]


# --- tasks -------------------------------------------------------------------------------------------------


def task_details(**changes) -> dict:
  details = {
    "name": "Set up the room",
    "description": {"html": "<p>Chairs and <em>coffee</em>.</p>"},
    "repeat": "weekly",
    "weekday": 3,
    # A fixed start, so the dates in these tests do not depend on the day they run.
    "first_date": "2026-01-01",
    "first_notification": {"html": "<p>Tomorrow: set up the room.</p>"},
    "second_notification": {"text": ""},
  }
  details.update(changes)
  return details


def rule(repeat, start="2026-01-01", every=1, weekdays=(), weeks=(), day=None) -> dict:
  return {
    "repeat": repeat, "first_date": date.fromisoformat(start), "interval_count": every, "weekdays": list(weekdays),
    "weeks_of_month": list(weeks), "day_of_month": day,
  }


def dates(task: dict, today: date, count: int = 4) -> list[str]:
  return [day.isoformat() for day in admin_tasks.next_dates(task, today, count)]


def test_the_next_dates_of_each_repeat():
  thursday = date(2026, 11, 19)
  # Weekly, on one or several weekdays.
  assert dates(rule("weekly", weekdays=[3]), thursday, 2) == ["2026-11-19", "2026-11-26"]
  assert dates(rule("weekly", weekdays=[2, 6]), thursday) == ["2026-11-22", "2026-11-25", "2026-11-29", "2026-12-02"]
  # Every two or three weeks, counted from the week of the start; nothing before the start.
  assert dates(rule("weekly", start="2026-11-05", every=2, weekdays=[3]), date(2026, 11, 1)) == ["2026-11-05", "2026-11-19", "2026-12-03", "2026-12-17"]
  assert dates(rule("weekly", start="2026-11-20", every=3, weekdays=[4]), thursday, 2) == ["2026-11-20", "2026-12-11"]
  # Monthly on a day (the 31st is the last day of a shorter month), every three months, once a year.
  assert dates(rule("monthly_day", day=31), date(2027, 1, 1)) == ["2027-01-31", "2027-02-28", "2027-03-31", "2027-04-30"]
  assert dates(rule("monthly_day", start="2026-10-01", every=3, day=1), thursday, 3) == ["2027-01-01", "2027-04-01", "2027-07-01"]
  assert dates(rule("monthly_day", start="2026-12-01", every=12, day=25), thursday, 2) == ["2026-12-25", "2027-12-25"]
  # The first Sunday (communion), the first and third Sunday, the last Thursday of November each year.
  assert dates(rule("monthly_weekday", weekdays=[6], weeks=[1]), thursday, 3) == ["2026-12-06", "2027-01-03", "2027-02-07"]
  assert dates(rule("monthly_weekday", weekdays=[6], weeks=[1, 3]), thursday, 3) == ["2026-12-06", "2026-12-20", "2027-01-03"]
  assert dates(rule("monthly_weekday", start="2026-11-01", every=12, weekdays=[3], weeks=[5]), date(2026, 11, 1), 2) == ["2026-11-26", "2027-11-25"]
  # The fourth and the last can be the same day; it comes once.
  assert dates(rule("monthly_weekday", weekdays=[0], weeks=[4, 5]), date(2026, 2, 1), 3) == ["2026-02-23", "2026-03-23", "2026-03-30"]


def test_how_often_in_words():
  start = "2026-11-20"
  assert admin_tasks.describe(rule("weekly", weekdays=[6, 2])) == "Every week on Wednesday and Sunday"
  assert admin_tasks.describe(rule("weekly", start=start, every=2, weekdays=[4])) == "Every two weeks on Friday, from November 20, 2026"
  assert admin_tasks.describe(rule("monthly_day", day=30)) == "Every month on the 30th (the last day in shorter months)"
  assert admin_tasks.describe(rule("monthly_day", start="2027-01-01", every=3, day=1)) == "Every three months on the 1st, from January 2027"
  assert admin_tasks.describe(rule("monthly_weekday", weekdays=[6], weeks=[1])) == "Every month on the first Sunday"
  assert admin_tasks.describe(rule("monthly_weekday", weekdays=[6], weeks=[3, 1])) == "Every month on the first and third Sunday"
  assert admin_tasks.describe(rule("monthly_weekday", start="2026-11-01", every=12, weekdays=[3], weeks=[5])) == "Every year in November on the last Thursday"


def test_a_task_is_kept_with_its_formatted_fields():
  task = admin_tasks.create_task(task_details(), OWNER, "Paul")
  assert task["description_html"] == "<p>Chairs and <em>coffee</em>.</p>"
  assert task["first_notification_text"] == "Tomorrow: set up the room."
  assert task["second_notification_html"] == "" and task["second_notification_text"] == ""
  assert task["how_often"] == "Every week on Thursday"
  assert task["owner_uid"] == OWNER


def test_communion_on_the_first_sunday_and_only_the_repeats_fields_kept():
  communion = admin_tasks.create_task(
    task_details(name="Communion", repeat="monthly_weekday", weekdays=["6"], weeks_of_month=["1"], first_date="2026-11-19", day_of_month=4),
    OWNER, "Paul",
  )
  assert communion["how_often"] == "Every month on the first Sunday" and communion["next_date"] == "2026-12-06"
  assert communion["day_of_month"] is None and communion["weekdays"] == [6] and communion["weeks_of_month"] == [1]
  changed = admin_tasks.update_task(communion["id"], task_details(repeat="monthly_day", day_of_month="30", interval_count=6, first_date="2026-12-01"))
  assert changed["weekdays"] == [] and changed["weeks_of_month"] == [] and changed["day_of_month"] == 30
  assert changed["how_often"] == "Every six months on the 30th (the last day in shorter months), from December 2026"
  # Older input still taken: every two weeks on the first date's weekday, monthly on a day.
  older = admin_tasks.create_task(task_details(repeat="biweekly", weekday=3, first_date="2026-11-20"), OWNER, "Paul")
  assert older["how_often"] == "Every two weeks on Friday, from November 20, 2026" and older["interval_count"] == 2


def test_a_task_is_refused_without_what_it_needs():
  with pytest.raises(TaskProblem, match="name is needed"):
    admin_tasks.create_task(task_details(name=""), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="how often"):
    admin_tasks.create_task(task_details(repeat="daily"), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="day of the week"):
    admin_tasks.create_task(task_details(weekday=7), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="starts from"):
    admin_tasks.create_task(task_details(first_date="not a date"), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="day of the month"):
    admin_tasks.create_task(task_details(repeat="monthly_day", day_of_month=0), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="1 to 8 weeks"):
    admin_tasks.create_task(task_details(interval_count=9), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="once a year"):
    admin_tasks.create_task(task_details(repeat="monthly_day", day_of_month=1, interval_count=5), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="first, second, third, fourth or last"):
    admin_tasks.create_task(task_details(repeat="monthly_weekday", weekdays=[6], weeks_of_month=[]), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="day of the week"):
    admin_tasks.create_task(task_details(repeat="monthly_weekday", weekday=None, weekdays=[], weeks_of_month=[1]), OWNER, "Paul")


def test_tasks_are_listed_per_owner_and_deleted():
  mine = admin_tasks.create_task(task_details(name="Mine"), OWNER, "Paul")
  admin_tasks.create_task(task_details(name="Theirs"), OTHER_OWNER, "Ruth")
  assert [task["name"] for task in admin_tasks.list_tasks(OWNER)] == ["Mine"]
  assert len(admin_tasks.list_tasks()) == 2
  admin_tasks.delete_task(mine["id"])
  with pytest.raises(TaskProblem, match="not found"):
    admin_tasks.get_task(mine["id"])


def test_the_tasks_tool():
  status, answer = run_tool("manage_tasks.py", ["create", f"--owner={OWNER}"], {**task_details(), "owner_name": "Paul"})
  assert status == 0 and answer["task"]["name"] == "Set up the room"
  task_id = answer["task"]["id"]
  status, answer = run_tool("manage_tasks.py", ["get", f"--id={task_id}"])
  assert status == 0 and answer["task"]["weekday"] == 3
  status, answer = run_tool("manage_tasks.py", ["update", f"--id={task_id}"], task_details(repeat="daily"))
  assert status == 1 and "how often" in answer["error"]
  status, answer = run_tool("manage_tasks.py", ["delete", f"--id={task_id}"])
  assert status == 0


# --- scheduled tasks ---------------------------------------------------------------------------------------


@pytest.fixture
def site_users():
  """Two made-up site accounts (one closed), deleted afterwards."""
  with connect() as connection:
    open_id = connection.execute(
      "INSERT INTO users (email, password_hash, first_name, last_name, email_verified_at) VALUES ('scheduled-ruth@example.org', 'x', 'Ruth', 'Test', now()) RETURNING id"
    ).fetchone()[0]
    closed_id = connection.execute(
      "INSERT INTO users (email, password_hash, disabled_at) VALUES ('scheduled-closed@example.org', 'x', now()) RETURNING id"
    ).fetchone()[0]
  yield open_id, closed_id
  with connect() as connection:
    connection.execute("DELETE FROM users WHERE id IN (%s, %s)", (open_id, closed_id))


SUNDAY_TASK = task_details(name="Greeter", weekday=6)
THURSDAY = date(2026, 11, 19)


def test_the_options_are_the_dates_of_the_next_two_months_and_the_open_accounts(site_users):
  open_id, closed_id = site_users
  task = admin_tasks.create_task(SUNDAY_TASK, OWNER, "Paul")
  offered = scheduled_tasks.options(task["id"], THURSDAY)
  # Every Sunday to two months on (2026-11-28: Dec 27, five weeks out, was not offered when it was the next four).
  assert [day["value"] for day in offered["dates"]] == [
    "2026-11-22", "2026-11-29", "2026-12-06", "2026-12-13", "2026-12-20", "2026-12-27", "2027-01-03", "2027-01-10", "2027-01-17",
  ]
  assert offered["dates"][0]["label"] == "Sunday, November 22, 2026"
  user_ids = [user["id"] for user in offered["users"]]
  assert open_id in user_ids and closed_id not in user_ids
  assert {"id": open_id, "label": "Ruth Test (scheduled-ruth@example.org)"} in offered["users"]
  every_two_weeks = admin_tasks.create_task(task_details(interval_count=2, first_date="2026-11-05"), OWNER, "Paul")
  assert [day["value"] for day in scheduled_tasks.options(every_two_weeks["id"], THURSDAY)["dates"]] == ["2026-11-19", "2026-12-03", "2026-12-17", "2026-12-31", "2027-01-14"]
  # A monthly task still offers at least its next four dates, though they run past two months.
  monthly = admin_tasks.create_task(task_details(repeat="monthly_day", day_of_month=31, first_date="2026-11-01"), OWNER, "Paul")
  assert [day["value"] for day in scheduled_tasks.options(monthly["id"], date(2027, 1, 1))["dates"]] == ["2027-01-31", "2027-02-28", "2027-03-31", "2027-04-30"]


def test_a_task_is_scheduled_changed_and_removed(site_users):
  open_id, _ = site_users
  task = admin_tasks.create_task(SUNDAY_TASK, OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(task["id"], {"user_id": str(open_id), "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  # A new scheduled task is not confirmed (migration 073 set those that existed before to true).
  assert scheduled["confirmed"] is False
  assert scheduled_tasks.get_scheduled(scheduled["id"], THURSDAY)["confirmed"] is False
  changed = scheduled_tasks.update_scheduled(scheduled["id"], {"user_id": open_id, "on_date": "2026-11-29", "confirmed": True}, THURSDAY)
  assert changed["confirmed"] is True
  # Left out of the details, it stays; "0" unticks it.
  assert scheduled_tasks.update_scheduled(scheduled["id"], {"user_id": open_id, "on_date": "2026-11-29"}, THURSDAY)["confirmed"] is True
  assert scheduled_tasks.update_scheduled(scheduled["id"], {"user_id": open_id, "on_date": "2026-11-29", "confirmed": "0"}, THURSDAY)["confirmed"] is False
  assert scheduled["task_name"] == "Greeter" and scheduled["user_name"] == "Ruth Test"
  assert scheduled["on_date"] == "2026-11-29" and scheduled["owner_uid"] == OWNER and scheduled["created_by_name"] == "Paul"
  with pytest.raises(TaskProblem, match="already has this task"):
    scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  # A week later the 29th is still offered; three weeks later it is not, but the scheduled one may keep it.
  later = date(2026, 12, 7)
  changed = scheduled_tasks.update_scheduled(scheduled["id"], {"user_id": open_id, "on_date": "2026-11-29"}, later)
  assert changed["on_date"] == "2026-11-29" and changed["past"]
  changed = scheduled_tasks.update_scheduled(scheduled["id"], {"user_id": open_id, "on_date": "2026-12-13"}, later)
  assert changed["on_date"] == "2026-12-13" and not changed["past"]
  assert [item["id"] for item in scheduled_tasks.list_scheduled(OWNER)] == [scheduled["id"]]
  assert scheduled_tasks.list_scheduled(OTHER_OWNER) == []
  scheduled_tasks.remove_scheduled(scheduled["id"])
  assert scheduled_tasks.list_scheduled() == []


def test_a_schedule_is_refused_without_a_good_person_or_date(site_users):
  open_id, closed_id = site_users
  task = admin_tasks.create_task(SUNDAY_TASK, OWNER, "Paul")
  with pytest.raises(TaskProblem, match="site user"):
    scheduled_tasks.add_scheduled(task["id"], {"on_date": "2026-11-22"}, OWNER, "Paul", THURSDAY)
  with pytest.raises(TaskProblem, match="closed"):
    scheduled_tasks.add_scheduled(task["id"], {"user_id": closed_id, "on_date": "2026-11-22"}, OWNER, "Paul", THURSDAY)
  with pytest.raises(TaskProblem, match="next 2 months"):
    scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-23"}, OWNER, "Paul", THURSDAY)
  with pytest.raises(TaskProblem, match="next 2 months"):
    scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2027-01-24"}, OWNER, "Paul", THURSDAY)
  # Five weeks out is within two months.
  assert scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-12-27"}, OWNER, "Paul", THURSDAY)["on_date"] == "2026-12-27"


def test_deleting_the_task_or_the_account_removes_its_schedules(site_users):
  open_id, _ = site_users
  task = admin_tasks.create_task(SUNDAY_TASK, OWNER, "Paul")
  first_day = scheduled_tasks.options(task["id"])["dates"][0]["value"]
  scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": first_day}, OWNER, "Paul")
  admin_tasks.delete_task(task["id"])
  assert scheduled_tasks.list_scheduled() == []


def test_the_schedule_commands_of_the_tool(site_users):
  open_id, _ = site_users
  task = admin_tasks.create_task(SUNDAY_TASK, OWNER, "Paul")
  status, answer = run_tool("manage_tasks.py", ["schedule-options", f"--id={task['id']}"])
  assert status == 0 and len(answer["dates"]) >= 8 and answer["task"]["name"] == "Greeter"
  day = answer["dates"][1]["value"]
  status, answer = run_tool("manage_tasks.py", ["add-schedule", f"--id={task['id']}", f"--by={OWNER}"], {"user_id": open_id, "on_date": day, "created_by_name": "Paul"})
  assert status == 0 and answer["schedule"]["on_date"] == day
  schedule_id = answer["schedule"]["id"]
  status, answer = run_tool("manage_tasks.py", ["schedules", f"--owner={OWNER}"])
  assert status == 0 and [item["id"] for item in answer["schedules"]] == [schedule_id]
  status, answer = run_tool("manage_tasks.py", ["update-schedule", f"--schedule={schedule_id}"], {"user_id": open_id, "on_date": "2000-01-02"})
  assert status == 1 and "next 2 months" in answer["error"]
  status, answer = run_tool("manage_tasks.py", ["remove-schedule", f"--schedule={schedule_id}"])
  assert status == 0


# --- reminders ---------------------------------------------------------------------------------------------


def reminder_task(**changes) -> dict:
  values = {
    "name": "Greeter", "weekday": 6, "timezone": "America/Chicago", "owner_email": "leader@example.org",
    "first_notification": {"html": "<p>You are the <strong>greeter</strong> next week.</p>"}, "first_notice_days": 7,
    "second_notification": {"text": "You are the greeter tomorrow."}, "second_notice_days": 1,
  }
  values.update(changes)
  return task_details(**values)


@pytest.fixture
def mailbox(monkeypatch):
  sent = []
  monkeypatch.setattr(scheduled_tasks, "load_mail_settings", lambda: {"from_address": "site@example.test"})
  monkeypatch.setattr(scheduled_tasks, "send_email", lambda settings, email, recipients=None: sent.append(email))
  return sent


def at_utc(year, month, day, hour):
  return datetime(year, month, day, hour, tzinfo=timezone.utc)


def test_the_days_before_are_checked():
  task = admin_tasks.create_task(reminder_task(), OWNER, "Paul")
  assert (task["first_notice_days"], task["second_notice_days"], task["timezone"], task["owner_email"]) == (7, 1, "America/Chicago", "leader@example.org")
  with pytest.raises(TaskProblem, match="fewer days"):
    admin_tasks.create_task(reminder_task(second_notice_days=7), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="from 0 to 90"):
    admin_tasks.create_task(reminder_task(first_notice_days=91), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="Write the second notification"):
    admin_tasks.create_task(reminder_task(second_notification={"text": ""}), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="time zone"):
    admin_tasks.create_task(reminder_task(timezone="Mars/Olympus"), OWNER, "Paul")
  # Changed by someone else (no time zone or address given): the owner's stay.
  changed = admin_tasks.update_task(task["id"], task_details(name="Greeter", weekday=6, first_notice_days="", second_notice_days=None))
  assert changed["first_notice_days"] is None and changed["timezone"] == "America/Chicago" and changed["owner_email"] == "leader@example.org"


def test_each_reminder_goes_once_at_eight_in_the_tasks_time_zone(site_users, mailbox):
  open_id, _ = site_users
  task = admin_tasks.create_task(reminder_task(), OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  assert scheduled["first_notice_date"] == "2026-11-22" and scheduled["second_notice_date"] == "2026-11-28"
  assert scheduled_tasks.send_due(at_utc(2026, 11, 22, 13))["sent"] == 0  # 7:00 AM in Chicago
  assert scheduled_tasks.send_due(at_utc(2026, 11, 22, 14))["sent"] == 1  # 8:00 AM
  assert scheduled_tasks.send_due(at_utc(2026, 11, 22, 20))["sent"] == 0
  email = mailbox[0]
  assert email["To"] == "scheduled-ruth@example.org" and email["Reply-To"] == "leader@example.org"
  assert email["Subject"] == "Reminder: Greeter on Sunday, November 29, 2026"
  assert "<strong>greeter</strong>" in email.get_body(("html",)).get_content()
  assert "You are the greeter next week." in email.get_body(("plain",)).get_content()
  assert scheduled_tasks.send_due(at_utc(2026, 11, 28, 15))["sent"] == 1
  assert "greeter tomorrow" in mailbox[1].get_body(("plain",)).get_content()
  assert scheduled_tasks.send_due(at_utc(2026, 11, 29, 15))["sent"] == 0
  after = scheduled_tasks.get_scheduled(scheduled["id"])
  assert after["first_notice_result"] == "Sent by email." and after["second_notice_result"] == "Sent by email." and len(mailbox) == 2


def test_a_late_schedule_sends_only_the_second_reminder(site_users, mailbox):
  open_id, _ = site_users
  task = admin_tasks.create_task(reminder_task(), OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-22"}, OWNER, "Paul", THURSDAY)
  result = scheduled_tasks.send_due(at_utc(2026, 11, 21, 15))
  assert (result["sent"], result["skipped"]) == (1, 1) and len(mailbox) == 1
  assert "tomorrow" in mailbox[0].get_body(("plain",)).get_content()
  after = scheduled_tasks.get_scheduled(scheduled["id"])
  assert after["first_notice_result"].startswith("Skipped") and after["second_notice_result"] == "Sent by email."


def test_a_new_date_lets_the_reminders_go_again_and_a_passed_date_sends_none(site_users, mailbox):
  open_id, _ = site_users
  task = admin_tasks.create_task(reminder_task(), OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  scheduled_tasks.send_due(at_utc(2026, 11, 22, 15))
  assert len(mailbox) == 1
  moved = scheduled_tasks.update_scheduled(scheduled["id"], {"user_id": open_id, "on_date": "2026-12-06"}, THURSDAY)
  assert moved["first_notice_at"] is None and moved["first_notice_result"] == ""
  # The job was not running until after the new date: nothing is sent late.
  result = scheduled_tasks.send_due(at_utc(2026, 12, 7, 15))
  assert result["sent"] == 0 and result["skipped"] == 2 and len(mailbox) == 1
  assert scheduled_tasks.get_scheduled(scheduled["id"])["first_notice_result"].startswith("Skipped: the date passed")


def test_an_unconfirmed_address_is_not_emailed(site_users, mailbox):
  open_id, _ = site_users
  with connect() as connection:
    connection.execute("UPDATE users SET email_verified_at = NULL WHERE id = %s", (open_id,))
  task = admin_tasks.create_task(reminder_task(second_notice_days=None), OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  assert scheduled_tasks.send_due(at_utc(2026, 11, 22, 15))["skipped"] == 1 and mailbox == []
  assert "not confirmed" in scheduled_tasks.get_scheduled(scheduled["id"])["first_notice_result"]


def test_the_name_fields_are_filled_in_and_a_missing_name_reads_friend():
  words = "Hi [FIRST_NAME]! [full_name] / [Last_Name] [OTHER]"
  assert scheduled_tasks.fill_names(words, "Ruth", "Test") == "Hi Ruth! Ruth Test / Test [OTHER]"
  assert scheduled_tasks.fill_names(words, None, "") == "Hi friend! friend /  [OTHER]"
  assert scheduled_tasks.fill_names(words, "", "Test") == "Hi friend! Test / Test [OTHER]"
  assert scheduled_tasks.fill_names("<p>[FIRST_NAME]</p>", "<b>", None, html=True) == "<p>&lt;b&gt;</p>"


def test_a_note_and_the_name_fields_go_in_the_reminder(site_users, mailbox):
  open_id, _ = site_users
  task = admin_tasks.create_task(reminder_task(
    name="Greeter for [FIRST_NAME]", second_notice_days=None,
    first_notification={"html": "<p>Hi [FIRST_NAME], you greet next week.</p>"},
  ), OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(
    task["id"], {"user_id": open_id, "on_date": "2026-11-29", "note": {"html": "<p>Bring <em>name tags</em>, [FULL_NAME].</p>"}},
    OWNER, "Paul", THURSDAY,
  )
  assert scheduled["note_text"] == "Bring name tags, [FULL_NAME]." and "<em>name tags</em>" in scheduled["note_html"]
  # Changing only the person or date (no note given) keeps the note.
  kept = scheduled_tasks.update_scheduled(scheduled["id"], {"user_id": open_id, "on_date": "2026-11-29"}, THURSDAY)
  assert kept["note_text"] == scheduled["note_text"]
  scheduled_tasks.send_due(at_utc(2026, 11, 22, 15))
  email = mailbox[0]
  assert email["Subject"] == "Reminder: Greeter for Ruth on Sunday, November 29, 2026"
  plain = email.get_body(("plain",)).get_content()
  assert "Hi Ruth, you greet next week.\n\nBring name tags, Ruth Test." in plain
  assert "<em>name tags</em>, Ruth Test." in email.get_body(("html",)).get_content()
  # An empty note clears it.
  cleared = scheduled_tasks.update_scheduled(scheduled["id"], {"user_id": open_id, "on_date": "2026-11-29", "note": {"html": ""}}, THURSDAY)
  assert cleared["note_html"] == "" and cleared["note_text"] == ""


@pytest.fixture
def texts(monkeypatch):
  sent = []
  monkeypatch.setattr(scheduled_tasks.sms, "is_configured", lambda: True)
  monkeypatch.setattr(scheduled_tasks.sms, "send_text", lambda number, text, media_url=None: sent.append((number, text)) or True)
  return sent


def choose(user_id, by_email, by_text, verified_email=True):
  with connect() as connection:
    connection.execute(
      """UPDATE users SET phone = '+1 (555) 201-4567', phone_is_cell = true, sms_number = '+15552014567', sms_opt_in = %s,
        send_via_email = %s, send_via_sms = %s, email_verified_at = CASE WHEN %s THEN now() END WHERE id = %s""",
      (by_text, by_email, by_text, verified_email, user_id),
    )


def test_reminders_follow_the_site_users_delivery_choice(site_users, mailbox, texts):
  open_id, _ = site_users
  task = admin_tasks.create_task(reminder_task(first_notification={"text": "Hi [FIRST_NAME], you greet next week."}), OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(
    task["id"], {"user_id": open_id, "on_date": "2026-11-29", "note": {"text": "Bring name tags."}}, OWNER, "Paul", THURSDAY
  )

  choose(open_id, by_email=False, by_text=True)
  scheduled_tasks.send_due(at_utc(2026, 11, 22, 15))
  assert mailbox == [] and len(texts) == 1
  number, text = texts[0]
  assert number == "+15552014567"
  assert "Reminder: Greeter on Sunday, November 29, 2026. Hi Ruth, you greet next week. Bring name tags." in text
  assert text.endswith("Reply STOP to end texts.")
  assert scheduled_tasks.get_scheduled(scheduled["id"])["first_notice_result"] == "Sent by text."

  choose(open_id, by_email=True, by_text=True)
  scheduled_tasks.send_due(at_utc(2026, 11, 28, 15))
  assert len(mailbox) == 1 and len(texts) == 2
  assert scheduled_tasks.get_scheduled(scheduled["id"])["second_notice_result"] == "Sent by email and text."


def test_an_unconfirmed_address_still_gets_the_text(site_users, mailbox, texts):
  open_id, _ = site_users
  task = admin_tasks.create_task(reminder_task(second_notice_days=None), OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  with connect() as connection:
    connection.execute(
      """UPDATE users SET email_verified_at = NULL, phone_verified_at = now(), sms_number = '+15552014567', sms_opt_in = true,
        phone_is_cell = true, send_via_email = true, send_via_sms = true WHERE id = %s""",
      (open_id,),
    )
  scheduled_tasks.send_due(at_utc(2026, 11, 22, 15))
  assert mailbox == [] and len(texts) == 1
  assert scheduled_tasks.get_scheduled(scheduled["id"])["first_notice_result"] == "Sent by text."


def test_a_task_sends_only_one_reminder_a_day(site_users, mailbox):
  open_id, _ = site_users
  # Reminders 1 day and 0 days before; scheduled at 7:00 on the date itself (Chicago): the first is overdue, the
  # second is due at 8:00. Only the second goes.
  task = admin_tasks.create_task(reminder_task(first_notice_days=1, second_notice_days=0), OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  result = scheduled_tasks.send_due(at_utc(2026, 11, 29, 13))  # 7:00 AM in Chicago
  assert (result["sent"], result["skipped"]) == (0, 1) and mailbox == []
  assert scheduled_tasks.get_scheduled(scheduled["id"])["first_notice_result"] == "Skipped: the second reminder goes later the same day."
  assert scheduled_tasks.send_due(at_utc(2026, 11, 29, 14))["sent"] == 1  # 8:00 AM
  assert len(mailbox) == 1 and "greeter tomorrow" in mailbox[0].get_body(("plain",)).get_content()

  # A late first reminder on an earlier day still goes (the second is on another day).
  task = admin_tasks.create_task(reminder_task(name="Usher", first_notice_days=2, second_notice_days=0), OWNER, "Paul")
  other = scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  scheduled_tasks.send_due(at_utc(2026, 11, 28, 13))  # 7:00 AM the day before: the first is a day late
  assert scheduled_tasks.get_scheduled(other["id"])["first_notice_result"].startswith("Sent")


def test_a_failed_text_falls_back_to_email_for_a_texts_only_member(site_users, mailbox, monkeypatch):
  open_id, _ = site_users
  monkeypatch.setattr(scheduled_tasks.sms, "is_configured", lambda: True)
  tried = []

  def failing_text(number, text, media_url=None):
    tried.append(number)
    return False  # what send_text answers when Telnyx refuses or cannot be reached

  monkeypatch.setattr(scheduled_tasks.sms, "send_text", failing_text)
  task = admin_tasks.create_task(reminder_task(), OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  choose(open_id, by_email=False, by_text=True)
  result = scheduled_tasks.send_due(at_utc(2026, 11, 22, 15))
  assert result["sent"] == 1 and tried == ["+15552014567"] and len(mailbox) == 1
  assert scheduled_tasks.get_scheduled(scheduled["id"])["first_notice_result"] == "Sent by email (the text could not be sent)."

  # Without a confirmed address there is nothing to fall back to.
  choose(open_id, by_email=False, by_text=True, verified_email=False)
  with connect() as connection:
    connection.execute("UPDATE users SET phone_verified_at = now() WHERE id = %s", (open_id,))
  result = scheduled_tasks.send_due(at_utc(2026, 11, 28, 15))
  assert result["failed"] == 1 and len(mailbox) == 1
  assert scheduled_tasks.get_scheduled(scheduled["id"])["second_notice_result"] == "Not sent: the text."


def test_a_failed_text_never_stops_the_email_for_a_member_who_chose_both(site_users, mailbox, monkeypatch):
  open_id, _ = site_users
  monkeypatch.setattr(scheduled_tasks.sms, "is_configured", lambda: True)

  def broken_text(number, text, media_url=None):
    raise RuntimeError("Telnyx is down")

  monkeypatch.setattr(scheduled_tasks.sms, "send_text", broken_text)
  task = admin_tasks.create_task(reminder_task(second_notice_days=None), OWNER, "Paul")
  scheduled = scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  choose(open_id, by_email=True, by_text=True)
  scheduled_tasks.send_due(at_utc(2026, 11, 22, 15))
  assert len(mailbox) == 1
  assert scheduled_tasks.get_scheduled(scheduled["id"])["first_notice_result"].startswith("Sent by email; not sent: the text")


def test_a_task_signature_goes_at_the_foot_of_its_reminder_emails_only(site_users, mailbox, monkeypatch):
  open_id, _ = site_users
  mine = signatures.create_signature({"name": "Pastor", "signature": {"html": "<p><strong>Pastor Paul</strong><br>Grace Church</p>"}}, OWNER, "Paul")
  theirs = signatures.create_signature({"name": "Theirs", "signature": {"text": "Someone else"}}, OTHER_OWNER, "Ann")
  with pytest.raises(TaskProblem, match="not one of the task owner's"):
    admin_tasks.create_task(reminder_task(signature_id=theirs["id"]), OWNER, "Paul")
  task = admin_tasks.create_task(reminder_task(signature_id=str(mine["id"])), OWNER, "Paul")
  assert task["signature_id"] == mine["id"]
  # Changing the task without a signature_id keeps it.
  assert admin_tasks.update_task(task["id"], reminder_task())["signature_id"] == mine["id"]

  monkeypatch.setattr(scheduled_tasks.sms, "is_configured", lambda: True)
  texts = []
  monkeypatch.setattr(scheduled_tasks.sms, "send_text", lambda number, text, media_url=None: texts.append(text) or True)
  choose(open_id, by_email=True, by_text=True)
  scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  scheduled_tasks.send_due(at_utc(2026, 11, 22, 15))
  plain = mailbox[0].get_body(("plain",)).get_content()
  html = mailbox[0].get_body(("html",)).get_content()
  assert "You are the greeter next week.\n\nPastor Paul\nGrace Church\n\n--\n" in plain
  assert "<strong>Pastor Paul</strong>" in html and html.index("Pastor Paul") < html.index("<hr>")
  assert "Pastor Paul" not in texts[0]

  # No signature chosen: none; a deleted signature leaves the task with none.
  cleared = admin_tasks.update_task(task["id"], reminder_task(signature_id=""))
  assert cleared["signature_id"] is None
  admin_tasks.update_task(task["id"], reminder_task(signature_id=mine["id"]))
  signatures.delete_signature(mine["id"])
  assert admin_tasks.get_task(task["id"])["signature_id"] is None


def test_schedule_tasks_offers_the_tasks_of_a_date_and_schedules_several_at_once(site_users):
  open_id, closed_id = site_users
  greeter = admin_tasks.create_task(SUNDAY_TASK, OWNER, "Paul")
  coffee = admin_tasks.create_task(task_details(name="Coffee", weekday=6), OWNER, "Paul")
  admin_tasks.create_task(task_details(name="Thursday study", weekday=3), OWNER, "Paul")
  someone_elses = admin_tasks.create_task(task_details(name="Theirs", weekday=6), OTHER_OWNER, "Ann")

  offered = scheduled_tasks.day_options(date(2026, 11, 29), OWNER, THURSDAY)
  assert [task["name"] for task in offered["tasks"]] == ["Coffee", "Greeter"]  # not Thursday's, not another owner's
  assert offered["label"] == "Sunday, November 29, 2026" and open_id in [user["id"] for user in offered["users"]]
  assert [task["name"] for task in scheduled_tasks.day_options(date(2026, 12, 27), OWNER, THURSDAY)["tasks"]] == ["Coffee", "Greeter"]
  assert scheduled_tasks.day_options(date(2027, 3, 7), OWNER, THURSDAY)["tasks"] == []  # beyond two months

  added = scheduled_tasks.add_many({"on_date": "2026-11-29", "items": [
    {"task_id": greeter["id"], "user_id": open_id, "note": {"text": "cookies"}},
    {"task_id": coffee["id"], "user_id": str(open_id)},
  ]}, OWNER, "Paul", OWNER, THURSDAY)
  assert [(item["task_name"], item["note_text"]) for item in added] == [("Greeter", "cookies"), ("Coffee", "")]
  assert scheduled_tasks.day_options(date(2026, 11, 29), OWNER, THURSDAY)["tasks"][1]["scheduled_for"] == ["Ruth Test (scheduled-ruth@example.org)"]

  # All or none: one bad row saves nothing, and the message names its task.
  before = len(scheduled_tasks.list_scheduled(OWNER))
  with pytest.raises(TaskProblem, match="Coffee: That site user was not found"):
    scheduled_tasks.add_many({"on_date": "2026-12-06", "items": [
      {"task_id": greeter["id"], "user_id": open_id}, {"task_id": coffee["id"], "user_id": closed_id},
    ]}, OWNER, "Paul", OWNER, THURSDAY)
  with pytest.raises(TaskProblem, match="already has this task"):
    scheduled_tasks.add_many({"on_date": "2026-11-29", "items": [{"task_id": greeter["id"], "user_id": open_id}]}, OWNER, "Paul", OWNER, THURSDAY)
  with pytest.raises(TaskProblem, match="not one of your tasks"):
    scheduled_tasks.add_many({"on_date": "2026-11-29", "items": [{"task_id": someone_elses["id"], "user_id": open_id}]}, OWNER, "Paul", OWNER, THURSDAY)
  with pytest.raises(TaskProblem, match="Choose at least one task"):
    scheduled_tasks.add_many({"on_date": "2026-11-29", "items": []}, OWNER, "Paul", OWNER, THURSDAY)
  assert len(scheduled_tasks.list_scheduled(OWNER)) == before


def test_an_administrator_can_move_a_signature_or_a_task_to_another_owner():
  signature = signatures.create_signature({"name": "Clipboard", "signature": {"text": "Paul"}}, OTHER_OWNER, "admin")
  task = admin_tasks.create_task(reminder_task(signature_id=signature["id"]), OTHER_OWNER, "admin")
  # Moving the task alone: the old owner's signature is not the new owner's, so it is dropped (not refused).
  moved = admin_tasks.update_task(task["id"], reminder_task(
    new_owner_uid=OWNER, new_owner_name="Paul Carrick", owner_email="paul@example.org", timezone="America/Los_Angeles",
  ))
  assert (moved["owner_uid"], moved["owner_name"], moved["owner_email"], moved["timezone"], moved["signature_id"]) == (
    OWNER, "Paul Carrick", "paul@example.org", "America/Los_Angeles", None,
  )
  # Moving the signature too, then choosing it on the task, works.
  moved_signature = signatures.update_signature(signature["id"], {"name": "Clipboard", "signature": {"text": "Paul"}, "new_owner_uid": OWNER, "new_owner_name": "Paul Carrick"})
  assert (moved_signature["owner_uid"], moved_signature["owner_name"]) == (OWNER, "Paul Carrick")
  assert admin_tasks.update_task(task["id"], reminder_task(signature_id=signature["id"]))["signature_id"] == signature["id"]
  # Without new_owner_uid the owner stays, and another's signature is still refused.
  other = signatures.create_signature({"name": "Theirs", "signature": {"text": "Ann"}}, OTHER_OWNER, "Ann")
  with pytest.raises(TaskProblem, match="not one of the task owner's"):
    admin_tasks.update_task(task["id"], reminder_task(signature_id=other["id"]))
  # Moving a signature away drops it from its old owner's tasks.
  signatures.update_signature(signature["id"], {"name": "Clipboard", "signature": {"text": "Paul"}, "new_owner_uid": OTHER_OWNER, "new_owner_name": "Ann"})
  assert admin_tasks.get_task(task["id"])["signature_id"] is None


def test_a_message_to_the_people_of_a_day(site_users, monkeypatch):
  import day_messages

  open_id, _ = site_users
  with connect() as connection:
    other_id = connection.execute(
      "INSERT INTO users (email, password_hash, first_name, last_name, email_verified_at) VALUES ('scheduled-ann@example.org', 'x', 'Ann', 'Test', now()) RETURNING id"
    ).fetchone()[0]
  try:
    sent = []
    monkeypatch.setattr(day_messages, "load_mail_settings", lambda: {"from_address": "site@example.test"})
    monkeypatch.setattr(day_messages, "send_email", lambda settings, email, recipients=None: sent.append(email))
    monkeypatch.setattr(day_messages, "PAUSE_SECONDS", 0)
    greeter = admin_tasks.create_task(SUNDAY_TASK, OWNER, "Paul")
    coffee = admin_tasks.create_task(task_details(name="Coffee", weekday=6), OWNER, "Paul")
    for task, user in ((greeter, open_id), (coffee, open_id), (coffee, other_id)):
      scheduled_tasks.add_scheduled(task["id"], {"user_id": user, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)

    assert [(day["value"], day["people"]) for day in day_messages.dates(OWNER, THURSDAY)] == [("2026-11-29", 2)]
    people = day_messages.people(date(2026, 11, 29), OWNER)
    assert [(person["label"].split(" (")[0], person["tasks"]) for person in people] == [("Ann Test", ["Coffee"]), ("Ruth Test", ["Coffee", "Greeter"])]
    signature = signatures.create_signature({"name": "Paul", "signature": {"text": "Paul, deacon"}}, OWNER, "Paul")

    result = day_messages.send({
      "on_date": "2026-11-29", "user_ids": [open_id], "subject": "Sunday, [FIRST_NAME]",
      "message": {"html": "<p>Hi [FIRST_NAME], see you <strong>Sunday</strong>.</p>"}, "signature_id": signature["id"],
      "sender_name": "Paul Carrick", "sender_email": "leader@example.org",
    }, OWNER, OWNER)
    assert result["sent"] == [{"label": "Ruth Test (scheduled-ruth@example.org)", "how": "email"}] and len(sent) == 1
    email = sent[0]
    assert email["To"] == "scheduled-ruth@example.org" and email["Reply-To"] == "leader@example.org" and email["Subject"] == "Sunday, Ruth"
    plain = email.get_body(("plain",)).get_content()
    assert "Hi Ruth, see you Sunday.\n\nPaul, deacon\n\n--\nSent by Paul Carrick to the people scheduled on Sunday, November 29, 2026" in plain
    assert "<strong>Sunday</strong>" in email.get_body(("html",)).get_content()

    with pytest.raises(TaskProblem, match="not scheduled on that date"):
      day_messages.send({"on_date": "2026-11-29", "user_ids": [999999999], "subject": "x", "message": {"text": "x"}}, OWNER, OWNER)
    with pytest.raises(TaskProblem, match="Tick at least one person"):
      day_messages.send({"on_date": "2026-11-29", "user_ids": [], "subject": "x", "message": {"text": "x"}}, OWNER, OWNER)
    with pytest.raises(TaskProblem, match="not one of yours"):
      day_messages.send({"on_date": "2026-11-29", "user_ids": [open_id], "subject": "x", "message": {"text": "x"}, "signature_id": signature["id"]}, OTHER_OWNER, None)
    # Another owner sees none of these dates or people.
    assert day_messages.dates(OTHER_OWNER, THURSDAY) == [] and day_messages.people(date(2026, 11, 29), OTHER_OWNER) == []
  finally:
    with connect() as connection:
      connection.execute("DELETE FROM users WHERE id = %s", (other_id,))


def test_files_attached_to_a_message_of_a_day(site_users, monkeypatch, tmp_path):
  import io
  import time
  import zipfile

  from fastapi.testclient import TestClient
  from PIL import Image

  import day_messages
  import message_files
  from main import app

  open_id, _ = site_users
  sent, texts = [], []
  monkeypatch.setattr(day_messages, "load_mail_settings", lambda: {"from_address": "site@example.test"})
  monkeypatch.setattr(day_messages, "send_email", lambda settings, email, recipients=None: sent.append(email))
  monkeypatch.setattr(day_messages, "PAUSE_SECONDS", 0)
  monkeypatch.setattr(day_messages.sms, "is_configured", lambda: True)
  monkeypatch.setattr(day_messages.sms, "send_text", lambda number, text, media_url=None: texts.append((text, media_url)) or True)
  choose(open_id, by_email=True, by_text=True)
  task = admin_tasks.create_task(SUNDAY_TASK, OWNER, "Paul")
  scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)

  pdf = tmp_path / "upload1"
  pdf.write_bytes(b"%PDF-1.4\n% a tiny test file\n")
  picture = tmp_path / "upload2"
  buffer = io.BytesIO()
  Image.new("RGB", (3000, 2000), (20, 120, 200)).save(buffer, "PNG")
  picture.write_bytes(buffer.getvalue())
  details = {"on_date": "2026-11-29", "user_ids": [open_id], "subject": "Sunday", "message": {"text": "See the sheet."}}
  result = day_messages.send(details, OWNER, OWNER, [(str(pdf), "Sign-up sheet.pdf"), (str(picture), "room.png")])
  assert result["sent"][0]["how"] == "email and text"
  names = [part.get_filename() for part in sent[0].iter_attachments()]
  assert names == ["Sign-up sheet.pdf", "room.png"]
  text, media_url = texts[0]
  key = media_url.split("/message-file/")[1].split("/")[0]
  assert media_url.endswith("/picture.jpg")
  assert "Sunday: See the sheet." in text and f"/api/message-file/{key}" in text

  client = TestClient(app)
  picture_answer = client.get(f"/message-file/{key}/picture.jpg")
  assert picture_answer.status_code == 200 and max(Image.open(io.BytesIO(picture_answer.content)).size) == message_files.PICTURE_SIZE
  download = client.get(f"/message-file/{key}")
  assert download.headers["content-type"] == "application/zip" and "attachments.zip" in download.headers["content-disposition"]
  assert sorted(zipfile.ZipFile(io.BytesIO(download.content)).namelist()) == ["Sign-up sheet.pdf", "room.png"]
  assert client.get("/message-file/not-a-key").status_code == 404

  # Refused: a file that is not what its name says, and too many files.
  fake = tmp_path / "upload3"
  fake.write_bytes(b"MZ not a pdf")
  with pytest.raises(TaskProblem, match="not really a PDF"):
    day_messages.send(details, OWNER, OWNER, [(str(fake), "notes.pdf")])
  with pytest.raises(TaskProblem, match="cannot be attached"):
    day_messages.send(details, OWNER, OWNER, [(str(fake), "program.exe")])
  with pytest.raises(TaskProblem, match="at most 5 files"):
    day_messages.send(details, OWNER, OWNER, [(str(pdf), f"{number}.pdf") for number in range(6)])
  # After 30 days they go.
  assert message_files.remove_old(time.time() + 31 * 86400) >= 1 and client.get(f"/message-file/{key}").status_code == 404


def test_the_sent_by_line_can_be_left_out_of_task_reminders_and_day_messages(site_users, mailbox, monkeypatch):
  import day_messages

  open_id, _ = site_users
  task = admin_tasks.create_task(reminder_task(second_notice_days=None, show_sent_by=False), OWNER, "Paul")
  assert task["show_sent_by"] is False
  assert admin_tasks.update_task(task["id"], reminder_task(second_notice_days=None))["show_sent_by"] is False  # kept when not given
  scheduled_tasks.add_scheduled(task["id"], {"user_id": open_id, "on_date": "2026-11-29"}, OWNER, "Paul", THURSDAY)
  scheduled_tasks.send_due(at_utc(2026, 11, 22, 15))
  plain = mailbox[0].get_body(("plain",)).get_content()
  assert "You are the greeter next week." in plain and "A reminder of" not in plain and "--" not in plain

  sent = []
  monkeypatch.setattr(day_messages, "load_mail_settings", lambda: {"from_address": "site@example.test"})
  monkeypatch.setattr(day_messages, "send_email", lambda settings, email, recipients=None: sent.append(email))
  details = {"on_date": "2026-11-29", "user_ids": [open_id], "subject": "Sunday", "message": {"text": "See you."}}
  day_messages.send({**details, "show_sent_by": False}, OWNER, OWNER)
  day_messages.send(details, OWNER, OWNER)
  assert "Sent by" not in sent[0].get_body(("plain",)).get_content()
  assert "Sent by" in sent[1].get_body(("plain",)).get_content()


def test_a_member_sees_their_own_scheduled_tasks(site_users, monkeypatch):
  """My scheduled tasks on the site (scheduled_tasks.member_tasks, GET /scheduled-tasks/mine) and the account's
  in_a_group, which shows it in the menu (a member of at least one group, whether or not they have tasks)."""
  import accounts
  import main
  from fastapi.testclient import TestClient

  open_id, closed_id = site_users

  def flag(user_id):
    with connect() as connection:
      row = connection.execute(f"SELECT {accounts._USER_COLUMNS} FROM users WHERE id = %s", (user_id,)).fetchone()
    return accounts._describe_user(row)["in_a_group"]

  assert flag(open_id) is False
  today = date.today()
  task = admin_tasks.create_task(
    {**SUNDAY_TASK, "name": "Greeter for [FIRST_NAME]", "description": {"html": "<p>Welcome people, [FULL_NAME].</p>"}},
    OWNER, "Paul",
  )
  with connect() as connection:
    for days, note, confirmed in ((7, "<p>Bring the bulletins</p>", True), (-3, "", False), (-90, "", False)):
      connection.execute(
        "INSERT INTO admin_scheduled_tasks (task_id, user_id, on_date, created_by_uid, note_html, confirmed) VALUES (%s, %s, %s, %s, %s, %s)",
        (task["id"], open_id, today + timedelta(days=days), OWNER, note, confirmed),
      )
  # Scheduled tasks alone do not show the menu entry; being in a group does.
  assert flag(open_id) is False
  with connect() as connection:
    group_id = connection.execute(
      "INSERT INTO member_groups (name, owner_uid, owner_name) VALUES ('Tasks check group', %s, 'Paul') RETURNING id", (OWNER,)
    ).fetchone()[0]
    connection.execute(
      "INSERT INTO group_members (group_id, user_id, stop_token) VALUES (%s, %s, 'tasks-check-token')", (group_id, open_id)
    )
  try:
    assert flag(open_id) is True and flag(closed_id) is False
  finally:
    with connect() as connection:
      connection.execute("DELETE FROM member_groups WHERE id = %s", (group_id,))

  mine = scheduled_tasks.member_tasks(open_id, today)
  assert [each["on_date"] for each in mine["upcoming"]] == [(today + timedelta(days=7)).isoformat()]
  assert [each["on_date"] for each in mine["past"]] == [(today - timedelta(days=3)).isoformat()]
  upcoming = mine["upcoming"][0]
  assert upcoming["task_name"] == "Greeter for Ruth" and upcoming["confirmed"] is True and upcoming["owner_name"] == "Paul"
  assert "Welcome people, Ruth Test." in upcoming["description_html"] and "Bring the bulletins" in upcoming["note_html"]
  assert mine["past"][0]["confirmed"] is False
  assert scheduled_tasks.member_tasks(closed_id, today) == {"upcoming": [], "past": []}

  client = TestClient(main.app)
  assert client.get("/scheduled-tasks/mine").status_code == 401
  monkeypatch.setattr(main, "user_for_token", lambda token: {"id": open_id})
  answer = client.get("/scheduled-tasks/mine", cookies={"session": "x"}).json()
  assert len(answer["upcoming"]) == 1 and len(answer["past"]) == 1

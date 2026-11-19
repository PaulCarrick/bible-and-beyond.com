"""Tests for the signatures (signatures.py) and tasks (admin_tasks.py) of the Drupal admin. They use the real
tables: their rows are set aside before each test and put back afterwards."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

import admin_tasks
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
    for table in ("admin_signatures", "admin_tasks"):
      cursor = connection.execute(f"SELECT * FROM {table}")
      saved[table] = ([column.name for column in cursor.description], cursor.fetchall())
      connection.execute(f"DELETE FROM {table}")
  yield
  with connect() as connection:
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
    "first_notification": {"html": "<p>Tomorrow: set up the room.</p>"},
    "second_notification": {"text": ""},
  }
  details.update(changes)
  return details


def test_the_next_date_of_each_repeat():
  thursday = date(2026, 11, 19)
  assert next_date({"repeat": "weekly", "weekday": 3}, thursday) == thursday
  assert next_date({"repeat": "weekly", "weekday": 0}, thursday) == date(2026, 11, 23)
  first = date(2026, 11, 5)
  assert next_date({"repeat": "biweekly", "first_date": first}, date(2026, 11, 1)) == first
  assert next_date({"repeat": "biweekly", "first_date": first}, thursday) == thursday
  assert next_date({"repeat": "biweekly", "first_date": first}, date(2026, 11, 20)) == date(2026, 12, 3)
  assert next_date({"repeat": "monthly", "day_of_month": 25}, thursday) == date(2026, 11, 25)
  assert next_date({"repeat": "monthly", "day_of_month": 10}, thursday) == date(2026, 12, 10)
  assert next_date({"repeat": "monthly", "day_of_month": 31}, date(2027, 2, 1)) == date(2027, 2, 28)


def test_a_task_is_kept_with_its_formatted_fields():
  task = admin_tasks.create_task(task_details(), OWNER, "Paul")
  assert task["description_html"] == "<p>Chairs and <em>coffee</em>.</p>"
  assert task["first_notification_text"] == "Tomorrow: set up the room."
  assert task["second_notification_html"] == "" and task["second_notification_text"] == ""
  assert task["how_often"] == "Every week on Thursday"
  assert task["owner_uid"] == OWNER


def test_only_the_field_of_the_repeat_is_kept():
  task = admin_tasks.create_task(task_details(repeat="biweekly", weekday=3, first_date="2026-11-20", day_of_month=4), OWNER, "Paul")
  assert task["weekday"] is None and task["day_of_month"] is None and task["first_date"] == "2026-11-20"
  assert task["how_often"] == "Every two weeks on Friday, from November 20, 2026"
  changed = admin_tasks.update_task(task["id"], task_details(repeat="monthly", day_of_month="30"))
  assert changed["first_date"] is None and changed["day_of_month"] == 30
  assert changed["how_often"] == "Every month on the 30th (the last day in shorter months)"


def test_a_task_is_refused_without_what_it_needs():
  with pytest.raises(TaskProblem, match="name is needed"):
    admin_tasks.create_task(task_details(name=""), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="how often"):
    admin_tasks.create_task(task_details(repeat="daily"), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="day of the week"):
    admin_tasks.create_task(task_details(weekday=7), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="first date"):
    admin_tasks.create_task(task_details(repeat="biweekly", first_date="not a date"), OWNER, "Paul")
  with pytest.raises(TaskProblem, match="day of the month"):
    admin_tasks.create_task(task_details(repeat="monthly", day_of_month=0), OWNER, "Paul")


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

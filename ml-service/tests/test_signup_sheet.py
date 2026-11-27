"""Tests for the sign-up sheet PDF (signup_sheet.py) and the tasks' expected occurrences and sheet order
(admin_tasks.py, migration 074). Real database; their own @sign-up-sheet-test.example accounts, a group and tasks
owned by LEADER, all removed after."""

import base64
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

import admin_tasks
import signup_sheet
from search import connect

LEADER = 990501
DOMAIN = "sign-up-sheet-test.example"
TOOL = Path(__file__).resolve().parent.parent / "scripts" / "manage_tasks.py"
SUNDAY = {"description": {"text": "x"}, "repeat": "weekly", "weekdays": [6], "interval_count": 1, "first_date": "2026-11-01"}


@pytest.fixture
def setup():
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM admin_tasks WHERE owner_uid = %s", (LEADER,))
      connection.execute("DELETE FROM member_groups WHERE owner_uid = %s", (LEADER,))
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  coffee = admin_tasks.create_task({**SUNDAY, "name": "Coffee", "sheet_order": 3}, LEADER, "Pastor Dan")
  baked = admin_tasks.create_task({**SUNDAY, "name": "Baked Goods", "expected_occurrences": 2, "sheet_order": 1}, LEADER, "Pastor Dan")
  cleanup = admin_tasks.create_task({**SUNDAY, "name": "CleanUp", "sheet_order": 9}, LEADER, "Pastor Dan")
  with connect() as connection:
    group = connection.execute(
      "INSERT INTO member_groups (name, owner_uid, owner_name) VALUES ('Fellowship', %s, 'Pastor Dan') RETURNING id", (LEADER,)
    ).fetchone()[0]
    people = []
    for first in ("Ruth", "Daniel", "Grace"):
      people.append(connection.execute(
        f"INSERT INTO users (email, password_hash, first_name, last_name, phone) VALUES ('{first.lower()}@{DOMAIN}', 'x', %s, 'Sample', '+1 (555) 201-0000') RETURNING id",
        (first,),
      ).fetchone()[0])
    for task, person, day, confirmed, note in (
      (baked, people[0], "2026-12-06", True, "cookies"), (coffee, people[1], "2026-12-06", True, ""),
      (coffee, people[2], "2026-12-06", False, "decaf"), (cleanup, people[2], "2026-12-13", True, ""),
    ):
      connection.execute(
        "INSERT INTO admin_scheduled_tasks (task_id, user_id, on_date, created_by_uid, confirmed, note_text) VALUES (%s, %s, %s, %s, %s, %s)",
        (task["id"], person, day, LEADER, confirmed, note),
      )
  yield {"group": group, "baked": baked, "coffee": coffee}
  clear()


def test_tasks_keep_their_expected_occurrences_and_sheet_order(setup):
  baked = admin_tasks.get_task(setup["baked"]["id"])
  assert baked["expected_occurrences"] == 2 and baked["sheet_order"] == 1
  assert admin_tasks.get_task(setup["coffee"]["id"])["expected_occurrences"] == 1
  # A change without them keeps them; with them, sets them; out of range is refused.
  assert admin_tasks.update_task(baked["id"], {**SUNDAY, "name": "Baked Goods"})["expected_occurrences"] == 2
  assert admin_tasks.update_task(baked["id"], {**SUNDAY, "name": "Baked Goods", "expected_occurrences": "3"})["expected_occurrences"] == 3
  with pytest.raises(admin_tasks.TaskProblem, match="Expected occurrences"):
    admin_tasks.update_task(baked["id"], {**SUNDAY, "name": "Baked Goods", "expected_occurrences": 0})
  with pytest.raises(admin_tasks.TaskProblem, match="order"):
    admin_tasks.update_task(baked["id"], {**SUNDAY, "name": "Baked Goods", "sheet_order": 1000})


def test_a_blank_sheet_has_the_expected_rows_in_order(setup):
  with connect() as connection:
    tasks = signup_sheet._tasks(connection, LEADER)
  dates = signup_sheet.sheet_dates(tasks, date(2026, 12, 1), date(2026, 12, 14), None)
  assert [day for day, _ in dates] == [date(2026, 12, 6), date(2026, 12, 13)]
  assert [row["task"] for row in dates[0][1]] == ["Baked Goods 1", "Baked Goods 2", "Coffee", "CleanUp"]
  assert all(set(row) == {"task"} for row in dates[0][1])


def test_a_filled_sheet_has_the_people_and_blank_rows_up_to_the_number(setup):
  with connect() as connection:
    tasks = signup_sheet._tasks(connection, LEADER)
    people = signup_sheet._people(connection, [task["id"] for task in tasks], date(2026, 12, 1), date(2026, 12, 14))
  first = signup_sheet.sheet_dates(tasks, date(2026, 12, 1), date(2026, 12, 14), people)[0][1]
  assert [(row["task"], row.get("name")) for row in first] == [
    ("Baked Goods 1", "Ruth Sample"), ("Baked Goods 2", None),
    # Two people on a task that expects one: both get a row, numbered, the confirmed one first.
    ("Coffee 1", "Daniel Sample"), ("Coffee 2", "Grace Sample"), ("CleanUp", None),
  ]
  assert first[0]["notes"] == "cookies" and first[0]["email"] == f"ruth@{DOMAIN}" and first[3]["confirmed"] is False


def test_the_pdf_is_made_and_the_title_and_notes_are_kept(setup):
  made = signup_sheet.make({"group_id": setup["group"], "start": "2026-12-01", "end": "2026-12-31", "filled": True,
                            "title": "After Church Fellowship Time", "notes": {"html": "<p><strong>Thank you!</strong> Bring food by 9:45.</p><ul><li>One</li></ul>"}})
  pdf = base64.b64decode(made["pdf"])
  assert pdf.startswith(b"%PDF") and made["dates"] == 4
  assert made["file_name"] == "After Church Fellowship Time 2026-12-01 to 2026-12-31.pdf"
  kept = [group for group in signup_sheet.groups(LEADER) if group["id"] == setup["group"]][0]
  assert kept["sheet_title"] == "After Church Fellowship Time" and "<strong>Thank you!</strong>" in kept["sheet_notes_html"]
  blank = signup_sheet.make({"group_id": setup["group"], "start": "2026-12-01", "end": "2026-12-31", "filled": False, "title": "Sheet", "notes": {"html": ""}})
  assert blank["file_name"].endswith("(blank).pdf")
  assert signup_sheet.notes_paragraphs("") == [] and len(signup_sheet.notes_paragraphs("<p>a</p><p>b</p>")) == 2


def test_a_long_filled_sheet_runs_onto_more_pages(setup):
  from pypdf import PdfReader
  from io import BytesIO

  admin_tasks.update_task(setup["coffee"]["id"], {**SUNDAY, "name": "Coffee", "expected_occurrences": 20})
  made = signup_sheet.make({"group_id": setup["group"], "start": "2026-12-01", "end": "2027-01-31", "filled": True, "title": "Long", "notes": {"html": ""}})
  assert len(PdfReader(BytesIO(base64.b64decode(made["pdf"]))).pages) >= 5


def test_refusals_and_the_tool(setup):
  with pytest.raises(signup_sheet.SheetProblem, match="not found"):
    signup_sheet.make({"group_id": setup["group"], "start": "2026-12-01", "end": "2026-12-31"}, owner_uid=LEADER + 1)
  with pytest.raises(signup_sheet.SheetProblem, match="before"):
    signup_sheet.make({"group_id": setup["group"], "start": "2026-12-31", "end": "2026-12-01"})
  with pytest.raises(signup_sheet.SheetProblem, match="a year"):
    signup_sheet.make({"group_id": setup["group"], "start": "2026-01-01", "end": "2027-06-01"})
  with pytest.raises(signup_sheet.SheetProblem, match="fall in that period"):
    signup_sheet.make({"group_id": setup["group"], "start": "2026-12-01", "end": "2026-12-05"})
  completed = subprocess.run(
    [sys.executable, str(TOOL), "sign-up-sheet", f"--owner={LEADER}"],
    input=json.dumps({"group_id": setup["group"], "start": "2026-12-01", "end": "2026-12-14", "filled": False, "title": "T", "notes": {"html": ""}}),
    capture_output=True, text=True,
  )
  answer = json.loads(completed.stdout)
  assert completed.returncode == 0 and base64.b64decode(answer["pdf"]).startswith(b"%PDF")
  completed = subprocess.run([sys.executable, str(TOOL), "sheet-groups", f"--owner={LEADER}"], capture_output=True, text=True)
  assert [group["name"] for group in json.loads(completed.stdout)["groups"]] == ["Fellowship"]

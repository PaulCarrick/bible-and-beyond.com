"""Tests for members asking for a task and taking themselves off one (member_task_requests.py), the emails to
their group leader, and the email to the member when a leader confirms (scheduled_tasks.update_scheduled). Real
database; their own @task-requests-test.example accounts, a group and tasks owned by LEADER, all removed after."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import admin_tasks
import main
import member_task_requests
import scheduled_tasks
from search import connect

LEADER = 990401
OTHER_OWNER = 990402
DOMAIN = "task-requests-test.example"
TODAY = date(2026, 11, 26)  # a Thursday
SUNDAY = {"name": "Greeter", "description": {"text": "Welcome people"}, "repeat": "weekly", "weekdays": [6],
          "interval_count": 1, "first_date": "2026-11-01", "owner_email": "dan@example.test"}


@pytest.fixture
def setup(monkeypatch):
  sent = []
  for module in (member_task_requests,):
    monkeypatch.setattr(module, "load_mail_settings", lambda: {"from_address": "site@example.test"})
    monkeypatch.setattr(module, "send_email", lambda settings, email, recipients=None: sent.append(email))

  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM admin_tasks WHERE owner_uid IN (%s, %s)", (LEADER, OTHER_OWNER))
      connection.execute("DELETE FROM member_groups WHERE owner_uid = %s", (LEADER,))
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  with connect() as connection:
    member = connection.execute(
      f"INSERT INTO users (email, password_hash, first_name, last_name, email_verified_at) VALUES ('grace@{DOMAIN}', 'x', 'Grace', 'Sample', now()) RETURNING id"
    ).fetchone()[0]
    outsider = connection.execute(
      f"INSERT INTO users (email, password_hash, first_name, email_verified_at) VALUES ('sam@{DOMAIN}', 'x', 'Sam', now()) RETURNING id"
    ).fetchone()[0]
    group = connection.execute(
      "INSERT INTO member_groups (name, owner_uid, owner_name, owner_email) VALUES ('Greeters', %s, 'Pastor Dan', 'dan@example.test') RETURNING id",
      (LEADER,),
    ).fetchone()[0]
    connection.execute("INSERT INTO group_members (group_id, user_id, stop_token) VALUES (%s, %s, 'task-requests-token')", (group, member))
  sunday = SUNDAY
  greeter = admin_tasks.create_task(sunday, LEADER, "Pastor Dan")
  elsewhere = admin_tasks.create_task({**sunday, "name": "Ushers"}, OTHER_OWNER, "Someone else")
  yield {"member": member, "outsider": outsider, "greeter": greeter, "elsewhere": elsewhere, "sent": sent}
  clear()


def test_a_member_is_offered_their_leaders_tasks_for_two_months(setup):
  offered = member_task_requests.offered(setup["member"], TODAY)["tasks"]
  assert [task["name"] for task in offered] == ["Greeter"]
  days = [day["value"] for day in offered[0]["dates"]]
  # Every Sunday from today to the same day two months on (November 26 to January 26).
  assert days == ["2026-11-29", "2026-12-06", "2026-12-13", "2026-12-20", "2026-12-27", "2027-01-03", "2027-01-10", "2027-01-17", "2027-01-24"]
  assert offered[0]["dates"][0]["label"] == "Sunday, November 29, 2026"
  assert member_task_requests.offered(setup["outsider"], TODAY) == {"tasks": []}


def test_asking_for_a_task_adds_it_unconfirmed_and_emails_the_group_leader(setup):
  added = member_task_requests.request_task(setup["member"], setup["greeter"]["id"], "2026-12-06", TODAY)
  assert added["scheduled"]["confirmed"] is False and added["scheduled"]["on_date"] == "2026-12-06"
  assert added["scheduled"]["created_by_name"] == "Grace Sample (on the site)"
  assert member_task_requests.tell_leaders(added["notice"]) == 1
  email = setup["sent"][0]
  assert email["To"] == "dan@example.test" and email["Reply-To"] == f"grace@{DOMAIN}"
  assert email["Subject"] == "Task request: Grace Sample for Greeter on Sunday, December 6, 2026"
  assert "not confirmed yet" in email.get_body(("plain",)).get_content()
  # The date is no longer offered, and asking again is refused.
  days = [day["value"] for day in member_task_requests.offered(setup["member"], TODAY)["tasks"][0]["dates"]]
  assert "2026-12-06" not in days
  with pytest.raises(member_task_requests.RequestProblem, match="not offered"):
    member_task_requests.request_task(setup["member"], setup["greeter"]["id"], "2026-12-06", TODAY)
  with pytest.raises(member_task_requests.RequestProblem, match="not offered"):
    member_task_requests.request_task(setup["member"], setup["greeter"]["id"], "2026-12-07", TODAY)
  with pytest.raises(member_task_requests.RequestProblem, match="not one you can ask for"):
    member_task_requests.request_task(setup["member"], setup["elsewhere"]["id"], "2026-12-06", TODAY)
  with pytest.raises(member_task_requests.RequestProblem) as refused:
    member_task_requests.request_task(setup["outsider"], setup["greeter"]["id"], "2026-12-06", TODAY)
  assert refused.value.status_code == 403


def test_taking_yourself_off_a_task_emails_the_group_leader(setup):
  added = member_task_requests.request_task(setup["member"], setup["greeter"]["id"], "2026-12-13", TODAY)
  scheduled_id = added["scheduled"]["id"]
  with pytest.raises(member_task_requests.RequestProblem) as refused:
    member_task_requests.withdraw(setup["outsider"], scheduled_id, TODAY)
  assert refused.value.status_code == 404
  removed = member_task_requests.withdraw(setup["member"], scheduled_id, TODAY)
  member_task_requests.tell_leaders(removed["notice"])
  assert setup["sent"][-1]["Subject"] == "Task removed: Grace Sample is off Greeter on Sunday, December 13, 2026"
  assert scheduled_tasks.member_tasks(setup["member"], TODAY) == {"upcoming": [], "past": []}
  # A past one cannot be removed.
  past = member_task_requests.request_task(setup["member"], setup["greeter"]["id"], "2026-11-29", TODAY)
  with pytest.raises(member_task_requests.RequestProblem, match="already happened"):
    member_task_requests.withdraw(setup["member"], past["scheduled"]["id"], date(2026, 12, 1))


def test_the_member_is_told_when_a_leader_confirms(setup):
  added = member_task_requests.request_task(setup["member"], setup["greeter"]["id"], "2026-12-20", TODAY)
  scheduled_id = added["scheduled"]["id"]
  saved = scheduled_tasks.update_scheduled(scheduled_id, {"user_id": setup["member"], "on_date": "2026-12-20", "confirmed": True}, TODAY)
  assert saved["confirmed"] is True and saved["confirmation_notice"] == "Told by email"
  email = setup["sent"][-1]
  assert email["To"] == f"grace@{DOMAIN}" and email["Subject"] == "Confirmed: Greeter on Sunday, December 20, 2026"
  assert email["Reply-To"] == "dan@example.test"
  # Saving again while confirmed tells nobody.
  count = len(setup["sent"])
  again = scheduled_tasks.update_scheduled(scheduled_id, {"user_id": setup["member"], "on_date": "2026-12-20", "confirmed": True}, TODAY)
  assert "confirmation_notice" not in again and len(setup["sent"]) == count


def test_the_endpoints_need_a_login(setup, monkeypatch):
  client = TestClient(main.app)
  assert client.get("/scheduled-tasks/offered").status_code == 401
  assert client.post("/scheduled-tasks/mine", json={"task_id": 1, "on_date": "2026-12-06"}).status_code == 401
  assert client.delete("/scheduled-tasks/mine/1").status_code == 401
  monkeypatch.setattr(main, "user_for_token", lambda token: {"id": setup["outsider"]})
  answer = client.post("/scheduled-tasks/mine", json={"task_id": setup["greeter"]["id"], "on_date": "2026-12-06"}, cookies={"session": "x"})
  assert answer.status_code == 403


def test_a_date_with_as_many_people_as_expected_is_not_offered(setup):
  with connect() as connection:
    connection.execute(
      "INSERT INTO admin_scheduled_tasks (task_id, user_id, on_date, created_by_uid) VALUES (%s, %s, '2026-12-06', %s)",
      (setup["greeter"]["id"], setup["outsider"], LEADER),
    )
  days = [day["value"] for day in member_task_requests.offered(setup["member"], TODAY)["tasks"][0]["dates"]]
  assert "2026-12-06" not in days  # it expects one person (the default) and has one
  admin_tasks.update_task(setup["greeter"]["id"], {**SUNDAY, "expected_occurrences": 2})
  days = [day["value"] for day in member_task_requests.offered(setup["member"], TODAY)["tasks"][0]["dates"]]
  assert "2026-12-06" in days
  member_task_requests.request_task(setup["member"], setup["greeter"]["id"], "2026-12-06", TODAY)
  with connect() as connection:
    third = connection.execute(
      f"INSERT INTO users (email, password_hash, first_name) VALUES ('ruth@{DOMAIN}', 'x', 'Ruth') RETURNING id"
    ).fetchone()[0]
    group_id = connection.execute("SELECT id FROM member_groups WHERE owner_uid = %s", (LEADER,)).fetchone()[0]
    connection.execute("INSERT INTO group_members (group_id, user_id, stop_token) VALUES (%s, %s, 'task-requests-token-2')", (group_id, third))
  with pytest.raises(member_task_requests.RequestProblem, match="not offered"):
    member_task_requests.request_task(third, setup["greeter"]["id"], "2026-12-06", TODAY)

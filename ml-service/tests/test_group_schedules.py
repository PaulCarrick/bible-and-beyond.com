"""Tests for scheduled group messages (group_schedules.py). Mail and Telnyx are faked: nothing is sent. They use the
real tables with their own groups (owner 990101) and remove them after."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import group_schedules
import groups
import sms
from groups import GroupProblem
from search import connect

OWNER = 990101
CHICAGO = ZoneInfo("America/Chicago")
# Monday, November 16, 2026, 9:00 in Chicago.
NOW = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def outbox(monkeypatch):
  sent = {"emails": []}
  monkeypatch.setattr(sms, "is_configured", lambda: False)
  monkeypatch.setattr(groups, "load_mail_settings", lambda: {"from_address": "site@example.test"})
  # The members' copies only (not the leader's own copy of each send).
  monkeypatch.setattr(groups, "send_email", lambda settings, email, recipients=None: recipients != ["dave@example.org"] and sent["emails"].append(email))
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM member_groups WHERE owner_uid = %s", (OWNER,))

  clear()
  yield sent
  clear()


def group_with_a_member():
  group = groups.save_group(None, {"name": "Care list"}, OWNER, "Deacon Dave", "dave@example.org")
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  return group


def local(moment: str) -> str:
  return datetime.fromisoformat(moment).astimezone(CHICAGO).strftime("%a %Y-%m-%d %H:%M")


BASE = {"send_time": time(9, 0), "timezone": "America/Chicago", "on_date": None, "day_of_month": None, "weekday": None, "week_of_month": None}


@pytest.mark.parametrize(
  "schedule, after, expected",
  [
    (dict(BASE, repeat="monthly_weekday", weekday=0, week_of_month=1), NOW, "2026-12-07 09:00"),  # first Monday; today's has gone
    (dict(BASE, repeat="monthly_weekday", weekday=0, week_of_month=1), NOW - timedelta(days=16), "2026-11-02 09:00"),
    (dict(BASE, repeat="monthly_weekday", weekday=4, week_of_month=5), NOW, "2026-11-27 09:00"),  # last Friday
    (dict(BASE, repeat="monthly_weekday", weekday=6, week_of_month=3), NOW, "2026-12-20 09:00"),  # third Sunday (November's has gone)
    (dict(BASE, repeat="monthly_day", day_of_month=31), NOW, "2026-11-30 09:00"),  # the last day of a shorter month
    (dict(BASE, repeat="monthly_day", day_of_month=31), datetime(2027, 2, 1, tzinfo=timezone.utc), "2027-02-28 09:00"),
    (dict(BASE, repeat="monthly_day", day_of_month=16), NOW - timedelta(minutes=1), "2026-11-16 09:00"),
    (dict(BASE, repeat="weekly", weekday=6), NOW, "2026-11-22 09:00"),
    (dict(BASE, repeat="once", on_date=date(2026, 12, 25)), NOW, "2026-12-25 09:00"),
  ],
)
def test_the_next_time(schedule, after, expected):
  assert group_schedules.next_occurrence(schedule, after).astimezone(CHICAGO).strftime("%Y-%m-%d %H:%M") == expected


def test_a_time_across_a_clock_change_stays_at_the_local_hour():
  schedule = dict(BASE, repeat="weekly", weekday=0)
  before = group_schedules.next_occurrence(schedule, datetime(2026, 10, 20, tzinfo=timezone.utc))  # Monday October 26
  after = group_schedules.next_occurrence(schedule, datetime(2026, 10, 27, tzinfo=timezone.utc))  # Monday November 2
  assert before.astimezone(CHICAGO).hour == after.astimezone(CHICAGO).hour == 9
  assert (after - before) == timedelta(days=7, hours=1)  # daylight saving time ended on November 1


def test_described_in_words():
  assert group_schedules.describe(dict(BASE, repeat="monthly_weekday", weekday=0, week_of_month=1)) == "Every month on the first Monday at 9:00 AM (America/Chicago)"
  assert group_schedules.describe(dict(BASE, repeat="monthly_day", day_of_month=22)) == "Every month on the 22nd at 9:00 AM (America/Chicago)"
  assert "last day in shorter months" in group_schedules.describe(dict(BASE, repeat="monthly_day", day_of_month=30))


def message(**extra):
  return {"kind": "message", "subject": "Prayer meeting", "text": "We meet tonight at 7.", "send_time": "09:00", "timezone": "America/Chicago", **extra}


def test_add_edit_and_remove():
  group = group_with_a_member()
  schedule = group_schedules.add_schedule(group["id"], message(repeat="monthly_weekday", weekday=0, week_of_month=1), "dave", now=NOW)
  assert local(schedule["next_run_at"]) == "Mon 2026-12-07 09:00" and schedule["description"].startswith("Every month on the first Monday")
  changed = group_schedules.update_schedule(group["id"], schedule["id"], message(repeat="monthly_day", day_of_month=1, subject="Changed"), now=NOW)
  assert changed["subject"] == "Changed" and local(changed["next_run_at"]) == "Tue 2026-12-01 09:00"
  assert [each["id"] for each in group_schedules.list_schedules(group["id"])] == [schedule["id"]]
  group_schedules.remove_schedule(group["id"], schedule["id"])
  assert group_schedules.list_schedules(group["id"]) == []


@pytest.mark.parametrize(
  "details, fragment",
  [
    (message(repeat="once", on_date="2026-11-01"), "already passed"),
    (message(repeat="once", on_date="not a date"), "date"),
    (message(repeat="weekly"), "day of the week"),
    (message(repeat="monthly_weekday", weekday=0, week_of_month=9), "week of the month"),
    (message(repeat="monthly_day", day_of_month=32), "day of the month"),
    (message(repeat="weekly", weekday=0, send_time="25:00"), "time"),
    (message(repeat="weekly", weekday=0, timezone="Mars/Olympus"), "time zone"),
    (message(repeat="weekly", weekday=0, subject=""), "subject"),
    (message(repeat="sometimes"), "when"),
  ],
)
def test_bad_schedules_are_refused(details, fragment):
  group = group_with_a_member()
  with pytest.raises(GroupProblem, match=fragment):
    group_schedules.add_schedule(group["id"], details, "dave", now=NOW)


def test_a_due_message_is_sent_once_and_moves_on(outbox):
  group = group_with_a_member()
  schedule = group_schedules.add_schedule(group["id"], message(repeat="weekly", weekday=0), "dave", now=NOW - timedelta(hours=1))
  assert local(schedule["next_run_at"]) == "Mon 2026-11-16 09:00"
  assert group_schedules.send_due(NOW - timedelta(minutes=5), pause=0)["sent"] == 0  # not yet
  assert group_schedules.send_due(NOW + timedelta(minutes=2), pause=0)["sent"] == 1
  assert group_schedules.send_due(NOW + timedelta(minutes=7), pause=0)["sent"] == 0  # not twice
  assert [email["Subject"] for email in outbox["emails"]] == ["Prayer meeting"]
  after = group_schedules.get_schedule(group["id"], schedule["id"])
  assert local(after["next_run_at"]) == "Mon 2026-11-23 09:00" and after["last_result"] == "1 emailed, 0 texted"
  assert groups.list_sent(group["id"])[0]["sent_by"] == "schedule (dave)"


def test_a_one_time_message_goes_once_and_a_verse_card_is_new_each_time(outbox):
  group = group_with_a_member()
  once = group_schedules.add_schedule(group["id"], {"kind": "verse", "repeat": "once", "on_date": "2026-11-16", "send_time": "09:30", "timezone": "America/Chicago"}, "dave", now=NOW)
  assert group_schedules.send_due(NOW + timedelta(minutes=31), pause=0)["sent"] == 1
  email = outbox["emails"][0]
  assert email["Subject"].startswith("A verse for Care list: ") and [part for part in email.walk() if part.get_content_type() == "image/jpeg"]
  assert group_schedules.get_schedule(group["id"], once["id"])["next_run_at"] is None


def test_a_run_missed_by_hours_is_skipped_not_sent_late(outbox):
  group = group_with_a_member()
  schedule = group_schedules.add_schedule(group["id"], message(repeat="weekly", weekday=0), "dave", now=NOW - timedelta(hours=1))
  result = group_schedules.send_due(NOW + timedelta(hours=7), pause=0)
  assert result["late"] == 1 and result["sent"] == 0 and outbox["emails"] == []
  after = group_schedules.get_schedule(group["id"], schedule["id"])
  assert after["last_result"].startswith("Skipped") and local(after["next_run_at"]) == "Mon 2026-11-23 09:00"


def test_a_picture_message_is_made_at_send_time(outbox):
  group = group_with_a_member()
  group_schedules.add_schedule(group["id"], message(kind="picture", text="Praying for you.", repeat="weekly", weekday=0), "dave", now=NOW - timedelta(hours=1))
  assert group_schedules.send_due(NOW + timedelta(minutes=1), pause=0)["sent"] == 1
  assert [part for part in outbox["emails"][0].walk() if part.get_content_type() == "image/jpeg"]


def test_deleting_the_group_removes_its_schedules():
  group = group_with_a_member()
  group_schedules.add_schedule(group["id"], message(repeat="weekly", weekday=2), "dave", now=NOW)
  groups.delete_group(group["id"])
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM group_schedules WHERE group_id = %s", (group["id"],)).fetchone()[0] == 0

"""Tests for scheduled group messages (group_schedules.py). Mail and Telnyx are faked: nothing is sent. They use the
real tables with their own groups (owner 990101) and remove them after."""

import re
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
  sent = groups.list_sent(group["id"])[0]
  assert sent["sent_by"] == "schedule (dave)"
  # The copy kept (2026-11-18) is a member's, with the scheduled email's own stop links (the code a placeholder).
  copy = groups.get_copy(group["id"], sent["id"])
  assert copy["subject"] == "Prayer meeting" and len(copy["bcc"]) == 1
  assert f"{groups.STOP_CODE_PLACEHOLDER}.s{schedule['id']}" in copy["text"] and f"{groups.STOP_CODE_PLACEHOLDER}.sall" in copy["text"]


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


def test_a_test_goes_to_the_leader_only_and_leaves_the_schedule_alone(monkeypatch):
  delivered = []
  monkeypatch.setattr(groups, "send_email", lambda settings, email, recipients=None: delivered.append((recipients, email)))
  texts = []
  monkeypatch.setattr(sms, "send_text", lambda *arguments, **keywords: texts.append(arguments))
  group = group_with_a_member()
  groups.add_member(group["id"], {"email": "sam@example.org", "name": "Sam"})
  schedule = group_schedules.add_schedule(group["id"], message(repeat="weekly", weekday=0), "dave", now=NOW)
  before = group_schedules.get_schedule(group["id"], schedule["id"])

  answer = group_schedules.send_test(group["id"], schedule["id"])
  assert answer["to"] == "dave@example.org" and answer["schedule"]["id"] == schedule["id"]
  # One email, to the leader alone: no member, no text.
  assert [recipients for recipients, _ in delivered] == [["dave@example.org"]] and texts == []
  email = delivered[0][1]
  # Exactly what a member gets (the owner's request): the same subject and the same foot with all the stop links
  # and the one-click header, but with a made-up member code that matches nobody.
  delivered.clear()
  with connect() as connection:
    connection.execute("UPDATE group_schedules SET next_run_at = %s WHERE id = %s", (NOW, schedule["id"]))
    tokens = [row[0] for row in connection.execute("SELECT stop_token FROM group_members WHERE group_id = %s", (group["id"],))]
  group_schedules.send_due(NOW + timedelta(minutes=1), pause=0)
  member_copy = next(sent for recipients, sent in delivered if recipients == ["pat@example.org"])
  pat_token = next(token for token in tokens if token in member_copy["List-Unsubscribe"])
  fake = email["List-Unsubscribe"].split("token=")[1].split(".s")[0]
  assert fake not in tokens and len(fake) == len(pat_token)
  assert email["Subject"] == member_copy["Subject"] == "Prayer meeting" and email["To"] == "dave@example.org"
  assert email.get_content().replace(fake, "CODE") == member_copy.get_content().replace(pat_token, "CODE")
  assert email["List-Unsubscribe"].replace(fake, "CODE") == member_copy["List-Unsubscribe"].replace(pat_token, "CODE")
  assert "To stop this scheduled email (“Prayer meeting”)" in email.get_content()
  assert "pat@example.org" not in email.as_string() and "sam@example.org" not in email.as_string()
  # Its links stop nothing.
  from subscriptions import SubscriptionProblem, unsubscribe_with_token

  for suffix in (f".s{schedule['id']}", ".sall", ""):
    with pytest.raises(SubscriptionProblem):
      unsubscribe_with_token(fake + suffix)
  with connect() as connection:
    connection.execute("UPDATE group_schedules SET next_run_at = %s, last_run_at = %s, last_result = %s WHERE id = %s",
                       (before["next_run_at"], before["last_run_at"], before["last_result"], schedule["id"]))
    connection.execute("DELETE FROM group_messages WHERE group_id = %s", (group["id"],))
  # The schedule and the Sent table are as they were.
  assert group_schedules.get_schedule(group["id"], schedule["id"]) == before and groups.list_sent(group["id"]) == []

  # A verse card is made afresh, as at its time, with its picture.
  delivered.clear()
  verse = group_schedules.add_schedule(group["id"], {"kind": "verse", "repeat": "weekly", "weekday": 0, "send_time": "09:00", "timezone": "America/Chicago"}, "dave", now=NOW)
  group_schedules.send_test(group["id"], verse["id"])
  email = delivered[0][1]
  assert email["Subject"].startswith("A verse for Care list: ") and ".sall" in email.get_body(("plain",)).get_content() and [part for part in email.walk() if part.get_content_type() == "image/jpeg"]

  # Refused: a group whose leader has no address, and a schedule of another group.
  groups.save_group(group["id"], {"name": "Care list"}, OWNER, "Deacon Dave", "")
  with pytest.raises(GroupProblem, match="no email address"):
    group_schedules.send_test(group["id"], schedule["id"])
  other = groups.save_group(None, {"name": "Other"}, OWNER, "Deacon Dave", "dave@example.org")
  with pytest.raises(GroupProblem):
    group_schedules.send_test(other["id"], schedule["id"])
  assert len(delivered) == 1


def test_a_scheduled_email_can_be_stopped_alone_or_all_without_leaving_the_group(outbox):
  from fastapi.testclient import TestClient
  from main import app

  client = TestClient(app)
  group = group_with_a_member()  # Pat
  groups.add_member(group["id"], {"email": "sam@example.org", "name": "Sam"})
  weekly = group_schedules.add_schedule(group["id"], message(repeat="weekly", weekday=0), "dave", now=NOW - timedelta(hours=1))
  monthly = group_schedules.add_schedule(group["id"], message(repeat="monthly_day", day_of_month=16, subject="Monthly news"), "dave", now=NOW - timedelta(hours=1))
  assert group_schedules.send_due(NOW + timedelta(minutes=1), pause=0)["sent"] == 2
  # Each scheduled email carries its own stop links: this one, all scheduled ones, and everything from the group.
  text = outbox["emails"][0].get_content()
  assert "To stop this scheduled email (“Prayer meeting”), open: " in text or "To stop this scheduled email (“Monthly news”), open: " in text
  assert "To stop all scheduled emails from this group, open: " in text and "To stop all messages from this group, open: " in text
  assert "You stay in the group" in text

  with connect() as connection:
    tokens = dict(connection.execute("SELECT email, stop_token FROM group_members WHERE group_id = %s", (group["id"],)).fetchall())
  # The one-click header of a scheduled email stops that scheduled email only.
  headers = [email["List-Unsubscribe"] for email in outbox["emails"]]
  assert f"token={tokens['pat@example.org']}.s{weekly['id']}>" in " ".join(headers)

  # Pat stops the weekly one only (as the site's stop page does).
  answer = client.post(f"/subscriptions/unsubscribe?token={tokens['pat@example.org']}.s{weekly['id']}")
  assert answer.status_code == 200 and "Prayer meeting" in answer.json()["devotional"] and "stay in the group" in answer.json()["devotional"]
  # Sam stops all the group's scheduled emails.
  answer = client.post(f"/subscriptions/unsubscribe?token={tokens['sam@example.org']}.sall")
  assert answer.status_code == 200 and "scheduled emails from the group “Care list”" in answer.json()["devotional"]

  # Both are still members, and not stopped for what the leader sends by hand.
  after = {member["email"]: member for member in groups.get_group(group["id"])["members"]}
  assert set(after) == {"pat@example.org", "sam@example.org"} and not any(member["stopped"] for member in after.values())
  assert after["pat@example.org"]["stopped_schedules"] == 1 and after["pat@example.org"]["schedules_stopped"] is False
  assert after["sam@example.org"]["schedules_stopped"] is True
  counts = {schedule["id"]: schedule["stopped_count"] for schedule in group_schedules.list_schedules(group["id"])}
  assert counts == {weekly["id"]: 2, monthly["id"]: 1}

  # Next week: the weekly one goes to nobody (both skipped); the monthly one (next month) only to Pat.
  outbox["emails"].clear()
  assert group_schedules.send_due(NOW + timedelta(days=7, minutes=1), pause=0)["sent"] == 1
  assert outbox["emails"] == [] and group_schedules.get_schedule(group["id"], weekly["id"])["last_result"] == "0 emailed, 0 texted, 2 skipped"
  later = datetime(2026, 12, 16, 15, 1, tzinfo=timezone.utc)
  group_schedules.send_due(later, pause=0)
  assert [email["Subject"] for email in outbox["emails"]] == ["Monthly news"]
  assert tokens["pat@example.org"] in outbox["emails"][0]["List-Unsubscribe"]
  # A scheduled email added later is stopped for Sam too.
  outbox["emails"].clear()
  group_schedules.add_schedule(group["id"], message(repeat="weekly", weekday=1, subject="New one"), "dave", now=later)
  group_schedules.send_due(later + timedelta(days=6, minutes=10), pause=0)
  assert [email["List-Unsubscribe"].count(tokens["pat@example.org"]) for email in outbox["emails"]] == [1]
  # What the leader sends by hand still reaches both.
  outbox["emails"].clear()
  assert groups.send(group["id"], "message", {"subject": "By hand", "text": "Hi"}, "dave", pause=0)["emailed"] == 2
  assert "To stop this scheduled email" not in outbox["emails"][0].get_content()

  # Links that are not good: a schedule of another group, garbage, an unknown member.
  other = groups.save_group(None, {"name": "Other"}, OWNER, "Deacon Dave", "dave@example.org")
  other_schedule = group_schedules.add_schedule(other["id"], message(repeat="weekly", weekday=0), "dave", now=NOW)
  for bad in (f"{tokens['pat@example.org']}.s{other_schedule['id']}", f"{tokens['pat@example.org']}.sx", "nobody-at-all-here.s1"):
    assert client.post(f"/subscriptions/unsubscribe?token={bad}").status_code == 404
  # Removing the schedule removes its stops.
  group_schedules.remove_schedule(group["id"], weekly["id"])
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM group_schedule_stops WHERE schedule_id = %s", (weekly["id"],)).fetchone()[0] == 0


def test_a_scheduled_message_from_the_editor_keeps_its_formatting(outbox):
  group = group_with_a_member()
  details = message(repeat="weekly", weekday=0)
  details.pop("text")
  details["html"] = "<p>We meet <strong>tonight</strong></p><script>x</script>"
  schedule = group_schedules.add_schedule(group["id"], details, "dave", now=NOW - timedelta(hours=1))
  assert schedule["html"] == "<p>We meet <strong>tonight</strong></p>" and schedule["text"] == "We meet tonight"
  assert group_schedules.send_due(NOW + timedelta(minutes=1), pause=0)["sent"] == 1
  email = outbox["emails"][0]
  assert "<strong>tonight</strong>" in email.get_body(("html",)).get_content() and "To stop this scheduled email" in email.get_body(("html",)).get_content()
  assert "We meet tonight" in email.get_body(("plain",)).get_content()
  # An older plain message still goes as plain text.
  plain = group_schedules.add_schedule(group["id"], message(repeat="weekly", weekday=1), "dave", now=NOW)
  assert plain["html"] is None


def test_the_stop_page_says_it_plainly_and_the_leader_can_undo(outbox):
  from fastapi.testclient import TestClient
  from main import app

  client = TestClient(app)
  group = group_with_a_member()  # Pat
  weekly = group_schedules.add_schedule(group["id"], message(repeat="weekly", weekday=0), "dave", now=NOW - timedelta(hours=1))
  verse = group_schedules.add_schedule(group["id"], {"kind": "verse", "repeat": "weekly", "weekday": 2, "send_time": "09:00", "timezone": "America/Chicago"}, "dave", now=NOW)
  with connect() as connection:
    token, member_id = connection.execute("SELECT stop_token, id FROM group_members WHERE group_id = %s", (group["id"],)).fetchone()

  # The sentence the stop page shows, for each kind of link.
  answer = client.post(f"/subscriptions/unsubscribe?token={token}.s{weekly['id']}").json()
  assert answer["message"] == (
    "You will not get the scheduled email “Prayer meeting” from the group “Care list” any more. You are still in the "
    "group, and still get the messages your leader sends and its other scheduled emails."
  )
  answer = client.post(f"/subscriptions/unsubscribe?token={token}.s{verse['id']}").json()
  assert answer["message"].startswith("You will not get the scheduled verse card from the group “Care list” any more.")
  answer = client.post(f"/subscriptions/unsubscribe?token={token}.sall").json()
  assert answer["message"] == (
    "You will not get any scheduled emails from the group “Care list” any more. You are still in the group, and still "
    "get the messages your leader sends."
  )
  pat = groups.get_group(group["id"])["members"][0]
  assert pat["schedules_stopped"] is True and pat["stopped_schedules"] == 2

  # The leader's undo clears both kinds; the scheduled emails reach Pat again.
  again = groups.restart_schedules(group["id"], member_id)
  assert again["schedules_stopped"] is False and again["stopped_schedules"] == 0
  assert {schedule["stopped_count"] for schedule in group_schedules.list_schedules(group["id"])} == {0}
  assert group_schedules.send_due(NOW + timedelta(minutes=1), pause=0)["sent"] == 1
  assert [email["Subject"] for email in outbox["emails"]] == ["Prayer meeting"]
  # It does not undo the group's own stop link (everything from the group), and refuses another group's member.
  client.post(f"/subscriptions/unsubscribe?token={token}")
  assert groups.restart_schedules(group["id"], member_id)["stopped"] is True
  other = groups.save_group(None, {"name": "Other"}, OWNER, "Deacon Dave", "dave@example.org")
  with pytest.raises(GroupProblem, match="not in the group"):
    groups.restart_schedules(other["id"], member_id)


def test_deleting_the_group_removes_its_schedules():
  group = group_with_a_member()
  group_schedules.add_schedule(group["id"], message(repeat="weekly", weekday=2), "dave", now=NOW)
  groups.delete_group(group["id"])
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM group_schedules WHERE group_id = %s", (group["id"],)).fetchone()[0] == 0


def test_a_message_to_one_member_can_wait_for_its_time(outbox):
  """"Send at" on a member's Email box (2026-11-18): a later time keeps it as a one-time email to that member."""
  group = group_with_a_member()
  groups.add_member(group["id"], {"email": "sam@example.org", "name": "Sam"})
  members = {member["name"]: member["id"] for member in groups.get_group(group["id"])["members"]}
  details = {"subject": "Sunday lunch", "html": "<p>Hi <strong>Pat</strong>, see you Sunday.</p>", "on_date": "2026-11-17", "send_time": "10:30", "timezone": "America/Chicago"}
  schedule = group_schedules.schedule_member_email(group["id"], members["Pat"], details, "dave", now=NOW)
  assert schedule["member_id"] == members["Pat"] and schedule["repeat"] == "once"
  assert local(schedule["next_run_at"]) == "Tue 2026-11-17 10:30"
  listed = group_schedules.list_schedules(group["id"])
  # The subject typed in the box (2026-11-18).
  assert [(each["member_name"], each["subject"]) for each in listed] == [("Pat", "Sunday lunch")]
  assert listed[0]["stopped_count"] == 0

  # Not before its time; then once, to Pat alone, as Send on the box would.
  assert group_schedules.send_due(now=NOW)["sent"] == 0 and outbox["emails"] == []
  due = datetime.fromisoformat(schedule["next_run_at"]) + timedelta(minutes=2)
  assert group_schedules.send_due(now=due, pause=0)["sent"] == 1
  assert len(outbox["emails"]) == 1
  email = outbox["emails"][0]
  assert email["Subject"] == "Sunday lunch" and email["To"] == "pat@example.org"
  # Like Send on the box: the words only, no group foot or stop link (2026-11-18).
  assert "Pat" in email.get_body(("html",)).get_content() and "Sent by" not in email.as_string() and email["List-Unsubscribe"] is None
  after = group_schedules.get_schedule(group["id"], schedule["id"])
  assert after["next_run_at"] is None and after["last_result"] == "Emailed to Pat"
  assert group_schedules.send_due(now=due + timedelta(minutes=10), pause=0)["sent"] == 0 and len(outbox["emails"]) == 1
  assert groups.list_sent(group["id"])[0]["subject"].endswith("(to one member)")


def test_a_message_to_one_member_is_checked_and_follows_the_member(outbox):
  group = group_with_a_member()
  pat = groups.get_group(group["id"])["members"][0]["id"]
  later = {"text": "Hello", "on_date": "2026-11-20", "send_time": "08:00", "timezone": "America/Chicago"}
  with pytest.raises(GroupProblem, match="already passed"):
    group_schedules.schedule_member_email(group["id"], pat, dict(later, on_date="2026-11-15"), "dave", now=NOW)
  with pytest.raises(GroupProblem, match="date and time"):
    group_schedules.schedule_member_email(group["id"], pat, dict(later, send_time="later"), "dave", now=NOW)
  with pytest.raises(GroupProblem, match="message"):
    group_schedules.schedule_member_email(group["id"], pat, dict(later, text="  "), "dave", now=NOW)
  with pytest.raises(GroupProblem, match="not in the group"):
    group_schedules.schedule_member_email(group["id"], pat + 100000, later, "dave", now=NOW)
  schedule = group_schedules.schedule_member_email(group["id"], pat, later, "dave", now=NOW)
  # It cannot be edited as a group's scheduled email (remove it and write it again).
  with pytest.raises(GroupProblem, match="cannot be changed"):
    group_schedules.update_schedule(group["id"], schedule["id"], {"kind": "message"}, now=NOW)
  # A member who stopped the group's messages meanwhile is not emailed; the result says why.
  with connect() as connection:
    connection.execute("UPDATE group_members SET stopped_at = now() WHERE id = %s", (pat,))
  due = datetime.fromisoformat(schedule["next_run_at"]) + timedelta(minutes=1)
  assert group_schedules.send_due(now=due, pause=0)["failed"] == 1 and outbox["emails"] == []
  assert "stopped the group's messages" in group_schedules.get_schedule(group["id"], schedule["id"])["last_result"]
  # Removing the member removes what was waiting for them.
  groups.remove_member(group["id"], pat)
  assert group_schedules.list_schedules(group["id"]) == []


# --- a signature on each scheduled email (2026-11-19) ------------------------------------------------------


@pytest.fixture
def signatures_of_the_leader():
  """Two of the leader's signatures and one of someone else's; deleted afterwards."""
  import signatures

  made = [
    signatures.create_signature({"name": "Formal", "signature": {"html": "<p><strong>Deacon Dave</strong><br>First Church</p>"}}, OWNER, "Dave"),
    signatures.create_signature({"name": "Short", "signature": {"text": "Dave"}}, OWNER, "Dave"),
    signatures.create_signature({"name": "Not his", "signature": {"text": "Someone else"}}, OWNER + 1, "Ruth"),
  ]
  yield made
  with connect() as connection:
    connection.execute("DELETE FROM admin_signatures WHERE id = ANY(%s)", ([item["id"] for item in made],))


def test_each_scheduled_email_has_its_own_signature(outbox, signatures_of_the_leader):
  formal, short, not_his = signatures_of_the_leader
  group = group_with_a_member()
  signed = group_schedules.add_schedule(
    group["id"], {**message(repeat="weekly", weekday=0), "html": "<p>See you <em>Sunday</em>.</p>", "signature_id": str(formal["id"])}, "dave", now=NOW - timedelta(hours=1)
  )
  plain = group_schedules.add_schedule(group["id"], message(repeat="weekly", weekday=0), "dave", now=NOW - timedelta(hours=1))
  assert signed["signature_id"] == formal["id"] and plain["signature_id"] is None
  listed = {item["id"]: item for item in group_schedules.list_schedules(group["id"])}
  assert listed[signed["id"]]["signature_name"] == "Formal" and listed[plain["id"]]["signature_name"] is None
  assert group_schedules.send_due(NOW + timedelta(minutes=2), pause=0)["sent"] == 2
  by_signature = {"First Church" in email.get_body(("plain",)).get_content(): email for email in outbox["emails"]}
  with_it, without = by_signature[True], by_signature[False]
  text = with_it.get_body(("plain",)).get_content()
  assert text.index("Sunday") < text.index("Deacon Dave\nFirst Church") < text.index("--")
  assert "<em>Sunday</em>.</p><p><strong>Deacon Dave</strong><br>First Church</p><hr>" in with_it.get_body(("html",)).get_content()
  assert "First Church" not in without.get_body(("plain",)).get_content()
  # Changed to another signature, or to none; someone else's is refused.
  changed = group_schedules.update_schedule(group["id"], signed["id"], {**message(repeat="weekly", weekday=0), "signature_id": short["id"]}, now=NOW)
  assert changed["signature_id"] == short["id"]
  with pytest.raises(GroupProblem, match="not one of the group leader's"):
    group_schedules.update_schedule(group["id"], signed["id"], {**message(repeat="weekly", weekday=0), "signature_id": not_his["id"]}, now=NOW)
  assert group_schedules.update_schedule(group["id"], signed["id"], {**message(repeat="weekly", weekday=0), "signature_id": ""}, now=NOW)["signature_id"] is None


def test_a_deleted_signature_leaves_the_schedule_with_none(outbox, signatures_of_the_leader):
  import signatures

  formal = signatures_of_the_leader[0]
  group = group_with_a_member()
  schedule = group_schedules.add_schedule(group["id"], {**message(repeat="weekly", weekday=0), "signature_id": formal["id"]}, "dave", now=NOW)
  signatures.delete_signature(formal["id"])
  assert group_schedules.get_schedule(group["id"], schedule["id"])["signature_id"] is None


def test_a_test_of_a_scheduled_email_has_its_signature(outbox, signatures_of_the_leader, monkeypatch):
  short = signatures_of_the_leader[1]
  group = group_with_a_member()
  schedule = group_schedules.add_schedule(group["id"], {**message(repeat="weekly", weekday=0), "signature_id": short["id"]}, "dave", now=NOW)
  tests = []
  monkeypatch.setattr(groups, "send_email", lambda settings, email, recipients=None: tests.append(email))
  group_schedules.send_test(group["id"], schedule["id"])
  assert "\n\nDave\n" in tests[0].get_body(("plain",)).get_content()


def test_the_stop_links_of_a_formatted_scheduled_email_are_whole_links(outbox):
  # Found 2026-11-19: the group's stop address is the start of the scheduled email's, and making them links one
  # after the other put a link inside a link.
  group = group_with_a_member()
  group_schedules.add_schedule(group["id"], {**message(repeat="weekly", weekday=0), "html": "<p>Hello</p>"}, "dave", now=NOW - timedelta(hours=1))
  group_schedules.send_due(NOW + timedelta(minutes=2), pause=0)
  html = outbox["emails"][0].get_body(("html",)).get_content()
  links = re.findall(r'<a href="([^"]+)">([^<]+)</a>', html)
  assert len(links) == 3 and all(address == shown for address, shown in links)
  assert len({address for address, _ in links}) == 3
  assert '<a href="<a' not in html and "</a></a>" not in html and "</a>.s" not in html


def test_an_email_to_one_member_can_have_a_signature_now_or_later(outbox, signatures_of_the_leader):
  formal, _, not_his = signatures_of_the_leader
  group = group_with_a_member()
  pat = groups.get_group(group["id"])["members"][0]["id"]
  # Send now: the tool checks it is the leader's, then the email has it after the words.
  groups.email_member(group["id"], pat, "", "dave", html="<p>Hello Pat</p>", signature=groups.signature_words(formal["id"]))
  email = outbox["emails"][-1]
  assert email.get_body(("plain",)).get_content().startswith("Hello Pat\n\nDeacon Dave\nFirst Church")
  assert "<p>Hello Pat</p><p><strong>Deacon Dave</strong><br>First Church</p>" in email.get_body(("html",)).get_content()
  with pytest.raises(GroupProblem, match="not one of the group leader's"):
    groups.leader_signature(group, not_his["id"])
  # Send at: kept with the schedule and sent with it.
  later = {"html": "<p>See you</p>", "subject": "Lunch", "on_date": "2026-11-17", "send_time": "10:30", "timezone": "America/Chicago", "signature_id": formal["id"]}
  schedule = group_schedules.schedule_member_email(group["id"], pat, later, "dave", now=NOW)
  assert schedule["signature_id"] == formal["id"]
  with pytest.raises(GroupProblem, match="not one of the group leader's"):
    group_schedules.schedule_member_email(group["id"], pat, dict(later, signature_id=not_his["id"]), "dave", now=NOW)
  outbox["emails"].clear()
  assert group_schedules.send_due(now=datetime(2026, 11, 17, 16, 31, tzinfo=timezone.utc), pause=0)["sent"] == 1
  assert "See you\n\nDeacon Dave\nFirst Church" in outbox["emails"][0].get_body(("plain",)).get_content()


def test_a_message_sent_now_can_have_a_signature(outbox, signatures_of_the_leader):
  formal, _, not_his = signatures_of_the_leader
  group = group_with_a_member()
  groups.send(group["id"], "message", {"subject": "Thanksgiving", "html": "<p>Greetings,</p>", "signature_id": str(formal["id"])}, "dave", pause=0)
  email = outbox["emails"][-1]
  plain = email.get_body(("plain",)).get_content()
  # After the words, before the foot.
  assert plain.index("Deacon Dave\nFirst Church") < plain.index("--")
  assert "<strong>Deacon Dave</strong>" in email.get_body(("html",)).get_content()
  # A verse card can have one too, and none is fine.
  preview = groups.preview_verse()
  groups.send(group["id"], "verse", {"card": preview["card"], "verse": preview["verse"], "signature_id": str(formal["id"])}, "dave", pause=0)
  assert "First Church" in outbox["emails"][-1].get_body(("plain",)).get_content()
  groups.send(group["id"], "message", {"subject": "Hi", "text": "Hello.", "signature_id": ""}, "dave", pause=0)
  assert "First Church" not in outbox["emails"][-1].get_body(("plain",)).get_content()
  with pytest.raises(GroupProblem, match="not one of the group leader's"):
    groups.send(group["id"], "message", {"subject": "Hi", "text": "Hello.", "signature_id": str(not_his["id"])}, "dave", pause=0)

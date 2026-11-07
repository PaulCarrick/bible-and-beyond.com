"""Tests for daily devotional emails. The mail server and drush are faked: nothing is sent. They use the real
devotionals and tables, and remove their own users (and so their subscriptions) after."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import accounts
import subscriptions
from main import app
from search import connect

PASSWORD = "correct horse battery"
client = TestClient(app)
SETTINGS = {"smtp_host": "x", "smtp_port": 25, "from_address": "site@example.test", "to_address": "o@example.test", "subject": "s"}


def utc(year, month, day, hour=0, minute=0):
  return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
  """Account emails are collected, and so are the devotional emails: both as the messages that would be sent."""
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  sent = []
  monkeypatch.setattr(subscriptions, "load_mail_settings", lambda: SETTINGS)
  monkeypatch.setattr(subscriptions, "send_email", lambda settings, email: sent.append(email))
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM users WHERE email LIKE '%@subs-test.example'")

  clear()
  client.cookies.clear()
  yield sent
  clear()


def sign_up(name="ann", verified=True):
  response = client.post(
    "/account/register",
    json={"email": f"{name}@subs-test.example", "password": PASSWORD, "password_confirmation": PASSWORD},
  )
  assert response.status_code == 200
  user_id = response.json()["user"]["id"]
  if verified:
    with connect() as connection:
      connection.execute("UPDATE users SET email_verified_at = now() WHERE id = %s", (user_id,))
  return user_id


def subscribe(devotional="morning-and-evening", send_time="07:00", zone="America/Chicago", **extra):
  return client.put(f"/devotional-subscriptions/{devotional}", json={"send_time": send_time, "timezone": zone, **extra})


def run(now, sent):
  sent.clear()
  return subscriptions.send_due(now, pause=0)


def test_subscriptions_need_a_login_and_a_confirmed_address():
  assert subscribe().status_code == 401
  assert client.get("/devotional-subscriptions").status_code == 401
  sign_up(verified=False)

  response = subscribe()

  assert response.status_code == 403 and "confirm your email address" in response.json()["detail"]


def test_a_visitor_subscribes_changes_the_time_and_stops():
  sign_up()

  saved = subscribe(send_time="06:30", zone="Europe/London").json()["subscription"]
  assert (saved["devotional_id"], saved["send_time"], saved["timezone"], saved["kind"]) == ("morning-and-evening", "06:30", "Europe/London", "daily")
  assert saved["devotional_name"] == "Morning and Evening" and saved["next_section"] is None

  changed = subscribe(send_time="19:15", zone="Asia/Tokyo").json()["subscription"]
  assert (changed["send_time"], changed["timezone"]) == ("19:15", "Asia/Tokyo")
  assert len(client.get("/devotional-subscriptions").json()["subscriptions"]) == 1

  assert client.delete("/devotional-subscriptions/morning-and-evening").status_code == 200
  assert client.get("/devotional-subscriptions").json()["subscriptions"] == []
  assert client.delete("/devotional-subscriptions/morning-and-evening").status_code == 404


@pytest.mark.parametrize(
  "changes, fragment",
  [
    ({"send_time": "7am"}, "time of day"),
    ({"send_time": "25:00"}, "time of day"),
    ({"zone": "Mars/Olympus"}, "time zone"),
  ],
)
def test_a_bad_time_or_zone_is_refused(changes, fragment):
  sign_up()

  response = subscribe(**changes)

  assert response.status_code == 422 and fragment in response.json()["detail"]
  assert client.get("/devotional-subscriptions").json()["subscriptions"] == []


def test_an_unknown_devotional_is_refused():
  sign_up()

  assert subscribe("no-such-book").status_code == 404
  assert subscribe("Bad Id!").status_code == 404


def test_a_daily_devotional_sends_the_readers_dates_reading_at_their_time(fakes):
  sign_up()
  subscribe(send_time="07:00", zone="America/Chicago")  # created now; its first email is tomorrow's or today's, so reset:
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")

  early = run(utc(2026, 11, 4, 12, 30), fakes)   # 06:30 in Chicago (CST, UTC-6)
  due = run(utc(2026, 11, 4, 13, 5), fakes)      # 07:05 in Chicago

  assert early["sent"] == 0 and due["sent"] == 1
  email = fakes[0]
  assert email["To"] == "ann@subs-test.example" and email["From"] == "site@example.test"
  assert email["Subject"].startswith("Morning and Evening: November 4")
  body = email.get_content()
  assert "MORNING" in body and "EVENING" in body and "?unsubscribe=" in body


def test_it_is_sent_once_a_day_however_often_the_job_runs(fakes):
  sign_up()
  subscribe(send_time="07:00", zone="America/Chicago")
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")

  first = run(utc(2026, 11, 4, 13, 5), fakes)
  again = run(utc(2026, 11, 4, 13, 10), fakes)
  evening = run(utc(2026, 11, 5, 2, 0), fakes)   # still the 4th in Chicago
  next_day = run(utc(2026, 11, 5, 13, 5), fakes)

  assert (first["sent"], again["sent"], evening["sent"], next_day["sent"]) == (1, 0, 0, 1)
  assert fakes[0]["Subject"].startswith("Morning and Evening: November 5")


def test_the_reading_follows_the_visitors_own_date_and_leap_day_works(fakes):
  sign_up()
  subscribe(send_time="07:00", zone="Pacific/Auckland")  # a day ahead of Chicago
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")

  run(utc(2028, 2, 28, 19, 30), fakes)   # 08:30 on 29 February in Auckland (NZDT, UTC+13)

  assert fakes[0]["Subject"].startswith("Morning and Evening: February 29")


def test_subscribing_after_todays_time_waits_for_tomorrow(fakes):
  sign_up()
  # It is 09:00 in Chicago and the visitor asks for 07:00: no email this morning.
  with_now = subscriptions.save_subscription(
    client.get("/account/me").json()["user"]["id"], "morning-and-evening", "07:00", "America/Chicago", now=utc(2026, 11, 4, 15, 0)
  )

  assert with_now["last_sent_on"] == "2026-11-04"
  assert run(utc(2026, 11, 4, 16, 0), fakes)["sent"] == 0
  assert run(utc(2026, 11, 5, 13, 5), fakes)["sent"] == 1


def test_a_devotional_with_chapters_sends_one_in_order_and_stops_after_the_last(fakes):
  sign_up()
  assert subscribe("imitation-of-christ", send_time="07:00", zone="UTC").status_code == 200
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")
    total = connection.execute("SELECT count(DISTINCT (section, unit)) FROM devotional_entries WHERE devotional_id = 'imitation-of-christ'").fetchone()[0]

  first = run(utc(2026, 11, 4, 7, 5), fakes)
  assert first["sent"] == 1 and "Chapter I." in fakes[0]["Subject"]
  second = run(utc(2026, 11, 5, 7, 5), fakes)
  assert second["sent"] == 1 and "Chapter II." in fakes[0]["Subject"]
  assert client.get("/devotional-subscriptions").json()["subscriptions"][0]["next_unit"] == 3
  assert total > 100  # the whole book is there to be sent, a chapter a day


def test_a_chapter_devotional_can_start_at_a_chosen_chapter_and_finishes(fakes):
  sign_up()
  with connect() as connection:
    last = connection.execute("SELECT section, unit FROM devotional_entries WHERE devotional_id = 'imitation-of-christ' ORDER BY section DESC, unit DESC LIMIT 1").fetchone()
  subscribe("imitation-of-christ", send_time="07:00", zone="UTC", start_section=last[0], start_unit=last[1])
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")

  run(utc(2026, 11, 4, 7, 5), fakes)

  assert "last chapter" in fakes[0].get_content()
  assert client.get("/devotional-subscriptions").json()["subscriptions"] == []
  assert subscribe("imitation-of-christ", zone="UTC", start_section=99, start_unit=99).status_code == 422


def test_only_confirmed_addresses_are_sent_to(fakes):
  user_id = sign_up()
  subscribe(send_time="07:00", zone="UTC")
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")
    connection.execute("UPDATE users SET email_verified_at = NULL WHERE id = %s", (user_id,))

  assert run(utc(2026, 11, 4, 7, 5), fakes)["sent"] == 0


def test_every_email_has_a_working_unsubscribe_link(fakes):
  sign_up()
  subscribe(send_time="07:00", zone="UTC")
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")
  run(utc(2026, 11, 4, 7, 5), fakes)
  email = fakes[0]
  token = email["List-Unsubscribe"].split("token=")[1].rstrip(">")

  assert email["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
  assert email["List-Unsubscribe"].startswith("<https://site.example/api/subscriptions/unsubscribe?token=")
  assert f"https://site.example/?unsubscribe={token}" in email.get_content()
  client.cookies.clear()  # no login is needed
  response = client.post("/subscriptions/unsubscribe", params={"token": token})
  assert response.status_code == 200 and response.json() == {"devotional": "Morning and Evening"}
  assert client.post("/subscriptions/unsubscribe", params={"token": token}).status_code == 404
  assert client.post("/subscriptions/unsubscribe", params={"token": "made-up"}).status_code == 404
  assert run(utc(2026, 11, 5, 7, 5), fakes)["sent"] == 0


def test_a_failed_send_is_tried_again_a_few_times_then_given_up_for_the_day(fakes, monkeypatch):
  sign_up()
  subscribe(send_time="07:00", zone="UTC")
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")

  def fail(settings, email):
    raise subscriptions.MailUnavailable("down")

  monkeypatch.setattr(subscriptions, "send_email", fail)
  results = [subscriptions.send_due(utc(2026, 11, 4, 7, 5 + minute), pause=0)["failed"] for minute in range(5)]
  assert results == [1, 1, 1, 0, 0]  # three tries, then none for the rest of the day

  monkeypatch.setattr(subscriptions, "send_email", lambda settings, email: fakes.append(email))
  assert subscriptions.send_due(utc(2026, 11, 5, 7, 5), pause=0)["sent"] == 1  # a fresh day


def test_a_failure_does_not_move_a_chapter_devotional_on(fakes, monkeypatch):
  sign_up()
  subscribe("imitation-of-christ", send_time="07:00", zone="UTC")
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")
  monkeypatch.setattr(subscriptions, "send_email", lambda settings, email: (_ for _ in ()).throw(subscriptions.MailUnavailable("down")))

  subscriptions.send_due(utc(2026, 11, 4, 7, 5), pause=0)

  assert client.get("/devotional-subscriptions").json()["subscriptions"][0]["next_unit"] == 1


def test_one_visitor_never_sees_or_stops_anothers_subscription():
  sign_up("ann")
  subscribe()
  client.cookies.clear()
  sign_up("bob")

  assert client.get("/devotional-subscriptions").json()["subscriptions"] == []
  assert client.delete("/devotional-subscriptions/morning-and-evening").status_code == 404


def test_deleting_the_account_removes_its_subscriptions():
  user_id = sign_up()
  subscribe()

  with connect() as connection:
    connection.execute("DELETE FROM users WHERE id = %s", (user_id,))
    assert connection.execute("SELECT count(*) FROM devotional_subscriptions WHERE user_id = %s", (user_id,)).fetchone()[0] == 0


def test_only_one_run_sends_at_a_time(fakes):
  sign_up("ann")
  subscribe(send_time="07:00", zone="UTC")
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")
    connection.execute("SELECT pg_advisory_lock(%s)", (subscriptions.LOCK_NUMBER,))
    other = subscriptions.send_due(utc(2026, 11, 4, 7, 5), pause=0)
    connection.execute("SELECT pg_advisory_unlock(%s)", (subscriptions.LOCK_NUMBER,))

  assert other["already_running"] is True and fakes == []


def test_a_run_sends_no_more_than_its_limit_and_the_rest_wait_for_the_next(fakes, monkeypatch):
  monkeypatch.setattr(subscriptions, "EMAILS_PER_RUN", 1)
  for name in ("ann", "bob"):
    client.cookies.clear()
    sign_up(name)
    subscribe(send_time="07:00", zone="UTC")
  with connect() as connection:
    connection.execute("UPDATE devotional_subscriptions SET last_sent_on = NULL")

  first = run(utc(2026, 11, 4, 7, 5), fakes)
  second = run(utc(2026, 11, 4, 7, 10), fakes)
  third = run(utc(2026, 11, 4, 7, 15), fakes)

  assert (first["sent"], second["sent"], third["sent"]) == (1, 1, 0)

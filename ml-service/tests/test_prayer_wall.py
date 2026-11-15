"""Tests for the Prayer Wall choices (anonymous, private, email to the prayer list) and the prayer list email. The
mail server is faked: nothing is sent. They use the real tables and remove their own users (and so their posts and
subscriptions) after."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import accounts
import prayer_list
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "prayer-wall-test.example"
client = TestClient(app)
SETTINGS = {"smtp_host": "x", "smtp_port": 25, "from_address": "site@example.test", "to_address": "o@example.test", "subject": "s"}


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
  sent = []
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(prayer_list, "load_mail_settings", lambda: SETTINGS)
  monkeypatch.setattr(prayer_list, "send_email", lambda settings, email: sent.append(email))
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield sent
  clear()


def sign_up(name="ann", allowed=True, verified=True):
  """A new account, logged in (the client keeps its cookie)."""
  client.cookies.clear()
  response = client.post(
    "/account/register",
    json={
      "email": f"{name}@{DOMAIN}",
      "password": PASSWORD,
      "password_confirmation": PASSWORD,
      "first_name": name.title(),
      "last_name": "Test",
    },
  )
  assert response.status_code == 200
  user_id = response.json()["user"]["id"]
  with connect() as connection:
    connection.execute(
      "UPDATE users SET use_conversations = %s, email_verified_at = CASE WHEN %s THEN now() END WHERE id = %s",
      (allowed, verified, user_id),
    )
  return user_id


def log_in(name):
  client.cookies.clear()
  assert client.post("/account/login", json={"email": f"{name}@{DOMAIN}", "password": PASSWORD}).status_code == 200


def post(title, **options):
  response = client.post("/conversations", json={"title": title, "body": "<p>Please pray</p>", "board": "prayer", **options})
  assert response.status_code == 200, response.text
  return response.json()["post"]


def wall(**query):
  return client.get("/conversations", params={"board": "prayer", **query}).json()["posts"]


def titles(posts):
  return [entry["title"] for entry in posts]


def test_an_anonymous_request_hides_the_name_and_is_not_found_by_it():
  sign_up("ann")
  mine = post("Healing for my mother", is_anonymous=True)
  assert mine["author"] == "Anonymous" and mine["is_anonymous"] and mine["is_mine"]

  sign_up("bob")
  seen = wall()
  assert seen[0]["author"] == "Anonymous" and not seen[0]["is_mine"]
  # Searching the author's name must not give them away.
  assert wall(query="Ann") == []
  assert titles(wall(query="mother")) == ["Healing for my mother"]


def test_a_private_request_is_seen_only_by_its_author():
  sign_up("ann")
  private = post("Just between me and God", is_private=True)
  post("For everyone")
  assert titles(wall()) == ["For everyone", "Just between me and God"]

  sign_up("bob")
  assert titles(wall()) == ["For everyone"]
  # Nobody else can reply to it either.
  assert client.post(f"/conversations/{private['id']}/replies", json={"body": "<p>Praying</p>"}).status_code == 404

  client.cookies.clear()
  assert titles(wall()) == ["For everyone"]


def test_a_private_request_is_never_emailed():
  sign_up("ann")
  response = client.post(
    "/conversations",
    json={"title": "Both", "body": "<p>x</p>", "board": "prayer", "is_private": True, "email_to_prayer_list": True},
  )
  assert response.status_code == 422


def test_conversations_posts_cannot_have_the_choices():
  sign_up("ann")
  for option in ("is_anonymous", "is_private", "email_to_prayer_list"):
    response = client.post("/conversations", json={"title": "x", "body": "<p>x</p>", "board": "conversations", option: True})
    assert response.status_code == 422


def test_the_choices_can_be_changed_with_edit():
  sign_up("ann")
  mine = post("Work", is_private=True)
  changed = client.put(
    f"/conversations/{mine['id']}",
    json={"title": "Work", "body": "<p>x</p>", "is_anonymous": True, "email_to_prayer_list": True},
  ).json()["post"]
  assert changed["is_anonymous"] and not changed["is_private"] and changed["email_to_prayer_list"]
  with connect() as connection:
    assert connection.execute("SELECT listed_at IS NOT NULL FROM conversation_posts WHERE id = %s", (mine["id"],)).fetchone()[0]


def test_signing_up_for_the_prayer_list_needs_a_login_and_a_confirmed_address():
  weekly = {"send_weekday": 6, "send_time": "07:00", "timezone": "America/Chicago"}
  client.cookies.clear()
  assert client.get("/prayer-list-subscription").status_code == 401
  sign_up("ann", allowed=False, verified=False)
  assert client.put("/prayer-list-subscription", json=weekly).status_code == 403
  # No invitation (use_conversations) is needed, only a confirmed address.
  sign_up("bob", allowed=False)
  assert client.get("/prayer-list-subscription").json()["subscription"] is None
  assert client.put("/prayer-list-subscription", json={**weekly, "send_weekday": 7}).status_code == 422
  saved = client.put("/prayer-list-subscription", json=weekly).json()["subscription"]
  assert saved["send_weekday"] == 6 and saved["send_time"] == "07:00" and saved["timezone"] == "America/Chicago"
  assert client.get("/prayer-list-subscription").json()["subscription"]["send_weekday"] == 6
  assert client.delete("/prayer-list-subscription").status_code == 200
  assert client.get("/prayer-list-subscription").json()["subscription"] is None
  assert client.delete("/prayer-list-subscription").status_code == 404


def test_only_the_author_marks_a_request_answered_without_editing_it():
  sign_up("ann")
  mine = post("New job", email_to_prayer_list=True)
  answered = client.put(f"/conversations/{mine['id']}/answered", json={"answered": True}).json()["post"]
  assert answered["answered_at"] is not None and answered["title"] == "New job" and answered["email_to_prayer_list"]
  # Editing keeps it answered.
  edited = client.put(f"/conversations/{mine['id']}", json={"title": "New job!", "body": "<p>x</p>", "email_to_prayer_list": True}).json()["post"]
  assert edited["answered_at"] == answered["answered_at"]
  conversation = client.post("/conversations", json={"title": "Chat", "body": "<p>x</p>"}).json()["post"]
  assert client.put(f"/conversations/{conversation['id']}/answered", json={"answered": True}).status_code == 422

  sign_up("bob")
  assert wall()[0]["answered_at"] is not None
  assert client.put(f"/conversations/{mine['id']}/answered", json={"answered": False}).status_code == 404

  log_in("ann")
  assert client.put(f"/conversations/{mine['id']}/answered", json={"answered": False}).json()["post"]["answered_at"] is None


# Friday 1 March 2030, noon UTC: the reader signs up for Saturdays (weekday 5) at 07:00 UTC.
FRIDAY_NOON = datetime(2030, 3, 1, 12, 0, tzinfo=timezone.utc)
SATURDAY = 5


def at(day, hour, minute=0):
  return datetime(2030, 3, day, hour, minute, tzinfo=timezone.utc)


def subscriber(name="ruth"):
  reader = sign_up(name, allowed=False)
  prayer_list.save_subscription(reader, SATURDAY, "07:00", "UTC", now=FRIDAY_NOON)
  return reader


def list_at(post_id, when):
  with connect() as connection:
    connection.execute("UPDATE conversation_posts SET listed_at = %s WHERE id = %s", (when, post_id))


def test_the_email_goes_weekly_on_the_chosen_day_with_the_new_requests(fakes):
  subscriber()
  sign_up("ann")
  emailed = post("Job interview", email_to_prayer_list=True)
  anonymous = post("A hard week", email_to_prayer_list=True, is_anonymous=True)
  kept = post("Not for the list")
  post("Private", is_private=True)
  list_at(emailed["id"], FRIDAY_NOON + timedelta(hours=1))
  list_at(anonymous["id"], FRIDAY_NOON + timedelta(hours=2))

  # Before the time on Saturday: nothing. Then one email with both.
  assert prayer_list.send_due(at(2, 6, 59), pause=0)["sent"] == 0
  assert prayer_list.send_due(at(2, 7, 1), pause=0)["sent"] == 1 and len(fakes) == 1
  text = fakes[0].get_content()
  assert "JOB INTERVIEW" in text and "Ann Test" in text
  assert "A HARD WEEK" in text and "Anonymous" in text and text.count("Ann Test") == 1
  assert "NOT FOR THE LIST" not in text and "PRIVATE" not in text
  assert fakes[0]["Subject"] == "Prayer list: 2 new requests this week"
  assert fakes[0]["List-Unsubscribe"].startswith("<https://site.example/api/subscriptions/unsubscribe?token=")
  assert kept["email_to_prayer_list"] is False

  # Not again that week, on any day.
  for moment in (at(2, 9), at(3, 7, 1), at(6, 7, 1), at(8, 23)):
    assert prayer_list.send_due(moment, pause=0)["sent"] == 0
  # The next Saturday has nothing new: no email.
  assert prayer_list.send_due(at(9, 7, 1), pause=0)["empty"] == 1
  assert len(fakes) == 1


def test_only_the_past_weeks_requests_are_sent(fakes):
  sign_up("ann")
  old = post("Old request", email_to_prayer_list=True)
  recent = post("Recent request", email_to_prayer_list=True)
  list_at(old["id"], at(2, 7) - timedelta(days=10))
  list_at(recent["id"], at(2, 7) - timedelta(days=2))
  # A new subscriber's first email has the past week's requests, from before they signed up too.
  subscriber()
  assert prayer_list.send_due(at(2, 7, 1), pause=0)["sent"] == 1
  text = fakes[0].get_content()
  assert "RECENT REQUEST" in text and "OLD REQUEST" not in text


def test_answered_requests_are_not_emailed(fakes):
  subscriber()
  sign_up("ann")
  done = post("Answered already", email_to_prayer_list=True)
  list_at(done["id"], FRIDAY_NOON + timedelta(hours=1))
  client.put(f"/conversations/{done['id']}/answered", json={"answered": True})
  assert prayer_list.send_due(at(2, 7, 1), pause=0)["empty"] == 1
  assert fakes == []


def test_a_missed_day_is_caught_up_at_the_next_run(fakes):
  subscriber()
  sign_up("ann")
  emailed = post("Travel", email_to_prayer_list=True)
  list_at(emailed["id"], FRIDAY_NOON + timedelta(hours=1))
  # The job did not run on Saturday; on Monday it sends that week's email, once.
  assert prayer_list.send_due(at(4, 8), pause=0)["sent"] == 1
  assert prayer_list.send_due(at(4, 9), pause=0)["sent"] == 0


def test_a_failed_send_keeps_the_requests_for_the_next_try(fakes, monkeypatch):
  subscriber()
  sign_up("ann")
  emailed = post("Travel", email_to_prayer_list=True)
  list_at(emailed["id"], FRIDAY_NOON + timedelta(hours=1))

  monkeypatch.setattr(prayer_list, "send_email", lambda settings, email: (_ for _ in ()).throw(prayer_list.MailUnavailable("down")))
  assert prayer_list.send_due(at(2, 7, 1), pause=0)["failed"] == 1
  monkeypatch.setattr(prayer_list, "send_email", lambda settings, email: fakes.append(email))
  assert prayer_list.send_due(at(2, 7, 6), pause=0)["sent"] == 1
  assert "TRAVEL" in fakes[0].get_content()


def test_the_unsubscribe_link_stops_the_prayer_list(fakes):
  reader = subscriber()
  with connect() as connection:
    token = connection.execute("SELECT unsubscribe_token FROM prayer_list_subscriptions WHERE user_id = %s", (reader,)).fetchone()[0]
  response = client.post("/subscriptions/unsubscribe", params={"token": token})
  assert response.status_code == 200 and response.json()["devotional"] == "the Prayer Wall prayer list"
  assert prayer_list.get_subscription(reader) is None


def test_private_requests_go_only_to_subscribers_marked_as_administrators(fakes):
  subscriber("ruth")
  admin = subscriber("owner")
  with connect() as connection:
    connection.execute("UPDATE users SET see_private_prayers = true WHERE id = %s", (admin,))
  sign_up("ann")
  shared = post("For everyone", email_to_prayer_list=True)
  private = post("Just for the owner", is_private=True)
  done = post("Private and answered", is_private=True)
  for entry in (shared, private, done):
    list_at(entry["id"], FRIDAY_NOON + timedelta(hours=1))
  client.put(f"/conversations/{done['id']}/answered", json={"answered": True})

  assert prayer_list.send_due(at(2, 7, 1), pause=0)["sent"] == 2
  by_address = {email["To"]: email.get_content() for email in fakes}
  ordinary = by_address[f"ruth@{DOMAIN}"]
  owner = by_address[f"owner@{DOMAIN}"]
  assert "FOR EVERYONE" in ordinary and "JUST FOR THE OWNER" not in ordinary
  assert "FOR EVERYONE" in owner and "JUST FOR THE OWNER" in owner and "PRIVATE: sent only to the site's administrators" in owner
  assert "PRIVATE AND ANSWERED" not in owner


def test_making_a_request_private_puts_it_in_the_administrators_next_email():
  sign_up("ann")
  mine = post("Later private")
  with connect() as connection:
    assert connection.execute("SELECT listed_at FROM conversation_posts WHERE id = %s", (mine["id"],)).fetchone()[0] is None
  client.put(f"/conversations/{mine['id']}", json={"title": "Later private", "body": "<p>x</p>", "is_private": True})
  with connect() as connection:
    assert connection.execute("SELECT listed_at FROM conversation_posts WHERE id = %s", (mine["id"],)).fetchone()[0] is not None


def test_the_site_users_tool_sets_the_private_prayers_flag():
  import site_users

  user = site_users.create_user(f"admin@{DOMAIN}", PASSWORD, True, False, see_private_prayers=True)
  assert user["see_private_prayers"] is True
  assert site_users.update_user(user["id"], see_private_prayers=False)["see_private_prayers"] is False

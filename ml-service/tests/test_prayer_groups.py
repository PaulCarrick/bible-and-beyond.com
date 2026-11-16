"""Tests for Prayer Wall requests emailed to a group or its leader (conversations.py, groups.send_prayer_request).
Mail and Telnyx are faked: nothing is sent. They use the real tables with their own accounts and groups, and
remove them after."""

import pytest
from fastapi.testclient import TestClient

import accounts
import conversations
import groups
import sms
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "prayer-groups-test.example"
OWNER = 990201
client = TestClient(app)


@pytest.fixture(autouse=True)
def outbox(monkeypatch):
  sent = []
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(sms, "is_configured", lambda: False)
  monkeypatch.setattr(groups, "load_mail_settings", lambda: {"from_address": "site@example.test"})

  def fake_send(settings, email, recipients=None):
    email["X-Delivered-To"] = ", ".join(recipients or [])
    sent.append(email)

  monkeypatch.setattr(groups, "send_email", fake_send)
  monkeypatch.setattr(groups, "PAUSE_BETWEEN_MEMBERS", 0)
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM member_groups WHERE owner_uid = %s", (OWNER,))
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield sent
  clear()


def member(name):
  client.cookies.clear()
  user = client.post(
    "/account/register",
    json={"email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD, "first_name": name.title(), "last_name": "Prayer"},
  ).json()["user"]
  with connect() as connection:
    connection.execute("UPDATE users SET email_verified_at = now(), use_conversations = true WHERE id = %s", (user["id"],))
  return user


def family():
  """A group with Ann (who will post), Bob and a contact, Pat."""
  group = groups.save_group(None, {"name": "Carrick family"}, OWNER, "Deacon Paul", "paul@example.org")
  ann, bob = member("ann"), member("bob")
  groups.add_accounts(group["id"], [ann["id"], bob["id"]])
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  return group, ann, bob


def log_in(name):
  client.cookies.clear()
  assert client.post("/account/login", json={"email": f"{name}@{DOMAIN}", "password": PASSWORD}).status_code == 200


def post(**options):
  answer = client.post("/conversations", json={"title": "Surgery Friday", "body": "<p>Please pray for Mom.</p>", "board": "prayer", **options})
  return answer


def test_a_member_sees_their_groups():
  group, ann, bob = family()
  log_in("ann")
  assert client.get("/my-groups").json() == {"groups": [{"id": group["id"], "name": "Carrick family"}]}
  client.cookies.clear()
  assert client.get("/my-groups").status_code == 401


def test_email_the_group_sends_at_once_makes_it_private_and_skips_the_author(outbox):
  group, ann, bob = family()
  log_in("ann")
  answer = post(share_with="group", share_group_id=group["id"], is_anonymous=True)
  assert answer.status_code == 200, answer.text
  saved = answer.json()["post"]
  assert saved["is_private"] and not saved["is_anonymous"] and saved["share_with"] == "group" and saved["share_group_name"] == "Carrick family"
  delivered = [email["X-Delivered-To"] for email in outbox]
  # Bob and Pat (never Ann, who wrote it), then the leader's copy.
  assert sorted(delivered[:2]) == sorted([f"bob@{DOMAIN}", "pat@example.org"]) and delivered[2] == "paul@example.org"
  email = outbox[0]
  assert email["Subject"] == "Prayer request from Ann Prayer: Surgery Friday" and email["Reply-To"] == f"ann@{DOMAIN}"
  assert email["To"] == "paul@example.org" and "Please pray for Mom." in email.get_content()
  assert "To stop messages from this group" in email.get_content()
  # Private on the Prayer Wall: Bob does not see it there.
  log_in("bob")
  titles = [each["title"] for each in client.get("/conversations", params={"board": "prayer"}).json()["posts"]]
  assert "Surgery Friday" not in titles
  # Recorded with the subject only.
  record = groups.list_sent(group["id"])[0]
  assert record["subject"].startswith("Prayer request from Ann Prayer") and record["text"] == "" and record["emailed"] == 2


def test_email_the_leader_goes_to_the_leader_only(outbox):
  group, ann, bob = family()
  log_in("ann")
  saved = post(share_with="leader", share_group_id=group["id"]).json()["post"]
  assert saved["is_private"] and saved["share_with"] == "leader"
  assert [email["X-Delivered-To"] for email in outbox] == ["paul@example.org"]
  assert "to you, the leader of “Carrick family”" in outbox[0].get_content()


def test_saving_again_does_not_send_again_but_another_choice_does(outbox):
  group, ann, bob = family()
  log_in("ann")
  saved = post(share_with="leader", share_group_id=group["id"]).json()["post"]
  outbox.clear()
  edit = {"title": "Surgery Friday", "body": "<p>Update: it went well.</p>", "share_with": "leader", "share_group_id": group["id"]}
  assert client.put(f"/conversations/{saved['id']}", json=edit).status_code == 200
  assert outbox == []
  assert client.put(f"/conversations/{saved['id']}", json={**edit, "share_with": "group"}).status_code == 200
  assert len(outbox) == 3
  # Back to Public: no longer private or shared.
  public = client.put(f"/conversations/{saved['id']}", json={"title": "Surgery Friday", "body": "<p>x</p>"}).json()["post"]
  assert not public["is_private"] and public["share_with"] is None


def test_only_ones_own_group_and_only_on_the_prayer_wall():
  group, ann, bob = family()
  other = groups.save_group(None, {"name": "Other"}, OWNER, "Deacon Paul", "paul@example.org")
  log_in("ann")
  answer = post(share_with="group", share_group_id=other["id"])
  assert answer.status_code == 422 and "not in that group" in answer.json()["detail"]
  answer = client.post("/conversations", json={"title": "x", "body": "<p>x</p>", "board": "conversations", "share_with": "group", "share_group_id": group["id"]})
  assert answer.status_code == 422
  assert post(share_with="everyone", share_group_id=group["id"]).status_code == 422


def test_the_other_choices_are_as_before():
  group, ann, bob = family()
  log_in("ann")
  anonymous = post(is_anonymous=True).json()["post"]
  assert anonymous["author"] == "Anonymous" and not anonymous["is_private"] and anonymous["share_with"] is None
  listed = post(email_to_prayer_list=True).json()["post"]
  assert listed["email_to_prayer_list"] and not listed["is_private"]
  assert conversations.share_is_due(listed["id"]) is False

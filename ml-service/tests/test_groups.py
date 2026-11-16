"""Tests for Groups (groups.py, scripts/manage_groups.py). Mail and Telnyx are faked: nothing is sent. They use
the real tables with their own accounts and groups (owner 990001), temporary folders (conftest.py), and remove
their rows after."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import accounts
import groups
import sms
from groups import GroupProblem
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "groups-test.example"
OWNER = 990001
TOOL = Path(__file__).resolve().parent.parent / "scripts" / "manage_groups.py"
client = TestClient(app)


@pytest.fixture(autouse=True)
def outbox(monkeypatch):
  sent = {"emails": [], "texts": []}
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(sms, "is_configured", lambda: True)
  monkeypatch.setattr(sms, "send_text", lambda number, text, media_url=None: sent["texts"].append((number, text, media_url)) or True)
  monkeypatch.setattr(groups, "load_mail_settings", lambda: {"from_address": "site@example.test"})
  # Each email with who it is really delivered to (its hidden recipients), kept as X-Delivered-To for the tests.
  def fake_send(settings, email, recipients=None):
    email["X-Delivered-To"] = ", ".join(recipients or [])
    sent["emails"].append(email)

  monkeypatch.setattr(groups, "send_email", fake_send)
  monkeypatch.setenv("SITE_URL", "https://site.example")

  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM member_groups WHERE owner_uid IN (%s, %s)", (OWNER, OWNER + 1))
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  yield sent
  clear()


def account(name, verified=True, texts=False):
  client.cookies.clear()
  extra = {"phone": "555 234 5678", "phone_is_cell": True, "send_via_sms": True} if texts else {}
  user = client.post(
    "/account/register",
    json={"email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD, "first_name": name.title(), "last_name": "Member", **extra},
  ).json()["user"]
  if verified:
    with connect() as connection:
      connection.execute("UPDATE users SET email_verified_at = now() WHERE id = %s", (user["id"],))
  return user


def new_group(name="Deacon group", owner=OWNER):
  return groups.save_group(None, {"name": name, "description": "Our care group"}, owner, "Deacon Dave", "dave@example.org")


def test_groups_belong_to_their_leader():
  mine = new_group("Mine")
  new_group("Someone else's", owner=OWNER + 1)
  assert [group["name"] for group in groups.list_groups(OWNER)] == ["Mine"]
  assert {"Mine", "Someone else's"} <= {group["name"] for group in groups.list_groups()}
  renamed = groups.save_group(mine["id"], {"name": "  Care   group ", "description": ""}, OWNER, "Deacon Dave", "dave@example.org")
  assert renamed["name"] == "Care group"
  with pytest.raises(GroupProblem, match="name"):
    groups.save_group(None, {"name": " "}, OWNER, "", "")


def test_an_administrator_can_give_a_group_another_leader():
  group = new_group("Care list")
  # A plain save keeps the leader (the names given are those Drupal sends: the leader's own).
  kept = groups.save_group(group["id"], {"name": "Care list"}, OWNER, "Deacon Dave", "dave@example.org")
  assert (kept["owner_uid"], kept["owner_email"]) == (OWNER, "dave@example.org")
  moved = groups.save_group(group["id"], {"name": "Care list"}, OWNER + 1, "Deacon Danne", "danne@example.org", set_owner=True)
  assert (moved["owner_uid"], moved["owner_name"], moved["owner_email"]) == (OWNER + 1, "Deacon Danne", "danne@example.org")
  assert [each["id"] for each in groups.list_groups(OWNER + 1)] == [group["id"]] and groups.list_groups(OWNER) == []


def test_members_are_accounts_by_address_or_contacts_by_name():
  group = new_group()
  ann = account("ann", texts=True)
  member = groups.add_member(group["id"], {"email": f"ANN@{DOMAIN}"})
  assert member["is_account"] and member["name"] == "Ann Member" and member["receives"] == "Email and text"
  contact = groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat Example", "phone": "5552345678"})
  assert not contact["is_account"] and contact["phone"] == "+1 (555) 234-5678" and contact["receives"] == "Email"
  with pytest.raises(GroupProblem, match="already"):
    groups.add_member(group["id"], {"email": f"ann@{DOMAIN}"})
  with pytest.raises(GroupProblem, match="type the person's name"):
    groups.add_member(group["id"], {"email": "nobody@example.org"})
  with pytest.raises(GroupProblem, match="valid email"):
    groups.add_member(group["id"], {"email": "not an address", "name": "X"})
  changed = groups.update_member(group["id"], contact["id"], {"email": "pat2@example.org", "name": "Pat E.", "phone": ""})
  assert (changed["email"], changed["name"]) == ("pat2@example.org", "Pat E.")
  with pytest.raises(GroupProblem, match="their own details"):
    groups.update_member(group["id"], member["id"], {"email": "x@example.org", "name": "X"})
  groups.remove_member(group["id"], contact["id"])
  assert [each["name"] for each in groups.get_group(group["id"])["members"]] == ["Ann Member"]
  assert ann["id"]


def test_site_accounts_are_listed_and_added_several_at_once():
  group = new_group()
  ann, bob, cat = account("ann"), account("bob"), account("cat", verified=False)
  candidates = {each["email"]: each for each in groups.list_candidates(group["id"])}
  assert {f"ann@{DOMAIN}", f"bob@{DOMAIN}", f"cat@{DOMAIN}"} <= set(candidates)
  assert candidates[f"ann@{DOMAIN}"]["name"] == "Ann Member" and candidates[f"cat@{DOMAIN}"]["confirmed"] is False
  added = groups.add_accounts(group["id"], [ann["id"], str(bob["id"]), ann["id"]])
  assert sorted(member["name"] for member in added) == ["Ann Member", "Bob Member"] and all(member["is_account"] for member in added)
  # Those in the group are no longer listed, and adding one again does nothing.
  remaining = {each["email"] for each in groups.list_candidates(group["id"])}
  assert f"ann@{DOMAIN}" not in remaining and f"cat@{DOMAIN}" in remaining
  assert groups.add_accounts(group["id"], [ann["id"]]) == []
  with pytest.raises(GroupProblem, match="tick"):
    groups.add_accounts(group["id"], [])
  assert groups.add_accounts(group["id"], [987654321]) == []  # no such account
  assert cat["id"]


def test_a_message_goes_by_each_members_choice(outbox):
  group = new_group()
  account("ann", texts=True)  # email and text
  account("bob")  # email
  account("cat", verified=False)  # nothing until confirmed
  groups.add_member(group["id"], {"email": f"ann@{DOMAIN}"})
  groups.add_member(group["id"], {"email": f"bob@{DOMAIN}"})
  groups.add_member(group["id"], {"email": f"cat@{DOMAIN}"})
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})  # a contact: email
  outbox["texts"].clear()
  counts = groups.send(group["id"], "message", {"subject": "Potluck Sunday", "text": "Bring a dish."}, "dave", pause=0)
  assert counts == {"emailed": 3, "texted": 1, "skipped": 1, "failed": 0}
  delivered = [email["X-Delivered-To"] for email in outbox["emails"]]
  # Each member as a hidden recipient of their own copy, then one copy for the leader.
  assert sorted(delivered[:3]) == sorted([f"ann@{DOMAIN}", f"bob@{DOMAIN}", "pat@example.org"]) and delivered[3] == "dave@example.org"
  email = outbox["emails"][0]
  assert email["Subject"] == "Potluck Sunday" and email["Reply-To"] == "dave@example.org"
  # The To shows the leader; no member's address is anywhere in any email (headers or text) but the delivery.
  for each in outbox["emails"]:
    assert each["To"] == "dave@example.org" and each["Bcc"] is None and each["Cc"] is None
    shown = each.as_string().replace(f"X-Delivered-To: {each['X-Delivered-To']}", "")
    assert DOMAIN not in shown and "pat@example.org" not in shown
  leader_copy = outbox["emails"][3].get_content()
  assert "your copy as the group's leader: it went to 3 members" in leader_copy and "To stop messages" not in leader_copy
  assert "Bring a dish." in email.get_content() and "To stop messages from this group" in email.get_content()
  assert not email.is_multipart()  # no picture
  assert outbox["texts"][0][0] == "+15552345678" and "Bring a dish." in outbox["texts"][0][1] and outbox["texts"][0][2] is None
  assert groups.list_sent(group["id"])[0]["emailed"] == 3


def test_the_stop_link_stops_only_that_group(outbox):
  first, second = new_group("First"), new_group("Second")
  groups.add_member(first["id"], {"email": "pat@example.org", "name": "Pat"})
  groups.add_member(second["id"], {"email": "pat@example.org", "name": "Pat"})
  groups.send(first["id"], "message", {"subject": "Hello", "text": "Hi"}, "dave", pause=0)
  token = outbox["emails"][0]["List-Unsubscribe"].split("token=")[1].rstrip(">")
  answer = client.post(f"/subscriptions/unsubscribe?token={token}")
  assert answer.status_code == 200 and "First" in json.dumps(answer.json())
  outbox["emails"].clear()
  assert groups.send(first["id"], "message", {"subject": "Again", "text": "Hi"}, "dave", pause=0)["skipped"] == 1
  assert groups.send(second["id"], "message", {"subject": "Again", "text": "Hi"}, "dave", pause=0)["emailed"] == 1
  assert groups.get_group(first["id"])["members"][0]["stopped"] is True


def test_a_verse_card_is_sent_as_previewed_with_the_verse_a_link(outbox):
  group = new_group()
  account("ann", texts=True)
  groups.add_member(group["id"], {"email": f"ann@{DOMAIN}"})
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  preview = groups.preview_verse()
  assert preview["image"].startswith("data:image/jpeg;base64,") and preview["caption"].endswith("(BSB)")
  outbox["texts"].clear()
  counts = groups.send(group["id"], "verse", {"card": preview["card"], "verse": preview["verse"]}, "dave", pause=0)
  assert counts["emailed"] == 2 and counts["texted"] == 1
  email = outbox["emails"][0]
  assert email["Subject"].startswith("A verse for Deacon group: ")
  html = email.get_body(("html",)).get_content()
  assert "cid:" in html and '<a href="https://site.example/?read=BSB&amp;book=' in html
  assert [part for part in email.walk() if part.get_content_type() == "image/jpeg"]
  assert outbox["texts"][0][2].endswith(preview["card"])  # the same picture as an MMS


def test_a_picture_message_has_the_leaders_words_on_a_random_picture(outbox):
  group = new_group()
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  preview = groups.preview_picture("Praying for you all this week.")
  counts = groups.send(group["id"], "picture", {"subject": "This week", "text": "Praying for you all this week.", "card": preview["card"]}, "dave", pause=0)
  assert counts["emailed"] == 1
  email = outbox["emails"][0]
  assert [part for part in email.walk() if part.get_content_type() == "image/jpeg"]
  with pytest.raises(GroupProblem, match="at most"):
    groups.preview_picture("word " * 200)
  with pytest.raises(GroupProblem, match="make the preview again"):
    groups.send(group["id"], "picture", {"subject": "x", "text": "y", "card": "gone.jpg"}, "dave", pause=0)


def test_one_failure_does_not_stop_the_others(outbox, monkeypatch):
  group = new_group()
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  groups.add_member(group["id"], {"email": "sam@example.org", "name": "Sam"})

  def flaky(settings, email, recipients=None):
    if recipients == ["pat@example.org"]:
      raise groups.MailUnavailable("down")
    outbox["emails"].append(email)

  monkeypatch.setattr(groups, "send_email", flaky)
  assert groups.send(group["id"], "message", {"subject": "Hi", "text": "Hello"}, "dave", pause=0) == {"emailed": 1, "texted": 0, "skipped": 0, "failed": 1}


def test_deleting_a_group_keeps_the_accounts():
  group = new_group()
  ann = account("ann")
  groups.add_member(group["id"], {"email": f"ann@{DOMAIN}"})
  groups.delete_group(group["id"])
  with pytest.raises(GroupProblem, match="does not exist"):
    groups.get_group(group["id"])
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM users WHERE id = %s", (ann["id"],)).fetchone()[0] == 1


def test_the_tool():
  def run(*arguments, details=None):
    done = subprocess.run(
      [sys.executable, str(TOOL), *arguments], input=json.dumps(details) if details else "", capture_output=True, text=True, env={**os.environ}
    )
    return done.returncode, json.loads(done.stdout)

  code, answer = run("save", f"--owner={OWNER}", details={"name": "Tool group", "owner_name": "Dave", "owner_email": "dave@example.org"})
  group_id = answer["group"]["id"]
  code, answer = run("add-member", f"--group={group_id}", details={"email": "pat@example.org", "name": "Pat"})
  assert code == 0 and answer["member"]["receives"] == "Email"
  code, answer = run("get", f"--group={group_id}")
  assert answer["group"]["members"][0]["name"] == "Pat" and answer["group"]["sent"] == []
  code, answer = run("list", f"--owner={OWNER}")
  assert [group["member_count"] for group in answer["groups"]] == [1]
  code, answer = run("add-member", f"--group={group_id}", details={"email": "pat@example.org", "name": "Pat"})
  assert code == 1 and answer == {"ok": False, "error": "That person is already in the group."}

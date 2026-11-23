"""Tests for Groups (groups.py, scripts/manage_groups.py). Mail and Telnyx are faked: nothing is sent. They use
the real tables with their own accounts and groups (owner 990001), temporary folders (conftest.py), and remove
their rows after."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import accounts
import group_schedules
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
    # Without hidden recipients an email goes to its To (an email to one member, since 2026-11-18).
    email["X-Delivered-To"] = ", ".join(recipients or [email["To"]])
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


def test_one_member_can_be_emailed_alone(outbox):
  group = new_group()
  bob = account("bob")
  account("ann", texts=True)
  account("cat", verified=False)
  for name in ("ann", "bob", "cat"):
    groups.add_member(group["id"], {"email": f"{name}@{DOMAIN}"})
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  members = {member["email"]: member for member in groups.get_group(group["id"])["members"]}
  # The list gives the account's id (for the Site users link) and whether the address is confirmed.
  assert members[f"bob@{DOMAIN}"]["user_id"] == bob["id"] and members["pat@example.org"]["user_id"] is None
  assert members[f"cat@{DOMAIN}"]["confirmed"] is False and members["pat@example.org"]["confirmed"] is True
  outbox["texts"].clear()

  answer = groups.email_member(group["id"], members[f"bob@{DOMAIN}"]["id"], "  Hello Bob,\r\nsee you Sunday.  ", "dave")
  assert answer == {"id": members[f"bob@{DOMAIN}"]["id"], "name": "Bob Member"}
  # One email, delivered to Bob alone: no other member, no leader's copy, no text (even to Ann, who takes texts).
  assert [email["X-Delivered-To"] for email in outbox["emails"]] == [f"bob@{DOMAIN}"] and outbox["texts"] == []
  email = outbox["emails"][0]
  # To one member openly: their address is the To (no hidden recipients); replies go to the leader.
  assert email["To"] == f"bob@{DOMAIN}" and email["Reply-To"] == "dave@example.org" and email["Bcc"] is None
  assert email["Subject"] == "A message from Deacon Dave (Deacon group)"
  text = email.get_content()
  # Not a group email (the owner's request, 2026-11-18): the leader's words only, no foot, no stop link.
  assert text == "Hello Bob,\nsee you Sunday.\n"
  assert email["List-Unsubscribe"] is None and "unsubscribe" not in email.as_string() and "Sent by" not in email.as_string()
  # No other member's address is in it.
  assert f"ann@{DOMAIN}" not in email.as_string() and f"cat@{DOMAIN}" not in email.as_string()
  sent = groups.list_sent(group["id"])[0]
  assert sent["subject"].endswith("(to one member)") and sent["emailed"] == 1 and "bob" not in sent["subject"].lower()

  # A contact gets it too; the words are plain text, sent as typed (nothing in them is markup).
  outbox["emails"].clear()
  groups.email_member(group["id"], members["pat@example.org"]["id"], "<b>Hi</b> & welcome", "dave")
  assert outbox["emails"][0]["X-Delivered-To"] == "pat@example.org" and not outbox["emails"][0].is_multipart()
  assert "<b>Hi</b> & welcome" in outbox["emails"][0].get_content()

  # Refused: an unconfirmed address, a stopped member, an empty message, a member of another group.
  outbox["emails"].clear()
  with pytest.raises(GroupProblem, match="not confirmed"):
    groups.email_member(group["id"], members[f"cat@{DOMAIN}"]["id"], "Hi", "dave")
  with connect() as connection:
    connection.execute("UPDATE group_members SET stopped_at = now() WHERE id = %s", (members["pat@example.org"]["id"],))
  with pytest.raises(GroupProblem, match="stopped"):
    groups.email_member(group["id"], members["pat@example.org"]["id"], "Hi", "dave")
  with pytest.raises(GroupProblem, match="message is needed"):
    groups.email_member(group["id"], members[f"bob@{DOMAIN}"]["id"], "   ", "dave")
  other = new_group("Other")
  with pytest.raises(GroupProblem, match="not in the group"):
    groups.email_member(other["id"], members[f"bob@{DOMAIN}"]["id"], "Hi", "dave")
  assert outbox["emails"] == []


def test_a_member_email_from_the_editor_is_cleaned_html_with_a_text_copy(outbox):
  group = new_group()
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  member_id = groups.get_group(group["id"])["members"][0]["id"]
  html = (
    '<h2>Sunday</h2><p>Hi <strong>Pat</strong>, <s>old</s> see <a href="https://site.example/x" onclick="evil()">this</a>'
    ' and <a href="javascript:alert(1)">that</a>.</p><script>alert(1)</script><ul><li>One</li></ul>'
    '<p style="color:red"><img src="https://tracker.example/p.gif">Bye</p>'
  )
  groups.email_member(group["id"], member_id, "", "dave", html=html)
  email = outbox["emails"][0]
  assert email["X-Delivered-To"] == "pat@example.org" and email.is_multipart()
  plain = email.get_body(("plain",)).get_content()
  sent_html = email.get_body(("html",)).get_content()
  assert "Hi Pat, old see this and that." in plain and "To stop messages" not in plain and "Sent by" not in plain
  # Kept: the editor's formatting and the safe link. Dropped: the script, the handler, the javascript: link,
  # the style and the picture.
  assert "<h2>Sunday</h2>" in sent_html and "<strong>Pat</strong>" in sent_html and "<s>old</s>" in sent_html
  assert re.search(r'<a href="https://site\.example/x"[^>]*>this</a>', sent_html) and "<li>One</li>" in sent_html
  assert ">that</a>" not in sent_html and " and that." in sent_html
  for gone in ("script", "onclick", "javascript:", "style=", "<img", "tracker.example"):
    assert gone not in sent_html
  assert "Sent by" not in sent_html and "unsubscribe" not in sent_html and "<hr>" not in sent_html
  assert groups.list_sent(group["id"])[0]["text"].startswith("Sunday")
  with pytest.raises(GroupProblem, match="write something"):
    groups.email_member(group["id"], member_id, "", "dave", html="<p> </p><img src='x'>")


def test_a_member_email_has_the_subject_typed_in_the_box(outbox):
  group = new_group()
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  member_id = groups.get_group(group["id"])["members"][0]["id"]
  groups.email_member(group["id"], member_id, "See you at 7.", "dave", subject="  Bible study   tonight ")
  email = outbox["emails"][0]
  assert email["Subject"] == "Bible study tonight" and email["To"] == "pat@example.org"
  assert groups.list_sent(group["id"])[0]["subject"] == "Bible study tonight (to one member)"
  # Left empty, it has the subject it always had; a subject on two lines is refused.
  outbox["emails"].clear()
  groups.email_member(group["id"], member_id, "Hi", "dave", subject="")
  assert outbox["emails"][0]["Subject"] == "A message from Deacon Dave (Deacon group)"
  with pytest.raises(GroupProblem, match="subject"):
    groups.email_member(group["id"], member_id, "Hi", "dave", subject="Line one\x07")


def test_emailing_a_member_says_so_when_mail_is_off(outbox, monkeypatch):
  import contact

  group = new_group()
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  member_id = groups.get_group(group["id"])["members"][0]["id"]
  monkeypatch.setattr(groups, "load_mail_settings", contact.load_mail_settings)
  monkeypatch.setenv("OUTGOING_EMAIL", "off")
  with pytest.raises(GroupProblem, match="OUTGOING_EMAIL=off"):
    groups.email_member(group["id"], member_id, "Hi", "dave")
  assert outbox["emails"] == [] and groups.list_sent(group["id"]) == []


def test_a_closed_account_gets_nothing_from_its_groups(outbox):
  group = new_group()
  ann = account("ann", texts=True)
  account("bob")
  groups.add_member(group["id"], {"email": f"ann@{DOMAIN}"})
  groups.add_member(group["id"], {"email": f"bob@{DOMAIN}"})
  with connect() as connection:
    connection.execute("UPDATE users SET disabled_at = now() WHERE id = %s", (ann["id"],))
  ann_member = next(member for member in groups.get_group(group["id"])["members"] if member["email"] == f"ann@{DOMAIN}")
  assert ann_member["closed"] is True and ann_member["confirmed"] is False and ann_member["receives"] == "Nothing: they closed their account"
  outbox["texts"].clear()
  counts = groups.send(group["id"], "message", {"subject": "Hello", "text": "Hi"}, "dave", pause=0)
  assert counts == {"emailed": 1, "texted": 0, "skipped": 1, "failed": 0} and outbox["texts"] == []
  assert f"ann@{DOMAIN}" not in [email["X-Delivered-To"] for email in outbox["emails"]]
  with pytest.raises(GroupProblem, match="closed their account"):
    groups.email_member(group["id"], ann_member["id"], "Hi", "dave")
  # Not offered when adding people.
  other = new_group("Other")
  assert f"ann@{DOMAIN}" not in [candidate["email"] for candidate in groups.list_candidates(other["id"])]


def test_a_message_from_the_editor_is_sent_formatted_with_the_words_in_texts(outbox):
  group = new_group()
  account("ann", texts=True)
  groups.add_member(group["id"], {"email": f"ann@{DOMAIN}"})
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  outbox["texts"].clear()
  html = '<p>Potluck <strong>Sunday</strong></p><ul><li>Bring a dish</li></ul><script>alert(1)</script><p onclick="x()">See <a href="https://site.example/x">this</a></p>'
  counts = groups.send(group["id"], "message", {"subject": "Potluck", "html": html}, "dave", pause=0)
  assert counts["emailed"] == 2 and counts["texted"] == 1
  member = next(email for email in outbox["emails"] if email["X-Delivered-To"] == "pat@example.org")
  sent_html = member.get_body(("html",)).get_content()
  assert "<strong>Sunday</strong>" in sent_html and "<li>Bring a dish</li>" in sent_html and "https://site.example/x" in sent_html
  assert "script" not in sent_html and "onclick" not in sent_html
  assert "To stop messages from this group" in sent_html and "?unsubscribe=" in sent_html
  plain = member.get_body(("plain",)).get_content()
  assert "Potluck Sunday" in plain and "Bring a dish" in plain and "<" not in plain.split("--")[0]
  # The text has the words, never the markup.
  assert "Potluck Sunday" in outbox["texts"][0][1] and "<" not in outbox["texts"][0][1]
  # The leader's copy is formatted too; the Sent table keeps the words.
  leader = next(email for email in outbox["emails"] if email["X-Delivered-To"] == "dave@example.org")
  assert "<strong>Sunday</strong>" in leader.get_body(("html",)).get_content()
  assert groups.list_sent(group["id"])[0]["text"].startswith("Potluck Sunday")
  with pytest.raises(GroupProblem, match="write something"):
    groups.send(group["id"], "message", {"subject": "Empty", "html": "<p> </p>"}, "dave", pause=0)


def test_group_notes_from_the_editor_are_cleaned():
  group = groups.save_group(None, {"name": "Notes", "description_html": '<p>Call <em>Pat</em></p><img src="x"><script>alert(1)</script>'}, OWNER, "Dave", "dave@example.org")
  assert group["description"] == "<p>Call <em>Pat</em></p>"
  emptied = groups.save_group(group["id"], {"name": "Notes", "description_html": "<p></p>"}, OWNER, "Dave", "dave@example.org")
  assert emptied["description"] == ""
  plain = groups.save_group(group["id"], {"name": "Notes", "description": "Plain notes"}, OWNER, "Dave", "dave@example.org")
  assert plain["description"] == "Plain notes"


def test_a_member_who_logs_in_with_a_phone_gets_texts_and_never_email(outbox):
  group = new_group()
  client.cookies.clear()
  user = client.post(
    "/account/register",
    json={"email": "", "password": PASSWORD, "password_confirmation": PASSWORD, "first_name": "Pho", "last_name": "Ne",
          "phone": "555 234 6666", "send_via_sms": True},
  ).json()["user"]
  try:
    candidates = groups.list_candidates(group["id"])
    assert any(candidate["id"] == user["id"] and candidate["email"] == "+1 (555) 234-6666" for candidate in candidates)
    groups.add_accounts(group["id"], [user["id"]])
    member = groups.get_group(group["id"])["members"][0]
    # Not confirmed yet: nothing; then texts only.
    assert member["email"] == "" and member["receives"] == "Nothing until they confirm their email address or phone number"
    with connect() as connection:
      connection.execute("UPDATE users SET phone_verified_at = now() WHERE id = %s", (user["id"],))
    assert groups.get_group(group["id"])["members"][0]["receives"] == "Text"
    outbox["texts"].clear()
    counts = groups.send(group["id"], "message", {"subject": "Hello", "text": "Hi"}, "dave", pause=0)
    assert counts == {"emailed": 0, "texted": 1, "skipped": 0, "failed": 0}
    assert outbox["texts"][0][0] == "+15552346666" and [email["X-Delivered-To"] for email in outbox["emails"]] == ["dave@example.org"]
    with pytest.raises(GroupProblem, match="no email address"):
      groups.email_member(group["id"], member["id"], "Hi", "dave")
  finally:
    with connect() as connection:
      connection.execute("DELETE FROM users WHERE id = %s", (user["id"],))


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
  # email-member (in a separate process, so mail is off there: it is refused, and says why).
  member_id = run("get", f"--group={group_id}")[1]["group"]["members"][0]["id"]
  code, answer = run("email-member", f"--group={group_id}", f"--member={member_id}", details={"text": "", "sent_by": "dave"})
  assert code == 1 and answer == {"ok": False, "error": "The message is needed."}
  done = subprocess.run(
    [sys.executable, str(TOOL), "email-member", f"--group={group_id}", f"--member={member_id}"],
    input=json.dumps({"text": "Hi", "sent_by": "dave"}), capture_output=True, text=True, env={**os.environ, "OUTGOING_EMAIL": "off"},
  )
  assert done.returncode == 1 and "OUTGOING_EMAIL=off" in json.loads(done.stdout)["error"]
  # sent-copy: the copy kept of a sent email (sent here, where mail is faked); none for a message without one.
  groups.send(group_id, "message", {"subject": "Hello", "text": "Hi all"}, "dave", pause=0)
  message_id = run("get", f"--group={group_id}")[1]["group"]["sent"][0]["id"]
  code, answer = run("sent-copy", f"--group={group_id}", f"--message={message_id}")
  assert code == 0 and answer["copy"]["bcc"] == ["pat@example.org"] and answer["copy"]["subject"] == "Hello"
  code, answer = run("sent-copy", f"--group={group_id}", f"--message={message_id + 100000}")
  assert code == 1 and "no copy" in answer["error"]


def test_a_copy_of_each_sent_email_is_kept_with_its_hidden_recipients(outbox):
  """The owner's request, 2026-11-18: an exact copy of each email sent (to, bcc, subject, contents), viewable from
  the Sent table. A member's copy is kept, with STOP_CODE_PLACEHOLDER in place of their stop code."""
  group = new_group()
  account("ann", texts=True)
  account("cat", verified=False)
  groups.add_member(group["id"], {"email": f"ann@{DOMAIN}"})
  groups.add_member(group["id"], {"email": f"cat@{DOMAIN}"})
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  groups.send(group["id"], "message", {"subject": "Potluck", "html": "<p>Bring a <strong>dish</strong>.</p>"}, "dave", pause=0)
  sent = groups.list_sent(group["id"])[0]
  assert sent["has_copy"] is True
  copy = groups.get_copy(group["id"], sent["id"])
  assert (copy["from"], copy["to"], copy["reply_to"], copy["subject"]) == ("site@example.test", "dave@example.org", "dave@example.org", "Potluck")
  # Every address it was emailed to (not the unconfirmed one), and the leader's own copy.
  assert sorted(copy["bcc"]) == sorted([f"ann@{DOMAIN}", "pat@example.org"]) and copy["leader_copy"] is True
  assert "<strong>dish</strong>" in copy["html"] and "Bring a dish." in copy["text"]
  # The same email the members got, but no member's own stop code in it.
  with connect() as connection:
    codes = [row[0] for row in connection.execute("SELECT stop_token FROM group_members WHERE group_id = %s", (group["id"],))]
  assert groups.STOP_CODE_PLACEHOLDER in copy["text"] and groups.STOP_CODE_PLACEHOLDER in copy["html"]
  assert not any(code in copy["text"] or code in copy["html"] for code in codes)
  member_text = outbox["emails"][0].get_body(("plain",)).get_content()
  own = next(code for code in codes if code in member_text)
  assert member_text.replace(own, groups.STOP_CODE_PLACEHOLDER) == copy["text"]
  # Not another group's message.
  other = new_group("Other")
  with pytest.raises(GroupProblem, match="no copy"):
    groups.get_copy(other["id"], sent["id"])


def test_a_verse_card_copy_keeps_its_picture_and_older_messages_have_none(outbox):
  group = new_group()
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  preview = groups.preview_verse()
  groups.send(group["id"], "verse", {"card": preview["card"], "verse": preview["verse"]}, "dave", pause=0)
  copy = groups.get_copy(group["id"], groups.list_sent(group["id"])[0]["id"])
  assert copy["bcc"] == ["pat@example.org"] and "cid:" not in copy["html"] and 'src="data:image/jpeg;base64,' in copy["html"]
  # A message from before copies were kept: no copy, and no View link (has_copy false).
  with connect() as connection:
    old = connection.execute(
      "INSERT INTO group_messages (group_id, kind, subject, text, sent_by, emailed) VALUES (%s, 'message', 'Old', 'x', 'dave', 1) RETURNING id",
      (group["id"],),
    ).fetchone()[0]
  assert next(each for each in groups.list_sent(group["id"]) if each["id"] == old)["has_copy"] is False
  with pytest.raises(GroupProblem, match="no copy"):
    groups.get_copy(group["id"], old)


def test_a_copy_of_an_email_to_one_member_and_none_for_texts_only(outbox):
  group = new_group()
  groups.add_member(group["id"], {"email": "pat@example.org", "name": "Pat"})
  member = groups.get_group(group["id"])["members"][0]
  groups.email_member(group["id"], member["id"], "Thinking of you.", "dave")
  copy = groups.get_copy(group["id"], groups.list_sent(group["id"])[0]["id"])
  assert copy["to"] == "pat@example.org" and copy["bcc"] == [] and copy["leader_copy"] is False and copy["html"] is None
  # The copy is the email as sent: the words only (no foot, so no stop code).
  assert copy["text"].strip() == "Thinking of you." and groups.STOP_CODE_PLACEHOLDER not in copy["text"]
  # A send that emailed nobody (all failed) keeps no copy.
  empty = new_group("Empty")
  groups.send(empty["id"], "message", {"subject": "Hi", "text": "Hello"}, "dave", pause=0)
  assert groups.list_sent(empty["id"])[0]["has_copy"] is False


def test_the_sent_by_line_can_be_left_out(outbox):
  group = new_group()
  account("ann")
  groups.add_member(group["id"], {"email": f"ann@{DOMAIN}"})
  groups.send(group["id"], "message", {"subject": "Thank you", "text": "Thank you all.", "show_sent_by": False}, "dave", pause=0)
  member = outbox["emails"][0].get_content()
  assert "Thank you all." in member and "Sent by" not in member
  # The member's stop link stays (and its one-click header).
  assert "To stop messages from this group" in member and outbox["emails"][0]["List-Unsubscribe"]
  outbox["emails"].clear()
  groups.send(group["id"], "message", {"subject": "Hello", "text": "Hello."}, "dave", pause=0)
  assert "Sent by Deacon Dave to the group" in outbox["emails"][0].get_content()  # on unless unticked

  # A scheduled email keeps the choice.
  schedule = group_schedules.add_schedule(group["id"], {
    "kind": "message", "subject": "Weekly", "text": "Every week.", "repeat": "weekly", "weekday": 6,
    "send_time": "09:00", "timezone": "America/Chicago", "show_sent_by": False,
  }, "dave")
  assert schedule["show_sent_by"] is False
  assert group_schedules._details_for(group_schedules._get(schedule["id"], group["id"]))["show_sent_by"] is False

"""Tests for saved verse cards (saved_cards.py): My cards, the Drupal administrator's site account and a card
attached to a group message. Mail and Telnyx are faked: nothing is sent. They use the real tables with their own
accounts and groups, temporary folders (conftest.py), and remove their rows after."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import accounts
import custom_cards
import groups
import saved_cards
import site_users
import sms
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "saved-cards-test.example"
OWNER = 990101
JOHN_3_16 = {"translation": "BSB", "book": 43, "chapter": 3, "verse": 16, "background": "plain"}
TOOL = Path(__file__).resolve().parent.parent / "scripts" / "manage_groups.py"
client = TestClient(app)


@pytest.fixture(autouse=True)
def outbox(monkeypatch):
  sent = {"emails": [], "texts": []}
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)
  monkeypatch.setattr(sms, "is_configured", lambda: True)
  monkeypatch.setattr(sms, "send_text", lambda number, text, media_url=None: sent["texts"].append((number, text, media_url)) or True)
  settings = lambda: {"from_address": "site@example.test"}
  for module in (custom_cards, groups):
    monkeypatch.setattr(module, "load_mail_settings", settings)
    monkeypatch.setattr(module, "send_email", lambda settings, email, recipients=None: sent["emails"].append(email))
  monkeypatch.setenv("SITE_URL", "https://site.example")
  custom_cards._sends.clear()

  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM member_groups WHERE owner_uid = %s", (OWNER,))
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield sent
  clear()


def register(name, texts=False):
  client.cookies.clear()
  extra = {"phone": "555 234 5678", "phone_is_cell": True, "send_via_sms": True} if texts else {}
  response = client.post(
    "/account/register",
    json={"email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD, "first_name": name.title(), "last_name": "Member", **extra},
  )
  assert response.status_code == 200, response.text
  user = response.json()["user"]
  with connect() as connection:
    connection.execute("UPDATE users SET email_verified_at = now() WHERE id = %s", (user["id"],))
  return user


def test_a_downloaded_or_sent_card_is_kept_once_and_shown_only_to_its_member(outbox):
  assert client.post("/saved-cards", json=JOHN_3_16).status_code == 401
  register("ruth")
  ann = register("ann")
  first = client.post("/saved-cards", json=JOHN_3_16).json()["card"]
  assert first["caption"] == "John 3:16 (BSB)" and first["words"].startswith("For God so loved")
  # The same verse and background again (sent this time) is the same card, moved to the top.
  sent = client.post("/day-card/send", json={**JOHN_3_16, "email": "friend@example.test"}).json()
  assert sent["card"]["id"] == first["id"]
  other = client.post("/saved-cards", json={**JOHN_3_16, "verse": 17}).json()["card"]
  cards = client.get("/saved-cards").json()["cards"]
  assert [card["id"] for card in cards] == [other["id"], first["id"]]
  picture = client.get(cards[0]["image"])
  assert picture.status_code == 200 and picture.content[:3] == b"\xff\xd8\xff"
  assert client.get(cards[0]["thumbnail"]).status_code == 200
  # Another member sees none of them.
  register("bob")
  assert client.get("/saved-cards").json()["cards"] == []
  assert client.get(cards[0]["image"]).status_code == 404
  assert client.delete(f"/saved-cards/{first['id']}").status_code == 404
  assert ann["id"]


def test_editing_a_card_replaces_it_and_delete_removes_its_files():
  register("ann")
  card = client.post("/saved-cards", json=JOHN_3_16).json()["card"]
  old_file = saved_cards.picture_path(saved_cards.get_card(client.get("/account/me").json()["user"]["id"], card["id"])["file_name"])
  edited = client.post("/saved-cards", json={**JOHN_3_16, "verse": 18, "card_id": card["id"]}).json()["card"]
  assert edited["id"] == card["id"] and edited["verse"] == 18
  assert not old_file.exists()
  # Sending from the editor replaces it too.
  sent = client.post("/day-card/send", json={**JOHN_3_16, "verse": 19, "card_id": card["id"], "email": "friend@example.test"}).json()
  assert sent["card"]["id"] == card["id"] and sent["card"]["verse"] == 19
  assert len(client.get("/saved-cards").json()["cards"]) == 1
  user_id = client.get("/account/me").json()["user"]["id"]
  path = saved_cards.picture_path(saved_cards.get_card(user_id, card["id"])["file_name"])
  assert client.delete(f"/saved-cards/{card['id']}").status_code == 200
  assert not path.exists() and client.get("/saved-cards").json()["cards"] == []


def test_a_saved_card_can_be_sent_again_as_it_was_kept(outbox):
  ruth = register("ruth")
  register("ann")
  card = client.post("/saved-cards", json=JOHN_3_16).json()["card"]
  answer = client.post("/day-card/send", json={"saved_card_id": card["id"], "recipient_id": ruth["id"]})
  assert answer.status_code == 200, answer.text
  assert answer.json()["ways"] == ["email"] and answer.json()["card"]["id"] == card["id"]
  assert outbox["emails"][-1]["Subject"] == "Ann Member sent you a verse: John 3:16"
  assert client.post("/day-card/send", json={"saved_card_id": 999999999, "email": "friend@example.test"}).status_code == 404
  assert client.post("/day-card/send", json={"email": "friend@example.test"}).status_code == 422


def test_a_drupal_account_is_its_linked_site_account_else_the_one_with_its_email():
  ann = register("ann")
  bob = register("bob")
  assert saved_cards.account_for_admin(4242, f"ANN@{DOMAIN}")["id"] == ann["id"]
  assert saved_cards.account_for_admin(4242, "nobody@example.test") is None
  site_users.update_user(bob["id"], drupal_uid=4242)
  assert saved_cards.account_for_admin(4242, f"ann@{DOMAIN}")["id"] == bob["id"]
  # Ann's address no longer matches another Drupal account once she is linked to one.
  site_users.update_user(ann["id"], drupal_uid=4343)
  assert saved_cards.account_for_admin(5000, f"ann@{DOMAIN}") is None
  # Linking another account to 4242 unlinks Bob.
  site_users.update_user(ann["id"], drupal_uid=4242)
  assert site_users.get_user(bob["id"])["drupal_uid"] is None
  site_users.update_user(ann["id"], drupal_uid=0)
  assert site_users.get_user(ann["id"])["drupal_uid"] is None


def test_a_leaders_saved_card_goes_with_a_group_message_inline_and_attached(outbox):
  leader = register("dave")
  card = client.post("/saved-cards", json=JOHN_3_16).json()["card"]
  register("ann", texts=True)
  group = groups.save_group(None, {"name": "Care group"}, OWNER, "Deacon Dave", f"dave@{DOMAIN}")
  groups.add_member(group["id"], {"email": f"ann@{DOMAIN}"})
  # The tool lists the leader's cards with their thumbnails.
  listed = subprocess.run(
    [sys.executable, str(TOOL), "my-cards", "--drupal-uid=7777", f"--email=dave@{DOMAIN}"], capture_output=True, text=True,
  )
  answer = json.loads(listed.stdout)
  assert answer["account"]["id"] == leader["id"] and answer["cards"][0]["id"] == card["id"]
  assert answer["cards"][0]["thumbnail"].startswith("data:image/jpeg;base64,")
  outbox["texts"].clear()
  details = {"subject": "This week", "html": "<p>Be <strong>encouraged</strong>.</p>", "saved_card": card["id"], "admin": {"uid": 7777, "email": f"dave@{DOMAIN}"}}
  counts = groups.send(group["id"], "message", details, "dave", pause=0)
  assert counts["emailed"] == 1 and counts["texted"] == 1
  email = outbox["emails"][0]
  html = email.get_body(("html",)).get_content()
  assert "cid:" in html and "<strong>encouraged</strong>" in html
  attachments = [part for part in email.iter_attachments() if part.get_filename() == "verse-card.jpg"]
  assert len(attachments) == 1 and attachments[0].get_content()[:3] == b"\xff\xd8\xff"
  assert outbox["texts"][0][2].startswith("https://site.example/api/message-card/")
  # Someone else's card, or no linked account, is refused.
  with pytest.raises(groups.GroupProblem):
    groups.send(group["id"], "message", {**details, "admin": {"uid": 1, "email": "nobody@example.test"}}, "dave", pause=0)
  # A plain message gets an HTML version for the picture.
  outbox["emails"].clear()
  groups.send(group["id"], "message", {"subject": "Hi", "text": "Hello.", "saved_card": card["id"], "admin": {"uid": 7777, "email": f"dave@{DOMAIN}"}}, "dave", pause=0)
  plain_email = outbox["emails"][0]
  assert "cid:" in plain_email.get_body(("html",)).get_content()
  assert any(part.get_filename() == "verse-card.jpg" for part in plain_email.iter_attachments())


def test_deleting_an_account_deletes_its_cards_files():
  ann = register("ann")
  card = client.post("/saved-cards", json=JOHN_3_16).json()["card"]
  path = saved_cards.picture_path(saved_cards.get_card(ann["id"], card["id"])["file_name"])
  assert path.exists()
  site_users.delete_user(ann["id"])
  assert not path.exists()

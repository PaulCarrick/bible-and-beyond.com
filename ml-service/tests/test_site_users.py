"""Tests for managing the main site's accounts from Drupal. They use the real users tables and remove only
their own accounts (addresses at site-users-test.example) before and after."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from accounts import log_in, password_matches
from search import connect
from site_users import UserProblem, create_user, delete_user, get_user, list_users, update_user

PASSWORD = "a long enough password"
DOMAIN = "site-users-test.example"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_users.py"


@pytest.fixture(autouse=True)
def clean_accounts():
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM users WHERE email LIKE %s", (f"%@{DOMAIN}",))

  clear()
  yield
  clear()


def stored_hash(user_id):
  with connect() as connection:
    return connection.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,)).fetchone()[0]


def test_a_new_account_is_stored_with_its_settings_and_a_hashed_password():
  user = create_user(f" Ann@{DOMAIN.upper()} ", PASSWORD, email_verified=True, open_ai_queries=False)

  assert user["email"] == f"ann@{DOMAIN}"
  assert user["email_verified"] is True and user["open_ai_queries"] is False
  assert user["note_count"] == 0 and user["subscription_count"] == 0 and user["last_login_at"] is None
  assert "password" not in json.dumps(user)
  assert password_matches(PASSWORD, stored_hash(user["id"]))
  assert log_in(f"ann@{DOMAIN}", PASSWORD)[0]["id"] == user["id"]


def test_an_administrator_can_set_change_and_clear_the_names_and_phone():
  user = create_user(f"ann@{DOMAIN}", PASSWORD, False, False, first_name=" Ann ", last_name="Lee", phone="555 0199")
  assert (user["first_name"], user["last_name"], user["phone"]) == ("Ann", "Lee", "555 0199")

  changed = update_user(user["id"], last_name="Lee-Smith")
  assert (changed["first_name"], changed["last_name"], changed["phone"]) == ("Ann", "Lee-Smith", "555 0199")

  changed = update_user(user["id"], phone="")
  assert changed["phone"] == "" and changed["first_name"] == "Ann"
  with connect() as connection:
    assert connection.execute("SELECT phone FROM users WHERE id = %s", (user["id"],)).fetchone()[0] is None


def test_an_administrator_may_leave_the_names_empty_but_not_send_bad_ones():
  user = create_user(f"ann@{DOMAIN}", PASSWORD, False, False)
  assert (user["first_name"], user["last_name"], user["phone"]) == ("", "", "")

  for profile, fragment in [
    ({"first_name": "A" * 101}, "at most 100"),
    ({"last_name": "Lee\rX"}, "on one line"),
    ({"phone": "5" * 41}, "at most 40"),
  ]:
    with pytest.raises(UserProblem, match=fragment):
      create_user(f"bob@{DOMAIN}", PASSWORD, False, False, **profile)
    with pytest.raises(UserProblem, match=fragment):
      update_user(user["id"], **profile)
  assert list_users(DOMAIN)["total"] == 1


def test_the_list_can_be_searched_by_name():
  create_user(f"ann@{DOMAIN}", PASSWORD, False, False, first_name="Ann", last_name="Lee")
  create_user(f"bob@{DOMAIN}", PASSWORD, False, False)

  assert [user["email"] for user in list_users("ann lee")["users"]] == [f"ann@{DOMAIN}"]
  assert list_users("LEE")["users"][0]["last_name"] == "Lee"


def test_open_ai_queries_is_off_for_accounts_made_on_the_site():
  with connect() as connection:
    user_id = connection.execute(
      "INSERT INTO users (email, password_hash) VALUES (%s, 'x') RETURNING id", (f"bob@{DOMAIN}",)
    ).fetchone()[0]

  assert get_user(user_id)["open_ai_queries"] is False


def test_bad_details_are_refused_and_nothing_is_saved():
  create_user(f"ann@{DOMAIN}", PASSWORD, False, False)
  for email, password, fragment in [
    ("not an address", PASSWORD, "valid email"),
    (f"bob@{DOMAIN}", "short", "at least 8"),
    (f"bob@{DOMAIN}", "x" * 129, "at most 128"),
    (f"ANN@{DOMAIN}", PASSWORD, "already exists"),
  ]:
    with pytest.raises(UserProblem, match=fragment):
      create_user(email, password, False, False)

  assert list_users(DOMAIN)["total"] == 1


def test_changes_apply_only_to_what_is_given():
  user = create_user(f"ann@{DOMAIN}", PASSWORD, False, False)
  before = stored_hash(user["id"])

  changed = update_user(user["id"], open_ai_queries=True)
  assert changed["open_ai_queries"] is True and changed["email"] == f"ann@{DOMAIN}" and changed["email_verified"] is False
  assert stored_hash(user["id"]) == before

  changed = update_user(user["id"], email=f"Anne@{DOMAIN}", email_verified=True)
  assert changed["email"] == f"anne@{DOMAIN}" and changed["email_verified"] is True and changed["open_ai_queries"] is True

  changed = update_user(user["id"], email_verified=False, open_ai_queries=False)
  assert changed["email_verified"] is False and changed["open_ai_queries"] is False


def test_a_new_password_logs_the_account_out_everywhere():
  user = create_user(f"ann@{DOMAIN}", PASSWORD, True, False)
  log_in(f"ann@{DOMAIN}", PASSWORD)
  with connect() as connection:
    connection.execute(
      "INSERT INTO account_tokens (token_hash, user_id, purpose, expires_at) VALUES ('test-reset', %s, 'reset', %s)",
      (user["id"], datetime.now(timezone.utc) + timedelta(hours=1)),
    )

  update_user(user["id"], password="a different password")

  assert password_matches("a different password", stored_hash(user["id"]))
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM user_sessions WHERE user_id = %s", (user["id"],)).fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM account_tokens WHERE user_id = %s", (user["id"],)).fetchone()[0] == 0


def test_an_address_used_by_another_account_is_refused():
  create_user(f"ann@{DOMAIN}", PASSWORD, False, False)
  bob = create_user(f"bob@{DOMAIN}", PASSWORD, False, False)

  with pytest.raises(UserProblem, match="Another account"):
    update_user(bob["id"], email=f"ann@{DOMAIN}")
  with pytest.raises(UserProblem, match="at least 8"):
    update_user(bob["id"], password="short")
  assert get_user(bob["id"])["email"] == f"bob@{DOMAIN}"


def test_deleting_an_account_removes_its_notes_too():
  user = create_user(f"ann@{DOMAIN}", PASSWORD, False, False)
  with connect() as connection:
    connection.execute(
      "INSERT INTO notes (user_id, item_type, source_code, book_number, chapter, verse, body, body_text) "
      "VALUES (%s, 'bible_verse', 'BSB', 43, 3, 16, '<p>x</p>', 'x')",
      (user["id"],),
    )
  assert get_user(user["id"])["note_count"] == 1

  assert delete_user(user["id"])["email"] == f"ann@{DOMAIN}"
  with pytest.raises(UserProblem, match="no such account"):
    get_user(user["id"])
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM notes WHERE user_id = %s", (user["id"],)).fetchone()[0] == 0


def test_the_list_is_newest_first_searchable_and_paged(monkeypatch):
  import site_users

  monkeypatch.setattr(site_users, "PER_PAGE", 2)
  for name in ("ann", "bob", "cat"):
    create_user(f"{name}@{DOMAIN}", PASSWORD, False, False)

  first = list_users(DOMAIN, 1)
  assert first["total"] == 3 and [user["email"] for user in first["users"]] == [f"cat@{DOMAIN}", f"bob@{DOMAIN}"]
  assert [user["email"] for user in list_users(DOMAIN, 2)["users"]] == [f"ann@{DOMAIN}"]
  assert list_users(f"BOB@{DOMAIN}")["total"] == 1
  # "%" and "_" are taken literally, not as patterns.
  assert list_users(f"%@{DOMAIN}")["total"] == 0
  assert list_users(f"a_n@{DOMAIN}")["total"] == 0


def run_tool(*arguments, password=None):
  completed = subprocess.run(
    [sys.executable, str(SCRIPT), *arguments], input=password, capture_output=True, text=True, check=False
  )
  return completed.returncode, json.loads(completed.stdout), completed.stderr


def test_the_tool_reads_the_password_from_its_input_and_answers_in_json():
  status, answer, _ = run_tool("create", f"--email=ann@{DOMAIN}", "--open-ai-queries", "--password-on-input", password=PASSWORD + "\n")
  assert status == 0 and answer["ok"] and answer["user"]["open_ai_queries"] is True
  user_id = answer["user"]["id"]
  assert password_matches(PASSWORD, stored_hash(user_id))

  status, answer, _ = run_tool("update", f"--id={user_id}", "--open-ai-queries=no", "--email-verified=yes")
  assert status == 0 and answer["user"]["open_ai_queries"] is False and answer["user"]["email_verified"] is True

  status, answer, _ = run_tool("update", f"--id={user_id}", "--first-name=Ann", "--last-name=Lee", "--phone=555 0199")
  assert status == 0 and (answer["user"]["first_name"], answer["user"]["phone"]) == ("Ann", "555 0199")
  status, answer, _ = run_tool("update", f"--id={user_id}", "--phone=")
  assert status == 0 and answer["user"]["phone"] == "" and answer["user"]["last_name"] == "Lee"

  status, answer, _ = run_tool("list", f"--query={DOMAIN}")
  assert status == 0 and answer["total"] == 1

  status, answer, _ = run_tool("create", f"--email=bob@{DOMAIN}", "--password-on-input", password="short\n")
  assert status == 1 and answer == {"ok": False, "error": "The password must be at least 8 characters."}

  status, answer, _ = run_tool("delete", f"--id={user_id}")
  assert status == 0 and answer["user"]["email"] == f"ann@{DOMAIN}"
  status, answer, _ = run_tool("get", f"--id={user_id}")
  assert status == 1 and "no such account" in answer["error"]


def test_an_administrator_can_reopen_or_close_an_account():
  from accounts import AccountProblem, close_account

  user = create_user(f"reopen@{DOMAIN}", PASSWORD, email_verified=True, open_ai_queries=False)
  assert user["closed"] is False and user["closed_at"] is None
  close_account(user["id"], PASSWORD)
  closed = get_user(user["id"])
  assert closed["closed"] is True and closed["closed_at"] is not None
  assert any(found["closed"] for found in list_users(f"reopen@{DOMAIN}")["users"])
  with pytest.raises(AccountProblem, match="closed"):
    log_in(f"reopen@{DOMAIN}", PASSWORD)
  # Unticking "Account closed" reopens it: it can log in again; other edits leave the flag alone.
  assert update_user(user["id"], first_name="Ruth")["closed"] is True
  assert update_user(user["id"], closed=False)["closed"] is False
  assert log_in(f"reopen@{DOMAIN}", PASSWORD)[0]["id"] == user["id"]
  # Ticking it closes it and logs it out everywhere.
  assert update_user(user["id"], closed=True)["closed"] is True
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM user_sessions WHERE user_id = %s", (user["id"],)).fetchone()[0] == 0


def test_an_account_can_have_a_phone_instead_of_an_email():
  try:
    user = create_user("", PASSWORD, email_verified=False, open_ai_queries=False, phone="555 234 7777", first_name="Phone", phone_verified=True)
    assert user["email"] == "" and user["login_phone"] == "+15552347777" and user["phone_verified"] is True
    assert user["email_verified"] is False
    assert log_in("(555) 234-7777", PASSWORD)[0]["id"] == user["id"]
    # Found by the digits of its phone, however typed.
    assert [found["id"] for found in list_users("234-7777")["users"]] == [user["id"]]
    with pytest.raises(UserProblem, match="cell phone number"):
      create_user("", PASSWORD, email_verified=False, open_ai_queries=False, phone="")
    with pytest.raises(UserProblem, match="already exists"):
      create_user("", PASSWORD, email_verified=False, open_ai_queries=False, phone="5552347777")
    # Adding an address: it logs in either way; taking it away again needs the phone.
    both = update_user(user["id"], email=f"phone@{DOMAIN}")
    assert both["email"] == f"phone@{DOMAIN}" and both["login_phone"] == "+15552347777"
    assert log_in(f"phone@{DOMAIN}", PASSWORD)[0]["id"] == user["id"]
    back = update_user(user["id"], email="")
    assert back["email"] == "" and back["login_phone"] == "+15552347777"
    with pytest.raises(UserProblem, match="cell phone number"):
      update_user(user["id"], phone="")
    # A new number is the new login, not confirmed unless ticked.
    moved = update_user(user["id"], phone="555 234 8888")
    assert moved["login_phone"] == "+15552348888" and moved["phone_verified"] is False
    assert update_user(user["id"], phone_verified=True)["phone_verified"] is True
  finally:
    with connect() as connection:
      connection.execute("DELETE FROM users WHERE login_phone IN ('+15552347777', '+15552348888')")


def test_an_email_account_needs_its_email_unless_it_logs_in_with_a_phone():
  user = create_user(f"keep@{DOMAIN}", PASSWORD, email_verified=True, open_ai_queries=False)
  with pytest.raises(UserProblem, match="cell phone number"):
    update_user(user["id"], email="")


def texting(user_id):
  with connect() as connection:
    return connection.execute(
      "SELECT sms_opt_in, sms_number, send_via_sms, send_via_email, sms_consent_at IS NOT NULL, sms_stopped_at IS NOT NULL FROM users WHERE id = %s",
      (user_id,),
    ).fetchone()


@pytest.fixture
def welcomed(monkeypatch):
  import site_users

  numbers = []
  monkeypatch.setattr(site_users, "welcome_text", numbers.append)
  return numbers


def test_an_administrator_can_turn_texts_on_and_off(welcomed):
  user = create_user(f"ann@{DOMAIN}", PASSWORD, email_verified=True, open_ai_queries=False, phone="555-201-4567", texts=True)
  assert user["sms_opt_in"] is True
  assert texting(user["id"]) == (True, "+15552014567", True, True, True, False)
  assert welcomed == ["+15552014567"]

  # Saving again with texts on (the form always sends the box) sends no second welcome.
  update_user(user["id"], first_name="Ann", texts=True)
  assert welcomed == ["+15552014567"]

  off = update_user(user["id"], texts=False)
  assert off["sms_opt_in"] is False and texting(user["id"])[:4] == (False, "+15552014567", False, True)

  # A member who replied STOP keeps their choice when the box is left unticked (so START brings texts back).
  with connect() as connection:
    connection.execute("UPDATE users SET sms_opt_in = false, sms_stopped_at = now(), send_via_sms = true WHERE id = %s", (user["id"],))
  update_user(user["id"], texts=False)
  assert texting(user["id"])[2] is True
  # Ticked again: on, the stop cleared, a welcome text.
  update_user(user["id"], texts=True)
  assert texting(user["id"]) == (True, "+15552014567", True, True, True, False) and len(welcomed) == 2


def test_texts_need_a_cell_number_and_a_new_number_turns_them_off_unless_ticked(welcomed):
  with pytest.raises(UserProblem, match="US or Canadian cell number"):
    create_user(f"bob@{DOMAIN}", PASSWORD, email_verified=True, open_ai_queries=False, phone="", texts=True)
  user = create_user(f"bob@{DOMAIN}", PASSWORD, email_verified=True, open_ai_queries=False, phone="555-201-4567", texts=True)
  update_user(user["id"], phone="555-201-9999")  # texts not given: a new number turns them off
  assert texting(user["id"])[:3] == (False, None, False)
  moved = update_user(user["id"], phone="555-201-8888", texts=True)
  assert moved["sms_opt_in"] is True and texting(user["id"])[1] == "+15552018888" and welcomed[-1] == "+15552018888"


def test_the_tool_turns_texts_on(welcomed):
  made = subprocess.run(
    [sys.executable, str(SCRIPT), "create", f"--email=tool@{DOMAIN}", "--phone=555-201-4567", "--password-on-input"],
    input=PASSWORD + "\n", capture_output=True, text=True,
  )
  user_id = json.loads(made.stdout)["user"]["id"]
  # The tool runs in its own process, so texting is turned off there: no welcome text is sent.
  import os

  quiet = {**os.environ, "OUTGOING_SMS": "off"}
  changed = subprocess.run(
    [sys.executable, str(SCRIPT), "update", f"--id={user_id}", "--texts=yes"], capture_output=True, text=True, env=quiet
  )
  assert json.loads(changed.stdout)["user"]["sms_opt_in"] is True

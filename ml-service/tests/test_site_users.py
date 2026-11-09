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
    (f"bob@{DOMAIN}", "short", "at least 10"),
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
  with pytest.raises(UserProblem, match="at least 10"):
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
  assert status == 1 and answer == {"ok": False, "error": "The password must be at least 10 characters."}

  status, answer, _ = run_tool("delete", f"--id={user_id}")
  assert status == 0 and answer["user"]["email"] == f"ann@{DOMAIN}"
  status, answer, _ = run_tool("get", f"--id={user_id}")
  assert status == 1 and "no such account" in answer["error"]

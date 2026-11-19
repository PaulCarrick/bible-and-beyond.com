"""Tests for the external sites (external_sites.py). They use the real table: its rows are set aside before each test
and put back afterwards."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import external_sites
from external_sites import ExternalSiteProblem, check_address
from search import connect

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_external_sites.py"


@pytest.fixture(autouse=True)
def empty_table():
  with connect() as connection:
    cursor = connection.execute("SELECT * FROM admin_external_sites")
    columns, rows = [column.name for column in cursor.description], cursor.fetchall()
    connection.execute("DELETE FROM admin_external_sites")
  yield
  with connect() as connection:
    connection.execute("DELETE FROM admin_external_sites")
    for row in rows:
      connection.execute(f"INSERT INTO admin_external_sites ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})", row)
    connection.execute("SELECT setval(pg_get_serial_sequence('admin_external_sites', 'id'), GREATEST((SELECT max(id) FROM admin_external_sites), 1))")


def test_only_web_addresses_are_kept():
  assert check_address("  https://read.amazon.com/kindle-library  ") == "https://read.amazon.com/kindle-library"
  assert check_address("read.amazon.com") == "https://read.amazon.com"
  assert check_address("http://example.org/a?b=c") == "http://example.org/a?b=c"
  for bad in ("", "javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,x", "file:///etc/passwd", "ftp://example.org",
              "https://", "https://exa mple.org", "mailto:a@example.org"):
    with pytest.raises(ExternalSiteProblem):
      check_address(bad)
  with pytest.raises(ExternalSiteProblem, match="password"):
    check_address("https://me:secret@read.amazon.com")


def test_sites_are_added_listed_changed_and_deleted():
  kindle = external_sites.create_site({"name": " Kindle   reader ", "address": "read.amazon.com", "notes": "Sign in once in its window.\r\n"}, "paul")
  assert kindle["name"] == "Kindle reader" and kindle["address"] == "https://read.amazon.com" and kindle["host"] == "read.amazon.com"
  assert kindle["notes"] == "Sign in once in its window." and kindle["created_by"] == "paul"
  external_sites.create_site({"name": "Archive", "address": "https://archive.org"}, "paul")
  assert [site["name"] for site in external_sites.list_sites()] == ["Archive", "Kindle reader"]
  changed = external_sites.update_site(kindle["id"], {"name": "Kindle", "address": "https://read.amazon.com/kindle-library", "notes": ""})
  assert changed["name"] == "Kindle" and changed["address"].endswith("/kindle-library") and changed["notes"] == ""
  assert changed["sign_in_address"] == ""
  # An optional sign-in page, checked like the address.
  signed = external_sites.update_site(kindle["id"], {"name": "Kindle", "address": "read.amazon.com", "sign_in_address": "www.amazon.com/ap/signin"})
  assert signed["sign_in_address"] == "https://www.amazon.com/ap/signin"
  with pytest.raises(ExternalSiteProblem, match="sign-in address"):
    external_sites.update_site(kindle["id"], {"name": "Kindle", "address": "read.amazon.com", "sign_in_address": "javascript:alert(1)"})
  external_sites.delete_site(kindle["id"])
  with pytest.raises(ExternalSiteProblem, match="not found"):
    external_sites.get_site(kindle["id"])
  with pytest.raises(ExternalSiteProblem, match="name is needed"):
    external_sites.create_site({"name": "", "address": "https://archive.org"}, "paul")


def test_the_tool():
  completed = subprocess.run(
    [sys.executable, str(SCRIPT), "create"], input=json.dumps({"name": "Kindle", "address": "https://read.amazon.com", "created_by": "paul"}),
    capture_output=True, text=True, check=False,
  )
  assert completed.returncode == 0 and json.loads(completed.stdout)["site"]["name"] == "Kindle"
  completed = subprocess.run(
    [sys.executable, str(SCRIPT), "create"], input=json.dumps({"name": "Bad", "address": "javascript:alert(1)"}), capture_output=True, text=True, check=False,
  )
  assert completed.returncode == 1 and "web address" in json.loads(completed.stdout)["error"]
  completed = subprocess.run([sys.executable, str(SCRIPT), "list"], capture_output=True, text=True, check=False)
  assert [site["name"] for site in json.loads(completed.stdout)["sites"]] == ["Kindle"]

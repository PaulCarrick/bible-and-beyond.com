"""Tests for the site icons (site_icons.py, GET /site-icon, the tool). conftest.py gives each test its own
icons folder."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import site_icons
from main import app
from site_icons import IconProblem

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_site_icons.py"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"></svg>'


def write(tmp_path, name, content):
  path = tmp_path / name
  path.write_bytes(content)
  return path


def test_the_site_settings_say_no_icon_is_replaced_at_first():
  settings = client.get("/site-settings").json()
  assert settings["header_icon"] is None and settings["tab_icon"] is None
  assert client.get("/site-icon/header").status_code == 404


def test_an_uploaded_icon_is_served_with_a_version_and_a_safe_policy(tmp_path):
  site_icons.save("header", write(tmp_path, "logo.png", PNG), "logo.png")
  site_icons.save("tab", write(tmp_path, "tab.svg", SVG), "tab.svg")

  settings = client.get("/site-settings").json()
  assert settings["header_icon"].startswith("/site-icon/header?v=")
  assert settings["tab_icon"].startswith("/site-icon/tab?v=")
  header = client.get("/site-icon/header")
  assert header.status_code == 200 and header.content == PNG and header.headers["content-type"] == "image/png"
  tab = client.get("/site-icon/tab")
  assert tab.headers["content-type"].startswith("image/svg+xml")
  assert "sandbox" in tab.headers["content-security-policy"] and tab.headers["x-content-type-options"] == "nosniff"
  assert client.get("/site-icon/other").status_code == 404


def test_replacing_an_icon_with_another_kind_of_file_keeps_only_the_new_one(tmp_path):
  site_icons.save("header", write(tmp_path, "a.png", PNG), "a.png")
  site_icons.save("header", write(tmp_path, "b.svg", SVG), "b.svg")
  assert sorted(path.name for path in site_icons.icons_folder().iterdir()) == ["header.svg"]
  site_icons.remove("header")
  assert site_icons.current("header") is None


def test_wrong_files_are_refused(tmp_path, monkeypatch):
  with pytest.raises(IconProblem, match="PNG, JPEG"):
    site_icons.save("header", write(tmp_path, "a.txt", b"hello"), "a.txt")
  with pytest.raises(IconProblem, match="not really"):
    site_icons.save("header", write(tmp_path, "fake.png", b"GIF89a....."), "fake.png")
  with pytest.raises(IconProblem, match="empty"):
    site_icons.save("header", write(tmp_path, "empty.png", b""), "empty.png")
  monkeypatch.setattr(site_icons, "MAX_BYTES", 10)
  with pytest.raises(IconProblem, match="larger"):
    site_icons.save("header", write(tmp_path, "big.png", PNG), "big.png")
  with pytest.raises(IconProblem, match="header emblem"):
    site_icons.save("footer", write(tmp_path, "ok.png", PNG), "ok.png")
  assert site_icons.current("header") is None


def run_tool(*arguments):
  completed = subprocess.run([sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True, env=os.environ.copy())
  return completed.returncode, json.loads(completed.stdout)


def test_the_tool_uploads_shows_a_preview_and_removes(tmp_path):
  status, answer = run_tool("upload", "--kind=tab", f"--file={write(tmp_path, 'upload.png', PNG)}", "--name=upload.png")
  assert status == 0 and answer["icons"]["tab"]["media_type"] == "image/png"
  assert answer["icons"]["tab"]["data_uri"].startswith("data:image/png;base64,") and answer["icons"]["header"] is None
  status, answer = run_tool("remove", "--kind=tab")
  assert status == 0 and answer["icons"]["tab"] is None
  status, answer = run_tool("upload", "--kind=tab", f"--file={write(tmp_path, 'bad.png', b'nope')}", "--name=bad.png")
  assert status == 1 and answer["ok"] is False and "not really" in answer["error"]

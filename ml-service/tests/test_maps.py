"""Tests for the maps and the members' notes, pins and routes on them. They use the real tables and remove only
their own maps (ids starting test-map-) and accounts (@maps-test.example); the maps folder is a temporary one
for each test."""

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import accounts
import maps
from main import app
from search import connect

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_maps.py"
PASSWORD = "correct horse battery"
DETAILS = {
  "title": "  Paul's   first journey ",
  "description": "Cyprus and Galatia\r\n\n\n\nwith Barnabas",
  "source": "Drawn for the test",
  "keywords": "missionary, Barnabas",
  "verses": "Acts 13:4-14; acts 14:26",
}


@pytest.fixture(autouse=True)
def folder(tmp_path, monkeypatch):
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)

  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM maps WHERE id LIKE 'test-map-%'")
      connection.execute("DELETE FROM users WHERE email LIKE '%@maps-test.example'")

  monkeypatch.setenv("MAPS_FOLDER", str(tmp_path / "maps"))
  clear()
  client.cookies.clear()
  yield tmp_path / "maps"
  clear()


def picture(tmp_path, name="map.png", size=(800, 600), kind="PNG"):
  path = tmp_path / name
  Image.new("RGBA" if kind == "PNG" else "RGB", size, (200, 180, 120, 255)).save(path, kind)
  return path


def pdf(tmp_path, pages=2):
  path = tmp_path / "map.pdf"
  first, *rest = [Image.new("RGB", (400 + 100 * page, 300), "white") for page in range(pages)]
  first.save(path, "PDF", save_all=True, append_images=rest)
  return path


def sign_up(name="ann", allowed=True):
  client.cookies.clear()
  response = client.post(
    "/account/register",
    json={"email": f"{name}@maps-test.example", "password": PASSWORD, "password_confirmation": PASSWORD},
  )
  assert response.status_code == 200
  user_id = response.json()["user"]["id"]
  with connect() as connection:
    connection.execute("UPDATE users SET use_maps = %s WHERE id = %s", (allowed, user_id))
  return user_id


def log_in(name):
  client.cookies.clear()
  assert client.post("/account/login", json={"email": f"{name}@maps-test.example", "password": PASSWORD}).status_code == 200


def published_map(tmp_path, map_id="test-map-journey"):
  maps.upload(picture(tmp_path), "map.png", map_id, DETAILS)
  maps.set_published(map_id, True)
  return map_id


def test_a_map_is_hidden_until_published_with_its_copies_and_verses(tmp_path, folder):
  found = maps.upload(picture(tmp_path, size=(7000, 3500)), "Journey.PNG", "test-map-journey", DETAILS)
  assert found["title"] == "Paul's first journey" and found["is_published"] is False
  assert found["description"] == "Cyprus and Galatia\n\nwith Barnabas"
  assert found["verses_text"] == "Acts 13:4–14; Acts 14:26"
  assert found["verses"][0] == {"book_number": 44, "chapter": 13, "verse": 4, "end_verse": 14, "label": "Acts 13:4–14"}
  # The copy shown is at most 5000 pixels on its longer side; the original is kept as uploaded.
  assert (found["width"], found["height"]) == (5000, 2500)
  assert {path.name for path in folder.iterdir()} == {"test-map-journey.png", "test-map-journey-display.webp", "test-map-journey-thumbnail.webp"}
  assert Image.open(folder / "test-map-journey-thumbnail.webp").width == maps.THUMBNAIL_WIDTH
  assert "test-map-journey" not in [entry["id"] for entry in client.get("/maps").json()["maps"]]
  assert client.get("/map-file/test-map-journey/display").status_code == 404

  maps.set_published("test-map-journey", True)
  listed = [entry for entry in client.get("/maps").json()["maps"] if entry["id"] == "test-map-journey"]
  assert listed and "file_name" not in listed[0]
  shown = client.get("/map-file/test-map-journey/display")
  assert shown.status_code == 200 and shown.headers["content-type"] == "image/webp"
  # The file as uploaded is never offered for download.
  assert client.get("/map-file/test-map-journey/original").status_code == 422
  assert maps.map_file("test-map-journey", "original") is None
  assert client.get("/map-file/test-map-journey/other").status_code == 422


def test_the_maps_of_a_verse_include_a_verse_inside_a_range(tmp_path):
  published_map(tmp_path)

  def ids(**verse):
    return [entry["id"] for entry in client.get("/maps", params=verse).json()["maps"]]

  assert "test-map-journey" in ids(book=44, chapter=13, verse=9)
  assert "test-map-journey" in ids(book=44, chapter=14, verse=26)
  assert "test-map-journey" not in ids(book=44, chapter=13, verse=15)


def test_verses_that_do_not_exist_are_refused_and_nothing_is_saved(tmp_path):
  with pytest.raises(maps.MapProblem, match="Hezekiah 3:2.*John 3:99"):
    maps.upload(picture(tmp_path), "map.png", "test-map-bad", {**DETAILS, "verses": "Acts 13:4; Hezekiah 3:2; John 3:99"})
  with pytest.raises(maps.MapProblem, match="somewhere"):
    maps.parse_verses("Acts 13:4 somewhere")
  with pytest.raises(maps.MapProblem, match="Acts 13:4-2"):
    maps.parse_verses("Acts 13:4-2")
  assert maps.get_map("test-map-bad", published_only=False) is None


def test_a_pdf_page_is_drawn_and_another_page_can_be_chosen(tmp_path, folder):
  found = maps.upload(pdf(tmp_path), "atlas.pdf", "test-map-atlas", DETAILS, pdf_page=2)
  assert found["kind"] == "pdf" and found["pdf_page"] == 2 and found["width"] == 5000 and found["height"] == 3000
  changed = maps.update_details("test-map-atlas", {**DETAILS, "title": "Atlas"}, pdf_page=1)
  assert changed["pdf_page"] == 1 and changed["title"] == "Atlas" and changed["height"] == 3750
  with pytest.raises(maps.MapProblem, match="no page 3"):
    maps.update_details("test-map-atlas", DETAILS, pdf_page=3)


def test_other_kinds_of_picture_are_taken_by_their_contents(tmp_path, folder):
  for kind, extension in (("JPEG", ".jpg"), ("TIFF", ".tif"), ("GIF", ".gif"), ("WEBP", ".webp")):
    path = picture(tmp_path, "upload" + extension, kind=kind)
    found = maps.upload(path, "upload" + extension, "test-map-kind", DETAILS)
    assert found["file_type"] == extension[1:].upper() and found["width"] == 800
  # A JPEG with a .png name is kept as what it is.
  found = maps.upload(picture(tmp_path, "real.jpg", kind="JPEG"), "named.png", "test-map-kind", DETAILS)
  assert found["file_type"] == "JPG" and not (folder / "test-map-kind.webp").exists()
  with pytest.raises(maps.MapProblem, match="must be a picture"):
    maps.upload(picture(tmp_path), "map.svg", "test-map-kind", DETAILS)
  bad = tmp_path / "bad.png"
  bad.write_text("<html>not a picture</html>")
  with pytest.raises(maps.MapProblem, match="not a real PNG"):
    maps.upload(bad, "bad.png", "test-map-kind", DETAILS)


def test_keywords_and_verses_are_kept_when_not_given(tmp_path):
  maps.upload(picture(tmp_path), "map.png", "test-map-keep", DETAILS)
  found = maps.upload(picture(tmp_path), "map.png", "test-map-keep", {"title": "Again"})
  assert found["keywords"] == "missionary, Barnabas" and len(found["verses"]) == 2
  found = maps.update_details("test-map-keep", {"title": "Again", "keywords": "", "verses": ""})
  assert found["keywords"] == "" and found["verses"] == [] and found["verses_text"] == ""


def test_search_finds_title_keywords_description_and_a_verse(tmp_path):
  published_map(tmp_path)

  def ids(query, mode="all"):
    response = client.get("/search-maps", params={"query": query, "match_mode": mode})
    assert response.status_code == 200
    return [result["id"] for result in response.json()["results"]]

  assert "test-map-journey" in ids("journey")
  assert "test-map-journey" in ids("barnabas missionary")
  assert "test-map-journey" in ids("Galatia")
  assert "test-map-journey" in ids("Acts 13:9")
  assert "test-map-journey" not in ids("Acts 15:1")
  assert "test-map-journey" not in ids("journey zebra")
  assert "test-map-journey" in ids("journey zebra", "any")


def test_search_everything_has_a_maps_group(tmp_path):
  published_map(tmp_path)
  groups = client.get("/search-everything", params={"query": "Barnabas missionary"}).json()["groups"]
  map_group = next(group for group in groups if group["kind"] == "map")
  assert "test-map-journey" in [hit["id"] for hit in map_group["results"]]


def test_marks_need_a_login_and_the_flag(tmp_path):
  map_id = published_map(tmp_path)
  assert client.get(f"/maps/{map_id}/marks").status_code == 401
  assert client.post(f"/maps/{map_id}/marks", json={"kind": "note", "body": "Hi"}).status_code == 401
  sign_up("ann", allowed=False)
  assert client.get("/account/me").json()["user"]["use_maps"] is False
  assert client.get(f"/maps/{map_id}/marks").status_code == 403
  assert client.post(f"/maps/{map_id}/marks", json={"kind": "note", "body": "Hi"}).status_code == 403
  assert client.put("/map-marks/1", json={"body": "Hi"}).status_code == 403
  assert client.delete("/map-marks/1").status_code == 403


def test_a_member_keeps_notes_pins_and_routes_that_only_they_see(tmp_path):
  map_id = published_map(tmp_path)
  sign_up("ann")
  note = client.post(f"/maps/{map_id}/marks", json={"kind": "note", "body": "  Read Acts 13:4 first  "}).json()["mark"]
  assert note["body"] == "Read Acts 13:4 first" and note["references"] == [[5, 14, "44:13:4"]]
  pin = client.post(f"/maps/{map_id}/marks", json={"kind": "pin", "x": 0.25, "y": 1, "body": "Paphos"}).json()["mark"]
  assert (pin["x"], pin["y"]) == (0.25, 1.0)
  route = client.post(
    f"/maps/{map_id}/marks",
    json={"kind": "route", "points": [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]], "colour": "#1F6FB2"},
  ).json()["mark"]
  assert route["name"] == "Route" and route["colour"] == "#1f6fb2" and route["points"][1] == [0.3, 0.4]
  assert [mark["kind"] for mark in client.get(f"/maps/{map_id}/marks").json()["marks"]] == ["note", "pin", "route"]

  moved = client.put(f"/map-marks/{pin['id']}", json={"x": 0.5, "y": 0.5, "body": "Salamis", "kind": "route"}).json()["mark"]
  assert moved["kind"] == "pin" and moved["x"] == 0.5 and moved["body"] == "Salamis"

  sign_up("ben")
  assert client.get(f"/maps/{map_id}/marks").json()["marks"] == []
  assert client.put(f"/map-marks/{pin['id']}", json={"x": 0, "y": 0}).status_code == 404
  assert client.delete(f"/map-marks/{pin['id']}").status_code == 404

  log_in("ann")
  assert client.delete(f"/map-marks/{pin['id']}").json() == {"deleted": True}
  assert len(client.get(f"/maps/{map_id}/marks").json()["marks"]) == 2


def test_marks_are_checked(tmp_path):
  map_id = published_map(tmp_path)
  sign_up("ann")

  def status(mark):
    return client.post(f"/maps/{map_id}/marks", json=mark).status_code

  assert status({"kind": "note", "body": "  "}) == 422
  assert status({"kind": "pin", "x": 1.5, "y": 0}) == 422
  assert status({"kind": "pin", "x": 0.5}) == 422
  assert status({"kind": "route", "points": [[0.1, 0.1]]}) == 422
  assert status({"kind": "route", "points": [[0.1, 0.1], [0.2, 2]]}) == 422
  assert status({"kind": "route", "points": [[0.1, 0.1], [0.2, 0.2]], "colour": "#123456"}) == 422
  assert status({"kind": "note", "body": "x" * 5001}) == 422
  assert client.get("/maps/test-map-none/marks").status_code == 404
  maps.set_published(map_id, False)
  assert status({"kind": "note", "body": "Hidden"}) == 404


def test_deleting_the_map_or_the_user_deletes_the_marks(tmp_path, folder):
  map_id = published_map(tmp_path)
  user_id = sign_up("ann")
  client.post(f"/maps/{map_id}/marks", json={"kind": "note", "body": "Mine"})
  assert maps.get_map(map_id, published_only=False)["mark_count"] == 1
  maps.delete(map_id)
  assert list(folder.iterdir()) == []
  with connect() as connection:
    assert connection.execute("SELECT count(*) FROM map_marks WHERE user_id = %s", (user_id,)).fetchone()[0] == 0


def run_tool(*arguments, details=None):
  completed = subprocess.run(
    [sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True,
    input=json.dumps(details) if details is not None else "",
  )
  return completed.returncode, json.loads(completed.stdout)


def test_the_tool_uploads_changes_publishes_and_deletes(tmp_path, folder):
  code, answer = run_tool("upload", str(picture(tmp_path)), "--name=map.png", "--id=test-map-tool", details=DETAILS)
  assert code == 0 and answer["map"]["is_published"] is False and answer["map"]["file_present"] is True
  code, answer = run_tool("check-verses", details={"verses": "Acts 13:4; Nowhere 1:1"})
  assert code == 1 and "Nowhere 1:1" in answer["error"]
  code, answer = run_tool("update", "--id=test-map-tool", details={**DETAILS, "title": "Changed"})
  assert code == 0 and answer["map"]["title"] == "Changed"
  assert run_tool("publish", "--id=test-map-tool")[1]["map"]["is_published"] is True
  assert "test-map-tool" in [entry["id"] for entry in run_tool("list")[1]["maps"]]
  assert run_tool("delete", "--id=test-map-tool")[0] == 0
  assert run_tool("get", "--id=test-map-tool")[0] == 1


def test_site_users_can_set_the_flag():
  import site_users

  user = site_users.create_user("cal@maps-test.example", PASSWORD, True, False, use_maps=True)
  assert user["use_maps"] is True and user["map_mark_count"] == 0
  assert site_users.update_user(user["id"], use_maps=False)["use_maps"] is False


def test_a_large_display_copy_is_a_valid_webp(tmp_path, folder):
  maps.upload(picture(tmp_path, size=(1200, 900)), "map.png", "test-map-webp", DETAILS)
  with Image.open(io.BytesIO((folder / "test-map-webp-display.webp").read_bytes())) as shown:
    assert shown.format == "WEBP" and shown.size == (1200, 900)


def test_a_mark_is_shared_only_with_the_members_chosen(tmp_path):
  map_id = published_map(tmp_path)
  ann = sign_up("ann")
  with connect() as connection:
    connection.execute("UPDATE users SET first_name = 'Ann', last_name = 'Lee' WHERE id = %s", (ann,))
  sign_up("ben")
  sign_up("dan")
  sign_up("cal", allowed=False)

  log_in("ann")
  # Someone without the maps flag, or with no account, or oneself, cannot be chosen: nothing is saved.
  for address in ("cal@maps-test.example", "nobody@maps-test.example", "ann@maps-test.example"):
    refused = client.post(f"/maps/{map_id}/marks", json={"kind": "note", "body": "x", "shared_with": [address]})
    assert refused.status_code == 422 and address in refused.json()["detail"]
  shared = client.post(
    f"/maps/{map_id}/marks",
    json={"kind": "pin", "x": 0.5, "y": 0.5, "body": "For Ben", "shared_with": [" BEN@maps-test.example "]},
  ).json()["mark"]
  assert shared["shared_with"] == [{"email": "ben@maps-test.example", "name": "A member"}] and shared["author"] == "Ann Lee"
  client.post(f"/maps/{map_id}/marks", json={"kind": "note", "body": "Private"})
  assert len(client.get(f"/maps/{map_id}/marks").json()["marks"]) == 2

  log_in("ben")
  own = client.post(f"/maps/{map_id}/marks", json={"kind": "note", "body": "Ben's own"}).json()["mark"]
  seen = client.get(f"/maps/{map_id}/marks").json()["marks"]
  # The member's own first, then what was shared with them; never another member's private ones, nor who else
  # a mark is shared with.
  assert [(mark["body"], mark["is_mine"]) for mark in seen] == [("Ben's own", True), ("For Ben", False)]
  assert seen[1]["author"] == "Ann Lee" and seen[1]["shared_with"] == []
  assert client.put(f"/map-marks/{shared['id']}", json={"x": 0, "y": 0}).status_code == 404
  assert client.delete(f"/map-marks/{shared['id']}").status_code == 404

  log_in("dan")
  assert client.get(f"/maps/{map_id}/marks").json()["marks"] == []

  # An author who loses the flag stops sharing; a change without shared_with keeps them; [] takes them back.
  with connect() as connection:
    connection.execute("UPDATE users SET use_maps = false WHERE id = %s", (ann,))
  log_in("ben")
  assert [mark["id"] for mark in client.get(f"/maps/{map_id}/marks").json()["marks"]] == [own["id"]]
  with connect() as connection:
    connection.execute("UPDATE users SET use_maps = true WHERE id = %s", (ann,))
  log_in("ann")
  kept = client.put(f"/map-marks/{shared['id']}", json={"x": 0.4, "y": 0.4, "body": "For Ben"}).json()["mark"]
  assert len(kept["shared_with"]) == 1
  assert client.put(f"/map-marks/{shared['id']}", json={"x": 0.4, "y": 0.4, "body": "For Ben", "shared_with": []}).json()["mark"]["shared_with"] == []
  log_in("ben")
  assert len(client.get(f"/maps/{map_id}/marks").json()["marks"]) == 1


def test_a_routes_points_can_be_changed(tmp_path):
  map_id = published_map(tmp_path)
  sign_up("ann")
  route = client.post(f"/maps/{map_id}/marks", json={"kind": "route", "points": [[0.1, 0.1], [0.2, 0.2]], "name": "Way"}).json()["mark"]
  changed = client.put(
    f"/map-marks/{route['id']}", json={"points": [[0.1, 0.1], [0.3, 0.25], [0.4, 0.4]], "name": "Way", "colour": "#2e8540"}
  ).json()["mark"]
  assert changed["points"] == [[0.1, 0.1], [0.3, 0.25], [0.4, 0.4]] and changed["colour"] == "#2e8540"
  assert client.put(f"/map-marks/{route['id']}", json={"points": [[0.1, 0.1]], "name": "Way"}).status_code == 422

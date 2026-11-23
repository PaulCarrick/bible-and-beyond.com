"""Tests for members' head shots (head_shots.py): uploaded on My account, shown only to the member. The pictures are
made here with Pillow; the folder is a temporary one (conftest.py). Their own @head-shots-test.example accounts."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import accounts
import head_shots
import site_users
from main import app
from search import connect

PASSWORD = "correct horse battery"
DOMAIN = "head-shots-test.example"
client = TestClient(app)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
  monkeypatch.setattr(accounts, "send_plain_message", lambda address, subject, text: None)

  def clear():
    with connect() as connection:
      connection.execute(f"DELETE FROM users WHERE email LIKE '%@{DOMAIN}'")

  clear()
  client.cookies.clear()
  yield
  clear()


def sign_up(name="ann"):
  client.cookies.clear()
  response = client.post(
    "/account/register",
    json={"email": f"{name}@{DOMAIN}", "password": PASSWORD, "password_confirmation": PASSWORD, "first_name": name.title()},
  )
  return response.json()["user"]


def photo(width=800, height=600, kind="JPEG", exif=False) -> bytes:
  picture = Image.new("RGB", (width, height), (200, 40, 40))
  output = io.BytesIO()
  if exif:
    information = Image.Exif()
    information[0x010F] = "Phone maker"  # Make
    picture.save(output, kind, exif=information.tobytes())
  else:
    picture.save(output, kind)
  return output.getvalue()


def test_a_head_shot_is_squared_stripped_and_shown_only_to_its_member():
  user = sign_up()
  assert user["head_shot"] is None
  answer = client.put("/account/head-shot", content=photo(exif=True))
  assert answer.status_code == 200
  address = answer.json()["user"]["head_shot"]
  assert address == "/account/head-shot?v=1"
  picture = client.get(address)
  assert picture.status_code == 200 and picture.headers["content-type"] == "image/webp"
  assert "private" in picture.headers["cache-control"]
  kept = Image.open(io.BytesIO(picture.content))
  assert kept.size == (head_shots.SIZE, head_shots.SIZE) and not kept.getexif()
  assert client.get("/account/me").json()["user"]["head_shot"] == address

  # Another member gets their own (none), never this one; nobody logged out gets any.
  sign_up("bob")
  assert client.get("/account/head-shot").status_code == 404
  client.cookies.clear()
  assert client.get("/account/head-shot").status_code == 401


def test_a_new_picture_gets_a_new_version_and_remove_takes_it_away():
  user = sign_up()
  client.put("/account/head-shot", content=photo(kind="PNG"))
  assert client.put("/account/head-shot", content=photo()).json()["user"]["head_shot"].endswith("v=2")
  assert client.delete("/account/head-shot").json()["user"]["head_shot"] is None
  assert not head_shots.path_for(user["id"]).exists()
  assert client.get("/account/head-shot").status_code == 404


def test_what_is_not_a_picture_or_too_large_is_refused():
  sign_up()
  refused = client.put("/account/head-shot", content=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
  assert refused.status_code == 422 and "not a picture" in refused.json()["detail"]
  assert client.put("/account/head-shot", content=b"").status_code == 422
  large = client.put("/account/head-shot", content=b"x" * (head_shots.MAX_UPLOAD_BYTES + 1))
  assert large.status_code == 422 and "too large" in large.json()["detail"]
  assert client.get("/account/me").json()["user"]["head_shot"] is None


def test_deleting_the_account_on_site_users_deletes_the_picture():
  user = sign_up()
  client.put("/account/head-shot", content=photo())
  assert head_shots.path_for(user["id"]).exists()
  site_users.delete_user(user["id"])
  assert not head_shots.path_for(user["id"]).exists()

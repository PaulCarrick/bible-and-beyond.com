"""Tests for the verse a day pictures (verse_images.py, scripts/manage_verse_images.py). They use the real table
with their own ids (starting "test-vi-") and a temporary folder (conftest.py), and remove their rows after."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

import verse_images
from search import connect
from verse_images import ImageProblem

TOOL = Path(__file__).resolve().parent.parent / "scripts" / "manage_verse_images.py"


@pytest.fixture(autouse=True)
def clean():
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM verse_images WHERE id LIKE 'test-vi-%'")

  clear()
  yield
  clear()


def picture(tmp_path, name="sunrise.jpg", size=(1200, 800), kind="JPEG"):
  path = tmp_path / name
  Image.new("RGB", size, (220, 160, 90)).save(path, kind)
  return path


def test_an_upload_keeps_the_file_and_a_thumbnail_and_is_in_use(tmp_path):
  image = verse_images.upload(picture(tmp_path), "sunrise.jpg", "test-vi-sunrise", "  Sunrise   over hills ")
  assert image["title"] == "Sunrise over hills" and image["in_use"] and image["file_present"]
  assert (image["width"], image["height"], image["media_type"]) == (1200, 800, "image/jpeg")
  folder = verse_images.images_folder()
  assert (folder / "test-vi-sunrise.jpg").read_bytes() == picture(tmp_path).read_bytes()
  with Image.open(folder / "test-vi-sunrise-thumbnail.webp") as thumbnail:
    assert thumbnail.width == verse_images.THUMBNAIL_WIDTH
  listed = [each for each in verse_images.list_images(with_thumbnails=True) if each["id"] == "test-vi-sunrise"]
  assert listed[0]["thumbnail"].startswith("data:image/webp;base64,")


def test_the_type_is_what_the_file_holds(tmp_path):
  # A PNG named .jpg is kept as a PNG.
  image = verse_images.upload(picture(tmp_path, "field.png", kind="PNG"), "field.jpg", "test-vi-field", "Field")
  assert image["file_name"] == "test-vi-field.png" and image["media_type"] == "image/png"
  webp = verse_images.upload(picture(tmp_path, "sea.webp", kind="WEBP"), "sea.webp", "test-vi-sea", "Sea")
  assert webp["media_type"] == "image/webp"


@pytest.mark.parametrize(
  "name, contents, fragment",
  [
    ("notes.txt", b"hello", "PNG, JPEG or WebP"),
    ("fake.jpg", b"this is not a picture", "not a real JPG"),
    ("empty.png", b"", "empty"),
  ],
)
def test_bad_files_are_refused(tmp_path, name, contents, fragment):
  path = tmp_path / name
  path.write_bytes(contents)
  with pytest.raises(ImageProblem, match=fragment):
    verse_images.upload(path, name, "test-vi-bad", "Bad")
  assert verse_images.get_image("test-vi-bad") is None


def test_a_damaged_picture_and_a_bad_id_or_name_are_refused(tmp_path):
  damaged = tmp_path / "broken.png"
  damaged.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
  with pytest.raises(ImageProblem, match="could not be read"):
    verse_images.upload(damaged, "broken.png", "test-vi-broken", "Broken")
  with pytest.raises(ImageProblem, match="id"):
    verse_images.upload(picture(tmp_path), "a.jpg", "Bad Id!", "A")
  with pytest.raises(ImageProblem, match="name"):
    verse_images.upload(picture(tmp_path), "a.jpg", "test-vi-a", "   ")


def test_an_id_in_use_is_refused(tmp_path):
  verse_images.upload(picture(tmp_path), "a.jpg", "test-vi-a", "A")
  with pytest.raises(ImageProblem, match="already"):
    verse_images.upload(picture(tmp_path), "a.jpg", "test-vi-a", "A again")


def test_out_of_use_pictures_are_never_chosen_and_delete_removes_the_files(tmp_path):
  verse_images.upload(picture(tmp_path), "a.jpg", "test-vi-a", "A")
  verse_images.upload(picture(tmp_path), "b.jpg", "test-vi-b", "B")
  assert verse_images.set_in_use("test-vi-b", False)["in_use"] is False

  class Chooser:
    def choice(self, images):
      self.offered = [image["id"] for image in images]
      return images[0]

  chooser = Chooser()
  image, path = verse_images.random_image(chooser)
  assert "test-vi-a" in chooser.offered and "test-vi-b" not in chooser.offered and path.is_file()

  verse_images.delete("test-vi-a")
  folder = verse_images.images_folder()
  assert not (folder / "test-vi-a.jpg").exists() and not (folder / "test-vi-a-thumbnail.webp").exists()
  with pytest.raises(ImageProblem, match="does not exist"):
    verse_images.delete("test-vi-a")
  with pytest.raises(ImageProblem, match="does not exist"):
    verse_images.set_in_use("test-vi-a", True)


def test_a_picture_can_be_renamed_and_keeps_its_id_and_files(tmp_path):
  verse_images.upload(picture(tmp_path), "a.jpg", "test-vi-a", "Sunrise")
  renamed = verse_images.rename("test-vi-a", "  Sunrise   over the lake ")
  assert renamed["title"] == "Sunrise over the lake" and renamed["id"] == "test-vi-a" and renamed["file_present"]
  assert (verse_images.images_folder() / "test-vi-a.jpg").is_file()
  with pytest.raises(ImageProblem):
    verse_images.rename("test-vi-a", "   ")
  assert verse_images.get_image("test-vi-a")["title"] == "Sunrise over the lake"
  with pytest.raises(ImageProblem, match="does not exist"):
    verse_images.rename("test-vi-gone", "New")


def test_a_preview_is_a_larger_copy_made_on_request(tmp_path):
  verse_images.upload(picture(tmp_path, size=(3000, 2000)), "big.jpg", "test-vi-big", "Big")
  shown = verse_images.preview("test-vi-big")
  assert shown["preview"].startswith("data:image/webp;base64,")
  import base64
  from io import BytesIO

  with Image.open(BytesIO(base64.b64decode(shown["preview"].split(",", 1)[1]))) as copy:
    assert copy.size == (1600, 1067)
  assert sorted(path.name for path in verse_images.images_folder().iterdir() if path.name.startswith("test-vi-big")) == [
    "test-vi-big-thumbnail.webp", "test-vi-big.jpg"]
  with pytest.raises(ImageProblem, match="does not exist"):
    verse_images.preview("test-vi-gone")


def run_tool(*arguments, environment):
  completed = subprocess.run([sys.executable, str(TOOL), *arguments], capture_output=True, text=True, env=environment)
  return completed.returncode, json.loads(completed.stdout)


def test_the_tool(tmp_path):
  import os

  environment = {**os.environ}
  path = picture(tmp_path)
  code, answer = run_tool("upload", str(path), "--name=sunrise.jpg", "--id=test-vi-tool", "--title=Sunrise", environment=environment)
  assert code == 0 and answer["image"]["id"] == "test-vi-tool"
  code, answer = run_tool("list", environment=environment)
  assert any(each["id"] == "test-vi-tool" and each["thumbnail"] for each in answer["images"])
  code, answer = run_tool("rename", "--id=test-vi-tool", "--title=Morning sky", environment=environment)
  assert code == 0 and answer["image"]["title"] == "Morning sky"
  code, answer = run_tool("rename", "--id=test-vi-tool", "--title=Sunrise", environment=environment)
  code, answer = run_tool("preview", "--id=test-vi-tool", environment=environment)
  assert code == 0 and answer["image"]["preview"].startswith("data:image/webp")
  code, answer = run_tool("unuse", "--id=test-vi-tool", environment=environment)
  assert answer["image"]["in_use"] is False
  code, answer = run_tool("upload", str(path), "--name=sunrise.jpg", "--id=test-vi-tool", "--title=Again", environment=environment)
  assert code == 1 and answer == {"ok": False, "error": "There is already a picture with the id “test-vi-tool”."}
  code, answer = run_tool("delete", "--id=test-vi-tool", environment=environment)
  assert code == 0 and answer["image"]["title"] == "Sunrise"

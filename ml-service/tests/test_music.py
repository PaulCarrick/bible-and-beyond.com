"""Tests for the Christian music section. They use the real music_tracks table and remove only their own songs
(ids starting test-music-); the music folder is a temporary one for each test."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import music
import service_settings
from main import app
from search import connect

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage_music.py"
MP4 = b"\x00\x00\x00\x18ftypisom" + bytes(range(256)) * 40
MP3 = b"ID3\x04\x00\x00" + bytes(range(256)) * 20
DETAILS = {"title": "  Amazing   Grace ", "author": "John Newton", "lyrics": "Amazing grace! How sweet the sound\r\nThat saved a wretch like me!\n\n\n\nI once was lost"}


@pytest.fixture(autouse=True)
def folder(tmp_path, monkeypatch):
  def clear():
    with connect() as connection:
      connection.execute("DELETE FROM music_tracks WHERE id LIKE 'test-music-%'")

  monkeypatch.setenv("MUSIC_FOLDER", str(tmp_path / "music"))
  clear()
  yield tmp_path / "music"
  clear()


def write(tmp_path, name, content):
  path = tmp_path / name
  path.write_bytes(content)
  return path


def test_a_song_is_hidden_until_published_and_its_file_can_be_played_in_parts(tmp_path, folder):
  song = music.upload(write(tmp_path, "upload.bin", MP4), "Amazing Grace.MP4", "test-music-grace", DETAILS)
  assert song["title"] == "Amazing Grace" and song["kind"] == "video" and song["is_published"] is False
  assert song["lyrics"] == "Amazing grace! How sweet the sound\nThat saved a wretch like me!\n\nI once was lost"
  assert (folder / "test-music-grace.mp4").read_bytes() == MP4
  assert "test-music-grace" not in [entry["id"] for entry in client.get("/music").json()]
  assert client.get("/music/test-music-grace/file").status_code == 404

  music.set_published("test-music-grace", True)
  listed = [entry for entry in client.get("/music").json() if entry["id"] == "test-music-grace"]
  assert listed and "file_name" not in listed[0]
  whole = client.get("/music/test-music-grace/file")
  assert whole.status_code == 200 and whole.content == MP4 and whole.headers["content-type"] == "video/mp4"
  part = client.get("/music/test-music-grace/file", headers={"Range": "bytes=0-99"})
  assert part.status_code == 206 and part.content == MP4[:100]


def test_uploading_again_replaces_the_file_keeps_the_state_and_removes_an_old_kind(tmp_path, folder):
  music.upload(write(tmp_path, "a", MP4), "a.mp4", "test-music-well", DETAILS)
  music.set_published("test-music-well", True)
  song = music.upload(write(tmp_path, "b", MP3), "b.mp3", "test-music-well", {**DETAILS, "title": "It Is Well"})
  assert song["is_published"] is True and song["kind"] == "audio" and song["title"] == "It Is Well"
  assert not (folder / "test-music-well.mp4").exists() and (folder / "test-music-well.mp3").exists()

  changed = music.update_details("test-music-well", {"title": "It Is Well with My Soul", "author": "", "lyrics": ""})
  assert changed["title"] == "It Is Well with My Soul" and changed["file_present"] is True

  music.delete("test-music-well")
  assert not (folder / "test-music-well.mp3").exists()
  with pytest.raises(music.MusicProblem):
    music.delete("test-music-well")


def test_wrong_files_and_details_are_refused(tmp_path):
  with pytest.raises(music.MusicProblem, match="MP3"):
    music.upload(write(tmp_path, "a", MP4), "a.wav", "test-music-a", DETAILS)
  with pytest.raises(music.MusicProblem, match="not a real MP4"):
    music.upload(write(tmp_path, "b", b"<html>not a video</html>"), "b.mp4", "test-music-b", DETAILS)
  with pytest.raises(music.MusicProblem, match="not a real MP3"):
    music.upload(write(tmp_path, "c", MP4), "c.mp3", "test-music-c", DETAILS)
  with pytest.raises(music.MusicProblem, match="id"):
    music.upload(write(tmp_path, "d", MP4), "d.mp4", "Bad Id!", DETAILS)
  with pytest.raises(music.MusicProblem, match="title"):
    music.upload(write(tmp_path, "e", MP4), "e.mp4", "test-music-e", {"title": " "})


def test_the_search_finds_words_titles_and_authors_of_published_songs(tmp_path):
  music.upload(write(tmp_path, "a", MP4), "a.mp4", "test-music-grace", DETAILS)
  hidden = client.get("/search-music", params={"query": "wretch"}).json()
  assert all(result["id"] != "test-music-grace" for result in hidden["results"])

  music.set_published("test-music-grace", True)
  found = client.get("/search-music", params={"query": "wretch"}).json()
  ours = [result for result in found["results"] if result["id"] == "test-music-grace"]
  assert ours and "\u0001wretch\u0002" in ours[0]["text"]
  assert any(result["id"] == "test-music-grace" for result in client.get("/search-music", params={"query": "Newton"}).json()["results"])
  assert client.get("/search-music", params={"query": "!!"}).status_code == 422


def test_the_drupal_tool_reads_the_details_on_its_input(tmp_path, folder):
  def run(*arguments, details=None):
    completed = subprocess.run(
      [sys.executable, str(SCRIPT), *arguments], input=json.dumps(details) if details is not None else "",
      capture_output=True, text=True, check=False,
    )
    return completed.returncode, json.loads(completed.stdout)

  status, uploaded = run("upload", str(write(tmp_path, "upload.bin", MP3)), "--name=Hymn.mp3", "--id=test-music-tool", details=DETAILS)
  assert status == 0 and uploaded["song"]["file_name"] == "test-music-tool.mp3" and uploaded["song"]["file_present"] is True
  assert (folder / "test-music-tool.mp3").exists()
  status, listing = run("list")
  assert any(song["id"] == "test-music-tool" for song in listing["songs"])
  status, published = run("publish", "--id=test-music-tool")
  assert published["song"]["is_published"] is True
  status, refused = run("update", "--id=test-music-tool", details={"title": ""})
  assert status == 1 and refused == {"ok": False, "error": "Fill in the title."}
  status, deleted = run("delete", "--id=test-music-tool")
  assert status == 0 and not (folder / "test-music-tool.mp3").exists()


def test_the_music_folder_setting_must_be_a_full_path_it_can_write_to(tmp_path, monkeypatch):
  monkeypatch.delenv("MUSIC_FOLDER")
  assert service_settings.get_setting("music_folder").endswith("ml-service/data/music")
  with pytest.raises(service_settings.ServiceSettingsProblem, match="full path"):
    service_settings.save({"music_folder": "music"}, [])
  new_folder = tmp_path / "volume" / "music"
  described = service_settings.save({"music_folder": str(new_folder) + "/"}, [])
  assert described["settings"]["music_folder"]["value"] == str(new_folder) and new_folder.is_dir()
  assert music.music_folder() == new_folder


PDF = b"%PDF-1.4\n" + b"0" * 500
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 500
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 500


def test_the_words_can_be_a_pdf_or_a_picture_shown_below_the_text(tmp_path, folder):
  song = music.upload(write(tmp_path, "a", MP4), "a.mp4", "test-music-words", DETAILS, (write(tmp_path, "w", PDF), "Words.PDF"))
  assert song["words_kind"] == "pdf" and song["words_file_present"] is True and song["lyrics"]
  assert (folder / "test-music-words-words.pdf").read_bytes() == PDF
  assert client.get("/music/test-music-words/words").status_code == 404  # hidden

  music.set_published("test-music-words", True)
  listed = [entry for entry in client.get("/music").json() if entry["id"] == "test-music-words"][0]
  assert listed["words_kind"] == "pdf" and "words_file_name" not in listed
  served = client.get("/music/test-music-words/words")
  assert served.status_code == 200 and served.content == PDF and served.headers["content-type"] == "application/pdf"

  # A picture replaces the PDF (the old file goes); a JPEG named .jpeg is kept as .jpg.
  changed = music.update_details("test-music-words", DETAILS, (write(tmp_path, "j", JPEG), "scan.jpeg"))
  assert changed["words_kind"] == "image" and changed["words_file_name"] == "test-music-words-words.jpg"
  assert not (folder / "test-music-words-words.pdf").exists()
  assert client.get("/music/test-music-words/words").headers["content-type"] == "image/jpeg"

  # Uploading the song again without a words file keeps it; removing it brings back the typed words.
  assert music.upload(write(tmp_path, "b", MP4), "b.mp4", "test-music-words", DETAILS)["words_kind"] == "image"
  removed = music.update_details("test-music-words", DETAILS, remove_words=True)
  assert removed["words_kind"] is None and not (folder / "test-music-words-words.jpg").exists()

  music.update_details("test-music-words", DETAILS, (write(tmp_path, "p", PNG), "page.png"))
  music.delete("test-music-words")
  assert list(folder.iterdir()) == []


def test_remove_words_takes_away_only_the_words_file(tmp_path, folder):
  music.upload(write(tmp_path, "a", MP4), "a.mp4", "test-music-remove", DETAILS, (write(tmp_path, "w", PDF), "Words.pdf"))
  music.set_published("test-music-remove", True)
  answer = subprocess.run(
    [sys.executable, str(SCRIPT), "remove-words", "--id=test-music-remove"], capture_output=True, text=True,
    env={**__import__("os").environ, "MUSIC_FOLDER": str(folder)},
  )
  song = json.loads(answer.stdout)["song"]
  assert answer.returncode == 0 and song["words_kind"] is None
  assert song["is_published"] is True and song["title"] == "Amazing Grace" and song["lyrics"] and song["file_present"]
  assert not (folder / "test-music-remove-words.pdf").exists() and (folder / "test-music-remove.mp4").exists()
  assert client.get("/music/test-music-remove/words").status_code == 404
  # Nothing to remove, or no such song, is refused.
  with pytest.raises(music.MusicProblem, match="no PDF or picture"):
    music.remove_words_file("test-music-remove")
  with pytest.raises(music.MusicProblem, match="does not exist"):
    music.remove_words_file("test-music-none")


def test_a_wrong_words_file_is_refused_and_nothing_is_saved(tmp_path, folder):
  with pytest.raises(music.MusicProblem, match="PDF"):
    music.upload(write(tmp_path, "a", MP4), "a.mp4", "test-music-bad", DETAILS, (write(tmp_path, "s", b"<svg/>"), "words.svg"))
  with pytest.raises(music.MusicProblem, match="not a real PNG"):
    music.upload(write(tmp_path, "b", MP4), "b.mp4", "test-music-bad", DETAILS, (write(tmp_path, "f", PDF), "words.png"))
  assert music.get_song("test-music-bad", published_only=False) is None and not folder.exists() or list(folder.iterdir()) == []


def test_keywords_are_found_by_the_search_kept_when_left_out_and_changed_when_given(tmp_path):
  music.upload(write(tmp_path, "a", MP4), "a.mp4", "test-music-grace", {**DETAILS, "keywords": "recovery, hurts habits"})
  music.set_published("test-music-grace", True)
  song = music.get_song("test-music-grace")
  assert song["keywords"] == "recovery, hurts habits"

  # Found by a keyword that is not in the title, author or words, and listed first.
  found = client.get("/search-music", params={"query": "recovery"}).json()
  assert found["results"][0]["id"] == "test-music-grace"
  assert client.get("/search-music", params={"query": "hurts habits", "match_mode": "phrase"}).json()["total"] >= 1

  # Uploading again or changing the details without keywords keeps them; giving them changes them.
  music.upload(write(tmp_path, "b", MP4), "b.mp4", "test-music-grace", DETAILS)
  music.update_details("test-music-grace", {"title": "Amazing Grace"})
  assert music.get_song("test-music-grace")["keywords"] == "recovery, hurts habits"
  music.update_details("test-music-grace", {"title": "Amazing Grace", "keywords": ""})
  assert music.get_song("test-music-grace")["keywords"] == ""
  assert all(result["id"] != "test-music-grace" for result in client.get("/search-music", params={"query": "recovery"}).json()["results"])
  with pytest.raises(music.MusicProblem, match="keywords"):
    music.update_details("test-music-grace", {"title": "Amazing Grace", "keywords": "x" * 501})


# --- Spotify items (2026-11-19) ------------------------------------------------------------------------------


def test_spotify_links_are_read_in_their_usual_forms():
  playlist = "37i9dQZF1DXcBWIGoYBM5M"
  for link in (
    f"https://open.spotify.com/playlist/{playlist}?si=abc123",
    f"https://open.spotify.com/intl-de/playlist/{playlist}",
    f"https://open.spotify.com/embed/playlist/{playlist}",
    f"spotify:playlist:{playlist}",
  ):
    assert music.check_spotify_link(link) == f"playlist/{playlist}"
  assert music.check_spotify_link("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC") == "track/4uLU6hMCjMI75M1A2tKUQC"
  for bad in ("", "https://example.org/playlist/37i9dQZF1DXcBWIGoYBM5M", "https://open.spotify.com/user/someone",
              "https://open.spotify.com/playlist/short", "javascript:alert(1)", "https://open.spotify.com.evil.example/playlist/37i9dQZF1DXcBWIGoYBM5M"):
    with pytest.raises(music.MusicProblem, match="Spotify link"):
      music.check_spotify_link(bad)


def test_a_spotify_item_is_listed_searched_and_played_by_spotify_not_by_a_file(folder):
  item = music.add_spotify("test-music-spotify", "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=x",
                           {"title": "Hymns of praise", "author": "A Spotify playlist", "keywords": "worship hymns"})
  assert item["kind"] == "spotify" and item["is_published"] is False and item["file_present"] is True
  assert item["spotify_embed"] == "https://open.spotify.com/embed/playlist/37i9dQZF1DXcBWIGoYBM5M"
  music.set_published("test-music-spotify", True)
  listed = [entry for entry in client.get("/music").json() if entry["id"] == "test-music-spotify"]
  assert listed and listed[0]["kind"] == "spotify" and listed[0]["spotify_link"] == "playlist/37i9dQZF1DXcBWIGoYBM5M"
  assert client.get("/music/test-music-spotify/file").status_code == 404
  found = client.get("/search-music", params={"query": "worship", "match_mode": "all", "page": 1, "per_page": 10}).json()
  assert any(hit["id"] == "test-music-spotify" and hit["kind"] == "spotify" for hit in found["results"])
  # Its link and details change; a song with a file keeps its id from becoming one; delete has no file to remove.
  changed = music.update_details("test-music-spotify", {"title": "Hymns", "spotify_link": "spotify:album:1ATL5GLyefJaxhQzSPVrLX"})
  assert changed["title"] == "Hymns" and changed["spotify_link"] == "album/1ATL5GLyefJaxhQzSPVrLX"
  music.upload(write(folder.parent, "a.mp3", MP3), "a.mp3", "test-music-file", DETAILS)
  with pytest.raises(music.MusicProblem, match="song with a file"):
    music.add_spotify("test-music-file", "spotify:track:4uLU6hMCjMI75M1A2tKUQC", {"title": "x"})
  assert music.delete("test-music-spotify")["id"] == "test-music-spotify"


def test_the_tool_adds_a_spotify_item():
  completed = subprocess.run(
    [sys.executable, str(SCRIPT), "spotify", "--id=test-music-tool-spotify"],
    input=json.dumps({"spotify_link": "https://open.spotify.com/album/1ATL5GLyefJaxhQzSPVrLX", "title": "An album"}),
    capture_output=True, text=True, check=False,
  )
  assert completed.returncode == 0 and json.loads(completed.stdout)["song"]["spotify_link"] == "album/1ATL5GLyefJaxhQzSPVrLX"
  completed = subprocess.run(
    [sys.executable, str(SCRIPT), "spotify", "--id=test-music-tool-bad"], input=json.dumps({"spotify_link": "https://example.org", "title": "x"}),
    capture_output=True, text=True, check=False,
  )
  assert completed.returncode == 1 and "Spotify link" in json.loads(completed.stdout)["error"]

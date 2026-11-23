"""Shared test set-up."""

import pytest


@pytest.fixture(autouse=True)
def no_saved_service_settings(tmp_path, monkeypatch):
  """Tests never read or write the real service settings file (the keys saved on the Site settings screen),
  so the keys come from the environment the tests set, as before."""
  monkeypatch.setenv("SERVICE_SETTINGS_FILE", str(tmp_path / "service_settings.json"))


@pytest.fixture(autouse=True)
def no_real_site_icons(tmp_path, monkeypatch):
  """Tests never read, replace or remove the real site icons (data/site-icons)."""
  monkeypatch.setenv("SITE_ICONS_FOLDER", str(tmp_path / "site-icons"))
  monkeypatch.setenv("KINDLE_COVERS_FOLDER", str(tmp_path / "kindle-covers"))
  monkeypatch.setenv("HEAD_SHOTS_FOLDER", str(tmp_path / "head-shots"))
  monkeypatch.setenv("MESSAGE_FILES_FOLDER", str(tmp_path / "message-files"))


@pytest.fixture(autouse=True)
def no_real_library_images(tmp_path, monkeypatch):
  """Tests never write pictures of uploaded documents into the real data/library-images."""
  monkeypatch.setenv("LIBRARY_IMAGES_FOLDER", str(tmp_path / "library-images"))
  monkeypatch.setenv("LIBRARY_PAGES_FOLDER", str(tmp_path / "library-pages"))


@pytest.fixture(autouse=True)
def no_real_maps(tmp_path, monkeypatch):
  """Tests never write map files into the real data/maps."""
  monkeypatch.setenv("MAPS_FOLDER", str(tmp_path / "maps"))


@pytest.fixture(autouse=True)
def no_real_verse_images(tmp_path, monkeypatch):
  """Tests never write pictures into the real data/verse-images."""
  monkeypatch.setenv("VERSE_IMAGES_FOLDER", str(tmp_path / "verse-images"))
  monkeypatch.setenv("MESSAGE_CARDS_FOLDER", str(tmp_path / "message-cards"))

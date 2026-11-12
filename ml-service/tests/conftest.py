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

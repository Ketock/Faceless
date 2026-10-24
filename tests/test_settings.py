"""Tests for faceless.settings — JSON-persisted application settings."""

from __future__ import annotations

import json
import logging

from faceless import paths
from faceless.settings import Settings, load, save


def test_load_returns_defaults_when_file_missing():
    settings = load()
    assert settings == Settings()
    assert settings.library_paths == []
    assert settings.show_concept_previews is True
    assert settings.confirm_before_apply is True
    assert settings.enable_live_reload is True
    assert settings.debug_logging is False


def test_save_and_load_roundtrip():
    settings = Settings(
        library_paths=["/tmp/rices", "~/my-rices"],
        backup_dir="/tmp/backups",
        show_concept_previews=False,
        confirm_before_apply=False,
        enable_live_reload=False,
        detect_detailed_components=False,
        debug_logging=True,
    )
    assert save(settings) is True
    assert paths.settings_file().is_file()
    loaded = load()
    assert loaded == settings
    assert loaded.library_paths == ["/tmp/rices", "~/my-rices"]


def test_corrupt_settings_file_falls_back_to_defaults_with_warning(caplog):
    path = paths.settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json at all", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        settings = load()
    assert settings == Settings()
    assert any("Could not load settings" in r.getMessage() for r in caplog.records)


def test_non_object_settings_root_falls_back_to_defaults(caplog):
    path = paths.settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert load() == Settings()
    assert any("settings root must be an object" in r.getMessage() for r in caplog.records)


def test_unknown_and_null_keys_are_ignored():
    path = paths.settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"library_paths": ["/tmp/rices"], "bogus_key": 1, "debug_logging": None}),
        encoding="utf-8",
    )
    settings = load()
    assert settings.library_paths == ["/tmp/rices"]
    assert settings.debug_logging is False  # None does not clobber the default
    assert not hasattr(settings, "bogus_key") or settings.__dict__.get("bogus_key") is None


def test_save_overwrites_previous_content():
    save(Settings(library_paths=["/old"]))
    save(Settings(library_paths=["/new"]))
    assert load().library_paths == ["/new"]

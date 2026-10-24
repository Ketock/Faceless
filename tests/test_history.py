"""Tests for faceless.core.history — append-only operation log."""

from __future__ import annotations

import logging
import time

import pytest

from faceless import paths
from faceless.core import history


def make_entry(**overrides) -> history.HistoryEntry:
    defaults = dict(
        ts=time.time(),
        operation="apply",
        profile_id="rice",
        profile_name="Rice",
        status="success",
        detail="",
        backup_id="",
        files_touched=0,
        warnings=[],
    )
    defaults.update(overrides)
    return history.HistoryEntry(**defaults)


def test_record_and_read_roundtrip():
    entry = make_entry(
        detail="did a thing",
        backup_id="20240101-000000-abcd1234",
        files_touched=3,
        warnings=["watch out"],
    )
    assert history.record(entry) is True
    entries = history.read_all()
    assert len(entries) == 1
    back = entries[0]
    assert back.operation == "apply"
    assert back.profile_id == "rice"
    assert back.profile_name == "Rice"
    assert back.status == "success"
    assert back.detail == "did a thing"
    assert back.backup_id == "20240101-000000-abcd1234"
    assert back.files_touched == 3
    assert back.warnings == ["watch out"]
    assert back.ts == pytest.approx(entry.ts)


def test_read_all_missing_file_returns_empty():
    assert history.read_all() == []
    assert history.last_entry() is None
    assert history.recent() == []


def test_corrupt_history_returns_empty_with_warning(caplog):
    path = paths.history_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{definitely not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert history.read_all() == []
    assert any("history unreadable" in r.getMessage() for r in caplog.records)


def test_max_entries_trims_oldest(monkeypatch):
    monkeypatch.setattr(history, "MAX_ENTRIES", 3)
    for i in range(5):
        assert history.record(make_entry(detail=f"entry-{i}")) is True
    entries = history.read_all()
    assert len(entries) == 3
    assert [e.detail for e in entries] == ["entry-2", "entry-3", "entry-4"]


def test_recent_returns_newest_first():
    for i in range(4):
        history.record(make_entry(detail=f"entry-{i}"))
    recent = history.recent(limit=3)
    assert [e.detail for e in recent] == ["entry-3", "entry-2", "entry-1"]
    assert history.last_entry().detail == "entry-3"


def test_record_survives_unwritable_location(monkeypatch, tmp_path):
    # point history_file() at a path whose parent is a *file* → mkdir fails
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    monkeypatch.setattr(paths, "state_home", lambda: blocker)
    assert history.record(make_entry()) is False

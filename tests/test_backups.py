"""Tests for faceless.core.backups — BackupStore create/list/get/restore."""

from __future__ import annotations

import os
import stat

import pytest

from faceless.core.backups import BackupError, BackupStore


@pytest.fixture
def store() -> BackupStore:
    return BackupStore()


def test_create_archives_existing_file_and_get_roundtrips(store, tmp_path):
    dest = tmp_path / ".config" / "hypr" / "hyprland.conf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("original")
    record = store.create([dest], profile_id="rice", profile_name="Rice")
    assert record.entries, "existing file must be archived"
    entry = record.entries[0]
    assert entry.dest == str(dest)
    archived = store.root / record.id / "content" / entry.archived
    assert archived.is_file()
    assert archived.read_text() == "original"

    fetched = store.get(record.id)
    assert fetched.id == record.id
    assert fetched.profile_id == "rice"
    assert fetched.operation == "apply"
    assert len(fetched.entries) == 1
    assert fetched.summary().endswith("1 file(s)")


def test_create_skips_missing_and_dangling_destinations(store, tmp_path):
    missing = tmp_path / "does-not-exist.conf"
    dangling = tmp_path / "dangling.conf"
    dangling.symlink_to(tmp_path / "nowhere")
    record = store.create([missing, dangling], profile_id="rice", profile_name="Rice")
    assert record.entries == []
    assert (store.root / record.id / "backup.json").is_file()


def test_restore_of_nonexistent_id_raises(store):
    with pytest.raises(BackupError, match="not found"):
        store.restore("00000000-nope")


def test_restore_of_empty_backup_raises(store, tmp_path):
    record = store.create([], profile_id="rice", profile_name="Rice")
    with pytest.raises(BackupError, match="no restorable files"):
        store.restore(record.id)


def test_restore_puts_original_back_byte_for_byte_and_preserves_mode(store, tmp_path):
    dest = tmp_path / ".config" / "kitty" / "kitty.conf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("ORIGINAL\n")
    os.chmod(dest, 0o600)
    backup = store.create([dest], profile_id="rice", profile_name="Rice")

    dest.write_text("REPLACED BY APPLY\n")
    store.restore(backup.id)

    assert dest.read_text() == "ORIGINAL\n"
    assert stat.S_IMODE(dest.stat().st_mode) == 0o600


def test_restore_creates_pre_restore_backup(store, tmp_path):
    dest = tmp_path / ".config" / "kitty" / "kitty.conf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("ORIGINAL\n")
    backup = store.create([dest], profile_id="rice", profile_name="Rice")
    dest.write_text("NEW\n")
    store.restore(backup.id)

    listed = store.list()
    pre_restores = [r for r in listed if r.operation == "pre-restore"]
    assert pre_restores, "restore must snapshot current state first"
    current = store.get(pre_restores[0].id)
    assert current.entries[0].dest == str(dest)
    archived = store.root / current.id / "content" / current.entries[0].archived
    assert archived.read_text() == "NEW\n"


def test_list_skips_corrupt_and_missing_metadata(store):
    good = store.create([], profile_id="a", profile_name="A")
    corrupt = store.create([], profile_id="b", profile_name="B")
    missing_meta = store.create([], profile_id="c", profile_name="C")
    (store.root / corrupt.id / "backup.json").write_text("{not json", encoding="utf-8")
    (store.root / missing_meta.id / "backup.json").unlink()
    (store.root / "stray-dir").mkdir()
    (store.root / "stray-file.txt").write_text("x", encoding="utf-8")

    listed = store.list()
    assert [r.id for r in listed] == [good.id]
    # corrupt/missing entries were skipped without raising


def test_list_on_empty_root(store, tmp_path):
    assert BackupStore(root=tmp_path / "nope").list() == []


def test_invalid_backup_id_rejected(store):
    for bad in ("", "../evil", "a/b", "a\\b"):
        with pytest.raises(BackupError, match="invalid backup id"):
            store.get(bad)


def test_inspect_returns_record_and_existing_content(store, tmp_path):
    dest = tmp_path / "conf.ini"
    dest.write_text("data")
    record = store.create([dest], profile_id="rice", profile_name="Rice")
    got, files = store.inspect(record.id)
    assert got.id == record.id
    assert len(files) == 1
    assert files[0].read_text() == "data"

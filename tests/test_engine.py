"""Tests for faceless.core.engine — the apply pipeline and its guarantees."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from faceless import paths
from faceless.core import history
from faceless.core.backups import BackupError, BackupStore
from faceless.core.engine import ApplyEngine, ApplyFailure, active_rice
from faceless.core.schema import load_profile

pytestmark = pytest.mark.usefixtures("build_profile", "manifest_dict", "default_files")


@pytest.fixture
def lib(tmp_path) -> Path:
    return tmp_path / "lib"


def config_dest(rel: str = "hypr/hyprland.conf") -> Path:
    return paths.config_home() / rel


def last_history_entry() -> history.HistoryEntry | None:
    entries = history.read_all()
    return entries[-1] if entries else None


# ------------------------------------------------------------- fresh apply


def test_apply_to_fresh_system_writes_files_and_active_rice(
    lib, build_profile, manifest_dict, default_files
):
    doc = manifest_dict()
    doc["files"] = {
        "config": {"hypr/hyprland.conf": "files/hyprland.conf"},
        "home": {".zshrc": "files/zshrc"},
    }
    files = {**default_files, "files/zshrc": "export EDITOR=vi\n"}
    profile = load_profile(build_profile(lib, doc, files))

    result = ApplyEngine().apply(profile)

    assert result.ok is True
    assert result.error == ""
    assert result.applied_files == 2
    assert result.backed_up == 0
    conf = paths.config_home() / "hypr" / "hyprland.conf"
    assert conf.read_text() == "monitor=,preferred,auto,1\n"
    zshrc = paths.home() / ".zshrc"
    assert zshrc.read_text() == "export EDITOR=vi\n"

    active = active_rice()
    assert active is not None
    assert active.profile_id == "test-rice"

    entry = last_history_entry()
    assert entry is not None
    assert (entry.operation, entry.status, entry.profile_id) == ("apply", "success", "test-rice")


def test_apply_fresh_creates_no_backup_files(lib, build_profile, manifest_dict, default_files):
    profile = load_profile(build_profile(lib, manifest_dict(), default_files))
    result = ApplyEngine().apply(profile)
    assert result.ok
    record = BackupStore().get(result.backup_id)
    assert record.entries == []


# ----------------------------------------------- apply over existing config


def test_apply_over_existing_preserves_original_in_backup_and_restores(
    lib, build_profile, manifest_dict, default_files
):
    dest = config_dest()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("ORIGINAL USER CONFIG\n")

    profile = load_profile(build_profile(lib, manifest_dict(), default_files))
    engine = ApplyEngine()
    result = engine.apply(profile)

    assert result.ok
    assert result.backed_up == 1
    assert dest.read_text() == "monitor=,preferred,auto,1\n"

    # original byte-for-byte inside the backup store
    record = engine.backups.get(result.backup_id)
    assert record.entries[0].dest == str(dest)
    archived = engine.backups.root / record.id / "content" / record.entries[0].archived
    assert archived.read_text() == "ORIGINAL USER CONFIG\n"

    # restore puts the original back and snapshots the new state first
    store = BackupStore()
    before = {r.id for r in store.list()}
    store.restore(result.backup_id)
    assert dest.read_text() == "ORIGINAL USER CONFIG\n"
    pre_restores = [r for r in store.list() if r.operation == "pre-restore" and r.id not in before]
    assert pre_restores, "restore must have created a pre-restore backup"


# ------------------------------------------------------------------ rollback


def test_mid_apply_failure_rolls_back_existing_file(
    lib, tmp_path, monkeypatch, build_profile, manifest_dict, default_files
):
    doc = manifest_dict()
    doc["files"] = {
        "config": {"hypr/hyprland.conf": "files/hyprland.conf"},
        "home": {".zshrc": "files/zshrc"},
    }
    files = {**default_files, "files/zshrc": "export EDITOR=vi\n"}
    profile = load_profile(build_profile(lib, doc, files))

    existing = config_dest()
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("ORIGINAL USER CONFIG\n")

    def apply_first_then_fail(self, plan, staged):
        planned = plan.files[0]
        source = staged[(planned.spec.dest_root, planned.spec.dest_rel)]
        dest = Path(planned.dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)  # simulate the first file being written
        raise RuntimeError("simulated mid-apply failure")

    monkeypatch.setattr(ApplyEngine, "_apply_files", apply_first_then_fail)

    with pytest.raises(ApplyFailure, match="rolled back"):
        ApplyEngine().apply(profile)

    # the overwritten user file is restored byte-for-byte…
    assert existing.read_text() == "ORIGINAL USER CONFIG\n"
    # …and the never-applied second file did not land.
    assert not (paths.home() / ".zshrc").exists()

    entry = last_history_entry()
    assert entry is not None
    assert entry.operation == "rollback"
    assert entry.status == "success"
    assert "simulated mid-apply failure" in entry.detail
    assert entry.backup_id


def test_rollback_removes_new_files_created_by_the_failed_apply(
    lib, build_profile, manifest_dict, default_files, monkeypatch
):
    """A mid-apply failure must also delete files the apply already created
    from scratch — leaving them behind would silently keep profile data."""
    files = {**default_files, "files/extra.conf": b"brand new\n"}
    doc = manifest_dict()
    doc["files"]["config"]["kitty/new-file.conf"] = "files/extra.conf"
    profile = load_profile(build_profile(lib, doc, files))

    def apply_all_then_fail(self, plan, staged):
        # write BOTH files, then explode — the new file must be rolled back too
        for planned in plan.files:
            source = staged[(planned.spec.dest_root, planned.spec.dest_rel)]
            dest = Path(planned.dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        raise RuntimeError("boom after everything was written")

    monkeypatch.setattr(ApplyEngine, "_apply_files", apply_all_then_fail)

    with pytest.raises(ApplyFailure):
        ApplyEngine().apply(profile)

    assert not (paths.config_home() / "kitty" / "new-file.conf").exists()
    assert not (paths.config_home() / "kitty" / "kitty.conf").exists()
    entry = last_history_entry()
    assert entry.status == "success" and entry.operation == "rollback"


def test_rollback_failure_is_recorded_as_failure(
    lib, build_profile, manifest_dict, default_files, monkeypatch
):
    """If rollback itself cannot restore a file, history must say 'failure'."""
    import faceless.core.engine as engine_mod

    profile = load_profile(build_profile(lib, manifest_dict(), default_files))
    real_rollback = engine_mod.ApplyEngine._rollback_from_backup

    def failing_rollback(self, backup, plan):
        restored, failures = real_rollback(self, backup, plan)
        return restored, failures + ["simulated rollback failure: disk full"]

    monkeypatch.setattr(ApplyEngine, "_rollback_from_backup", failing_rollback)
    monkeypatch.setattr(ApplyEngine, "_apply_files", lambda self, plan, staged: 1 / 0)

    with pytest.raises(ApplyFailure, match="ROLLBACK ISSUES"):
        ApplyEngine().apply(profile)
    entry = last_history_entry()
    assert entry.operation == "rollback"
    assert entry.status == "failure"
    assert "simulated rollback failure" in entry.detail


def test_rollback_restore_is_atomic_and_keeps_backup(
    lib, build_profile, manifest_dict, default_files, monkeypatch
):
    profile = load_profile(build_profile(lib, manifest_dict(), default_files))
    existing = paths.config_home() / "kitty" / "kitty.conf"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("USER ORIGINAL\n")
    os.chmod(existing, 0o600)

    monkeypatch.setattr(ApplyEngine, "_apply_files", lambda self, plan, staged: 1 / 0)
    with pytest.raises(ApplyFailure):
        ApplyEngine().apply(profile)

    assert existing.read_text() == "USER ORIGINAL\n"
    assert (existing.stat().st_mode & 0o777) == 0o600
    # No temp rollback files left behind.
    leftovers = [p for p in existing.parent.iterdir() if p.name.startswith(".fl-rb-")]
    assert leftovers == []
    # The backup is kept for manual recovery even after successful rollback.
    from faceless.core.backups import BackupStore

    assert BackupStore().list()


# --------------------------------------------------------- staging safety


def test_payload_symlink_escaping_profile_dir_is_refused(
    lib, tmp_path, build_profile, manifest_dict, default_files
):
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("top secret\n")
    profile_dir = build_profile(lib, manifest_dict(), default_files)
    payload = profile_dir / "files" / "hyprland.conf"
    payload.unlink()
    payload.symlink_to(outside)

    profile = load_profile(profile_dir)  # schema accepts it (symlink looks like a file)

    with pytest.raises(ApplyFailure, match="escapes profile dir"):
        ApplyEngine().apply(profile)
    assert not config_dest().exists()


def test_payload_deleted_between_scan_and_apply_fails_cleanly(
    lib, build_profile, manifest_dict, default_files
):
    profile_dir = build_profile(lib, manifest_dict(), default_files)
    profile = load_profile(profile_dir)
    (profile_dir / "files" / "hyprland.conf").unlink()

    with pytest.raises(ApplyFailure, match="staging failed"):
        ApplyEngine().apply(profile)
    assert not config_dest().exists()


def test_payload_with_traversal_declared_in_manifest_never_reaches_plan(
    lib, build_profile, manifest_dict, default_files
):
    # schema-level rejection: the payload itself must be a relative path.
    doc = manifest_dict()
    doc["files"] = {"config": {"hypr/hyprland.conf": "../outside.conf"}}
    profile_dir = build_profile(lib, doc, default_files)
    with pytest.raises(Exception, match="'.' or '..'"):
        load_profile(profile_dir)


# ----------------------------------------------------------------- wallpaper


def test_manifest_wallpaper_traversal_rejected_at_schema(
    lib, build_profile, manifest_dict, default_files
):
    doc = manifest_dict(wallpaper="../evil.png")
    profile_dir = build_profile(lib, doc, default_files)
    with pytest.raises(Exception, match="'.' or '..'"):
        load_profile(profile_dir)


def test_wallpaper_file_deleted_before_apply_is_a_warning(
    lib, build_profile, manifest_dict, default_files
):
    doc = manifest_dict(wallpaper="assets/wall.png")
    profile_dir = build_profile(lib, doc, {**default_files, "assets/wall.png": b"\x89PNG"})
    (profile_dir / "assets" / "wall.png").unlink()
    profile = load_profile(profile_dir)

    result = ApplyEngine().apply(profile)

    assert result.ok is True
    assert any("could not stage wallpaper" in w for w in result.warnings)


def test_wallpaper_symlink_escape_is_skipped_with_warning(
    lib, tmp_path, build_profile, manifest_dict, default_files
):
    outside = tmp_path / "elsewhere.png"
    outside.write_bytes(b"\x89PNG")
    doc = manifest_dict(wallpaper="assets/wall.png")
    profile_dir = build_profile(lib, doc, default_files)
    wall = profile_dir / "assets" / "wall.png"
    wall.parent.mkdir(parents=True, exist_ok=True)
    wall.symlink_to(outside)
    profile = load_profile(profile_dir)

    result = ApplyEngine().apply(profile)
    assert result.ok is True
    assert any("escapes profile dir" in w for w in result.warnings)


def test_wallpaper_is_stored_in_data_dir_even_without_backend(
    lib, tmp_path, monkeypatch, build_profile, manifest_dict, default_files
):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    doc = manifest_dict(wallpaper="assets/wall.png")
    profile = load_profile(
        build_profile(lib, doc, {**default_files, "assets/wall.png": b"\x89PNG"})
    )
    ApplyEngine().apply(profile)
    # Fixed, engine-controlled name: untrusted profile wallpaper filenames must
    # never reach command/script contexts (e.g. the Plasma evaluateScript path).
    stored = paths.data_home() / "faceless" / "wallpapers" / "test-rice" / "wallpaper.png"
    assert stored.read_bytes() == b"\x89PNG"
    # A hostile wallpaper filename gets its extension normalized away.
    doc2 = manifest_dict(wallpaper="assets/evil');.png")
    profile2 = load_profile(
        build_profile(lib, doc2, {**default_files, "assets/evil');.png": b"\x89PNG"})
    )
    ApplyEngine().apply(profile2)
    stored2 = paths.data_home() / "faceless" / "wallpapers" / "test-rice" / "wallpaper.png"
    assert stored2.is_file()


# -------------------------------------------------------------------- reload


def test_live_reload_disabled_yields_warning(lib, build_profile, manifest_dict, default_files):
    profile = load_profile(build_profile(lib, manifest_dict(), default_files))
    result = ApplyEngine(live_reload=False).apply(profile)
    assert result.ok
    assert any("live reload disabled" in w for w in result.warnings)


def test_reload_disabled_does_not_crash(lib, build_profile, manifest_dict, default_files):
    profile = load_profile(build_profile(lib, manifest_dict(), default_files))
    result = ApplyEngine(live_reload=False, set_wallpaper=False).apply(profile)
    assert result.ok
    assert result.reloaded == []


# ---------------------------------------------------------- backup failures


def test_backup_failure_aborts_before_anything_is_applied(
    lib, monkeypatch, build_profile, manifest_dict, default_files
):
    profile = load_profile(build_profile(lib, manifest_dict(), default_files))
    engine = ApplyEngine()

    def broken_create(*args, **kwargs):
        raise BackupError("disk full")

    monkeypatch.setattr(engine.backups, "create", broken_create)
    dest = config_dest()

    with pytest.raises(ApplyFailure, match="backup failed"):
        engine.apply(profile)
    assert not dest.exists()


def test_backup_failure_keeps_existing_file_untouched(
    lib, monkeypatch, build_profile, manifest_dict, default_files
):
    dest = config_dest()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("ORIGINAL\n")
    profile = load_profile(build_profile(lib, manifest_dict(), default_files))
    engine = ApplyEngine()

    def broken_create(*args, **kwargs):
        raise BackupError("disk full")

    monkeypatch.setattr(engine.backups, "create", broken_create)
    with pytest.raises(ApplyFailure, match="backup failed"):
        engine.apply(profile)
    assert dest.read_text() == "ORIGINAL\n"


# --------------------------------------------------------------- plan blocks


def test_apply_refuses_blocked_plan(lib, tmp_path, monkeypatch):
    from faceless.core import schema

    evil = schema.Profile(
        directory=tmp_path,
        id="evil-rice",
        name="Evil",
        version="1.0.0",
        description="attempts traversal",
        author="",
        tags=(),
        targets=("hyprland",),
        requires=(),
        files=(schema.FileSpec("config", "../escape.conf", "files/x.conf"),),
        previews=(),
        wallpaper=None,
        source="test",
    )
    result = ApplyEngine().apply(evil)
    assert result.ok is False
    assert "plan blocked" in result.error
    assert not (paths.config_home() / "escape.conf").exists()

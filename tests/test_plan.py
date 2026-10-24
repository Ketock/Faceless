"""Tests for faceless.core.plan — planned-change calculation and compatibility."""

from __future__ import annotations

import pytest

from faceless import paths
from faceless.core import detection, schema
from faceless.core.plan import Compat, build_plan

pytestmark = pytest.mark.usefixtures("build_profile", "manifest_dict", "default_files")


@pytest.fixture
def profile(tmp_path, build_profile, manifest_dict, default_files):
    from faceless.core.schema import load_profile

    return load_profile(build_profile(tmp_path / "lib", manifest_dict(), default_files))


def _clear_session_env(monkeypatch):
    """Make session detection see a bare environment (process probing is
    already neutralised by the autouse fixture)."""
    for key in (
        "HYPRLAND_INSTANCE_SIGNATURE",
        "SWAYSOCK",
        "KDE_FULL_SESSION",
        "XDG_CURRENT_DESKTOP",
        "XDG_SESSION_TYPE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_fresh_destination_has_no_overwrite_warning(profile):
    plan = build_plan(profile)
    assert not plan.blocked
    assert len(plan.files) == 1
    planned = plan.files[0]
    assert planned.exists is False
    assert planned.problem == ""
    assert planned.dest == str(paths.config_home() / "hypr" / "hyprland.conf")
    assert plan.warnings == []


def test_existing_destination_flags_overwrite_and_backup_warning(profile, tmp_path):
    dest = paths.config_home() / "hypr" / "hyprland.conf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("user's own config")
    plan = build_plan(profile)
    planned = plan.files[0]
    assert planned.exists is True
    assert any("backed up and replaced" in w for w in plan.warnings)


def test_symlinked_destination_counts_as_existing(profile, tmp_path):
    real = paths.config_home() / "elsewhere.conf"
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text("x")
    dest = paths.config_home() / "hypr" / "hyprland.conf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(real)
    plan = build_plan(profile)
    assert plan.files[0].exists is True


def test_ancestor_symlink_escape_is_a_file_problem_not_block(
    tmp_path, monkeypatch, build_profile, manifest_dict, default_files
):
    from faceless.core.schema import load_profile

    dest = paths.config_home() / "hypr"
    paths.config_home().mkdir(parents=True, exist_ok=True)
    outside = f"/tmp/nonexistent-faceless-{id(dest):x}"
    dest.symlink_to(outside)
    p = load_profile(build_profile(tmp_path / "lib", manifest_dict(), default_files))
    plan = build_plan(p)
    assert not plan.blocked
    assert plan.files[0].problem == "ancestor symlink escapes $HOME"


def test_plan_blocked_for_unsafe_destination(tmp_path, monkeypatch):
    # schema.parse_manifest would already reject a `../` destination, so the
    # plan-level guard is exercised with a hand-built Profile (defence in
    # depth: engine also validates at apply time).
    _clear_session_env(monkeypatch)
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
    plan = build_plan(evil)
    assert plan.blocked is True
    assert "unsafe destination" in plan.blocked_reason
    assert plan.files[0].problem != ""
    assert plan.files[0].dest == ""


def test_missing_dependency_reported(
    profile, manifest_dict, tmp_path, build_profile, default_files
):
    from faceless.core.schema import load_profile

    doc = manifest_dict(requires=["definitely-not-a-real-binary-xyz"])
    p = load_profile(build_profile(tmp_path / "lib", doc, default_files))
    plan = build_plan(p)
    assert plan.missing_requires == ["definitely-not-a-real-binary-xyz"]
    assert any("missing optional/required dependency" in w for w in plan.warnings)


def test_compositor_mismatch_is_partial(
    tmp_path, monkeypatch, build_profile, manifest_dict, default_files
):
    from faceless.core.schema import load_profile

    _clear_session_env(monkeypatch)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    doc = manifest_dict(id="sway-rice", targets=["sway"])
    p = load_profile(build_profile(tmp_path / "lib", doc, default_files))
    plan = build_plan(p)
    assert plan.compatibility is Compat.PARTIAL
    assert plan.compat_reasons
    assert "sway" in plan.compat_reasons[0]


def test_compositor_match_is_full(
    tmp_path, monkeypatch, build_profile, manifest_dict, default_files
):
    from faceless.core.schema import load_profile

    _clear_session_env(monkeypatch)
    monkeypatch.setenv("SWAYSOCK", "/run/sway-ipc.sock")
    doc = manifest_dict(id="sway-rice", targets=["sway"])
    p = load_profile(build_profile(tmp_path / "lib", doc, default_files))
    plan = build_plan(p)
    assert plan.compatibility is Compat.FULL
    assert plan.compat_reasons == []


def test_no_compositor_targets_is_full(profile):
    plan_profile = schema.Profile(
        directory=profile.directory,
        id=profile.id,
        name=profile.name,
        version=profile.version,
        description=profile.description,
        author=profile.author,
        tags=profile.tags,
        targets=("kitty", "waybar"),
        requires=profile.requires,
        files=profile.files,
        previews=profile.previews,
        wallpaper=profile.wallpaper,
        source=profile.source,
    )
    plan2 = build_plan(plan_profile)
    assert plan2.compatibility is Compat.FULL


def test_plan_records_session(profile, monkeypatch):
    _clear_session_env(monkeypatch)
    plan = build_plan(profile)
    assert isinstance(plan.session, detection.Session)
    assert plan.session.kind == "tty"

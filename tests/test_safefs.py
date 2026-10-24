"""Tests for faceless.core.safefs — destination resolution and safe writes."""

from __future__ import annotations

import os
import uuid

import pytest

from faceless import paths
from faceless.core import safefs


def test_resolve_dest_maps_roots_under_faceless_home(tmp_path):
    assert paths.home() == tmp_path
    assert safefs.resolve_dest("config", "hypr/hyprland.conf") == (
        tmp_path / ".config" / "hypr" / "hyprland.conf"
    )
    assert safefs.resolve_dest("home", ".zshrc") == tmp_path / ".zshrc"
    assert safefs.resolve_dest("share", "fonts/x.ttf") == (
        tmp_path / ".local" / "share" / "fonts" / "x.ttf"
    )
    assert safefs.resolve_dest("state", "cache.dat") == (
        tmp_path / ".local" / "state" / "cache.dat"
    )


@pytest.mark.parametrize(
    "root, rel",
    [
        ("config", "/etc/passwd"),            # absolute
        ("config", "hypr/../../etc/passwd"),  # traversal
        ("config", "hypr\\evil.conf"),        # backslash
        ("config", ""),                       # empty
        ("config", "   "),                    # whitespace only
        ("config", "hypr/"),                  # trailing slash
        ("config", "hypr/../."),              # dot components
        ("media", "x.conf"),                  # unknown root
        ("", "x.conf"),                       # empty root
    ],
)
def test_resolve_dest_rejects_unsafe_paths(root, rel):
    with pytest.raises(safefs.UnsafePathError):
        safefs.resolve_dest(root, rel)


def test_ensure_within_returns_resolved_path_for_normal_dest(tmp_path):
    dest = paths.config_home() / "hypr" / "hyprland.conf"
    assert safefs.ensure_within(dest, "config") == dest.resolve()


def test_ensure_within_rejects_symlink_escape(tmp_path):
    escape_target = f"/tmp/nonexistent-faceless-{uuid.uuid4().hex}"
    link = paths.config_home() / "escape"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(escape_target)
    with pytest.raises(safefs.UnsafePathError, match="escapes its root"):
        safefs.ensure_within(link, "config")


def test_ensure_within_allows_symlink_into_root(tmp_path):
    # A symlink resolving to a sibling *inside* the config root is fine.
    real = paths.config_home() / "hypr" / "real.conf"
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text("ok")
    link = paths.config_home() / "alias.conf"
    link.symlink_to(real)
    assert safefs.ensure_within(link, "config") == real.resolve()


def test_parent_symlink_escape_detects_ancestor_pointing_outside_home(tmp_path):
    dest = paths.config_home() / "hypr" / "hyprland.conf"
    paths.config_home().mkdir(parents=True, exist_ok=True)
    outside_target = f"/tmp/nonexistent-faceless-{uuid.uuid4().hex}"
    dest.parent.symlink_to(outside_target)  # ancestor symlink → outside $HOME
    assert safefs.parent_symlink_escape(dest) is True


def test_parent_symlink_escape_false_for_plain_dirs(tmp_path):
    dest = paths.config_home() / "hypr" / "hyprland.conf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    assert safefs.parent_symlink_escape(dest) is False


def test_parent_symlink_escape_false_for_symlink_within_home(tmp_path):
    # An ancestor symlink that stays inside $HOME is acceptable.
    real_dir = paths.home() / ".config" / "hypr-real"
    real_dir.mkdir(parents=True, exist_ok=True)
    alias = paths.home() / ".config" / "hypr"
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.symlink_to(real_dir)
    dest = alias / "hyprland.conf"
    assert safefs.parent_symlink_escape(dest) is False


def test_atomic_replace_swaps_content(tmp_path):
    dest = tmp_path / "dest.conf"
    dest.write_text("old")
    source = tmp_path / "staged.conf"
    source.write_text("new")
    safefs.atomic_replace(source, dest)
    assert dest.read_text() == "new"
    assert not source.exists()


def test_atomic_replace_preserves_sane_mode(tmp_path):
    dest = tmp_path / "dest.conf"
    dest.write_text("old")
    source = tmp_path / "staged.conf"
    source.write_text("new")
    os.chmod(source, 0o600)
    safefs.atomic_replace(source, dest)
    assert (dest.stat().st_mode & 0o777) == 0o600


def test_atomic_replace_coerces_odd_modes(tmp_path):
    dest = tmp_path / "dest.conf"
    source = tmp_path / "staged.conf"
    source.write_text("new")
    os.chmod(source, 0o777)  # outside the allowed band → coerced to 0o644
    safefs.atomic_replace(source, dest)
    assert (dest.stat().st_mode & 0o777) == 0o644


def test_atomic_replace_creates_missing_parents(tmp_path):
    dest = tmp_path / "deep" / "nested" / "dest.conf"
    source = tmp_path / "staged.conf"
    source.write_text("new")
    safefs.atomic_replace(source, dest)
    assert dest.read_text() == "new"


def test_snapshot_metadata(tmp_path):
    f = tmp_path / "f.conf"
    f.write_text("12345")
    meta = safefs.snapshot_metadata(f)
    assert meta["mode"] == f.stat().st_mode & 0o777
    assert meta["size"] == 5
    assert meta["mtime"] == f.stat().st_mtime

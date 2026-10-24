"""Tests for faceless.core.schema — manifest parsing and validation."""

from __future__ import annotations

import pytest

from faceless.core.schema import (
    MANIFEST_NAME,
    ProfileError,
    load_profile,
    parse_manifest,
)

pytestmark = pytest.mark.usefixtures("build_profile", "manifest_dict", "default_files")


@pytest.fixture
def valid_profile_dir(tmp_path, build_profile, manifest_dict, default_files):
    return build_profile(tmp_path / "lib", manifest_dict(), default_files)


# ---------------------------------------------------------------- happy path


def test_minimal_manifest_loads(valid_profile_dir, manifest_dict, default_files):
    profile = load_profile(valid_profile_dir, source="test")
    assert profile.id == "test-rice"
    assert profile.name == "Test Rice"
    assert profile.version == "1.0.0"
    assert profile.description == "A rice used by tests"
    assert profile.author == ""
    assert profile.tags == ()
    assert profile.targets == ("hyprland",)
    assert profile.requires == ()
    assert profile.previews == ()
    assert profile.wallpaper is None
    assert profile.source == "test"
    assert len(profile.files) == 1
    spec = profile.files[0]
    assert (spec.dest_root, spec.dest_rel, spec.payload) == (
        "config",
        "hypr/hyprland.conf",
        "files/hyprland.conf",
    )
    assert spec.display_dest() == "config:hypr/hyprland.conf"
    assert profile.payload_path(spec) == valid_profile_dir / "files/hyprland.conf"
    assert profile.preview_paths() == []


def test_full_manifest_loads(tmp_path, build_profile, manifest_dict, default_files):
    doc = manifest_dict(
        id="full-rice",
        author="someone",
        tags=["dark", "minimal"],
        previews=["assets/preview.png"],
        wallpaper="assets/wall.png",
        requires=["waybar"],
        targets=["hyprland", "waybar", "kitty"],
    )
    doc["files"] = {
        "config": {"hypr/hyprland.conf": "files/hyprland.conf"},
        "home": {".zshrc": "files/zshrc"},
    }
    files = {
        **default_files,
        "files/zshrc": "export EDITOR=vi\n",
        "assets/preview.png": b"\x89PNG-fake",
        "assets/wall.png": b"\x89PNG-wall",
    }
    profile = load_profile(build_profile(tmp_path / "lib", doc, files))
    assert profile.author == "someone"
    assert profile.tags == ("dark", "minimal")
    assert profile.previews == ("assets/preview.png",)
    assert profile.wallpaper == "assets/wall.png"
    assert profile.requires == ("waybar",)
    assert profile.targets == ("hyprland", "waybar", "kitty")
    assert len(profile.files) == 2
    assert profile.preview_paths() == [profile.directory / "assets/preview.png"]


# ------------------------------------------------------------ required fields


def test_missing_required_field_rejected(valid_profile_dir, manifest_dict):
    for missing in ("id", "name", "version", "description"):
        doc = manifest_dict()
        doc.pop(missing)
        with pytest.raises(ProfileError, match=missing):
            parse_manifest(doc, valid_profile_dir)


def test_empty_required_field_rejected(valid_profile_dir, manifest_dict):
    with pytest.raises(ProfileError, match="name"):
        parse_manifest(manifest_dict(name="   "), valid_profile_dir)


# ---------------------------------------------------------------------- id


def test_bad_id_characters_rejected(valid_profile_dir, manifest_dict):
    for bad in ("My_Rice", "UPPER", "has space", "a", "x" * 41, "-leading"):
        with pytest.raises(ProfileError, match="invalid"):
            parse_manifest(manifest_dict(id=bad), valid_profile_dir)


def test_directory_name_must_match_id(tmp_path, build_profile, manifest_dict, default_files):
    profile_dir = build_profile(
        tmp_path / "lib", manifest_dict(id="real-id"), default_files, dirname="other-name"
    )
    with pytest.raises(ProfileError, match="does not match id"):
        load_profile(profile_dir)


# ------------------------------------------------------------------ version


def test_non_semantic_version_rejected(valid_profile_dir, manifest_dict):
    for bad in ("1.0", "v1.0.0", "one.two.three", "1.0.0.0"):
        with pytest.raises(ProfileError, match="not semantic"):
            parse_manifest(manifest_dict(version=bad), valid_profile_dir)


# ------------------------------------------------------------------- files


def test_absolute_dest_rejected(valid_profile_dir, manifest_dict):
    doc = manifest_dict()
    doc["files"] = {"config": {"/etc/evil.conf": "files/hyprland.conf"}}
    with pytest.raises(ProfileError, match="relative posix path"):
        parse_manifest(doc, valid_profile_dir)


def test_traversal_dest_rejected(valid_profile_dir, manifest_dict):
    doc = manifest_dict()
    doc["files"] = {"config": {"../../escape.conf": "files/hyprland.conf"}}
    with pytest.raises(ProfileError, match="'.' or '..'"):
        parse_manifest(doc, valid_profile_dir)


def test_empty_dest_rejected(valid_profile_dir, manifest_dict):
    doc = manifest_dict()
    doc["files"] = {"config": {"": "files/hyprland.conf"}}
    with pytest.raises(ProfileError, match="non-empty string"):
        parse_manifest(doc, valid_profile_dir)


def test_unknown_files_root_rejected(valid_profile_dir, manifest_dict):
    doc = manifest_dict()
    doc["files"] = {"media": {"x.conf": "files/hyprland.conf"}}
    with pytest.raises(ProfileError, match="not a known destination root"):
        parse_manifest(doc, valid_profile_dir)


def test_missing_payload_on_disk_rejected(valid_profile_dir, manifest_dict):
    (valid_profile_dir / "files" / "hyprland.conf").unlink()
    with pytest.raises(ProfileError, match="payload missing on disk"):
        load_profile(valid_profile_dir)


def test_duplicate_destinations_rejected(valid_profile_dir, manifest_dict, default_files):
    doc = manifest_dict()
    # "./a.conf" and "a.conf" normalise to the same destination.
    doc["files"] = {
        "config": {
            "hypr/hyprland.conf": "files/hyprland.conf",
            "./hypr/hyprland.conf": "files/hyprland.conf",
        }
    }
    with pytest.raises(ProfileError, match="duplicate destinations"):
        parse_manifest(doc, valid_profile_dir)


def test_empty_files_table_rejected(valid_profile_dir, manifest_dict):
    with pytest.raises(ProfileError, match="non-empty \\[files\\]"):
        parse_manifest(manifest_dict(files={}), valid_profile_dir)


def test_files_table_not_table_rejected(valid_profile_dir, manifest_dict):
    with pytest.raises(ProfileError, match="\\[files\\]"):
        parse_manifest(manifest_dict(files="nope"), valid_profile_dir)


# -------------------------------------------------------- previews/wallpaper


def test_preview_must_live_under_assets(valid_profile_dir, manifest_dict):
    with pytest.raises(ProfileError, match="previews must live under assets/"):
        parse_manifest(manifest_dict(previews=["screenshots/preview.png"]), valid_profile_dir)


@pytest.mark.parametrize(
    "bad", ["/etc/preview.png", "../preview.png", ""],
)
def test_bad_preview_paths_rejected(valid_profile_dir, manifest_dict, bad):
    with pytest.raises(ProfileError):
        parse_manifest(manifest_dict(previews=[bad]), valid_profile_dir)


@pytest.mark.parametrize(
    "bad", ["/etc/wall.png", "../wall.png", ""],
)
def test_bad_wallpaper_paths_rejected(valid_profile_dir, manifest_dict, bad):
    with pytest.raises(ProfileError):
        parse_manifest(manifest_dict(wallpaper=bad), valid_profile_dir)


def test_wallpaper_must_live_under_assets(valid_profile_dir, manifest_dict):
    with pytest.raises(ProfileError, match="wallpaper must live under assets/"):
        parse_manifest(manifest_dict(wallpaper="pictures/wall.png"), valid_profile_dir)


# ------------------------------------------------------------------- targets


def test_unknown_target_rejected(valid_profile_dir, manifest_dict):
    with pytest.raises(ProfileError, match="unknown target"):
        parse_manifest(manifest_dict(targets=["definitely-not-a-wm"]), valid_profile_dir)


def test_empty_targets_rejected(valid_profile_dir, manifest_dict):
    with pytest.raises(ProfileError, match="must not be empty"):
        parse_manifest(manifest_dict(targets=[]), valid_profile_dir)


def test_duplicate_targets_rejected(valid_profile_dir, manifest_dict):
    with pytest.raises(ProfileError, match="duplicates"):
        parse_manifest(manifest_dict(targets=["hyprland", "hyprland"]), valid_profile_dir)


# ----------------------------------------------------------------- misc input


def test_invalid_toml_rejected(tmp_path):
    bad = tmp_path / "test-rice"
    bad.mkdir()
    (bad / MANIFEST_NAME).write_bytes(b"id = [not toml")
    with pytest.raises(ProfileError, match="not valid TOML"):
        load_profile(bad)


def test_missing_manifest_rejected(tmp_path):
    empty = tmp_path / "test-rice"
    empty.mkdir()
    with pytest.raises(ProfileError, match="missing manifest.toml"):
        load_profile(empty)

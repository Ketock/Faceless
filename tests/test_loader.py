"""Tests for faceless.core.profile_loader — library scanning and problem collection."""

from __future__ import annotations

import pytest

from faceless.core.profile_loader import Library, scan

pytestmark = pytest.mark.usefixtures("build_profile", "manifest_dict", "default_files")


def test_scan_collects_profiles_from_multiple_dirs(
    tmp_path, build_profile, manifest_dict, default_files
):
    lib1 = tmp_path / "lib1"
    lib2 = tmp_path / "lib2"
    build_profile(lib1, manifest_dict(id="alpha"), default_files)
    build_profile(lib2, manifest_dict(id="beta"), default_files)

    lib = scan([lib1, lib2])
    assert lib.valid_ids() == {"alpha", "beta"}
    assert lib.problems == {}
    assert {str(lib1), str(lib2)} == {p.source for p in lib.profiles}


def test_scan_collects_problems_without_raising(
    tmp_path, build_profile, manifest_dict, default_files
):
    lib1 = tmp_path / "lib1"
    build_profile(lib1, manifest_dict(id="good"), default_files)
    broken = lib1 / "broken"
    broken.mkdir()
    (broken / "manifest.toml").write_text("id = [not toml", encoding="utf-8")
    missing_manifest = lib1 / "no-manifest"
    missing_manifest.mkdir()

    lib = scan([lib1])
    assert "good" in lib.valid_ids()
    assert "missing manifest.toml" in lib.problems[str(missing_manifest)]
    assert "not valid TOML" in lib.problems[str(broken)]


def test_scan_duplicate_id_is_deduplicated_with_problem_note(
    tmp_path, build_profile, manifest_dict, default_files
):
    lib1 = tmp_path / "lib1"
    lib2 = tmp_path / "lib2"
    build_profile(lib1, manifest_dict(id="twin", name="First"), default_files)
    build_profile(lib2, manifest_dict(id="twin", name="Second"), default_files)

    lib = scan([lib1, lib2])
    assert [p.id for p in lib.profiles] == ["twin"]
    assert lib.profiles[0].name == "First"  # first library dir wins
    assert "duplicate profile id 'twin'" in lib.problems[str(lib2 / "twin")]


def test_scan_skips_hidden_dirs_and_plain_files(
    tmp_path, build_profile, manifest_dict, default_files
):
    lib1 = tmp_path / "lib1"
    build_profile(lib1, manifest_dict(id="alpha"), default_files)
    (lib1 / ".hidden-rice").mkdir()
    (lib1 / "stray.txt").write_text("not a profile", encoding="utf-8")

    lib = scan([lib1])
    assert lib.valid_ids() == {"alpha"}
    assert lib.problems == {}


def test_scan_missing_dir_is_ignored(tmp_path):
    lib = scan([tmp_path / "does-not-exist"])
    assert lib.profiles == []
    assert lib.problems == {}


def test_scan_default_dirs_includes_faceless_home_library(
    tmp_path, build_profile, manifest_dict, default_files
):
    user_lib = tmp_path / ".config" / "faceless" / "library"
    build_profile(user_lib, manifest_dict(id="home-rice"), default_files)
    lib = scan()
    assert lib.by_id("home-rice") is not None


def test_library_by_id_and_valid_ids(tmp_path, build_profile, manifest_dict, default_files):
    lib1 = tmp_path / "lib1"
    build_profile(lib1, manifest_dict(id="alpha"), default_files)
    lib = scan([lib1])
    assert lib.by_id("alpha") is not None
    assert lib.by_id("nope") is None
    assert lib.valid_ids() == {"alpha"}


def test_library_defaults():
    lib = Library()
    assert lib.profiles == []
    assert lib.problems == {}
    assert lib.valid_ids() == set()
    assert lib.by_id("anything") is None

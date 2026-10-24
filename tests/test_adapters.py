"""Tests for faceless.adapters.base — ComponentAdapter protocol semantics."""

from __future__ import annotations

import stat

import pytest

from faceless import paths
from faceless.adapters import get
from faceless.adapters.base import Category, ComponentAdapter, ReloadOutcome, safe_session_env


class DummyAdapter(ComponentAdapter):
    id = "dummy"
    name = "Dummy Component"
    category = Category.THEME
    binaries = ("definitely-not-a-real-binary-xyz",)
    config_dirs = ("exists-dir", "missing-dir")


class AlwaysActiveAdapter(ComponentAdapter):
    id = "always-active"
    name = "Always Active"
    category = Category.BAR
    binaries = ("definitely-not-a-real-binary-xyz",)
    reload_actions = ()

    def is_active(self) -> bool:
        return True


class ReloadActionAdapter(AlwaysActiveAdapter):
    id = "reload-action"
    name = "Reload Action"
    reload_actions = (("faceless-fake-reloader", "--reload"),)


@pytest.fixture
def dummy() -> DummyAdapter:
    return DummyAdapter()


def test_uninstalled_binary_reports_not_installed(dummy):
    assert dummy.find_binary() is None
    assert dummy.is_installed() is False


def test_describe_populates_state(dummy):
    (paths.config_home() / "exists-dir").mkdir(parents=True)
    state = dummy.describe()
    assert state.adapter_id == "dummy"
    assert state.name == "Dummy Component"
    assert state.category == "theme"
    assert state.installed is False
    assert state.active is False
    assert paths.config_home() / "exists-dir" in state.config_paths
    assert paths.config_home() / "missing-dir" not in state.config_paths


def test_reload_when_inactive_is_failure_with_restart_hint(dummy):
    outcome = dummy.reload()
    assert isinstance(outcome, ReloadOutcome)
    assert outcome.ok is False
    assert "not running" in outcome.detail
    assert "next launch" in outcome.requires_restart_hint


def test_reload_with_no_actions_ok_when_active():
    outcome = AlwaysActiveAdapter().reload()
    assert outcome.ok is True
    assert "automatically" in outcome.detail


def test_reload_with_missing_action_binary_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    outcome = ReloadActionAdapter().reload()
    assert outcome.ok is False
    assert "faceless-fake-reloader not available" in outcome.detail
    assert "relaunch" in outcome.requires_restart_hint


def test_reload_with_present_action_binary_succeeds(monkeypatch, tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "faceless-fake-reloader"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bindir))
    outcome = ReloadActionAdapter().reload()
    assert outcome.ok is True
    assert "reloaded" in outcome.detail


def test_reload_with_failing_action_binary_reports_exit(monkeypatch, tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "faceless-fake-reloader"
    fake.write_text("#!/bin/sh\necho boom >&2; exit 3\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bindir))
    outcome = ReloadActionAdapter().reload()
    assert outcome.ok is False
    assert "exit 3" in outcome.detail
    assert "boom" in outcome.detail


def test_registry_get():
    assert get("hyprland") is not None
    assert get("hyprland").id == "hyprland"
    assert get("wallpaper").is_installed() is True
    assert get("not-an-adapter") is None


def test_matches_target(dummy):
    assert dummy.matches_target("dummy")
    assert not dummy.matches_target("other")


def test_safe_session_env_filters_keys(monkeypatch):
    for key in (
        "XDG_CURRENT_DESKTOP",
        "XDG_SESSION_TYPE",
        "DESKTOP_SESSION",
        "WAYLAND_DISPLAY",
        "DISPLAY",
        "HYPRLAND_INSTANCE_SIGNATURE",
        "SWAYSOCK",
        "XDG_RUNTIME_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "sig")
    monkeypatch.setenv("PATH", "/usr/bin")  # not whitelisted
    monkeypatch.setenv("SWAYSOCK", "")  # empty values dropped
    env = safe_session_env()
    assert env == {"HYPRLAND_INSTANCE_SIGNATURE": "sig"}


def test_installed_binary_found(monkeypatch, tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "definitely-not-a-real-binary-xyz").write_text("#!/bin/sh\n", encoding="utf-8")
    (bindir / "definitely-not-a-real-binary-xyz").chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir))
    assert DummyAdapter().is_installed() is True

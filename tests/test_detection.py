"""Tests for faceless.core.detection — session detection via env/process probing."""

from __future__ import annotations

import pytest

from faceless.core.detection import Session, detect_session

_SESSION_KEYS = (
    "HYPRLAND_INSTANCE_SIGNATURE",
    "SWAYSOCK",
    "KDE_FULL_SESSION",
    "XDG_CURRENT_DESKTOP",
    "XDG_SESSION_TYPE",
    "DESKTOP_SESSION",
    "WAYLAND_DISPLAY",
    "DISPLAY",
)


@pytest.fixture(autouse=True)
def bare_session_env(monkeypatch):
    """Give every detection test a controlled environment."""
    for key in _SESSION_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_detect_hyprland(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "sig123")
    s = detect_session()
    assert s.kind == "hyprland"
    assert "HYPRLAND_INSTANCE_SIGNATURE" in s.detail
    assert s.human == "Hyprland"


def test_detect_sway(monkeypatch):
    monkeypatch.setenv("SWAYSOCK", "/run/sway-ipc.sock")
    s = detect_session()
    assert s.kind == "sway"
    assert "SWAYSOCK" in s.detail


def test_detect_plasma_via_kde_full_session(monkeypatch):
    monkeypatch.setenv("KDE_FULL_SESSION", "1")
    s = detect_session()
    assert s.kind == "plasma"
    assert s.human == "KDE Plasma"


def test_detect_plasma_via_xdg_current_desktop(monkeypatch):
    # Code matches the substring "plasma" in XDG_CURRENT_DESKTOP; a bare
    # "KDE" value alone is NOT enough (KDE_FULL_SESSION is the KDE signal).
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE:plasma")
    s = detect_session()
    assert s.kind == "plasma"


def test_bare_kde_desktop_without_kde_full_session_is_plasma(monkeypatch):
    # Fixed behaviour: a bare "KDE" XDG_CURRENT_DESKTOP segment is enough —
    # matching is done on desktop segments ("kde" in "KDE:whatever"), so the
    # common KDE setup that never sets KDE_FULL_SESSION still detects Plasma.
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    s = detect_session()
    assert s.kind == "plasma"
    # Segment matching is exact: an unrelated desktop name is not KDE.
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDECosmos")
    assert detect_session().kind != "plasma"


def test_detect_gnome(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    s = detect_session()
    assert s.kind == "gnome"


def test_wayland_generic_fallback(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    s = detect_session()
    assert s.kind == "wayland-generic"
    assert s.display_server == "wayland"


def test_x11_fallback(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    s = detect_session()
    assert s.kind == "x11"
    assert s.display_server == "x11"


def test_tty_when_nothing_detected():
    s = detect_session()
    assert s.kind == "tty"
    assert s.display_server == "unknown"


def test_display_server_mapping_from_session_type(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "tty")
    assert detect_session().display_server == "tty"


def test_process_detection_used_when_env_absent(monkeypatch):
    import faceless.core.detection as detection

    calls = []

    def fake_running(name: str) -> bool:
        calls.append(name)
        return name == "sway"

    monkeypatch.setattr(detection, "_process_running", fake_running)
    s = detect_session()
    assert s.kind == "sway"
    assert "process" in s.detail
    assert calls == ["hyprland", "sway"]


def test_session_human_falls_back_to_kind():
    assert Session(kind="weird-kind").human == "weird-kind"
    assert Session(kind="gnome").human == "GNOME"

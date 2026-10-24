"""Shared fixtures for the Faceless test suite.

Every test runs with FACELESS_HOME pointed at a per-test temp directory, so
nothing ever touches the real user's desktop configuration. FACELESS_HOME is
also pinned at import time (before any faceless module is imported) because
some faceless modules install a file logger (which writes under the XDG state
dir) at import time.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Collection-phase safety net: pin FACELESS_HOME to a session temp dir before
# any faceless module is imported anywhere (pytest imports test modules after
# conftest). Each test then re-pins it to its own tmp_path.
_SESSION_HOME = Path(tempfile.mkdtemp(prefix="faceless-test-home-"))
os.environ["FACELESS_HOME"] = str(_SESSION_HOME)
atexit.register(shutil.rmtree, _SESSION_HOME, ignore_errors=True)

# Session-detection variables that leak in from the developer's real session.
# Tests that care about session detection override these explicitly.
_SESSION_ENV_KEYS = (
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
def faceless_home(tmp_path, monkeypatch):
    """Point FACELESS_HOME (and HOME, as a second line of defence) at tmp_path."""
    monkeypatch.setenv("FACELESS_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    yield
    assert os.environ.get("FACELESS_HOME") == str(tmp_path)


@pytest.fixture(autouse=True)
def no_process_probing(monkeypatch):
    """Never inspect the real host's running processes from tests."""
    import faceless.core.detection as detection

    monkeypatch.setattr(detection, "_process_running", lambda name: False)


# ---------------------------------------------------------------- TOML writing


def _toml_key(key: str) -> str:
    if key and all(c.isalnum() or c in "-_" for c in key) and not key[0].isdigit():
        return key
    return json.dumps(key)


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"cannot serialize {type(value)!r} as TOML")


def toml_dumps(doc: dict) -> str:
    """Minimal TOML writer for manifest dicts (strings, lists, one nested table)."""
    scalars, tables = [], []
    for key, value in doc.items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            scalars.append(f"{_toml_key(key)} = {_toml_value(value)}")
    lines = list(scalars)
    for key, value in tables:
        if value and all(isinstance(v, dict) for v in value.values()):
            for sub_key, mapping in value.items():
                lines.append("")
                lines.append(f"[{_toml_key(key)}.{_toml_key(sub_key)}]")
                for dk, dv in mapping.items():
                    lines.append(f"{_toml_key(dk)} = {_toml_value(dv)}")
        else:
            lines.append("")
            lines.append(f"[{_toml_key(key)}]")
            for dk, dv in value.items():
                lines.append(f"{_toml_key(dk)} = {_toml_value(dv)}")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------- profile builder


@pytest.fixture
def manifest_dict():
    """Factory for a valid minimal manifest dict; keyword args override fields."""

    def _make(**overrides) -> dict:
        doc: dict = {
            "id": "test-rice",
            "name": "Test Rice",
            "version": "1.0.0",
            "description": "A rice used by tests",
            "targets": ["hyprland"],
            "files": {"config": {"hypr/hyprland.conf": "files/hyprland.conf"}},
        }
        doc.update(overrides)
        return doc

    return _make


@pytest.fixture
def build_profile(manifest_dict):
    """Factory: write a profile directory (manifest + payload files) on disk."""

    def _make(
        lib_dir: Path,
        manifest: dict | None = None,
        files: dict[str, str | bytes] | None = None,
        *,
        dirname: str | None = None,
    ) -> Path:
        doc = manifest if manifest is not None else manifest_dict()
        profile_dir = lib_dir / (dirname if dirname is not None else doc["id"])
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "manifest.toml").write_text(toml_dumps(doc), encoding="utf-8")
        for rel, content in (files or {}).items():
            target = profile_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8")
        return profile_dir

    return _make


@pytest.fixture
def default_files():
    """Payload contents matching the default manifest_dict."""

    return {"files/hyprland.conf": "monitor=,preferred,auto,1\n"}

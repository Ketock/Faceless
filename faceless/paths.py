"""Runtime paths for Faceless.

All user-facing locations honour XDG Base Directory conventions and can be
overridden for testing via the FACELESS_HOME environment variable (which
redirects every Faceless-managed location into a sandbox).
"""

from __future__ import annotations

import os
from pathlib import Path


def _xdg(env_key: str, default: Path) -> Path:
    raw = os.environ.get(env_key, "").strip()
    return Path(raw).expanduser() if raw else default


def _home() -> Path:
    return Path(os.environ.get("FACELESS_HOME") or Path.home()).expanduser()


def home() -> Path:
    """The effective user home directory used for rice destinations."""
    return _home()


def config_home() -> Path:
    if os.environ.get("FACELESS_HOME"):
        return _home() / ".config"
    return _xdg("XDG_CONFIG_HOME", _home() / ".config")


def data_home() -> Path:
    if os.environ.get("FACELESS_HOME"):
        return _home() / ".local" / "share"
    return _xdg("XDG_DATA_HOME", _home() / ".local" / "share")


def state_home() -> Path:
    if os.environ.get("FACELESS_HOME"):
        return _home() / ".local" / "state"
    return _xdg("XDG_STATE_HOME", _home() / ".local" / "state")


def settings_file() -> Path:
    return config_home() / "faceless" / "settings.json"


def backup_root() -> Path:
    return data_home() / "faceless" / "backups"


def history_file() -> Path:
    return state_home() / "faceless" / "history.json"


def log_file() -> Path:
    return state_home() / "faceless" / "faceless.log"


def library_dirs() -> list[Path]:
    """Profile library directories, in priority order (user libs first)."""
    dirs = [config_home() / "faceless" / "library"]
    bundled = _bundled_profiles_dir()
    if bundled is not None:
        dirs.append(bundled)
    return dirs


def _bundled_profiles_dir() -> Path | None:
    candidates = [
        Path(__file__).resolve().parent.parent / "data" / "profiles",  # repo checkout
        Path("/usr/share/faceless/profiles"),  # distro package
        Path("/usr/local/share/faceless/profiles"),
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None

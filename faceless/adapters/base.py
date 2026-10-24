"""Adapter protocol and shared helpers.

Each supported desktop component gets an adapter describing how it is
detected, configured, validated and reloaded. Adapters never mutate
configuration themselves; they expose capabilities the engine uses.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Category(StrEnum):
    COMPOSITOR = "compositor"
    BAR = "bar"
    LAUNCHER = "launcher"
    TERMINAL = "terminal"
    NOTIFICATIONS = "notifications"
    LOCK = "lock"
    SHELL = "shell"
    THEME = "theme"
    WALLPAPER = "wallpaper"


@dataclass
class RunResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""


@dataclass
class ReloadOutcome:
    ok: bool
    detail: str
    requires_restart_hint: str = ""


@dataclass
class ComponentState:
    adapter_id: str
    name: str
    category: str
    installed: bool
    active: bool
    config_paths: list[Path] = field(default_factory=list)
    detail: str = ""


class ComponentAdapter:
    """Base class for desktop component adapters."""

    id: str = "unknown"
    name: str = "Unknown"
    category: Category = Category.THEME
    binaries: tuple[str, ...] = ()
    config_dirs: tuple[str, ...] = ()  # relative to config root, e.g. "hypr"
    reload_actions: tuple[tuple[str, ...], ...] = ()  # whitelisted argv prefixes

    # ---- detection -------------------------------------------------
    def find_binary(self) -> Path | None:
        for binary in self.binaries:
            found = shutil.which(binary)
            if found:
                return Path(found)
        return None

    def is_installed(self) -> bool:
        return self.find_binary() is not None

    def config_locations(self) -> list[Path]:
        from faceless import paths

        root = paths.config_home()
        out = []
        for rel in self.config_dirs:
            candidate = root / rel
            if candidate.exists():
                out.append(candidate)
        return out

    def is_active(self) -> bool:
        """Whether this component is running in the *current* session."""
        return self.is_installed()

    def describe(self) -> ComponentState:
        return ComponentState(
            adapter_id=self.id,
            name=self.name,
            category=self.category.value,
            installed=self.is_installed(),
            active=self.is_active(),
            config_paths=self.config_locations(),
        )

    # ---- reload ----------------------------------------------------
    def reload(self) -> ReloadOutcome:
        """Attempt the declared, whitelisted reload actions.

        Only exact argv tuples declared by the adapter are executed — the
        engine never interpolates user/profile data into commands.
        """
        if not self.is_active():
            return ReloadOutcome(
                False, f"{self.name} is not running", "Apply will take effect next launch."
            )
        if not self.reload_actions:
            return ReloadOutcome(
                True,
                f"{self.name} reloads automatically or needs no reload.",
                "",
            )
        failures: list[str] = []
        for argv in self.reload_actions:
            if not shutil.which(argv[0]):
                failures.append(f"{argv[0]} not available")
                continue
            try:
                result = subprocess.run(
                    argv, capture_output=True, text=True, timeout=15, check=False
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                failures.append(f"{argv[0]}: {exc}")
                continue
            if result.returncode == 0:
                return ReloadOutcome(True, f"{self.name} reloaded ({' '.join(argv)}).")
            failures.append(
                f"{argv[0]} exit {result.returncode}: {(result.stderr or result.stdout).strip()}"
            )
        return ReloadOutcome(
            False,
            "; ".join(failures),
            "You may need to relaunch the component manually.",
        )

    # ---- matching --------------------------------------------------
    def matches_target(self, target: str) -> bool:
        return self.id == target


def safe_session_env() -> dict[str, str]:
    """Optional helper for adapters that want a filtered environment subset.

    Returns only the whitelisted desktop-session variables. Adapters are not
    required to use it; reload actions run with the inherited environment so
    tools like hyprctl can find their sockets.
    """
    import os

    keys = (
        "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "DESKTOP_SESSION",
        "WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
        "SWAYSOCK", "XDG_RUNTIME_DIR",
    )
    return {k: v for k, v in os.environ.items() if k in keys and v}

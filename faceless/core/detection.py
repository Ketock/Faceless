"""Desktop session detection.

Detects the running compositor/session type using environment variables and
running-process inspection — never by probing writable config state.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field


@dataclass
class Session:
    kind: str = "unknown"  # hyprland | sway | plasma | gnome | wayland-generic | x11
    display_server: str = "unknown"  # wayland | x11 | tty
    detail: str = ""
    extras: dict[str, str] = field(default_factory=dict)

    @property
    def human(self) -> str:
        names = {
            "hyprland": "Hyprland",
            "sway": "Sway",
            "plasma": "KDE Plasma",
            "gnome": "GNOME",
            "wayland-generic": "Wayland (unspecified compositor)",
            "x11": "X11 (unspecified window manager)",
            "tty": "TTY (no graphical session)",
            "unknown": "Unknown session",
        }
        return names.get(self.kind, self.kind)


def detect_session() -> Session:
    env = os.environ
    session = Session()

    xdg_desktop = env.get("XDG_CURRENT_DESKTOP", "").lower()
    xdg_type = env.get("XDG_SESSION_TYPE", "").lower()
    session.display_server = (
        "wayland" if "wayland" in xdg_type else "x11" if "x11" in xdg_type else xdg_type or "unknown"
    )

    if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        session.kind = "hyprland"
        session.detail = "HYPRLAND_INSTANCE_SIGNATURE present"
        return session
    if env.get("SWAYSOCK"):
        session.kind = "sway"
        session.detail = "SWAYSOCK present"
        return session
    if any(seg in ("plasma", "kde") for seg in xdg_desktop.split(":")) or env.get("KDE_FULL_SESSION"):
        session.kind = "plasma"
        session.detail = f"XDG_CURRENT_DESKTOP={xdg_desktop or 'plasma'}"
        return session
    if "gnome" in xdg_desktop:
        session.kind = "gnome"
        session.detail = f"XDG_CURRENT_DESKTOP={xdg_desktop}"
        return session

    # Fall back to process inspection (works when launched from an app menu
    # without exported compositor variables).
    if _process_running("hyprland"):
        session.kind = "hyprland"
        session.detail = "hyprland process found"
        return session
    if _process_running("sway"):
        session.kind = "sway"
        session.detail = "sway process found"
        return session

    if session.display_server == "wayland":
        session.kind = "wayland-generic"
    elif session.display_server == "x11":
        session.kind = "x11"
    else:
        session.kind = "tty"
    session.detail = f"XDG_CURRENT_DESKTOP={xdg_desktop!r}"
    return session


def _process_running(name: str) -> bool:
    try:
        out = subprocess.run(
            ["pgrep", "-x", name], capture_output=True, text=True, timeout=5, check=False
        )
        return out.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect_gtk_settings() -> dict[str, str]:
    """Read the user's current GTK settings (read-only, for the overview)."""
    values: dict[str, str] = {}
    for key, schema_id in (
        ("gtk-theme", "org.gnome.desktop.interface"),
        ("icon-theme", "org.gnome.desktop.interface"),
        ("cursor-theme", "org.gnome.desktop.interface"),
        ("font-name", "org.gnome.desktop.interface"),
    ):
        try:
            out = subprocess.run(
                ["gsettings", "get", schema_id, key],
                capture_output=True, text=True, timeout=5, check=False,
            )
            if out.returncode == 0:
                values[key] = out.stdout.strip().strip("'")
        except (OSError, subprocess.TimeoutExpired):
            continue
    return values

"""Theme, shell, and wallpaper adapters."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from faceless.adapters.base import Category, ComponentAdapter, ReloadOutcome


class GtkAdapter(ComponentAdapter):
    id = "gtk"
    name = "GTK Themes"
    category = Category.THEME
    binaries = ("gsettings",)
    config_dirs = ("gtk-3.0", "gtk-4.0", "themes", "icons")

    def is_active(self) -> bool:
        # GTK settings apply to every session; treat "active" as "settings readable".
        return shutil.which("gsettings") is not None


class ShellAdapter(ComponentAdapter):
    id = "shell"
    name = "Shell (zsh/bash)"
    category = Category.SHELL
    binaries = ()
    config_dirs = ("zsh",)

    def is_installed(self) -> bool:
        return shutil.which("zsh") is not None or shutil.which("bash") is not None


class FontsAdapter(ComponentAdapter):
    id = "fonts"
    name = "Fonts"
    category = Category.THEME
    binaries = ()
    config_dirs = ()

    def is_installed(self) -> bool:
        return (Path.home() / ".local" / "share" / "fonts").exists() or Path(
            "/usr/share/fonts"
        ).exists()


class WallpaperAdapter(ComponentAdapter):
    """Applies profile wallpapers through the session's supported mechanism.

    The wallpaper file itself is copied by the engine into the Faceless data
    dir; this adapter only performs the (explicit, previewed) set operation.
    """

    id = "wallpaper"
    name = "Wallpaper"
    category = Category.WALLPAPER
    binaries = ()
    config_dirs = ("hypr", "sway")

    def is_installed(self) -> bool:
        return True

    def is_active(self) -> bool:
        return True

    def set_wallpaper(self, image: Path) -> ReloadOutcome:
        """Set the wallpaper using the first supported backend."""
        image = Path(image).expanduser().resolve()
        if not image.is_file():
            return ReloadOutcome(False, f"wallpaper file missing: {image}")
        backends = (
            ("hyprland", self._set_hyprpaper),
            ("sway", self._set_sway),
            ("plasma", self._set_plasma),
            ("gnome", self._set_gnome),
        )
        from faceless.core import detection

        session = detection.detect_session()
        for kind, setter in backends:
            if session.kind == kind:
                return setter(image)
        return ReloadOutcome(
            False,
            f"no wallpaper backend for session '{session.kind}'",
            "Set the wallpaper manually from the applied file.",
        )

    def _set_hyprpaper(self, image: Path) -> ReloadOutcome:
        if not shutil.which("hyprctl"):
            return ReloadOutcome(False, "hyprctl not available", "Use your wallpaper tool of choice.")
        try:
            subprocess.run(["hyprctl", "hyprpaper", "unload", "all"], capture_output=True, timeout=10, check=False)
            preload = subprocess.run(
                ["hyprctl", "hyprpaper", "preload", str(image)],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if preload.returncode != 0:
                return ReloadOutcome(False, f"hyprpaper preload failed: {preload.stderr.strip()}")
            out = subprocess.run(
                ["hyprctl", "hyprpaper", "wallpaper", f", {image}"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            ok = out.returncode == 0
            return ReloadOutcome(ok, "wallpaper set via hyprpaper" if ok else out.stderr.strip())
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ReloadOutcome(False, f"hyprpaper: {exc}")

    def _set_sway(self, image: Path) -> ReloadOutcome:
        if not shutil.which("swaymsg"):
            return ReloadOutcome(False, "swaymsg not available")
        try:
            out = subprocess.run(
                ["swaymsg", "output", "*", "bg", str(image), "fill"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            ok = out.returncode == 0
            return ReloadOutcome(ok, "wallpaper set via swaymsg" if ok else out.stderr.strip())
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ReloadOutcome(False, f"swaymsg: {exc}")

    def _set_plasma(self, image: Path) -> ReloadOutcome:
        """Set the wallpaper through the running plasmashell.

        The engine stores the wallpaper under a fixed, sanitized name, but we
        still escape the path before interpolating it into the script string —
        profile data must never reach an execution context unescaped.
        """
        binary = next((b for b in ("qdbus", "qdbus6", "qdbus-qt6") if shutil.which(b)), None)
        if binary is None:
            return ReloadOutcome(False, "qdbus not available", "Set the wallpaper from Plasma settings.")
        safe_path = str(image).replace("\\", "\\\\").replace("'", "\\'")
        script = (
            "const d = desktops()[0]; d.wallpaperPlugin = 'org.kde.image';"
            "d.currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General'];"
            f"d.writeConfig('Image', '{safe_path}');"
        )
        try:
            out = subprocess.run(
                [binary, "org.kde.plasmashell", "/PlasmaShell", "evaluateScript", script],
                capture_output=True, text=True, timeout=20, check=False,
            )
            ok = out.returncode == 0
            return ReloadOutcome(ok, "wallpaper set via Plasma" if ok else out.stderr.strip())
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ReloadOutcome(False, f"plasma wallpaper: {exc}")

    def _set_gnome(self, image: Path) -> ReloadOutcome:
        if not shutil.which("gsettings"):
            return ReloadOutcome(False, "gsettings not available")
        try:
            out = subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", f"file://{image}"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", f"file://{image}"],
                capture_output=True, timeout=10, check=False,
            )
            ok = out.returncode == 0
            return ReloadOutcome(ok, "wallpaper set via gsettings" if ok else out.stderr.strip())
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ReloadOutcome(False, f"gsettings: {exc}")

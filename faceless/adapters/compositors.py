"""Compositor adapters (Hyprland, Sway)."""

from __future__ import annotations

import shutil
import subprocess

from faceless.adapters.base import Category, ComponentAdapter, ReloadOutcome


class HyprlandAdapter(ComponentAdapter):
    id = "hyprland"
    name = "Hyprland"
    category = Category.COMPOSITOR
    binaries = ("Hyprland", "hyprland")
    config_dirs = ("hypr",)
    reload_actions = (("hyprctl", "reload"),)

    def is_active(self) -> bool:
        import os

        return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) or super().is_active()

    def reload(self) -> ReloadOutcome:
        if not self.is_active():
            return ReloadOutcome(False, "Hyprland is not running", "Config applies next login.")
        socket = shutil.which("hyprctl")
        if not socket:
            return ReloadOutcome(False, "hyprctl not available", "Restart Hyprland to apply.")
        try:
            out = subprocess.run(["hyprctl", "reload"], capture_output=True, text=True, timeout=15, check=False)
            ok = out.returncode == 0 and "ok" in (out.stdout + out.stderr).lower()
            detail = (out.stdout or out.stderr).strip() or ("reloaded" if ok else "failed")
            return ReloadOutcome(ok, detail, "" if ok else "Restart Hyprland to apply.")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ReloadOutcome(False, f"hyprctl: {exc}", "Restart Hyprland to apply.")


class SwayAdapter(ComponentAdapter):
    id = "sway"
    name = "Sway"
    category = Category.COMPOSITOR
    binaries = ("sway",)
    config_dirs = ("sway",)
    reload_actions = (("swaymsg", "reload"),)

    def is_active(self) -> bool:
        import os

        return bool(os.environ.get("SWAYSOCK")) or super().is_active()

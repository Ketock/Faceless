"""Bars, launchers, terminals, notification daemons."""

from __future__ import annotations

from faceless.adapters.base import Category, ComponentAdapter


class WaybarAdapter(ComponentAdapter):
    id = "waybar"
    name = "Waybar"
    category = Category.BAR
    binaries = ("waybar",)
    config_dirs = ("waybar",)


class WofiAdapter(ComponentAdapter):
    id = "wofi"
    name = "Wofi"
    category = Category.LAUNCHER
    binaries = ("wofi",)
    config_dirs = ("wofi",)


class RofiAdapter(ComponentAdapter):
    id = "rofi"
    name = "Rofi"
    category = Category.LAUNCHER
    binaries = ("rofi",)
    config_dirs = ("rofi",)


class KittyAdapter(ComponentAdapter):
    id = "kitty"
    name = "Kitty"
    category = Category.TERMINAL
    binaries = ("kitty",)
    config_dirs = ("kitty",)


class AlacrittyAdapter(ComponentAdapter):
    id = "alacritty"
    name = "Alacritty"
    category = Category.TERMINAL
    binaries = ("alacritty",)
    config_dirs = ("alacritty",)


class FootAdapter(ComponentAdapter):
    id = "foot"
    name = "Foot"
    category = Category.TERMINAL
    binaries = ("foot",)
    config_dirs = ("foot",)


class MakoAdapter(ComponentAdapter):
    id = "mako"
    name = "Mako"
    category = Category.NOTIFICATIONS
    binaries = ("mako",)
    config_dirs = ("mako",)
    reload_actions = (("makoctl", "reload"),)


class SwayncAdapter(ComponentAdapter):
    id = "swaync"
    name = "SwayNC"
    category = Category.NOTIFICATIONS
    binaries = ("swaync",)
    config_dirs = ("swaync",)
    reload_actions = (("swaync-client", "-rs"), (("swaync-client", "-R")))


class DunstAdapter(ComponentAdapter):
    id = "dunst"
    name = "Dunst"
    category = Category.NOTIFICATIONS
    binaries = ("dunst",)
    config_dirs = ("dunst",)
    reload_actions = (("killall", "-SIGUSR2", "dunst"),)

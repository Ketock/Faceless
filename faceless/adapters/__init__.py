"""Adapter registry."""

from __future__ import annotations

from faceless.adapters.base import Category, ComponentAdapter, ComponentState, ReloadOutcome
from faceless.adapters.compositors import HyprlandAdapter, SwayAdapter
from faceless.adapters.themes import FontsAdapter, GtkAdapter, ShellAdapter, WallpaperAdapter
from faceless.adapters.tools import (
    AlacrittyAdapter,
    DunstAdapter,
    FootAdapter,
    KittyAdapter,
    MakoAdapter,
    RofiAdapter,
    SwayncAdapter,
    WaybarAdapter,
    WofiAdapter,
)

ALL: tuple[ComponentAdapter, ...] = (
    HyprlandAdapter(),
    SwayAdapter(),
    WaybarAdapter(),
    WofiAdapter(),
    RofiAdapter(),
    KittyAdapter(),
    AlacrittyAdapter(),
    FootAdapter(),
    MakoAdapter(),
    SwayncAdapter(),
    DunstAdapter(),
    GtkAdapter(),
    ShellAdapter(),
    FontsAdapter(),
    WallpaperAdapter(),
)


def get(adapter_id: str) -> ComponentAdapter | None:
    return next((a for a in ALL if a.id == adapter_id), None)


def all_states() -> list[ComponentState]:
    return [a.describe() for a in ALL]


__all__ = [
    "ALL", "Category", "ComponentAdapter", "ComponentState", "ReloadOutcome",
    "all_states", "get",
]

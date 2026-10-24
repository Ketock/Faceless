"""ComponentsView — every known desktop component and its state."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from faceless.adapters.base import ComponentState
from faceless.controller import AppController, Snapshot
from faceless.ui.widgets import (
    clear_children,
    scrollable,
    state_chip,
)

_CATEGORY_ORDER = (
    "compositor", "bar", "launcher", "terminal", "notifications",
    "lock", "shell", "theme", "wallpaper",
)
_CATEGORY_TITLES = {
    "compositor": "Compositors",
    "bar": "Bars & panels",
    "launcher": "Launchers",
    "terminal": "Terminals",
    "notifications": "Notifications",
    "lock": "Lock screens",
    "shell": "Shells",
    "theme": "Theme & fonts",
    "wallpaper": "Wallpaper",
}
_PAGE_CLAMP = 860


class ComponentsView(Gtk.Box):
    """ComponentState list grouped by category, with per-profile targeting."""

    def __init__(self, controller: AppController, toast):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._controller = controller
        self._toast = toast

        self._body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._body.set_margin_top(24)
        self._body.set_margin_bottom(24)
        self._body.set_margin_start(24)
        self._body.set_margin_end(24)
        clamp = Adw.Clamp(maximum_size=_PAGE_CLAMP, tightening_threshold=700)
        clamp.set_child(self._body)
        self.append(scrollable(clamp))

        self._placeholder = Gtk.Label(label="Loading components…")
        self._placeholder.add_css_class("fl-dim")
        self._body.append(self._placeholder)

    # ------------------------------------------------------------- updates

    def apply_snapshot(self, snap: Snapshot) -> None:
        clear_children(self._body)
        targeting = self._targeting_map(snap)
        categories = sorted(
            {c.category for c in snap.components},
            key=lambda k: _CATEGORY_ORDER.index(k) if k in _CATEGORY_ORDER else 99,
        )
        for category in categories:
            states = [c for c in snap.components if c.category == category]
            if not states:
                continue
            self._body.append(self._build_group(category, states, targeting))
        if not snap.components:
            empty = Gtk.Label(label="No components detected.")
            empty.add_css_class("fl-dim")
            self._body.append(empty)

    def _targeting_map(self, snap: Snapshot) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for profile in snap.library.profiles:
            for target in profile.targets:
                out.setdefault(target, []).append(profile.name)
        return out

    # ------------------------------------------------------------ building

    def _build_group(self, category: str, states: list[ComponentState], targeting) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("fl-card")
        title = Gtk.Label(label=_CATEGORY_TITLES.get(category, category.replace("-", " ")))
        title.add_css_class("fl-section-title")
        title.set_halign(Gtk.Align.START)
        title.set_xalign(0.0)
        card.append(title)
        for state in states:
            card.append(self._build_row(state, targeting.get(state.adapter_id, [])))
        return card

    def _build_row(self, state: ComponentState, targeted_by: list[str]) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name = Gtk.Label(label=state.name)
        name.add_css_class("fl-card-title")
        name.set_halign(Gtk.Align.START)
        top.append(name)
        chip = state_chip(state.installed, state.active)
        chip.set_valign(Gtk.Align.CENTER)
        top.append(chip)
        row.append(top)

        if state.installed:
            note = state.detail or "installed"
        else:
            note = "not installed — Faceless skips this component when applying"
        note_label = Gtk.Label(label=note, wrap=True)
        note_label.add_css_class("fl-dim")
        note_label.set_xalign(0.0)
        note_label.set_halign(Gtk.Align.START)
        row.append(note_label)

        if state.config_paths:
            paths = " · ".join(str(p) for p in state.config_paths[:3])
            paths_label = Gtk.Label(label=paths, wrap=True)
            paths_label.add_css_class("fl-mono")
            paths_label.set_xalign(0.0)
            paths_label.set_halign(Gtk.Align.START)
            row.append(paths_label)

        if targeted_by:
            target_label = Gtk.Label(label="targeted by " + ", ".join(targeted_by))
            target_label.add_css_class("fl-dim")
            target_label.set_xalign(0.0)
            target_label.set_halign(Gtk.Align.START)
            target_label.set_wrap(True)
            row.append(target_label)

        divider = Gtk.Box()
        divider.add_css_class("fl-diamond-line")
        divider.set_hexpand(True)
        row.append(divider)
        return row

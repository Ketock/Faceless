"""HomeView — the session dashboard."""

from __future__ import annotations

import time

from gi.repository import Adw, Gtk

from faceless.controller import AppController, Snapshot
from faceless.ui.widgets import (
    diamond_glyph,
    format_ts,
    scrollable,
)

_PAGE_CLAMP = 900


class HomeView(Gtk.Box):
    """Greeting, session / active-rice / system cards, history, warnings."""

    def __init__(self, controller: AppController, navigate, toast):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._controller = controller
        self._navigate = navigate
        self._toast = toast

        clamp = Adw.Clamp(maximum_size=_PAGE_CLAMP, tightening_threshold=760)
        self._body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._body.set_margin_top(24)
        self._body.set_margin_bottom(24)
        self._body.set_margin_start(24)
        self._body.set_margin_end(24)
        clamp.set_child(self._body)
        self.append(scrollable(clamp))

        self._build()

    # ------------------------------------------------------------ skeleton

    def _build(self) -> None:
        self._greeting = Gtk.Label(label="Faceless")
        self._greeting.add_css_class("fl-display")
        self._greeting.add_css_class("fl-display-xl")
        self._greeting.set_halign(Gtk.Align.START)
        self._greeting.set_xalign(0.0)
        self._body.append(self._greeting)

        self._subtitle = Gtk.Label(label="Loading session…")
        self._subtitle.add_css_class("fl-dim")
        self._subtitle.set_halign(Gtk.Align.START)
        self._body.append(self._subtitle)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        row.set_homogeneous(True)
        self._session_card = self._card("Session", row_placeholder=True)
        self._rice_card = self._card("Active rice")
        self._system_card = self._card("System")
        row.append(self._session_card)
        row.append(self._rice_card)
        row.append(self._system_card)
        self._body.append(row)

        self._body.append(self._build_history_card())
        self._body.append(self._build_warnings_card())

    def _card(self, title: str, row_placeholder: bool = False) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("fl-card")
        label = Gtk.Label(label=title)
        label.add_css_class("fl-section-title")
        label.set_halign(Gtk.Align.START)
        label.set_xalign(0.0)
        card.append(label)
        if row_placeholder:
            self._fill_session_rows(card)
        return card

    def _fill_session_rows(self, card: Gtk.Box) -> None:
        self._session_values: dict[str, Gtk.Label] = {}
        for key in ("Compositor", "Display server", "Detail"):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name = Gtk.Label(label=key)
            name.add_css_class("fl-card-row-label")
            name.set_halign(Gtk.Align.START)
            value = Gtk.Label(label="…")
            value.set_halign(Gtk.Align.END)
            value.set_xalign(0.0)
            value.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            value.set_hexpand(True)
            value.set_selectable(True)
            row.append(name)
            row.append(value)
            card.append(row)
            self._session_values[key] = value

    def _build_history_card(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("fl-card")
        title = Gtk.Label(label="Recent history")
        title.add_css_class("fl-section-title")
        title.set_halign(Gtk.Align.START)
        title.set_xalign(0.0)
        card.append(title)
        self._history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.append(self._history_box)
        self._history_box.append(Gtk.Label(label="Loading…"))
        self._history_box.get_first_child().add_css_class("fl-dim")
        return card

    def _build_warnings_card(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("fl-card")
        self._warnings_card = card
        title = Gtk.Label(label="Profile problems")
        title.add_css_class("fl-section-title")
        title.add_css_class("fl-warning-text")
        title.set_halign(Gtk.Align.START)
        title.set_xalign(0.0)
        card.append(title)
        self._warnings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.append(self._warnings_box)
        card.set_visible(False)
        return card

    # ------------------------------------------------------------- updates

    def apply_snapshot(self, snap: Snapshot) -> None:
        session = snap.session
        hour = time.localtime().tm_hour
        part = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
        self._subtitle.set_text(
            f"Good {part} — jester at your service on {session.human}."
        )

        self._session_values["Compositor"].set_text(session.human)
        self._session_values["Display server"].set_text(session.display_server)
        self._session_values["Detail"].set_text(session.detail or "—")

        self._fill_rice_card(snap)
        self._fill_system_card(snap)
        self._fill_history(snap)
        self._fill_warnings(snap)

    def _fill_rice_card(self, snap: Snapshot) -> None:
        clear_box(self._rice_card, keep=1)
        active = snap.active
        profile = (
            self._controller.get_profile(active.profile_id)
            if active is not None
            else None
        )
        if active is not None and profile is not None:
            head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            head.append(diamond_glyph("fl-active-diamond"))
            name = Gtk.Label(label=profile.name)
            name.add_css_class("fl-card-title")
            name.set_halign(Gtk.Align.START)
            head.append(name)
            self._rice_card.append(head)
            note = Gtk.Label(
                label=f"Applied {format_ts(active.applied_at)} · {profile.version}",
                wrap=True,
            )
            note.add_css_class("fl-dim")
            self._rice_card.append(note)
        elif active is not None:
            note = Gtk.Label(label=active.profile_id, wrap=True)
            note.add_css_class("fl-dim")
            self._rice_card.append(note)
        else:
            note = Gtk.Label(label="No rice applied yet.")
            note.add_css_class("fl-dim")
            note.set_wrap(True)
            self._rice_card.append(note)
            hint = Gtk.Label(
                label="Pick a profile in the Rice Library to dress this desktop.",
                wrap=True,
            )
            hint.add_css_class("fl-dim")
            self._rice_card.append(hint)

        button = Gtk.Button(label="Change Rice")
        button.add_css_class("fl-apply-button")
        button.set_halign(Gtk.Align.START)
        button.connect("clicked", lambda *_: self._navigate("library"))
        self._rice_card.append(button)

    def _fill_system_card(self, snap: Snapshot) -> None:
        clear_box(self._system_card, keep=1)
        installed = sum(1 for c in snap.components if c.installed)
        active = sum(1 for c in snap.components if c.active)
        comp = Gtk.Label(
            label=f"{active} active · {installed} installed of {len(snap.components)} components",
            wrap=True,
        )
        self._system_card.append(comp)

        backups = Gtk.Label(
            label=f"{len(snap.backups)} backup record(s) in the vault.",
            wrap=True,
        )
        backups.add_css_class("fl-dim")
        self._system_card.append(backups)

        last = max((b.created for b in snap.backups), default=None)
        status = (
            f"Last backup {format_ts(last)}" if last else "No backups yet — applies will create them."
        )
        status_label = Gtk.Label(label=status, wrap=True)
        status_label.add_css_class("fl-dim")
        self._system_card.append(status_label)

    def _fill_history(self, snap: Snapshot) -> None:
        from faceless.ui.widgets import clear_children

        clear_children(self._history_box)
        if not snap.history:
            label = Gtk.Label(label="Nothing applied yet — the mask stays behind the curtain.")
            label.add_css_class("fl-dim")
            label.set_wrap(True)
            self._history_box.append(label)
            return
        for entry in snap.history[:5]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            icon = Gtk.Label(label="✓" if entry.status == "success" else "✕")
            icon.add_css_class(
                "fl-success" if entry.status == "success" else "fl-danger"
            )
            icon.add_css_class("fl-history-icon")
            text = Gtk.Label(
                label=f"{entry.operation} · {entry.profile_name} · {format_ts(entry.ts)}",
            )
            text.set_halign(Gtk.Align.START)
            text.set_ellipsize(3)
            text.set_hexpand(True)
            row.append(icon)
            row.append(text)
            self._history_box.append(row)

    def _fill_warnings(self, snap: Snapshot) -> None:
        from faceless.ui.widgets import clear_children

        clear_children(self._warnings_box)
        if not snap.library.problems:
            self._warnings_card.set_visible(False)
            return
        for path, reason in list(snap.library.problems.items())[:6]:
            line = Gtk.Label(label=f"{path}\n{reason}", wrap=True)
            line.add_css_class("fl-danger")
            line.add_css_class("fl-mono")
            line.set_xalign(0.0)
            self._warnings_box.append(line)
        self._warnings_card.set_visible(True)


def clear_box(card: Gtk.Box, keep: int) -> None:
    """Remove children of ``card`` beyond the first ``keep`` (its title)."""
    child = card.get_first_child()
    index = 0
    while child is not None:
        nxt = child.get_next_sibling()
        if index >= keep:
            card.remove(child)
        index += 1
        child = nxt

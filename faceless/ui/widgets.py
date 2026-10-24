"""Shared UI helpers for the Faceless design system.

Small, focused builders for chips, diamond ornaments, empty states,
previews, and background work. Every widget here is presentation-only;
data flows in from AppController callers.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from gi.repository import Gdk, Gio, GLib, Gtk

from faceless.core.plan import Compat
from faceless.core.schema import Profile

# ------------------------------------------------------------------ chips

_COMPAT_CHIP: dict[str, tuple[str, str]] = {
    "full": ("full", "Fully compatible"),
    "partial": ("partial", "Partial compatibility"),
    "incompatible": ("bad", "Incompatible"),
}


def make_chip(text: str, kind: str = "neutral", tooltip: str | None = None) -> Gtk.Label:
    """A small rounded design-system label (`fl-chip` + variant class)."""
    chip = Gtk.Label(label=text)
    chip.add_css_class("fl-chip")
    chip.add_css_class(f"fl-chip-{kind}")
    if tooltip:
        chip.set_tooltip_text(tooltip)
    return chip


def compatibility_chip(compat: Compat | str) -> Gtk.Label:
    """Chip describing profile compatibility (full / partial / incompatible)."""
    value = getattr(compat, "value", str(compat))
    kind, text = _COMPAT_CHIP.get(value, ("neutral", value))
    return make_chip(text, kind)


def state_chip(installed: bool, active: bool) -> Gtk.Label:
    """Chip for component state: active > installed > not installed."""
    if active:
        return make_chip("active", "good")
    if installed:
        return make_chip("installed", "installed")
    return make_chip("not installed", "missing")


def operation_chip(operation: str) -> Gtk.Label:
    """Chip for backup operation kind (apply / restore / pre-restore)."""
    kinds = {"apply": "neutral", "restore": "gold", "pre-restore": "neutral"}
    return make_chip(operation, kinds.get(operation, "neutral"))


def chip_row() -> Gtk.FlowBox:
    """A wrapping row of chips (GTK4 Boxes cannot wrap; FlowBox can)."""
    row = Gtk.FlowBox()
    row.set_selection_mode(Gtk.SelectionMode.NONE)
    row.set_min_children_per_line(1)
    row.set_max_children_per_line(16)
    row.set_column_spacing(6)
    row.set_row_spacing(6)
    row.set_halign(Gtk.Align.START)
    row.set_valign(Gtk.Align.CENTER)
    return row


# --------------------------------------------------------------- ornaments


def diamond_glyph(css_class: str = "fl-diamond-glyph", glyph: str = "◆") -> Gtk.Label:
    """A tiny harlequin diamond as a text glyph."""
    label = Gtk.Label(label=glyph)
    label.add_css_class(css_class)
    return label


def diamond_divider() -> Gtk.Box:
    """Ornament: line ◆ line, centered."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    box.set_halign(Gtk.Align.FILL)
    line_left = Gtk.Box()
    line_left.add_css_class("fl-diamond-line")
    line_left.set_hexpand(True)
    line_left.set_valign(Gtk.Align.CENTER)
    line_right = Gtk.Box()
    line_right.add_css_class("fl-diamond-line")
    line_right.set_hexpand(True)
    line_right.set_valign(Gtk.Align.CENTER)
    box.append(line_left)
    box.append(diamond_glyph())
    box.append(line_right)
    return box


# -------------------------------------------------------------- empty state


def empty_state(
    title: str,
    subtitle: str = "",
    action: Gtk.Widget | None = None,
) -> Gtk.Box:
    """Large diamond outline + caption + optional recovery action."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    box.add_css_class("fl-empty")
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)

    art = Gtk.Label(label="◇")
    art.add_css_class("fl-empty-diamond")
    art.set_halign(Gtk.Align.CENTER)

    heading = Gtk.Label(label=title)
    heading.add_css_class("fl-display")
    heading.set_halign(Gtk.Align.CENTER)

    box.append(art)
    box.append(heading)
    if subtitle:
        note = Gtk.Label(label=subtitle, wrap=True)
        note.add_css_class("fl-dim")
        note.set_justify(Gtk.Justification.CENTER)
        note.set_max_width_chars(48)
        note.set_halign(Gtk.Align.CENTER)
        box.append(note)
    if action is not None:
        action.set_halign(Gtk.Align.CENTER)
        box.append(action)
    return box


# ------------------------------------------------------------------ previews


def make_picture(path: Path, content_fit: Gtk.ContentFit) -> Gtk.Picture | None:
    """Load an image file safely; returns None if missing or corrupt."""
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return None
        # Validate through Gdk.Texture first: Picture.new_for_filename silently
        # accepts corrupt files, Texture raises GLib.Error instead.
        texture = Gdk.Texture.new_from_file(Gio.File.new_for_path(str(path)))
        if texture is None:
            return None
        picture = Gtk.Picture.new_for_paintable(texture)
        picture.set_content_fit(content_fit)
        return picture
    except Exception:  # noqa: BLE001 — a broken image must never crash the UI
        return None


def preview_widget(
    profile: Profile,
    height: int = 120,
    content_fit: Gtk.ContentFit = Gtk.ContentFit.COVER,
) -> Gtk.Widget:
    """First existing preview image, else a diamond placeholder platter."""
    try:
        for candidate in profile.preview_paths():
            picture = make_picture(candidate, content_fit)
            if picture is not None:
                picture.set_size_request(-1, height)
                picture.set_hexpand(True)
                picture.add_css_class("fl-preview")
                return picture
    except OSError:  # preview_paths may hit odd filesystems
        pass
    return placeholder_platter(height)


def placeholder_platter(height: int = 120) -> Gtk.Box:
    """Diamond placeholder area used when no preview image exists."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.add_css_class("fl-platter")
    box.set_size_request(-1, height)
    box.set_hexpand(True)
    glyph = Gtk.Label(label="◆")
    glyph.add_css_class("fl-diamond-glyph")
    glyph.set_halign(Gtk.Align.CENTER)
    glyph.set_valign(Gtk.Align.CENTER)
    # GTK4 has no Box.set_center_widget; a Label as the overlay's main child
    # fills the platter and centers itself via its aligns.
    overlay = Gtk.Overlay()
    overlay.set_child(glyph)
    box.append(overlay)
    return box


# ------------------------------------------------------------------- misc


def format_ts(ts: float) -> str:
    """Human timestamp for history/backup rows."""
    if not ts:
        return "unknown"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def scrollable(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    """A scrolled viewport with neutral shadows."""
    window = Gtk.ScrolledWindow()
    window.set_child(child)
    window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    window.set_hexpand(True)
    window.set_vexpand(True)
    return window


def clear_children(container: Gtk.Widget) -> None:
    """Remove every child widget (ListBox rows, Box children, …)."""
    child = container.get_first_child()
    while child is not None:
        nxt = child.get_next_sibling()
        container.remove(child)
        child = nxt


# --------------------------------------------------------------- threading


def run_in_background(job, callback) -> None:
    """Run ``job()`` on a worker thread; marshal ``callback(result, error)``
    back onto the GTK main loop via GLib.idle_add.

    ``job`` takes no arguments; ``callback`` receives (result, error) where
    exactly one of them is set. Errors are delivered, never swallowed.
    """

    def worker() -> None:
        result = None
        error: Exception | None = None
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 — surfaced through callback
            error = exc

        def marshal() -> bool:
            callback(result, error)
            return False

        GLib.idle_add(marshal)

    thread = threading.Thread(target=worker, daemon=True, name="faceless-bg")
    thread.start()

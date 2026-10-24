"""LibraryView — searchable, sortable grid of rice profiles."""

from __future__ import annotations

from gi.repository import GLib, Gtk

from faceless.controller import AppController, Snapshot
from faceless.core.plan import Compat
from faceless.core.schema import Profile
from faceless.ui.widgets import (
    chip_row,
    clear_children,
    compatibility_chip,
    empty_state,
    make_chip,
    preview_widget,
    scrollable,
)

COMPOSITOR_TARGETS = ("hyprland", "sway", "plasma", "gnome")
SORT_MODES = ("Name", "Compatibility", "Recently applied")
_SEARCH_DEBOUNCE_MS = 250
_COMPAT_RANK = {Compat.FULL: 0, Compat.PARTIAL: 1, Compat.INCOMPATIBLE: 2}


def cheap_compat(profile: Profile, session_kind: str) -> tuple[Compat, str]:
    """Session-kind vs targets compatibility, without building a full plan."""
    compositor_targets = [t for t in profile.targets if t in COMPOSITOR_TARGETS]
    if not compositor_targets:
        return Compat.FULL, ""
    if session_kind in compositor_targets:
        return Compat.FULL, ""
    reason = (
        f"profile targets {', '.join(sorted(compositor_targets))} "
        f"but this session is {session_kind}"
    )
    return Compat.PARTIAL, reason


class LibraryView(Gtk.Box):
    """Grid of profile cards with filter + sort, and a recovery empty state."""

    def __init__(self, controller: AppController, open_profile, goto_settings, toast):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._controller = controller
        self._open_profile = open_profile
        self._goto_settings = goto_settings
        self._toast = toast
        self._snap: Snapshot | None = None
        self._query = ""
        self._sort = 0
        self._debounce_id: int | None = None

        self.append(self._build_toolbar())

        pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        pages.set_transition_duration(160)
        pages.set_vexpand(True)

        self._flow = Gtk.FlowBox()
        self._flow.set_valign(Gtk.Align.START)
        self._flow.set_max_children_per_line(3)
        self._flow.set_min_children_per_line(1)
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_column_spacing(14)
        self._flow.set_row_spacing(14)
        self._flow.set_margin_top(18)
        self._flow.set_margin_bottom(24)
        self._flow.set_margin_start(24)
        self._flow.set_margin_end(24)
        pages.add_named(scrollable(self._flow), "cards")

        action = Gtk.Button(label="Add a library path in Settings")
        action.add_css_class("fl-apply-button")
        action.connect("clicked", lambda *_: goto_settings())
        self._empty = empty_state(
            "No rices found",
            "Faceless scans your library paths for profile directories. "
            "Point it at a folder of rices and they will appear here.",
            action,
        )
        pages.add_named(self._empty, "empty")

        self._no_match = empty_state(
            "No matching rices",
            "Nothing in the library answers that search. Try another mask.",
        )
        pages.add_named(self._no_match, "no-match")
        self._pages = pages
        self.append(pages)

    # ------------------------------------------------------------ toolbar

    def _build_toolbar(self) -> Gtk.Box:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bar.set_margin_top(18)
        bar.set_margin_bottom(6)
        bar.set_margin_start(24)
        bar.set_margin_end(24)

        self._search = Gtk.SearchEntry()
        self._search.set_hexpand(True)
        self._search.set_placeholder_text("Search rices by name, tag or id…")
        self._search.connect("search-changed", self._on_search)
        bar.append(self._search)

        label = Gtk.Label(label="Sort")
        label.add_css_class("fl-dim")
        bar.append(label)
        self._sorter = Gtk.DropDown.new(Gtk.StringList.new(list(SORT_MODES)), None)
        self._sorter.connect("notify::selected", self._on_sort)
        bar.append(self._sorter)
        return bar

    # ------------------------------------------------------------- updates

    def apply_snapshot(self, snap: Snapshot) -> None:
        self._snap = snap
        self.reflow()

    def _on_search(self, entry: Gtk.SearchEntry) -> None:
        self._query = entry.get_text().strip().lower()
        # Debounce: typing rebuilds the FlowBox (and re-decodes card previews),
        # so only reflow 250ms after the last keystroke.
        if self._debounce_id is not None:
            GLib.source_remove(self._debounce_id)
        self._debounce_id = GLib.timeout_add(
            _SEARCH_DEBOUNCE_MS, self._debounced_reflow
        )

    def _debounced_reflow(self) -> bool:
        self._debounce_id = None
        if self._snap is None:
            return False
        self.reflow()
        return False

    def _on_sort(self, *args) -> None:
        self._sort = self._sorter.get_selected()
        self.reflow()

    def _filtered(self) -> list[Profile]:
        snap = self._snap
        if snap is None:
            return []
        profiles = list(snap.library.profiles)
        if self._query:
            def matches(p: Profile) -> bool:
                haystack = " ".join([p.name, p.id, p.description, " ".join(p.tags)])
                return self._query in haystack.lower()

            profiles = [p for p in profiles if matches(p)]

        applied_ts = {}
        for entry in snap.history:
            if entry.operation == "apply" and entry.profile_id not in applied_ts:
                applied_ts[entry.profile_id] = entry.ts
        if self._sort == 1:
            kind = snap.session.kind
            profiles.sort(key=lambda p: (_COMPAT_RANK[cheap_compat(p, kind)[0]], p.name.lower()))
        elif self._sort == 2:
            profiles.sort(
                key=lambda p: (-applied_ts.get(p.id, 0.0), p.name.lower())
            )
        else:
            profiles.sort(key=lambda p: p.name.lower())
        return profiles

    def reflow(self) -> None:
        clear_children(self._flow)
        profiles = self._filtered()
        if self._snap is not None and not self._snap.library.profiles:
            self._pages.set_visible_child_name("empty")
        elif not profiles:
            self._pages.set_visible_child_name("no-match")
        else:
            for profile in profiles:
                self._flow.append(self._build_card(profile))
            self._pages.set_visible_child_name("cards")

    def _build_card(self, profile: Profile) -> Gtk.Button:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("fl-profile-card")
        card.set_size_request(230, -1)

        card.append(preview_widget(profile, height=120))

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(4)
        inner.set_margin_bottom(12)
        inner.set_margin_start(12)
        inner.set_margin_end(12)

        name = Gtk.Label(label=profile.name)
        name.add_css_class("fl-card-title")
        name.set_halign(Gtk.Align.START)
        name.set_xalign(0.0)
        name.set_ellipsize(3)
        inner.append(name)

        tag_row = chip_row()
        for tag in profile.tags[:3]:
            tag_row.append(make_chip(tag))
        compat, _ = self._compat(profile)
        tag_row.append(compatibility_chip(compat))
        tag_row.append(make_chip("in use", "gold") if self._is_active(profile) else make_chip("available"))
        inner.append(tag_row)
        card.append(inner)

        button = Gtk.Button()
        button.set_child(card)
        button.add_css_class("fl-profile-card")
        button.set_tooltip_text(f"Open {profile.name}")
        button.connect("clicked", lambda *_b: self._open_profile(profile.id))
        return button

    def _compat(self, profile: Profile) -> tuple[Compat, str]:
        if self._snap is None:
            return Compat.FULL, ""
        return cheap_compat(profile, self._snap.session.kind)

    def _is_active(self, profile: Profile) -> bool:
        return (
            self._snap is not None
            and self._snap.active is not None
            and self._snap.active.profile_id == profile.id
        )

"""FacelessApp — the application shell: sidebar, pages, snapshot plumbing."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from faceless import logging as fl_logging  # noqa: E402
from faceless.controller import AppController, Snapshot  # noqa: E402
from faceless.ui import theme  # noqa: E402
from faceless.ui.pages.backups import BackupsView  # noqa: E402
from faceless.ui.pages.components import ComponentsView  # noqa: E402
from faceless.ui.pages.home import HomeView  # noqa: E402
from faceless.ui.pages.library import LibraryView  # noqa: E402
from faceless.ui.pages.profile_detail import ProfileDetailView  # noqa: E402
from faceless.ui.pages.settings_page import SettingsPage  # noqa: E402

APP_ID = "io.github.ketock.Faceless"
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 720

_NAV_ITEMS = (
    ("home", "Home", "go-home-symbolic"),
    ("library", "Rice Library", "view-grid-symbolic"),
    ("components", "Components", "application-x-executable-symbolic"),
    ("backups", "Backups", "document-save-symbolic"),
    ("settings", "Settings", "preferences-system-symbolic"),
)


class FacelessApp(Adw.Application):
    """The single Adw.Application; builds the whole UI on activation."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.controller = AppController()
        self._pages: dict[str, Gtk.Widget] = {}
        self._nav_rows: dict[str, Gtk.ListBoxRow] = {}
        self._snapshot: Snapshot | None = None
        self._snapshot_running = False

    # ------------------------------------------------------- app lifecycle

    def do_activate(self) -> None:
        fl_logging.configure(debug=self.controller.settings.debug_logging)
        theme.apply_theme(Gdk.Display.get_default())
        win = self._build_window()
        win.present()
        self.reload_snapshot()

    # ----------------------------------------------------------- window UI

    def _build_window(self) -> Adw.ApplicationWindow:
        self._toast_overlay = Adw.ToastOverlay()
        split = Adw.NavigationSplitView()
        # Sidebar pinned at the spec'd 240 px (fraction-based API interpolates
        # between min and max; equal values pin it).
        split.set_min_sidebar_width(240)
        split.set_max_sidebar_width(240)
        split.set_content(self._build_content_page())
        split.set_sidebar(self._build_sidebar_page())
        self._toast_overlay.set_child(split)

        win = Adw.ApplicationWindow(application=self)
        win.set_title("Faceless")
        win.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        win.set_content(self._toast_overlay)
        win.add_css_class("fl-root")
        return win

    def _build_sidebar_page(self) -> Adw.NavigationPage:
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand.add_css_class("fl-mask-header")
        brand.set_halign(Gtk.Align.START)
        brand.set_margin_top(6)
        brand.set_margin_bottom(6)
        paintable = theme.logo_paintable()
        if paintable is not None:
            logo = Gtk.Image.new_from_paintable(paintable)
            logo.set_pixel_size(30)
            brand.append(logo)
        title = Gtk.Label(label="Faceless")
        title.add_css_class("fl-display")
        title.add_css_class("fl-brand-title")
        brand.append(title)

        self._nav_list = Gtk.ListBox()
        self._nav_list.add_css_class("navigation-sidebar")
        self._nav_list.add_css_class("fl-sidebar")
        self._nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._nav_list.set_vexpand(True)
        for key, label, icon in _NAV_ITEMS:
            row = Gtk.ListBoxRow(child=self._nav_row(label, icon))
            self._nav_rows[key] = row
            self._nav_list.append(row)
        self._nav_list.connect("row-selected", self._on_nav_selected)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_child(self._nav_list)
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.add_css_class("fl-sidebar")
        sidebar_scroll.set_vexpand(True)

        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sidebar_box.set_margin_top(12)
        sidebar_box.set_margin_bottom(12)
        sidebar_box.set_margin_start(10)
        sidebar_box.set_margin_end(10)
        sidebar_box.append(brand)
        sidebar_box.append(sidebar_scroll)

        view = Adw.ToolbarView()
        view.set_content(sidebar_box)
        view.add_top_bar(Gtk.HeaderBar())
        page = Adw.NavigationPage.new(view, "Sidebar")
        return page

    @staticmethod
    def _nav_row(label: str, icon: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        diamond = Gtk.Label(label="◆")
        diamond.add_css_class("fl-nav-diamond")
        image = Gtk.Image.new_from_icon_name(icon)
        image.add_css_class("fl-nav-icon")
        text = Gtk.Label(label=label)
        text.set_halign(Gtk.Align.START)
        text.set_hexpand(True)
        row.append(diamond)
        row.append(image)
        row.append(text)
        return row

    def _build_content_page(self) -> Adw.NavigationPage:
        self._title_label = Gtk.Label(label="Home")
        self._title_label.add_css_class("fl-display")

        header = Gtk.HeaderBar(title_widget=self._title_label)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(220)
        self._stack.set_vexpand(True)
        self._stack.add_css_class("fl-content")

        self._build_pages()

        view = Adw.ToolbarView()
        view.set_content(self._stack)
        view.add_top_bar(header)
        return Adw.NavigationPage.new(view, "Faceless")

    def _build_pages(self) -> None:
        self._pages["home"] = HomeView(self.controller, self.navigate, self.toast)
        self._pages["library"] = LibraryView(
            self.controller, self.open_profile, lambda: self.navigate("settings"), self.toast
        )
        self._pages["components"] = ComponentsView(self.controller, self.toast)
        self._pages["backups"] = BackupsView(
            self.controller, self.toast, self.reload_snapshot
        )
        self._pages["settings"] = SettingsPage(
            self.controller, self.toast, lambda: self.reload_snapshot()
        )
        self._pages["profile-detail"] = ProfileDetailView(
            self.controller, self.toast, lambda: self.navigate("library"), self.reload_snapshot
        )
        for key, widget in self._pages.items():
            self._stack.add_named(widget, key)

    # ------------------------------------------------------------ navigation

    def navigate(self, key: str) -> None:
        title = next((t for k, t, _i in _NAV_ITEMS if k == key), "Profile")
        self._stack.set_visible_child_name(key)
        self._title_label.set_text(title)
        row = self._nav_rows.get(key)
        if row is not None:
            self._nav_list.select_row(row)

    def _on_nav_selected(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        for key, candidate in self._nav_rows.items():
            if candidate is row:
                self.navigate(key)
                return

    def open_profile(self, profile_id: str) -> None:
        profile = self.controller.get_profile(profile_id)
        if profile is None:
            self.toast("That rice is no longer in the library.")
            return
        detail = self._pages["profile-detail"]
        detail.show_profile(profile, self._snapshot)  # type: ignore[union-attr]
        title = self._title_label
        title.set_text(profile.name)
        self._stack.set_visible_child_name("profile-detail")
        self._nav_list.select_row(self._nav_rows.get("library"))

    # ------------------------------------------------------------- toasts

    def toast(self, text: str) -> None:
        toast = Adw.Toast.new(text)
        toast.set_timeout(4)
        self._toast_overlay.add_toast(toast)

    # ---------------------------------------------------------- snapshotting

    def reload_snapshot(self) -> None:
        """Fetch a fresh Snapshot off the UI thread (detection shells out)."""
        if self._snapshot_running:
            return
        self._snapshot_running = True

        def job() -> Snapshot:
            return self.controller.snapshot()

        from faceless.ui.widgets import run_in_background

        run_in_background(job, self._on_snapshot)

    def _on_snapshot(self, snap: Snapshot | None, error: Exception | None) -> None:
        self._snapshot_running = False
        if error is not None or snap is None:
            self.toast(f"Could not inspect this system: {error}")
            return
        self._snapshot = snap
        for page in self._pages.values():
            if hasattr(page, "apply_snapshot"):
                page.apply_snapshot(snap)
        if self._stack.get_visible_child_name() == "profile-detail":
            self._title_label.set_text(self._pages["profile-detail"].current_title())


def main() -> None:
    app = FacelessApp()
    app.run(None)


if __name__ == "__main__":
    main()

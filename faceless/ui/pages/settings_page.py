"""SettingsPage — library paths, backup dir, toggles, diagnostics."""

from __future__ import annotations

import subprocess
from pathlib import Path

from gi.repository import Adw, Gtk

from faceless import logging as fl_logging
from faceless import paths
from faceless.controller import AppController, Snapshot
from faceless.ui.widgets import (
    run_in_background,
    scrollable,
)

_TOGGLE_DEFS = (
    ("confirm_before_apply", "Confirm before apply", "Show a summary dialog listing conflicts before applying."),
    ("enable_live_reload", "Enable live reload", "Ask running components to reload after an apply."),
    ("show_concept_previews", "Show concept previews", "Display profile preview images in the library."),
    ("detect_detailed_components", "Detailed component detection", "Probe component state in depth during detection."),
    ("debug_logging", "Debug logging", "Verbose logging (takes effect after restart)."),
)


class SettingsPage(Gtk.Box):
    """Application settings; the app theme itself is fixed and not changed."""

    def __init__(self, controller: AppController, toast, changed):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._controller = controller
        self._toast = toast
        self._changed = changed

        clamp = Adw.Clamp(maximum_size=760, tightening_threshold=600)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        body.set_margin_top(24)
        body.set_margin_bottom(24)
        body.set_margin_start(24)
        body.set_margin_end(24)
        clamp.set_child(body)
        self.append(scrollable(clamp))

        body.append(self._build_library_group())
        body.append(self._build_backup_group())
        body.append(self._build_toggles())
        body.append(self._build_appearance_note())
        body.append(self._build_diagnostics())

    # ------------------------------------------------------------ builders

    def _build_library_group(self) -> Adw.PreferencesGroup:
        self._paths_group = Adw.PreferencesGroup(
            title="Rice library",
            description="Folders scanned for profile directories.",
        )
        self._path_rows: list[Adw.ActionRow] = []
        self._refresh_paths()
        return self._paths_group

    def _refresh_paths(self) -> None:
        for row in self._path_rows:
            self._paths_group.remove(row)
        self._path_rows = []
        configured = self._controller.settings.library_paths
        for raw in configured:
            row = Adw.ActionRow(title=raw)
            row.set_selectable(False)
            remove = Gtk.Button()
            remove.set_icon_name("user-trash-symbolic")
            remove.set_tooltip_text(f"Remove {raw}")
            remove.add_css_class("flat")
            remove.add_css_class("fl-danger")
            remove.set_valign(Gtk.Align.CENTER)
            remove.connect("clicked", lambda _b, p=raw: self._remove_path(p))
            row.add_suffix(remove)
            self._paths_group.add(row)
            self._path_rows.append(row)

        add_row = Adw.ActionRow(
            title="Add a library path",
            subtitle=(
                "Faceless also scans its default library locations."
                if not configured
                else None
            ),
        )
        add_btn = Gtk.Button()
        add_btn.set_icon_name("list-add-symbolic")
        add_btn.add_css_class("flat")
        add_btn.set_valign(Gtk.Align.CENTER)
        add_btn.connect("clicked", self._choose_folder)
        add_row.add_suffix(add_btn)
        add_row.set_activatable_widget(add_btn)
        self._paths_group.add(add_row)
        self._path_rows.append(add_row)

    def _choose_folder(self, button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title="Choose a rice library folder")
        dialog.select_folder(self.get_root(), None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except Exception:  # noqa: BLE001 — cancelled or failed chooser
            return
        path = folder.get_path() if folder is not None else None
        if not path:
            return
        ok, message = self._controller.add_library_path(path)
        self._toast(message if not ok else f"Library path added: {message}")
        if ok:
            self._refresh_paths()
            self._changed()

    def _remove_path(self, raw: str) -> None:
        if self._controller.remove_library_path(raw):
            self._toast(f"Removed library path: {raw}")
            self._refresh_paths()
            self._changed()
        else:
            self._toast("Could not remove that path.")

    # ------------------------------------------------------- backup + toggles

    def _build_backup_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Backups")
        settings = self._controller.settings
        self._backup_entry = Adw.EntryRow(title="Backup directory override (blank = default)")
        self._backup_entry.set_text(settings.backup_dir)
        self._backup_entry.set_show_apply_button(True)
        self._backup_entry.connect("apply", self._on_backup_dir_apply)
        group.add(self._backup_entry)
        return group

    def _on_backup_dir_apply(self, row: Adw.EntryRow) -> None:
        value = row.get_text().strip()
        self._controller.settings.backup_dir = value
        if self._controller.save_settings():
            self._toast(
                "Backup directory updated."
                if value
                else "Backup directory reset to the default."
            )
            self._changed()
        else:
            self._toast("Could not save settings — check the log folder.")

    def _build_toggles(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Behaviour")
        settings = self._controller.settings
        self._toggles: dict[str, Adw.SwitchRow] = {}
        for field, title, subtitle in _TOGGLE_DEFS:
            row = Adw.SwitchRow(title=title, subtitle=subtitle)
            row.set_active(bool(getattr(settings, field)))
            row.connect("notify::active", self._on_toggle, field)
            self._toggles[field] = row
            group.add(row)
        return group

    def _on_toggle(self, row: Adw.SwitchRow, _pspec, field: str) -> None:
        setattr(self._controller.settings, field, row.get_active())
        if self._controller.save_settings():
            self._toast(f"Saved: {field.replace('_', ' ')}")
        else:
            self._toast("Could not save settings — check the log folder.")

    def _build_appearance_note(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Appearance")
        note = Adw.ActionRow(
            title="Faceless keeps its own jester theme",
            subtitle=(
                "This app is always dark — ink, bone, crimson and gold. Your "
                "desktop GTK theme is never touched by the application itself."
            ),
        )
        note.set_sensitive(False)
        group.add(note)
        return group

    def _build_diagnostics(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Diagnostics")

        expander_row = Adw.ExpanderRow(title="Open diagnostics")
        text = Gtk.TextView()
        text.set_editable(False)
        text.set_cursor_visible(False)
        text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text.add_css_class("fl-mono")
        text.set_margin_top(10)
        text.set_margin_bottom(10)
        text.set_margin_start(10)
        text.set_margin_end(10)
        window = Gtk.ScrolledWindow()
        window.set_child(text)
        window.set_size_request(-1, 240)
        window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        expander_row.add_row(window)
        self._diag_text = text
        self._diag_expander = expander_row
        self._diag_loaded = False
        expander_row.connect("notify::expanded", self._on_diag_expanded)
        group.add(expander_row)

        open_row = Adw.ActionRow(title="Log folder", subtitle=self._log_dir())
        open_btn = Gtk.Button(label="Open log folder")
        open_btn.add_css_class("flat")
        open_btn.set_valign(Gtk.Align.CENTER)
        open_btn.connect("clicked", self._open_log_folder)
        open_row.add_suffix(open_btn)
        open_row.set_activatable_widget(open_btn)
        group.add(open_row)
        return group

    def _on_diag_expanded(self, row: Adw.ExpanderRow, _pspec) -> None:
        if not row.get_expanded() or self._diag_loaded:
            return
        self._diag_loaded = True
        self._diag_text.get_buffer().set_text("Collecting diagnostics…")

        def job() -> str:
            # diagnostics() shells out (pgrep + gsettings); keep it off the
            # UI thread so expanding never freezes the window.
            lines = []
            try:
                lines = self._controller.diagnostics()
            except Exception as exc:  # noqa: BLE001 — diagnostics must not crash
                lines = [f"diagnostics failed: {exc}"]
            lines.append("")
            lines.append("— recent log lines —")
            lines.extend(fl_logging.recent_entries()[-40:] or ["(no log lines yet)"])
            return "\n".join(lines)

        run_in_background(job, self._on_diag_ready)

    def _on_diag_ready(self, text: str | None, error: Exception | None) -> None:
        if error is not None or not text:
            text = f"diagnostics failed: {error}"
        self._diag_text.get_buffer().set_text(text)

    # -------------------------------------------------------------- helpers

    def _log_dir(self) -> str:
        try:
            return str(Path(fl_logging.log_file() if hasattr(fl_logging, "log_file")
                            else paths.log_file()).parent)
        except Exception:  # noqa: BLE001
            return "unknown"

    def _open_log_folder(self, button: Gtk.Button) -> None:
        folder = paths.log_file().parent
        try:
            subprocess.Popen(
                ["xdg-open", str(folder)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            self._toast("Could not open the log folder.")

    def apply_snapshot(self, snap: Snapshot) -> None:
        """Keep toggles/paths in sync with external state changes."""
        self._refresh_paths()

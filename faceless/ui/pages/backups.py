"""BackupsView — the restore vault."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from faceless.controller import AppController, Snapshot
from faceless.core.backups import BackupRecord
from faceless.ui.widgets import (
    clear_children,
    empty_state,
    format_ts,
    operation_chip,
    run_in_background,
    scrollable,
)


class BackupsView(Gtk.Box):
    """Backup records with inspect / restore / delete actions."""

    def __init__(self, controller: AppController, toast, changed):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._controller = controller
        self._toast = toast
        # App shell hook (FacelessApp.reload_snapshot) — keeps the vault fresh
        # after restore/delete so users never act on a stale list.
        self._refresh = changed

        self._body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self._body.set_margin_top(24)
        self._body.set_margin_bottom(24)
        self._body.set_margin_start(24)
        self._body.set_margin_end(24)
        clamp = Adw.Clamp(maximum_size=860, tightening_threshold=700)
        clamp.set_child(self._body)
        self.append(scrollable(clamp))

        self._placeholder = Gtk.Label(label="Loading backups…")
        self._placeholder.add_css_class("fl-dim")
        self._body.append(self._placeholder)

    # ------------------------------------------------------------- updates

    def apply_snapshot(self, snap: Snapshot) -> None:
        clear_children(self._body)
        if not snap.backups:
            self._body.append(
                empty_state(
                    "The vault is empty",
                    "Backups are created automatically each time an apply would "
                    "overwrite an existing file.",
                )
            )
            return
        for record in snap.backups:
            self._body.append(self._build_row(record))

    # ------------------------------------------------------------ building

    def _build_row(self, record: BackupRecord) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("fl-card")

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        name = Gtk.Label(label=record.profile_name)
        name.add_css_class("fl-card-title")
        name.set_halign(Gtk.Align.START)
        top.append(name)
        top.append(operation_chip(record.operation))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        top.append(spacer)
        when = Gtk.Label(label=format_ts(record.created))
        when.add_css_class("fl-dim")
        top.append(when)
        card.append(top)

        meta = Gtk.Label(label=record.summary())
        meta.add_css_class("fl-dim")
        meta.set_halign(Gtk.Align.START)
        meta.set_xalign(0.0)
        meta.set_wrap(True)
        card.append(meta)
        if record.note:
            note = Gtk.Label(label=record.note, wrap=True)
            note.add_css_class("fl-mono")
            note.set_xalign(0.0)
            card.append(note)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        detail_btn = Gtk.Button(label="Files")
        detail_btn.add_css_class("flat")
        detail_btn.connect("clicked", lambda *_: self._show_files(record))
        restore_btn = Gtk.Button(label="Restore")
        restore_btn.add_css_class("flat")
        restore_btn.connect("clicked", lambda *_: self._confirm_restore(record))
        delete_btn = Gtk.Button(label="Delete")
        delete_btn.add_css_class("flat")
        delete_btn.add_css_class("fl-danger")
        delete_btn.connect("clicked", lambda *_: self._confirm_delete(record))
        for btn in (detail_btn, restore_btn, delete_btn):
            actions.append(btn)
        card.append(actions)
        return card

    # -------------------------------------------------------------- actions

    def _root(self):
        return self.get_root()

    def _dialog(self, heading: str, body: str) -> Adw.MessageDialog:
        dialog = Adw.MessageDialog.new(self._root(), heading, None)
        dialog.set_body(body)
        dialog.add_response("cancel", "Cancel")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        return dialog

    def _show_files(self, record: BackupRecord) -> None:
        try:
            _rec, files = self._controller.backup_detail(record.id)
        except Exception as exc:  # noqa: BLE001 — surfaced to the user
            self._toast(f"Could not inspect backup: {exc}")
            return
        if not files:
            listing = "(no archived files remain on disk)"
        else:
            listing = "\n".join(str(p) for p in files[:40])
            if len(files) > 40:
                listing += f"\n… and {len(files) - 40} more"
        dialog = Adw.MessageDialog.new(
            self._root(), f"Files in {record.id}", None
        )
        dialog.set_body(listing)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        dialog.present()

    def _confirm_restore(self, record: BackupRecord) -> None:
        dialog = self._dialog(
            f"Restore {record.id}?",
            f"This writes the {len(record.entries)} archived file(s) from "
            f"{record.profile_name} back to their original destinations. "
            "The current state is backed up first.",
        )
        dialog.add_response("confirm", "Restore files")
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _d, r: self._run_restore(record) if r == "confirm" else None)
        dialog.present()

    def _run_restore(self, record: BackupRecord) -> None:
        def job() -> BackupRecord:
            return self._controller.restore_backup(record.id)

        def done(_record, error) -> None:
            if error is not None:
                self._toast(f"Restore failed: {error}")
            else:
                self._toast(f"Restored {len(record.entries)} file(s).")
            self._refresh()

        run_in_background(job, done)

    def _confirm_delete(self, record: BackupRecord) -> None:
        dialog = self._dialog(
            f"Delete {record.id}?",
            "This permanently removes the archived files. Existing files at "
            "their destinations are not touched.",
        )
        dialog.add_response("confirm", "Delete")
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _d, r: self._run_delete(record) if r == "confirm" else None)
        dialog.present()

    def _run_delete(self, record: BackupRecord) -> None:
        def job() -> bool:
            return self._controller.delete_backup(record.id)

        def done(ok, error) -> None:
            if error is not None or not ok:
                self._toast("Could not delete backup.")
            else:
                self._toast(f"Deleted backup {record.id}.")
            self._refresh()

        run_in_background(job, done)

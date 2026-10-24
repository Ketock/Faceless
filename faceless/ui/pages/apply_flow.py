"""Apply flow for ProfileDetailView: confirm dialog → background apply → result.

Kept as a mixin so the (large) detail view stays focused on rendering;
this module owns only the apply interaction.
"""

from __future__ import annotations

from gi.repository import Adw, GLib

from faceless.core.engine import ApplyResult
from faceless.core.plan import ApplyPlan
from faceless.ui.widgets import run_in_background


class ApplyFlowMixin:
    """Mixin for ProfileDetailView; expects the view's attributes."""

    _controller: object
    _profile: object
    _plan: ApplyPlan | None
    _applying: bool
    _confirm_dialog: Adw.MessageDialog | None
    _status: GLib.Object
    _spinner: Adw.Object
    _apply_btn: Adw.Object
    _toast: object
    _changed: object
    _load_plan: object

    # ---------------------------------------------------------- entry point

    def _start_apply(self) -> None:
        profile, plan = self._profile, self._plan
        if profile is None or plan is None or self._applying:
            return
        if plan.blocked:
            self._toast("Plan is blocked — see the Compatibility section.")
            return
        if not self._controller.settings.confirm_before_apply:
            self._run_apply()
            return

        conflicts = [f.dest for f in plan.files if f.exists]
        body = []
        if conflicts:
            body.append("These existing files will be backed up and replaced:")
            body.extend(f"  • {d}" for d in conflicts[:8])
            if len(conflicts) > 8:
                body.append(f"  • … and {len(conflicts) - 8} more")
        else:
            body.append("No existing files will be replaced.")
        if plan.warnings:
            body.append("")
            body.append("Warnings:")
            body.extend(f"  • {w}" for w in plan.warnings)

        dialog = Adw.MessageDialog.new(self.get_root(), f"Apply {profile.name}?", None)
        dialog.set_body("\n".join(body))
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("confirm", "Apply rice")
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        self._confirm_dialog = dialog
        dialog.connect("response", self._on_confirm)
        dialog.present()

    def _on_confirm(self, dialog: Adw.MessageDialog, response: str) -> None:
        self._confirm_dialog = None
        if response == "confirm":
            self._run_apply()

    # ------------------------------------------------------------- running

    def _run_apply(self) -> None:
        profile = self._profile
        if profile is None or self._applying:
            return
        self._applying = True
        self._apply_btn.set_sensitive(False)
        self._spinner.set_spinning(True)
        self._status.set_text("Applying…")

        def progress(step: str, detail: str) -> None:
            GLib.idle_add(self._set_status, f"{step}: {detail}")

        def job():
            return self._controller.apply_profile(profile.id, progress=progress)

        run_in_background(job, self._on_applied)

    def _set_status(self, text: str) -> bool:
        self._status.set_text(text)
        return False

    def _on_applied(self, result: ApplyResult | None, error: Exception | None) -> None:
        self._applying = False
        self._spinner.set_spinning(False)
        profile = self._profile
        if error is not None or result is None:
            self._status.set_text(f"Apply crashed: {error}")
            self._toast("Apply failed unexpectedly.")
            self._changed()
            return
        name = profile.name if profile else result.profile.name
        if result.ok:
            self._status.set_text(
                f"Applied — {result.applied_files} file(s), reloaded: "
                + (", ".join(result.reloaded) or "nothing")
            )
            heading, body = f"Applied {name}", self._success_body(result)
        else:
            rolled = "and rolled back " if result.rolled_back else ""
            self._status.set_text(f"Apply failed {rolled}— see dialog")
            heading = f"Apply failed — {name}"
            body = result.error or "unknown error"
            if result.rolled_back:
                body += "\n\nYour previous files were restored from the backup."
            if result.warnings:
                body += "\n\n" + "\n".join(result.warnings)
        dialog = Adw.MessageDialog.new(self.get_root(), heading, None)
        dialog.set_body(body)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        dialog.present()
        self._changed()
        if profile is not None and result.ok:
            self._load_plan(keep_status=True)

    @staticmethod
    def _success_body(result: ApplyResult) -> str:
        lines = [
            f"{result.applied_files} file(s) written, {result.backed_up} backed up.",
        ]
        if result.reloaded:
            lines.append("Reloaded: " + ", ".join(result.reloaded))
        if result.wallpaper:
            lines.append(f"Wallpaper set: {result.wallpaper}")
        for warning in result.warnings:
            lines.append(f"⚠ {warning}")
        if not result.reloaded and not result.wallpaper:
            lines.append("No live reloads were needed.")
        return "\n".join(lines)

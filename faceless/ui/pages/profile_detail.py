"""ProfileDetailView — full profile dossier + the apply flow."""

from __future__ import annotations

import shutil

from gi.repository import Adw, Gtk

from faceless.controller import AppController, Snapshot
from faceless.core.plan import ApplyPlan
from faceless.core.schema import Profile
from faceless.ui.pages.apply_flow import ApplyFlowMixin
from faceless.ui.widgets import (
    chip_row,
    clear_children,
    compatibility_chip,
    make_chip,
    make_picture,
    placeholder_platter,
    run_in_background,
    scrollable,
)

_PAGE_CLAMP = 900


class ProfileDetailView(ApplyFlowMixin, Gtk.Box):
    """Preview gallery, metadata, target/file/compat sections, apply flow."""

    def __init__(self, controller: AppController, toast, go_back, changed):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._controller = controller
        self._toast = toast
        self._go_back = go_back
        self._changed = changed
        self._profile: Profile | None = None
        self._plan: ApplyPlan | None = None
        self._snap: Snapshot | None = None
        self._applying = False
        self._confirm_dialog: Adw.MessageDialog | None = None

        self._status = Gtk.Label(label="")
        self._status.add_css_class("fl-dim")
        self._status.set_ellipsize(3)
        self._spinner = Gtk.Spinner()
        self._apply_btn = Gtk.Button(label="Apply rice")
        self._apply_btn.add_css_class("fl-apply-button")
        self._apply_btn.set_sensitive(False)
        self._apply_btn.connect("clicked", lambda *_: self._start_apply())

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bottom.set_margin_top(10)
        bottom.set_margin_bottom(14)
        bottom.set_margin_start(24)
        bottom.set_margin_end(24)
        bottom.append(self._spinner)
        bottom.append(self._status)
        bottom.append(Gtk.Box())  # spacer
        self._status.set_hexpand(True)
        bottom.append(self._apply_btn)

        self._body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        clamp = Adw.Clamp(maximum_size=_PAGE_CLAMP, tightening_threshold=760)
        clamp.set_child(self._body)
        scrolled = scrollable(clamp)
        bar = Adw.ToolbarView()
        bar.set_content(scrolled)
        bar.add_bottom_bar(bottom)
        self.append(bar)

    # ------------------------------------------------------------- public

    def show_profile(self, profile: Profile, snap: Snapshot | None) -> None:
        self._profile = profile
        self._snap = snap
        self._plan = None
        self._status.set_text("")
        self._spinner.set_spinning(True)
        self._apply_btn.set_sensitive(False)
        self._render()
        self._load_plan()

    def apply_snapshot(self, snap: Snapshot) -> None:
        self._snap = snap
        if self._profile is not None and self._plan is None and not self._applying:
            self._load_plan()

    def current_title(self) -> str:
        """Window header title for this page."""
        return self._profile.name if self._profile is not None else "Profile"

    # ------------------------------------------------------------ planning

    def _load_plan(self, keep_status: bool = False) -> None:
        if self._profile is None:
            return

        def job() -> ApplyPlan:
            return self._controller.plan_for(self._profile.id)  # type: ignore[union-attr]

        def done(plan: ApplyPlan | None, error: Exception | None) -> None:
            self._on_plan(plan, error, keep_status=keep_status)

        run_in_background(job, done)

    def _on_plan(
        self, plan: ApplyPlan | None, error: Exception | None, keep_status: bool = False
    ) -> None:
        self._spinner.set_spinning(False)
        if error is not None:
            self._status.set_text(f"Could not compute plan: {error}")
            return
        if self._profile is None or plan.profile.id != self._profile.id:
            return
        self._plan = plan
        self._render()
        if not keep_status:
            self._status.set_text("")
        self._apply_btn.set_sensitive(not plan.blocked and not self._applying)

    # ------------------------------------------------------------ rendering

    def _render(self) -> None:
        clear_children(self._body)
        profile = self._profile
        if profile is None:
            return
        self._body.append(self._build_back_row(profile))
        self._body.append(self._build_header(profile))
        self._body.append(self._build_gallery(profile))
        self._body.append(self._build_tags(profile))
        self._body.append(self._build_targets(profile))
        self._body.append(self._build_files_card())
        self._body.append(self._build_compat_card())
        self._body.append(self._build_changes_card())

    def _section(self, title: str) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("fl-card")
        label = Gtk.Label(label=title)
        label.add_css_class("fl-section-title")
        label.set_halign(Gtk.Align.START)
        label.set_xalign(0.0)
        card.append(label)
        return card

    def _build_back_row(self, profile: Profile) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button = Gtk.Button()
        content = Adw.ButtonContent(icon_name="go-previous-symbolic", label="Rice Library")
        button.set_child(content)
        button.add_css_class("flat")
        button.set_valign(Gtk.Align.CENTER)
        button.connect("clicked", lambda *_: self._go_back())
        row.append(button)
        return row

    def _build_header(self, profile: Profile) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title = Gtk.Label(label=profile.name)
        title.add_css_class("fl-display")
        title.add_css_class("fl-display-xl")
        title.set_xalign(0.0)
        title.set_hexpand(True)
        title.set_wrap(True)
        title_row.append(title)
        if self._plan is not None:
            title_row.append(compatibility_chip(self._plan.compatibility))
        box.append(title_row)

        meta = " · ".join(
            x for x in (f"v{profile.version}", profile.author and f"by {profile.author}") if x
        )
        meta_label = Gtk.Label(label=meta or profile.id)
        meta_label.add_css_class("fl-dim")
        meta_label.set_halign(Gtk.Align.START)
        box.append(meta_label)

        desc = Gtk.Label(label=profile.description, wrap=True)
        desc.set_halign(Gtk.Align.START)
        desc.set_xalign(0.0)
        box.append(desc)
        return box

    def _build_gallery(self, profile: Profile) -> Gtk.Widget:
        pictures = []
        try:
            candidates = profile.preview_paths()
        except Exception:  # noqa: BLE001
            candidates = []
        for path in candidates:
            picture = make_picture(path, Gtk.ContentFit.CONTAIN)
            if picture is not None:
                picture.set_size_request(-1, 260)
                pictures.append(picture)
        if not pictures:
            return placeholder_platter(200)
        if len(pictures) == 1:
            return pictures[0]
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        stack.set_transition_duration(220)
        stack.set_size_request(-1, 260)
        for index, picture in enumerate(pictures):
            stack.add_named(picture, f"preview-{index}")
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        prev = Gtk.Button(icon_name="go-previous-symbolic")
        nxt = Gtk.Button(icon_name="go-next-symbolic")
        prev.connect("clicked", lambda *_: self._step_gallery(stack, -1, len(pictures)))
        nxt.connect("clicked", lambda *_: self._step_gallery(stack, 1, len(pictures)))
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav.set_halign(Gtk.Align.CENTER)
        nav.append(prev)
        nav.append(nxt)
        controls.append(stack)
        controls.append(nav)
        return controls

    def _step_gallery(self, stack: Gtk.Stack, delta: int, count: int) -> None:
        current = int(stack.get_visible_child_name().rsplit("-", 1)[-1])
        stack.set_visible_child_name(f"preview-{(current + delta) % count}")

    def _build_tags(self, profile: Profile) -> Gtk.Widget | None:
        if not profile.tags:
            return None
        row = chip_row()
        for tag in profile.tags:
            row.append(make_chip(tag))
        return row

    def _build_targets(self, profile: Profile) -> Gtk.Box:
        card = self._section("Targets")
        row = chip_row()
        states = {c.adapter_id: c for c in self._snap.components} if self._snap else {}
        for target in profile.targets:
            state = states.get(target)
            if state is None:
                chip = make_chip(target, "missing", "No component adapter for this target")
            elif state.active:
                chip = make_chip(f"{target} · active", "good", str(state.detail or ""))
            elif state.installed:
                chip = make_chip(f"{target} · installed", "installed")
            else:
                chip = make_chip(f"{target} · not installed", "missing", "will apply on next launch")
            row.append(chip)
        card.append(row)
        if profile.requires:
            label = Gtk.Label(label="Requires")
            label.add_css_class("fl-section-title")
            label.set_halign(Gtk.Align.START)
            card.append(label)
            req_row = chip_row()
            for dep in profile.requires:
                if shutil.which(dep):
                    req_row.append(make_chip(dep, "installed"))
                else:
                    req_row.append(make_chip(dep, "missing", "missing dependency"))
            card.append(req_row)
        if profile.wallpaper:
            wall = Gtk.Label(label=f"Wallpaper: {profile.wallpaper}")
            wall.add_css_class("fl-dim")
            wall.set_halign(Gtk.Align.START)
            card.append(wall)
        return card

    def _build_files_card(self) -> Gtk.Box:
        card = self._section("Managed files")
        self._files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.append(self._files_box)
        if self._plan is None:
            hint = Gtk.Label(label="Calculating planned changes…")
            hint.add_css_class("fl-dim")
            self._files_box.append(hint)
        else:
            self._fill_files()
        return card

    def _fill_files(self) -> None:
        clear_children(self._files_box)
        plan = self._plan
        if plan is None:
            return
        for planned in plan.files[:40]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            dest = Gtk.Label(label=planned.dest or planned.spec.display_dest())
            dest.add_css_class("fl-mono")
            dest.set_halign(Gtk.Align.START)
            dest.set_ellipsize(1)  # PANGO_ELLIPSIZE_START keeps the filename visible
            dest.set_hexpand(True)
            row.append(dest)
            if planned.problem:
                row.append(make_chip("unsafe", "bad", planned.problem))
            elif planned.exists:
                row.append(make_chip("overwrites", "partial", "existing file will be backed up"))
            else:
                row.append(make_chip("new", "full"))
            self._files_box.append(row)
        if len(plan.files) > 40:
            more = Gtk.Label(label=f"… and {len(plan.files) - 40} more files")
            more.add_css_class("fl-dim")
            self._files_box.append(more)

    def _build_compat_card(self) -> Gtk.Box:
        card = self._section("Compatibility")
        self._compat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.append(self._compat_box)
        if self._plan is None:
            hint = Gtk.Label(label="Calculating…")
            hint.add_css_class("fl-dim")
            self._compat_box.append(hint)
        else:
            self._fill_compat()
        return card

    def _fill_compat(self) -> None:
        clear_children(self._compat_box)
        plan = self._plan
        if plan is None:
            return
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(compatibility_chip(plan.compatibility))
        if plan.blocked:
            head.append(make_chip("plan blocked", "bad", plan.blocked_reason))
        self._compat_box.append(head)
        for reason in plan.compat_reasons:
            line = Gtk.Label(label=reason, wrap=True)
            line.add_css_class("fl-warning-text")
            line.set_xalign(0.0)
            self._compat_box.append(line)
        if plan.missing_requires:
            line = Gtk.Label(
                label="missing dependencies: " + ", ".join(plan.missing_requires), wrap=True
            )
            line.add_css_class("fl-danger")
            line.set_xalign(0.0)
            self._compat_box.append(line)

    def _build_changes_card(self) -> Gtk.Box:
        card = self._section("Planned changes")
        self._changes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.append(self._changes_box)
        if self._plan is None:
            hint = Gtk.Label(label="Calculating planned changes…")
            hint.add_css_class("fl-dim")
            self._changes_box.append(hint)
        else:
            self._fill_changes()
        return card

    def _fill_changes(self) -> None:
        clear_children(self._changes_box)
        plan = self._plan
        if plan is None:
            return
        profile = plan.profile
        overwrites = sum(1 for f in plan.files if f.exists and not f.problem)
        lines = [
            f"{len(plan.files)} file(s) to write",
            f"{overwrites} existing file(s) will be backed up first",
            f"wallpaper: {profile.wallpaper or 'none'}",
            "live reload: " + ("enabled" if self._controller.engine.live_reload else "disabled"),
        ]
        for text in lines:
            line = Gtk.Label(label=text, wrap=True)
            line.set_xalign(0.0)
            self._changes_box.append(line)
        for warning in plan.warnings:
            line = Gtk.Label(label=warning, wrap=True)
            line.add_css_class("fl-warning-text")
            line.set_xalign(0.0)
            self._changes_box.append(line)


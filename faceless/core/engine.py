"""The safe apply engine: plan → backup → stage → apply → reload → record.

Guarantees:
- every overwrite is preceded by a backup inside this same call;
- payloads are staged in a temp dir and atomically moved into place;
- a failure after staging triggers automatic rollback from the backup;
- no untrusted code is executed; no root is required; no session restarts.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from faceless import paths
from faceless.core import history, safefs
from faceless.core import plan as plan_mod
from faceless.core.backups import BackupError, BackupStore
from faceless.core.jsonio import atomic_json_write
from faceless.core.plan import ApplyPlan
from faceless.core.schema import Profile, ProfileError
from faceless.logging import logger

_LOG = logger("faceless.engine")


class ApplyFailure(Exception):  # noqa: N818 — established public API name
    """A profile apply failed (rollback was attempted)."""


@dataclass
class ApplyResult:
    ok: bool
    profile: Profile
    backup_id: str = ""
    applied_files: int = 0
    backed_up: int = 0
    reloaded: list[str] = field(default_factory=list)
    reload_warnings: list[str] = field(default_factory=list)
    wallpaper: str = ""
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    rolled_back: bool = False


@dataclass
class ActiveRice:
    profile_id: str
    applied_at: float


class ApplyEngine:
    def __init__(
        self,
        backup_store: BackupStore | None = None,
        *,
        live_reload: bool = True,
        set_wallpaper: bool = True,
    ):
        self.backups = backup_store or BackupStore()
        self.live_reload = live_reload
        self.set_wallpaper = set_wallpaper

    # ------------------------------------------------------------------ API
    def plan(self, profile: Profile) -> ApplyPlan:
        return plan_mod.build_plan(profile)

    def apply(
        self,
        profile: Profile,
        progress=None,  # optional callable(step: str, detail: str)
    ) -> ApplyResult:
        def notify(step: str, detail: str) -> None:
            _LOG.info("apply[%s]: %s", profile.id, detail)
            if progress:
                progress(step, detail)

        notify("validate", "validating profile manifest")
        plan = self.plan(profile)
        if plan.blocked:
            return ApplyResult(False, profile, error=f"plan blocked: {plan.blocked_reason}")
        failed_file = next((f for f in plan.files if f.problem), None)
        if failed_file:
            return ApplyResult(
                False, profile,
                error=f"cannot apply {failed_file.spec.display_dest()}: {failed_file.problem}",
            )

        staging_dir = self._make_staging_dir()
        try:
            notify("stage", f"staging {len(profile.files)} file(s)")
            staged = self._stage_payload(profile, staging_dir)

            dests = [Path(f.dest) for f in plan.files if f.dest]
            existing = [d for d in dests if d.is_file() or d.is_symlink()]
            notify("backup", f"backing up {len(existing)} existing file(s)")
            try:
                backup = self.backups.create(
                    existing,
                    profile_id=profile.id,
                    profile_name=profile.name,
                    operation="apply",
                    note=f"before applying {profile.id} v{profile.version}",
                )
            except BackupError as exc:
                raise ApplyFailure(f"backup failed, nothing applied: {exc}") from exc

            try:
                notify("apply", "applying staged files")
                count = self._apply_files(plan, staged)
            except Exception as exc:
                notify("rollback", f"apply failed ({exc}); rolling back")
                restored, rollback_failures = self._rollback_from_backup(backup, plan)
                detail = f"rolled back after failed apply: {exc}"
                if rollback_failures:
                    detail += f"; rollback incomplete: {'; '.join(rollback_failures)}"
                history.record(
                    history.HistoryEntry(
                        ts=time.time(), operation="rollback", profile_id=profile.id,
                        profile_name=profile.name,
                        status="failure" if rollback_failures else "success",
                        detail=detail,
                        backup_id=backup.id,
                    )
                )
                raise ApplyFailure(
                    f"apply failed and was rolled back ({restored} file(s) restored): {exc}"
                    + (f" ROLLBACK ISSUES: {'; '.join(rollback_failures)}" if rollback_failures else "")
                ) from exc

            warnings: list[str] = []
            wallpaper_note = ""
            if profile.wallpaper and self.set_wallpaper:
                notify("wallpaper", "applying profile wallpaper")
                wallpaper_note = self._apply_wallpaper(profile, warnings)

            reloaded, reload_warnings = self._reload_components(plan, notify)
            warnings.extend(reload_warnings)

            self._mark_active(profile)
            history.record(
                history.HistoryEntry(
                    ts=time.time(), operation="apply", profile_id=profile.id,
                    profile_name=profile.name, status="success",
                    backup_id=backup.id, files_touched=count,
                    warnings=warnings,
                )
            )
            notify("done", f"applied {profile.name} ({count} files)")
            return ApplyResult(
                ok=True, profile=profile, backup_id=backup.id, applied_files=count,
                backed_up=len(backup.entries), reloaded=reloaded, wallpaper=wallpaper_note,
                warnings=warnings,
            )
        except ApplyFailure:
            raise
        except (ProfileError, BackupError, OSError) as exc:
            _LOG.exception("apply of %s failed", profile.id)
            history.record(
                history.HistoryEntry(
                    ts=time.time(), operation="apply", profile_id=profile.id,
                    profile_name=profile.name, status="failure", detail=str(exc),
                )
            )
            return ApplyResult(False, profile, error=str(exc))
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    # ------------------------------------------------------------ internals
    def _make_staging_dir(self) -> Path:
        base = paths.state_home() / "faceless" / "staging"
        base.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="apply-", dir=base))

    def _stage_payload(self, profile: Profile, staging_dir: Path) -> dict[tuple[str, str], Path]:
        staged: dict[tuple[str, str], Path] = {}
        for i, spec in enumerate(profile.files):
            payload = profile.directory / spec.payload
            # Defense in depth: payload must stay inside the profile directory.
            try:
                payload.resolve().relative_to(profile.directory.resolve())
            except ValueError as exc:
                raise ApplyFailure(f"payload escapes profile dir: {spec.payload}") from exc
            target = staging_dir / f"{i:04d}" / Path(spec.dest_rel).name
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(payload, target)
            except OSError as exc:
                raise ApplyFailure(f"staging failed for {spec.payload}: {exc}") from exc
            staged[(spec.dest_root, spec.dest_rel)] = target
        return staged

    def _apply_files(self, plan: ApplyPlan, staged: dict[tuple[str, str], Path]) -> int:
        count = 0
        for planned in plan.files:
            if planned.problem:
                raise ApplyFailure(f"cannot apply {planned.spec.display_dest()}: {planned.problem}")
            key = (planned.spec.dest_root, planned.spec.dest_rel)
            source = staged[key]
            dest = Path(planned.dest)
            if safefs.parent_symlink_escape(dest):
                raise ApplyFailure(f"destination {dest} would escape $HOME via symlink")
            resolved = safefs.ensure_within(dest, planned.spec.dest_root)
            if dest.is_symlink():
                # dest itself is a symlink pointing elsewhere; replace the link,
                # never follow it into the target (could clobber foreign data).
                _LOG.info("replacing symlink at %s (resolves to %s)", dest, resolved)
            safefs.atomic_replace(source, dest)
            count += 1
        return count

    def _apply_wallpaper(self, profile: Profile, warnings: list[str]) -> str:
        from faceless.adapters import get as get_adapter

        adapter = get_adapter("wallpaper")
        if adapter is None or profile.wallpaper is None:
            return ""
        image = profile.directory / profile.wallpaper
        try:
            image.resolve().relative_to(profile.directory.resolve())
        except ValueError:
            warnings.append("wallpaper asset escapes profile dir; skipped")
            return ""
        store_dir = paths.data_home() / "faceless" / "wallpapers" / profile.id
        try:
            store_dir.mkdir(parents=True, exist_ok=True)
            # Store under a fixed, engine-controlled name: wallpaper filenames come
            # from untrusted profiles and must never reach command/script contexts.
            suffix = image.suffix
            if not re.fullmatch(r"\.[A-Za-z0-9]{1,7}", suffix):
                suffix = ".png"
            stored = store_dir / f"wallpaper{suffix}"
            shutil.copyfile(image, stored)
        except OSError as exc:
            warnings.append(f"could not stage wallpaper: {exc}")
            return ""
        outcome = adapter.set_wallpaper(stored)  # type: ignore[union-attr]
        if not outcome.ok:
            warnings.append(f"wallpaper: {outcome.detail} {outcome.requires_restart_hint}".strip())
        return str(stored)

    def _reload_components(
        self, plan: ApplyPlan, notify
    ) -> tuple[list[str], list[str]]:
        reloaded: list[str] = []
        warnings: list[str] = []
        if not self.live_reload:
            warnings.append("live reload disabled in settings; changes apply on next launch.")
            return reloaded, warnings
        for adapter in plan_mod.reload_targets(plan.profile):
            if not adapter.is_active():
                continue
            notify("reload", f"reloading {adapter.name}")
            outcome = adapter.reload()
            if outcome.ok:
                reloaded.append(adapter.name)
            else:
                warnings.append(f"{adapter.name}: {outcome.detail} {outcome.requires_restart_hint}".strip())
        return reloaded, warnings

    def _rollback_from_backup(self, backup, plan: ApplyPlan) -> tuple[int, list[str]]:
        """Restore the pre-apply state. Returns (restored_count, failure_notes).

        - Files that existed before (in the backup) are restored atomically.
        - Files created by the failed apply (no backup entry) are removed.
        - The backup itself is always kept for manual recovery.
        """
        restored = 0
        failures: list[str] = []
        backed_up_dests = {e.dest for e in backup.entries}

        for planned in plan.files:
            dest = Path(planned.dest)
            if not planned.dest or planned.problem:
                continue
            if str(dest) in backed_up_dests:
                entry = next(e for e in backup.entries if e.dest == str(dest))
                archived = self.backups.root / backup.id / "content" / entry.archived
                if not archived.is_file():
                    failures.append(f"{dest}: archived copy missing")
                    continue
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.is_symlink() or (dest.is_file() and not dest.is_symlink()):
                        pass  # unlink below via os.replace over any existing node
                    tmp = dest.parent / f".fl-rb-{uuid.uuid4().hex[:10]}"
                    shutil.copy2(archived, tmp)
                    os.replace(tmp, dest)  # atomic, replaces file or dangling link
                    try:
                        dest.chmod(entry.mode & 0o777)
                    except OSError:
                        pass
                    restored += 1
                except OSError as exc:
                    failures.append(f"{dest}: {exc}")
            else:
                # Created by this apply — remove to restore the pre-state.
                try:
                    if dest.is_file() or dest.is_symlink():
                        dest.unlink()
                        restored += 1
                except OSError as exc:
                    failures.append(f"{dest}: could not remove applied file: {exc}")
        _LOG.info(
            "rollback for backup %s: %d handled, %d failure(s)",
            backup.id, restored, len(failures),
        )
        return restored, failures

    def _mark_active(self, profile: Profile) -> None:
        path = paths.data_home() / "faceless" / "active.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json_write(path, {"profile_id": profile.id, "applied_at": time.time()})
        except OSError as exc:
            _LOG.warning("could not record active profile: %s", exc)


def active_rice() -> ActiveRice | None:
    path = paths.data_home() / "faceless" / "active.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ActiveRice(profile_id=data["profile_id"], applied_at=data["applied_at"])
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def clear_active() -> None:
    path = paths.data_home() / "faceless" / "active.json"
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass

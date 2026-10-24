"""AppController — the single seam between the GTK UI and the core engine.

The UI layer only ever talks to this class (or data returned by it). Core
modules stay GUI-free and testable.
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from faceless import adapters, paths
from faceless import settings as settings_mod
from faceless.core import detection, history
from faceless.core import engine as engine_mod
from faceless.core import plan as plan_mod
from faceless.core.backups import BackupError, BackupRecord, BackupStore
from faceless.core.engine import ActiveRice, ApplyEngine, ApplyFailure, ApplyResult
from faceless.core.profile_loader import Library, scan
from faceless.core.schema import Profile, ProfileError
from faceless.logging import logger

_LOG = logger("faceless.controller")


@dataclass
class Snapshot:
    session: detection.Session
    gtk_settings: dict[str, str]
    components: list[adapters.ComponentState]
    library: Library
    active: ActiveRice | None
    backups: list[BackupRecord]
    history: list[history.HistoryEntry]
    library_paths: list[str]


class AppController:
    def __init__(self) -> None:
        self.settings = settings_mod.load()
        self.engine = ApplyEngine(
            live_reload=self.settings.enable_live_reload,
            set_wallpaper=True,
        )
        # Serializes apply/restore/delete so concurrent UI jobs can never
        # interleave writes to the same destinations.
        self._operation_lock = threading.Lock()
        self._library: Library | None = None

    # ------------------------------------------------------------- snapshot
    def snapshot(self) -> Snapshot:
        return Snapshot(
            session=detection.detect_session(),
            gtk_settings=detection.detect_gtk_settings(),
            components=adapters.all_states(),
            library=self.library(),
            active=engine_mod.active_rice(),
            backups=self._backup_store().list(),
            history=history.recent(15),
            library_paths=[str(p) for p in self._all_library_dirs()],
        )

    # ------------------------------------------------------------- library
    def library(self, refresh: bool = False) -> Library:
        if self._library is None or refresh:
            self._library = scan(self._all_library_dirs())
        return self._library

    def get_profile(self, profile_id: str) -> Profile | None:
        return self.library().by_id(profile_id)

    def _all_library_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        for raw in self.settings.library_paths:
            candidate = Path(raw).expanduser()
            if candidate.is_dir() and candidate not in dirs:
                dirs.append(candidate)
        for d in paths.library_dirs():
            if d.is_dir() and d not in dirs:
                dirs.append(d)
        return dirs

    def plan_for(self, profile_id: str) -> plan_mod.ApplyPlan:
        profile = self.get_profile(profile_id)
        if profile is None:
            raise ProfileError(f"unknown profile {profile_id!r}")
        return self.engine.plan(profile)

    # ------------------------------------------------------------- apply
    def apply_profile(
        self, profile_id: str, progress=None
    ) -> ApplyResult:
        profile = self.get_profile(profile_id)
        if profile is None:
            raise ProfileError(f"unknown profile {profile_id!r}")
        with self._operation_lock:
            try:
                return self.engine.apply(profile, progress=progress)
            except ApplyFailure as exc:
                _LOG.error("apply failed: %s", exc)
                result = ApplyResult(False, profile, error=str(exc), rolled_back=True)
                return result

    # ------------------------------------------------------------- backups
    def _backup_store(self) -> BackupStore:
        override = self.settings.backup_dir.strip()
        root = Path(override).expanduser() if override else None
        return BackupStore(root)

    def backups_list(self) -> list[BackupRecord]:
        return self._backup_store().list()

    def backup_detail(self, backup_id: str) -> tuple[BackupRecord, list[Path]]:
        return self._backup_store().inspect(backup_id)

    def restore_backup(self, backup_id: str) -> BackupRecord:
        with self._operation_lock:
            record = self._backup_store().restore(backup_id)
        history.record(
            history.HistoryEntry(
                ts=record.created,
                operation="restore",
                profile_id=record.profile_id,
                profile_name=record.profile_name,
                status="success",
                detail=f"restored backup {backup_id}",
                backup_id=backup_id,
                files_touched=len(record.entries),
            )
        )
        return record

    def delete_backup(self, backup_id: str) -> bool:
        # Defense in depth: validate the id before touching the filesystem.
        try:
            self._backup_store()._record_path(backup_id)
        except BackupError:
            return False
        record_dir = self._backup_store().root / backup_id
        with self._operation_lock:
            try:
                shutil.rmtree(record_dir)
                _LOG.info("deleted backup %s", backup_id)
                return True
            except OSError as exc:
                _LOG.error("could not delete backup %s: %s", backup_id, exc)
                return False

    # ------------------------------------------------------------- settings
    def save_settings(self) -> bool:
        ok = settings_mod.save(self.settings)
        if ok:
            self.engine.live_reload = self.settings.enable_live_reload
            self._library = None  # rescan with new paths
        return ok

    def add_library_path(self, path: str) -> tuple[bool, str]:
        candidate = Path(path).expanduser()
        if not candidate.is_dir():
            return False, f"{path} is not a directory"
        resolved = str(candidate.resolve())
        if resolved in self.settings.library_paths:
            return False, "already configured"
        self.settings.library_paths.append(resolved)
        return (self.save_settings(), resolved)

    def remove_library_path(self, path: str) -> bool:
        if path in self.settings.library_paths:
            self.settings.library_paths.remove(path)
            return self.save_settings()
        return False

    # ------------------------------------------------------------- diagnostics
    def diagnostics(self) -> list[str]:
        lines = [f"Faceless diagnostics — {time.strftime('%Y-%m-%d %H:%M:%S')}"]
        snap = self.snapshot()
        lines.append(f"session: {snap.session.kind} ({snap.session.display_server}) — {snap.session.detail}")
        lines.append(f"home: {paths.home()}")
        lines.append(f"config home: {paths.config_home()}")
        lines.append(f"library dirs: {', '.join(str(d) for d in self._all_library_dirs()) or '(none)'}")
        lines.append(f"backup root: {self._backup_store().root}")
        lines.append(f"profiles found: {len(snap.library.profiles)}; problems: {len(snap.library.problems)}")
        for problem, reason in snap.library.problems.items():
            lines.append(f"  ! {problem}: {reason}")
        for c in snap.components:
            state = "active" if c.active else "installed" if c.installed else "absent"
            lines.append(f"component {c.adapter_id}: {state}")
        if snap.active:
            lines.append(f"active rice: {snap.active.profile_id}")
        return lines

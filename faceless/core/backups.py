"""Backup store: timestamped, restorable snapshots of overwritten configs.

Layout::

    <backup_root>/<id>/
      backup.json          # metadata + original destinations + modes
      content/…            # files mirrored from their destination structure
"""

from __future__ import annotations

import json
import shutil
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from faceless import paths
from faceless.core import safefs
from faceless.logging import logger

_LOG = logger("faceless.backups")


class BackupError(Exception):
    pass


@dataclass
class BackupEntry:
    dest: str          # absolute original path
    archived: str      # relative path inside content/
    mode: int


@dataclass
class BackupRecord:
    id: str
    created: float
    profile_id: str
    profile_name: str
    operation: str     # apply | restore
    entries: list[BackupEntry]
    note: str = ""

    def summary(self) -> str:
        return f"{self.id} · {self.profile_name} · {len(self.entries)} file(s)"


class BackupStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else paths.backup_root()

    def _record_path(self, backup_id: str) -> Path:
        if not backup_id or "/" in backup_id or ".." in backup_id or "\\" in backup_id:
            raise BackupError(f"invalid backup id {backup_id!r}")
        return self.root / backup_id / "backup.json"

    def create(
        self,
        dest_files: list[Path],
        profile_id: str,
        profile_name: str,
        operation: str = "apply",
        note: str = "",
    ) -> BackupRecord:
        """Archive every existing file in dest_files. Missing files are skipped."""
        backup_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        backup_dir = self.root / backup_id
        content_dir = backup_dir / "content"
        entries: list[BackupEntry] = []

        try:
            for dest in dest_files:
                dest = Path(dest)
                if not dest.is_file() and not dest.is_symlink():
                    continue
                if dest.is_symlink() and not dest.resolve(strict=False).is_file():
                    continue  # dangling or odd symlink: skip, never follow into trees
                if dest.is_symlink():
                    # A symlink *to* a file outside $HOME must not be archived
                    # by content — that would copy foreign data into the vault.
                    home = paths.home().resolve()
                    try:
                        dest.resolve(strict=False).relative_to(home)
                    except ValueError:
                        _LOG.warning("backup: skipping symlink escaping $HOME: %s", dest)
                        continue
                try:
                    safe = dest.resolve(strict=False)
                except OSError:
                    continue
                archived = str(uuid.uuid4().hex[:12]) + "_" + safe.name
                target = content_dir / archived
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(safe, target, follow_symlinks=True)
                except OSError as exc:
                    raise BackupError(f"could not archive {dest}: {exc}") from exc
                try:
                    mode = stat.S_IMODE(safe.stat(follow_symlinks=True).st_mode)
                except OSError:
                    mode = 0o644
                entries.append(BackupEntry(dest=str(dest), archived=archived, mode=mode))

            record = BackupRecord(
                id=backup_id,
                created=time.time(),
                profile_id=profile_id,
                profile_name=profile_name,
                operation=operation,
                entries=entries,
                note=note,
            )
            backup_dir.mkdir(parents=True, exist_ok=True)
            self._record_path(backup_id).write_text(
                json.dumps(self._serialize(record), indent=2), encoding="utf-8"
            )
        except OSError as exc:
            # Never leave orphaned partial backups behind.
            shutil.rmtree(backup_dir, ignore_errors=True)
            if isinstance(exc, BackupError):
                raise
            raise BackupError(f"could not write backup: {exc}") from exc
        except BackupError:
            shutil.rmtree(backup_dir, ignore_errors=True)
            raise
        _LOG.info(
            "backup %s created for %s (%d files)", backup_id, profile_id, len(entries)
        )
        return record

    def _serialize(self, record: BackupRecord) -> dict:
        return {
            "id": record.id,
            "created": record.created,
            "profile_id": record.profile_id,
            "profile_name": record.profile_name,
            "operation": record.operation,
            "note": record.note,
            "entries": [e.__dict__ for e in record.entries],
        }

    def list(self) -> list[BackupRecord]:
        out: list[BackupRecord] = []
        if not self.root.is_dir():
            return out
        for entry_dir in self.root.iterdir():
            meta = entry_dir / "backup.json"
            if not entry_dir.is_dir() or not meta.is_file():
                continue
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                out.append(
                    BackupRecord(
                        id=data["id"],
                        created=data["created"],
                        profile_id=data.get("profile_id", "?"),
                        profile_name=data.get("profile_name", "?"),
                        operation=data.get("operation", "apply"),
                        entries=[
                            BackupEntry(e["dest"], e["archived"], e["mode"])
                            for e in data.get("entries", [])
                        ],
                        note=data.get("note", ""),
                    )
                )
            except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
                _LOG.warning("skipping unreadable backup %s: %s", entry_dir, exc)
        # Newest first; tie-break on id (timestamp prefix) then reverse name.
        out.sort(key=lambda r: (r.created, r.id), reverse=True)
        return out

    def inspect(self, backup_id: str) -> tuple[BackupRecord, list[Path]]:
        record = self.get(backup_id)
        files = []
        for entry in record.entries:
            candidate = self.root / record.id / "content" / entry.archived
            if candidate.is_file():
                files.append(candidate)
        return record, files

    def get(self, backup_id: str) -> BackupRecord:
        path = self._record_path(backup_id)
        if not path.is_file():
            raise BackupError(f"backup {backup_id!r} not found")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return BackupRecord(
                id=data["id"],
                created=data["created"],
                profile_id=data.get("profile_id", "?"),
                profile_name=data.get("profile_name", "?"),
                operation=data.get("operation", "apply"),
                entries=[BackupEntry(e["dest"], e["archived"], e["mode"]) for e in data.get("entries", [])],
                note=data.get("note", ""),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise BackupError(f"backup metadata corrupt: {exc}") from exc

    def restore(self, backup_id: str) -> BackupRecord:
        """Restore every archived file to its original destination.

        Only files recorded in this backup are touched; nothing else is
        removed. Pre-restores the current state as a safety backup.
        """
        record = self.get(backup_id)
        if not record.entries:
            raise BackupError("backup contains no restorable files")

        # Safety: snapshot whatever is currently at the destinations.
        self.create(
            [Path(e.dest) for e in record.entries],
            profile_id=record.profile_id,
            profile_name=record.profile_name,
            operation="pre-restore",
            note=f"auto-snapshot before restoring {backup_id}",
        )

        restored = 0
        for entry in record.entries:
            archived = self.root / record.id / "content" / entry.archived
            if not archived.is_file():
                _LOG.warning("backup %s: missing archived file %s", record.id, entry.archived)
                continue
            dest = Path(entry.dest)
            try:
                safefs.ensure_within(dest, self._root_of(dest))
                safefs.atomic_replace(archived, dest)
                try:
                    dest.chmod(entry.mode & 0o777)
                except OSError:
                    pass
                restored += 1
            except (safefs.UnsafePathError, OSError) as exc:
                raise BackupError(
                    f"restore aborted after {restored}/{len(record.entries)} files: {exc}"
                ) from exc
        _LOG.info("restore %s: %d/%d files restored", record.id, restored, len(record.entries))
        return record

    @staticmethod
    def _root_of(dest: Path) -> str:
        from faceless import paths as p

        s = str(dest)
        for root_name, base in (
            ("config", p.config_home()),
            ("share", p.data_home()),
            ("state", p.state_home()),
            ("home", p.home()),
        ):
            if s.startswith(str(base) + "/"):
                return root_name
        return "home"

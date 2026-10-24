"""Operation history — append-only JSON log of everything Faceless changed."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from faceless import paths
from faceless.core.jsonio import atomic_json_write
from faceless.logging import logger

_LOG = logger("faceless.history")

MAX_ENTRIES = 500


@dataclass
class HistoryEntry:
    ts: float
    operation: str          # apply | restore | rollback | pre-restore
    profile_id: str
    profile_name: str
    status: str             # success | failure
    detail: str = ""
    backup_id: str = ""
    files_touched: int = 0
    warnings: list[str] = field(default_factory=list)


def record(entry: HistoryEntry) -> bool:
    path = paths.history_file()
    try:
        entries = read_all()
        entries.append(entry)
        if len(entries) > MAX_ENTRIES:
            entries = entries[-MAX_ENTRIES:]
        payload = [e.__dict__ for e in entries]
        atomic_json_write(path, payload)
        return True
    except OSError as exc:
        _LOG.error("could not write history: %s", exc)
        return False


def read_all() -> list[HistoryEntry]:
    path = paths.history_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            HistoryEntry(
                ts=item["ts"],
                operation=item["operation"],
                profile_id=item["profile_id"],
                profile_name=item["profile_name"],
                status=item["status"],
                detail=item.get("detail", ""),
                backup_id=item.get("backup_id", ""),
                files_touched=item.get("files_touched", 0),
                warnings=item.get("warnings", []),
            )
            for item in data
        ]
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
        _LOG.warning("history unreadable (%s); starting fresh", exc)
        return []


def recent(limit: int = 10) -> list[HistoryEntry]:
    return read_all()[-limit:][::-1]


def last_entry(ts: float | None = None) -> HistoryEntry | None:
    entries = read_all()
    return entries[-1] if entries else None

"""Centralised logging / diagnostics for Faceless.

Writes to ``XDG_STATE_HOME/faceless/faceless.log`` and mirrors records to a
bounded in-memory ring buffer so the Settings page can display recent activity
without reading the file.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path

from faceless import paths

_RING: deque[str] = deque(maxlen=200)
_configured = False


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime(record.created))
        _RING.append(f"[{stamp}] {record.levelname[:4]} {record.getMessage()}")


def configure(debug: bool = False) -> Path | None:
    """Install handlers; returns the log file path when writable."""
    global _configured
    if _configured:
        return None
    logger = logging.getLogger("faceless")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    logger.addHandler(_RingHandler())
    path: Path | None = None
    try:
        path = paths.log_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        path = None
    _configured = True
    return path


def logger(name: str = "faceless") -> logging.Logger:
    if not _configured:
        configure()
    return logging.getLogger(name)


def recent_entries() -> list[str]:
    return list(_RING)

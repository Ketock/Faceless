"""Application settings with JSON persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from faceless import paths
from faceless.core.jsonio import atomic_json_write
from faceless.logging import logger

_LOG = logger("faceless.settings")


@dataclass
class Settings:
    library_paths: list[str] = field(default_factory=list)
    backup_dir: str = ""
    show_concept_previews: bool = True
    confirm_before_apply: bool = True
    enable_live_reload: bool = True
    detect_detailed_components: bool = True
    debug_logging: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load() -> Settings:
    path = paths.settings_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("settings root must be an object")
        settings = Settings()
        for key, value in raw.items():
            if hasattr(settings, key) and value is not None:
                setattr(settings, key, value)
        return settings
    except FileNotFoundError:
        return Settings()
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        _LOG.warning("Could not load settings (%s); using defaults", exc)
        return Settings()


def save(settings: Settings) -> bool:
    path = paths.settings_file()
    try:
        atomic_json_write(path, settings.to_dict())
        return True
    except OSError as exc:
        _LOG.error("Could not save settings: %s", exc)
        return False

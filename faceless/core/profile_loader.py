"""Profile discovery: scan library directories for valid profiles.

Invalid profile directories are collected as problems (path → reason) so the UI
can surface actionable errors instead of silently hiding directories.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from faceless import paths
from faceless import settings as settings_mod
from faceless.core import schema
from faceless.logging import logger

_LOG = logger("faceless.library")


@dataclass
class Library:
    profiles: list[schema.Profile] = field(default_factory=list)
    problems: dict[str, str] = field(default_factory=dict)

    def by_id(self, profile_id: str) -> schema.Profile | None:
        return next((p for p in self.profiles if p.id == profile_id), None)

    def valid_ids(self) -> set[str]:
        return {p.id for p in self.profiles}


def scan(library_dirs: list[Path] | None = None) -> Library:
    dirs = library_dirs if library_dirs is not None else _configured_dirs()
    lib = Library()
    seen_ids: set[str] = set()
    for root in dirs:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            try:
                profile = schema.load_profile(entry, source=str(root))
                if profile.id in seen_ids:
                    lib.problems[str(entry)] = f"duplicate profile id {profile.id!r} ignored"
                    continue
                seen_ids.add(profile.id)
                lib.profiles.append(profile)
            except schema.ProfileError as exc:
                lib.problems[str(entry)] = str(exc)
                _LOG.warning("skipping profile %s: %s", entry, exc)
            except OSError as exc:
                lib.problems[str(entry)] = f"unreadable: {exc}"
    return lib


def _configured_dirs() -> list[Path]:
    settings = settings_mod.load()
    dirs: list[Path] = []
    for raw in settings.library_paths:
        try:
            candidate = Path(raw).expanduser()
        except (OSError, RuntimeError):
            continue
        if candidate.is_dir() and candidate not in dirs:
            dirs.append(candidate)
    for d in paths.library_dirs():
        if d.is_dir() and d not in dirs:
            dirs.append(d)
    return dirs

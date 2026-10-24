"""Planned-change calculation and compatibility checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from faceless.adapters import get as get_adapter
from faceless.adapters.base import ComponentAdapter
from faceless.core import detection, schema
from faceless.core.safefs import UnsafePathError, parent_symlink_escape, resolve_dest


class Compat(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    INCOMPATIBLE = "incompatible"


@dataclass
class PlannedFile:
    spec: schema.FileSpec
    dest: str                    # absolute destination
    exists: bool = False         # will be overwritten (⇒ backup)
    problem: str = ""


@dataclass
class PlannedAction:
    kind: str                    # copy-file | set-wallpaper | reload
    summary: str
    detail: str = ""


@dataclass
class ApplyPlan:
    profile: schema.Profile
    session: detection.Session
    compatibility: Compat = Compat.FULL
    compat_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_requires: list[str] = field(default_factory=list)
    files: list[PlannedFile] = field(default_factory=list)
    blocked: bool = False
    blocked_reason: str = ""


def _deps_available(profile: schema.Profile) -> tuple[list[str], list[str]]:
    """Check `requires`: names may be adapter ids or executables."""
    import shutil

    missing: list[str] = []
    found: list[str] = []
    for dep in profile.requires:
        adapter = get_adapter(dep)
        if adapter is not None:
            (found if adapter.is_installed() else missing).append(dep)
        elif shutil.which(dep):
            found.append(dep)
        else:
            missing.append(dep)
    return found, missing


def build_plan(profile: schema.Profile) -> ApplyPlan:
    session = detection.detect_session()
    plan = ApplyPlan(profile=profile, session=session)

    # --- compatibility --------------------------------------------------
    compositor_targets = {t for t in profile.targets if t in ("hyprland", "sway", "plasma", "gnome")}
    if compositor_targets:
        if session.kind in compositor_targets:
            plan.compatibility = Compat.FULL
        elif session.kind in ("wayland-generic", "x11", "unknown", "tty"):
            plan.compatibility = Compat.PARTIAL
            plan.compat_reasons.append(
                f"profile targets {', '.join(sorted(compositor_targets))} but this session is "
                f"{session.human}; non-compositor files still apply."
            )
        else:
            plan.compatibility = Compat.PARTIAL
            plan.compat_reasons.append(
                f"profile targets {', '.join(sorted(compositor_targets))}; this session is "
                f"{session.human}. Configs are written but the compositor itself is not driven."
            )
    else:
        plan.compatibility = Compat.FULL

    # --- dependencies ----------------------------------------------------
    found, missing = _deps_available(profile)
    plan.missing_requires = missing
    if missing:
        plan.warnings.append(
            "missing optional/required dependency(s): " + ", ".join(missing)
        )

    # --- file plan ---------------------------------------------------------
    for spec in profile.files:
        try:
            dest = resolve_dest(spec.dest_root, spec.dest_rel)
            if parent_symlink_escape(dest):
                plan.files.append(
                    PlannedFile(spec, str(dest), problem="ancestor symlink escapes $HOME")
                )
                continue
            exists = dest.is_file() or dest.is_symlink()
            plan.files.append(PlannedFile(spec, str(dest), exists=exists))
        except UnsafePathError as exc:
            plan.files.append(PlannedFile(spec, "", problem=str(exc)))
            plan.blocked = True
            plan.blocked_reason = f"unsafe destination declared by profile: {exc}"

    overwrites = [f for f in plan.files if f.exists]
    if overwrites:
        plan.warnings.append(
            f"{len(overwrites)} existing file(s) will be backed up and replaced."
        )
    return plan


def reload_targets(profile: schema.Profile) -> list[ComponentAdapter]:
    adapters = []
    for target in profile.targets:
        adapter = get_adapter(target)
        if adapter is not None and adapter.id != "wallpaper":
            adapters.append(adapter)
    return adapters

"""Safe filesystem primitives used by the apply engine.

Every destination path is rooted, relative, and validated against traversal
and symlink escapes. Writes are atomic (temp file + os.replace).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath

from faceless import paths
from faceless.logging import logger

_LOG = logger("faceless.safefs")

ROOT_NAMES = ("config", "home", "share", "state")
ALLOWED_MODE_MASK = 0o777


class UnsafePathError(Exception):
    """A destination path failed validation."""


def resolve_dest(root: str, rel: str) -> Path:
    """Map a rooted, relative destination to an absolute path under $HOME.

    Raises UnsafePathError for absolute paths, traversal, empty components or
    reserved names.
    """
    if root not in ROOT_NAMES:
        raise UnsafePathError(f"unknown destination root {root!r}")
    if not isinstance(rel, str) or not rel.strip():
        raise UnsafePathError("empty destination path")
    if rel.startswith("/") or "\\" in rel or rel.endswith("/"):
        raise UnsafePathError(f"destination must be a relative file path: {rel!r}")
    parts = PurePosixPath(rel).parts
    if not parts:
        raise UnsafePathError(f"empty destination path: {rel!r}")
    if any(part in ("..", ".") for part in parts):
        raise UnsafePathError(f"path traversal in destination: {rel!r}")
    if any(part == "" for part in parts):
        raise UnsafePathError(f"empty path component in destination: {rel!r}")

    base = {
        "config": paths.config_home(),
        "home": paths.home(),
        "share": paths.data_home(),
        "state": paths.state_home(),
    }[root]
    dest = base.joinpath(*parts)
    return dest


def ensure_within(dest: Path, root: str) -> Path:
    """Verify dest resolves inside its root; refuse symlink escapes."""
    base = {
        "config": paths.config_home(),
        "home": paths.home(),
        "share": paths.data_home(),
        "state": paths.state_home(),
    }[root]
    resolved = dest.resolve(strict=False)
    base_resolved = base.resolve(strict=False)
    if not str(resolved).startswith(str(base_resolved) + os.sep):
        raise UnsafePathError(
            f"destination escapes its root ({dest} not under {base})"
        )
    return resolved


def parent_symlink_escape(dest: Path) -> bool:
    """True if any existing ancestor of dest is a symlink pointing outside $HOME."""
    home = paths.home().resolve()
    current = dest.parent
    while True:
        if current.is_symlink():
            target = current.resolve(strict=False)
            try:
                target.relative_to(home)
            except ValueError:
                return True
        if current == current.parent:
            return False
        current = current.parent


def _sane_file_mode(mode: int) -> int:
    """Clamp a payload mode to a sane owner-read/writable file mode.

    Rejects setuid/setgid/sticky bits and any group/other write bits;
    keeps otherwise-valid modes as authored, else falls back to 0o644.
    """
    if mode & 0o7000:  # setuid/setgid/sticky — never propagate
        return 0o644
    if mode & 0o022:   # group/other must never gain write access
        return 0o644
    if not (mode & 0o400):  # owner must be able to read its own config
        return 0o644
    return mode


def atomic_replace(source: Path, dest: Path) -> None:
    """Move a staged file onto dest atomically, preserving sane permissions."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    mode = _sane_file_mode(source.stat().st_mode & 0o777)
    os.chmod(source, mode)
    os.replace(source, dest)


def snapshot_metadata(path: Path) -> dict:
    st = path.stat()
    return {"mode": st.st_mode & 0o777, "size": st.st_size, "mtime": st.st_mtime}


def copy_tree_into(source_dir: Path, dest_dir: Path) -> None:
    """Copy a directory tree without following symlinks into the destination."""
    shutil.copytree(source_dir, dest_dir, symlinks=True, dirs_exist_ok=True)

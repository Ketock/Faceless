"""Rice profile schema — manifest model, parsing, and validation.

A profile directory looks like::

    my-rice/
      manifest.toml
      files/…        → payloads copied to destinations during apply
      assets/…       → previews and wallpapers (never applied as configs)

The manifest (TOML) is the single source of truth:

    id          = "my-rice"             # unique, [a-z0-9-]{2,40}
    name        = "My Rice"
    version     = "1.0.0"
    description = "…"
    author      = "someone"             # optional
    tags        = ["dark", "minimal"]   # optional
    previews    = ["assets/preview.png"]# optional, relative
    targets     = ["hyprland", "waybar", "kitty"]
    requires    = ["waybar"]            # optional dependency names
    wallpaper   = "assets/wall.png"     # optional

    [files.config]                      # destination root → mapping
    "hypr/hyprland.conf" = "files/hyprland.conf"
    …other roots: config, home, share, state

Profiles are pure *data*. Faceless never executes scripts bundled in a profile;
component behaviour (reload, wallpaper) is provided by adapters.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 1
MANIFEST_NAME = "manifest.toml"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[a-z0-9.]+)?$")
# Destination roots: where a managed file may land on disk.
ROOTS = ("config", "home", "share", "state")
KNOWN_TARGETS = frozenset(
    {
        "hyprland", "sway", "waybar", "wofi", "rofi", "kitty", "alacritty",
        "mako", "swaync", "gtk", "wallpaper", "shell", "fonts", "plasma",
        "gnome", "dunst", "foot", "zsh", "bash",
    }
)


class ProfileError(Exception):
    """Raised for invalid or untrustworthy profile manifests."""


@dataclass(frozen=True)
class FileSpec:
    """One managed file: destination (rooted) → payload relative to profile."""

    dest_root: str
    dest_rel: str
    payload: str

    def display_dest(self) -> str:
        return f"{self.dest_root}:{self.dest_rel}"


@dataclass(frozen=True)
class Profile:
    directory: Path
    id: str
    name: str
    version: str
    description: str
    author: str
    tags: tuple[str, ...]
    targets: tuple[str, ...]
    requires: tuple[str, ...]
    files: tuple[FileSpec, ...]
    previews: tuple[str, ...]
    wallpaper: str | None
    source: str  # "bundled" | "user" | library dir name

    def preview_paths(self) -> list[Path]:
        return [self.directory / p for p in self.previews]

    def payload_path(self, spec: FileSpec) -> Path:
        return self.directory / spec.payload


def _clean_rel_path(raw: str, what: str) -> str:
    """Validate a manifest-declared relative path; returns a posix-style path."""
    if not isinstance(raw, str) or not raw.strip():
        raise ProfileError(f"{what} must be a non-empty string, got {raw!r}")
    if raw.startswith("/") or "\\" in raw:
        raise ProfileError(f"{what} must be a relative posix path, got {raw!r}")
    p = PurePosixPath(raw)
    if p.is_absolute() or any(part in ("..", ".") for part in p.parts):
        raise ProfileError(f"{what} must not contain '.' or '..' components: {raw!r}")
    if len(p.parts) == 0 or p.parts[0] in ("", "/"):
        raise ProfileError(f"invalid {what}: {raw!r}")
    return str(p)


def _validate_string_list(raw: object, what: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(x, str) and x.strip() for x in raw):
        raise ProfileError(f"{what} must be a list of non-empty strings")
    if not raw and not allow_empty:
        raise ProfileError(f"{what} must not be empty")
    if len(raw) != len(set(raw)):
        raise ProfileError(f"{what} contains duplicates")
    return tuple(raw)


def parse_manifest(data: bytes | dict, directory: Path, source: str = "user") -> Profile:
    """Parse + validate manifest content into a Profile."""
    try:
        doc = data if isinstance(data, dict) else tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ProfileError(f"manifest is not valid TOML: {exc}") from exc
    if not isinstance(doc, dict):
        raise ProfileError("manifest root must be a table")

    for key in ("id", "name", "version", "description"):
        value = doc.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ProfileError(f"missing or empty required field: {key}")

    pid = doc["id"].strip()
    if not ID_RE.match(pid):
        raise ProfileError(
            f"id {pid!r} invalid: expected lowercase [a-z0-9-], 2–40 chars"
        )
    version = doc["version"].strip()
    if not SEMVER_RE.match(version):
        raise ProfileError(f"version {version!r} is not semantic (x.y.z)")

    if directory.name != pid:
        raise ProfileError(
            f"profile directory name {directory.name!r} does not match id {pid!r}"
        )

    targets = _validate_string_list(doc.get("targets"), "targets", allow_empty=False)
    unknown = [t for t in targets if t not in KNOWN_TARGETS]
    if unknown:
        raise ProfileError(
            "unknown target(s) " + ", ".join(sorted(unknown))
            + f"; known targets: {', '.join(sorted(KNOWN_TARGETS))}"
        )

    requires = _validate_string_list(doc.get("requires"), "requires")
    tags = _validate_string_list(doc.get("tags"), "tags")
    previews = tuple(
        _clean_rel_path(p, "previews entry") for p in _validate_string_list(doc.get("previews"), "previews")
    )
    for p in previews:
        if not p.startswith("assets/"):
            raise ProfileError(f"previews must live under assets/: {p!r}")

    wallpaper_raw = doc.get("wallpaper")
    wallpaper = None
    if wallpaper_raw is not None:
        wallpaper = _clean_rel_path(wallpaper_raw, "wallpaper")
        if not wallpaper.startswith("assets/"):
            raise ProfileError(f"wallpaper must live under assets/: {wallpaper!r}")

    files_doc = doc.get("files")
    if not isinstance(files_doc, dict) or not files_doc:
        raise ProfileError("manifest must declare a non-empty [files] table")

    specs: list[FileSpec] = []
    for root, mapping in files_doc.items():
        if root not in ROOTS:
            raise ProfileError(
                f"files table {root!r} is not a known destination root "
                f"({', '.join(ROOTS)})"
            )
        if not isinstance(mapping, dict):
            raise ProfileError(f"[files.{root}] must be a table of dest = payload")
        for dest, payload in mapping.items():
            dest_rel = _clean_rel_path(dest, f"files.{root} destination")
            payload_rel = _clean_rel_path(payload, f"files.{root} payload")
            specs.append(FileSpec(root, dest_rel, payload_rel))

    if len(specs) != len({s.display_dest() for s in specs}):
        raise ProfileError("duplicate destinations in [files] table")

    for spec in specs:
        if not (directory / spec.payload).is_file():
            raise ProfileError(f"declared payload missing on disk: {spec.payload!r}")

    return Profile(
        directory=directory,
        id=pid,
        name=doc["name"].strip(),
        version=version,
        description=doc["description"].strip(),
        author=str(doc.get("author", "")).strip(),
        tags=tags,
        targets=targets,
        requires=requires,
        files=tuple(specs),
        previews=previews,
        wallpaper=wallpaper,
        source=source,
    )


def load_profile(directory: Path, source: str = "user") -> Profile:
    manifest = directory / MANIFEST_NAME
    if not manifest.is_file():
        raise ProfileError(f"{directory}: missing {MANIFEST_NAME}")
    try:
        return parse_manifest(manifest.read_bytes(), directory, source)
    except ProfileError:
        raise
    except OSError as exc:
        raise ProfileError(f"{directory}: could not read manifest: {exc}") from exc

# Development Guide

## Requirements

- Linux (Arch Linux / Arch-based is the primary target; anything with GTK4 works)
- `python >= 3.11`, `gtk4`, `libadwaita`, `python-gobject`
  (on Arch: `sudo pacman -S gtk4 libadwaita python-gobject python-pip`)
- A display server for running the GUI (Wayland/X11). Tests do **not** need one.

## Setup

```sh
git clone https://github.com/Ketock/Faceless.git
cd Faceless
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
# On Arch the system PyGObject is usually used instead:
#   python3 -m venv .venv --system-site-packages
```

> On Arch, `PyGObject` is provided by the system package `python-gobject`.
> Either create the venv with `--system-site-packages` (as above) or install
> `python-gobject` into the venv. GTK libs themselves are always system-level.

## Run

```sh
.venv/bin/python -m faceless          # GUI
.venv/bin/faceless                    # if installed via pip entry point
.venv/bin/python -m faceless --debug  # verbose logging
```

## Test & lint

```sh
.venv/bin/python -m pytest            # 128+ tests, all sandboxed
.venv/bin/ruff check faceless tests
.venv/bin/python -m pytest --cov=faceless
```

Tests never touch your real desktop configuration: every test pins
`FACELESS_HOME` (see `faceless/paths.py`) to a temp directory. **Do not disable
that fixture.**

## Regenerate sample-profile artwork

```sh
.venv/bin/python scripts/generate_previews.py
```

## Architecture rules

- `faceless/core/**` and `faceless/adapters/**` must never import `gi`.
  They must stay testable headless.
- The UI layer (`faceless/ui/**`) talks only to `faceless/controller.py`.
- See `docs/architecture.md`, `docs/profile-schema.md`, `docs/design-system.md`,
  `docs/adapters.md`.

## Packaging (Arch)

```sh
cd packaging
makepkg -sf
sudo pacman -U faceless-0.1.0-1-any.pkg.tar.zst
```

The PKGBUILD installs the Python package, bundled profiles to
`/usr/share/faceless/profiles`, the desktop entry, and the icon.

## Skills / tooling notes for contributors using OpenCode

No OpenCode skill is required to build or run Faceless — runtime use never
depends on OpenCode. During development we checked the skill ecosystem for
GTK/desktop-application skills; the only candidates were low-install-count
community skills, which we declined for security reasons. The GNOME/GTK4
official documentation is the reference used instead.

## Release checklist

1. `pytest` green, `ruff` clean
2. Bump version in `pyproject.toml` + `packaging/PKGBUILD`
3. Review `git diff`, commit with Conventional Commits
4. `makepkg -sf` from `packaging/` builds cleanly

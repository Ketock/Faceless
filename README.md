# Faceless — The Jester-Masked Rice Manager

<p align="center">
  <img src="faceless/ui/assets/faceless-logo.svg" width="96" alt="Faceless logo" />
</p>

**Faceless** is a Linux desktop *rice manager* for **Arch Linux and Arch-based
distributions**: change the look and feel of your desktop in a few clicks — no
manual dotfile surgery, no memorised terminal commands.

It wears a jester's mask. Your desktop does not have to.

| | |
|---|---|
| **The application** | A dark, theatrical, jester-mask identity — split crimson/violet mask, gold eyes, harlequin diamonds |
| **Your desktop** | Whatever the rice you choose looks like. Obsidian, Aurora, Monochrome, or your own profiles |

> The bundled previews are honest **generated concept images** (labelled as
> such), not screenshots of third-party themes.

## Features

- **Rice profiles** — versioned TOML manifests bundling configs for your
  compositor, bar, launcher, terminal, notification daemon, shell, GTK and
  wallpapers. See [`docs/profile-schema.md`](docs/profile-schema.md).
- **Safe apply engine** — plan → backup → stage → apply → reload → record,
  with automatic rollback on failure. Never silently overwrites; every
  replaced file is backed up first. See [`docs/architecture.md`](docs/architecture.md).
- **Backups & one-click restore** — every apply produces a restorable
  snapshot; restores are themselves preceded by an automatic safety snapshot.
- **Desktop & component detection** — session type (Hyprland, Sway, Plasma,
  GNOME, generic Wayland/X11), installed vs. *active* components, config
  locations, compatibility reports.
- **Rice library** — bundled sample profiles + your own local library paths,
  with search, sorting, compatibility chips and problem reporting.
- **Live reload where supported** — `hyprctl reload`, `swaymsg reload`,
  `makoctl reload`, `swaync-client -rs`, … declared per-adapter, never
  profile-supplied.
- **Wallpaper management** — hyprpaper / swaymsg / Plasma / GNOME backends,
  selected by detected session.
- **No root. No scripts from profiles. No session restarts.**

## Screens

Home (session + active rice + recent activity) · Rice Library (search/sort/
preview cards) · Profile Details (gallery, compatibility, planned changes,
apply) · Components (detected integrations) · Backups (inspect/restore/
delete) · Settings (library paths, backup dir, behavior, diagnostics).

## Supported integrations

Hyprland and Sway are first-class. Plasma and GNOME are supported at the
detection/settings level, with wallpapers; GTK settings apply to all sessions.
Also integrated: Waybar, Wofi, Rofi, Kitty, Alacritty, Foot, Mako, SwayNC,
Dunst, GTK themes, shell, fonts. Missing components are explained, never
guessed at. Extending an adapter is a ~40-line subclass — see
[`docs/adapters.md`](docs/adapters.md).

## Installation (Arch Linux)

```sh
git clone https://github.com/Ketock/Faceless.git
cd Faceless/packaging
makepkg -sf
sudo pacman -U faceless-0.1.0-1-any.pkg.tar.zst
```

Dependencies: `gtk4 libadwaita python python-gobject` (pulled in
automatically). Optional integrations (hyprland, waybar, kitty, …) are
`optdepends`.

Or run straight from a checkout:

```sh
cd Faceless
python -m venv .venv --system-site-packages
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m faceless
```

## Usage

1. Launch **Faceless** (app menu, or `faceless`).
2. Home shows your session, detected components and the active rice.
3. Open **Rice Library**, browse previews, pick a profile.
4. Review the **planned changes** — every file that will be written or backed
   up, compatibility notes, missing dependencies.
5. Press **Apply rice**. Faceless backs up conflicting files, applies
   atomically, reloads supported components and records the operation.
6. Something went wrong? **Backups** restores the exact previous state.

## Rice library & own profiles

Place profile directories under `~/.config/faceless/library/` or add any
folder in **Settings → Rice library paths**. Copy `data/profiles/obsidian`
as a starting template and edit. Profiles are validated on load; broken ones
are listed with reasons instead of crashing. See
[`docs/profile-schema.md`](docs/profile-schema.md).

## Safety model

- Every destination is rooted and relative; traversal and symlink escapes
  are rejected (in schema **and** in the engine, defence in depth).
- Existing files are archived with permissions before replacement.
- Replacement is atomic (`os.replace`); payloads are staged and verified.
- Failure after staging → automatic rollback from the just-created backup.
- Profiles are data: bundled scripts are never executed, commands are never
  interpolated.
- Nothing requires root; Faceless only writes inside your `$HOME`/XDG dirs.
- Destructive operations (restore, delete backup) always ask for explicit
  confirmation.

## Testing

```sh
.venv/bin/python -m pytest    # 128 tests — schema, plan, engine, rollback,
                              # backups, adapters, detection, settings, history
.venv/bin/ruff check faceless tests scripts
```

Every test runs in a sandboxed `FACELESS_HOME`; tests never touch your real
desktop configuration.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — layers + apply pipeline
- [`docs/profile-schema.md`](docs/profile-schema.md) — manifest reference
- [`docs/adapters.md`](docs/adapters.md) — integration adapters + extension
- [`docs/design-system.md`](docs/design-system.md) — jester-mask design tokens
- [`docs/development.md`](docs/development.md) — dev setup + release checklist

## Contributing

PRs welcome. Please keep `faceless/core` and `faceless/adapters` GUI-free and
test-covered; add adapters via the documented extension procedure; run
`pytest` and `ruff` before submitting.

## License

MIT — see [`LICENSE`](LICENSE).

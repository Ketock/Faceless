# Faceless Rice Profile Schema

Version **1** of the schema. Manifests are TOML files named `manifest.toml`
at the root of a profile directory.

## Directory layout

```
my-rice/
  manifest.toml        # required, the only interpreted file
  files/               # payloads copied to destinations during apply
  assets/              # previews + wallpaper (never applied as config)
```

## Fields

| Field         | Type            | Required | Validation                                        |
|---------------|-----------------|----------|---------------------------------------------------|
| `id`          | string          | yes      | `^[a-z0-9][a-z0-9-]{1,39}$`, must equal directory name |
| `name`        | string          | yes      | non-empty                                         |
| `version`     | string          | yes      | semantic `x.y.z[-suffix]`                          |
| `description` | string          | yes      | non-empty                                         |
| `author`      | string          | no       | —                                                 |
| `tags`        | list of strings | no       | unique, non-empty                                 |
| `targets`     | list of strings | yes      | each must be a known adapter id (see below)       |
| `requires`    | list of strings | no       | adapter ids or executable names                   |
| `previews`    | list of strings | no       | relative paths under `assets/`                    |
| `wallpaper`   | string          | no       | relative path under `assets/`                     |
| `files`       | table           | yes      | `[files.<root>]` tables of `"dest" = "payload"`    |

### Destination roots

Destination keys are one of:

| Root    | Resolves to                        |
|---------|------------------------------------|
| `config`| `XDG_CONFIG_HOME` (usually `~/.config`) |
| `home`  | `$HOME`                            |
| `share` | `XDG_DATA_HOME` (usually `~/.local/share`) |
| `state` | `XDG_STATE_HOME` (usually `~/.local/state`) |

Destination and payload paths must be **relative**, POSIX-style, and contain no
`.`/`..` components. Payloads must exist inside the profile directory at scan
time.

### Known targets (adapter ids)

`hyprland, sway, plasma, gnome, waybar, wofi, rofi, kitty, alacritty, foot,
mako, swaync, dunst, gtk, shell, fonts, wallpaper, zsh, bash`

Unknown targets are rejected — adding a target requires implementing an
adapter first.

## Semantics

- Profiles are **pure data**. Faceless never executes scripts bundled in a
  profile; there is no way to declare arbitrary shell hooks.
- `targets` declares which components the profile manages. Those components
  are what Faceless attempts to reload after applying (if running and a
  supported mechanism exists).
- `requires` declares soft dependencies. Missing ones are surfaced as
  warnings in the plan; they do not block application of file payloads.
- `wallpaper` is copied into `XDG_DATA_HOME/faceless/wallpapers/<id>/` and set
  through the session's supported backend (hyprpaper/swaymsg/plasma/gsettings).

## Example

```toml
id = "obsidian"
name = "Obsidian"
version = "1.0.0"
description = "A restrained dark developer desktop."
author = "Faceless maintainers"
tags = ["dark", "developer"]
targets = ["hyprland", "waybar", "kitty", "wallpaper"]
previews = ["assets/preview.png"]
wallpaper = "assets/wallpaper.png"

[files.config]
"hypr/hyprland.conf" = "files/hyprland.conf"
"kitty/kitty.conf" = "files/kitty.conf"
```

Three complete examples ship with Faceless: `data/profiles/obsidian`,
`aurora`, and `monochrome`.

## Honest previews

Previews bundled with the sample profiles are **generated concept images**
(see `scripts/generate_previews.py`), clearly derived from each profile's
palette. They are not screenshots of any third-party theme. When you import
third-party profiles, Faceless displays previews only if the profile ships
real ones.

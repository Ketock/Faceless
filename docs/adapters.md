# Component Adapters

Adapters translate Faceless' core engine into per-component behaviour:
detection, configuration locations, and reload mechanisms.

## Base protocol (`faceless/adapters/base.py`)

Every adapter is a `ComponentAdapter` subclass declaring:

| Member            | Meaning                                                        |
|-------------------|----------------------------------------------------------------|
| `id`              | Profile-manifest target id (`hyprland`, `waybar`, …)           |
| `name`            | Human name shown in the UI                                     |
| `category`        | compositor / bar / launcher / terminal / notifications / theme / wallpaper / shell |
| `binaries`        | executables used for *installed* detection (`shutil.which`)     |
| `config_dirs`     | config-relative directories for *location* display             |
| `reload_actions`  | whitelisted argv tuples the engine may execute to reload        |
| `is_installed()`  | binaries present?                                              |
| `is_active()`     | running in the *current* session (env/process based)           |
| `reload()`        | perform declared reload; never fabricates success              |

Reload commands are declared **only by the adapter itself** as fixed argv
tuples — the engine never interpolates profile data into commands, and
profiles cannot declare commands.

## Implemented adapters

| Adapter     | Detection                          | Reload                       |
|-------------|------------------------------------|------------------------------|
| `hyprland`  | `HYPRLAND_INSTANCE_SIGNATURE` / binary | `hyprctl reload`          |
| `sway`      | `SWAYSOCK` / binary                | `swaymsg reload`             |
| `waybar`    | binary                             | none (auto-observes config)  |
| `wofi`      | binary                             | none (relaunch to apply)     |
| `rofi`      | binary                             | none (relaunch to apply)     |
| `kitty`     | binary                             | none (auto-reloads via kitty.conf) |
| `alacritty` | binary                             | none (relaunch to apply)     |
| `foot`      | binary                             | none (relaunch to apply)     |
| `mako`      | binary                             | `makoctl reload`             |
| `swaync`    | binary                             | `swaync-client -rs`          |
| `dunst`     | binary                             | `killall -SIGUSR2 dunst`     |
| `gtk`       | `gsettings` binary                 | n/a (settings apply live)    |
| `shell`     | `zsh`/`bash`                       | n/a                          |
| `fonts`     | font directories                   | n/a                          |
| `wallpaper` | always available                   | session backend (see below)  |

## Wallpaper backends

The `wallpaper` adapter sets a wallpaper through the **first backend matching
the detected session**:

- Hyprland → `hyprctl hyprpaper` (unload all, preload, wallpaper)
- Sway → `swaymsg output * bg <path> fill`
- Plasma → plasmashell script via qdbus
- GNOME → `gsettings set org.gnome.desktop.background`

The image file is first copied into
`XDG_DATA_HOME/faceless/wallpapers/<profile>/` so the profile directory can
change without breaking the active wallpaper.

## Extending

1. Create a module under `faceless/adapters/`.
2. Subclass `ComponentAdapter`, set `id`/`name`/`category`/`binaries`, and
   (optionally) `reload_actions` — fixed argv only.
3. Register it in the `ALL` tuple in `faceless/adapters/__init__.py`.
4. Add the id to `KNOWN_TARGETS` in `faceless/core/schema.py`.
5. Add tests under `tests/test_adapters.py`.

Adapters must never mutate configuration themselves and must never require
root. Live-reload failures are surfaced as warnings, never silently ignored.

# Faceless Architecture

Faceless is a native Linux desktop application (GTK4 + libadwaita via PyGObject)
that manages *rices* — curated desktop configuration profiles.

## Layers

```
┌─────────────────────────────────────────────┐
│ UI (faceless.ui)        GTK4 / libadwaita   │  ← knows nothing about file ops
├─────────────────────────────────────────────┤
│ Controller (faceless.controller)            │  ← orchestrates core calls, caches state
├─────────────────────────────────────────────┤
│ Core (faceless.core)    pure Python, no GTK │
│   schema      profile manifest dataclasses  │
│   profile_loader  discovery + validation    │
│   detection   session / component discovery │
│   plan        planned-change calculation    │
│   engine      apply pipeline w/ rollback    │
│   backups     backup store                  │
│   history     operation log                 │
├─────────────────────────────────────────────┤
│ Adapters (faceless.adapters)                │  ← one module per desktop component
├─────────────────────────────────────────────┤
│ Runtime paths (faceless.paths, safefs)      │  ← XDG handling, safe fs primitives
└─────────────────────────────────────────────┘
```

**Rule:** everything under `faceless/core` and `faceless/adapters` must be
importable and testable without a display server. The UI layer is the only
module that imports `gi`.

## Apply pipeline (transactional)

```
plan(profile) -> ApplyPlan
   validate manifest, check session/compat/dependencies,
   enumerate every destination file, detect conflicts

apply(profile, plan)
   1. backup   – copy every existing conflicting destination into the
                 backup store, preserving structure + permissions
   2. stage    – copy profile payload into a temp staging dir, verify
   3. apply    – atomic os.replace() into destinations
   4. reload   – notify affected, running components (adapters decide how)
   5. record   – append outcome to the operation history
   on any failure after step 2 → automatic rollback from the backup,
   then the failure is recorded and re-raised.
```

## Safety invariants (enforced in code + tests)

- Destinations must be relative (`config:kitty/kitty.conf` style roots); absolute
  paths, `..`, empty segments, and symlink escapes are rejected.
- Existing files are never silently overwritten — they are always backed up first.
- No profile-bundled scripts are ever executed. Profiles are data.
- No root required; everything runs under the invoking user's HOME/XDG dirs.
- Atomic replacement via `os.replace` (same-filesystem), never in-place truncation.
- Full session restarts are never triggered automatically; components are
  reloaded through their supported mechanisms only (documented per adapter).
- Unbounded recursive deletion on config dirs is forbidden; restore only
  removes files that this backup actually owns.

## Known limitations

- A destination that is itself a symlink is archived by *content* and
  restored as a regular file — the link itself is not preserved. Symlinks
  pointing outside `$HOME` are never archived at all (and their content is
  never copied into the backup vault).

## Data locations (XDG)

| Purpose        | Path (default)                          |
|----------------|-----------------------------------------|
| Profile libs   | `~/.config/faceless/library`, bundled `data/profiles` |
| Backups        | `~/.local/share/faceless/backups`       |
| History log    | `~/.local/state/faceless/history.json`  |
| Diagnostics    | `~/.local/state/faceless/faceless.log`  |
| Settings       | `~/.config/faceless/settings.json`      |

## Profile manifest

TOML — see `docs/profile-schema.md`. Example location: `data/profiles/<id>/`.

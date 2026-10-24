# Faceless Design System — "The Jester's Mask"

The application identity is a stylized jester's mask: theatrical, dark,
geometric, with controlled duality. It defines **only the Faceless app UI** —
never the user's desktop.

## Palette tokens (CSS variables in `faceless/ui/assets/faceless.css`)

| Token            | Value     | Use                                   |
|------------------|-----------|---------------------------------------|
| `--fl-ink`       | `#0d0a0f` | App background (deep ink/plum-black)  |
| `--fl-charcoal`  | `#17131b` | Raised surfaces, cards                |
| `--fl-charcoal-2`| `#221c28` | Hover / secondary surfaces            |
| `--fl-bone`      | `#efe8dc` | Primary text (warm bone white)        |
| `--fl-bone-dim`  | `#a89fae` | Secondary text, muted labels          |
| `--fl-crimson`   | `#c22f4a` | Primary actions (Apply), danger accent|
| `--fl-crimson-deep`| `#8c1f36` | Hover state for primary actions     |
| `--fl-violet`    | `#7d4bd6` | Secondary accents, selection          |
| `--fl-gold`      | `#d9a441` | Highlights, active-rice marks, focus  |
| `--fl-success`   | `#4fae7a` | Success semantics                     |
| `--fl-warning`   | `#d9a441` | Warning semantics (shared w/ gold)    |
| `--fl-danger`    | `#e05662` | Error semantics (distinct from crimson brand) |

Accessibility: body text `--fl-bone` on `--fl-ink` ≥ 12:1 contrast; dim text ≥ 5:1.
Accents are used sparingly — one accent per element, never all five.

## Shape & motif

- Cards: 12px radius; buttons 10px; the "apply" button is `pill` shaped.
- Harlequin diamond: a 45°-rotated square, used as list bullet, divider
  ornament, and empty-state art (always tiny, never dominant).
- Duality: split accents (left crimson / right violet) reserved for the logo,
  splash mark, and the active-rice indicator — nowhere else.
- Sharp corner "mask cut": headers get a small notch clip on one side
  (`clip-path` via CSS in header widgets) to echo a mask edge.

## Typography

- Display/headers: "Jester Display" concept — use **Noto Serif Display** or
  fallback `serif` with letter-spacing 0.06em, weight 700, small caps feel
  via `text-transform: uppercase` on section titles only.
- Body/UI: system default (Adwaita Sans / Cantarell fallback), 15px base.
- Never use decorative fonts for controls or body text.

## Components

- `fl-card` — charcoal surface card, 1px border `#2a2330`.
- `fl-titlebar` — custom header with mask notch + inline logo.
- `fl-profile-card` — preview image top (or diamond placeholder), name,
  tags row, compatibility chip.
- `fl-chip` — small rounded label; `fl-chip-good/full/partial/bad` variants.
- `fl-apply-button` — crimson pill, bone text, crimson-deep hover;
  disabled = charcoal with dim text.
- `fl-diamond-divider` — ornament: line ◆ line, centered.
- Empty states: large diamond outline + bone-dim caption + recovery action.
- Motion: 160ms ease-out on hover/press, 220ms page transitions; all motion
  suppressed under `gtk-enable-animations = false`.

## Branding assets

- `faceless/ui/assets/faceless-logo.svg` — split jester mask (crimson/violet
  halves, gold eyes), works at 16px.
- `data/icons/hicolor/scalable/apps/faceless.svg` — full app icon with ink
  rounded-square plate.
- One mask silhouette; abstract; no copyrighted imagery.

"""Theme loading for the Faceless UI.

Resolves the design-system assets relative to this file, registers the
"Jester's Mask" stylesheet application-wide, and exposes logo helpers.
"""

from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gdk, Gio, Gtk

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
CSS_PATH = ASSETS_DIR / "faceless.css"
LOGO_PATH = ASSETS_DIR / "faceless-logo.svg"
SYMBOLIC_PATH = ASSETS_DIR / "faceless-symbolic.svg"

_provider: Gtk.CssProvider | None = None


def css_provider() -> Gtk.CssProvider:
    """Parse (once) and return the design-system stylesheet."""
    global _provider
    if _provider is None:
        if not CSS_PATH.is_file():
            raise FileNotFoundError(f"missing stylesheet: {CSS_PATH}")
        provider = Gtk.CssProvider()
        provider.load_from_path(str(CSS_PATH))
        _provider = provider
    return _provider


def apply_theme(display: Gdk.Display | None = None) -> None:
    """Register the stylesheet for the whole display (application priority)."""
    display = display or Gdk.Display.get_default()
    if display is None:
        return
    # The app owns a fixed dark jester theme; FORCE_DARK applies to this
    # application only (Adw.StyleManager is per-app, never the desktop).
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    Gtk.StyleContext.add_provider_for_display(
        display, css_provider(), Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def load_logo() -> Gio.File:
    """The application logo as a Gio.File."""
    return Gio.File.new_for_path(str(LOGO_PATH))


def load_symbolic() -> Gio.File:
    """The monochrome mask symbol as a Gio.File."""
    return Gio.File.new_for_path(str(SYMBOLIC_PATH))


def logo_paintable() -> Gdk.Paintable | None:
    """Load the mask logo as a Gdk.Texture (None on failure)."""
    return _texture(LOGO_PATH)


def symbolic_paintable() -> Gdk.Paintable | None:
    """Load the monochrome mask symbol as a Gdk.Texture (None on failure)."""
    return _texture(SYMBOLIC_PATH)


def _texture(path: Path) -> Gdk.Texture | None:
    if not path.is_file():
        return None
    try:
        texture = Gdk.Texture.new_from_file(
            Gio.File.new_for_path(str(path))
        )
    except Exception:  # noqa: BLE001 — corrupt/missing assets must not crash
        return None
    return texture

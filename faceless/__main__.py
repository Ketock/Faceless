"""Faceless entry point: ``python -m faceless`` or the ``faceless`` script."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="faceless", description="Faceless — the jester-masked Linux rice manager."
    )
    parser.add_argument("--version", action="version", version=f"faceless {__import__('faceless').__version__}")
    parser.add_argument(
        "--debug", action="store_true", help="verbose diagnostics logging"
    )
    args = parser.parse_args(argv)

    from faceless.logging import configure

    configure(debug=args.debug)

    try:
        from faceless.ui.app import main as ui_main

        ui_main()
    except ImportError as exc:  # missing GTK runtime on minimal systems
        print(
            "Faceless requires GTK4 + libadwaita (PyGObject).\n"
            f"Import failed: {exc}\n"
            "On Arch: sudo pacman -S gtk4 libadwaita python-gobject",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

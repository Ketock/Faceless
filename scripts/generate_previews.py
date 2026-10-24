#!/usr/bin/env python3
"""Generate honest concept-preview PNGs and gradient wallpapers for the
bundled sample profiles.

Previews are clearly *generated concept images* of the profile's palette and
layout (bar on top, terminal window, desktop) — never screenshots of real
third-party themes. Usage: .venv/bin/python scripts/generate_previews.py
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

W, H = 960, 540
REPO = Path(__file__).resolve().parent.parent


def chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(
        ">I", zlib.crc32(tag + data) & 0xFFFFFFFF
    )


def png(width: int, height: int, pixel_fn) -> bytes:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel_fn(x, y))
    idat = zlib.compress(bytes(raw), 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(max(0, min(255, int(a[i] + (b[i] - a[i]) * t))) for i in range(3))


def vertical_gradient(top, bottom, pixel_fn=None):
    return lambda x, y: pixel_fn(x, y) if pixel_fn else lerp(top, bottom, y / H)


PROFILE_ART = {
    # (bg_top, bg_bottom, bar, terminal_bg, text, accent)
    "obsidian": ((24, 26, 33), (13, 14, 18), (18, 20, 26), (22, 24, 31), (188, 197, 214), (110, 172, 218)),
    "aurora": ((38, 16, 64), (10, 8, 24), (28, 12, 50), (20, 10, 38), (238, 226, 255), (128, 94, 247)),
    "monochrome": ((30, 30, 30), (16, 16, 16), (22, 22, 22), (24, 24, 24), (200, 200, 200), (160, 160, 160)),
}


def preview(profile_id: str) -> bytes:
    bg_top, bg_bottom, bar, term, text, accent = PROFILE_ART[profile_id]
    bg = vertical_gradient(bg_top, bg_bottom)

    def label_text(x, y, color):
        # fake caption strip, 3px tall blocks
        return color

    def pixel(x, y):
        c = bg(x, y)
        # top bar
        if 12 <= y < 40 and 12 <= x < W - 12:
            return bar
        # waybar "modules": little pill blocks
        if 18 <= y < 34:
            for bx, bw in ((20, 60), (90, 40), (140, 46)):
                if bx <= x < bx + bw and 20 <= y < 32:
                    return lerp(bar, text, 0.22)
            if W - 12 - 46 <= x < W - 12 - 16 and 20 <= y < 32:
                return lerp(bar, accent, 0.5)
        # terminal window
        if 90 <= y < H - 60 and 140 <= x < W - 140:
            return term
        if 90 <= y < 116 and 140 <= x < W - 140:
            return lerp(term, (255, 255, 255), 0.08)
        # titlebar buttons
        if 98 <= y < 108:
            for i, bx in enumerate((W - 140 - 26, W - 140 - 46, W - 140 - 66)):
                if bx <= x < bx + 10:
                    return (200, 90, 90) if i == 0 else lerp(term, text, 0.3)
        # prompt + code lines (colored strips)
        if 130 <= y < H - 80 and 160 <= x < W - 180:
            row = (y - 130) // 18
            col = (x - 160) // 9
            line = row % 7
            widths = (10, 22, 16, 30, 12, 26, 8)
            if col < widths[line]:
                t = (col + row) % 5
                color = accent if t == 0 else lerp(text, term, 0.35) if t in (1, 3) else lerp(text, term, 0.6)
                if y % 18 < 10:
                    return color
        return c

    return png(W, H, pixel)


def wallpaper(profile_id: str) -> bytes:
    bg_top, bg_bottom, bar, term, text, accent = PROFILE_ART[profile_id]
    mid = lerp(bg_top, bg_bottom, 0.5)

    def pixel(x, y):
        t = y / H
        c = lerp(bg_top, mid, t * 2) if t < 0.5 else lerp(mid, bg_bottom, (t - 0.5) * 2)
        # soft radial glow accent
        dx, dy = x - W * 0.7, y - H * 0.35
        d = (dx * dx + dy * dy) / (W * W * 0.22)
        if d < 1:
            c = lerp(c, accent, (1 - d) * 0.45)
        return c

    return png(1600, 900, pixel)


def main() -> int:
    for profile_id in PROFILE_ART:
        directory = REPO / "data" / "profiles" / profile_id / "assets"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "preview.png").write_bytes(preview(profile_id))
        (directory / "wallpaper.png").write_bytes(wallpaper(profile_id))
        print(f"generated {profile_id}: preview.png, wallpaper.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())

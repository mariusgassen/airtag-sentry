"""One-off: render AirTagSentry's PWA icons and commit the resulting PNGs.

Not a runtime dependency - Pillow is only needed to run this script once:
    pip install pillow
    python scripts/generate_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent.parent / "airtag_sentry" / "web" / "static" / "icons"
FAVICON_OUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "favicon.ico"
BG = (10, 132, 255)  # matches the app's --accent (index.css)
FG = (255, 255, 255)


def _draw_glyph(draw: ImageDraw.ImageDraw, size: int) -> None:
    # A simple location-pin-with-dot glyph, scaled to `size`.
    cx = size / 2
    pin_top = size * 0.18
    pin_bottom = size * 0.62
    radius = size * 0.22

    draw.ellipse(
        [cx - radius, pin_top, cx + radius, pin_top + 2 * radius],
        fill=FG,
    )
    draw.polygon(
        [
            (cx - radius * 0.75, pin_top + radius * 1.55),
            (cx + radius * 0.75, pin_top + radius * 1.55),
            (cx, pin_bottom),
        ],
        fill=FG,
    )
    dot_radius = radius * 0.35
    draw.ellipse(
        [cx - dot_radius, pin_top + radius - dot_radius, cx + dot_radius, pin_top + radius + dot_radius],
        fill=BG,
    )


def make_icon(size: int, maskable: bool) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG if maskable else (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if not maskable:
        draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=size * 0.18, fill=BG)
    # Maskable icons need extra safe-zone padding (~10%) so OS masks don't clip the glyph.
    inset = size * 0.15 if maskable else 0
    glyph_size = size - 2 * inset
    glyph = Image.new("RGBA", (int(glyph_size), int(glyph_size)), (0, 0, 0, 0))
    _draw_glyph(ImageDraw.Draw(glyph), int(glyph_size))
    img.paste(glyph, (int(inset), int(inset)), glyph)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_icon(192, maskable=False).save(OUT_DIR / "icon-192.png")
    make_icon(512, maskable=False).save(OUT_DIR / "icon-512.png")
    make_icon(512, maskable=True).save(OUT_DIR / "icon-maskable-512.png")
    print(f"Wrote icons to {OUT_DIR}")

    # Browsers/bookmark tools request /favicon.ico directly regardless of the
    # <link rel="icon"> tag - render it from the same glyph at the sizes a
    # .ico is actually expected to carry, into frontend/public/ so Vite
    # copies it to the build root alongside the manifest.
    FAVICON_OUT.parent.mkdir(parents=True, exist_ok=True)
    make_icon(256, maskable=False).save(
        FAVICON_OUT, sizes=[(16, 16), (32, 32), (48, 48)]
    )
    print(f"Wrote favicon to {FAVICON_OUT}")


if __name__ == "__main__":
    main()

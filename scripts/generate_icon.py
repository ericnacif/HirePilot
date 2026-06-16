"""Gera cv_apply/static/icon.ico — marca HirePilot (#F6F8FC + #5D8CFF)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cv_apply" / "static" / "icon.ico"

SURFACE = (246, 248, 252, 255)  # #F6F8FC
BLUE = (93, 140, 255, 255)  # #5D8CFF
BLUE_DARK = (74, 122, 238, 255)  # #4A7AEE
BLUE_LIGHT = (143, 176, 255, 255)  # #8FB0FF
INK = (26, 32, 48, 255)


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _vertical_gradient(size: int, top: tuple[int, ...], bottom: tuple[int, ...]) -> Image.Image:
    img = Image.new("RGBA", (size, size))
    px = img.load()
    for y in range(size):
        t = y / max(size - 1, 1)
        row = tuple(_lerp(top[i], bottom[i], t) for i in range(4))
        for x in range(size):
            px[x, y] = row
    return img


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _draw_plane(draw: ImageDraw.ImageDraw, s: float, ox: float, oy: float) -> None:
    body = [
        (ox + 11 * s, oy + 27.5 * s),
        (ox + 29 * s, oy + 12.5 * s),
        (ox + 19.5 * s, oy + 21.5 * s),
        (ox + 23.5 * s, oy + 29.5 * s),
        (ox + 19 * s, oy + 27 * s),
    ]
    shadow = [(x + 1.2 * s, y + 1.6 * s) for x, y in body]
    draw.polygon(shadow, fill=(74, 122, 238, 70))
    draw.polygon(body, fill=BLUE)
    draw.polygon(
        [
            (ox + 11 * s, oy + 27.5 * s),
            (ox + 19.5 * s, oy + 21.5 * s),
            (ox + 23.5 * s, oy + 29.5 * s),
        ],
        fill=BLUE_DARK,
    )
    draw.line(
        [(ox + 11 * s, oy + 27.5 * s), (ox + 19.5 * s, oy + 21.5 * s), (ox + 23.5 * s, oy + 29.5 * s)],
        fill=(246, 248, 252, 170),
        width=max(1, int(0.85 * s)),
        joint="curve",
    )
    draw.ellipse(
        (
            ox + 27.2 * s,
            oy + 11.2 * s,
            ox + 29.8 * s,
            oy + 13.8 * s,
        ),
        fill=BLUE_LIGHT,
    )


def _draw_icon(size: int) -> Image.Image:
    scale = 4 if size >= 48 else 2
    canvas = size * scale
    radius = int(canvas * 0.22)

    base = _vertical_gradient(canvas, (255, 255, 255, 255), SURFACE)
    mask = _rounded_mask(canvas, radius)
    rounded = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    rounded.paste(base, mask=mask)

    draw = ImageDraw.Draw(rounded)
    # anel suave
    ring_pad = canvas * 0.11
    draw.ellipse(
        (ring_pad, ring_pad, canvas - ring_pad, canvas - ring_pad),
        outline=(93, 140, 255, 55),
        width=max(1, canvas // 64),
    )

    s = canvas / 40.0
    ox = canvas * 0.02
    oy = canvas * 0.02
    _draw_plane(draw, s, ox, oy)

    glow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse(
        (canvas * 0.18, canvas * 0.22, canvas * 0.82, canvas * 0.78),
        fill=(93, 140, 255, 38),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=canvas // 18))
    rounded = Image.alpha_composite(glow, rounded)

    border = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        (0, 0, canvas - 1, canvas - 1),
        radius=radius,
        outline=(93, 140, 255, 42),
        width=max(1, canvas // 80),
    )
    rounded = Image.alpha_composite(rounded, border)

    if scale > 1:
        rounded = rounded.resize((size, size), Image.Resampling.LANCZOS)
    return rounded


def main() -> None:
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    images = [_draw_icon(s) for s, _ in sizes]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(OUT, format="ICO", sizes=sizes, append_images=images[1:])
    png = OUT.with_suffix(".png")
    _draw_icon(512).save(png, format="PNG")
    print(f"Ícone gerado: {OUT}")
    print(f"Preview PNG: {png}")


if __name__ == "__main__":
    main()

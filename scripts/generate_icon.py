"""Gera cv_apply/static/icon.ico — marca HirePilot (#F6F8FC + #5D8CFF)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cv_apply" / "static" / "icon.ico"

SURFACE = (246, 248, 252, 255)  # #F6F8FC
BLUE = (93, 140, 255, 255)  # #5D8CFF
WHITE = (246, 248, 252, 255)


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


def _lerp_color(c1: tuple[int, ...], c2: tuple[int, ...], t: float) -> tuple[int, ...]:
    return tuple(_lerp(c1[i], c2[i], t) for i in range(4))


def _draw_mark(draw: ImageDraw.ImageDraw, s: float, ox: float, oy: float) -> None:
    """Mesmo símbolo do logo.svg: degraus + trilha + alvo."""
    # trilha
    trail = [
        (ox + 8 * s, oy + 30.5 * s),
        (ox + 14 * s, oy + 30.5 * s),
        (ox + 18 * s, oy + 22 * s),
        (ox + 22 * s, oy + 16.5 * s),
        (ox + 25 * s, oy + 12.5 * s),
        (ox + 28.5 * s, oy + 9.5 * s),
        (ox + 32.5 * s, oy + 8 * s),
    ]
    draw.line(trail, fill=(93, 140, 255, 70), width=max(1, int(2.2 * s)), joint="curve")

    bars = [
        (8, 25, 5.5, 9, 0.42),
        (16, 19.5, 5.5, 14.5, 0.68),
        (24, 14, 5.5, 20, 1.0),
    ]
    for x, y, w, h, alpha in bars:
        x0, y0 = ox + x * s, oy + y * s
        x1, y1 = ox + (x + w) * s, oy + (y + h) * s
        fill = (BLUE[0], BLUE[1], BLUE[2], int(255 * alpha))
        draw.rounded_rectangle((x0, y0, x1, y1), radius=2.75 * s, fill=fill)

    # seta
    arrow = [
        (ox + 26.75 * s, oy + 10.5 * s),
        (ox + 32.5 * s, oy + 8 * s),
        (ox + 30.25 * s, oy + 13.75 * s),
    ]
    draw.polygon(arrow, fill=WHITE, outline=BLUE)

    # alvo
    cx, cy = ox + 32.5 * s, oy + 8 * s
    r1, r2 = 2.1 * s, 0.85 * s
    draw.ellipse((cx - r1, cy - r1, cx + r1, cy + r1), fill=BLUE)
    draw.ellipse((cx - r2, cy - r2, cx + r2, cy + r2), fill=WHITE)


def _draw_icon(size: int) -> Image.Image:
    scale = 4 if size >= 48 else 2
    canvas = size * scale
    radius = int(canvas * 0.22)

    base = _vertical_gradient(canvas, (255, 255, 255, 255), SURFACE)
    mask = _rounded_mask(canvas, radius)
    rounded = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    rounded.paste(base, mask=mask)

    glow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse(
        (canvas * 0.12, canvas * 0.1, canvas * 0.88, canvas * 0.82),
        fill=(93, 140, 255, 32),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=canvas // 16))
    rounded = Image.alpha_composite(glow, rounded)

    draw = ImageDraw.Draw(rounded)
    s = canvas / 40.0
    _draw_mark(draw, s, 0, 0)

    border = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        (0, 0, canvas - 1, canvas - 1),
        radius=radius,
        outline=(93, 140, 255, 48),
        width=max(1, canvas // 72),
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

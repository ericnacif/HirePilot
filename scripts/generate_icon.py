"""Gera cv_apply/static/icon.ico a partir de logo.png (arte oficial)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "cv_apply" / "static" / "logo.png"
OUT = ROOT / "cv_apply" / "static" / "icon.ico"


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _draw_icon(size: int) -> Image.Image:
    scale = 4 if size >= 48 else 2
    canvas = size * scale
    radius = int(canvas * 0.22)

    base = Image.new("RGBA", (canvas, canvas), (8, 10, 14, 255))
    mask = _rounded_mask(canvas, radius)
    rounded = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    rounded.paste(base, mask=mask)

    logo = Image.open(LOGO).convert("RGBA")
    pad = int(canvas * 0.14)
    inner = canvas - pad * 2
    logo.thumbnail((inner, inner), Image.Resampling.LANCZOS)
    lx = (canvas - logo.width) // 2
    ly = (canvas - logo.height) // 2
    rounded.paste(logo, (lx, ly), logo)

    glow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse(
        (canvas * 0.08, canvas * 0.06, canvas * 0.92, canvas * 0.88),
        fill=(93, 140, 255, 28),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=canvas // 16))
    rounded = Image.alpha_composite(glow, rounded)

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
    if not LOGO.is_file():
        raise SystemExit(f"Arquivo não encontrado: {LOGO}. Rode scripts/import_brand_assets.py primeiro.")

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

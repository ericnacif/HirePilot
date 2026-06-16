"""Gera cv_apply/static/icon.ico a partir do visual do logo HirePilot."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cv_apply" / "static" / "icon.ico"


def _draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(2, size // 16)
    draw.ellipse(
        (pad, pad, size - pad, size - pad),
        outline=(37, 99, 235, 90),
        width=max(1, size // 18),
    )
    # Avião estilizado (coordenadas relativas ao logo SVG)
    s = size / 40.0
    pts = [
        (11 * s, 27.5 * s),
        (29 * s, 12.5 * s),
        (19.5 * s, 21.5 * s),
        (23.5 * s, 29.5 * s),
        (19 * s, 27 * s),
    ]
    draw.polygon(pts, fill=(37, 99, 235, 255))
    draw.polygon(
        [(11 * s, 27.5 * s), (19.5 * s, 21.5 * s), (23.5 * s, 29.5 * s)],
        outline=(255, 255, 255, 120),
    )
    return img


def main() -> None:
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    images = [_draw_icon(s) for s, _ in sizes]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(OUT, format="ICO", sizes=sizes, append_images=images[1:])
    print(f"Ícone gerado: {OUT}")


if __name__ == "__main__":
    main()

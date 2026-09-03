"""Importa logos de brand_assets/ para cv_apply/static/.

Coloque na pasta brand_assets/ (não versionada):
  - logo-source.png      — ícone sozinho (fundo escuro ok)
  - wordmark-source.png  — logo com texto Vaga em Vista

Uso: python scripts/import_brand_assets.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BRAND_DIR = ROOT / "brand_assets"
STATIC = ROOT / "cv_apply" / "static"

DEFAULT_ICON = BRAND_DIR / "logo-source.png"
DEFAULT_WORDMARK = BRAND_DIR / "wordmark-source.png"

INK = (26, 32, 48, 255)  # #1A2030


def _is_bg(r: int, g: int, b: int, threshold: int = 28) -> bool:
    return r <= threshold and g <= threshold and b <= threshold


def _crop_content(img: Image.Image, pad: int = 8) -> Image.Image:
    rgba = img.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    min_x, min_y, max_x, max_y = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a and not _is_bg(r, g, b):
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x <= min_x:
        return rgba
    return rgba.crop(
        (max(0, min_x - pad), max(0, min_y - pad), min(w, max_x + pad), min(h, max_y + pad))
    )


def _remove_black_bg(img: Image.Image, threshold: int = 42) -> Image.Image:
    """Remove só o fundo preto conectado às bordas (preserva roxo escuro do logo)."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    seen = bytearray(w * h)
    stack: list[tuple[int, int]] = []

    def bg_at(x: int, y: int) -> bool:
        r, g, b, _a = px[x, y]
        return _is_bg(r, g, b, threshold)

    for x in range(w):
        if bg_at(x, 0):
            stack.append((x, 0))
        if bg_at(x, h - 1):
            stack.append((x, h - 1))
    for y in range(h):
        if bg_at(0, y):
            stack.append((0, y))
        if bg_at(w - 1, y):
            stack.append((w - 1, y))

    while stack:
        x, y = stack.pop()
        idx = y * w + x
        if seen[idx]:
            continue
        if not bg_at(x, y):
            continue
        seen[idx] = 1
        px[x, y] = (0, 0, 0, 0)
        if x:
            stack.append((x - 1, y))
        if x + 1 < w:
            stack.append((x + 1, y))
        if y:
            stack.append((x, y - 1))
        if y + 1 < h:
            stack.append((x, y + 1))
    return rgba


def _is_white_text(r: int, g: int, b: int) -> bool:
    return r > 210 and g > 210 and b > 210 and max(r, g, b) - min(r, g, b) < 25


def _wordmark_light(img: Image.Image) -> Image.Image:
    """Versão para tema claro: 'Hire' branco vira tinta escura."""
    rgba = img.convert("RGBA")
    px = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = px[x, y]
            if not a:
                continue
            if _is_white_text(r, g, b):
                px[x, y] = INK
    return rgba


def _resolve_src(path: Path | None, default: Path) -> Path:
    src = path or default
    if not src.is_file():
        raise SystemExit(
            f"Arquivo não encontrado: {src}\n"
            f"Coloque as imagens em {BRAND_DIR}/ ou passe --icon / --wordmark."
        )
    return src


def main() -> None:
    parser = argparse.ArgumentParser(description="Processa logos para cv_apply/static/")
    parser.add_argument("--icon", type=Path, help="PNG do ícone (padrão: brand_assets/logo-source.png)")
    parser.add_argument("--wordmark", type=Path, help="PNG com texto (padrão: brand_assets/wordmark-source.png)")
    args = parser.parse_args()

    icon_src = _resolve_src(args.icon, DEFAULT_ICON)
    wordmark_src = _resolve_src(args.wordmark, DEFAULT_WORDMARK)

    STATIC.mkdir(parents=True, exist_ok=True)

    icon = _remove_black_bg(_crop_content(Image.open(icon_src)))
    icon.save(STATIC / "logo.png", optimize=True)
    print(f"logo.png: {icon.size}")

    wordmark = _remove_black_bg(_crop_content(Image.open(wordmark_src)))
    wordmark.save(STATIC / "logo-wordmark.png", optimize=True)
    print(f"logo-wordmark.png: {wordmark.size}")

    light = _wordmark_light(wordmark.copy())
    light.save(STATIC / "logo-wordmark-light.png", optimize=True)
    print(f"logo-wordmark-light.png: {light.size}")


if __name__ == "__main__":
    main()

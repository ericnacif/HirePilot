"""Importa logos enviadas pelo usuário para cv_apply/static/."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(
    r"C:/Users/Levex/.cursor/projects/c-Users-Levex-Desktop-LOGOS-PNG-eric/assets"
)
STATIC = ROOT / "cv_apply" / "static"

ICON_SRC = ASSETS / (
    "c__Users_Levex_AppData_Roaming_Cursor_User_workspaceStorage_"
    "a8ea636a7fe656e6b853e8210a475330_images_image-8e54e566-ab86-4862-9424-2f6d29433aa1.png"
)
WORDMARK_SRC = ASSETS / (
    "c__Users_Levex_AppData_Roaming_Cursor_User_workspaceStorage_"
    "a8ea636a7fe656e6b853e8210a475330_images_image-f09160d6-65e4-48d3-a2f6-23d1e885b169.png"
)

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


def main() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)

    icon = _remove_black_bg(_crop_content(Image.open(ICON_SRC)))
    icon.save(STATIC / "logo.png", optimize=True)
    print(f"logo.png: {icon.size}")

    wordmark = _remove_black_bg(_crop_content(Image.open(WORDMARK_SRC)))
    wordmark.save(STATIC / "logo-wordmark.png", optimize=True)
    print(f"logo-wordmark.png: {wordmark.size}")

    light = _wordmark_light(wordmark.copy())
    light.save(STATIC / "logo-wordmark-light.png", optimize=True)
    print(f"logo-wordmark-light.png: {light.size}")


if __name__ == "__main__":
    main()

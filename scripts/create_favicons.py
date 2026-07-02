"""Create raster favicon assets from the existing StudyRoute mark."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "assets" / "images"


def draw_icon(size: int) -> Image.Image:
    scale = size / 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = int(12 * scale)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill="#0f766e")

    def s(value: float) -> float:
        return value * scale

    draw.polygon(
        [
            (s(18), s(20)),
            (s(36), s(20)),
            (s(42), s(22)),
            (s(46), s(26)),
            (s(46), s(32)),
            (s(42), s(36)),
            (s(36), s(38)),
            (s(26), s(38)),
            (s(26), s(48)),
            (s(18), s(48)),
        ],
        fill="#ffffff",
    )
    draw.rectangle((s(26), s(27), s(36), s(31)), fill="#0f766e")
    draw.polygon([(s(39), s(39)), (s(47), s(48)), (s(38), s(48)), (s(31), s(39))], fill="#9fd6cd")
    return image


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    draw_icon(32).save(IMAGE_DIR / "favicon-32x32.png")
    draw_icon(180).save(IMAGE_DIR / "apple-touch-icon.png")
    draw_icon(64).save(
        IMAGE_DIR / "favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64)],
    )
    print("Created favicon.ico, favicon-32x32.png, apple-touch-icon.png")


if __name__ == "__main__":
    main()

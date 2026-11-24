"""Portrait still for the plant-knowledge plate.

The glass case and the two makers at the leaf tray stay at one source
scale. The ground and the decorative swoosh are left out so the objects
can stack. This is not the beginning of tea in India, and not an estate.
"""
from pathlib import Path
import re

import cairosvg
from PIL import Image

HERE = Path(__file__).resolve().parent
ART = HERE.parent
SAGE = (232, 236, 223, 255)


def render(svg: str, width: int) -> Image.Image:
    png = HERE / "_render.png"
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png), output_width=width)
    im = Image.open(png).convert("RGBA")
    plate = Image.new("RGBA", im.size, SAGE)
    return Image.alpha_composite(plate, im).convert("RGB")


def crop_view(im: Image.Image, box, pad: int = 12) -> Image.Image:
    sx = im.width / 760
    sy = im.height / 320
    x0, y0, x1, y1 = box
    l = max(0, int((x0 - pad) * sx))
    t = max(0, int((y0 - pad) * sy))
    r = min(im.width, int((x1 + pad) * sx))
    b = min(im.height, int((y1 + pad) * sy))
    return im.crop((l, t, r, b))


def stack(parts: list[Image.Image], gap: int = 40) -> Image.Image:
    width = max(part.width for part in parts)
    height = sum(part.height for part in parts) + gap * (len(parts) - 1)
    canvas = Image.new("RGB", (width, height), SAGE[:3])
    y = 0
    for part in parts:
        canvas.paste(part, ((width - part.width) // 2, y))
        y += part.height + gap
    return canvas


def main() -> None:
    raw = (HERE / "plant-knowledge.svg").read_text()
    raw = re.sub(r"<rect\b[^>]*/>", "", raw, count=1)
    raw = raw.replace(
        '<path d="M24 261 Q154 204 277 249 Q480 198 735 254 V294 H24Z" fill="#d1dbc6" stroke="#d1dbc6" stroke-width="3"/>',
        "",
    )
    raw = raw.replace(
        '<path d="M36 104 Q120 48 216 90 T409 94" fill="none" stroke="#c6d1bd" stroke-width="15"/>',
        "",
    )
    im = render(raw, 1600)
    case = crop_view(im, (48, 80, 250, 270))
    makers = crop_view(im, (310, 70, 720, 310))
    plate = stack([case, makers])
    for name in ("h04-known.png", "h04-takeaway.png"):
        plate.save(ART / name)
    print("h04", plate.size)


if __name__ == "__main__":
    main()

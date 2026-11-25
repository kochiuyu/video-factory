"""Portrait still for the monastery-day plate.

Official objects stay whole and at one source scale: the dawn window with
the tea bowl in front of it, the bell, and the open book. The wide shelf
that only connected them is left out. This is not a monastery interior.
"""
from pathlib import Path

import cairosvg
from PIL import Image

HERE = Path(__file__).resolve().parent
ART = HERE.parent
CREAM = (250, 245, 232, 255)


def render(svg: str, width: int) -> Image.Image:
    png = HERE / "_render.png"
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png), output_width=width)
    im = Image.open(png).convert("RGBA")
    plate = Image.new("RGBA", im.size, CREAM)
    return Image.alpha_composite(plate, im).convert("RGB")


def crop_view(im: Image.Image, box, pad: int = 10) -> Image.Image:
    """Crop a viewBox rectangle. `box` is in the 760×320 source space."""
    sx = im.width / 760
    sy = im.height / 320
    x0, y0, x1, y1 = box
    l = max(0, int((x0 - pad) * sx))
    t = max(0, int((y0 - pad) * sy))
    r = min(im.width, int((x1 + pad) * sx))
    b = min(im.height, int((y1 + pad) * sy))
    return im.crop((l, t, r, b))


def row(parts: list[Image.Image], gap: int = 36) -> Image.Image:
    height = max(part.height for part in parts)
    width = sum(part.width for part in parts) + gap * (len(parts) - 1)
    canvas = Image.new("RGB", (width, height), CREAM[:3])
    x = 0
    for part in parts:
        canvas.paste(part, (x, (height - part.height) // 2))
        x += part.width + gap
    return canvas


def stack(parts: list[Image.Image], gap: int = 48) -> Image.Image:
    width = max(part.width for part in parts)
    height = sum(part.height for part in parts) + gap * (len(parts) - 1)
    canvas = Image.new("RGB", (width, height), CREAM[:3])
    y = 0
    for part in parts:
        canvas.paste(part, ((width - part.width) // 2, y))
        y += part.height + gap
    return canvas


def main() -> None:
    raw = (HERE / "monastery-day.svg").read_text()
    # The shelf only ties the objects into a landscape card.
    raw = raw.replace(
        '<path d="M40 258 H720 M70 259 V285 M691 259 V285" fill="#b4c1a5"/>',
        "",
    )
    raw = raw.replace(
        '<path d="M542 280 H713" fill="none" stroke="#b4c1a5"/>',
        "",
    )
    im = render(raw, 1600)
    # Window and bowl overlap in the official drawing, so they stay one crop.
    window = crop_view(im, (40, 30, 232, 262))
    bell = crop_view(im, (548, 58, 720, 248))
    book = crop_view(im, (242, 158, 516, 250))
    plate = stack([row([window, bell]), book])
    for name in ("h02-practice.png", "h02-timetable.png", "h02-takeaway.png"):
        plate.save(ART / name)
    print("h02", plate.size)


if __name__ == "__main__":
    main()

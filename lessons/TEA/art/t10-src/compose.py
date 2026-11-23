"""Stack the official brewing tools into a portrait still.

Thermometer, spoon, cup, and timer stay at one source scale.
Nothing is stretched. The cup foot, thermometer bulb, and timer crown stay whole.
"""
from pathlib import Path

import cairosvg
from PIL import Image

HERE = Path(__file__).resolve().parent
ART = HERE.parent
BG = (232, 236, 223, 255)
PAD = 28


def render(svg: str, width: int) -> Image.Image:
    png = HERE / "_render.png"
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png), output_width=width)
    im = Image.open(png).convert("RGBA")
    plate = Image.new("RGBA", im.size, BG)
    return Image.alpha_composite(plate, im).convert("RGB")


def bbox(im: Image.Image, tol: int = 12):
    px = im.load()
    w, h = im.size
    minx, miny, maxx, maxy = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - 232) > tol or abs(g - 236) > tol or abs(b - 223) > tol:
                minx = min(minx, x)
                miny = min(miny, y)
                maxx = max(maxx, x)
                maxy = max(maxy, y)
    return minx, miny, maxx + 1, maxy + 1


def trim(im: Image.Image, pad: int = 10) -> Image.Image:
    x0, y0, x1, y1 = bbox(im)
    return im.crop((
        max(0, x0 - pad),
        max(0, y0 - pad),
        min(im.width, x1 + pad),
        min(im.height, y1 + pad),
    ))


def row(parts: list[Image.Image], gap: int = 24) -> Image.Image:
    width = sum(part.width for part in parts) + gap * (len(parts) - 1)
    height = max(part.height for part in parts)
    canvas = Image.new("RGB", (width, height), BG[:3])
    x = 0
    for part in parts:
        canvas.paste(part, (x, (height - part.height) // 2))
        x += part.width + gap
    return canvas


def stack(parts: list[Image.Image], gap: int = 36) -> Image.Image:
    width = max(part.width for part in parts) + PAD * 2
    height = sum(part.height for part in parts) + gap * (len(parts) - 1) + PAD * 2
    canvas = Image.new("RGB", (width, height), BG[:3])
    y = PAD
    for part in parts:
        canvas.paste(part, ((width - part.width) // 2, y))
        y += part.height + gap
    return canvas


def piece(svg: str, start: str, end: str | None) -> str:
    i = svg.find(start)
    if i < 0:
        raise SystemExit(f"missing {start[:48]}")
    j = len(svg) if end is None else svg.find(end, i)
    if j < 0:
        raise SystemExit(f"missing end {end[:48]}")
    head = svg[: svg.find(">") + 1]
    body = svg[i:j].replace("</svg>", "")
    return head + body + "</svg>"


def main() -> None:
    svg = (HERE / "brewing.svg").read_text()
    cup = piece(svg, '<path d="M132 76', '<path d="M51 95')
    steam = piece(svg, '<path d="M105 53', None)
    spoon = piece(svg, '<path d="M51 95', '<path d="M44 31')
    thermo = piece(svg, '<path d="M44 31', '<rect x="180"')
    timer = piece(svg, '<rect x="180"', '<path d="M105 53')
    head = svg[: svg.find(">") + 1]
    cup_svg = head + cup[cup.find(">") + 1 : -6] + steam[steam.find(">") + 1 :]
    width = 1400
    thermo_im = trim(render(thermo, width))
    spoon_im = trim(render(spoon, width))
    cup_im = trim(render(cup_svg, width))
    timer_im = trim(render(timer, width))
    tools = row([thermo_im, spoon_im, cup_im], gap=20)
    plate = stack([tools, timer_im], gap=36)
    for name in ("t10-hook.png", "t10-brew.png", "t10-takeaway.png"):
        plate.save(ART / name)
    print("t10", plate.size)
    (HERE / "_render.png").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

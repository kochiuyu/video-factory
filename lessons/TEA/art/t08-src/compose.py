"""Stack the official decaf packet and leaf plate into a portrait still.

The unmarked packet and the loose leaves stay at one source scale.
Nothing is stretched, and no leaf or packet edge is cropped.
The plate has no zero-caffeine badge.
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


def trim(im: Image.Image, pad: int = 12) -> Image.Image:
    x0, y0, x1, y1 = bbox(im)
    return im.crop((
        max(0, x0 - pad),
        max(0, y0 - pad),
        min(im.width, x1 + pad),
        min(im.height, y1 + pad),
    ))


def stack(parts: list[Image.Image], gap: int = 48) -> Image.Image:
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
        raise SystemExit(f"missing {start[:40]}")
    j = len(svg) if end is None else svg.find(end, i)
    if j < 0:
        raise SystemExit(f"missing end {end[:40]}")
    head = svg[: svg.find(">") + 1]
    body = svg[i:j].replace("</svg>", "")
    return head + body + "</svg>"


def main() -> None:
    svg = (HERE / "decaf.svg").read_text()
    packet = piece(svg, '<path d="M155 32', '<ellipse cx="93"')
    leaves = piece(svg, '<ellipse cx="93"', None)
    width = 1400
    packet_im = trim(render(packet, width))
    leaves_im = trim(render(leaves, width))
    plate = stack([packet_im, leaves_im], gap=40)
    for name in ("t08-hook.png", "t08-claim.png", "t08-takeaway.png"):
        plate.save(ART / name)
    print("t08", plate.size, "packet", packet_im.size, "leaves", leaves_im.size)
    (HERE / "_render.png").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

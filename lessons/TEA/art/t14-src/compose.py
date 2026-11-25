"""Portrait stills for earlier tea forms and a later mug.

The Song bowl and whisk stay at one source scale, with the foot and the
tines whole. The later card uses one complete official mug.
This is not the grocery-matcha plate.
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


def stack(parts: list[Image.Image], gap: int = 40) -> Image.Image:
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
    song = (HERE / "song-powder.svg").read_text()
    bowl = piece(song, '<path d="M39 72', '<path d="M177 26')
    whisk = piece(song, '<path d="M177 26', None)
    width = 1400
    bowl_im = trim(render(bowl, width))
    whisk_im = trim(render(whisk, width))
    powder = stack([whisk_im, bowl_im], gap=36)
    powder.save(ART / "t14-powder.png")

    mug_svg = (HERE / "mug.svg").read_text()
    mug = piece(mug_svg, '<ellipse cx="91"', '<ellipse cx="253"')
    mug_im = trim(render(mug, 1200), pad=16)
    mug_im.save(ART / "t14-hook.png")
    mug_im.save(ART / "t14-takeaway.png")
    print("powder", powder.size, "bowl", bowl_im.size, "whisk", whisk_im.size, "mug", mug_im.size)
    (HERE / "_render.png").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

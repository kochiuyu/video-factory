"""Stack official matcha plates into portrait stills.

The powder, bowl, and whisk stay at the scale of their source drawing.
Nothing is stretched, and no tine, rim, or mound is cropped.
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


def trim(im: Image.Image, pad: int = 8) -> Image.Image:
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


def save(im: Image.Image, name: str) -> None:
    im.save(ART / name)
    print(name, im.size)


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
    matcha = (HERE / "matcha.svg").read_text()
    powder = piece(matcha, '<ellipse cx="68"', '<path d="M126')
    bowl = piece(matcha, '<path d="M126', None)
    # Drop the shared ground shadow; each object keeps its own drawing.
    powder = powder.replace(
        '<ellipse cx="124" cy="124" rx="94" ry="8" fill="#d1dbc6" stroke="none" stroke-width="1.5"/>',
        "",
    )
    width = 1400
    powder_im = trim(render(powder, width))
    bowl_im = trim(render(bowl, width))
    save(stack([powder_im, bowl_im], gap=56), "t07-hook.png")

    whisk_svg = (HERE / "matcha-whisk.svg").read_text()
    head = whisk_svg[: whisk_svg.find(">") + 1]
    bowl_body = whisk_svg[whisk_svg.find('<path d="M64 108') : whisk_svg.find('<g transform="rotate')]
    whisk_body = whisk_svg[whisk_svg.find('<g transform="rotate') :]
    tea_bowl = (
        head
        + '<ellipse cx="143" cy="171" rx="88" ry="9" fill="#576a45" stroke="none" stroke-width="2" opacity=".10"/>'
        + bowl_body
        + "</svg>"
    )
    whisk = (
        head
        + '<ellipse cx="282" cy="169" rx="37" ry="5" fill="#576a45" stroke="none" stroke-width="2" opacity=".10"/>'
        + whisk_body
    )
    # The whisk file is 360 wide. Render at a width that matches matcha's scale
    # only within this file: bowl and whisk share one render width.
    w = 1600
    tea_bowl_im = trim(render(tea_bowl, w), pad=12)
    whisk_im = trim(render(whisk, w), pad=16)
    save(stack([whisk_im, tea_bowl_im], gap=36), "t07-whisk.png")
    save(stack([tea_bowl_im], gap=0), "t07-takeaway.png")
    (HERE / "_render.png").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

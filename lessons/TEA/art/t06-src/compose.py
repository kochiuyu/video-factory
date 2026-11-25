"""Rearrange official tea-companion plates into T06 portrait stills.

Sources are the SVGs in this folder. Nothing is stretched. The Assam map
keeps its full coastline and locator dot; only the English "India" label
is omitted so the shared PNG stays unlabeled. Earl Grey keeps the fruit
separate from the leaves. Orange Pekoe keeps the whole dish.
"""
from pathlib import Path

import cairosvg
from PIL import Image

HERE = Path(__file__).resolve().parent
ART = HERE.parent
BG = (232, 236, 223, 255)
PAD = 36


def render(name: str, width: int, drop_india: bool = False) -> Image.Image:
    raw = (HERE / name).read_text()
    if drop_india:
        raw = raw.replace(
            '<text x="93.91" y="62.42" fill="#395448" '
            'font-family="system-ui,sans-serif" font-size="17" '
            'font-weight="600" text-anchor="middle">India</text>',
            "",
        )
    png = HERE / "_render.png"
    cairosvg.svg2png(bytestring=raw.encode(), write_to=str(png), output_width=width)
    im = Image.open(png).convert("RGBA")
    plate = Image.new("RGBA", im.size, BG)
    return Image.alpha_composite(plate, im).convert("RGB")


def bbox(im: Image.Image, tol: int = 14):
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


def trim(im: Image.Image, pad: int = PAD) -> Image.Image:
    x0, y0, x1, y1 = bbox(im)
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(im.width, x1 + pad)
    y1 = min(im.height, y1 + pad)
    return im.crop((x0, y0, x1, y1))


def save(im: Image.Image, name: str) -> None:
    im.save(ART / name)
    print(name, im.size)


def main() -> None:
    # Full north-up map. Crop only the outer margin, not the land or the dot.
    assam = render("assam.svg", 1200, drop_india=True)
    scale = 1200 / 240
    panel = assam.crop((
        int(8 * scale), int(6 * scale), int(232 * scale), int(144 * scale),
    ))
    save(panel, "t06-place.png")

    raw = (HERE / "earl-grey.svg").read_text()
    cut = raw.find('<path d="M185 46')
    plate_svg = raw[:cut] + "</svg>"
    fruit_svg = raw[: raw.find(">") + 1] + raw[cut:]
    width = 1100
    tmp = HERE / "_part.svg"
    tmp.write_text(plate_svg)
    plate = trim(render("_part.svg", width))
    tmp.write_text(fruit_svg)
    fruit = trim(render("_part.svg", width))
    gap = 72
    stack = Image.new("RGB", (
        max(plate.width, fruit.width) + PAD * 2,
        fruit.height + gap + plate.height + PAD * 2,
    ), BG[:3])
    stack.paste(fruit, ((stack.width - fruit.width) // 2, PAD))
    stack.paste(plate, ((stack.width - plate.width) // 2, PAD + fruit.height + gap))
    save(stack, "t06-bergamot.png")
    tmp.unlink(missing_ok=True)
    (HERE / "_render.png").unlink(missing_ok=True)

    save(trim(render("op.svg", 1200)), "t06-size.png")
    label = trim(render("label.svg", 1200))
    save(label, "t06-hook.png")
    save(label, "t06-takeaway.png")
    (HERE / "_render.png").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

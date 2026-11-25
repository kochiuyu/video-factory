"""Portrait still for the Canton exchange plate.

House, merchant desk, generic ship, and tea chests stay whole at one
source scale. The wide water band and the wave are left out. This is not
a named ship and not a reconstruction of the harbor.
"""
from pathlib import Path
import re

import cairosvg
from PIL import Image

HERE = Path(__file__).resolve().parent
ART = HERE.parent
SAGE = (232, 236, 223, 255)


def parts(svg: str) -> list[str]:
    match = re.search(r"<g stroke[^>]*>", svg)
    body = svg[match.end() : svg.rfind("</g>")]
    found: list[str] = []
    i = 0
    while i < len(body):
        if body[i].isspace() or not body.startswith("<", i):
            i += 1
            continue
        if body.startswith("<g", i):
            depth = 0
            j = i
            while j < len(body):
                if body.startswith("<g", j):
                    depth += 1
                    j += 2
                elif body.startswith("</g>", j):
                    depth -= 1
                    j += 4
                    if depth == 0:
                        found.append(body[i:j])
                        break
                else:
                    j += 1
            i = j
        else:
            j = body.find("/>", i)
            found.append(body[i : j + 2])
            i = j + 2
    return found


def render_group(head: str, chunks: list[str], width: int) -> Image.Image:
    svg = head + "".join(chunks) + "</g></svg>"
    png = HERE / "_render.png"
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png), output_width=width)
    im = Image.open(png).convert("RGBA")
    plate = Image.new("RGBA", im.size, SAGE)
    im = Image.alpha_composite(plate, im).convert("RGB")
    px = im.load()
    w, h = im.size
    minx, miny, maxx, maxy = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - 232) > 16 or abs(g - 236) > 16 or abs(b - 223) > 16:
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
    pad = 14
    return im.crop((
        max(0, minx - pad),
        max(0, miny - pad),
        min(w, maxx + pad + 1),
        min(h, maxy + pad + 1),
    ))


def row(parts_im: list[Image.Image], gap: int = 28) -> Image.Image:
    height = max(part.height for part in parts_im)
    width = sum(part.width for part in parts_im) + gap * (len(parts_im) - 1)
    canvas = Image.new("RGB", (width, height), SAGE[:3])
    x = 0
    for part in parts_im:
        canvas.paste(part, (x, (height - part.height) // 2))
        x += part.width + gap
    return canvas


def stack(parts_im: list[Image.Image], gap: int = 36) -> Image.Image:
    width = max(part.width for part in parts_im)
    height = sum(part.height for part in parts_im) + gap * (len(parts_im) - 1)
    canvas = Image.new("RGB", (width, height), SAGE[:3])
    y = 0
    for part in parts_im:
        canvas.paste(part, ((width - part.width) // 2, y))
        y += part.height + gap
    return canvas


def main() -> None:
    raw = (HERE / "canton-exchange.svg").read_text()
    head = (
        raw[: raw.find(">") + 1]
        + '<g stroke="#466356" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
    )
    item = parts(raw)
    width = 1400
    sun = render_group(head, [item[1]], width)
    ship = render_group(head, [item[3]], width)
    house = render_group(head, item[4:7], width)
    desk = render_group(head, item[7:16], width)
    chest_l = render_group(head, [item[16]], width)
    chest_r = render_group(head, item[17:19], width)
    plate = stack([row([house, sun]), desk, row([chest_l, chest_r, ship], gap=36)])
    for name in ("h05-past.png", "h05-exchange.png"):
        plate.save(ART / name)
    print("h05", plate.size)


if __name__ == "__main__":
    main()

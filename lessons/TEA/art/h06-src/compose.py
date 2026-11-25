"""Portrait stills for three tea settings.

Chaoshan people and the round table, the Taiwan tea setting, and the
milk-tea cup stay whole at one source scale within each plate. The
hanging-filter drawing is not used.
"""
from pathlib import Path
import re

import cairosvg
from PIL import Image

HERE = Path(__file__).resolve().parent
ART = HERE.parent
CREAM = (250, 245, 232, 255)
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


def render_group(head: str, chunks: list[str], width: int, bg) -> Image.Image:
    svg = head + "".join(chunks) + "</g></svg>"
    png = HERE / "_render.png"
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png), output_width=width)
    im = Image.open(png).convert("RGBA")
    plate = Image.new("RGBA", im.size, bg)
    im = Image.alpha_composite(plate, im).convert("RGB")
    px = im.load()
    w, h = im.size
    minx, miny, maxx, maxy = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - bg[0]) > 16 or abs(g - bg[1]) > 16 or abs(b - bg[2]) > 16:
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
    pad = 16
    return im.crop((
        max(0, minx - pad),
        max(0, miny - pad),
        min(w, maxx + pad + 1),
        min(h, maxy + pad + 1),
    ))


def stack(parts_im: list[Image.Image], gap: int, bg) -> Image.Image:
    width = max(part.width for part in parts_im)
    height = sum(part.height for part in parts_im) + gap * (len(parts_im) - 1)
    canvas = Image.new("RGB", (width, height), bg[:3])
    y = 0
    for part in parts_im:
        canvas.paste(part, ((width - part.width) // 2, y))
        y += part.height + gap
    return canvas


def row(parts_im: list[Image.Image], gap: int, bg) -> Image.Image:
    height = max(part.height for part in parts_im)
    width = sum(part.width for part in parts_im) + gap * (len(parts_im) - 1)
    canvas = Image.new("RGB", (width, height), bg[:3])
    x = 0
    for part in parts_im:
        canvas.paste(part, (x, (height - part.height) // 2))
        x += part.width + gap
    return canvas


def main() -> None:
    width = 1400
    chao = (HERE / "chaoshan-table.svg").read_text()
    head = (
        chao[: chao.find(">") + 1]
        + '<g stroke="#466356" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
    )
    item = parts(chao)
    people = [
        render_group(head, item[3:7], width, CREAM),
        render_group(head, item[7:11], width, CREAM),
        render_group(head, item[11:15], width, CREAM),
    ]
    table = render_group(head, item[15:], width, CREAM)
    chaoshan = stack(people + [table], 28, CREAM)
    chaoshan.save(ART / "h06-chaoshan.png")
    print("chaoshan", chaoshan.size)

    tai = (HERE / "taiwan-tea-art.svg").read_text()
    head = (
        tai[: tai.find(">") + 1]
        + '<g stroke="#466356" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
    )
    item = parts(tai)
    plant = render_group(head, item[10:16], width, CREAM)
    frame = render_group(head, item[16:19], width, CREAM)
    setting = render_group(head, item[1:10], width, CREAM)
    taiwan = stack([row([plant, frame], 48, CREAM), setting], 40, CREAM)

    cup_svg = (HERE / "milk-tea.svg").read_text()
    cup_svg = re.sub(r"<rect\b[^>]*/>", "", cup_svg, count=1)
    png = HERE / "_render.png"
    cairosvg.svg2png(bytestring=cup_svg.encode(), write_to=str(png), output_width=900)
    im = Image.open(png).convert("RGBA")
    plate = Image.new("RGBA", im.size, CREAM)
    im = Image.alpha_composite(plate, im).convert("RGB")
    px = im.load()
    w, h = im.size
    minx, miny, maxx, maxy = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - 250) > 16 or abs(g - 245) > 16 or abs(b - 232) > 16:
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
    cup = im.crop((max(0, minx - 12), max(0, miny - 12), min(w, maxx + 13), min(h, maxy + 13)))
    # Keep the cup's aspect. Size it with the setting, not stretched across it.
    target = int(taiwan.width * 0.62)
    if cup.width != target:
        scale = target / cup.width
        cup = cup.resize((target, max(1, int(round(cup.height * scale)))), Image.Resampling.LANCZOS)
    both = stack([taiwan, cup], 48, CREAM)
    taiwan.save(ART / "h06-taiwan.png")
    both.save(ART / "h06-scripts.png")
    print("taiwan", taiwan.size, "scripts", both.size)


if __name__ == "__main__":
    main()

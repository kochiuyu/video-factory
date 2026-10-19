#!/usr/bin/env python3
"""Print font/ffmpeg status and write a CJK probe PNG."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageDraw, ImageFont

from catalog import out_root
from glyphs import char_ok, face_paths, scan_lesson
from paths import bundled_cjk, bundled_latin, caption_font_name, cjk_regular, extra_cjk, fonts_dir, latin_regular
from validate import load_lesson


def main() -> None:
    print("platform:", sys.platform)
    print("latin   :", latin_regular() or "(none)")
    print("cjk     :", cjk_regular() or "(none)")
    print("cjk extra:", extra_cjk() or "(none)")
    print("stack   :", " | ".join(face_paths()) or "(none)")
    print("bundled cjk  :", bundled_cjk() or "(missing fonts/CJKFallback.ttf)")
    print("bundled latin:", bundled_latin() or "(missing fonts/LatinFallback.ttf)")
    print("fontsdir:", fonts_dir() or "(none)")
    print("caption :", caption_font_name())
    latin, cjk = latin_regular(), cjk_regular()
    if not cjk:
        print("FAIL: no CJK font.")
        raise SystemExit(2)
    img = Image.new("RGB", (960, 280), (247, 244, 238))
    draw = ImageDraw.Draw(img)
    if latin:
        draw.text((40, 40), "Incentives  Ag", font=ImageFont.truetype(latin, 48), fill=(11, 31, 58))
    draw.text((40, 140), "激励，沉没。機會？", font=ImageFont.truetype(cjk, 48), fill=(11, 31, 58))
    out = out_root() / "cjk_probe.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print("probe   :", out)
    print("Open that PNG. Top line English, bottom line Chinese.")
    sample = "Ag / 激励，沉没。機會？！：；、《》「」"
    bad = [ch for ch in sample if ch.strip() and not char_ok(ch)]
    if bad:
        print("FAIL glyphs:", " ".join(f"{ch!r}" for ch in bad))
    else:
        print("glyphs  : mixed Latin/CJK sample ok after sanitize")
    lessons = Path(__file__).resolve().parents[1] / "lessons"
    for path in sorted(lessons.glob("*.yaml")):
        try:
            hits = scan_lesson(load_lesson(path))
        except Exception as exc:
            print("FAIL", path.name, exc)
            continue
        if hits:
            print("FAIL", path.name)
            for h in hits:
                print(" -", h)
        else:
            print("glyphs  :", path.name, "ok")


if __name__ == "__main__":
    main()

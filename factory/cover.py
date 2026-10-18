#!/usr/bin/env python3
"""1920x1080 YouTube covers. Topic, slide language, speech language."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 1920, 1080

NAVY = "#0B1F3A"
GOLD = "#C4A35A"
CREAM = "#F7F4EE"
INK = "#141C28"
WHITE = "#FFFFFF"

LATIN = ROOT / "fonts" / "LatinFallback-Bold.ttf"
CJK = ROOT / "fonts" / "CJKFallback.ttf"

SPEECH = {
    "en": ("SPEECH", "English"),
    "zh": ("语音", "普通话"),
    "zh_cn": ("语音", "普通话"),
    "hk": ("語音", "粵語"),
    "zh_hk": ("語音", "粵語"),
}
SLIDES = {
    "en": ("English", "English"),
    "zh": ("Simplified Chinese", "简体中文"),
    "zh_cn": ("Simplified Chinese", "简体中文"),
    "hk": ("Traditional Chinese", "繁體中文"),
    "zh_hk": ("Traditional Chinese", "繁體中文"),
    "en+zh": ("English + Simplified", "English + 简体"),
    "zh+en": ("Simplified + English", "简体 + English"),
    "en+hk": ("English + Traditional", "English + 繁體"),
    "hk+en": ("Traditional + English", "繁體 + English"),
    "zh+hk": ("Simplified + Traditional", "简体 + 繁體"),
    "hk+zh": ("Traditional + Simplified", "繁體 + 简体"),
    "en+zh_hk": ("English + Traditional", "English + 繁體"),
    "zh_hk+en": ("Traditional + English", "繁體 + English"),
    "zh+zh_hk": ("Simplified + Traditional", "简体 + 繁體"),
    "zh_hk+zh": ("Traditional + Simplified", "繁體 + 简体"),
}


def font(size: int, cjk: bool = False) -> ImageFont.FreeTypeFont:
    path = CJK if cjk else LATIN
    return ImageFont.truetype(str(path), size)


def is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff" or ch in "，。？！、；：「」『』（）"


def has_cjk(text: str) -> bool:
    return any(is_cjk(ch) for ch in text)


def draw_mixed(draw, xy, text, size, fill):
    """Latin glyphs from the Latin face, CJK glyphs from the CJK face."""
    x, y = xy
    run, cjk = "", None
    def flush():
        nonlocal x, run, cjk
        if not run:
            return
        face = font(size, cjk=bool(cjk))
        draw.text((x, y), run, font=face, fill=fill)
        x += draw.textlength(run, font=face)
        run = ""
    for ch in text:
        this = is_cjk(ch)
        if cjk is None:
            cjk = this
        if this != cjk:
            flush()
            cjk = this
        run += ch
    flush()


def wrap(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words = text.split()
    if has_cjk(text) and len(words) == 1:
        lines, cur = [], ""
        for ch in text:
            trial = cur + ch
            if draw.textlength(trial, font=face) <= width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
        return lines or [text]
    lines, cur = [], ""
    for word in words:
        trial = word if not cur else f"{cur} {word}"
        if draw.textlength(trial, font=face) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [text]


def _langs(slide: str) -> list[str]:
    """Ordered slide languages. First is the speech language, second sits below."""
    parts = [p for p in (slide or "en").split("+") if p]
    return parts or ["en"]


def _text(lesson: dict, stem: str, code: str) -> str:
    if code in {"zh", "zh_cn"}:
        return lesson.get(f"{stem}_zh") or ""
    if code in {"hk", "zh_hk"}:
        return lesson.get(f"{stem}_zh_hk") or lesson.get(f"{stem}_zh") or ""
    return lesson.get(f"{stem}_en") or ""


def title_for(lesson: dict, slide: str) -> str:
    """Speech language on top, secondary language underneath, as on the slides."""
    lines = [_text(lesson, "title", code) for code in _langs(slide)]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines) or lesson.get("id") or ""


def _title_blocks(draw, raw: str) -> list[list[tuple[str, int]]]:
    """Fit every word, including the question mark, into two lines."""
    blocks: list[list[tuple[str, int]]] = []
    for block in [ln for ln in raw.split("\n") if ln.strip()]:
        start = 112 if has_cjk(block) else 132
        chosen = None
        for size in range(start, 63, -4):
            face = font(size, cjk=has_cjk(block))
            lines = wrap(draw, block, face, 1680)
            if len(lines) <= 2:
                chosen = [(line, size) for line in lines]
                break
        if chosen is None:
            size = 64
            face = font(size, cjk=has_cjk(block))
            chosen = [(line, size) for line in wrap(draw, block, face, 1680)[:3]]
        if chosen:
            blocks.append(chosen)
    return blocks or [[(raw, 120)]]


def paint(lesson: dict, slide: str, speech: str) -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 22, H), fill=GOLD)

    def course_lines(slide_key: str) -> list[str]:
        lines = []
        for code in _langs(slide_key):
            if code in {"zh", "zh_cn"}:
                lines.append(lesson.get("course_zh") or "商务统计")
            elif code in {"hk", "zh_hk"}:
                lines.append(lesson.get("course_zh_hk") or "商務統計")
            else:
                lines.append((lesson.get("course_en") or "Business Statistics").upper())
        return lines or [(lesson.get("course_en") or "Business Statistics").upper()]

    lines = course_lines(slide)
    size = 36 if len(lines) > 1 else 44
    y0 = 36
    for i, line in enumerate(lines):
        draw.text((80, y0 + i * (size + 8)), line, font=font(size, cjk=has_cjk(line)), fill=GOLD)
    short = lesson.get("id", "")
    short_w = draw.textlength(short, font=font(32))
    draw.text((W - 80 - short_w, 48), short, font=font(32), fill=GOLD)

    blocks = _title_blocks(draw, title_for(lesson, slide))
    mixed = len(blocks) > 1
    gap, rule_gap = 16, 28
    heights = [sum(size + gap for _, size in rows) - gap for rows in blocks]
    block_h = sum(heights) + (rule_gap if mixed else 0)
    y = max(160, (H - block_h) // 2 - 40)
    for bi, rows in enumerate(blocks):
        for line, size in rows:
            face = font(size, cjk=has_cjk(line))
            width = draw.textlength(line, font=face)
            draw.text(((W - width) / 2, y), line, font=face, fill=WHITE)
            y += size + gap
        if mixed and bi == 0:
            rule_w = 1280
            draw.rectangle(((W - rule_w) / 2, y + 2, (W + rule_w) / 2, y + 8), fill=GOLD)
            y += rule_gap
    speech_kind, speech_name = SPEECH.get(speech, ("SPEECH", speech))
    chip_w, chip_h = 720, 96
    x = (W - chip_w) / 2
    chip_y = y + 32
    draw.rounded_rectangle((x, chip_y, x + chip_w, chip_y + chip_h), radius=14, fill=CREAM)
    kind_w = draw.textlength(speech_kind, font=font(28, cjk=has_cjk(speech_kind)))
    name_size = 46
    while name_size > 30 and draw.textlength(speech_name, font=font(name_size, cjk=has_cjk(speech_name))) > chip_w - kind_w - 120:
        name_size -= 2
    name_w = draw.textlength(speech_name, font=font(name_size, cjk=has_cjk(speech_name)))
    row_w = kind_w + 28 + name_w
    left = x + (chip_w - row_w) / 2
    draw.text((left, chip_y + 28), speech_kind, font=font(28, cjk=has_cjk(speech_kind)), fill=GOLD)
    draw.text((left + kind_w + 28, chip_y + 22), speech_name, font=font(name_size, cjk=has_cjk(speech_name)), fill=INK)
    return img


def write_cover(lesson_path: Path, slide: str, speech: str, dest: Path) -> Path:
    lesson = yaml.safe_load(lesson_path.read_text(encoding="utf-8"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    paint(lesson, slide, speech).save(dest, "PNG")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("lesson")
    parser.add_argument("--slide", default="en")
    parser.add_argument("--speech", default="en")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    lesson_path = Path(args.lesson)
    lesson = yaml.safe_load(lesson_path.read_text(encoding="utf-8"))
    name = f"{lesson['id']}_slides-{args.slide}_speech-{args.speech}.png"
    dest = Path(args.out) if args.out else ROOT / "out" / "lessons" / lesson["id"] / "covers" / name
    print(write_cover(lesson_path, args.slide, args.speech, dest))


if __name__ == "__main__":
    main()

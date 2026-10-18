#!/usr/bin/env python3
"""Render language-neutral (or bilingual-label) 1920x1080 beat slides."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from glyphs import font_path_for_char, is_cjk, sanitize
from langs import field, field_native, label_code
from paths import cjk_bold, cjk_regular, latin_bold, latin_regular
from cache import digest_obj, stamp_ok, write_mark
from theme import load_theme

W, H = 1920, 1080
CONTENT_BOTTOM = H - 156

SCALE = {
    "kicker": 28, "footer": 22, "title": 96, "hook": 160, "subtitle": 44,
    "chip": 26, "tag": 26, "index": 28, "body": 56, "claim": 64,
    "formula": 72, "number": 160, "unit": 44, "caption": 44,
}
DUAL = {
    "title": (72, 38), "hook": (100, 50), "claim": (46, 30),
    "body": (44, 32), "caption": (34, 26), "formula": (60, 34), "unit": (36, 26),
}

FONT_LATIN = latin_regular()
FONT_LATIN_B = latin_bold()
FONT_CJK = cjk_regular()
FONT_CJK_B = cjk_bold()

KICKER_I18N = {
    "CONCEPT": {"zh": "概念", "zh_hk": "概念"},
    "DEFINITION": {"zh": "定义", "zh_hk": "定義"},
    "EXAMPLE": {"zh": "例子", "zh_hk": "例子"},
    "TAKEAWAY": {"zh": "要点", "zh_hk": "要點"},
    "PREDICT": {"zh": "预测", "zh_hk": "預測"},
    "RULE": {"zh": "规则", "zh_hk": "規則"},
    "FORMULA": {"zh": "公式", "zh_hk": "公式"},
    "OPEN": {"zh": "开场", "zh_hk": "開場"},
    "CLOSE": {"zh": "收束", "zh_hk": "收束"},
    "FACT": {"zh": "数据", "zh_hk": "數據"},
    "MECHANISM": {"zh": "机制", "zh_hk": "機制"},
    "COMPARE": {"zh": "比较", "zh_hk": "比較"},
    "BUSINESS": {"zh": "企业", "zh_hk": "企業"},
}

STAGEABLE = {
    "definition_card": 2, "formula": 2, "two_column": 3, "example": 3,
    "takeaway": 3, "three_column": 3, "steps": 3, "payoff_matrix": 5,
    "table_grid": 3, "series": 3, "schematic_chart": 3, "dag": 3, "pair": 3, "pair_chart": 3, "pair_box": 3, "pair_slope": 3, "redraw": 3, "turns": 3, "shrink": 3, "mix": 3, "coin": 3,
}
MIN_STAGE_BEAT = 5.0
MIN_SLICE = 1.2
LAYOUT_VERSION = "2026-10-15-series-reveal"


def lesson_stamp(lesson, theme, code, second, stage_cards) -> str:
    theme_id = (theme or {}).get("id") if isinstance(theme, dict) else theme
    payload = {
        "v": LAYOUT_VERSION,
        "id": lesson.get("id"),
        "code": code,
        "second": second,
        "stage": bool(stage_cards),
        "theme": theme_id,
        "beats": digest_obj(lesson.get("beats") or []),
    }
    return digest_obj(payload)


def stamp_matches(folder: Path, stamp: str) -> bool:
    mark = folder / ".stamp"
    return mark.is_file() and mark.read_text(encoding="utf-8").strip() == stamp


def write_stamp(folder: Path, stamp: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".stamp").write_text(stamp + "\n", encoding="utf-8")


def beat_stamp(beat: dict, code: str, second, theme, stage) -> str:
    return digest_obj({"v": LAYOUT_VERSION, "beat": beat, "code": code, "second": second, "stage": stage})


def list_slide_pngs(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.png") if "_s" not in p.stem and "_c" not in p.stem)


def resolve_kicker(beat: dict, code: str) -> str:
    raw = field_native(beat, "kicker", code) or beat.get("kicker") or ""
    raw = sanitize(raw or "")
    if raw in KICKER_I18N:
        return KICKER_I18N[raw].get(code, raw)
    return raw


_font_cache: dict = {}


def _font(path, size: int) -> ImageFont.FreeTypeFont:
    key = (str(path), int(size))
    hit = _font_cache.get(key)
    if hit is not None:
        return hit
    try:
        font = ImageFont.truetype(str(path), int(size)) if path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def font_for(text: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    if any(is_cjk(ch) for ch in (text or "")):
        return _font(FONT_CJK_B if bold else FONT_CJK, size)
    return _font(FONT_LATIN_B if bold else FONT_LATIN, size)


def font_for_char(ch: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = font_path_for_char(ch, bold=bold)
    return _font(path, size) if path else font_for(ch, size, bold=bold)


def _script_chunks(text: str) -> list[tuple[str, str]]:
    raw = sanitize(text or "")
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(raw):
        if raw[i] == "_" and i + 1 < len(raw):
            j = i + 1
            buf = []
            while j < len(raw) and raw[j] != "_":
                buf.append(raw[j]); j += 1
            if j < len(raw) and raw[j] == "_" and buf:
                out.append(("sub", "".join(buf))); i = j + 1; continue
        out.append(("norm", raw[i])); i += 1
    return out


def _match_cjk_digit(ch: str, text: str) -> str:
    """In a Chinese line, digits use the CJK em box so they match the characters."""
    if ch in "0123456789" and any(is_cjk(c) for c in (text or "")):
        return chr(ord(ch) + 0xFEE0)
    return ch


def mixed_length(draw: ImageDraw.ImageDraw, text: str, size: int, bold: bool = False) -> float:
    width = 0.0
    for kind, chunk in _script_chunks(text):
        sub = max(10, int(size * 0.62)) if kind == "sub" else size
        for ch in chunk:
            if ch in "\n\r":
                continue
            shown = _match_cjk_digit(ch, text)
            width += draw.textlength(shown, font=font_for_char(shown, sub, bold))
    return width


def draw_mixed(draw, xy, text, size, fill, bold: bool = False) -> None:
    x, y = xy
    for kind, chunk in _script_chunks(text):
        if kind == "sub":
            sub = max(10, int(size * 0.62))
            yy = y + size * 0.32
            for ch in chunk:
                if ch in "\n\r":
                    continue
                shown = _match_cjk_digit(ch, text)
                font = font_for_char(shown, sub, bold)
                draw.text((x, yy), shown, font=font, fill=fill)
                x += draw.textlength(shown, font=font)
            continue
        for ch in chunk:
            if ch in "\n\r":
                continue
            shown = _match_cjk_digit(ch, text)
            font = font_for_char(shown, size, bold)
            draw.text((x, y), shown, font=font, fill=fill)
            x += draw.textlength(shown, font=font)


def field2(obj: dict, stem: str, code: str, second: str | None = None) -> str:
    primary = field_native(obj, stem, code) or (field(obj, stem, code) if code == "en" else "")
    if not second or second == code:
        return primary
    other = field_native(obj, stem, second) or (field(obj, stem, second) if second == "en" else "")
    if not other or other == primary:
        return primary
    if not primary:
        return other
    return primary + "\n" + other


_CJK_NO_START = set("，。、．·？！；：…—～％‰°℃」』）】》〉’”" + ",.;:!?)]}%\"'")
_CJK_NO_END = set("「『（【《〈“‘([{")


def _cjk_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if ch in _CJK_NO_START and buf:
            buf += ch
            tokens.append(buf); buf = ""
        elif ch in _CJK_NO_END:
            if buf:
                tokens.append(buf)
            buf = ch
        else:
            if buf and buf[-1] in _CJK_NO_END:
                buf += ch
            else:
                if buf:
                    tokens.append(buf)
                buf = ch
    if buf:
        tokens.append(buf)
    return tokens


def wrap(draw, text: str, font, max_w: int, bold: bool = False) -> list[str]:
    text = sanitize(text or "")
    if not text:
        return []
    if "\n" in text:
        lines: list[str] = []
        for part in text.split("\n"):
            lines.extend(wrap(draw, part, font, max_w, bold=bold) or ([part] if part else []))
        return lines
    size = int(getattr(font, "size", 32) or 32)
    if any(is_cjk(ch) for ch in text):
        lines: list[str] = []
        cur = ""
        for tok in _cjk_tokens(text):
            trial = cur + tok
            if cur and mixed_length(draw, trial, size, bold) > max_w:
                lines.append(cur); cur = tok
            else:
                cur = trial
        if cur:
            lines.append(cur)
        return lines or [text]
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if cur and mixed_length(draw, trial, size, bold) > max_w:
            lines.append(cur); cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [text]


def fit_font(draw, text, size, max_w, bold=True, min_size=28, max_lines=3, max_h=None):
    text = sanitize(text or "")
    size = max(12, int(size))
    floor = max(18, int(min_size))
    best = font_for(text, floor, bold=bold)
    while size >= floor:
        font = font_for(text, size, bold=bold)
        lines = wrap(draw, text, font, max_w, bold=bold)
        widest = max((mixed_length(draw, ln, size, bold) for ln in lines), default=0)
        tall = int(size * 1.18) * max(1, len(lines))
        if widest <= max_w and len(lines) <= max_lines and (max_h is None or tall <= max_h):
            return font
        best = font
        size -= 2
    return best


def new_canvas(theme: dict):
    img = Image.new("RGB", (W, H), theme["bg"])
    draw = ImageDraw.Draw(img)
    if theme.get("blobs"):
        draw.ellipse([-80, 720, 420, 1220], fill=theme["wash"])
        draw.ellipse([1480, -180, 2100, 460], fill=theme["wash2"])
    if theme.get("corner"):
        draw.polygon([(W - 220, 0), (W, 0), (W, 220)], fill=theme["gold"])
    draw.rectangle([0, 0, 18, H], fill=theme["navy"])
    draw.rectangle([W - 18, 0, W, H], fill=theme["navy"])
    draw._vf_img = img
    return img, draw


def _split_pair(text: str) -> tuple[str, str]:
    raw = sanitize(text or "").strip()
    if "\n" not in raw:
        return raw, ""
    a, b = raw.split("\n", 1)
    return a.strip(), b.strip()


def _mostly_cjk(text: str) -> bool:
    chars = [ch for ch in text or "" if not ch.isspace()]
    if not chars:
        return False
    return sum(1 for ch in chars if "\u4e00" <= ch <= "\u9fff") * 3 >= len(chars)


def _center(draw, box, text, font, fill, bold: bool = True):
    x0, y0, x1, y1 = box
    max_w = max(40, int(x1 - x0))
    box_h = max(40, int(y1 - y0))
    primary, secondary = _split_pair(text)
    if not secondary:
        size = int(getattr(font, "size", SCALE["claim"]) or SCALE["claim"])
        lines = wrap(draw, primary, font, max_w, bold=bold) or [sanitize(primary or "")]
        line_h = int(size * 1.18)
        total = line_h * len(lines)
        ty = y0 + max(0, (box_h - total) / 2)
        for ln in lines:
            if ty + line_h > y1 + 4:
                break
            tw = mixed_length(draw, ln, size, bold)
            draw_mixed(draw, (x0 + (max_w - tw) / 2, ty), ln, size, fill, bold)
            ty += line_h
        return
    given = int(getattr(font, "size", 24) or 24)
    main = min(given, DUAL["claim"][0])
    sub = max(18, min(DUAL["claim"][1], int(main * 0.72)))
    p_font = fit_font(draw, primary, main, max_w, bold=True, min_size=24, max_lines=2)
    main = int(getattr(p_font, "size", main) or main)
    p_lines = wrap(draw, primary, p_font, max_w, bold=True) or [primary]
    s_font = fit_font(draw, secondary, sub, max_w, bold=False, min_size=18, max_lines=2)
    sub = int(getattr(s_font, "size", sub) or sub)
    s_lines = wrap(draw, secondary, s_font, max_w, bold=False) or [secondary]
    block = int(main * 1.12) * len(p_lines) + 6 + int(sub * 1.08) * len(s_lines)
    ty = y0 + max(0, (box_h - block) / 2)
    for ln in p_lines:
        tw = mixed_length(draw, ln, main, True)
        draw_mixed(draw, (x0 + (max_w - tw) / 2, ty), ln, main, fill, True)
        ty += int(main * 1.12)
    ty += 6
    gold = fill
    for ln in s_lines:
        tw = mixed_length(draw, ln, sub, False)
        draw_mixed(draw, (x0 + (max_w - tw) / 2, ty), ln, sub, gold, False)
        ty += int(sub * 1.08)


def draw_kicker(draw, kicker: str, theme: dict) -> None:
    if not kicker:
        return
    label = kicker.upper() if kicker.isascii() else kicker
    size = 22 if len(label) > 18 else SCALE["kicker"]
    tw = mixed_length(draw, label, size, bold=True)
    left, top, h = 64, 40, 56
    dot, gap, pad_l, pad_r = 18, 12, 16, 22
    text_x = left + pad_l + dot + gap
    right = min(W - 80, text_x + tw + pad_r)
    draw.rounded_rectangle([left, top, right, top + h], radius=h // 2, fill=theme["navy"])
    cy = top + h / 2
    draw.ellipse([left + pad_l, cy - dot / 2, left + pad_l + dot, cy + dot / 2], fill=theme["gold"])
    draw_mixed(draw, (text_x, top + 14), label, size, theme["bg"], bold=True)


def draw_footer(draw, title: str, index: int, n: int, theme: dict) -> None:
    label = sanitize(title or "")
    gap, r = 18, 8
    total = n * (2 * r) + max(0, n - 1) * gap
    dots_left = W - 64 - total
    y_dots = H - 118
    max_w = max(200, dots_left - 80)
    size = SCALE["footer"]
    while size >= 16 and mixed_length(draw, label, size, False) > max_w:
        size -= 1
    if mixed_length(draw, label, size, False) > max_w:
        while label and mixed_length(draw, label + "…", size, False) > max_w:
            label = label[:-1]
        label = (label + "…") if label else ""
    if label:
        draw_mixed(draw, (64, H - 128), label, size, theme["muted"], bold=False)
    x = dots_left
    for i in range(1, n + 1):
        box = [x, y_dots - r, x + 2 * r, y_dots + r]
        if i == index:
            draw.ellipse(box, fill=theme["gold"])
        else:
            draw.ellipse(box, outline=theme["muted"], width=2)
        x += 2 * r + gap


def _line_factor(text: str) -> float:
    """CJK fills the em box. Latin does not, so the same size needs less band."""
    return 1.28 if any(is_cjk(ch) for ch in (text or "")) else 1.08


def draw_title(draw, title: str, theme: dict, y: int = 112) -> int:
    max_w = W - 200
    primary, secondary = _split_pair(title)
    bar_gap = 22
    if not secondary:
        cap = 84 if any(is_cjk(ch) for ch in primary) else SCALE["title"]
        f = fit_font(draw, primary, cap, max_w, bold=True, min_size=48, max_lines=1)
        size = int(getattr(f, "size", cap) or cap)
        lines = (wrap(draw, primary, f, max_w, bold=True) or [sanitize(primary)])[:1]
        line_h = int(size * _line_factor(primary))
        band_h = max(132, 24 + line_h + bar_gap)
        sub_lines, sub_size = [], 0
    else:
        main, sub = DUAL["title"]
        pf = fit_font(draw, primary, main, max_w, bold=True, min_size=40, max_lines=1)
        main = int(getattr(pf, "size", main) or main)
        lines = (wrap(draw, primary, pf, max_w, bold=True) or [sanitize(primary)])[:1]
        sub_cap = min(sub, int(main * 0.48))
        sf = fit_font(draw, secondary, sub_cap, max_w, bold=False, min_size=22, max_lines=1)
        sub_size = int(getattr(sf, "size", sub_cap) or sub_cap)
        sub_lines = (wrap(draw, secondary, sf, max_w, bold=False) or [sanitize(secondary)])[:1]
        size = main
        line_h = int(main * _line_factor(primary))
        sub_h = int(sub_size * _line_factor(secondary))
        band_h = max(168, 20 + line_h + 8 + sub_h + bar_gap)
    draw.rectangle([0, y, W, y + band_h], fill=theme["navy"])
    draw.rectangle([0, y, 14, y + band_h], fill=theme["gold"])
    draw.rectangle([64, y + band_h - 14, 280, y + band_h - 8], fill=theme["gold"])
    if secondary:
        block = line_h + 8 + int(sub_size * _line_factor(secondary))
        yy = y + max(16, (band_h - bar_gap - block) // 2)
        for ln in lines:
            draw_mixed(draw, (64, yy), ln, size, theme["bg"], bold=True)
            yy += line_h
        yy += 8
        for ln in sub_lines:
            draw_mixed(draw, (64, yy), ln, sub_size, theme["gold"], bold=False)
    else:
        yy = y + max(16, (band_h - bar_gap - line_h) // 2)
        for ln in lines:
            draw_mixed(draw, (64, yy), ln, size, theme["bg"], bold=True)
    return y + band_h + 20


def _tag(draw, x, y, text, theme) -> None:
    draw.text((x, y), text, font=font_for(text, SCALE["tag"], bold=True), fill=theme["gold"])


def _fill_h(top: int, floor: int = 280) -> int:
    return max(floor, CONTENT_BOTTOM - top)


def _panel(draw, box, fill, theme, accent: bool = True) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle([x0, y0, x1, y1], radius=22, fill=fill)
    if accent:
        draw.rectangle([x0, y0, x0 + 14, y1], fill=theme["gold"])


def _show(stage, need: int) -> bool:
    return stage is None or stage == 0 or stage >= need


def render_title_card(draw, beat, lesson, code, theme, second=None) -> None:
    title = field2(beat, "title", code, second) or field2(lesson, "title", code, second)
    primary, secondary = _split_pair(title)
    max_w = W - 200
    kicker = resolve_kicker(beat, code)
    if second:
        other = resolve_kicker(beat, second)
        if other and other != kicker:
            kicker = f"{kicker}  {other}" if kicker else other
    kicker_label = ""
    ksize = 0
    if kicker:
        kicker_label = kicker.upper() if kicker.isascii() else kicker
        ksize = 24 if len(kicker_label) > 16 else SCALE["kicker"]
    # Measure the block, then center it vertically on the slide.
    if secondary:
        main, sub = DUAL["hook"]
        pf = fit_font(draw, primary, main, max_w, True, 64, 2)
        main = int(getattr(pf, "size", main) or main)
        p_lines = wrap(draw, primary, pf, max_w, True) or [primary]
        sf = fit_font(draw, secondary, sub, max_w, False, 32, 2)
        sub = int(getattr(sf, "size", sub) or sub)
        s_lines = wrap(draw, secondary, sf, max_w, False) or [secondary]
        block = 0
        if kicker_label:
            block += 56
        block += int(main * 1.08) * len(p_lines) + 12
        block += int(sub * 1.06) * len(s_lines)
        block += 36  # gold bar
        top = max(160, (H - block) // 2 - 20)
        if kicker_label:
            tw = mixed_length(draw, kicker_label, ksize, True)
            draw_mixed(draw, ((W - tw) / 2, top), kicker_label, ksize, theme["muted"], True)
            top += 56
        for ln in p_lines:
            tw = mixed_length(draw, ln, main, True)
            draw_mixed(draw, ((W - tw) / 2, top), ln, main, theme["navy"], True)
            top += int(main * 1.08)
        top += 12
        for ln in s_lines:
            tw = mixed_length(draw, ln, sub, False)
            draw_mixed(draw, ((W - tw) / 2, top), ln, sub, theme["muted"], False)
            top += int(sub * 1.06)
    else:
        font = fit_font(draw, primary, SCALE["hook"], max_w, True, 88, 3)
        size = int(getattr(font, "size", SCALE["hook"]) or SCALE["hook"])
        lines = wrap(draw, primary, font, max_w, True) or [primary]
        block = 0
        if kicker_label:
            block += 56
        block += int(size * 1.08) * len(lines)
        block += 36  # gold bar
        top = max(160, (H - block) // 2 - 20)
        if kicker_label:
            tw = mixed_length(draw, kicker_label, ksize, True)
            draw_mixed(draw, ((W - tw) / 2, top), kicker_label, ksize, theme["muted"], True)
            top += 56
        for ln in lines:
            tw = mixed_length(draw, ln, size, True)
            draw_mixed(draw, ((W - tw) / 2, top), ln, size, theme["navy"], True)
            top += int(size * 1.08)
    draw.rectangle([(W - 140) / 2, top + 18, (W + 140) / 2, top + 26], fill=theme["gold"])



def _formula_lines(text: str) -> list[str]:
    """Stack a pair of equations. Do not wrap one fence onto the next."""
    raw = sanitize(text or "").strip()
    if not raw:
        return []
    if "\n" in raw:
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    for sep in ("；", ";"):
        if sep not in raw:
            continue
        parts = [part.strip(" ;；") for part in raw.split(sep)]
        parts = [part for part in parts if part]
        if len(parts) >= 2 and all("=" in part for part in parts):
            return parts
    return [raw]


def _paint_formula_lines(draw, box, lines: list[str], fill) -> None:
    x0, y0, x1, y1 = box
    max_w = max(40, int(x1 - x0))
    box_h = max(40, int(y1 - y0))
    gap = 28
    size = SCALE["formula"]
    fonts = []
    while size >= 36:
        fonts = [fit_font(draw, ln, size, max_w, True, 36, 2) for ln in lines]
        size = min(int(getattr(font, "size", size) or size) for font in fonts)
        line_h = int(size * 1.2)
        if line_h * len(lines) + gap * (len(lines) - 1) <= box_h:
            break
        size -= 4
    line_h = int(size * 1.2)
    total = line_h * len(lines) + gap * (len(lines) - 1)
    ty = y0 + max(0, (box_h - total) / 2)
    for ln in lines:
        tw = mixed_length(draw, ln, size, True)
        draw_mixed(draw, (x0 + (max_w - tw) / 2, ty), ln, size, fill, True)
        ty += line_h + gap


def render_definition(draw, beat, code, y, theme, stage=None, second=None) -> None:
    body = field_native(beat, "formula", code) or beat.get("formula") or field_native(beat, "title", code) or ""
    gloss = field_native(beat, "gloss", code) or ""
    other = field_native(beat, "formula", second) if second else ""
    if other == body:
        other = ""
    gloss_other = field_native(beat, "gloss", second) if second else ""
    box_y = y + 12
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "DEFINITION", "zh": "定义", "zh_hk": "定義"}.get(code, "DEFINITION")
    if second:
        ot = {"en": "DEFINITION", "zh": "定义", "zh_hk": "定義"}.get(second)
        if ot and ot != tag:
            tag = f"{tag}  {ot}"
    _tag(draw, 108, box_y + 28, tag, theme)
    reveal = bool(gloss) and (second or _show(stage, 2))
    gloss_band = 100 if reveal else 28
    inner_bottom = box_y + box_h - gloss_band
    text = body
    if second and other:
        text = body + "\n" + other
    tex, tex2 = localized_tex(beat, code, second)
    try:
        from mathtex import looks_like_tex
    except Exception:
        looks_like_tex = lambda _s: False  # noqa: E731
    if not tex and looks_like_tex(body):
        tex = body
    if not tex2 and second and other and looks_like_tex(other):
        tex2 = other
    painted = False
    # A two-equation card should stack. One formula_tex line would wrap the pair again.
    if len(_formula_lines(text)) >= 2:
        tex, tex2 = "", ""
    if _show(stage, 1) and (tex or tex2):
        try:
            from mathtex import paste_math

            box = (100, box_y + 70, W - 100, inner_bottom)
            if tex and tex2:
                mid = (box[1] + box[3]) // 2
                painted = paste_math(draw, (box[0], box[1], box[2], mid - 6), tex, theme["bg"], 44)
                painted = paste_math(draw, (box[0], mid + 6, box[2], box[3]), tex2, theme["bg"], 36) or painted
            elif tex:
                painted = paste_math(draw, box, tex, theme["bg"], 48)
        except Exception:
            painted = False
    if _show(stage, 1) and text and not painted:
        lines = _formula_lines(text)
        box = (100, box_y + 70, W - 100, inner_bottom)
        if len(lines) >= 2:
            _paint_formula_lines(draw, box, lines, theme["bg"])
        else:
            ff = fit_font(draw, text, SCALE["formula"], W - 220, True, 36, 4, max(80, inner_bottom - box_y - 80))
            _center(draw, box, text, ff, theme["bg"])
    if reveal:
        gtxt = gloss if not (second and gloss_other) else gloss + "\n" + gloss_other
        gf = fit_font(draw, gtxt, 36, W - 240, False, 24, 2, 80)
        _center(draw, (100, inner_bottom + 6, W - 100, box_y + box_h - 18), gtxt, gf, theme["gold"], bold=False)


def render_two_column(draw, beat, code, y, theme, stage=None, second=None) -> None:
    left = field2(beat, "left", code, second) if _show(stage, 2) else ""
    right = field2(beat, "right", code, second) if _show(stage, 3) else ""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    mid = W // 2
    draw.rounded_rectangle([64, box_y, mid - 40, box_y + box_h], radius=24, fill=theme["navy"])
    draw.rounded_rectangle([mid + 40, box_y, W - 64, box_y + box_h], radius=24, fill=theme["emerald"])
    if _show(stage, 3):
        badge = [mid - 44, box_y + box_h // 2 - 44, mid + 44, box_y + box_h // 2 + 44]
        draw.ellipse(badge, fill=theme["gold"])
        vf = _font(FONT_LATIN_B, 28)
        tw = draw.textlength("VS", font=vf)
        draw.text((mid - tw / 2, box_y + box_h // 2 - 16), "VS", font=vf, fill=theme["navy"])
    if left:
        lf = fit_font(draw, left, SCALE["claim"], mid - 160, True, 32, 4, box_h - 80)
        _center(draw, (96, box_y + 36, mid - 64, box_y + box_h - 36), left, lf, theme["bg"])
    if right:
        rf = fit_font(draw, right, SCALE["claim"], mid - 160, True, 32, 4, box_h - 80)
        _center(draw, (mid + 64, box_y + 36, W - 96, box_y + box_h - 36), right, rf, theme["white"])


def render_takeaway(draw, beat, code, y, theme, stage=None, second=None) -> None:
    q1 = field2(beat, "q1", code, second)
    q2 = field2(beat, "q2", code, second)
    questions = [q for q in (q1, q2) if q]
    box_y = y + 8
    gap = 18
    available = max(200, CONTENT_BOTTOM - box_y)
    hbox = max(160, (available - gap * (len(questions) - 1)) // max(1, len(questions)))
    fills = (theme["navy"], theme["emerald"])
    for i, q in enumerate(questions):
        top = box_y + i * (hbox + gap)
        draw.rounded_rectangle([64, top, W - 64, top + hbox], radius=22, fill=fills[i % 2])
        draw.ellipse([96, top + hbox // 2 - 42, 180, top + hbox // 2 + 42], fill=theme["gold"])
        nf = _font(FONT_LATIN_B, 32)
        tw = draw.textlength(str(i + 1), font=nf)
        draw.text((138 - tw / 2, top + hbox // 2 - 20), str(i + 1), font=nf, fill=theme["navy"])
        if q and _show(stage, 2 if i == 0 else 3):
            qf = fit_font(draw, q, 64, W - 320, True, 32, 3 if hbox >= 200 else 2, hbox - 36)
            _center(draw, (200, top + 18, W - 80, top + hbox - 18), q, qf, theme["white"])


def localized_tex(beat, code, second=None):
    try:
        from mathtex import tex_field
        main = tex_field(beat, code)
        other = tex_field(beat, second) if second else ""
        if other == main:
            other = ""
        return main, other
    except Exception:
        return "", ""


def render_formula(draw, beat, code, y, theme, stage=None, second=None) -> None:
    render_definition(draw, beat, code, y, theme, stage=stage, second=second)


def _split_dual(text: str) -> tuple[str, str]:
    raw = sanitize(text or "").strip()
    if "\n" in raw:
        a, b = raw.split("\n", 1)
        return a.strip(), b.strip()
    return raw, ""


def _pair_tag(primary, second, other) -> str:
    if second and other and other != primary:
        return f"{primary}  {other}"
    return primary


def _paint_example_card(draw, box, fill, tag, primary, secondary, theme, show_body):
    x0, y0, x1, y1 = box
    _panel(draw, box, fill, theme)
    _tag(draw, x0 + 44, y0 + 20, tag, theme)
    if not show_body or not primary:
        return
    inner_l, max_w = x0 + 44, x1 - 36 - (x0 + 44)
    body_top, body_bot = y0 + 58, y1 - 24
    max_h = max(48, body_bot - body_top)
    if secondary:
        pf = fit_font(draw, primary, 40, max_w, True, 26, 4, max(40, max_h - 36))
        p_size = int(getattr(pf, "size", 40) or 40)
        p_lines = wrap(draw, primary, pf, max_w, True) or [primary]
        sf = fit_font(draw, secondary, 28, max_w, False, 22, 3, 84)
        s_size = int(getattr(sf, "size", 28) or 28)
        s_lines = wrap(draw, secondary, sf, max_w, False) or [secondary]
        block = int(p_size * 1.12) * len(p_lines) + 6 + int(s_size * 1.08) * len(s_lines)
        yy = body_top + max(0, (max_h - block) // 2)
        for ln in p_lines:
            if yy + int(p_size * 1.05) > body_bot:
                break
            draw_mixed(draw, (inner_l, yy), ln, p_size, theme["bg"], True)
            yy += int(p_size * 1.12)
        yy += 6
        for ln in s_lines:
            if yy + int(s_size * 1.05) > body_bot + 4:
                break
            draw_mixed(draw, (inner_l, yy), ln, s_size, theme["gold"], False)
            yy += int(s_size * 1.08)
        return
    pf = fit_font(draw, primary, 48, max_w, True, 28, 4, max_h)
    p_size = int(getattr(pf, "size", 48) or 48)
    p_lines = wrap(draw, primary, pf, max_w, True) or [primary]
    block = int(p_size * 1.14) * len(p_lines)
    yy = body_top + max(0, (max_h - block) // 2)
    for ln in p_lines:
        if yy + int(p_size * 1.05) > body_bot:
            break
        draw_mixed(draw, (inner_l, yy), ln, p_size, theme["bg"], True)
        yy += int(p_size * 1.14)


def render_example(draw, beat, code, y, theme, stage=None, second=None) -> None:
    setup = field2(beat, "setup", code, second) or field2(beat, "left", code, second)
    result = field2(beat, "result", code, second) or field2(beat, "right", code, second)
    setup_p, setup_s = _split_dual(setup)
    result_p, result_s = _split_dual(result)
    tags = {"en": ("SETUP", "RESULT"), "zh": ("设定", "结果"), "zh_hk": ("設定", "結果")}
    lab_s, lab_r = tags.get(code, tags["en"])
    other_s, other_r = tags.get(second or "", ("", ""))
    box_y = y + 8
    gap = 18
    box_h = max(176, (CONTENT_BOTTOM - box_y - gap) // 2)
    _paint_example_card(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], _pair_tag(lab_s, second, other_s), setup_p, setup_s, theme, _show(stage, 2))
    top = box_y + box_h + gap
    _paint_example_card(draw, (64, top, W - 64, top + box_h), theme["emerald"], _pair_tag(lab_r, second, other_r), result_p, result_s, theme, _show(stage, 3))


def render_three_column(draw, beat, code, y, theme, stage=None, second=None) -> None:
    cols = [field2(beat, f"col{i}", code, second) for i in (1, 2, 3)]
    if not any(cols):
        cols = [field2(beat, "left", code, second), field2(beat, "mid", code, second), field2(beat, "right", code, second)]
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    gap = 28
    width = (W - 128 - 2 * gap) // 3
    fills = (theme["navy"], theme["ink"], theme["emerald"])
    for i, text in enumerate(cols):
        x0 = 64 + i * (width + gap)
        draw.rounded_rectangle([x0, box_y, x0 + width, box_y + box_h], radius=20, fill=fills[i % 3])
        draw.ellipse([x0 + width / 2 - 28, box_y + 24, x0 + width / 2 + 28, box_y + 80], fill=theme["gold"])
        nf = _font(FONT_LATIN_B, SCALE["index"])
        tw = draw.textlength(str(i + 1), font=nf)
        draw.text((x0 + width / 2 - tw / 2, box_y + 38), str(i + 1), font=nf, fill=theme["navy"])
        if text and _show(stage, i + 1):
            lf = fit_font(draw, text, SCALE["claim"], width - 48, True, 28, 5, box_h - 120)
            _center(draw, (x0 + 20, box_y + 100, x0 + width - 20, box_y + box_h - 24), text, lf, theme["white"])


def render_big_number(draw, beat, code, y, theme, stage=None, second=None) -> None:
    number = field2(beat, "number", code, second) or field2(beat, "formula", code, second)
    unit = field2(beat, "unit", code, second)
    cap = field2(beat, "caption", code, second) or field2(beat, "gloss", code, second)
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "KEY NUMBER", "zh": "关键数字", "zh_hk": "關鍵數字"}.get(code, "KEY NUMBER")
    _tag(draw, 108, box_y + 28, tag, theme)
    nf = fit_font(draw, number or "", SCALE["number"], W - 240, True, 64, 1)
    _center(draw, (100, box_y + 80, W - 100, box_y + box_h - 160), number or "", nf, theme["bg"])
    if unit:
        uf = fit_font(draw, unit, SCALE["unit"], W - 240, True, 28, 1)
        _center(draw, (100, box_y + box_h - 150, W - 100, box_y + box_h - 90), unit, uf, theme["gold"])
    if cap:
        cf = fit_font(draw, cap, SCALE["caption"], W - 240, False, 24, 2)
        _center(draw, (100, box_y + box_h - 88, W - 100, box_y + box_h - 24), cap, cf, theme["white"], bold=False)


def _agenda_items(beat, code, second=None) -> list[str]:
    items = []
    for i in range(1, 6):
        line = field2(beat, f"item{i}", code, second)
        if line:
            items.append(line)
    return items


def render_module_open(draw, beat, lesson, code, theme, second=None) -> None:
    title = field2(beat, "title", code, second) or field2(lesson, "title", code, second)
    primary, secondary = _split_pair(title)
    kicker = field2(beat, "kicker", code, second) or {"en": "OPEN", "zh": "开场", "zh_hk": "開場"}.get(code, "OPEN")
    draw_mixed(draw, (80, 80), kicker, SCALE["kicker"], theme["gold"], True)
    top = 160
    font = fit_font(draw, primary, 92, W - 200, True, 56, 2)
    size = int(getattr(font, "size", 92) or 92)
    for ln in wrap(draw, primary, font, W - 200, True) or [primary]:
        draw_mixed(draw, (80, top), ln, size, theme["navy"], True)
        top += int(size * 1.08)
    if secondary:
        draw_mixed(draw, (80, top + 8), secondary.split("\n", 1)[0], 36, theme["muted"], False)
        top += 52
    for i, item in enumerate(_agenda_items(beat, code, second), start=1):
        main, sub = _split_pair(item)
        yy = top + 16
        draw_mixed(draw, (80, yy), f"{i:02d}  {main}", 36, theme["navy"], True)
        if sub:
            draw_mixed(draw, (148, yy + 40), sub, 26, theme["muted"], False)
            top = yy + 78
        else:
            top = yy + 52


def render_module_close(draw, beat, lesson, code, theme, second=None) -> None:
    title = field2(beat, "title", code, second) or field2(lesson, "title", code, second)
    claim = field2(beat, "claim", code, second)
    nxt = field2(beat, "next", code, second)
    kicker = field2(beat, "kicker", code, second) or {"en": "CLOSE", "zh": "收束", "zh_hk": "收束"}.get(code, "CLOSE")
    draw_mixed(draw, (80, 80), kicker, SCALE["kicker"], theme["gold"], True)
    primary, secondary = _split_pair(title)
    font = fit_font(draw, primary, 92, W - 200, True, 56, 2)
    size = int(getattr(font, "size", 92) or 92)
    top = 160
    for ln in wrap(draw, primary, font, W - 200, True) or [primary]:
        draw_mixed(draw, (80, top), ln, size, theme["navy"], True)
        top += int(size * 1.08)
    if claim:
        _panel(draw, (64, top + 30, W - 64, top + 220), theme["navy"], theme)
        cf = fit_font(draw, claim, 52, W - 180, True, 32, 3)
        _center(draw, (100, top + 50, W - 100, top + 200), claim, cf, theme["white"])
        top += 240
    if nxt:
        label = field2(beat, "next_label", code, second) or {"en": "NEXT", "zh": "下一讲", "zh_hk": "下一講"}.get(code, "NEXT")
        main, sub = _split_pair(nxt)
        yy = min(top + 20, 940)
        draw_mixed(draw, (80, yy), f"{label}  {main}", 32, theme["muted"], False)
        if sub:
            draw_mixed(draw, (80, yy + 40), sub, 26, theme["muted"], False)


def render_steps(draw, beat, code, y, theme, stage=None, second=None) -> None:
    items = []
    for i in range(1, 7):
        text = field2(beat, f"step{i}", code, second)
        ex = field2(beat, f"ex{i}", code, second)
        if text:
            items.append((text, ex))
    if len(items) <= 3:
        steps = [text for text, _ex in items] + [""] * (3 - len(items))
        box_y = y + 8
        box_h = _fill_h(box_y, 360)
        gap = 28
        width = (W - 128 - 2 * gap) // 3
        fills = (theme["navy"], theme.get("panel") or theme["navy"], theme["emerald"])
        for i, text in enumerate(steps):
            x0 = 64 + i * (width + gap)
            draw.rounded_rectangle([x0, box_y, x0 + width, box_y + box_h], radius=20, fill=fills[i % 3])
            draw.rectangle([x0, box_y, x0 + 14, box_y + box_h], fill=theme["gold"])
            if text and _show(stage, i + 1):
                lf = fit_font(draw, text, SCALE["claim"], width - 48, True, 28, 5, box_h - 60)
                _center(draw, (x0 + 28, box_y + 36, x0 + width - 20, box_y + box_h - 24), text, lf, theme["white"])
        return
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    gap = 12
    row_h = (box_h - 28 - gap * (len(items) - 1)) // len(items)
    for i, (text, ex) in enumerate(items):
        y0 = box_y + 14 + i * (row_h + gap)
        show = _show(stage, i + 1)
        fill = theme["gold"] if show and stage not in (None, 0) and int(stage) == i + 1 else theme.get("panel") or theme["navy"]
        ink = theme["navy"] if fill == theme["gold"] else theme["white"]
        draw.rounded_rectangle([88, y0, W - 88, y0 + row_h], radius=16, fill=fill)
        badge = str(i + 1)
        draw.ellipse([100, y0 + row_h / 2 - 22, 144, y0 + row_h / 2 + 22], fill=theme["gold"] if fill != theme["gold"] else theme["navy"])
        bf = fit_font(draw, badge, 28, 36, True, 22, 1)
        _center(draw, (100, y0 + row_h / 2 - 22, 144, y0 + row_h / 2 + 22), badge, bf, theme["navy"] if fill != theme["gold"] else theme["gold"])
        if show and text:
            primary, secondary = _split_pair(text)
            ex_primary, ex_secondary = _split_pair(ex or "")
            second_ink = theme["gold"] if fill != theme["gold"] else theme["white"]
            label_size = 28 if (secondary or ex) else 34
            block = label_size
            if secondary:
                block += 6 + int(label_size * 0.72)
            if ex_primary:
                block += 8 + 20
            if ex_secondary:
                block += 4 + 16
            ty = y0 + max(8, (row_h - block) / 2)
            ty = _draw_pair_line(draw, (164, ty), text, label_size, ink, second_ink, True)
            if ex_primary or ex_secondary:
                ty += 6
                _draw_pair_line(draw, (164, ty), ex or "", 20, ink, second_ink, False)


def _draw_pair_line(draw, xy, text, size, fill, second_fill, bold=True, max_w=900) -> int:
    """Draw a bilingual field. Second language sits under the first, in its own colour."""
    x, y = xy
    primary, secondary = _split_pair(text)
    if not primary and not secondary:
        return y
    main = size
    draw_mixed(draw, (x, y), primary, main, fill, bold)
    y += int(main * 1.05)
    if secondary:
        sub = max(16, int(size * 0.72))
        y += 4
        draw_mixed(draw, (x, y), secondary, sub, second_fill, False)
        y += int(sub * 1.05)
    return y


def _cell_lit(highlight: str, key: str, row: int, col: int) -> bool:
    """Gold a cell, a whole row (row1), a whole column (col2), or the grid (all)."""
    h = (highlight or "").strip().lower()
    if not h:
        return False
    if h in {"all", "*"}:
        return True
    if h == key:
        return True
    if h == f"row{row}":
        return True
    if h == f"col{col}":
        return True
    return False


def _matrix_highlight(beat: dict, stage) -> str:
    """Gold cell for this still. highlight_sN wins; else list; else single key."""
    if stage not in (None, 0):
        raw = beat.get(f"highlight_s{int(stage)}") or beat.get(f"highlight{int(stage)}")
        if raw:
            return str(raw).strip().lower()
    if stage in (None, 0):
        for n in (3, 2, 1):
            raw = beat.get(f"highlight_s{n}") or beat.get(f"highlight{n}")
            if raw:
                return str(raw).strip().lower()
    raw = beat.get("highlight")
    if isinstance(raw, (list, tuple)):
        keys = [str(x).strip().lower() for x in raw if x]
        if not keys:
            return ""
        if stage in (None, 0):
            return keys[-1]
        return keys[min(max(int(stage) - 1, 0), len(keys) - 1)]
    key = str(raw or "").strip().lower()
    if not key:
        return ""
    if stage in (None, 0) or int(stage) >= 4:
        return key
    return ""


def render_payoff_matrix(draw, beat, code, y, theme, stage=None, second=None) -> None:
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "PAYOFFS", "zh": "报酬", "zh_hk": "報酬"}.get(code, "PAYOFFS")
    if second:
        other = {"en": "PAYOFFS", "zh": "报酬", "zh_hk": "報酬"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 22, tag, theme)
    row_p = field2(beat, "row_player", code, second) or "Row"
    col_p = field2(beat, "col_player", code, second) or "Col"
    r1 = field2(beat, "row1", code, second) or "High"
    r2 = field2(beat, "row2", code, second) or "Low"
    c1 = field2(beat, "col1", code, second) or "High"
    c2 = field2(beat, "col2", code, second) or "Low"
    cells = [
        [field2(beat, "c11", code, second), field2(beat, "c12", code, second)],
        [field2(beat, "c21", code, second), field2(beat, "c22", code, second)],
    ]
    highlight = _matrix_highlight(beat, stage)
    gutter, label_w = 18, 200
    grid_top = box_y + 118
    grid_left = 64 + label_w
    grid_w = W - 64 - 36 - grid_left
    grid_h = box_y + box_h - 24 - grid_top
    cw = (grid_w - gutter) // 2
    ch = (grid_h - gutter) // 2
    tw = mixed_length(draw, col_p, 24, True)
    draw_mixed(draw, (grid_left + (grid_w - tw) / 2, box_y + 48), col_p, 24, theme["gold"], True)
    for j, lab in enumerate((c1, c2)):
        x0 = grid_left + j * (cw + gutter)
        tw = mixed_length(draw, lab, 26, True)
        draw_mixed(draw, (x0 + (cw - tw) / 2, grid_top - 40), lab, 26, theme["bg"], True)
    tw = mixed_length(draw, row_p, 22, True)
    draw_mixed(draw, (80 + (label_w - 28 - tw) / 2, box_y + 48), row_p, 22, theme["gold"], True)
    for i, lab in enumerate((r1, r2)):
        y0 = grid_top + i * (ch + gutter)
        tw = mixed_length(draw, lab, 28, True)
        draw_mixed(draw, (80 + (label_w - 28 - tw) / 2, y0 + ch / 2 - 16), lab, 28, theme["bg"], True)
    white = theme.get("white") or (247, 244, 238)
    for i in range(2):
        for j in range(2):
            x0 = grid_left + j * (cw + gutter)
            y0 = grid_top + i * (ch + gutter)
            key = f"c{i + 1}{j + 1}"
            fill = theme["gold"] if highlight == key else white
            ink = theme["navy"] if fill != theme["gold"] else theme["navy"]
            draw.rounded_rectangle([x0, y0, x0 + cw, y0 + ch], radius=18, fill=fill)
            show = True
            if stage not in (None, 0):
                if stage <= 2:
                    show = False
                elif stage == 3:
                    show = i == 0 and j == 0
            val = cells[i][j] or ""
            if show and val:
                vf = fit_font(draw, val, 56, cw - 40, True, 28, 2, ch - 36)
                _center(draw, (x0 + 16, y0 + 12, x0 + cw - 16, y0 + ch - 12), val, vf, ink)


def _grid_dims(beat: dict) -> tuple[int, int]:
    try:
        rows = int(beat.get("rows") or 2)
    except (TypeError, ValueError):
        rows = 2
    try:
        cols = int(beat.get("cols") or 2)
    except (TypeError, ValueError):
        cols = 2
    return max(2, min(rows, 4)), max(2, min(cols, 3))


def _grid_band_text(beat, code, second) -> list[str]:
    """Footer, stamp, and staged captions. The grid must clear the tallest one."""
    texts = []
    for stem in ("footer", "note", "stamp"):
        text = field2(beat, stem, code, second)
        if text:
            texts.append(text)
    for n in (1, 2, 3):
        for stem in (f"caption_s{n}", f"footer_s{n}"):
            text = field2(beat, stem, code, second)
            if text:
                texts.append(text)
    return texts


def _grid_foot(beat, code, second, rows: int, cols: int) -> int:
    texts = _grid_band_text(beat, code, second)
    cells = rows * cols
    if not texts:
        return 36 if cells >= 6 else 20
    bilingual = any("\n" in text for text in texts)
    foot = 112 if bilingual else 72
    if cells >= 6:
        foot += 20
    return foot


def render_table_grid(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """2x2 or 2x3 labeled grid. Stages: labels, cells, highlight+footer."""
    rows, cols = _grid_dims(beat)
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "TABLE", "zh": "对照表", "zh_hk": "對照表"}.get(code, "TABLE")
    if second:
        other = {"en": "TABLE", "zh": "对照表", "zh_hk": "對照表"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 18, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    stamp = field2(beat, "stamp", code, second)
    highlight = _matrix_highlight(beat, stage)
    label_w = 180 if rows >= 4 else 210
    head_h = 36 if rows >= 4 else 46
    grid_top = box_y + 64
    grid_left = 64 + label_w
    grid_right = W - 88
    foot = _grid_foot(beat, code, second, rows, cols)
    grid_bottom = box_y + box_h - foot
    gutter = 10 if rows >= 4 else 14
    cw = max(120, (grid_right - grid_left - gutter * (cols - 1)) // cols)
    avail = grid_bottom - grid_top - head_h - gutter * (rows - 1)
    ch = max(56, avail // rows)
    white = theme.get("white") or (247, 244, 238)
    for j in range(cols):
        lab = field2(beat, f"col{j + 1}", code, second) or ""
        x0 = grid_left + j * (cw + gutter)
        if lab:
            tw = mixed_length(draw, lab, 24, True)
            draw_mixed(draw, (x0 + max(0, (cw - tw) / 2), grid_top + 6), lab, 24, theme["gold"], True)
    for i in range(rows):
        lab = field2(beat, f"row{i + 1}", code, second) or ""
        y0 = grid_top + head_h + i * (ch + gutter)
        if lab:
            lf = fit_font(draw, lab, 26, label_w - 40, True, 18, 2, ch - 16)
            _center(draw, (80, y0, 64 + label_w - 16, y0 + ch), lab, lf, theme["bg"])
        for j in range(cols):
            x0 = grid_left + j * (cw + gutter)
            key = f"c{i + 1}{j + 1}"
            val = field2(beat, key, code, second) or beat.get(key) or ""
            val = str(val).strip()
            lit = bool(highlight) and _cell_lit(highlight, key, i + 1, j + 1)
            reveal = str(beat.get("reveal") or "").strip().lower()
            show_val = _show(stage, 2)
            if reveal in {"cols", "col", "columns"} and stage not in (None, 0):
                show_val = int(stage) >= j + 2
            _paint_cell(
                draw, (x0, y0, x0 + cw, y0 + ch), val, theme,
                lit=lit, fmt=_cell_fmt(beat, key), show=show_val,
            )
    caption = footer
    if stage not in (None, 0):
        caption = field2(beat, f"caption_s{int(stage)}", code, second) or field2(beat, f"footer_s{int(stage)}", code, second) or footer
    band_top = grid_bottom + 8
    band_bottom = box_y + box_h - 12
    if stamp and (stage in (None, 0) or _show(stage, 3)):
        sf = fit_font(draw, stamp, 26, W - 220, True, 18, 1)
        _center(draw, (100, band_top, W - 100, band_top + 32), stamp, sf, theme["gold"])
        band_top += 34
    if caption and (stage in (None, 0) or _show(stage, 1)):
        ff = fit_font(draw, caption, 28, W - 220, True, 20, 2)
        _center(draw, (100, band_top, W - 100, band_bottom), caption, ff, theme["gold"])



def render_series(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Two rows across up to six days.

    Default: stage 2 fills row 1, stage 3 fills row 2 and the footer.
    reveal: cells fills row 1 one cell at a time during stage 1, so a
    spoken count is on the card while it is being named.
    """
    try:
        cols = int(beat.get("cols") or 5)
    except (TypeError, ValueError):
        cols = 5
    cols = max(2, min(cols, 6))
    rows = 2
    reveal = str(beat.get("reveal") or "").strip().lower() == "cells"
    shown = cols
    if reveal and stage not in (None, 0):
        shown = min(cols, max(1, int(stage)))
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "FIVE DAYS", "zh": "五日", "zh_hk": "五日"}.get(code, "FIVE DAYS")
    if second:
        other = {"en": "FIVE DAYS", "zh": "五日", "zh_hk": "五日"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 18, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    label_w = 150
    head_h = 42
    grid_top = box_y + 70
    grid_left = 64 + label_w
    grid_right = W - 88
    foot = 88 if footer else 36
    grid_bottom = box_y + box_h - foot
    gutter = 12
    cw = max(110, (grid_right - grid_left - gutter * (cols - 1)) // cols)
    avail = grid_bottom - grid_top - head_h - gutter
    ch = max(72, avail // rows)
    for j in range(cols):
        lab = field2(beat, f"col{j + 1}", code, second) or f"{j + 1}"
        x0 = grid_left + j * (cw + gutter)
        tw = mixed_length(draw, lab, 22, True)
        draw_mixed(draw, (x0 + max(0, (cw - tw) / 2), grid_top + 8), lab, 22, theme["gold"], True)
    for i in range(rows):
        lab = field2(beat, f"row{i + 1}", code, second) or ""
        y0 = grid_top + head_h + i * (ch + gutter)
        if lab:
            lf = fit_font(draw, lab, 32, label_w - 36, True, 22, 1, ch - 20)
            _center(draw, (76, y0, 64 + label_w - 12, y0 + ch), lab, lf, theme["bg"])
        for j in range(cols):
            x0 = grid_left + j * (cw + gutter)
            key = f"c{i + 1}{j + 1}"
            val = str(field2(beat, key, code, second) or beat.get(key) or "").strip()
            if reveal and stage not in (None, 0):
                if i == 0:
                    show_val = j < shown or int(stage) > cols
                else:
                    show_val = int(stage) > cols + 1
            else:
                show_val = stage in (None, 0) or _show(stage, i + 2)
            _paint_cell(draw, (x0, y0, x0 + cw, y0 + ch), val, theme, show=show_val)
    foot_on = stage in (None, 0) or (reveal and stage not in (None, 0) and int(stage) > cols + 1) or (not reveal and _show(stage, 3))
    if footer and foot_on:
        ff = fit_font(draw, footer, 28, W - 220, True, 20, 2)
        _center(draw, (100, grid_bottom + 8, W - 100, box_y + box_h - 16), footer, ff, theme["gold"])


def _cell_fmt(beat: dict, key: str) -> str:
    """blank, mark, or quiet. Per-cell c11_fmt wins; else fmts: c21=blank, c13=mark."""
    direct = str(beat.get(f"{key}_fmt") or "").strip().lower()
    if direct:
        return direct
    raw = str(beat.get("fmts") or beat.get("cell_fmt") or "")
    for part in raw.replace(";", ",").split(","):
        if "=" not in part:
            continue
        name, kind = part.split("=", 1)
        if name.strip().lower() == key:
            return kind.strip().lower()
    return ""


def _paint_cell(draw, box, val, theme, lit=False, fmt="", show=True):
    x0, y0, x1, y1 = box
    white = theme.get("white") or (247, 244, 238)
    fill = theme["gold"] if lit else white
    if fmt == "blank" and not lit:
        fill = theme.get("wash") or (232, 226, 214)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=16, fill=fill)
    if fmt == "mark" and not lit:
        draw.rounded_rectangle([x0 + 4, y0 + 4, x1 - 4, y1 - 4], radius=12, outline=theme["gold"], width=4)
    if fmt == "quiet" and not lit:
        draw.rounded_rectangle([x0 + 3, y0 + 3, x1 - 3, y1 - 3], radius=12, outline=theme["muted"], width=2)
    if not (val and show):
        return
    ink = theme["navy"]
    if fmt == "blank" and not lit:
        ink = theme["muted"]
    if fmt == "quiet" and not lit:
        ink = theme["muted"]
    vf = fit_font(draw, val, 48, (x1 - x0) - 28, fmt != "quiet", 22, 2, (y1 - y0) - 24)
    _center(draw, (x0 + 10, y0 + 8, x1 - 10, y1 - 8), val, vf, ink)


def _chart_kind(beat: dict) -> str:
    raw = str(beat.get("chart") or beat.get("kind") or "scatter").strip().lower().replace("-", "_")
    aliases = {"hist": "histogram", "event_study": "two_line", "event": "two_line", "did": "two_line", "resid": "residual", "box": "boxplot", "means": "guesses", "strip": "guesses"}
    raw = aliases.get(raw, raw)
    if raw not in {"histogram", "scatter", "boxplot", "two_line", "residual", "guesses"}:
        return "scatter"
    return raw


def _axes(draw, box, theme, xlab, ylab) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    pad_l, pad_b, pad_t, pad_r = 78, 54, 18, 24
    ax0, ay0 = x0 + pad_l, y1 - pad_b
    ax1, ay1 = x1 - pad_r, y0 + pad_t
    ink = theme["bg"]
    draw.line([(ax0, ay0), (ax1, ay0)], fill=ink, width=3)
    draw.line([(ax0, ay0), (ax0, ay1)], fill=ink, width=3)
    if xlab:
        xf = fit_font(draw, xlab, 22, ax1 - ax0, False, 16, 1)
        _center(draw, (ax0, ay0 + 10, ax1, ay0 + 48), xlab, xf, theme["gold"], bold=False)
    if ylab:
        yf = fit_font(draw, ylab, 20, 200, False, 14, 2)
        # vertical-ish label sitting left of the axis
        _center(draw, (x0 + 8, ay1, ax0 - 8, ay0), ylab, yf, theme["gold"], bold=False)
    return ax0, ay1, ax1, ay0


def render_schematic_chart(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Named schematic only. No live data. Stages: axes, marks, annotation."""
    kind = _chart_kind(beat)
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {
        "histogram": {"en": "HISTOGRAM", "zh": "直方图", "zh_hk": "直方圖"},
        "scatter": {"en": "SCATTER", "zh": "散点", "zh_hk": "散點"},
        "boxplot": {"en": "BOXPLOT", "zh": "箱线图", "zh_hk": "箱線圖"},
        "two_line": {"en": "TRENDS", "zh": "趋势", "zh_hk": "趨勢"},
        "residual": {"en": "RESIDUALS", "zh": "残差", "zh_hk": "殘差"},
        "guesses": {"en": "GUESSES", "zh": "多次猜测", "zh_hk": "多次猜測"},
    }[kind].get(code, kind.upper())
    _tag(draw, 108, box_y + 16, tag, theme)
    xlab = field2(beat, "x", code, second) or field2(beat, "xlab", code, second)
    ylab = field2(beat, "y", code, second) or field2(beat, "ylab", code, second)
    note = field2(beat, "note", code, second) or field2(beat, "mark", code, second)
    ax0, ay1, ax1, ay0 = _axes(draw, (88, box_y + 56, W - 88, box_y + box_h - 18), theme, xlab if _show(stage, 1) else "", ylab if _show(stage, 1) else "")
    aw, ah = ax1 - ax0, ay0 - ay1
    gold, em, bg = theme["gold"], theme["emerald"], theme["bg"]
    if kind == "histogram" and _show(stage, 2):
        heights = (0.28, 0.46, 0.78, 0.62, 0.34, 0.16, 0.08)
        n = len(heights)
        gap = 8
        bw = max(18, (aw - gap * (n + 1)) // n)
        for i, h in enumerate(heights):
            x = ax0 + gap + i * (bw + gap)
            top = ay0 - int(ah * h)
            fill = gold if i == n - 1 else bg
            draw.rectangle([x, top, x + bw, ay0 - 1], fill=fill)
        if note and _show(stage, 3):
            draw_mixed(draw, (ax0 + aw - 280, ay1 + 12), note, 22, gold, True)
    elif kind == "scatter" and _show(stage, 2):
        raw = beat.get("points") or ""
        parsed = []
        for part in str(raw).replace("|", ";").split(";"):
            bits = [b.strip() for b in part.split(",") if b.strip()]
            if len(bits) < 2:
                continue
            try:
                parsed.append((float(bits[0]), float(bits[1])))
            except ValueError:
                continue
        flag = None
        flag_raw = str(beat.get("flag") or "")
        if "," in flag_raw:
            a, b = flag_raw.split(",", 1)
            try:
                flag = (float(a), float(b))
            except ValueError:
                flag = None
        if not parsed:
            parsed = [(9400, 310), (18600, 420)]
        xs = [p[0] for p in parsed] + ([flag[0]] if flag else [])
        xmax = max(xs) * 1.15 or 1
        crowd = _num(beat, "crowd_max", 520)
        flag_from = _num(beat, "flag_from", 4000)
        def px(v):
            return ax0 + int(aw * min(v, xmax) / xmax)
        def py(v):
            if v >= flag_from:
                return ay1 + 18
            return ay0 - int((ay0 - ay1 - 70) * min(v, crowd) / crowd)
        for x, yv in parsed:
            if flag and abs(x - flag[0]) < 1 and abs(yv - flag[1]) < 1 and not _show(stage, 3):
                continue
            marked = flag and abs(x - flag[0]) < 1 and abs(yv - flag[1]) < 1
            r = 10 if marked else 8
            cx, cy = px(x), py(yv)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=gold if marked else bg)
        bins = []
        for part in str(beat.get("bins") or "").replace("|", ";").split(";"):
            bits = [b.strip() for b in part.split(",") if b.strip()]
            if len(bits) < 2:
                continue
            try:
                bins.append((float(bits[0]), float(bits[1])))
            except ValueError:
                continue
        if bins and _show(stage, 3):
            pix = [(px(x), py(yv)) for x, yv in bins]
            if len(pix) > 1:
                draw.line(pix, fill=gold, width=4)
            for cx, cy in pix:
                draw.rectangle([cx - 9, cy - 9, cx + 9, cy + 9], fill=gold)
        fit = []
        for part in str(beat.get("fit") or "").replace("|", ";").split(";"):
            bits = [b.strip() for b in part.split(",") if b.strip()]
            if len(bits) < 2:
                continue
            try:
                fit.append((float(bits[0]), float(bits[1])))
            except ValueError:
                continue
        if len(fit) >= 2 and _show(stage, 3):
            band = _num(beat, "band", 0) if beat.get("band") not in (None, "") else None
            wide = _num(beat, "wide", 0) if beat.get("wide") not in (None, "") else None
            def _ribbon(offset, fill, outline=False):
                if not offset:
                    return
                upper = [(px(x), py(yv + offset)) for x, yv in fit]
                lower = [(px(x), py(yv - offset)) for x, yv in reversed(fit)]
                if outline:
                    draw.line(upper, fill=fill, width=3)
                    draw.line([(px(x), py(yv - offset)) for x, yv in fit], fill=fill, width=3)
                    return
                draw.polygon(upper + lower, fill=fill)
            _ribbon(wide, gold, outline=True)
            _ribbon(band, theme["emerald"])
            draw.line([(px(x), py(yv)) for x, yv in fit], fill=theme["emerald"], width=4)
        curve = []
        for part in str(beat.get("curve") or "").replace("|", ";").split(";"):
            bits = [b.strip() for b in part.split(",") if b.strip()]
            if len(bits) < 2:
                continue
            try:
                curve.append((float(bits[0]), float(bits[1])))
            except ValueError:
                continue
        if len(curve) >= 2 and _show(stage, 3):
            draw.line([(px(x), py(yv)) for x, yv in curve], fill=gold, width=4)
        kink = []
        for part in str(beat.get("kink") or "").replace("|", ";").split(";"):
            bits = [b.strip() for b in part.split(",") if b.strip()]
            if len(bits) < 2:
                continue
            try:
                kink.append((float(bits[0]), float(bits[1])))
            except ValueError:
                continue
        if len(kink) >= 3 and _show(stage, 3):
            draw.line([(px(x), py(yv)) for x, yv in kink], fill=theme["emerald"], width=4)
            kx, ky = px(kink[1][0]), py(kink[1][1])
            draw.ellipse([kx - 8, ky - 8, kx + 8, ky + 8], fill=gold)
        if note and _show(stage, 3):
            draw_mixed(draw, (ax0 + 16, ay1 + 12), note, 22, gold, True)
    elif kind == "guesses" and _show(stage, 2):
        vals = _num_list(beat, "guesses", (340, 348, 352, 358, 365, 372, 378, 386, 390))
        mark = _num(beat, "mark", 365)
        claim = _num(beat, "claim", 0) if beat.get("claim") not in (None, "") else None
        line = _num(beat, "line", 0) if beat.get("line") not in (None, "") else None
        band_lo = _num(beat, "band_lo", 0) if beat.get("band_lo") not in (None, "") else None
        band_hi = _num(beat, "band_hi", 0) if beat.get("band_hi") not in (None, "") else None
        extras = [mark] + ([claim] if claim is not None else []) + ([line] if line is not None else [])
        extras += [band_lo] if band_lo is not None else []
        extras += [band_hi] if band_hi is not None else []
        lo = min(vals + extras) - 20
        hi = max(vals + extras) + 20
        span = hi - lo or 1
        cy = (ay0 + ay1) // 2
        def gx(v):
            return ax0 + int(aw * (v - lo) / span)
        draw.line([(ax0, cy), (ax1, cy)], fill=bg, width=3)
        if band_lo is not None and band_hi is not None and _show(stage, 3):
            x0, x1 = gx(band_lo), gx(band_hi)
            draw.rectangle([x0, cy - 18, x1, cy + 18], fill=theme["emerald"])
        if claim is not None:
            cx = gx(claim)
            draw.line([(cx, cy - 28), (cx, cy + 28)], fill=theme["muted"], width=3)
            draw_mixed(draw, (cx - 18, cy + 36), str(beat.get("claim")), 22, theme["muted"], True)
        if line is not None and _show(stage, 3):
            lx = gx(line)
            draw.line([(lx, ay1 + 24), (lx, ay0 - 8)], fill=gold, width=3)
        for v in vals:
            cx = gx(v)
            past = line is not None and v >= line and _show(stage, 3)
            marked = abs(v - mark) < 0.5 and _show(stage, 3)
            r = 12 if marked else 8
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=gold if past or marked else bg)
        if _show(stage, 3):
            label = str(beat.get("mark") or int(mark))
            draw_mixed(draw, (gx(mark) - 18, cy - 42), label, 22, gold, True)
        if note and _show(stage, 3):
            draw_mixed(draw, (ax0 + 16, ay1 + 12), note, 22, gold, True)
    elif kind == "boxplot" and _show(stage, 2):
        mid = (ax0 + ax1) // 2
        box_w = 90
        q1, med, q3 = ay0 - int(ah * 0.32), ay0 - int(ah * 0.48), ay0 - int(ah * 0.64)
        whisk_lo, whisk_hi = ay0 - int(ah * 0.18), ay0 - int(ah * 0.78)
        draw.line([(mid, whisk_lo), (mid, whisk_hi)], fill=bg, width=3)
        draw.line([(mid - 28, whisk_lo), (mid + 28, whisk_lo)], fill=bg, width=3)
        draw.line([(mid - 28, whisk_hi), (mid + 28, whisk_hi)], fill=bg, width=3)
        draw.rectangle([mid - box_w, q3, mid + box_w, q1], outline=bg, width=3)
        draw.line([(mid - box_w, med), (mid + box_w, med)], fill=gold, width=4)
        if _show(stage, 3):
            ox, oy = mid + 130, ay0 - int(ah * 0.90)
            draw.ellipse([ox - 8, oy - 8, ox + 8, oy + 8], fill=gold)
            if note:
                draw_mixed(draw, (ox + 16, oy - 12), note, 22, gold, True)
    elif kind == "two_line" and _show(stage, 2):
        # comparison (emerald) and treated (bg), event at 0.55
        ev = ax0 + int(aw * 0.55)
        draw.line([(ev, ay1 + 8), (ev, ay0)], fill=theme["muted"], width=2)
        mark = field2(beat, "event", code, second) or "T"
        tw = mixed_length(draw, mark, 20, True)
        draw_mixed(draw, (ev - tw / 2, ay1 + 10), mark, 20, theme["gold"], True)
        def _poly(pts, color, width=4, dash=False):
            pix = [(ax0 + int(aw * a), ay0 - int(ah * b)) for a, b in pts]
            if not dash:
                draw.line(pix, fill=color, width=width)
                return
            for i in range(len(pix) - 1):
                xA, yA = pix[i]
                xB, yB = pix[i + 1]
                segs = 8
                for k in range(segs):
                    if k % 2:
                        continue
                    t0, t1 = k / segs, (k + 1) / segs
                    draw.line([(xA + (xB - xA) * t0, yA + (yB - yA) * t0),
                               (xA + (xB - xA) * t1, yA + (yB - yA) * t1)], fill=color, width=width)
        _poly([(0.06, 0.28), (0.55, 0.40), (0.94, 0.52)], em)
        _poly([(0.06, 0.48), (0.55, 0.60)], bg)
        if _show(stage, 3):
            _poly([(0.55, 0.60), (0.94, 0.72)], gold, dash=True)
            _poly([(0.55, 0.60), (0.94, 0.88)], bg)
            # vertical DiD tick near the end
            x = ax0 + int(aw * 0.90)
            y_obs = ay0 - int(ah * 0.88)
            y_cf = ay0 - int(ah * 0.72)
            draw.line([(x, y_obs), (x, y_cf)], fill=gold, width=4)
            dash = field2(beat, "dash", code, second)
            if dash:
                draw_mixed(draw, (ev + 18, y_cf - 28), dash, 20, gold, True)
            if note:
                draw_mixed(draw, (ax0 + 16, ay1 + 36), note, 22, gold, True)
    elif kind == "residual" and _show(stage, 2):
        raw = beat.get("points") or ""
        parsed = []
        for part in str(raw).replace("|", ";").split(";"):
            bits = [b.strip() for b in part.split(",") if b.strip()]
            if len(bits) < 2:
                continue
            try:
                parsed.append((float(bits[0]), float(bits[1])))
            except ValueError:
                continue
        fit = []
        for part in str(beat.get("fit") or "").replace("|", ";").split(";"):
            bits = [b.strip() for b in part.split(",") if b.strip()]
            if len(bits) < 2:
                continue
            try:
                fit.append((float(bits[0]), float(bits[1])))
            except ValueError:
                continue
        flag_y = None
        flag_raw = str(beat.get("flag") or "")
        if "," in flag_raw:
            try:
                flag_y = float(flag_raw.split(",", 1)[1])
            except ValueError:
                flag_y = None
        mid = (ay0 + ay1) // 2
        draw.line([(ax0, mid), (ax1, mid)], fill=theme["muted"], width=2)
        if parsed and len(fit) >= 2:
            x0, y0 = fit[0]
            x1, y1 = fit[1]
            slope = (y1 - y0) / (x1 - x0) if x1 != x0 else 0
            rows = []
            for x, yv in parsed:
                pred = y0 + slope * (x - x0)
                rows.append((x, yv - pred, flag_y is not None and abs(yv - flag_y) < 1))
            xs = [r[0] for r in rows]
            xmin, xmax = min(xs), max(xs)
            span = (xmax - xmin) or 1
            crowd = _num(beat, "crowd_max", 80)
            for x, resid, marked in rows:
                cx = ax0 + int(aw * (x - xmin) / span)
                if marked and _show(stage, 3):
                    cy = ay1 + 18
                    draw.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=gold)
                    continue
                if marked:
                    continue
                cy = mid - int((mid - ay1 - 70) * max(-crowd, min(crowd, resid)) / crowd)
                draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=bg)
        else:
            pts = [(0.10, 8), (0.18, -14), (0.26, 6), (0.34, -10), (0.42, 16),
                   (0.50, -6), (0.58, 22), (0.66, -18), (0.74, 28), (0.82, -24), (0.90, 34)]
            for px, dy in pts:
                cx = ax0 + int(aw * px)
                cy = mid - dy
                draw.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=bg)
            if _show(stage, 3):
                draw.line([(ax0 + int(aw * 0.12), mid - 6), (ax0 + int(aw * 0.92), mid - 40)], fill=gold, width=3)
        if note and _show(stage, 3):
            draw_mixed(draw, (ax0 + 16, ay1 + 12), note, 22, gold, True)


def _dag_nodes(beat, code, second=None) -> list[tuple[str, str]]:
    nodes = []
    for i in range(1, 6):
        nid = str(beat.get(f"n{i}_id") or beat.get(f"n{i}") or "").strip()
        lab = field2(beat, f"n{i}_label", code, second) or field2(beat, f"n{i}", code, second) or nid
        if nid or lab:
            nodes.append((nid or f"N{i}", lab or nid))
    if nodes:
        return nodes
    # compact fallback: nodes_en: "X, T, Y"
    raw = field2(beat, "nodes", code, second) or beat.get("nodes") or ""
    parts = [p.strip() for p in str(raw).replace(";", ",").split(",") if p.strip()]
    return [(p, p) for p in parts[:5]]


def _dag_edges(beat) -> list[tuple[str, str]]:
    edges = []
    raw_list = beat.get("edges")
    if isinstance(raw_list, list):
        seq = raw_list
    else:
        seq = [beat.get(f"e{i}") for i in range(1, 8)]
        extra = beat.get("edges")
        if extra:
            seq.append(extra)
    for item in seq:
        if not item:
            continue
        if isinstance(item, dict):
            a, b = item.get("from") or item.get("a"), item.get("to") or item.get("b")
        else:
            text = str(item).replace("→", "->").replace("=>", "->")
            if "->" not in text:
                continue
            a, b = text.split("->", 1)
        a, b = str(a).strip(), str(b).strip()
        if a and b:
            edges.append((a, b))
    return edges


def _dag_layout(n: int, ax0, ay1, ax1, ay0) -> list[tuple[int, int]]:
    cx, cy = (ax0 + ax1) // 2, (ay1 + ay0) // 2
    dx, dy = (ax1 - ax0) // 3, (ay0 - ay1) // 3
    if n <= 1:
        return [(cx, cy)]
    if n == 2:
        return [(cx - dx, cy), (cx + dx, cy)]
    if n == 3:
        return [(cx, cy - dy), (cx - dx, cy + dy // 2), (cx + dx, cy + dy // 2)]
    if n == 4:
        return [(cx, cy - dy), (cx + dx, cy), (cx, cy + dy), (cx - dx, cy)]
    return [(cx - dx, cy - dy), (cx + dx, cy - dy), (cx - dx, cy + dy), (cx, cy + dy // 6), (cx + dx, cy + dy)]


def render_dag(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Nodes, then edges, then one highlighted path plus a role tag."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "DAG", "zh": "因果图", "zh_hk": "因果圖"}.get(code, "DAG")
    _tag(draw, 108, box_y + 16, tag, theme)
    nodes = _dag_nodes(beat, code, second)
    edges = _dag_edges(beat)
    role = field2(beat, "role", code, second)
    hi_raw = str(beat.get("highlight") or beat.get("highlight_edge") or "").replace("→", "->")
    hi = tuple(p.strip() for p in hi_raw.split("->", 1)) if "->" in hi_raw else ()
    ax0, ay1, ax1, ay0 = 120, box_y + 70, W - 120, box_y + box_h - 70
    pts = _dag_layout(len(nodes), ax0, ay1, ax1, ay0)
    pos = {nodes[i][0]: pts[i] for i in range(len(nodes))}
    # also index by label
    for nid, lab in nodes:
        pos.setdefault(lab, pos[nid])
    r = 72
    if _show(stage, 2):
        for a, b in edges:
            if a not in pos or b not in pos:
                continue
            x0, y0 = pos[a]
            x1, y1 = pos[b]
            lit = hi == (a, b) and _show(stage, 3)
            color = theme["gold"] if lit else theme["bg"]
            width = 6 if lit else 3
            dx, dy = x1 - x0, y1 - y0
            dist = math.hypot(dx, dy) or 1
            ux, uy = dx / dist, dy / dist
            sx, sy = x0 + ux * (r + 4), y0 + uy * (r + 4)
            ex, ey = x1 - ux * (r + 4), y1 - uy * (r + 4)
            draw.line([(sx, sy), (ex, ey)], fill=color, width=width)
            hx, hy = -uy, ux
            draw.polygon(
                [
                    (ex, ey),
                    (ex - ux * 16 + hx * 8, ey - uy * 16 + hy * 8),
                    (ex - ux * 16 - hx * 8, ey - uy * 16 - hy * 8),
                ],
                fill=color,
            )
    if _show(stage, 1):
        for (nid, lab), (cx, cy) in zip(nodes, pts):
            lit = hi and nid in hi and _show(stage, 3)
            fill = theme["gold"] if lit else theme.get("white") or (247, 244, 238)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
            lf = fit_font(draw, lab, 26, 2 * r - 12, True, 16, 2, 2 * r - 16)
            _center(draw, (cx - r + 6, cy - r + 8, cx + r - 6, cy + r - 8), lab, lf, theme["navy"])
    if role and _show(stage, 3):
        rf = fit_font(draw, role, 28, W - 220, True, 20, 1)
        _center(draw, (100, box_y + box_h - 62, W - 100, box_y + box_h - 16), role, rf, theme["gold"])


def _mini_table(draw, beat, code, second, box, prefix, title_stem, rows, cols, stage, show_from, highlight, theme):
    x0, y0, x1, y1 = box
    title = field2(beat, title_stem, code, second) or ""
    if title:
        tf = fit_font(draw, title, 26, x1 - x0 - 24, True, 18, 1)
        draw_mixed(draw, (x0 + 12, y0 + 10), title, int(getattr(tf, "size", 24) or 24), theme["gold"], True)
    label_w = 168
    head_h = 28
    grid_top = y0 + 48
    grid_left = x0 + label_w
    grid_right = x1 - 12
    grid_bottom = y1 - 12
    gutter = 8
    cw = max(70, (grid_right - grid_left - gutter * (cols - 1)) // max(cols, 1))
    avail = grid_bottom - grid_top - head_h - gutter * (rows - 1)
    ch = max(44, avail // max(rows, 1))
    white = theme.get("white") or (247, 244, 238)
    show = stage in (None, 0) or int(stage) >= show_from
    for j in range(cols):
        lab = field2(beat, f"{prefix}col{j + 1}", code, second) or ""
        cx = grid_left + j * (cw + gutter)
        if lab and show:
            tw = mixed_length(draw, lab, 18, True)
            draw_mixed(draw, (cx + max(0, (cw - tw) / 2), grid_top), lab, 18, theme["bg"], True)
    for i in range(rows):
        lab = field2(beat, f"{prefix}row{i + 1}", code, second) or ""
        ry = grid_top + head_h + i * (ch + gutter)
        if lab and show:
            lf = fit_font(draw, lab, 20, label_w - 16, True, 14, 2, ch - 8)
            _center(draw, (x0 + 8, ry, x0 + label_w - 8, ry + ch), lab, lf, theme["bg"])
        for j in range(cols):
            cx = grid_left + j * (cw + gutter)
            key = f"{prefix}c{i + 1}{j + 1}"
            val = field2(beat, key, code, second) or beat.get(key) or ""
            val = str(val).strip()
            lit = highlight in {key, f"{prefix}row{i + 1}", title_stem, prefix} and (stage in (None, 0) or int(stage) >= 3)
            _paint_cell(draw, (cx, ry, cx + cw, ry + ch), val, theme, lit=lit, fmt=_cell_fmt(beat, key), show=show)


def render_pair(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Two small tables. Stage 1 fills the left, stage 2 the right, stage 3 the mark."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "PAIR", "zh": "对照", "zh_hk": "對照"}.get(code, "PAIR")
    if second:
        other = {"en": "PAIR", "zh": "对照", "zh_hk": "對照"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    highlight = str(_matrix_highlight(beat, stage) or "").strip().lower()
    gap = 18
    inner_top = box_y + 52
    inner_bottom = box_y + box_h - (52 if footer else 16)
    mid = 64 + (W - 128 - gap) // 2
    left_box = (84, inner_top, mid, inner_bottom)
    right_box = (mid + gap, inner_top, W - 84, inner_bottom)
    def dims(prefix, default_rows):
        try:
            rows = int(beat.get(f"{prefix}rows") or default_rows)
        except (TypeError, ValueError):
            rows = default_rows
        try:
            cols = int(beat.get(f"{prefix}cols") or 2)
        except (TypeError, ValueError):
            cols = 2
        return max(1, min(rows, 3)), max(1, min(cols, 2))
    lrows, lcols = dims("l", 3)
    rrows, rcols = dims("r", 3)
    _mini_table(draw, beat, code, second, left_box, "l", "left", lrows, lcols, stage, 1, highlight, theme)
    _mini_table(draw, beat, code, second, right_box, "r", "right", rrows, rcols, stage, 2, highlight, theme)
    if footer and _show(stage, 3):
        ff = fit_font(draw, footer, 26, W - 220, True, 18, 1)
        _center(draw, (100, box_y + box_h - 46, W - 100, box_y + box_h - 12), footer, ff, theme["gold"])


def _num_list(beat, key, default):
    raw = beat.get(key)
    if raw is None or raw == "":
        return list(default)
    if isinstance(raw, (list, tuple)):
        parts = raw
    else:
        parts = str(raw).replace(";", ",").split(",")
    out = []
    for part in parts:
        try:
            out.append(float(str(part).strip()))
        except ValueError:
            continue
    return out or list(default)


def _num(beat, key, default):
    raw = beat.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        return default


def _mini_hist(draw, box, heights, theme, mark_last=True):
    x0, y0, x1, y1 = box
    ax0, ay0 = x0 + 36, y1 - 28
    ax1, ay1 = x1 - 12, y0 + 8
    ink = theme["bg"]
    draw.line([(ax0, ay0), (ax1, ay0)], fill=ink, width=3)
    draw.line([(ax0, ay0), (ax0, ay1)], fill=ink, width=3)
    aw, ah = ax1 - ax0, ay0 - ay1
    n = len(heights)
    gap = 6
    bw = max(10, (aw - gap * (n + 1)) // n)
    for i, h in enumerate(heights):
        x = ax0 + gap + i * (bw + gap)
        top = ay0 - int(ah * h)
        fill = theme["gold"] if mark_last and i == n - 1 else ink
        draw.rectangle([x, top, x + bw, ay0 - 1], fill=fill)


def render_pair_chart(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Two schematic histograms. Stage 1 draws the left, stage 2 the right, stage 3 the notes."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "TWO WIDTHS", "zh": "两种组距", "zh_hk": "兩種組距"}.get(code, "TWO WIDTHS")
    if second:
        other = {"en": "TWO WIDTHS", "zh": "两种组距", "zh_hk": "兩種組距"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    gap = 28
    inner_top = box_y + 58
    inner_bottom = box_y + box_h - (58 if footer else 20)
    mid = 64 + (W - 128 - gap) // 2
    left_bars = _num_list(beat, "left_bars", (0.22, 0.58, 0.30, 0.74, 0.36, 0.62, 0.24, 0.18, 0.42))
    right_bars = _num_list(beat, "right_bars", (0.34, 0.82, 0.48, 0.16))
    panels = ((88, mid, "left", left_bars), (mid + gap, W - 88, "right", right_bars))
    for x0, x1, stem, heights in panels:
        title = field2(beat, stem, code, second) or ""
        show = stage in (None, 0) or int(stage) >= (1 if stem == "left" else 2)
        if title and show:
            tf = fit_font(draw, title, 26, x1 - x0 - 16, True, 18, 1)
            draw_mixed(draw, (x0, inner_top), title, int(getattr(tf, "size", 24) or 24), theme["gold"], True)
        if show:
            _mini_hist(draw, (x0, inner_top + 40, x1, inner_bottom - 28), heights, theme, mark_last=True)
        cap = field2(beat, f"{stem}_note", code, second) or ""
        if cap and _show(stage, 3):
            cf = fit_font(draw, cap, 22, x1 - x0 - 8, False, 16, 1)
            draw_mixed(draw, (x0, inner_bottom - 24), cap, int(getattr(cf, "size", 20) or 20), theme["gold"], False)
    if footer and _show(stage, 3):
        ff = fit_font(draw, footer, 26, W - 220, True, 18, 1)
        _center(draw, (100, box_y + box_h - 48, W - 100, box_y + box_h - 12), footer, ff, theme["gold"])


def _pair_cloud(draw, box, points, fit, theme, show_line):
    x0, y0, x1, y1 = box
    xs = [p[0] for p in points] or [0, 1]
    ys = [p[1] for p in points] + [p[1] for p in fit]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    spanx = (xmax - xmin) or 1
    spany = (ymax - ymin) or 1
    def px(x):
        return x0 + 16 + int((x1 - x0 - 32) * (x - xmin) / spanx)
    def py(yv):
        return y1 - 16 - int((y1 - y0 - 32) * (yv - ymin) / spany)
    for x, yv in points:
        cx, cy = px(x), py(yv)
        draw.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=theme["bg"])
    if show_line and len(fit) >= 2:
        draw.line([(px(a), py(b)) for a, b in fit], fill=theme["emerald"], width=4)


def render_pair_slope(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Two Mondays, two clouds, two green lines. Stage 1 left, stage 2 right, stage 3 the tilt."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "TWO MONDAYS", "zh": "两个周一", "zh_hk": "兩個周一"}.get(code, "TWO MONDAYS")
    if second:
        other = {"en": "TWO MONDAYS", "zh": "两个周一", "zh_hk": "兩個周一"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    gap = 28
    inner_top = box_y + 58
    inner_bottom = box_y + box_h - (58 if footer else 20)
    mid = 64 + (W - 128 - gap) // 2

    def pairs(key):
        out = []
        for part in str(beat.get(key) or "").replace("|", ";").split(";"):
            bits = [b.strip() for b in part.split(",") if b.strip()]
            if len(bits) < 2:
                continue
            try:
                out.append((float(bits[0]), float(bits[1])))
            except ValueError:
                continue
        return out

    panels = (
        (88, mid, "left", pairs("left_points"), pairs("left_fit")),
        (mid + gap, W - 88, "right", pairs("right_points"), pairs("right_fit")),
    )
    for x0, x1, stem, points, fit in panels:
        title = field2(beat, stem, code, second) or ""
        show = stage in (None, 0) or int(stage) >= (1 if stem == "left" else 2)
        if title and show:
            draw_mixed(draw, (x0, inner_top), title, 24, theme["gold"], True)
        if show and points:
            _pair_cloud(draw, (x0, inner_top + 40, x1, inner_bottom - 8), points, fit, theme, _show(stage, 3) or stage in (None, 0))
    if footer and _show(stage, 3):
        ff = fit_font(draw, footer, 26, W - 220, True, 18, 1)
        _center(draw, (100, box_y + box_h - 48, W - 100, box_y + box_h - 12), footer, ff, theme["gold"])


def _one_box(draw, cx, scale, theme, lo, q1, med, q3, hi, flag=None):
    def y(v):
        return scale(v)
    ink = theme["bg"]
    draw.line([(cx, y(lo)), (cx, y(hi))], fill=ink, width=4)
    draw.line([(cx - 28, y(lo)), (cx + 28, y(lo))], fill=ink, width=3)
    draw.line([(cx - 28, y(hi)), (cx + 28, y(hi))], fill=ink, width=3)
    draw.rectangle([cx - 54, y(q3), cx + 54, y(q1)], outline=ink, width=4)
    draw.line([(cx - 54, y(med)), (cx + 54, y(med))], fill=theme["gold"], width=5)
    if flag is not None:
        fy = y(flag)
        draw.ellipse([cx - 10, fy - 10, cx + 10, fy + 10], fill=theme["gold"])


def render_pair_box(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Two boxplots on one cup scale. Stage 1 left, stage 2 right, stage 3 the far shop."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "SAME SCALE", "zh": "同一尺度", "zh_hk": "同一尺度"}.get(code, "SAME SCALE")
    if second:
        other = {"en": "SAME SCALE", "zh": "同一尺度", "zh_hk": "同一尺度"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second)
    bilingual = "\n" in (footer or "")
    top = box_y + 64
    label_band = 36
    foot_band = (78 if bilingual else 44) if footer else 8
    bottom = box_y + box_h - label_band - foot_band - 8
    ax = 150
    draw.line([(ax, top + 70), (ax, bottom)], fill=theme["bg"], width=3)
    draw.line([(ax, top), (ax, top + 36)], fill=theme["bg"], width=3)
    draw_mixed(draw, (ax - 10, top + 40), "//", 22, theme["gold"], True)
    for cups, label, yy in (
        (_num(beat, "tick_lo", 0), str(beat.get("tick_lo") or "0"), bottom),
        (_num(beat, "tick_mid", 400), str(beat.get("tick_mid") or "400"), bottom - (bottom - top - 90) * 0.72),
        (_num(beat, "tick_hi", 4200), str(beat.get("tick_hi") or "4200"), top + 8),
    ):
        draw.line([(ax - 8, yy), (ax + 8, yy)], fill=theme["bg"], width=2)
        draw_mixed(draw, (70, yy - 12), label, 20, theme["bg"], True)
    crowd_top = top + 90
    crowd = _num(beat, "crowd_max", 520)
    flag_from = _num(beat, "flag_from", 4000)
    def scale(v):
        if v >= flag_from:
            return top + 18
        return bottom - (bottom - crowd_top) * (min(v, crowd) / crowd)
    left = field2(beat, "left", code, second) or "Left"
    right = field2(beat, "right", code, second) or "Right"
    show_left = stage in (None, 0) or int(stage) >= 1
    show_right = stage in (None, 0) or int(stage) >= 2
    left_flag = _num(beat, "left_flag", None)
    right_flag = _num(beat, "right_flag", None)
    if show_left:
        _one_box(
            draw, 620, scale, theme,
            _num(beat, "left_lo", 280), _num(beat, "left_q1", 360), _num(beat, "left_med", 390),
            _num(beat, "left_q3", 420), _num(beat, "left_hi", 500),
            left_flag if _show(stage, 3) else None,
        )
        name = left.split("\n", 1)[0]
        tw = mixed_length(draw, name, 24, True)
        draw_mixed(draw, (620 - tw / 2, bottom + 8), name, 24, theme["gold"], True)
    if show_right:
        _one_box(
            draw, 1180, scale, theme,
            _num(beat, "right_lo", 250), _num(beat, "right_q1", 280), _num(beat, "right_med", 310),
            _num(beat, "right_q3", 340), _num(beat, "right_hi", 360),
            right_flag if _show(stage, 3) else None,
        )
        name = right.split("\n", 1)[0]
        tw = mixed_length(draw, name, 24, True)
        draw_mixed(draw, (1180 - tw / 2, bottom + 8), name, 24, theme["gold"], True)
    if footer and _show(stage, 3):
        ff = fit_font(draw, footer, 24, W - 280, True, 18, 2)
        _center(draw, (140, box_y + box_h - foot_band - 4, W - 140, box_y + box_h - 10), footer, ff, theme["gold"])


def render_coin(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Two faces. Stage 1 chosen, stage 2 drawn, stage 3 the note."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "COIN", "zh": "硬币", "zh_hk": "硬幣"}.get(code, "COIN")
    if second:
        other = {"en": "COIN", "zh": "硬币", "zh_hk": "硬幣"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    faces = (
        (field2(beat, "left", code, second) or "Chosen", 1, theme["gold"]),
        (field2(beat, "right", code, second) or "Drawn", 2, theme["emerald"]),
    )
    gap = 80
    d = 280
    x = (W - (d * 2 + gap)) // 2
    cy = box_y + box_h // 2 - 16
    for label, show_from, ink in faces:
        if stage in (None, 0) or int(stage) >= show_from:
            box = (x, cy - d // 2, x + d, cy + d // 2)
            draw.ellipse(box, outline=ink, width=8)
            _center(draw, box, label, fit_font(draw, label, 40, d - 48, True, 22, 2), ink)
        x += d + gap
    if footer and _show(stage, 3):
        ff = fit_font(draw, footer, 26, W - 220, True, 18, 1)
        _center(draw, (100, box_y + box_h - 48, W - 100, box_y + box_h - 12), footer, ff, theme["gold"])


def render_mix(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """One gap, two unnamed stories. Stage 1 the gap, stage 2 the split, stage 3 the note. No shares."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "MIXED", "zh": "混着", "zh_hk": "混住"}.get(code, "MIXED")
    if second:
        other = {"en": "MIXED", "zh": "混着", "zh_hk": "混住"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    left = field2(beat, "left", code, second) or "Rent"
    right = field2(beat, "right", code, second) or "Already"
    ax0, ax1 = 280, W - 280
    cy = box_y + 150
    draw.rounded_rectangle([ax0, cy - 28, ax1, cy + 28], radius=12, fill=theme["gold"])
    gap = field2(beat, "gap", code, second) or "420 − 310"
    draw_mixed(draw, (ax0, cy - 64), gap, 28, theme["gold"], True)
    if _show(stage, 2):
        mid = (ax0 + ax1) // 2
        draw.line([(mid, cy + 48), (mid, cy + 130)], fill=theme["bg"], width=3)
        draw.rounded_rectangle([ax0, cy + 130, mid - 16, cy + 186], radius=12, outline=theme["emerald"], width=3)
        draw.rounded_rectangle([mid + 16, cy + 130, ax1, cy + 186], radius=12, outline=theme["bg"], width=3)
        _center(draw, (ax0, cy + 130, mid - 16, cy + 186), left, fit_font(draw, left, 28, mid - ax0 - 40, True, 18, 1), theme["emerald"])
        _center(draw, (mid + 16, cy + 130, ax1, cy + 186), right, fit_font(draw, right, 28, ax1 - mid - 40, True, 18, 1), theme["bg"])
    if footer and _show(stage, 3):
        ff = fit_font(draw, footer, 26, W - 220, True, 18, 1)
        _center(draw, (100, box_y + box_h - 48, W - 100, box_y + box_h - 12), footer, ff, theme["gold"])


def render_shrink(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """A step pulled toward zero. Stage 1 the copy, stage 2 the pull, stage 3 the note."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "PULL", "zh": "拉", "zh_hk": "拉"}.get(code, "PULL")
    if second:
        other = {"en": "PULL", "zh": "拉", "zh_hk": "拉"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    full = _num(beat, "full", 80)
    pulled = _num(beat, "pulled", 25)
    ax0, ax1 = 220, W - 180
    cy = box_y + box_h // 2 - 8
    span = full or 1
    def end(v):
        return ax0 + int((ax1 - ax0) * max(v, 0) / span)
    draw.line([(ax0, cy), (ax1, cy)], fill=theme["bg"], width=3)
    draw.line([(ax0, cy - 18), (ax0, cy + 18)], fill=theme["bg"], width=3)
    draw_mixed(draw, (ax0 - 36, cy + 28), "0", 22, theme["bg"], True)
    unit = field2(beat, "unit", code, second)
    if unit and _show(stage, 2):
        draw_mixed(draw, (ax0 - 8, cy - 78), unit, 22, theme["gold"], True)
    if stage in (None, 0) or int(stage) >= 1:
        draw.rectangle([ax0, cy - 28, end(full), cy + 28], fill=theme["gold"])
        draw_mixed(draw, (end(full) + 12, cy - 48), str(beat.get("full") or int(full)), 22, theme["gold"], True)
    if _show(stage, 2):
        draw.rectangle([ax0, cy - 14, end(pulled), cy + 14], fill=theme["emerald"])
        draw_mixed(draw, (end(pulled) + 12, cy + 20), str(beat.get("pulled") or int(pulled)), 22, theme["emerald"], True)
    if footer and _show(stage, 3):
        ff = fit_font(draw, footer, 26, W - 220, True, 18, 1)
        _center(draw, (100, box_y + box_h - 48, W - 100, box_y + box_h - 12), footer, ff, theme["gold"])


def render_turns(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """A row of Mondays. One is grey, in turn. Stage 1 the row, stage 2 the grey day, stage 3 the note."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "TURNS", "zh": "轮流", "zh_hk": "輪流"}.get(code, "TURNS")
    if second:
        other = {"en": "TURNS", "zh": "轮流", "zh_hk": "輪流"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    days = [p.strip() for p in str(beat.get("days") or "Mon;Tue;Wed;Thu").replace(",", ";").split(";") if p.strip()]
    hold = int(_num(beat, "hold", 2)) - 1
    n = max(1, min(len(days), 5))
    days = days[:n]
    gap = 28
    chip_w = min(280, (W - 220 - gap * (n - 1)) // n)
    row_w = n * chip_w + (n - 1) * gap
    x = (W - row_w) // 2
    cy = box_y + box_h // 2 - 10
    white = theme.get("white") or (247, 244, 238)
    for i, day in enumerate(days):
        show = stage in (None, 0) or int(stage) >= 1
        grey = i == hold and _show(stage, 2)
        if not show:
            continue
        box = (x, cy - 70, x + chip_w, cy + 70)
        draw.rounded_rectangle(box, radius=18, fill=theme["muted"] if grey else white)
        ink = theme["bg"] if grey else theme["navy"]
        _center(draw, box, day, fit_font(draw, day, 36, chip_w - 24, True, 20, 1), ink)
        x += chip_w + gap
    if footer and _show(stage, 3):
        ff = fit_font(draw, footer, 26, W - 220, True, 18, 1)
        _center(draw, (100, box_y + box_h - 48, W - 100, box_y + box_h - 12), footer, ff, theme["gold"])


def render_redraw(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Two redraws. Stage 1 left handful, stage 2 right, stage 3 the repeated row."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "REDRAW", "zh": "重抽", "zh_hk": "重抽"}.get(code, "REDRAW")
    if second:
        other = {"en": "REDRAW", "zh": "重抽", "zh_hk": "重抽"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second)
    gap = 28
    inner_top = box_y + 58
    inner_bottom = box_y + box_h - (58 if footer else 20)
    mid = 64 + (W - 128 - gap) // 2
    panels = ((88, mid, "l", 1), (mid + gap, W - 88, "r", 2))
    white = theme.get("white") or (247, 244, 238)
    for x0, x1, stem, show_from in panels:
        title = field2(beat, "left" if stem == "l" else "right", code, second) or ""
        show = stage in (None, 0) or int(stage) >= show_from
        if title and show:
            draw_mixed(draw, (x0, inner_top), title.split("\n", 1)[0], 26, theme["gold"], True)
        chips = []
        for i in range(1, 4):
            lab = field2(beat, f"{stem}{i}", code, second)
            if lab:
                chips.append(lab)
        if not show:
            continue
        ch = 78
        for i, lab in enumerate(chips):
            ry = inner_top + 48 + i * (ch + 14)
            repeated = stem == "r" and i == 1 and _show(stage, 3)
            fill = theme["gold"] if repeated else white
            draw.rounded_rectangle([x0, ry, x1 - 8, ry + ch], radius=16, fill=fill)
            ink = theme["navy"]
            lf = fit_font(draw, lab, 28, x1 - x0 - 36, True, 18, 1)
            _center(draw, (x0 + 12, ry, x1 - 20, ry + ch), lab, lf, ink)
    if footer and _show(stage, 3):
        ff = fit_font(draw, footer, 26, W - 220, True, 18, 1)
        _center(draw, (100, box_y + box_h - 46, W - 100, box_y + box_h - 12), footer, ff, theme["gold"])


RENDERERS = {
    "title_card": render_title_card,
    "definition_card": render_definition,
    "two_column": render_two_column,
    "takeaway": render_takeaway,
    "formula": render_formula,
    "example": render_example,
    "three_column": render_three_column,
    "big_number": render_big_number,
    "steps": render_steps,
    "module_open": render_module_open,
    "module_close": render_module_close,
    "payoff_matrix": render_payoff_matrix,
    "table_grid": render_table_grid,
    "series": render_series,
    "pair": render_pair,
    "pair_chart": render_pair_chart,
    "pair_box": render_pair_box,
    "pair_slope": render_pair_slope,
    "redraw": render_redraw,
    "turns": render_turns,
    "shrink": render_shrink,
    "mix": render_mix,
    "coin": render_coin,
    "schematic_chart": render_schematic_chart,
    "dag": render_dag,
}


def stage_count(beat: dict) -> int:
    if beat.get("stage") is False:
        return 1
    if beat.get("visual") == "series" and str(beat.get("reveal") or "").strip().lower() == "cells":
        try:
            cols = int(beat.get("cols") or 4)
        except (TypeError, ValueError):
            cols = 4
        cols = max(2, min(cols, 6))
        return cols + 2
    if beat.get("visual") == "steps":
        n = 0
        for i in range(1, 7):
            if any(str(beat.get(f"step{i}{suffix}") or "").strip() for suffix in ("", "_en", "_zh", "_zh_hk")):
                n = i
        if n >= 4:
            return n
    return STAGEABLE.get(beat.get("visual"), 1)


def stage_plan(beat: dict, duration: float, force: bool = False) -> list[int]:
    n = stage_count(beat)
    if n <= 1:
        return [0]
    if force:
        return list(range(1, n + 1))
    if float(duration) < MIN_STAGE_BEAT:
        return [0]
    if n == 2 and duration < MIN_SLICE * 2:
        return [0]
    if n == 3 and duration < MIN_SLICE * 3:
        return [1, n] if duration >= MIN_SLICE * 2 else [0]
    return list(range(1, n + 1))


def slice_durations(duration: float, stages: list[int]) -> list[float]:
    n = max(1, len(stages))
    if n == 1:
        return [float(duration)]
    if n == 2:
        weights = (0.45, 0.55)
    elif n == 3:
        weights = (0.30, 0.35, 0.35)
    else:
        weights = tuple(1.0 / n for _ in range(n))
    raw = [float(duration) * w for w in weights]
    return _clamp_slices(raw, float(duration))


def _clamp_slices(parts: list[float], total: float) -> list[float]:
    parts = [max(MIN_SLICE, p) for p in parts]
    s = sum(parts)
    parts = [p * total / s for p in parts]
    parts[-1] = total - sum(parts[:-1])
    if parts[-1] < MIN_SLICE:
        return [total]
    return parts


def _slide_workers() -> int:
    raw = os.environ.get("VF_SLIDE_JOBS") or os.environ.get("VF_PREVIEW_JOBS") or os.environ.get("VF_CLIP_JOBS", "3")
    try:
        n = int(str(raw).strip() or "3")
    except ValueError:
        n = 3
    return max(1, min(n, 4, os.cpu_count() or 2))


def render_beat(beat, lesson, index, n, lang_labels="en", theme=None, stage=None, second_lang=None):
    theme = theme or load_theme(None)
    img, draw = new_canvas(theme)
    visual = beat.get("visual", "definition_card")
    code = label_code(lang_labels)
    second = label_code(second_lang) if second_lang else None
    if second == code:
        second = None
    foot = field_native(lesson, "title", code) or field(lesson, "title", code) or lesson.get("id") or ""
    draw_footer(draw, foot, index, n, theme)
    if visual == "title_card":
        render_title_card(draw, beat, lesson, code, theme, second=second)
        return img
    if visual == "module_open":
        render_module_open(draw, beat, lesson, code, theme, second=second)
        return img
    if visual == "module_close":
        render_module_close(draw, beat, lesson, code, theme, second=second)
        return img
    kicker = resolve_kicker(beat, code)
    if second:
        other_k = resolve_kicker(beat, second)
        if other_k and other_k != kicker:
            kicker = f"{kicker}  {other_k}" if kicker else other_k
    draw_kicker(draw, kicker, theme)
    title = field2(beat, "title", code, second) or field2(lesson, "title", code, second)
    y = draw_title(draw, title, theme)
    renderer = RENDERERS.get(visual)
    if renderer and renderer is not render_title_card:
        renderer(draw, beat, code, y, theme, stage=None if not stage else stage, second=second)
    elif beat.get("formula"):
        render_formula(draw, beat, code, y, theme, stage=None if not stage else stage, second=second)
    return img


def _paint_one(args):
    beat, lesson, index, n, lang, theme, path, stage, second = args
    try:
        img = render_beat(beat, lesson, index, n, lang_labels=lang, theme=theme, stage=stage, second_lang=second)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, "PNG")
        return path, None
    except Exception as exc:
        return path, f"{type(exc).__name__}: {exc}"


def render_lesson_slides(lesson, dest: Path, label_lang="en", theme=None, second_lang=None) -> list[Path]:
    theme = theme or load_theme(None)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    beats = lesson.get("beats") or []
    n = len(beats)
    jobs = []
    paths = []
    for i, beat in enumerate(beats, start=1):
        path = dest / f"{i:02d}_{beat.get('id') or i}.png"
        paths.append(path)
        jobs.append((beat, lesson, i, n, label_lang, theme, path, None, second_lang))
    workers = _slide_workers()
    print(f"slides: paint {len(jobs)} stills, {workers} workers")
    fails = []
    if workers <= 1:
        for job in jobs:
            _, err = _paint_one(job)
            if err:
                fails.append(err)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for path, err in pool.map(_paint_one, jobs):
                if err:
                    fails.append(f"{path.name}: {err}")
    for msg in fails:
        print("slides: fail", msg)
    print("slides: wrote", dest)
    return paths


def write_stage_slides(lesson, dest: Path, code: str, durations, theme=None, force: bool = False, second_lang=None):
    theme = theme or load_theme(None)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    beats = lesson.get("beats") or []
    n = len(beats)
    written = []
    holds_all = []
    jobs = []
    for i, beat in enumerate(beats, start=1):
        dur = float(durations[i - 1]) if i - 1 < len(durations) else float(beat.get("seconds") or 20)
        plan = stage_plan(beat, dur, force=force)
        holds = slice_durations(dur, plan)
        holds_all.append(holds)
        if plan == [0]:
            written.append(dest / f"{i:02d}_{beat.get('id') or i}.png")
            continue
        for st in plan:
            path = dest / f"{i:02d}_{beat.get('id') or i}_s{st}.png"
            jobs.append((beat, lesson, i, n, code, theme, path, st, second_lang))
            written.append(path)
    workers = _slide_workers()
    print(f"slides: stage {len(jobs)} stills, {workers} workers")
    if jobs:
        if workers <= 1:
            for job in jobs:
                _paint_one(job)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(_paint_one, jobs))
    print("slides: wrote", dest)
    return written, holds_all


def stills_for_beat(slide_dir: Path, index: int, beat: dict, plan: list[int]) -> list[Path]:
    slide_dir = Path(slide_dir)
    bid = beat.get("id") or index
    base = slide_dir / f"{index:02d}_{bid}.png"
    if not plan or plan == [0]:
        return [base] if base.is_file() else []
    out = []
    for st in plan:
        staged = slide_dir / f"{index:02d}_{bid}_s{st}.png"
        out.append(staged if staged.is_file() else base)
    return [p for p in out if p.is_file()]

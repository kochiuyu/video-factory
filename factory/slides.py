#!/usr/bin/env python3
"""Render language-neutral (or bilingual-label) 1920x1080 beat slides."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from glyphs import font_path_for_char, is_cjk, sanitize, scan_lesson
from langs import field, field_native, label_code
from paths import cjk_bold, cjk_regular, latin_bold, latin_regular
from cache import digest_obj, stamp_ok, write_mark
from theme import load_theme

W, H = 1920, 1080

SCALE = {
    "kicker": 28,
    "footer": 22,
    "title": 96,
    "hook": 128,
    "subtitle": 44,
    "chip": 26,
    "tag": 26,
    "index": 28,
    "body": 56,
    "claim": 64,
    "formula": 72,
    "number": 160,
    "unit": 44,
    "caption": 44,
}

# When a mix paints two languages, the second line is smaller and tighter.
DUAL = {
    "title": (72, 38),
    "hook": (84, 42),
    "claim": (46, 30),
    "body": (42, 28),
    "caption": (34, 26),
    "formula": (60, 34),
    "unit": (36, 26),
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
    "definition_card": 2,
    "formula": 2,
    "two_column": 3,
    "example": 3,
    "takeaway": 3,
    "three_column": 3,
    "steps": 3,
    "payoff_matrix": 5,
}

MIN_STAGE_BEAT = 5.0
MIN_SLICE = 1.2
LAYOUT_VERSION = "2026-09-13-footer-title"


def lesson_stamp(lesson: dict, theme: dict | None, code: str, second: str | None, stage_cards: bool) -> str:
    theme_id = (theme or {}).get("id") if isinstance(theme, dict) else theme
    payload = {
        "v": LAYOUT_VERSION,
        "theme": theme_id,
        "code": code,
        "second": second or "",
        "stage": bool(stage_cards),
        "scale": SCALE,
        "lesson": {
            "id": lesson.get("id"),
            "title_en": lesson.get("title_en"),
            "title_zh": lesson.get("title_zh"),
            "title_zh_hk": lesson.get("title_zh_hk"),
            "beats": lesson.get("beats"),
        },
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def stamp_matches(folder: Path, stamp: str) -> bool:
    mark = folder / ".stamp"
    if not mark.is_file() or mark.read_text(encoding="utf-8").strip() != stamp:
        return False
    return any(folder.glob("*.png"))


def write_stamp(folder: Path, stamp: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".stamp").write_text(stamp + "\n", encoding="utf-8")


def beat_stamp(beat: dict, lesson: dict, code: str, second: str | None, theme: dict | None, stage: int | None) -> str:
    theme_id = (theme or {}).get("id") if isinstance(theme, dict) else theme
    return digest_obj(
        {
            "v": LAYOUT_VERSION,
            "theme": theme_id,
            "code": code,
            "second": second or "",
            "stage": stage,
            "scale": SCALE,
            "id": lesson.get("id"),
            "title_en": lesson.get("title_en"),
            "title_zh": lesson.get("title_zh"),
            "title_zh_hk": lesson.get("title_zh_hk"),
            "beat": beat,
        }
    )


def list_slide_pngs(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.png") if p.is_file())


def resolve_kicker(beat: dict, code: str) -> str:
    raw = field_native(beat, "kicker", code)
    if raw:
        return raw
    if code == "en":
        return (beat.get("kicker") or field(beat, "kicker", "en") or "").strip()
    key = (beat.get("kicker") or field(beat, "kicker", "en") or "").strip().upper()
    table = KICKER_I18N.get(key)
    if table:
        want = "zh_hk" if code == "zh_hk" else "zh"
        return table.get(want) or table.get("zh") or ""
    return ""


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def font_for(text: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    if any(is_cjk(ch) for ch in text):
        return _font(FONT_CJK_B if bold else FONT_CJK, size)
    return _font(FONT_LATIN_B if bold else FONT_LATIN, size)


def font_for_char(ch: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = font_path_for_char(ch, bold=bold)
    return _font(path, size) if path else font_for(ch, size, bold=bold)


def mixed_length(draw: ImageDraw.ImageDraw, text: str, size: int, bold: bool = False) -> float:
    return sum(draw.textlength(ch, font=font_for_char(ch, size, bold)) for ch in text)


def draw_mixed(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, size: int, fill, bold: bool = False) -> None:
    x, y = xy
    for ch in text:
        font = font_for_char(ch, size, bold)
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font)


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


# Must not start a line (行首禁则). Glue these to the previous character.
_CJK_NO_START = set(
    "，。、．·？！；：…—～％‰°℃"
    "」』）】》〉’”"
    ",.;:!?)]}%”'"
)
# Must not end a line. Glue the next character onto this mark.
_CJK_NO_END = set("「『（【《〈“‘([{")


def _cjk_tokens(text: str) -> list[str]:
    """Cluster each character with trailing punctuation so 。 never wraps alone."""
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in _CJK_NO_END:
            buf = ch
            i += 1
            if i < n:
                buf += text[i]
                i += 1
            while i < n and text[i] in _CJK_NO_START:
                buf += text[i]
                i += 1
            tokens.append(buf)
            continue
        buf = ch
        i += 1
        while i < n and text[i] in _CJK_NO_START:
            buf += text[i]
            i += 1
        tokens.append(buf)
    return tokens


def wrap(draw, text, font, max_w, bold: bool = False) -> list[str]:
    text = sanitize(text or "").strip()
    if not text:
        return []
    if "\n" in text:
        out: list[str] = []
        for part in text.split("\n"):
            out.extend(wrap(draw, part, font, max_w, bold) or ([part] if part.strip() else []))
        return out
    size = int(getattr(font, "size", 36) or 36)
    cjk = any(is_cjk(ch) for ch in text)
    if not cjk:
        words = text.split()
        lines, cur = [], ""
        for word in words:
            trial = (cur + " " + word).strip()
            if not cur or mixed_length(draw, trial, size, bold) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines
    lines, cur = [], ""
    for tok in _cjk_tokens(text):
        trial = cur + tok
        if cur and mixed_length(draw, trial, size, bold) > max_w:
            lines.append(cur)
            cur = tok
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def fit_font(draw, text: str, size: int, max_w: int, bold: bool = True, min_size: int = 28) -> ImageFont.FreeTypeFont:
    text = sanitize(text or "")
    size = max(min_size, int(size))
    while size > min_size:
        font = font_for(text, size, bold=bold)
        lines = wrap(draw, text, font, max_w, bold=bold)
        widest = max((mixed_length(draw, ln, size, bold) for ln in lines), default=0)
        if widest <= max_w:
            if len(lines) <= 3 or size <= min_size + 8:
                return font
        size -= 2
    return font_for(text, min_size, bold=bold)


def new_canvas(theme: dict):
    img = Image.new("RGB", (W, H), theme["bg"])
    draw = ImageDraw.Draw(img)
    if theme.get("blobs"):
        draw.ellipse([-200, 700, 520, 1280], fill=theme["wash"])
        draw.ellipse([1280, -260, 2100, 620], fill=theme["wash2"])
    if theme.get("corner"):
        draw.polygon([(W - 220, 0), (W, 0), (W, 220)], fill=theme["gold"])
    draw.rectangle([0, 0, 18, H], fill=theme["navy"])
    draw.rectangle([W - 18, 0, W, H], fill=theme["navy"])
    draw.rectangle([0, H - 18, W, H], fill=theme["navy"])
    draw._vf_img = img
    return img, draw


def _split_pair(text: str) -> tuple[str, str]:
    raw = sanitize(text or "")
    if "\n" not in raw:
        return raw.strip(), ""
    first, rest = raw.split("\n", 1)
    return first.strip(), rest.strip()


def _mostly_cjk(text: str) -> bool:
    chars = [ch for ch in text or "" if not ch.isspace()]
    if not chars:
        return False
    cjk = sum(1 for ch in chars if "\u4e00" <= ch <= "\u9fff")
    return cjk * 3 >= len(chars)


def _block_height(draw, text: str, size: int, max_w: int, bold: bool, gap: float = 1.12) -> tuple[list[str], int]:
    font = font_for(text, size, bold)
    lines = wrap(draw, text, font, max_w, bold=bold) or ([sanitize(text)] if text else [])
    return lines, int(size * gap) * max(1, len(lines)) if lines else 0


def _center(draw, box, text, font, fill, bold: bool = True, sub_fill=None) -> None:
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
            tw = mixed_length(draw, ln, size, bold)
            draw_mixed(draw, (x0 + (max_w - tw) / 2, ty), ln, size, fill, bold)
            ty += line_h
        return
    main = int(getattr(font, "size", DUAL["claim"][0]) or DUAL["claim"][0])
    main = min(main, DUAL["claim"][0])
    sub = DUAL["claim"][1]
    while main >= 32:
        p_lines, p_h = _block_height(draw, primary, main, max_w, True, 1.10)
        s_lines, s_h = _block_height(draw, secondary, sub, max_w, False, 1.08)
        if p_h + 8 + s_h <= box_h and len(p_lines) <= 2 and len(s_lines) <= 2:
            break
        main -= 2
        sub = max(22, sub - 1)
    p_lines, p_h = _block_height(draw, primary, main, max_w, True, 1.10)
    s_lines, s_h = _block_height(draw, secondary, sub, max_w, False, 1.08)
    total = p_h + (8 if s_lines else 0) + s_h
    ty = y0 + max(0, (box_h - total) / 2)
    for ln in p_lines:
        tw = mixed_length(draw, ln, main, True)
        draw_mixed(draw, (x0 + (max_w - tw) / 2, ty), ln, main, fill, True)
        ty += int(main * 1.10)
    ty += 8
    tone = sub_fill if sub_fill is not None else fill
    for ln in s_lines:
        tw = mixed_length(draw, ln, sub, False)
        draw_mixed(draw, (x0 + (max_w - tw) / 2, ty), ln, sub, tone, False)
        ty += int(sub * 1.08)


def draw_kicker(draw: ImageDraw.ImageDraw, kicker: str, theme: dict) -> None:
    if not kicker:
        return
    label = kicker.upper() if kicker.isascii() else kicker
    size = SCALE["kicker"]
    if len(label) > 18:
        size = 22
    tw = mixed_length(draw, label, size, bold=True)
    left, top, h = 64, 40, 56
    dot, gap, pad_l, pad_r = 18, 12, 16, 22
    text_x = left + pad_l + dot + gap
    right = min(W - 80, text_x + tw + pad_r)
    draw.rounded_rectangle([left, top, right, top + h], radius=h // 2, fill=theme["navy"])
    cy = top + h / 2
    draw.ellipse([left + pad_l, cy - dot / 2, left + pad_l + dot, cy + dot / 2], fill=theme["gold"])
    draw_mixed(draw, (text_x, top + 14), label, size, theme["bg"], bold=True)


def draw_footer(draw: ImageDraw.ImageDraw, title: str, index: int, n: int, theme: dict) -> None:
    """Short title at bottom-left, above the caption band. Dots stay bottom-right."""
    label = sanitize(title or "")
    gap, r = 18, 8
    total = n * (2 * r) + max(0, n - 1) * gap
    dots_left = W - 64 - total
    y_dots = H - 118
    max_w = max(200, dots_left - 80)
    size = SCALE["footer"]
    while size >= 16:
        tw = mixed_length(draw, label, size, bold=False)
        if tw <= max_w:
            break
        size -= 1
    if mixed_length(draw, label, size, bold=False) > max_w:
        while label and mixed_length(draw, label + "…", size, bold=False) > max_w:
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


def _latin_ok(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> bool:
    try:
        return draw.textlength("Ag", font=font) >= 12
    except Exception:
        return False


def draw_title(draw: ImageDraw.ImageDraw, title: str, theme: dict, y: int = 112) -> int:
    max_w = W - 200
    primary, secondary = _split_pair(title)
    if not secondary:
        f = fit_font(draw, primary, SCALE["title"], max_w, bold=True, min_size=64)
        size = int(getattr(f, "size", SCALE["title"]) or SCALE["title"])
        lines = wrap(draw, primary, f, max_w, bold=True) or [sanitize(primary)]
        line_h = int(size * 1.12)
        band_h = max(156, 32 + line_h * len(lines))
    else:
        main, sub = DUAL["title"]
        p_lines, p_h = _block_height(draw, primary, main, max_w, True, 1.08)
        s_lines, s_h = _block_height(draw, secondary, sub, max_w, False, 1.06)
        while main > 52 and (len(p_lines) > 2 or p_h + s_h + 36 > 220):
            main -= 2
            sub = max(28, sub - 1)
            p_lines, p_h = _block_height(draw, primary, main, max_w, True, 1.08)
            s_lines, s_h = _block_height(draw, secondary, sub, max_w, False, 1.06)
        band_h = min(220, max(168, 28 + p_h + 8 + s_h))
        size = main
        lines = p_lines
        line_h = int(main * 1.08)
        sub_lines = s_lines
        sub_size = sub
    draw.rectangle([0, y, W, y + band_h], fill=theme["navy"])
    draw.rectangle([0, y, 14, y + band_h], fill=theme["gold"])
    draw.rectangle([64, y + band_h - 16, 280, y + band_h - 10], fill=theme["gold"])
    if secondary:
        block = line_h * len(lines) + 6 + int(sub_size * 1.06) * max(1, len(sub_lines))
        yy = y + max(14, (band_h - block) // 2)
        for ln in lines:
            draw_mixed(draw, (64, yy), ln, size, theme["bg"], bold=True)
            yy += line_h
        yy += 6
        for ln in sub_lines:
            draw_mixed(draw, (64, yy), ln, sub_size, theme["gold"], bold=False)
            yy += int(sub_size * 1.06)
    else:
        yy = y + max(18, (band_h - line_h * len(lines)) // 2 - 4)
        for ln in lines:
            draw_mixed(draw, (64, yy), ln, size, theme["bg"], bold=True)
            yy += line_h
    return y + band_h + 20


def _tag(draw, x, y, text, theme) -> None:
    tf = font_for(text, SCALE["tag"], bold=True)
    draw.text((x, y), text, font=tf, fill=theme["gold"])


def _panel(draw, box, fill, theme, accent: bool = True) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle([x0, y0, x1, y1], radius=22, fill=fill)
    if accent:
        draw.rectangle([x0, y0, x0 + 14, y1], fill=theme["gold"])


def _fallback(code: str, table: dict) -> str:
    if code == "zh_hk":
        return table.get("zh_hk") or table.get("zh") or table.get("en") or ""
    if code == "zh":
        return table.get("zh") or table.get("en") or ""
    return table.get("en") or ""


def _show(stage: int | None, need: int) -> bool:
    return stage is None or stage >= need


def render_title_card(draw, beat, lesson, code, theme, second: str | None = None) -> None:
    title = field2(beat, "title", code, second) or field2(lesson, "title", code, second)
    kicker = resolve_kicker(beat, code)
    if second and second != code:
        other_k = resolve_kicker(beat, second)
        if other_k and other_k != kicker:
            kicker = f"{kicker}  {other_k}" if kicker else other_k
    max_w = W - 320
    primary, secondary = _split_pair(title)
    if secondary:
        main, sub = DUAL["hook"]
        p_lines, p_h = _block_height(draw, primary, main, max_w, True, 1.08)
        s_lines, s_h = _block_height(draw, secondary, sub, max_w, False, 1.06)
        while main > 60 and (len(p_lines) > 2 or p_h + s_h > 420):
            main -= 2
            sub = max(28, sub - 1)
            p_lines, p_h = _block_height(draw, primary, main, max_w, True, 1.08)
            s_lines, s_h = _block_height(draw, secondary, sub, max_w, False, 1.06)
        block = p_h + 12 + s_h
    else:
        font = fit_font(draw, primary, SCALE["hook"], max_w, bold=True, min_size=72)
        size = int(getattr(font, "size", SCALE["hook"]) or SCALE["hook"])
        p_lines = wrap(draw, primary, font, max_w, bold=True) or [sanitize(primary)]
        s_lines = []
        main, sub = size, 0
        block = int(size * 1.1) * len(p_lines)
    extra = 64 if kicker else 0
    top = (H - block - extra) / 2 - 20
    if kicker:
        label = kicker.upper() if kicker.isascii() else kicker
        ksize = 24 if len(label) > 16 else SCALE["kicker"]
        tw = mixed_length(draw, label, ksize, True)
        draw_mixed(draw, ((W - tw) / 2, top), label, ksize, theme["muted"], True)
        top += extra
    for ln in p_lines:
        tw = mixed_length(draw, ln, main, True)
        draw_mixed(draw, ((W - tw) / 2, top), ln, main, theme["navy"], True)
        top += int(main * 1.08)
    if s_lines:
        top += 10
        for ln in s_lines:
            tw = mixed_length(draw, ln, sub, False)
            draw_mixed(draw, ((W - tw) / 2, top), ln, sub, theme["muted"], False)
            top += int(sub * 1.06)
    rule_w = 140
    draw.rectangle([(W - rule_w) / 2, top + 18, (W + rule_w) / 2, top + 26], fill=theme["gold"])


def render_definition(draw, beat, code, y, theme, stage: int | None = None, second: str | None = None) -> None:
    formula_shared = (beat.get("formula") or "").strip()
    formula_main = (
        field_native(beat, "formula", code)
        or (formula_shared if code == "en" else "")
        or field_native(beat, "title", code)
    )
    formula_other = ""
    if second:
        formula_other = (
            field_native(beat, "formula", second)
            or (formula_shared if second == "en" else "")
            or field_native(beat, "title", second)
        )
        if formula_other == formula_main:
            formula_other = ""
    gloss_main = field_native(beat, "gloss", code)
    gloss_other = field_native(beat, "gloss", second) if second else ""
    keep_formula = bool(formula_main)
    box_y = y + 12
    box_h = 420
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "DEFINITION", "zh": "定义", "zh_hk": "定義"}.get(code, "DEFINITION")
    if second and second != code:
        other = {"en": "DEFINITION", "zh": "定义", "zh_hk": "定義"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 28, tag, theme)
    tex_main, tex_other = localized_tex(beat, code, second)
    if tex_main:
        from mathtex import paste_math

        reveal_gloss = bool(gloss_main) and (second or _show(stage, 2))
        bottom = box_y + box_h - (118 if reveal_gloss else 28)
        if tex_other:
            mid = box_y + 88 + (bottom - box_y - 88) // 2
            ok = paste_math(draw, (100, box_y + 78, W - 100, mid - 6), tex_main, theme["bg"], 40)
            paste_math(draw, (100, mid + 6, W - 100, bottom), tex_other, theme["gold"], 28)
        else:
            ok = paste_math(draw, (100, box_y + 78, W - 100, bottom), tex_main, theme["bg"], 44)
        if ok:
            if reveal_gloss:
                gf = fit_font(draw, gloss_main, SCALE["caption"], W - 240, bold=False, min_size=28)
                _center(draw, (100, box_y + box_h - 128, W - 100, box_y + box_h - 24), gloss_main, gf, theme["gold"], bold=False)
            return
    if second:
        lines = []
        if formula_main:
            lines.append((formula_main, 52, theme["bg"], True))
        if formula_other and formula_other != formula_main:
            lines.append((formula_other, 36, theme["gold"], False))
        if gloss_main:
            lines.append((gloss_main, 40, theme["bg"], True))
        if gloss_other and gloss_other != gloss_main:
            lines.append((gloss_other, 32, theme["gold"], False))
        if not lines:
            lines.append((field2(beat, "title", code, second), 48, theme["bg"], True))
        max_w = W - 220
        total = 0
        prepared = []
        for text, size, fill, bold in lines:
            font = fit_font(draw, text, size, max_w, bold=bold, min_size=28)
            size = int(getattr(font, "size", size) or size)
            wrapped = wrap(draw, text, font, max_w, bold=bold) or [text]
            prepared.append((wrapped, size, fill, bold))
            total += int(size * 1.16) * len(wrapped) + 12
        ty = box_y + 88 + max(0, (box_h - 120 - total) / 2)
        for wrapped, size, fill, bold in prepared:
            for ln in wrapped:
                tw = mixed_length(draw, ln, size, bold)
                draw_mixed(draw, (100 + (max_w - tw) / 2, ty), ln, size, fill, bold)
                ty += int(size * 1.16)
            ty += 12
        return
    gloss = gloss_main
    body = formula_main or gloss
    reveal_gloss = bool(gloss) and gloss != body and _show(stage, 2)
    inner_bottom = box_y + box_h - (118 if reveal_gloss else 28)
    ff = fit_font(draw, body, SCALE["formula"], W - 220, bold=True, min_size=40)
    _center(draw, (100, box_y + 70, W - 100, inner_bottom), body, ff, theme["bg"])
    if reveal_gloss:
        gf = fit_font(draw, gloss, SCALE["caption"], W - 240, bold=False, min_size=28)
        _center(draw, (100, box_y + box_h - 128, W - 100, box_y + box_h - 24), gloss, gf, theme["gold"], bold=False)


def render_two_column(draw, beat, code, y, theme, stage: int | None = None, second: str | None = None) -> None:
    left = field2(beat, "left", code, second) if _show(stage, 2) else ""
    right = field2(beat, "right", code, second) if _show(stage, 3) else ""
    box_y = y + 8
    box_h = 420
    mid = W // 2
    draw.rounded_rectangle([64, box_y, mid - 40, box_y + box_h], radius=24, fill=theme["navy"])
    draw.rounded_rectangle([mid + 40, box_y, W - 64, box_y + box_h], radius=24, fill=theme["emerald"])
    if _show(stage, 3):
        badge = [mid - 44, box_y + box_h // 2 - 44, mid + 44, box_y + box_h // 2 + 44]
        draw.ellipse(badge, fill=theme["gold"])
        vf = _font(FONT_LATIN_B, 28)
        tw = draw.textlength("VS", font=vf)
        draw.text((mid - tw / 2, box_y + box_h // 2 - 16), "VS", font=vf, fill=theme["navy"])
    for text, x0, x1, num in ((left, 64, mid - 40, "01"), (right, mid + 40, W - 64, "02")):
        nf = _font(FONT_LATIN_B, SCALE["index"])
        draw.text((x0 + 36, box_y + 28), num, font=nf, fill=theme["gold"])
        if text:
            lf = fit_font(draw, text, SCALE["claim"], x1 - x0 - 72, bold=True, min_size=40)
            _center(draw, (x0 + 24, box_y + 78, x1 - 24, box_y + box_h - 24), text, lf, theme["white"])


def render_takeaway(draw, beat, code, y, theme, stage: int | None = None, second: str | None = None) -> None:
    q1 = field2(beat, "q1", code, second)
    q2 = field2(beat, "q2", code, second)
    questions = [q for q in (q1, q2) if q]
    box_y = y + 8
    gap = 18
    available = H - 80 - box_y
    hbox = min(200, (available - gap * (len(questions) - 1)) // max(1, len(questions)))
    fills = (theme["navy"], theme["emerald"])
    for i, q in enumerate(questions):
        top = box_y + i * (hbox + gap)
        draw.rounded_rectangle([64, top, W - 64, top + hbox], radius=22, fill=fills[i % 2])
        draw.ellipse([96, top + hbox // 2 - 42, 180, top + hbox // 2 + 42], fill=theme["gold"])
        nf = _font(FONT_LATIN_B, 32)
        num = str(i + 1)
        tw = draw.textlength(num, font=nf)
        draw.text((138 - tw / 2, top + hbox // 2 - 20), num, font=nf, fill=theme["navy"])
        need = 2 if i == 0 else 3
        if q and _show(stage, need):
            qf = fit_font(draw, q, SCALE["claim"], W - 320, bold=True, min_size=40)
            _center(draw, (200, top + 16, W - 96, top + hbox - 16), q, qf, theme["white"])


def localized_tex(beat, code: str, second: str | None = None) -> tuple[str, str]:
    from mathtex import tex_field

    main = tex_field(beat, code)
    other = tex_field(beat, second) if second else ""
    if other == main:
        other = ""
    return main, other


def localized_formula(beat, code: str, second: str | None = None) -> tuple[str, str]:
    shared = (beat.get("formula_en") or beat.get("formula") or "").strip()
    main = field_native(beat, "formula", code) or (shared if code == "en" else "")
    other = ""
    if second:
        other = field_native(beat, "formula", second) or (shared if second == "en" else "")
        if other == main:
            other = ""
    return main, other


def render_formula(draw, beat, code, y, theme, stage: int | None = None, second: str | None = None) -> None:
    formula_main, formula_other = localized_formula(beat, code, second)
    if not formula_main:
        formula_main = field2(beat, "title", code, second)
    gloss_main = field_native(beat, "gloss", code)
    gloss_other = field_native(beat, "gloss", second) if second else ""
    box_y = y + 12
    box_h = 440
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "FORMULA", "zh": "公式", "zh_hk": "公式"}.get(code, "FORMULA")
    if second and second != code:
        other = {"en": "FORMULA", "zh": "公式", "zh_hk": "公式"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 28, tag, theme)
    tex_main, tex_other = localized_tex(beat, code, second)
    if tex_main:
        from mathtex import paste_math

        reveal_gloss = bool(gloss_main) and (second or _show(stage, 2))
        bottom = box_y + box_h - (120 if reveal_gloss else 32)
        if tex_other:
            mid = box_y + 90 + (bottom - box_y - 90) // 2
            ok = paste_math(draw, (100, box_y + 80, W - 100, mid - 6), tex_main, theme["bg"], 40)
            paste_math(draw, (100, mid + 6, W - 100, bottom), tex_other, theme["gold"], 28)
        else:
            ok = paste_math(draw, (100, box_y + 80, W - 100, bottom), tex_main, theme["bg"], 44)
        if ok:
            if reveal_gloss:
                gf = fit_font(draw, gloss_main, SCALE["caption"], W - 240, bold=False, min_size=28)
                _center(draw, (100, box_y + box_h - 128, W - 100, box_y + box_h - 24), gloss_main, gf, theme["gold"], bold=False)
            return
    if second:
        lines = []
        if formula_main:
            lines.append((formula_main, 52, theme["bg"], True))
        if formula_other:
            lines.append((formula_other, 36, theme["gold"], False))
        if gloss_main:
            lines.append((gloss_main, 36, theme["bg"], False))
        if gloss_other and gloss_other != gloss_main:
            lines.append((gloss_other, 32, theme["gold"], False))
        max_w = W - 220
        ty = box_y + 100
        for text, size, fill, bold in lines:
            font = fit_font(draw, text, size, max_w, bold=bold, min_size=28)
            size = int(getattr(font, "size", size) or size)
            for ln in wrap(draw, text, font, max_w, bold=bold) or [text]:
                tw = mixed_length(draw, ln, size, bold)
                draw_mixed(draw, (100 + (max_w - tw) / 2, ty), ln, size, fill, bold)
                ty += int(size * 1.16)
            ty += 10
        return
    gloss = gloss_main
    ff = fit_font(draw, formula_main, SCALE["formula"], W - 220, bold=True, min_size=40)
    bottom = box_y + box_h - (120 if gloss and _show(stage, 2) else 32)
    _center(draw, (100, box_y + 80, W - 100, bottom), formula_main, ff, theme["bg"])
    if gloss and _show(stage, 2):
        gf = fit_font(draw, gloss, SCALE["caption"], W - 240, bold=False, min_size=28)
        _center(draw, (100, box_y + box_h - 128, W - 100, box_y + box_h - 28), gloss, gf, theme["gold"], bold=False)


def render_example(draw, beat, code, y, theme, stage: int | None = None, second: str | None = None) -> None:
    setup = field2(beat, "setup", code, second) or field2(beat, "left", code, second)
    result = field2(beat, "result", code, second) or field2(beat, "right", code, second)
    box_y = y + 8
    box_h = 200
    labels = {
        "en": ("SETUP", "RESULT"),
        "zh": ("设定", "结果"),
        "zh_hk": ("設定", "結果"),
    }
    lab_setup, lab_result = labels.get(code, labels["en"])
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    _tag(draw, 108, box_y + 22, lab_setup, theme)
    if setup and _show(stage, 2):
        sf = fit_font(draw, setup, SCALE["body"], W - 220, bold=True, min_size=40)
        _center(draw, (100, box_y + 56, W - 100, box_y + box_h - 16), setup, sf, theme["white"])
    top = box_y + box_h + 20
    draw.rounded_rectangle([64, top, W - 64, top + box_h], radius=22, fill=theme["emerald"])
    draw.rectangle([64, top, 78, top + box_h], fill=theme["gold"])
    _tag(draw, 108, top + 22, lab_result, theme)
    if result and _show(stage, 3):
        rf = fit_font(draw, result, SCALE["body"], W - 220, bold=True, min_size=40)
        _center(draw, (100, top + 56, W - 100, top + box_h - 16), result, rf, theme["white"])


def render_three_column(draw, beat, code, y, theme, stage: int | None = None, second: str | None = None) -> None:
    cols = [field2(beat, f"col{i}", code, second) for i in (1, 2, 3)]
    if not any(cols):
        cols = [field2(beat, "left", code, second), field2(beat, "mid", code, second), field2(beat, "right", code, second)]
    box_y = y + 8
    box_h = 420
    gap = 28
    usable = W - 128
    width = (usable - 2 * gap) // 3
    fills = (theme["navy"], theme["ink"], theme["emerald"])
    for i, text in enumerate(cols):
        x0 = 64 + i * (width + gap)
        x1 = x0 + width
        draw.rounded_rectangle([x0, box_y, x1, box_y + box_h], radius=22, fill=fills[i])
        nf = _font(FONT_LATIN_B, SCALE["index"])
        draw.text((x0 + 28, box_y + 26), f"0{i + 1}", font=nf, fill=theme["gold"])
        need = 2 if i == 0 else 3
        if text and _show(stage, need):
            lf = fit_font(draw, text, SCALE["claim"], width - 48, bold=True, min_size=36)
            _center(draw, (x0 + 16, box_y + 78, x1 - 16, box_y + box_h - 24), text, lf, theme["white"])


def render_big_number(draw, beat, code, y, theme, stage: int | None = None, second: str | None = None) -> None:
    del stage
    number = str(beat.get("number") or beat.get("formula") or "").strip()
    unit_main = field_native(beat, "unit", code)
    unit_other = field_native(beat, "unit", second) if second else ""
    cap_main = field_native(beat, "caption", code) or field_native(beat, "gloss", code)
    cap_other = ""
    if second:
        cap_other = field_native(beat, "caption", second) or field_native(beat, "gloss", second)
        if cap_other == cap_main:
            cap_other = ""
    unit_line = " · ".join(part for part in (unit_main, unit_other) if part)
    box_y = y + 8
    box_h = 460
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "KEY NUMBER", "zh": "关键数字", "zh_hk": "關鍵數字"}.get(code, "KEY NUMBER")
    if second and second != code:
        other = {"en": "KEY NUMBER", "zh": "关键数字", "zh_hk": "關鍵數字"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 28, tag, theme)
    foot_h = 36
    if unit_line:
        foot_h += 56
    if cap_main:
        foot_h += 48
    if cap_other:
        foot_h += 40
    nf = fit_font(draw, number, SCALE["number"], W - 240, bold=True, min_size=64)
    _center(draw, (100, box_y + 70, W - 100, box_y + box_h - foot_h), number, nf, theme["bg"])
    extra_y = box_y + box_h - foot_h + 8
    max_w = W - 260
    if unit_line:
        uf = fit_font(draw, unit_line, SCALE["unit"], max_w, bold=True, min_size=28)
        _center(draw, (100, extra_y, W - 100, extra_y + 48), unit_line, uf, theme["gold"])
        extra_y += 52
    if cap_main:
        cf = fit_font(draw, cap_main, SCALE["caption"], max_w, bold=False, min_size=26)
        _center(draw, (100, extra_y, W - 100, extra_y + 40), cap_main, cf, theme["white"], bold=False)
        extra_y += 42
    if cap_other:
        cf = fit_font(draw, cap_other, 28, max_w, bold=False, min_size=24)
        _center(draw, (100, extra_y, W - 100, extra_y + 36), cap_other, cf, theme["gold"], bold=False)


def _agenda_items(beat: dict, code: str, second: str | None) -> list[str]:
    items = []
    for i in range(1, 5):
        text = field2(beat, f"item{i}", code, second)
        if text:
            items.append(text)
    return items


def render_module_open(draw, beat, lesson, code, theme, second: str | None = None) -> None:
    """Chapter plate: OPEN kicker, unit title, numbered agenda. Full frame, no header bar."""
    title = field2(beat, "title", code, second) or field2(lesson, "title", code, second)
    kicker = resolve_kicker(beat, code) or {"en": "OPEN", "zh": "开场", "zh_hk": "開場"}.get(code, "OPEN")
    if second and second != code:
        other_k = resolve_kicker(beat, second)
        if other_k and other_k != kicker:
            kicker = f"{kicker}  {other_k}"
    items = _agenda_items(beat, code, second)
    left, right = 120, W - 120
    max_w = right - left
    y = 88
    if kicker:
        label = kicker.upper() if kicker.isascii() else kicker
        draw_mixed(draw, (left, y), label, SCALE["kicker"], theme["gold"], True)
        y += 48
    primary, secondary = _split_pair(title)
    if secondary:
        main, sub = 78, 36
        p_lines, p_h = _block_height(draw, primary, main, max_w, True, 1.08)
        s_lines, s_h = _block_height(draw, secondary, sub, max_w, False, 1.06)
        lead = 1.18 if _mostly_cjk(primary) else 1.08
        for ln in p_lines:
            draw_mixed(draw, (left, y), ln, main, theme["navy"], True)
            y += int(main * lead)
        y += 20 if _mostly_cjk(primary) else 8
        for ln in s_lines:
            draw_mixed(draw, (left, y), ln, sub, theme["muted"], False)
            y += int(sub * 1.12)
    else:
        font = fit_font(draw, primary, 92, max_w, bold=True, min_size=64)
        size = int(getattr(font, "size", 92) or 92)
        lines = wrap(draw, primary, font, max_w, bold=True) or [sanitize(primary)]
        for ln in lines[:2]:
            draw_mixed(draw, (left, y), ln, size, theme["navy"], True)
            y += int(size * 1.08)
    y += 18
    draw.rectangle([left, y, left + 160, y + 8], fill=theme["gold"])
    y += 40
    n = max(1, len(items))
    row_h = 92 if n <= 3 else 78
    num_size = 28
    body_size = 48 if n <= 3 else 42
    for i, text in enumerate(items):
        cy = y + row_h // 2
        draw.ellipse([left, cy - 28, left + 56, cy + 28], fill=theme["gold"])
        nf = _font(FONT_LATIN_B, num_size)
        num = f"{i + 1:02d}"
        tw = draw.textlength(num, font=nf)
        draw.text((left + 28 - tw / 2, cy - 16), num, font=nf, fill=theme["navy"])
        primary_i, secondary_i = _split_pair(text)
        tf = fit_font(draw, primary_i, body_size, max_w - 88, bold=True, min_size=32)
        tsize = int(getattr(tf, "size", body_size) or body_size)
        cjk_row = _mostly_cjk(primary_i)
        lift = 16 if (secondary_i and cjk_row) else (10 if secondary_i else 0)
        draw_mixed(draw, (left + 76, cy - tsize // 2 - lift), primary_i, tsize, theme["navy"], True)
        if secondary_i:
            sub_y = cy + (22 if cjk_row else 12)
            draw_mixed(draw, (left + 76, sub_y), secondary_i, 26, theme["muted"], False)
        y += row_h + (8 if cjk_row and secondary_i else 0)


def render_module_close(draw, beat, lesson, code, theme, second: str | None = None) -> None:
    """Chapter plate: CLOSE kicker, unit title, claim panel, next-sitting line."""
    title = field2(beat, "title", code, second) or field2(lesson, "title", code, second)
    kicker = resolve_kicker(beat, code) or {"en": "CLOSE", "zh": "收束", "zh_hk": "收束"}.get(code, "CLOSE")
    if second and second != code:
        other_k = resolve_kicker(beat, second)
        if other_k and other_k != kicker:
            kicker = f"{kicker}  {other_k}"
    claim = field2(beat, "claim", code, second) or field2(beat, "", code, second)
    nxt = field2(beat, "next", code, second)
    left, right = 120, W - 120
    max_w = right - left
    y = 88
    if kicker:
        label = kicker.upper() if kicker.isascii() else kicker
        draw_mixed(draw, (left, y), label, SCALE["kicker"], theme["gold"], True)
        y += 48
    primary, secondary = _split_pair(title)
    if secondary:
        main, sub = 78, 36
        p_lines, _ = _block_height(draw, primary, main, max_w, True, 1.08)
        lead = 1.18 if _mostly_cjk(primary) else 1.08
        for ln in p_lines:
            draw_mixed(draw, (left, y), ln, main, theme["navy"], True)
            y += int(main * lead)
        y += 20 if _mostly_cjk(primary) else 8
        s_lines, _ = _block_height(draw, secondary, sub, max_w, False, 1.06)
        for ln in s_lines:
            draw_mixed(draw, (left, y), ln, sub, theme["muted"], False)
            y += int(sub * 1.06)
    else:
        font = fit_font(draw, primary, 92, max_w, bold=True, min_size=64)
        size = int(getattr(font, "size", 92) or 92)
        lines = wrap(draw, primary, font, max_w, bold=True) or [sanitize(primary)]
        for ln in lines[:2]:
            draw_mixed(draw, (left, y), ln, size, theme["navy"], True)
            y += int(size * 1.08)
    y += 18
    draw.rectangle([left, y, left + 160, y + 8], fill=theme["gold"])
    y += 36
    if claim:
        panel_h = 280 if nxt else 340
        draw.rounded_rectangle([left, y, right, y + panel_h], radius=24, fill=theme["navy"])
        cf = fit_font(draw, claim, 52, max_w - 80, bold=True, min_size=36)
        _center(draw, (left + 36, y + 28, right - 36, y + panel_h - 28), claim, cf, theme["white"])
        y += panel_h + 28
    if nxt:
        tag = {"en": "NEXT", "zh": "下一讲", "zh_hk": "下一講"}.get(code, "NEXT")
        if second and second != code:
            other = {"en": "NEXT", "zh": "下一讲", "zh_hk": "下一講"}.get(second)
            if other and other != tag:
                tag = f"{tag}  {other}"
        draw_mixed(draw, (left, y), tag, 24, theme["gold"], True)
        y += 36
        nf = fit_font(draw, nxt, 36, max_w, bold=False, min_size=28)
        nsize = int(getattr(nf, "size", 36) or 36)
        for ln in (wrap(draw, nxt, nf, max_w, bold=False) or [nxt])[:3]:
            draw_mixed(draw, (left, y), ln, nsize, theme["navy"], False)
            y += int(nsize * 1.2)


def render_steps(draw, beat, code, y, theme, stage: int | None = None, second: str | None = None) -> None:
    steps = [field2(beat, f"step{i}", code, second) for i in (1, 2, 3)]
    if not any(steps):
        steps = [field2(beat, f"col{i}", code, second) for i in (1, 2, 3)]
    box_y = y + 8
    box_h = 420
    gap = 28
    usable = W - 128
    width = (usable - 2 * gap) // 3
    for i, text in enumerate(steps):
        x0 = 64 + i * (width + gap)
        x1 = x0 + width
        fill = theme["navy"] if i != 1 else theme["emerald"]
        draw.rounded_rectangle([x0, box_y, x1, box_y + box_h], radius=22, fill=fill)
        draw.ellipse([x0 + width // 2 - 38, box_y + 28, x0 + width // 2 + 38, box_y + 104], fill=theme["gold"])
        nf = _font(FONT_LATIN_B, 32)
        num = str(i + 1)
        tw = draw.textlength(num, font=nf)
        draw.text((x0 + width // 2 - tw / 2, box_y + 48), num, font=nf, fill=theme["navy"])
        need = 2 if i == 0 else 3
        if text and _show(stage, need):
            lf = fit_font(draw, text, SCALE["claim"], width - 48, bold=True, min_size=36)
            _center(draw, (x0 + 16, box_y + 128, x1 - 16, box_y + box_h - 24), text, lf, theme["white"])
        if i < 2:
            ax = x1 + 4
            mid_y = box_y + 66
            draw.polygon([(ax, mid_y - 10), (ax + 18, mid_y), (ax, mid_y + 10)], fill=theme["gold"])


def _matrix_highlight(beat: dict) -> tuple[int, int] | None:
    raw = str(beat.get("highlight") or beat.get("highlight_cell") or "").strip().lower()
    raw = raw.replace("cell", "").replace(",", "").replace("-", "")
    if raw.startswith("c") and len(raw) >= 3 and raw[1].isdigit() and raw[2].isdigit():
        return int(raw[1]) - 1, int(raw[2]) - 1
    if raw in {"11", "12", "21", "22"}:
        return int(raw[0]) - 1, int(raw[1]) - 1
    return None


def render_payoff_matrix(draw, beat, code, y, theme, stage: int | None = None, second: str | None = None) -> None:
    """2x2 payoff grid. Stages: names → labels → (1,1) → full → gold ring."""
    row_p = field2(beat, "row_player", code, second)
    col_p = field2(beat, "col_player", code, second)
    rows = [field2(beat, "row1", code, second), field2(beat, "row2", code, second)]
    cols = [field2(beat, "col1", code, second), field2(beat, "col2", code, second)]
    cells = [
        [str(beat.get("c11") or "").strip(), str(beat.get("c12") or "").strip()],
        [str(beat.get("c21") or "").strip(), str(beat.get("c22") or "").strip()],
    ]
    note = field2(beat, "note", code, second)
    box_y = y + 8
    box_h = 440
    left, right = 64, W - 64
    _panel(draw, (left, box_y, right, box_y + box_h), theme["navy"], theme)
    tag = {"en": "PAYOFFS", "zh": "报酬", "zh_hk": "報酬"}.get(code, "PAYOFFS")
    if second and second != code:
        other = {"en": "PAYOFFS", "zh": "报酬", "zh_hk": "報酬"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 20, tag, theme)
    show_names = _show(stage, 1)
    show_labels = _show(stage, 2)
    show_c11 = _show(stage, 3)
    show_all = _show(stage, 4)
    show_ring = stage is not None and stage >= 5
    grid_l, grid_t = left + 36, box_y + 72
    grid_r, grid_b = right - 36, box_y + box_h - (56 if note else 28)
    corner_w, head_h = 280, 88
    body_w = grid_r - grid_l - corner_w
    body_h = grid_b - grid_t - head_h
    cell_w, cell_h = body_w // 2, body_h // 2
    ink = theme["white"]
    mute = theme["gold"]
    if show_names:
        if col_p:
            cf = fit_font(draw, col_p, 26, body_w, bold=True, min_size=20)
            _center(draw, (grid_l + corner_w, grid_t - 4, grid_r, grid_t + 28), col_p, cf, mute, bold=True)
        if row_p:
            rf = fit_font(draw, row_p, 22, corner_w - 16, bold=True, min_size=18)
            _center(draw, (grid_l, grid_t + 28, grid_l + corner_w, grid_t + head_h), row_p, rf, mute, bold=True)
    # header band
    draw.rectangle([grid_l + corner_w, grid_t + 28, grid_r, grid_t + head_h], outline=mute, width=2)
    draw.rectangle([grid_l, grid_t + head_h, grid_l + corner_w, grid_b], outline=mute, width=2)
    if show_labels:
        for j, label in enumerate(cols):
            if not label:
                continue
            x0 = grid_l + corner_w + j * cell_w
            hf = fit_font(draw, label, 28, cell_w - 16, bold=True, min_size=20)
            _center(draw, (x0, grid_t + 28, x0 + cell_w, grid_t + head_h), label, hf, ink, bold=True)
        for i, label in enumerate(rows):
            if not label:
                continue
            y0 = grid_t + head_h + i * cell_h
            hf = fit_font(draw, label, 28, corner_w - 20, bold=True, min_size=20)
            _center(draw, (grid_l + 8, y0, grid_l + corner_w - 8, y0 + cell_h), label, hf, ink, bold=True)
    boxes = []
    for i in range(2):
        for j in range(2):
            x0 = grid_l + corner_w + j * cell_w
            y0 = grid_t + head_h + i * cell_h
            boxes.append((i, j, x0, y0, x0 + cell_w, y0 + cell_h))
            draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], outline=theme["gold"], width=1)
            visible = show_all or (show_c11 and i == 0 and j == 0)
            text = cells[i][j]
            if visible and text:
                tf = fit_font(draw, text, 52, cell_w - 24, bold=True, min_size=32)
                _center(draw, (x0 + 8, y0 + 8, x0 + cell_w - 8, y0 + cell_h - 8), text, tf, ink, bold=True)
    if show_ring:
        mark = _matrix_highlight(beat) or (0, 1)
        for i, j, x0, y0, x1, y1 in boxes:
            if (i, j) == mark:
                draw.rounded_rectangle([x0 + 6, y0 + 6, x1 - 6, y1 - 6], radius=10, outline=theme["gold"], width=6)
                break
    if note and show_all:
        nf = fit_font(draw, note, 24, right - left - 80, bold=False, min_size=18)
        _center(draw, (left + 40, box_y + box_h - 52, right - 40, box_y + box_h - 8), note, nf, mute, bold=False)


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
}


def stage_count(beat: dict) -> int:
    if beat.get("stage") is False:
        return 1
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
    if s <= 0:
        return [total]
    parts = [p * total / s for p in parts]
    parts[-1] = total - sum(parts[:-1])
    if parts[-1] < MIN_SLICE:
        return [total]
    return parts


def render_beat(
    beat: dict,
    lesson: dict,
    index: int,
    n: int,
    lang_labels: str = "en",
    theme: dict | None = None,
    stage: int | None = None,
    second_lang: str | None = None,
) -> Image.Image:
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


def render_lesson_slides(
    lesson: dict,
    out_dir: Path,
    label_lang: str = "en",
    theme: dict | None = None,
    second_lang: str | None = None,
) -> list[Path]:
    theme = theme or load_theme(None)
    print(
        "slide fonts: latin=",
        FONT_LATIN or "(none)",
        "latin_bold=",
        FONT_LATIN_B or "(none)",
        "cjk=",
        FONT_CJK or "(none)",
    )
    if not FONT_CJK:
        print("warning: no CJK font found; Chinese on slides will be boxes")
    for err in scan_lesson(lesson):
        print("glyph:", err)
    out_dir.mkdir(parents=True, exist_ok=True)
    beats = lesson["beats"]
    paths: list[Path] = []
    code = label_lang
    for i, beat in enumerate(beats, start=1):
        path = out_dir / f"{i:02d}_{beat['id']}.png"
        mark = beat_stamp(beat, lesson, code, second_lang, theme, None)
        if stamp_ok(path, mark):
            print(f"slides: reuse beat {i}/{len(beats)} {beat['id']}")
        else:
            img = render_beat(
                beat, lesson, i, len(beats), lang_labels=label_lang, theme=theme, second_lang=second_lang
            )
            img.save(path, "PNG")
            write_mark(path, mark)
        paths.append(path)
    return paths


def write_stage_slides(
    lesson: dict,
    out_dir: Path,
    label_lang: str,
    durations: list[float],
    theme: dict | None = None,
    force: bool = False,
    second_lang: str | None = None,
) -> tuple[list[Path], list[float]]:
    """Full preview PNGs stay as-is. Extra _sN stills feed the silent master."""
    theme = theme or load_theme(None)
    slides: list[Path] = []
    slices: list[float] = []
    beats = lesson["beats"]
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, (beat, dur) in enumerate(zip(beats, durations), start=1):
        plan = stage_plan(beat, dur, force=force)
        holds = slice_durations(dur, plan)
        base = out_dir / f"{i:02d}_{beat['id']}.png"
        if plan == [0]:
            if not base.exists():
                render_beat(beat, lesson, i, len(beats), label_lang, theme, second_lang=second_lang).save(base)
            slides.append(base)
            slices.append(float(dur))
            continue
        for stage, hold in zip(plan, holds):
            dest = out_dir / f"{i:02d}_{beat['id']}_s{stage}.png"
            mark = beat_stamp(beat, lesson, label_lang, second_lang, theme, stage)
            if not stamp_ok(dest, mark):
                render_beat(
                    beat, lesson, i, len(beats), label_lang, theme, stage=stage, second_lang=second_lang
                ).save(dest)
                write_mark(dest, mark)
            slides.append(dest)
            slices.append(hold)
    return slides, slices


def stills_for_beat(
    out_dir: Path,
    index: int,
    beat: dict,
    plan: list[int],
) -> list[Path]:
    stem = f"{index:02d}_{beat['id']}"
    if plan == [0]:
        return [out_dir / f"{stem}.png"]
    paths = [out_dir / f"{stem}_s{stage}.png" for stage in plan]
    if any(not p.is_file() for p in paths):
        fallback = out_dir / f"{stem}.png"
        paths = [p if p.is_file() else fallback for p in paths]
        if fallback.is_file():
            return paths
        have = [p for p in paths if p.is_file()]
        return have or paths
    return paths

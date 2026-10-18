#!/usr/bin/env python3
"""Render language-neutral (or bilingual-label) 1920x1080 beat slides."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from glyphs import font_path_for_char, is_cjk, paints, sanitize
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
    "table_grid": 3, "series": 3, "rank_line": 3, "freq_bars": 3, "balance_line": 3, "box_line": 3, "dev_bars": 3, "ratio_bars": 3, "quad_scatter": 3, "schematic_chart": 3, "dag": 3, "pair": 3, "pair_chart": 3, "pair_box": 3, "pair_slope": 3, "redraw": 3, "turns": 3, "shrink": 3, "mix": 3, "coin": 3,
}
MIN_STAGE_BEAT = 5.0
MIN_SLICE = 1.2
LAYOUT_VERSION = "2026-10-18-quad-ruler-v1"


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
    """Digits and operators stay ASCII in every line.

    The old full-width swap made numbers in Chinese lines wide, spaced out,
    and unlike the same number on a pure-math line. Kept as a hook.
    """
    return ch


def _clusters(chunk: str) -> list[str]:
    """Group a base character with its combining marks (X + macron = X̄).

    Drawing a combining mark on its own makes the shaper paint a dotted circle.
    """
    out: list[str] = []
    for ch in chunk:
        if ch in "\n\r":
            continue
        if out and unicodedata.combining(ch):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _runs(text: str) -> list[tuple[str, str]]:
    """_script_chunks merged into runs of one kind, so a mark stays with its base."""
    out: list[tuple[str, str]] = []
    for kind, chunk in _script_chunks(text):
        if out and out[-1][0] == kind:
            out[-1] = (kind, out[-1][1] + chunk)
        else:
            out.append((kind, chunk))
    return out


def _one_line(text: str) -> str:
    """A bilingual pair painted on one line keeps a visible gap, not a run-on."""
    return re.sub(r"\s*\n\s*", "   ", text or "")


_PAIR_GAP = re.compile(r"(\s{2,})")


def _cjk_pieces(text: str) -> list[tuple[str, bool]]:
    """Split a painted line at the bilingual joiner (2+ spaces).

    Each piece says whether it holds CJK. Latin inside a CJK piece is drawn to
    match the CJK face; an English piece of a one-line pair keeps its own face.
    """
    return [(p, any(is_cjk(c) for c in p)) for p in _PAIR_GAP.split(text) if p]


def _equation_piece(piece: str) -> bool:
    """An equation with a unit word ("1,400 / 4 = 350 杯") keeps the Latin face,
    so it matches the pure-math line above it; only its baseline moves."""
    return any(op in piece for op in "=≈") and sum(1 for c in piece if is_cjk(c)) <= 3


def _cjk_face_path(bold: bool) -> str:
    return font_path_for_char("\u56fd", bold=bold)


def _cjk_face_has(ch: str, bold: bool) -> bool:
    """Printable ASCII the CJK face itself can paint (YaHei / Noto digits)."""
    if not ch or len(ch) != 1 or not ch.isascii() or not ch.isprintable() or ch.isspace():
        return False
    path = _cjk_face_path(bold)
    return bool(path) and paints(path, ch)


_LATIN_K: dict = {}


def _latin_k(bold: bool) -> float:
    """Scale for a Latin fallback face inside CJK text, so digit height matches
    the CJK face's own digit-to-ideograph ratio (about 0.93 of the ideograph top)."""
    hit = _LATIN_K.get(bold)
    if hit is not None:
        return hit
    k = 1.0
    try:
        cjk = _font(_cjk_face_path(bold), 100)
        lat = _font(font_path_for_char("0", bold=bold), 100)
        ideo = -cjk.getbbox("\u56fd", anchor="ls")[1]
        digit = -lat.getbbox("0", anchor="ls")[1]
        if ideo > 0 and digit > 0:
            k = max(0.85, min(1.0, 0.93 * ideo / digit))
    except Exception:
        k = 1.0
    _LATIN_K[bold] = k
    return k


def _mixed_face(cl: str, size: int, bold: bool, line_cjk: bool, piece_cjk: bool, equation: bool = False):
    """(font, dy) for one cluster of a painted line.

    In a line with CJK, Latin is put on the CJK baseline (not top-aligned on its
    own ascent, which floats digits up). Inside a CJK piece, digits and letters
    use the CJK face when it has them, else the Latin face scaled to match.
    """
    ch = cl[0]
    if not line_cjk or is_cjk(ch):
        return font_for_char(ch, size, bold), 0.0
    if piece_cjk and not equation and _cjk_face_has(ch, bold) and all(_cjk_face_has(c, bold) or unicodedata.combining(c) for c in cl):
        return _font(_cjk_face_path(bold), size), 0.0
    sz = max(10, int(round(size * (_latin_k(bold) if piece_cjk and not equation else 1.0))))
    font = font_for_char(ch, sz, bold)
    try:
        cjk_asc = _font(_cjk_face_path(bold), size).getmetrics()[0]
        dy = float(cjk_asc - font.getmetrics()[0])
    except Exception:
        dy = size * 0.10
    return font, dy


def mixed_length(draw: ImageDraw.ImageDraw, text: str, size: int, bold: bool = False) -> float:
    width = 0.0
    text = _one_line(text)
    line_cjk = any(is_cjk(c) for c in text)
    for piece, piece_cjk in _cjk_pieces(text):
        eq = _equation_piece(piece)
        for kind, chunk in _runs(piece):
            sub = max(10, int(size * 0.62)) if kind == "sub" else size
            for cl in _clusters(chunk):
                shown = _match_cjk_digit(cl, text)
                if kind == "sub":
                    font = font_for_char(shown[0], sub, bold)
                else:
                    font, _ = _mixed_face(shown, size, bold, line_cjk, piece_cjk, eq)
                width += draw.textlength(shown, font=font)
    return width


def draw_mixed(draw, xy, text, size, fill, bold: bool = False) -> None:
    x, y = xy
    text = _one_line(text)
    line_cjk = any(is_cjk(c) for c in text)
    for piece, piece_cjk in _cjk_pieces(text):
        eq = _equation_piece(piece)
        for kind, chunk in _runs(piece):
            if kind == "sub":
                sub = max(10, int(size * 0.62))
                yy = y + size * 0.32
                for cl in _clusters(chunk):
                    shown = _match_cjk_digit(cl, text)
                    font = font_for_char(shown[0], sub, bold)
                    draw.text((x, yy), shown, font=font, fill=fill)
                    x += draw.textlength(shown, font=font)
                continue
            for cl in _clusters(chunk):
                shown = _match_cjk_digit(cl, text)
                font, dy = _mixed_face(shown, size, bold, line_cjk, piece_cjk, eq)
                draw.text((x, y + dy), shown, font=font, fill=fill)
                x += draw.textlength(shown, font=font)


_MATH_KEEP = set("0123456789=+-−×÷/*^()%.,<>≤≥±√²³⁴₁₂₃₄ᵢ")


def _math_skeleton(text: str) -> tuple[str, int]:
    """Digits and operators of a line, plus how many word characters it had."""
    keep, words = [], 0
    for ch in str(text or ""):
        if ch in _MATH_KEEP:
            keep.append(ch)
        elif ch.isalpha() or is_cjk(ch):
            words += 1
    return "".join(keep).strip(".,"), words


def same_math(a: str, b: str) -> bool:
    """Two lines are the same equation when only a unit word differs.

    "1,400 / 4 = 350 cups" and "1,400 / 4 = 350 杯" print once on a bilingual card.
    """
    if "\n" in (a or "") or "\n" in (b or ""):
        # a multi-line formula prints once when every line is the same
        # (or the same equation up to a unit word) in both languages
        la, lb = (a or "").split("\n"), (b or "").split("\n")
        if len(la) != len(lb):
            return False
        hit = False
        for x, y in zip(la, lb):
            if x.strip() == y.strip():
                continue
            if not same_math(x, y):
                return False
            hit = True
        return hit or la == lb
    sa, wa = _math_skeleton(a)
    sb, wb = _math_skeleton(b)
    if not sa or sa != sb or "=" not in sa or not any(c.isdigit() for c in sa):
        return False
    return wa <= 8 and wb <= 8


def field2(obj: dict, stem: str, code: str, second: str | None = None) -> str:
    primary = field_native(obj, stem, code) or (field(obj, stem, code) if code == "en" else "")
    if not second or second == code:
        return primary
    other = field_native(obj, stem, second) or (field(obj, stem, second) if second == "en" else "")
    if not other or other == primary or (primary and same_math(primary, other)):
        return primary
    if not primary:
        return other
    return primary + "\n" + other


_CJK_NO_START = set("，。、．·？！；：…—～％‰°℃」』）】》〉’”" + ",.;:!?)]}%\"'")
_CJK_NO_END = set("「『（【《〈“‘([{")


def _glue_char(ch: str) -> bool:
    """Characters that belong to one unbreakable Latin / number token:
    letters, digits, decimal points, thousands commas, %, units, sub/superscripts,
    combining marks (x̄)."""
    if not ch or ch.isspace() or is_cjk(ch):
        return False
    if unicodedata.combining(ch):
        return True
    if ch.isascii():
        return ch.isalnum() or ch in ".,%'_/$-+#&"
    cat = unicodedata.category(ch)
    return cat[0] in ("L", "N") or ch in "×−·°℃‰€£¥₹’"


_BREAK_AFTER = set("，。、；：？！…—）」』】》〉,.;:!?) ")


def _cjk_tokens(text: str) -> list[str]:
    """Split mixed CJK text into wrap tokens.

    * a run of Latin letters / digits / commas / decimal points / units is one token,
      so '4,000', '12.5%', 'x̄' and 'Shop' never split;
    * each CJK character is its own token;
    * a space sticks to the token before it (a break after it is allowed);
    * closing punctuation never starts a line (kinsoku): it sticks to the token
      before it; opening brackets stick to the token after them.
    """
    raw: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if _glue_char(ch):
            j = i + 1
            while j < n and (_glue_char(text[j]) or (text[j] in ".," and j + 1 < n and text[j + 1].isdigit())):
                j += 1
            # A number keeps its one-character CJK unit or measure word (250杯, 5天, 4間).
            if any(c.isdigit() for c in text[i:j]) and j < n and is_cjk(text[j]):
                j += 1
            raw.append(text[i:j]); i = j
        else:
            raw.append(ch); i += 1
    tokens: list[str] = []
    pending_open = ""
    for tok in raw:
        if tok.isspace() or tok in _CJK_NO_START:
            if tokens:
                tokens[-1] += tok
            elif not tok.isspace():
                pending_open += tok
            continue
        if tok in _CJK_NO_END:
            pending_open += tok
            continue
        tokens.append(pending_open + tok)
        pending_open = ""
    if pending_open:
        if tokens:
            tokens[-1] += pending_open
        else:
            tokens.append(pending_open)
    return tokens


def _wrap_tokens(draw, tokens: list[str], size: int, max_w: int, bold: bool) -> list[str]:
    """Greedy fill, but when a line overflows, step back to the last space or
    punctuation break in the back 45% of the line rather than splitting two CJK
    characters of one phrase."""
    lines: list[str] = []
    cur: list[str] = []
    for tok in tokens:
        trial = "".join(cur + [tok])
        if cur and mixed_length(draw, trial.rstrip(), size, bold) > max_w:
            cut = len(cur)
            floor = max(1, int(len(cur) * 0.55))
            for k in range(len(cur) - 1, floor - 1, -1):
                if cur[k - 1][-1:] in _BREAK_AFTER or cur[k - 1][-1:].isspace():
                    cut = k
                    break
            lines.append("".join(cur[:cut]).strip())
            cur = cur[cut:] + [tok]
            while len(cur) > 1 and mixed_length(draw, "".join(cur).rstrip(), size, bold) > max_w:
                lines.append("".join(cur[:-1]).strip())
                cur = cur[-1:]
        else:
            cur.append(tok)
    if cur:
        lines.append("".join(cur).strip())
    return [ln for ln in lines if ln]


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
        return _wrap_tokens(draw, _cjk_tokens(text), size, max_w, bold) or [text]
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


def _equation_line(line: str) -> bool:
    """A short equation ("10,900 / 5 = 2,180", "平方之和 = 10,900") is one
    unbreakable unit: the font shrinks before the line is allowed to wrap."""
    line = (line or "").strip()
    if not line or len(line) > 40 or sum(line.count(op) for op in "=≈") != 1:
        return False
    if sum(1 for c in line if is_cjk(c)) > 6:
        return False
    rhs = re.split(r"[=≈]", line, maxsplit=1)[1]
    # the right side is a result (a number, maybe a short unit), not a sentence
    return any(c.isdigit() for c in rhs) and sum(1 for c in rhs if c.isascii() and c.isalpha()) <= 5


_EQ_SHRINK = 0.7  # an equation may shrink to 70% of the fitted size to stay on one line


def _equations_fit(draw, text: str, size: int, max_w: int, bold: bool) -> bool:
    for part in (text or "").split("\n"):
        for piece in _PAIR_GAP.split(part):
            if _equation_line(piece) and mixed_length(draw, piece.strip(), size, bold) > max_w:
                return False
    return True


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
            if _equations_fit(draw, text, size, max_w, bold):
                return font
            lo = max(floor, int(size * _EQ_SHRINK))
            for alt in range(size - 2, lo - 1, -2):
                if _equations_fit(draw, text, alt, max_w, bold):
                    return font_for(text, alt, bold=bold)
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
    p_lh = int(main * max(1.12, _line_factor(primary) - 0.04))
    block = p_lh * len(p_lines) + 10 + int(sub * 1.08) * len(s_lines)
    ty = y0 + max(0, (box_h - block) / 2)
    for ln in p_lines:
        tw = mixed_length(draw, ln, main, True)
        draw_mixed(draw, (x0 + (max_w - tw) / 2, ty), ln, main, fill, True)
        ty += p_lh
    ty += 10
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
        ksize = 26 if len(kicker_label) > 16 else 32
    # Measure the block, then center it vertically on the slide.
    if secondary:
        # One line as large as 140 / 64 when it fits; otherwise the old two-line fit.
        pf = fit_font(draw, primary, 140, max_w, True, 100, 1)
        if len(wrap(draw, primary, pf, max_w, True) or [primary]) > 1 or mixed_length(draw, primary, int(getattr(pf, "size", 100)), True) > max_w:
            pf = fit_font(draw, primary, DUAL["hook"][0], max_w, True, 64, 2)
        main = int(getattr(pf, "size", 100) or 100)
        p_lines = wrap(draw, primary, pf, max_w, True) or [primary]
        sub_cap = max(DUAL["hook"][1], min(64, int(main * 0.46)))
        sf = fit_font(draw, secondary, sub_cap, max_w, False, 40, 1)
        if mixed_length(draw, secondary, int(getattr(sf, "size", 40)), False) > max_w:
            sf = fit_font(draw, secondary, DUAL["hook"][1], max_w, False, 32, 2)
        sub = int(getattr(sf, "size", 40) or 40)
        s_lines = wrap(draw, secondary, sf, max_w, False) or [secondary]
        block = 0
        if kicker_label:
            block += 56
        block += int(main * max(1.08, _line_factor(primary) - 0.08)) * len(p_lines) + 16
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
            top += int(main * max(1.08, _line_factor(ln) - 0.08))
        top += 16
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


def _paint_formula_lines(draw, box, lines: list[str], fill, sub_lines=None, sub_fill=None) -> None:
    """Stack equation lines, wrapped to the panel. Optional second-language lines sit
    below in a smaller face, so a bilingual card never runs off the panel."""
    x0, y0, x1, y1 = box
    max_w = max(40, int(x1 - x0))
    box_h = max(40, int(y1 - y0))
    sub_lines = [ln for ln in (sub_lines or []) if ln]
    sub_fill = sub_fill or fill
    gap = 18
    size = 80 if not sub_lines else 68
    floor = 26

    def layout(sz):
        ssz = max(20, int(sz * 0.62))
        pw = [wrap(draw, ln, font_for(ln, sz, True), max_w, True) or [ln] for ln in lines]
        sw = [wrap(draw, ln, font_for(ln, ssz, False), max_w, False) or [ln] for ln in sub_lines]
        p_rows = [r for grp in pw for r in grp]
        s_rows = [r for grp in sw for r in grp]
        widest = max([mixed_length(draw, r, sz, True) for r in p_rows] + [mixed_length(draw, r, ssz, False) for r in s_rows] + [0])
        h = int(sz * 1.22) * len(p_rows) + gap * max(0, len(lines) - 1)
        if s_rows:
            h += 20 + int(ssz * 1.25) * len(s_rows) + gap // 2 * max(0, len(sub_lines) - 1)
        return ssz, p_rows, s_rows, h, widest

    while True:
        ssz, p_rows, s_rows, total, widest = layout(size)
        if (total <= box_h and widest <= max_w) or size <= floor:
            break
        size -= 2
    ty = y0 + max(0, (box_h - total) / 2)
    for ln in p_rows:
        tw = mixed_length(draw, ln, size, True)
        draw_mixed(draw, (x0 + (max_w - tw) / 2, ty), ln, size, fill, True)
        ty += int(size * 1.22)
    if s_rows:
        ty += 20
        for ln in s_rows:
            tw = mixed_length(draw, ln, ssz, False)
            draw_mixed(draw, (x0 + (max_w - tw) / 2, ty), ln, ssz, sub_fill, False)
            ty += int(ssz * 1.25)


def render_definition(draw, beat, code, y, theme, stage=None, second=None) -> None:
    body = field_native(beat, "formula", code) or beat.get("formula") or field_native(beat, "title", code) or ""
    gloss = field_native(beat, "gloss", code) or ""
    other = field_native(beat, "formula", second) if second else ""
    if other == body or (other and same_math(body, other)):
        other = ""
    gloss_other = field_native(beat, "gloss", second) if second else ""
    if gloss_other == gloss or (gloss_other and same_math(gloss, gloss_other)):
        gloss_other = ""
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
    gtxt = (gloss if not (second and gloss_other) else gloss + "\n" + gloss_other) if gloss else ""
    g_lay = _block_layout(draw, gtxt, W - 240, 150, 40 if gloss_other else 44, 24, 0.7, 2) if gtxt else None
    gloss_band = (g_lay["h"] + 48) if (reveal and g_lay) else 28
    inner_bottom = box_y + box_h - gloss_band
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
    # Judge that on the primary body only: a bilingual pair is not two equations.
    if len(_formula_lines(body)) >= 2:
        tex, tex2 = "", ""
    box = (100, box_y + 70, W - 100, inner_bottom)
    if _show(stage, 1) and (tex or tex2):
        try:
            from mathtex import paste_math

            if tex and tex2:
                mid = (box[1] + box[3]) // 2
                painted = paste_math(draw, (box[0], box[1], box[2], mid - 6), tex, theme["bg"], 56)
                painted = paste_math(draw, (box[0], mid + 6, box[2], box[3]), tex2, theme["bg"], 44) or painted
            elif tex:
                # formula_tex is language-neutral; the bilingual card shows it once, as mono does.
                painted = paste_math(draw, box, tex, theme["bg"], 64)
        except Exception:
            painted = False
    if _show(stage, 1) and body and not painted:
        lines = _formula_lines(body)
        sub = _formula_lines(other) if (second and other) else []
        if len(lines) >= 2 or sub:
            _paint_formula_lines(draw, box, lines, theme["bg"], sub_lines=sub, sub_fill=theme["gold"])
        else:
            ff = fit_font(draw, body, 84, W - 220, True, 36, 4, max(80, inner_bottom - box_y - 80))
            _center(draw, box, body, ff, theme["bg"])
    if reveal and g_lay:
        draw.line([(160, inner_bottom), (W - 160, inner_bottom)], fill=theme["gold"], width=2)
        _paint_block(draw, (120, inner_bottom + 8, W - 120, box_y + box_h - 16), g_lay, theme["gold"], theme["bg"])


def _is_cjk_text(text: str) -> bool:
    return any(is_cjk(ch) for ch in (text or ""))


def _block_layout(draw, text, max_w, max_h, cap, floor=24, sub_ratio=0.66, max_lines=3, sub_max_lines=2, bold=True, _shrinking=False):
    """Largest primary size <= cap whose wrapped block (primary, then the second
    language below at sub_ratio) fits max_w x max_h. Returns a layout dict."""
    primary, secondary = _split_pair(text)
    primary = sanitize(primary or "")
    size = max(floor, int(cap))
    while True:
        ssz = max(16, int(size * sub_ratio)) if secondary else 0
        p_lines = wrap(draw, primary, font_for(primary, size, bold), max_w, bold) or ([primary] if primary else [])
        s_lines = (wrap(draw, secondary, font_for(secondary, ssz, False), max_w, False) or [secondary]) if secondary else []
        p_lh = int(size * (1.24 if _is_cjk_text(primary) else 1.12))
        s_lh = int(ssz * (1.24 if _is_cjk_text(secondary) else 1.14)) if secondary else 0
        gap = max(8, int(size * 0.2)) if (secondary and p_lines) else 0
        h = p_lh * len(p_lines) + gap + s_lh * len(s_lines)
        widest = max([mixed_length(draw, ln, size, bold) for ln in p_lines] + [mixed_length(draw, ln, ssz, False) for ln in s_lines] + [0])
        ok = widest <= max_w and len(p_lines) <= max_lines and len(s_lines) <= sub_max_lines and h <= max_h
        if ok and not _shrinking and not (_equations_fit(draw, primary, size, max_w, bold) and (not secondary or _equations_fit(draw, secondary, ssz, max_w, False))):
            lo = max(floor, int(size * _EQ_SHRINK))
            for alt in range(size - 2, lo - 1, -2):
                a_ssz = max(16, int(alt * sub_ratio)) if secondary else 0
                if _equations_fit(draw, primary, alt, max_w, bold) and (not secondary or _equations_fit(draw, secondary, a_ssz, max_w, False)):
                    trial = _block_layout(draw, text, max_w, max_h, alt, alt, sub_ratio, max_lines, sub_max_lines, bold, _shrinking=True)
                    if trial["w"] <= max_w and trial["h"] <= max_h:
                        return trial
                    break
        if ok or size <= floor:
            lay = {"size": size, "ssz": ssz, "p": p_lines, "s": s_lines, "p_lh": p_lh, "s_lh": s_lh, "gap": gap, "h": h, "w": widest, "bold": bold}
            if ok and len(p_lines) > 1 and not _shrinking:
                # Up to ~18% smaller if that removes a wrapped line (no orphan '0' or a
                # one-word last line). Siblings then share the smaller size via min().
                lo = max(floor, int(size * 0.82))
                for alt in range(size - 2, lo - 1, -2):
                    trial = _block_layout(draw, text, max_w, max_h, alt, alt, sub_ratio, len(p_lines) - 1, sub_max_lines, bold, _shrinking=True)
                    if len(trial["p"]) < len(p_lines) and trial["w"] <= max_w and trial["h"] <= max_h:
                        return trial
            return lay
        size -= 2


def _paint_block(draw, box, lay, fill, sub_fill=None, align="center", valign="center"):
    x0, y0, x1, y1 = box
    max_w = x1 - x0
    ty = y0 + (max(0, (y1 - y0) - lay["h"]) / 2 if valign == "center" else 0)
    for ln in lay["p"]:
        tw = mixed_length(draw, ln, lay["size"], lay["bold"])
        tx = x0 + (max_w - tw) / 2 if align == "center" else x0
        draw_mixed(draw, (tx, ty), ln, lay["size"], fill, lay["bold"])
        ty += lay["p_lh"]
    ty += lay["gap"]
    for ln in lay["s"]:
        tw = mixed_length(draw, ln, lay["ssz"], False)
        tx = x0 + (max_w - tw) / 2 if align == "center" else x0
        draw_mixed(draw, (tx, ty), ln, lay["ssz"], sub_fill or fill, False)
        ty += lay["s_lh"]


def _shared_layouts(draw, texts, max_w, max_h, cap, floor, sub_ratio, max_lines, sub_max_lines=2):
    """Fit every text, then lay all of them out at the smallest fitted size so
    sibling panels share one type size."""
    lays = [_block_layout(draw, t, max_w, max_h, cap, floor, sub_ratio, max_lines, sub_max_lines) if t else None for t in texts]
    sizes = [l["size"] for l in lays if l]
    if not sizes:
        return lays, 0
    common = min(sizes)
    lays = [_block_layout(draw, t, max_w, max_h, common, floor, sub_ratio, max_lines, sub_max_lines) if t else None for t in texts]
    return lays, max(l["h"] for l in lays if l)


def _tight_height(block_h, avail, floor, fill=0.56, pad=0):
    """Panel height so the text block fills about `fill` of it, never under floor
    and never past the content area."""
    want = int(block_h / fill) + pad if block_h else floor
    return max(min(avail, floor), min(avail, max(floor, want)))


def render_two_column(draw, beat, code, y, theme, stage=None, second=None) -> None:
    left_full = field2(beat, "left", code, second)
    right_full = field2(beat, "right", code, second)
    box_y = y + 8
    avail = max(360, CONTENT_BOTTOM - box_y)
    mid = W // 2
    pad_x = 56
    inner_w = (mid - 40 - 64) - 2 * pad_x
    dual = bool(second)
    cap, floor = (72, 28) if dual else (84, 32)
    lays, block = _shared_layouts(draw, [left_full, right_full], inner_w, int((avail - 72) * 0.72), cap, floor, 0.62, 3)
    panel_h = _tight_height(block, avail, 380, 0.56)
    top = box_y + int((avail - panel_h) * 0.4)
    bot = top + panel_h
    draw.rounded_rectangle([64, top, mid - 40, bot], radius=24, fill=theme["navy"])
    draw.rounded_rectangle([mid + 40, top, W - 64, bot], radius=24, fill=theme["emerald"])
    if _show(stage, 3):
        cy = top + panel_h // 2
        draw.ellipse([mid - 44, cy - 44, mid + 44, cy + 44], fill=theme["gold"])
        vf = _font(FONT_LATIN_B, 28)
        tw = draw.textlength("VS", font=vf)
        draw.text((mid - tw / 2, cy - 16), "VS", font=vf, fill=theme["navy"])
    if lays[0] and _show(stage, 2):
        _paint_block(draw, (64 + pad_x, top, mid - 40 - pad_x, bot), lays[0], theme["bg"], theme["gold"])
    if lays[1] and _show(stage, 3):
        _paint_block(draw, (mid + 40 + pad_x, top, W - 64 - pad_x, bot), lays[1], theme["white"], theme["bg"])


def render_takeaway(draw, beat, code, y, theme, stage=None, second=None) -> None:
    q1 = field2(beat, "q1", code, second)
    q2 = field2(beat, "q2", code, second)
    questions = [q for q in (q1, q2) if q]
    box_y = y + 8
    gap = 22
    avail = max(200, CONTENT_BOTTOM - box_y)
    k = max(1, len(questions))
    full = (avail - gap * (k - 1)) // k
    text_l, text_r = 212, W - 104
    dual = bool(second)
    cap, floor = (60, 28) if dual else (68, 32)
    lays, block = _shared_layouts(draw, questions, text_r - text_l, full - 40, cap, floor, 0.66, 2)
    hbox = _tight_height(block, full, 200, 0.6)
    total = hbox * k + gap * (k - 1)
    start = box_y + int((avail - total) * 0.4)
    fills = (theme["navy"], theme["emerald"])
    for i, q in enumerate(questions):
        top = start + i * (hbox + gap)
        draw.rounded_rectangle([64, top, W - 64, top + hbox], radius=22, fill=fills[i % 2])
        cy = top + hbox // 2
        draw.ellipse([100, cy - 44, 188, cy + 44], fill=theme["gold"])
        nf = _font(FONT_LATIN_B, 36)
        tw = draw.textlength(str(i + 1), font=nf)
        draw.text((144 - tw / 2, cy - 22), str(i + 1), font=nf, fill=theme["navy"])
        if lays[i] and _show(stage, 2 if i == 0 else 3):
            _paint_block(draw, (text_l, top, text_r, top + hbox), lays[i], theme["white"], theme["gold"] if i % 2 == 0 else theme["bg"])


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


def _paint_example_card(draw, box, fill, tag, lay, theme, show_body):
    x0, y0, x1, y1 = box
    _panel(draw, box, fill, theme)
    _tag(draw, x0 + 44, y0 + 20, tag, theme)
    if not show_body or not lay:
        return
    _paint_block(draw, (x0 + 44, y0 + 62, x1 - 40, y1 - 22), lay, theme["bg"], theme["gold"], align="left")


def render_example(draw, beat, code, y, theme, stage=None, second=None) -> None:
    setup = field2(beat, "setup", code, second) or field2(beat, "left", code, second)
    result = field2(beat, "result", code, second) or field2(beat, "right", code, second)
    tags = {"en": ("SETUP", "RESULT"), "zh": ("设定", "结果"), "zh_hk": ("設定", "結果")}
    lab_s, lab_r = tags.get(code, tags["en"])
    other_s, other_r = tags.get(second or "", ("", ""))
    box_y = y + 8
    gap = 20
    avail = max(380, CONTENT_BOTTOM - box_y)
    half = max(176, (avail - gap) // 2)
    inner_w = W - 64 - 40 - (64 + 44)
    dual = bool(second)
    cap, floor = (56, 26) if dual else (64, 28)
    lays, block = _shared_layouts(draw, [setup, result], inner_w, half - 62 - 26, cap, floor, 0.64, 3)
    card_h = _tight_height(block, half, 210, 0.62, 62)
    total = 2 * card_h + gap
    start = box_y + int((avail - total) * 0.4)
    _paint_example_card(draw, (64, start, W - 64, start + card_h), theme["navy"], _pair_tag(lab_s, second, other_s), lays[0], theme, _show(stage, 2))
    top = start + card_h + gap
    _paint_example_card(draw, (64, top, W - 64, top + card_h), theme["emerald"], _pair_tag(lab_r, second, other_r), lays[1], theme, _show(stage, 3))


def render_three_column(draw, beat, code, y, theme, stage=None, second=None) -> None:
    cols = [field2(beat, f"col{i}", code, second) for i in (1, 2, 3)]
    if not any(cols):
        cols = [field2(beat, "left", code, second), field2(beat, "mid", code, second), field2(beat, "right", code, second)]
    box_y = y + 8
    avail = max(360, CONTENT_BOTTOM - box_y)
    gap = 28
    width = (W - 128 - 2 * gap) // 3
    inner_w = width - 64
    dual = bool(second)
    cap, floor = (56, 26) if dual else (64, 28)
    lays, block = _shared_layouts(draw, cols, inner_w, avail - 100 - 40, cap, floor, 0.66, 5)
    panel_h = _tight_height(block, avail, 400, 0.62, 100)
    top = box_y + int((avail - panel_h) * 0.4)
    fills = (theme["navy"], theme["ink"], theme["emerald"])
    for i, text in enumerate(cols):
        x0 = 64 + i * (width + gap)
        draw.rounded_rectangle([x0, top, x0 + width, top + panel_h], radius=20, fill=fills[i % 3])
        draw.ellipse([x0 + width / 2 - 28, top + 24, x0 + width / 2 + 28, top + 80], fill=theme["gold"])
        nf = _font(FONT_LATIN_B, SCALE["index"])
        tw = draw.textlength(str(i + 1), font=nf)
        draw.text((x0 + width / 2 - tw / 2, top + 38), str(i + 1), font=nf, fill=theme["navy"])
        if lays[i] and _show(stage, i + 1):
            _paint_block(draw, (x0 + 32, top + 96, x0 + width - 32, top + panel_h - 28), lays[i], theme["white"], theme["gold"])


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


def _big_title_block(draw, primary, secondary, theme, top: int) -> int:
    """Left-aligned unit title with its second language below. Returns the next y."""
    font = fit_font(draw, primary, 92, W - 200, True, 56, 2)
    size = int(getattr(font, "size", 92) or 92)
    line_h = int(size * _line_factor(primary))
    for ln in wrap(draw, primary, font, W - 200, True) or [primary]:
        draw_mixed(draw, (80, top), ln, size, theme["navy"], True)
        top += line_h
    if secondary:
        sub = secondary.split("\n", 1)[0]
        sf = fit_font(draw, sub, 40, W - 200, False, 26, 1)
        ssz = int(getattr(sf, "size", 40) or 40)
        top += 10
        draw_mixed(draw, (80, top), sub, ssz, theme["muted"], False)
        top += int(ssz * _line_factor(sub)) + 6
    return top


def render_module_open(draw, beat, lesson, code, theme, second=None) -> None:
    title = field2(beat, "title", code, second) or field2(lesson, "title", code, second)
    primary, secondary = _split_pair(title)
    kicker = field2(beat, "kicker", code, second) or {"en": "OPEN", "zh": "开场", "zh_hk": "開場"}.get(code, "OPEN")
    draw_mixed(draw, (80, 80), kicker, SCALE["kicker"], theme["gold"], True)
    top = _big_title_block(draw, primary, secondary, theme, 160)
    items = _agenda_items(beat, code, second)
    dual = any(_split_pair(it)[1] for it in items)
    room = CONTENT_BOTTOM - (top + 16)
    per = room // max(1, len(items))
    main_sz = max(28, min(40, int(per * (0.42 if dual else 0.62))))
    sub_sz = max(22, int(main_sz * 0.72))
    for i, item in enumerate(items, start=1):
        main, sub = _split_pair(item)
        yy = top + 16
        label = f"{i:02d}  "
        draw_mixed(draw, (80, yy), label + main, main_sz, theme["navy"], True)
        indent = 80 + mixed_length(draw, label, main_sz, True)
        yy += int(main_sz * _line_factor(main)) + 4
        if sub:
            draw_mixed(draw, (indent, yy), sub, sub_sz, theme["muted"], False)
            yy += int(sub_sz * _line_factor(sub))
        top = yy + max(10, int(main_sz * 0.45))


def render_module_close(draw, beat, lesson, code, theme, second=None) -> None:
    title = field2(beat, "title", code, second) or field2(lesson, "title", code, second)
    claim = field2(beat, "claim", code, second)
    nxt = field2(beat, "next", code, second)
    kicker = field2(beat, "kicker", code, second) or {"en": "CLOSE", "zh": "收束", "zh_hk": "收束"}.get(code, "CLOSE")
    draw_mixed(draw, (80, 80), kicker, SCALE["kicker"], theme["gold"], True)
    primary, secondary = _split_pair(title)
    top = _big_title_block(draw, primary, secondary, theme, 160)
    if claim:
        _panel(draw, (64, top + 30, W - 64, top + 230), theme["navy"], theme)
        cf = fit_font(draw, claim, 52, W - 180, True, 32, 3)
        _center(draw, (100, top + 50, W - 100, top + 210), claim, cf, theme["white"])
        top += 250
    if nxt:
        label = field2(beat, "next_label", code, second) or {"en": "NEXT", "zh": "下一讲", "zh_hk": "下一講"}.get(code, "NEXT")
        lab_main, lab_sub = _split_pair(label)
        main, sub = _split_pair(nxt)
        yy = min(top + 20, 900)
        def _lab(t):
            return "" if not t else (f"{t}：" if any(is_cjk(c) for c in t) else f"{t}: ")
        head = _lab(lab_main)
        nf = fit_font(draw, head + main, 32, W - 180, False, 22, 1)
        nsz = int(getattr(nf, "size", 32) or 32)
        draw_mixed(draw, (80, yy), head + main, nsz, theme["muted"], False)
        if sub:
            sub_head = _lab(lab_sub)
            sf = fit_font(draw, sub_head + sub, 26, W - 180, False, 20, 1)
            ssz = int(getattr(sf, "size", 26) or 26)
            draw_mixed(draw, (80, yy + int(nsz * _line_factor(main)) + 8), sub_head + sub, ssz, theme["muted"], False)


def render_steps(draw, beat, code, y, theme, stage=None, second=None) -> None:
    items = []
    for i in range(1, 7):
        text = field2(beat, f"step{i}", code, second)
        ex = field2(beat, f"ex{i}", code, second)
        if text:
            items.append((text, ex))
    as_rows = str(beat.get("layout") or "").strip().lower() in ("rows", "stack")
    if len(items) <= 3 and not as_rows:
        steps = [text for text, _ex in items] + [""] * (3 - len(items))
        box_y = y + 8
        box_h = _fill_h(box_y, 360)
        gap = 28
        width = (W - 128 - 2 * gap) // 3
        fills = (theme["navy"], theme.get("panel") or theme["navy"], theme["emerald"])
        fonts = [fit_font(draw, t, SCALE["claim"], width - 48, True, 28, 5, box_h - 60) if t else None for t in steps]
        for i, text in enumerate(steps):
            x0 = 64 + i * (width + gap)
            draw.rounded_rectangle([x0, box_y, x0 + width, box_y + box_h], radius=20, fill=fills[i % 3])
            draw.rectangle([x0, box_y, x0 + 14, box_y + box_h], fill=theme["gold"])
            if text and _show(stage, i + 1):
                _center(draw, (x0 + 28, box_y + 36, x0 + width - 20, box_y + box_h - 24), text, fonts[i], theme["white"])
        return
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    gap = 12
    row_h = (box_h - 28 - gap * (len(items) - 1)) // len(items)
    bd = max(22, min(30, row_h // 4))
    text_x = 100 + 2 * bd + 28
    max_w = W - 88 - text_x - 28
    any_second = any(_split_pair(t)[1] for t, _e in items)
    any_ex = any(e for _t, e in items)
    # Size the text to the row, not a fixed 28 px: about 48/34 px on a five-row bilingual stack.
    budget = row_h - 16
    if any_second:
        base = int((budget - 4) / (1.18 + 0.72 * 1.08 + (0.62 * 1.1 if any_ex else 0)))
    else:
        base = int(budget / (1.08 + (0.62 * 1.1 if any_ex else 0)))
    base = max(24, min(60 if not any_second else 56, base)) if not as_rows else max(24, min(80 if not any_second else 70, base))
    for i, (text, ex) in enumerate(items):
        y0 = box_y + 14 + i * (row_h + gap)
        show = _show(stage, i + 1)
        fill = theme["gold"] if show and stage not in (None, 0) and int(stage) == i + 1 else theme.get("panel") or theme["navy"]
        ink = theme["navy"] if fill == theme["gold"] else theme["white"]
        draw.rounded_rectangle([88, y0, W - 88, y0 + row_h], radius=16, fill=fill)
        badge = str(i + 1)
        draw.ellipse([100, y0 + row_h / 2 - bd, 100 + 2 * bd, y0 + row_h / 2 + bd], fill=theme["gold"] if fill != theme["gold"] else theme["navy"])
        bf = fit_font(draw, badge, int(bd * 1.25), int(bd * 1.6), True, 20, 1)
        _center(draw, (100, y0 + row_h / 2 - bd, 100 + 2 * bd, y0 + row_h / 2 + bd), badge, bf, theme["navy"] if fill != theme["gold"] else theme["gold"])
        if show and text:
            primary, secondary = _split_pair(text)
            ex_primary, ex_secondary = _split_pair(ex or "")
            second_ink = theme["gold"] if fill != theme["gold"] else theme["white"]
            p_sz = base
            while p_sz > 24 and mixed_length(draw, primary, p_sz, True) > max_w:
                p_sz -= 2
            s_sz = max(20, int(base * 0.72))
            while secondary and s_sz > 18 and mixed_length(draw, secondary, s_sz, False) > max_w:
                s_sz -= 2
            e_sz = max(18, int(base * 0.55))
            p_lh = int(p_sz * (1.18 if any(is_cjk(c) for c in primary) else 1.06))
            block = p_lh
            if secondary:
                block += 4 + int(s_sz * 1.08)
            if ex_primary:
                block += 6 + int(e_sz * 1.1)
            ty = y0 + max(6, (row_h - block) / 2)
            tx = text_x
            if as_rows:
                # short rows (an equation each): centre the block in the row
                bw_ = max(mixed_length(draw, primary, p_sz, True), mixed_length(draw, secondary, s_sz, False) if secondary else 0)
                tx = max(text_x, (text_x + max_w + text_x) / 2 - bw_ / 2 - (text_x - 100) / 2)
            draw_mixed(draw, (tx, ty), primary, p_sz, ink, True)
            ty += p_lh
            if secondary:
                ty += 4
                draw_mixed(draw, (tx, ty), secondary, s_sz, second_ink, False)
                ty += int(s_sz * 1.08)
            if ex_primary:
                ty += 6
                line = ex_primary if not ex_secondary else f"{ex_primary}  ·  {ex_secondary}"
                draw_mixed(draw, (text_x, ty), line, e_sz, second_ink, False)


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
    heads = [field2(beat, f"col{j + 1}", code, second) or "" for j in range(cols)]
    if any(_split_pair(h)[1] for h in heads):
        head_h = 76 if rows < 4 else 64
    avail = grid_bottom - grid_top - head_h - gutter * (rows - 1)
    ch = max(56, avail // rows)
    if ch > 220:
        ch = 220
        block = head_h + rows * ch + gutter * (rows - 1)
        grid_top += max(0, (grid_bottom - grid_top - block) // 2)
    white = theme.get("white") or (247, 244, 238)
    for j, lab in enumerate(heads):
        x0 = grid_left + j * (cw + gutter)
        if lab:
            hl = _block_layout(draw, lab, cw - 8, head_h - 8, 28 if rows < 4 else 24, 16, 0.78, 1, 1)
            _paint_block(draw, (x0, grid_top + 4, x0 + cw, grid_top + head_h - 4), hl, theme["gold"], theme["bg"], valign="top")
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



def _series_tag(beat, code, second) -> str:
    """Panel tag from tag_* only. The kicker pill already names the card, so no
    default tag is painted (the old fixed FIVE DAYS / 五日 is gone)."""
    tag = field2(beat, "tag", code, second)
    if not tag:
        return ""
    p, s2 = _split_pair(tag)
    p = p.upper() if p.isascii() else p
    s2 = s2.upper() if s2 and s2.isascii() else s2
    return f"{p}  {s2}" if s2 else p


def _series_rows(beat, code, second, cols: int) -> int:
    """Hide row 2 when it has no label and no values."""
    if str(beat.get("rows") or "").strip() == "1":
        return 1
    if field2(beat, "row2", code, second):
        return 2
    for j in range(cols):
        key = f"c2{j + 1}"
        if str(field2(beat, key, code, second) or beat.get(key) or "").strip():
            return 2
    return 1


def render_series(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Up to two rows across up to six days.

    Default: stage 2 fills row 1, stage 3 fills row 2 and the footer.
    reveal: cells fills row 1 one cell at a time during stage 1, so a
    spoken count is on the card while it is being named.
    """
    try:
        cols = int(beat.get("cols") or 5)
    except (TypeError, ValueError):
        cols = 5
    cols = max(2, min(cols, 6))
    rows = _series_rows(beat, code, second, cols)
    reveal = str(beat.get("reveal") or "").strip().lower() == "cells"
    shown = cols
    if reveal and stage not in (None, 0):
        shown = min(cols, max(1, int(stage)))
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = _series_tag(beat, code, second)
    if tag:
        _tag(draw, 108, box_y + 18, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    heads = [field2(beat, f"col{j + 1}", code, second) or f"{j + 1}" for j in range(cols)]
    dual_head = any(_split_pair(h)[1] for h in heads)
    row_labels = [field2(beat, f"row{i + 1}", code, second) or "" for i in range(rows)]
    # Label column wide enough for the label at a readable size (36 / 26), capped.
    need = 0
    for r in row_labels:
        p, s2 = _split_pair(r)
        need = max(need, mixed_length(draw, p, 34, True), mixed_length(draw, s2, 25, False) if s2 else 0)
    label_w = int(max(170, min(300, need + 44)))
    head_h = 86 if dual_head else 52
    grid_top = box_y + 66
    grid_left = 64 + label_w
    grid_right = W - 88
    foot = (112 if "\n" in (footer or "") else 84) if footer else 36
    grid_bottom = box_y + box_h - foot
    gutter = 12
    cw = max(110, (grid_right - grid_left - gutter * (cols - 1)) // cols)
    avail = grid_bottom - grid_top - head_h - gutter
    ch = max(72, avail // 2 - gutter // 2)
    if rows == 1:
        # One row: a slightly taller cell, and the header + row block centred between
        # the tag and the footer, so there is no empty band above the footer.
        ch = min(int(ch * 1.25), max(72, avail - 40))
        grid_top = grid_top + max(0, (grid_bottom - grid_top - head_h - ch) // 2)
    for j, lab in enumerate(heads):
        x0 = grid_left + j * (cw + gutter)
        p, s2 = _split_pair(lab)
        pf = fit_font(draw, p, 32, cw - 8, True, 18, 1)
        psz = int(getattr(pf, "size", 32) or 32)
        tw = mixed_length(draw, p, psz, True)
        draw_mixed(draw, (x0 + max(0, (cw - tw) / 2), grid_top + 4), p, psz, theme["gold"], True)
        if s2:
            sf = fit_font(draw, s2, 25, cw - 8, False, 16, 1)
            ssz = int(getattr(sf, "size", 25) or 25)
            tw = mixed_length(draw, s2, ssz, False)
            draw_mixed(draw, (x0 + max(0, (cw - tw) / 2), grid_top + 8 + int(psz * 1.28)), s2, ssz, theme["bg"], False)
    for i in range(rows):
        lab = row_labels[i]
        y0 = grid_top + head_h + i * (ch + gutter)
        if lab:
            ll = _block_layout(draw, lab, label_w - 40, ch - 12, 36, 20, 0.72, 2)
            _paint_block(draw, (84, y0, 64 + label_w - 12, y0 + ch), ll, theme["bg"], theme["gold"])
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
        fl = _block_layout(draw, footer, W - 240, box_y + box_h - 12 - grid_bottom - 8, 38, 20, 0.66, 1, 1)
        _paint_block(draw, (100, grid_bottom + 8, W - 100, box_y + box_h - 12), fl, theme["gold"], theme["bg"])


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


_RANK_SORTED = {"sorted", "sort", "asc", "ascending"}
_RANK_GIVEN = {"as_given", "given", "raw", "unsorted", "written"}
_RANK_MARK_OFF = {"none", "off", "no", "0"}
_RANK_MARK_ON = {"middle", "mid", "center", "centre"}
_RANK_MARK_ENDS = {"ends", "end", "extremes", "minmax", "min_max"}
_RANK_SPAN_ALL = {"ends", "all", "full", "extremes", "minmax", "min_max"}


def _split_rank_list(raw) -> list[str]:
    """Semicolon list, or a YAML list. Commas stay inside a value (4,200)."""
    if raw is None or raw is False:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(part).strip() for part in raw if str(part).strip()]
    text = str(raw).strip()
    if not text:
        return []
    return [part.strip() for part in text.replace("；", ";").split(";") if part.strip()]


def _rank_value_keys(code: str) -> tuple[str, ...]:
    if code == "zh_hk":
        return ("values_zh_hk", "values_zh", "values")
    if code == "zh":
        return ("values_zh_cn", "values_zh", "values")
    return ("values_en", "values")


def _values_for(beat: dict, code: str) -> list[str]:
    for key in _rank_value_keys(code):
        if key in beat and beat.get(key) not in (None, ""):
            return _split_rank_list(beat.get(key))
    return []


def _vstem_count(beat: dict) -> int:
    n = 0
    for i in range(1, 7):
        if not any(str(beat.get(f"v{i}{suf}") or "").strip() for suf in ("", "_en", "_zh", "_zh_cn", "_zh_hk")):
            break
        n += 1
    return n


def rank_value_count(beat: dict) -> int:
    """How many chips this beat names, before the 6-chip paint cap."""
    lists = [row for row in (_values_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if lists:
        return max(len(row) for row in lists)
    return _vstem_count(beat)


def _order_token(beat: dict) -> str:
    return str(beat.get("order") or "").strip().lower().replace("-", "_").replace(" ", "_")


def rank_order_mode(beat: dict) -> str:
    """sorted rearranges; as_given keeps the written order."""
    if _order_token(beat) in _RANK_GIVEN:
        return "as_given"
    return "sorted"


def _rank_number(text: str):
    primary = str(text or "").split("\n", 1)[0].strip()
    token = (
        primary.replace(",", "")
        .replace(" ", "")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
    )
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def rank_sorted(cells: list[str]) -> list[str]:
    """Low to high when every value is a number. Otherwise A–Z on the primary label."""
    nums = [_rank_number(cell) for cell in cells]
    if nums and all(num is not None for num in nums):
        order = sorted(range(len(cells)), key=lambda i: (nums[i], i))
    else:
        order = sorted(range(len(cells)), key=lambda i: (cells[i].split("\n", 1)[0].casefold(), i))
    return [cells[i] for i in order]


def rank_middles(n: int) -> list[int]:
    """0-based. Odd n: the one middle. Even n: the two middle positions."""
    if n <= 0:
        return []
    if n % 2:
        return [n // 2]
    return [n // 2 - 1, n // 2]


def rank_marks_middle(beat: dict) -> bool:
    raw = str(beat.get("mark") or "").strip().lower()
    return raw not in _RANK_MARK_OFF and raw not in _RANK_MARK_ENDS and not _rank_index_token(raw)


def _rank_index_token(raw: str) -> bool:
    raw = str(raw or "").strip()
    return bool(raw) and bool(re.fullmatch(r"\d+(\s*[;,]\s*\d+)*", raw)) and raw != "0"


def _rank_indices(raw: str, n: int) -> list[int]:
    out = []
    for part in re.split(r"[;,]", str(raw or "")):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= n:
            out.append(int(part) - 1)
    return sorted(set(out))


def rank_marked(beat: dict, n: int) -> list[int]:
    """0-based ordered positions to gold on stage 3.

    mark: middle (default) -> one middle (odd) or two middles (even);
    mark: ends -> first and last; mark: 2;4 -> 1-based positions; mark: none -> nothing.
    """
    raw = str(beat.get("mark") or "").strip().lower()
    if raw in _RANK_MARK_OFF or n <= 0:
        return []
    if raw in _RANK_MARK_ENDS:
        return sorted({0, n - 1})
    if _rank_index_token(raw):
        return _rank_indices(raw, n)
    return rank_middles(n)


def rank_span(beat: dict, n: int):
    """(lo, hi) 0-based ordered positions for the stage-3 bracket, or None.

    span: ends (or all) -> whole line; span: 2-4 -> positions 2 to 4 (1-based).
    """
    raw = beat.get("span")
    if raw is None or raw is False or n < 2:
        return None
    token = str(raw).strip().lower().replace("–", "-").replace("—", "-").replace(" ", "")
    if not token or token in _RANK_MARK_OFF:
        return None
    if token in _RANK_SPAN_ALL:
        return (0, n - 1)
    m = re.fullmatch(r"(\d+)-(\d+)", token)
    if m:
        lo, hi = int(m.group(1)) - 1, int(m.group(2)) - 1
        if 0 <= lo < hi < n:
            return (lo, hi)
    return None


def rank_break(beat: dict, n: int):
    """0-based ordered position that sits after an axis break, or None.

    break: 5 puts a gap with // marks before the 5th place (one far value).
    """
    raw = beat.get("break")
    if raw is None or raw is False or n < 3:
        return None
    token = str(raw).strip().lower()
    if token in ("last", "top", "high"):
        return n - 1
    if token in ("first", "low"):
        return 1
    if token.isdigit() and 2 <= int(token) <= n:
        return int(token) - 1
    return None


def _rank_label_keys(code: str) -> tuple[str, ...]:
    if code == "zh_hk":
        return ("labels_zh_hk", "labels_zh", "labels")
    if code == "zh":
        return ("labels_zh_cn", "labels_zh", "labels")
    return ("labels_en", "labels")


def _rank_labels_for(beat: dict, code: str) -> list[str]:
    for key in _rank_label_keys(code):
        if key in beat and beat.get(key) not in (None, ""):
            return _split_rank_list(beat.get(key))
    return []


def _rank_lstem_count(beat: dict) -> int:
    n = 0
    for i in range(1, 7):
        if not any(str(beat.get(f"l{i}{suf}") or "").strip() for suf in ("", "_en", "_zh", "_zh_cn", "_zh_hk")):
            break
        n += 1
    return n


def rank_labels(beat: dict, code: str = "en", second: str | None = None) -> list[str]:
    """Optional small caption per chip (Shop A). Travels with its value when sorted."""
    primary = _rank_labels_for(beat, code)
    if primary:
        cells = primary[:6]
        if second and second != code:
            other = _rank_labels_for(beat, second)[:6]
            if other and other != cells:
                cells = [
                    left if i >= len(other) or not other[i] or other[i] == left else f"{left}\n{other[i]}"
                    for i, left in enumerate(cells)
                ]
        return cells
    n = _rank_lstem_count(beat)
    return [field2(beat, f"l{i}", code, second) for i in range(1, n + 1)][:6]


def rank_sorted_order(cells: list[str]) -> list[int]:
    """Index permutation that rank_sorted applies."""
    nums = [_rank_number(cell) for cell in cells]
    if nums and all(num is not None for num in nums):
        return sorted(range(len(cells)), key=lambda i: (nums[i], i))
    return sorted(range(len(cells)), key=lambda i: (cells[i].split("\n", 1)[0].casefold(), i))


def rank_cells(beat: dict, code: str = "en", second: str | None = None) -> list[str]:
    """Up to six chips. `values` wins; otherwise v1..v6. Second language sits under the first."""
    primary = _values_for(beat, code)
    if primary:
        cells = primary[:6]
        if second and second != code:
            other = _values_for(beat, second)[:6]
            if other and other != cells:
                paired = []
                for i, left in enumerate(cells):
                    right = other[i] if i < len(other) else ""
                    paired.append(left if not right or right == left else f"{left}\n{right}")
                cells = paired
        return cells
    n = _vstem_count(beat)
    return [field2(beat, f"v{i}", code, second) for i in range(1, n + 1)][:6]


def rank_line_problems(beat: dict) -> list[str]:
    problems = []
    n = rank_value_count(beat)
    if n < 3 or n > 6:
        problems.append(f"rank_line needs 3 to 6 values, found {n}.")
    lengths = [len(row) for row in (_values_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if len(set(lengths)) > 1:
        problems.append("rank_line value lists differ in length across languages.")
    order = _order_token(beat)
    if order and order not in _RANK_SORTED and order not in _RANK_GIVEN:
        problems.append("rank_line order must be sorted or as_given.")
    mark = str(beat.get("mark") or "").strip().lower()
    if mark and mark not in _RANK_MARK_ON and mark not in _RANK_MARK_OFF and mark not in _RANK_MARK_ENDS:
        if not _rank_index_token(mark) or len(_rank_indices(mark, n)) != len(re.split(r"[;,]", mark)):
            problems.append("rank_line mark must be middle, ends, none, or 1-based positions such as 2;4.")
    raw_span = beat.get("span")
    if raw_span not in (None, False, "") and str(raw_span).strip().lower() not in _RANK_MARK_OFF:
        if rank_span(beat, n) is None:
            problems.append("rank_line span must be ends (or all) or a 1-based range such as 2-4 inside the line.")
    raw_break = beat.get("break")
    if raw_break not in (None, False, "") and rank_break(beat, n) is None:
        problems.append("rank_line break must be a 1-based place from 2 to the count (e.g. break: 5), or last.")
    lab_lengths = [len(row) for row in (_rank_labels_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if not lab_lengths and _rank_lstem_count(beat):
        lab_lengths = [_rank_lstem_count(beat)]
    if lab_lengths and n and any(ln != n for ln in lab_lengths):
        problems.append("rank_line labels length must match the value count.")
    return problems


def render_rank_line(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """An ordered value line. Stage 1 as written, stage 2 ordered, stage 3 gold mark(s),
    optional span bracket + span text, and footer.

    mark: middle (default) golds the middle (two middles when even); ends golds the
    first and last; 2;4 golds positions; none leaves the chips plain. Optional
    labels (Shop A) sit small above each value and travel with it when sorted.
    The layout reserves the bracket and footer rows from stage 1, so nothing jumps.
    """
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "RANK", "zh": "排序", "zh_hk": "排序"}.get(code, "RANK")
    if second:
        other = {"en": "RANK", "zh": "排序", "zh_hk": "排序"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    span_text = _minus_sign(field2(beat, "span", code, second) or "")
    given = rank_cells(beat, code, second)
    labels = rank_labels(beat, code, second)
    if len(labels) != len(given):
        labels = []
    if rank_order_mode(beat) == "as_given":
        perm = list(range(len(given)))
    else:
        perm = rank_sorted_order(given)
    show_ordered = _show(stage, 2)
    idx = perm if show_ordered else list(range(len(given)))
    cells = [given[i] for i in idx]
    labs = [labels[i] for i in idx] if labels else []
    n = len(cells)
    lit_on = show_ordered and _show(stage, 3)
    marked = set(rank_marked(beat, n)) if lit_on else set()
    span = rank_span(beat, n)
    footer_two = "\n" in (footer or "")
    foot = (112 if footer_two else 88) if footer else 28
    # span row: bracket + text (bilingual text takes two lines)
    span_h = 0
    if span:
        span_h = 34 + ((108 if "\n" in span_text else 72) if span_text else 0)
    badge = 56
    rule = 28
    top_limit = box_y + 72
    bottom_limit = box_y + box_h - foot
    avail = bottom_limit - top_limit - badge - rule - span_h
    has_labels = len(rank_labels(beat, code, second)) == len(given) and bool(given)
    chip_cap = 270 if has_labels else 220
    chip_h = max(140, min(chip_cap, int(avail * (0.72 if (span or has_labels) else 0.55))))
    block = badge + chip_h + rule + span_h
    chip_top = top_limit + badge + max(0, (bottom_limit - top_limit - block) // 2)
    white = theme.get("white") or (247, 244, 238)
    if n:
        gap = 18 if n >= 5 else 28
        brk = rank_break(beat, n)
        extra = 96 if brk is not None else 0
        max_w = W - 192
        chip_w = max(96, (max_w - gap * (n - 1) - extra) // n)
        chip_w = min(chip_w, 320)
        use_break = brk is not None and show_ordered
        row_w = n * chip_w + (n - 1) * gap + (extra if use_break else 0)
        x0 = (W - row_w) // 2
        y_line = chip_top + chip_h + 16
        lefts = []
        xx = x0
        for i in range(n):
            if use_break and i == brk:
                xx += extra
            lefts.append(xx)
            xx += chip_w + gap
        if show_ordered and n >= 2:
            if use_break:
                gx0 = lefts[brk - 1] + chip_w + gap // 2
                gx1 = lefts[brk] - gap // 2
                draw.line([(x0, y_line), (gx0 + 10, y_line)], fill=theme["gold"], width=5)
                draw.line([(gx1 - 10, y_line), (x0 + row_w, y_line)], fill=theme["gold"], width=5)
                for cxb in (gx0 + 22, gx1 - 22):
                    draw.line([(cxb - 10, y_line + 16), (cxb + 10, y_line - 16)], fill=theme["gold"], width=5)
                dots_y = y_line
                for k in range(3):
                    dx = (gx0 + gx1) / 2 + (k - 1) * 14
                    draw.ellipse([dx - 3, dots_y - 3, dx + 3, dots_y + 3], fill=theme["gold"])
            else:
                draw.line([(x0, y_line), (x0 + row_w, y_line)], fill=theme["gold"], width=5)
        lab_lays = []
        if labs:
            lab_lays = [
                _block_layout(draw, lab, chip_w - 24, 84, 36, 16, 0.72, 1, 1) if lab else None for lab in labs
            ]
            common = min([l["size"] for l in lab_lays if l] or [28])
            lab_lays = [
                _block_layout(draw, lab, chip_w - 24, 84, common, 16, 0.72, 1, 1) if lab else None for lab in labs
            ]
        lab_h = max([l["h"] for l in lab_lays if l] or [0])
        val_lays = []
        for val in cells:
            vh = chip_h - 24 - (lab_h + 6 if lab_h else 0)
            val_lays.append(_block_layout(draw, val, chip_w - 28, vh, 80 if lab_h else 68, 22, 0.6, 2) if val else None)
        centers = []
        for i, val in enumerate(cells):
            x = lefts[i]
            lit = i in marked
            box = (x, chip_top, x + chip_w, chip_top + chip_h)
            draw.rounded_rectangle(box, radius=18, fill=theme["gold"] if lit else white)
            cx = x + chip_w / 2
            centers.append((x, x + chip_w))
            if show_ordered:
                r = 24
                cy = chip_top - 36
                if n >= 2:
                    draw.line([(cx, chip_top + chip_h), (cx, chip_top + chip_h + 16)], fill=theme["gold"], width=4)
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=theme["gold"] if lit else theme["bg"])
                _center(
                    draw,
                    (cx - r, cy - r, cx + r, cy + r),
                    str(i + 1),
                    fit_font(draw, str(i + 1), 30, 40, True, 18, 1),
                    theme["navy"],
                )
            vy0 = chip_top + 8
            if lab_h and i < len(lab_lays) and lab_lays[i]:
                _paint_block(
                    draw,
                    (x + 10, chip_top + 14, x + chip_w - 10, chip_top + 14 + lab_h),
                    lab_lays[i],
                    theme["navy"] if lit else theme["muted"],
                    theme["navy"] if lit else theme["muted"],
                )
            if lab_h:
                vy0 = chip_top + 14 + lab_h
            if val_lays[i]:
                _paint_block(draw, (x + 10, vy0, x + chip_w - 10, chip_top + chip_h - 8), val_lays[i], theme["navy"], theme["muted"])
        if span and lit_on:
            lo, hi = span
            bx0 = centers[lo][0] + 6
            bx1 = centers[hi][1] - 6
            by = y_line + 22
            tick = 18
            draw.line([(bx0, by), (bx0, by + tick)], fill=white, width=4)
            draw.line([(bx1, by), (bx1, by + tick)], fill=white, width=4)
            draw.line([(bx0, by + tick), (bx1, by + tick)], fill=white, width=4)
            mid = (bx0 + bx1) / 2
            draw.line([(mid, by + tick), (mid, by + tick + 10)], fill=white, width=4)
            if span_text:
                th = span_h - 34
                sl = _block_layout(draw, span_text, max(360, int(bx1 - bx0) - 20), th, 48, 22, 0.66, 1, 1)
                _paint_block(draw, (bx0, by + tick + 12, bx1, by + tick + 12 + th), sl, theme["gold"], theme["bg"])
    if footer and _show(stage, 3):
        fl = _block_layout(draw, footer, W - 240, foot - 24, 36, 20, 0.72, 1, 1)
        _paint_block(draw, (100, box_y + box_h - foot + 8, W - 100, box_y + box_h - 16), fl, theme["gold"], theme["bg"])


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



_FREQ_MARK_OFF = {"none", "off", "no", "0"}
_FREQ_MARK_ALL = {"all", "every", "each"}
_FREQ_MARK_TALL = {"tallest", "max", "mode", "highest", ""}


def _split_freq_list(raw) -> list[str]:
    """Semicolon list, or a YAML list. Commas stay inside a label."""
    if raw is None or raw is False:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(part).strip() for part in raw if str(part).strip()]
    text = str(raw).strip()
    if not text:
        return []
    return [part.strip() for part in text.replace("；", ";").split(";") if part.strip()]


def _freq_label_keys(code: str) -> tuple[str, ...]:
    if code == "zh_hk":
        return ("labels_zh_hk", "labels_zh", "labels")
    if code == "zh":
        return ("labels_zh_cn", "labels_zh", "labels")
    return ("labels_en", "labels")


def _freq_labels_for(beat: dict, code: str) -> list[str]:
    for key in _freq_label_keys(code):
        if key in beat and beat.get(key) not in (None, ""):
            return _split_freq_list(beat.get(key))
    return []


def _freq_lstem_count(beat: dict) -> int:
    n = 0
    for i in range(1, 7):
        if not any(str(beat.get(f"l{i}{suf}") or "").strip() for suf in ("", "_en", "_zh", "_zh_cn", "_zh_hk")):
            break
        n += 1
    return n


def freq_counts(beat: dict) -> list[float]:
    raw = beat.get("counts")
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        parts = raw
    else:
        parts = str(raw).replace("；", ";").replace(",", ";").split(";")
    out = []
    for part in parts:
        token = str(part).strip().replace(",", "")
        if not token:
            continue
        try:
            out.append(float(token))
        except ValueError:
            continue
    return out


def freq_bar_count(beat: dict) -> int:
    counts = freq_counts(beat)
    if counts:
        return len(counts)
    lists = [row for row in (_freq_labels_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if lists:
        return max(len(row) for row in lists)
    return _freq_lstem_count(beat)


def freq_labels(beat: dict, code: str = "en", second: str | None = None) -> list[str]:
    """Category labels under the bars. labels wins; otherwise l1..l6."""
    primary = _freq_labels_for(beat, code)
    if primary:
        cells = primary[:6]
        if second and second != code:
            other = _freq_labels_for(beat, second)[:6]
            if other and other != cells:
                paired = []
                for i, left in enumerate(cells):
                    right = other[i] if i < len(other) else ""
                    paired.append(left if not right or right == left else f"{left}\n{right}")
                cells = paired
        return cells
    n = _freq_lstem_count(beat)
    return [field2(beat, f"l{i}", code, second) for i in range(1, n + 1)][:6]


def _freq_mark_token(beat: dict) -> str:
    return str(beat.get("mark") or "").strip().lower().replace("-", "_").replace(" ", "_")


def freq_marked_indices(beat: dict) -> list[int]:
    """0-based bars to gold on stage 3. Default: every bar that ties for the maximum count."""
    counts = freq_counts(beat)
    n = len(counts) or freq_bar_count(beat)
    token = _freq_mark_token(beat)
    if token in _FREQ_MARK_OFF:
        return []
    if token in _FREQ_MARK_ALL:
        return list(range(n))
    # explicit 1-based indices: "2" or "2;3"
    if token and token not in _FREQ_MARK_TALL:
        picked = []
        for part in token.replace(",", ";").split(";"):
            part = part.strip()
            if not part:
                continue
            try:
                idx = int(part) - 1
            except ValueError:
                continue
            if 0 <= idx < n:
                picked.append(idx)
        if picked:
            return sorted(set(picked))
    if not counts:
        return []
    top = max(counts)
    return [i for i, c in enumerate(counts) if c == top]


def freq_bars_problems(beat: dict) -> list[str]:
    problems = []
    n = freq_bar_count(beat)
    if n < 2 or n > 6:
        problems.append(f"freq_bars needs 2 to 6 bars, found {n}.")
    counts = freq_counts(beat)
    if not counts:
        problems.append("freq_bars needs counts (e.g. 40;280;100).")
    elif n and len(counts) != n and _freq_lstem_count(beat):
        problems.append("freq_bars counts length must match the label count.")
    lengths = [len(row) for row in (_freq_labels_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if len(set(lengths)) > 1:
        problems.append("freq_bars label lists differ in length across languages.")
    if counts and lengths and any(len(row) != len(counts) for row in (_freq_labels_for(beat, code) for code in ("en", "zh", "zh_hk")) if row):
        problems.append("freq_bars labels and counts differ in length.")
    return problems


def render_freq_bars(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Frequency bars for mode. Stage 1 labels, stage 2 bars+counts, stage 3 gold tallest + footer."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "COUNT", "zh": "清点", "zh_hk": "清點"}.get(code, "COUNT")
    if second:
        other = {"en": "COUNT", "zh": "清点", "zh_hk": "清點"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    labels = freq_labels(beat, code, second)
    counts = freq_counts(beat)
    n = max(len(labels), len(counts), 1)
    while len(labels) < n:
        labels.append("")
    while len(counts) < n:
        counts.append(0.0)
    labels = labels[:n]
    counts = counts[:n]
    marked = set(freq_marked_indices(beat)) if _show(stage, 3) else set()
    show_bars = _show(stage, 2)
    foot = (112 if "\n" in (footer or "") else 88) if footer else 28
    label_band = 96 if any(_split_pair(l)[1] for l in labels) else 64
    count_band = 58
    top = box_y + 64
    bottom = box_y + box_h - foot - label_band
    axis_y = bottom
    max_c = max(counts) if counts else 1.0
    if max_c <= 0:
        max_c = 1.0
    chart_h = max(40, axis_y - top - count_band)
    gap = 28 if n <= 3 else 18
    max_w = W - 220
    bar_w = max(72, (max_w - gap * (n - 1)) // n)
    bar_w = min(bar_w, 380 if n <= 3 else 320)
    row_w = n * bar_w + (n - 1) * gap
    x0 = (W - row_w) // 2
    # baseline
    draw.line([(x0 - 12, axis_y), (x0 + row_w + 12, axis_y)], fill=theme["bg"], width=4)
    white = theme.get("white") or (247, 244, 238)
    ink = theme["bg"]
    x = x0
    for i, (lab, count) in enumerate(zip(labels, counts)):
        # label under axis always from stage 1
        if _show(stage, 1) and lab:
            ll = _block_layout(draw, lab, bar_w + 8, label_band - 12, 36, 16, 0.7, 1, 1)
            _paint_block(draw, (x - 4, axis_y + 10, x + bar_w + 4, axis_y + label_band - 2), ll, theme["bg"], theme["gold"], valign="top")
        if show_bars:
            h = int(chart_h * (count / max_c)) if max_c else 0
            h = max(h, 8 if count > 0 else 4)
            top_y = axis_y - h
            lit = i in marked
            fill = theme["gold"] if lit else white
            draw.rounded_rectangle([x, top_y, x + bar_w, axis_y - 2], radius=14, fill=fill)
            # count above bar
            count_txt = str(int(count)) if float(count).is_integer() else str(count)
            cf = fit_font(draw, count_txt, 46, bar_w, True, 20, 1)
            _center(draw, (x, top_y - count_band, x + bar_w, top_y - 4), count_txt, cf, theme["gold"] if lit else theme["bg"])
        else:
            # stage 1 stub so the axis reads as a chart before the bars grow
            draw.rounded_rectangle([x + 8, axis_y - 10, x + bar_w - 8, axis_y - 2], radius=6, fill=ink)
        x += bar_w + gap
    if footer and _show(stage, 3):
        fl = _block_layout(draw, footer, W - 240, foot - 24, 36, 20, 0.72, 1, 1)
        _paint_block(draw, (100, box_y + box_h - foot + 8, W - 100, box_y + box_h - 16), fl, theme["gold"], theme["bg"])





def _split_balance_list(raw) -> list[str]:
    """Semicolon list, or a YAML list. Commas stay inside a value (1,200)."""
    if raw is None or raw is False:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(part).strip() for part in raw if str(part).strip()]
    text = str(raw).strip()
    if not text:
        return []
    return [part.strip() for part in text.replace("；", ";").split(";") if part.strip()]


def _balance_value_keys(code: str) -> tuple[str, ...]:
    if code == "zh_hk":
        return ("values_zh_hk", "values_zh", "values")
    if code == "zh":
        return ("values_zh_cn", "values_zh", "values")
    return ("values_en", "values")


def _balance_values_for(beat: dict, code: str) -> list[str]:
    for key in _balance_value_keys(code):
        if key in beat and beat.get(key) not in (None, ""):
            return _split_balance_list(beat.get(key))
    return []


def _balance_vstem_count(beat: dict) -> int:
    n = 0
    for i in range(1, 7):
        if not any(str(beat.get(f"v{i}{suf}") or "").strip() for suf in ("", "_en", "_zh", "_zh_cn", "_zh_hk")):
            break
        n += 1
    return n


def balance_value_count(beat: dict) -> int:
    lists = [row for row in (_balance_values_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if lists:
        return max(len(row) for row in lists)
    return _balance_vstem_count(beat)


def balance_cells(beat: dict, code: str = "en", second: str | None = None) -> list[str]:
    """Up to six chips. `values` wins; otherwise v1..v6."""
    primary = _balance_values_for(beat, code)
    if primary:
        cells = primary[:6]
        if second and second != code:
            other = _balance_values_for(beat, second)[:6]
            if other and other != cells:
                paired = []
                for i, left in enumerate(cells):
                    right = other[i] if i < len(other) else ""
                    paired.append(left if not right or right == left else f"{left}\n{right}")
                cells = paired
        return cells
    n = _balance_vstem_count(beat)
    return [field2(beat, f"v{i}", code, second) for i in range(1, n + 1)][:6]


def _balance_label_keys(code: str) -> tuple[str, ...]:
    if code == "zh_hk":
        return ("labels_zh_hk", "labels_zh", "labels")
    if code == "zh":
        return ("labels_zh_cn", "labels_zh", "labels")
    return ("labels_en", "labels")


def _balance_labels_for(beat: dict, code: str) -> list[str]:
    for key in _balance_label_keys(code):
        if key in beat and beat.get(key) not in (None, ""):
            return _split_balance_list(beat.get(key))
    return []


def _balance_lstem_count(beat: dict) -> int:
    n = 0
    for i in range(1, 7):
        if not any(str(beat.get(f"l{i}{suf}") or "").strip() for suf in ("", "_en", "_zh", "_zh_cn", "_zh_hk")):
            break
        n += 1
    return n


def balance_labels(beat: dict, code: str = "en", second: str | None = None) -> list[str]:
    """Optional shop/category labels above the chips. labels wins; otherwise l1..l6."""
    primary = _balance_labels_for(beat, code)
    if primary:
        cells = primary[:6]
        if second and second != code:
            other = _balance_labels_for(beat, second)[:6]
            if other and other != cells:
                paired = []
                for i, left in enumerate(cells):
                    right = other[i] if i < len(other) else ""
                    paired.append(left if not right or right == left else f"{left}\n{right}")
                cells = paired
        return cells
    n = _balance_lstem_count(beat)
    return [field2(beat, f"l{i}", code, second) for i in range(1, n + 1)][:6]


def balance_mean(beat: dict):
    """Fulcrum. `mean` wins; `center` is an alias."""
    for key in ("mean", "center", "fulcrum"):
        raw = beat.get(key)
        if raw is None or raw == "":
            continue
        num = _rank_number(str(raw))
        if num is not None:
            return num
    return None


def balance_numbers(beat: dict) -> list[float]:
    cells = balance_cells(beat, "en")
    nums = []
    for cell in cells:
        num = _rank_number(cell)
        if num is None:
            return []
        nums.append(num)
    return nums


def balance_deviations(beat: dict) -> list[float]:
    nums = balance_numbers(beat)
    mean = balance_mean(beat)
    if mean is None or not nums:
        return []
    return [n - mean for n in nums]


def balance_pulls(beat: dict) -> tuple[float, float]:
    """Absolute left pull and right pull from the mean."""
    left = right = 0.0
    for d in balance_deviations(beat):
        if d < 0:
            left += -d
        elif d > 0:
            right += d
    return left, right


def _fmt_pull(n: float) -> str:
    if float(n).is_integer():
        return str(int(n))
    return str(n)


def balance_problems(beat: dict) -> list[str]:
    problems = []
    n = balance_value_count(beat)
    if n < 3 or n > 6:
        problems.append(f"balance_line needs 3 to 6 values, found {n}.")
    nums = balance_numbers(beat)
    if n and not nums:
        problems.append("balance_line values must be numbers (e.g. 250;300;350;500).")
    if balance_mean(beat) is None:
        problems.append("balance_line needs mean (e.g. mean: 350).")
    lengths = [len(row) for row in (_balance_values_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if len(set(lengths)) > 1:
        problems.append("balance_line value lists differ in length across languages.")
    lab_lengths = [len(row) for row in (_balance_labels_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if lab_lengths and nums and any(ln != len(nums) for ln in lab_lengths):
        problems.append("balance_line labels length must match the value count.")
    if lab_lengths and len(set(lab_lengths)) > 1:
        problems.append("balance_line label lists differ in length across languages.")
    return problems


def _minus_sign(text: str) -> str:
    """ASCII hyphen used as a minus (-100, a - b) becomes U+2212."""
    if not text:
        return text
    text = re.sub(r"(?<![\w])-(?=\d)", "\u2212", text)
    text = re.sub(r"(?<=\s)-(?=\s)", "\u2212", text)
    return text


def render_balance_line(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Seesaw / mean balance line. Stage 1 values, stage 2 mean fulcrum, stage 3 left=right pulls + footer."""
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    tag = {"en": "BALANCE", "zh": "平衡", "zh_hk": "平衡"}.get(code, "BALANCE")
    if second:
        other = {"en": "BALANCE", "zh": "平衡", "zh_hk": "平衡"}.get(second)
        if other and other != tag:
            tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    footer = _minus_sign(field2(beat, "footer", code, second) or field2(beat, "note", code, second))
    cells = balance_cells(beat, code, second)
    labels = balance_labels(beat, code, second)
    nums = balance_numbers(beat)
    mean = balance_mean(beat)
    if not nums or mean is None:
        return
    while len(labels) < len(nums):
        labels.append("")
    labels = labels[: len(nums)]
    foot = (112 if "\n" in (footer or "") else 88) if footer else 28
    pull_band = 124  # reserved on every stage so the line never moves
    top = box_y + 58
    bottom = box_y + box_h - foot - pull_band
    has_labels = any(labels)
    dual_labels = any(_split_pair(l)[1] for l in labels)
    label_band = (84 if dual_labels else 52) if has_labels else 0
    # scale: pad so extremes are not on the edge
    lo = min(min(nums), mean)
    hi = max(max(nums), mean)
    span = hi - lo if hi > lo else 1.0
    pad = span * 0.12
    lo_s, hi_s = lo - pad, hi + pad
    span_s = hi_s - lo_s if hi_s > lo_s else 1.0
    x_left, x_right = 130, W - 130

    def x_at(val: float) -> int:
        return int(x_left + (val - lo_s) / span_s * (x_right - x_left))

    xs = sorted(x_at(v) for v in nums)
    min_gap = min([b - a for a, b in zip(xs, xs[1:]) if b - a > 0] or [400])
    chip_w = int(max(110, min(156, min_gap - 14)))
    chip_h = 96 if chip_w >= 130 else 84
    lab_w = int(max(chip_w + 8, min(chip_w + 60, min_gap - 10)))
    line_y = max(top + label_band + chip_h + 26, top + (bottom - top) // 2)
    white = theme.get("white") or (247, 244, 238)
    # baseline always
    draw.line([(x_left - 20, line_y), (x_right + 20, line_y)], fill=theme["bg"], width=5)
    # stage 1+: value chips on the line
    if _show(stage, 1):
        for i, (val, num) in enumerate(zip(cells, nums)):
            cx = x_at(num)
            # optional label above
            lab = labels[i] if i < len(labels) else ""
            if lab:
                ll = _block_layout(draw, lab, lab_w, label_band - 6, 32, 14, 0.72, 1, 1)
                _paint_block(draw, (cx - lab_w // 2, line_y - chip_h - 12 - label_band, cx + lab_w // 2, line_y - chip_h - 12), ll, theme["bg"], theme["gold"])
            box = (cx - chip_w // 2, line_y - chip_h - 6, cx + chip_w // 2, line_y - 6)
            draw.rounded_rectangle(box, radius=16, fill=white)
            vl = _block_layout(draw, val, chip_w - 16, chip_h - 12, 46, 18, 0.6, 2)
            _paint_block(draw, (box[0] + 6, box[1] + 4, box[2] - 6, box[3] - 4), vl, theme["navy"], theme["muted"])
            # tick (the fulcrum replaces it at the mean from stage 2)
            if _show(stage, 2) and mean is not None and abs(num - mean) < 1e-9:
                continue
            draw.line([(cx, line_y), (cx, line_y + 14)], fill=theme["bg"], width=4)
            draw.ellipse([cx - 7, line_y + 10, cx + 7, line_y + 24], fill=theme["bg"])

    # stage 2+: mean fulcrum
    if _show(stage, 2):
        mx = x_at(mean)
        # triangle fulcrum under the line
        tip = line_y + 4
        base = tip + 32
        draw.polygon([(mx, tip), (mx - 26, base), (mx + 26, base)], fill=theme["gold"])
        mean_txt = _fmt_pull(mean)
        mean_lab = {
            "en": f"mean = {mean_txt}",
            "zh": f"平均数 = {mean_txt}",
            "zh_hk": f"平均數 = {mean_txt}",
        }.get(code, f"mean = {mean_txt}")
        if second and second != code:
            other = {
                "en": f"mean = {mean_txt}",
                "zh": f"平均数 = {mean_txt}",
                "zh_hk": f"平均數 = {mean_txt}",
            }.get(second)
            if other and other != mean_lab:
                mean_lab = f"{mean_lab}\n{other}"
        # Mean label beside the fulcrum, pinned on stages 2 and 3 (no jump).
        # Side = the one with more free room before the next value's tick /
        # deviation number; falls back under the fulcrum (stage 2) if both are tight.
        def _dev_half(num):
            d = num - mean
            t = "0" if d == 0 else (f"+{_fmt_pull(d)}" if d > 0 else f"\u2212{_fmt_pull(-d)}")
            return mixed_length(draw, t, 34, True) / 2 + 18
        others = [x_at(v) for v in nums if abs(v - mean) > 1e-9]
        r_lim = min([x - _dev_half(v) for v, x in zip([v for v in nums if abs(v - mean) > 1e-9], others) if x > mx] + [W - 100])
        l_lim = max([x + _dev_half(v) for v, x in zip([v for v in nums if abs(v - mean) > 1e-9], others) if x < mx] + [100])
        r_room = int(r_lim - (mx + 38))
        l_room = int((mx - 38) - l_lim)
        lab_top, lab_h = line_y + 8, 84
        room = max(r_room, l_room)
        if room >= 170:
            ml = _block_layout(draw, mean_lab, min(room, 360), lab_h, 38, 20, 0.72, 1, 1)
            bw = max([mixed_length(draw, ln, ml["size"], ml["bold"]) for ln in ml["p"]] + [mixed_length(draw, ln, ml["ssz"], False) for ln in ml["s"]] + [1])
            x0 = mx + 38 if r_room >= l_room else int(mx - 38 - bw)
            _paint_block(draw, (x0, lab_top, x0 + int(bw) + 2, lab_top + lab_h), ml, theme["gold"], theme["bg"], align="left", valign="top")
        elif not _show(stage, 3):
            ml = _block_layout(draw, mean_lab, 320, 84, 38, 18, 0.72, 1, 1)
            _paint_block(draw, (mx - 160, base + 6, mx + 160, base + 90), ml, theme["gold"], theme["bg"], valign="top")
        else:
            ml = _block_layout(draw, mean_lab, max(120, room), lab_h, 30, 14, 0.72, 1, 1)
            _paint_block(draw, (mx + 38, lab_top, mx + 38 + max(120, room), lab_top + lab_h), ml, theme["gold"], theme["bg"], align="left", valign="top")

    # stage 3: deviation chips + left/right pull panels
    if _show(stage, 3):
        devs = balance_deviations(beat)
        for i, (num, d) in enumerate(zip(nums, devs)):
            cx = x_at(num)
            if d == 0:
                dtxt = "0"
            elif d > 0:
                dtxt = f"+{_fmt_pull(d)}"
            else:
                dtxt = f"−{_fmt_pull(-d)}"
            df = fit_font(draw, dtxt, 34, max(90, min_gap - 10), True, 16, 1)
            # under the ticks, clear of the fulcrum tip
            _center(draw, (cx - 70, line_y + 42, cx + 70, line_y + 84), dtxt, df, theme["gold"])
        left_pull, right_pull = balance_pulls(beat)
        left = field2(beat, "left", code, second)
        right = field2(beat, "right", code, second)
        if not left:
            lp = _fmt_pull(left_pull)
            left = {
                "en": f"{lp} below",
                "zh": f"偏低 {lp}",
                "zh_hk": f"偏低 {lp}",
            }.get(code, f"{lp} below")
            if second and second != code:
                other = {
                    "en": f"{lp} below",
                    "zh": f"偏低 {lp}",
                    "zh_hk": f"偏低 {lp}",
                }.get(second)
                if other and other != left:
                    left = f"{left}\n{other}"
        if not right:
            rp = _fmt_pull(right_pull)
            right = {
                "en": f"{rp} above",
                "zh": f"偏高 {rp}",
                "zh_hk": f"偏高 {rp}",
            }.get(code, f"{rp} above")
            if second and second != code:
                other = {
                    "en": f"{rp} above",
                    "zh": f"偏高 {rp}",
                    "zh_hk": f"偏高 {rp}",
                }.get(second)
                if other and other != right:
                    right = f"{right}\n{other}"
        panel_h = 100
        py = box_y + box_h - foot - panel_h - 10
        gap = 36
        mid = W // 2
        left_box = (100, py, mid - gap // 2, py + panel_h)
        right_box = (mid + gap // 2, py, W - 100, py + panel_h)
        draw.rounded_rectangle(left_box, radius=16, fill=theme["gold"])
        draw.rounded_rectangle(right_box, radius=16, fill=theme["gold"])
        lw = left_box[2] - left_box[0] - 32
        pl, _h = _shared_layouts(draw, [left, right], lw, panel_h - 14, 40, 16, 0.66, 1, 1)
        _paint_block(draw, (left_box[0] + 16, left_box[1], left_box[2] - 16, left_box[3]), pl[0], theme["navy"], theme["navy"])
        _paint_block(draw, (right_box[0] + 16, right_box[1], right_box[2] - 16, right_box[3]), pl[1], theme["navy"], theme["navy"])
        # equals hint between panels
        eq = "="
        ef = fit_font(draw, eq, 36, 40, True, 24, 1)
        _center(draw, (mid - 20, py, mid + 20, py + panel_h), eq, ef, theme["bg"])

    if footer and _show(stage, 3):
        fl = _block_layout(draw, footer, W - 240, foot - 24, 36, 20, 0.72, 1, 1)
        _paint_block(draw, (100, box_y + box_h - foot + 8, W - 100, box_y + box_h - 16), fl, theme["gold"], theme["bg"])


# ---------------------------------------------------------------- box_line
_BOX_TAG = {"en": "MIDDLE HALF", "zh": "中间一半", "zh_hk": "中間一半"}
_BOX_FENCE_TAG = {"en": "FENCES", "zh": "围栏", "zh_hk": "圍欄"}


def box_numbers(beat: dict) -> list[float]:
    """Numeric values, in the order written (box_line sorts them on the axis)."""
    raw = beat.get("values")
    if raw in (None, ""):
        raw = beat.get("values_en")
    nums = []
    for cell in _split_balance_list(raw):
        num = _rank_number(cell)
        if num is None:
            return []
        nums.append(num)
    return nums


def box_cells(beat: dict) -> list[str]:
    raw = beat.get("values")
    if raw in (None, ""):
        raw = beat.get("values_en")
    return _split_balance_list(raw)


def _box_scalar(beat: dict, key: str):
    raw = beat.get(key)
    if raw is None or raw == "":
        return None
    return _rank_number(str(raw))


def _nearest_rank(sorted_nums: list[float], p: float) -> float:
    n = len(sorted_nums)
    place = max(1, min(n, math.ceil(p * n - 1e-9)))
    return sorted_nums[place - 1]


def box_quartiles(beat: dict) -> tuple:
    """(q1, q3). Given `q1` / `q3` win; otherwise nearest rank: place = p × n, rounded up."""
    nums = sorted(box_numbers(beat))
    if not nums:
        return None, None
    q1 = _box_scalar(beat, "q1")
    q3 = _box_scalar(beat, "q3")
    if q1 is None:
        q1 = _nearest_rank(nums, 0.25)
    if q3 is None:
        q3 = _nearest_rank(nums, 0.75)
    return q1, q3


def box_fences(beat: dict):
    """(lower, upper) fences, None when off, or "bad" when unreadable.

    `fences: on` (or true / 1.5) gives Q1 − 1.5 × IQR and Q3 + 1.5 × IQR;
    `fences: 190;510` gives them directly.
    """
    raw = beat.get("fences")
    if raw is None or raw is False or str(raw).strip().lower() in ("", "off", "no", "none", "false"):
        return None
    q1, q3 = box_quartiles(beat)
    if q1 is None or q3 is None:
        return "bad"
    if raw is True or str(raw).strip().lower() in ("on", "yes", "true", "1.5", "tukey"):
        iqr = q3 - q1
        return (q1 - 1.5 * iqr, q3 + 1.5 * iqr)
    parts = _split_balance_list(raw)
    nums = [_rank_number(p) for p in parts]
    if len(nums) != 2 or any(n is None for n in nums):
        return "bad"
    return (min(nums), max(nums))


def box_line_problems(beat: dict) -> list[str]:
    problems = []
    cells = box_cells(beat)
    n = len(cells)
    if n < 3 or n > 8:
        problems.append(f"box_line needs 3 to 8 values, found {n}.")
    nums = box_numbers(beat)
    if n and not nums:
        problems.append("box_line values must be numbers (e.g. 280;310;360;390;420).")
    for key in ("q1", "q3", "median"):
        if beat.get(key) not in (None, "") and _box_scalar(beat, key) is None:
            problems.append(f"box_line {key} must be a number.")
    q1, q3 = box_quartiles(beat)
    if nums and q1 is not None and q3 is not None:
        if q1 > q3:
            problems.append("box_line q1 must not be above q3.")
        if q1 < min(nums) or q3 > max(nums):
            problems.append("box_line q1 and q3 must sit inside the values.")
    raw_break = beat.get("break")
    if raw_break not in (None, False, "") and str(raw_break).strip().lower() not in ("last", "top", "high"):
        problems.append("box_line break must be last (one far value at the top).")
    if raw_break not in (None, False, "") and len(nums) >= 2:
        s = sorted(nums)
        if s[-2] < (q3 if q3 is not None else s[-2]):
            problems.append("box_line break: last needs the far value above Q3.")
    fences = box_fences(beat)
    if fences == "bad":
        problems.append("box_line fences must be on, or two numbers (e.g. 190;510).")
    elif fences and q1 is not None and q3 is not None:
        if fences[0] > q1 or fences[1] < q3:
            problems.append("box_line fences must sit outside the box (lower <= Q1, upper >= Q3).")
        if raw_break not in (None, False, "") and len(nums) >= 2 and sorted(nums)[-1] <= fences[1]:
            problems.append("box_line fences with break: last need the far value above the upper fence.")
    return problems


def _blend(c1, c2, t: float):
    a = ImageColor.getrgb(c1) if isinstance(c1, str) else tuple(c1)
    b = ImageColor.getrgb(c2) if isinstance(c2, str) else tuple(c2)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _box_fmt(v: float) -> str:
    if float(v).is_integer():
        return f"{int(v):,}"
    return f"{v:g}"


def render_box_line(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """One horizontal box on a number line.

    Stage 1 the values as dots on the line, stage 2 Q1 and Q3 marked gold,
    stage 3 the box from Q1 to Q3, whiskers to the lowest and highest value,
    a bracket under the box with `span_*` (default "Q3 − Q1 = …"), and the footer.
    Optional `break: last` puts an axis break before one far value; optional
    `median` draws a line inside the box. The layout is pinned from stage 1.
    """
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    fences = box_fences(beat)
    if fences == "bad":
        fences = None
    table = _BOX_FENCE_TAG if fences else _BOX_TAG
    tag = field2(beat, "tag", code, second)
    if tag:
        a, b = _split_pair(tag)
        tag = f"{a}  {b}" if b else a
    else:
        tag = table.get(code, table["en"])
        if second:
            other = table.get(second)
            if other and other != tag:
                tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    cells = box_cells(beat)
    nums = box_numbers(beat)
    if not nums or len(cells) != len(nums):
        return
    q1, q3 = box_quartiles(beat)
    med = _box_scalar(beat, "median")
    footer = _minus_sign(field2(beat, "footer", code, second) or field2(beat, "note", code, second))
    span_text = _minus_sign(field2(beat, "span", code, second) or "")
    if not span_text:
        if fences:
            span_text = f"1.5 \u00d7 {_box_fmt(q3 - q1)} = {_box_fmt(1.5 * (q3 - q1))}"
        else:
            span_text = f"Q3 \u2212 Q1 = {_box_fmt(q3 - q1)}"
    order = sorted(range(len(nums)), key=lambda i: (nums[i], i))
    s_nums = [nums[i] for i in order]
    s_cells = [cells[i] for i in order]
    use_break = str(beat.get("break") or "").strip().lower() in ("last", "top", "high") and len(s_nums) >= 3
    white = theme.get("white") or "#FFFFFF"
    # ---- horizontal scale
    x_left, x_right = 190, W - 190
    main = s_nums[:-1] if use_break else s_nums
    lo, hi = min(main), max(main)
    if fences:
        lo = min(lo, fences[0])
        hi = max(hi, fences[1])
    span = (hi - lo) or max(1.0, abs(hi) * 0.2)
    pad = span * 0.06
    lo_s, hi_s = lo - pad, hi + pad
    main_right = x_right - 260 if use_break else x_right
    far_x = x_right - 40

    def x_at(v: float) -> float:
        if use_break and v > hi:
            return far_x
        return x_left + (v - lo_s) / (hi_s - lo_s) * (main_right - x_left)

    xs = [x_at(v) for v in s_nums]
    brk_x0, brk_x1 = main_right + 50, far_x - 70
    # ---- vertical plan (pinned on every stage)
    foot = (112 if "\n" in (footer or "") else 84) if footer else 20
    span_lines = 2 if "\n" in span_text else 1
    q_band = 64
    box_half = 70
    num_band = 60
    # fences widen the scale: numbers that crowd go on two staggered rows
    stagger = False
    if fences:
        _g = [b - a for a, b in zip(xs, xs[1:]) if b - a > 0]
        if _g and min(_g) < 90:
            stagger = True
            num_band = 100
    bracket = 30
    span_band = 52 * span_lines + 8
    block = q_band + 2 * box_half + 14 + num_band + bracket + span_band
    top_limit = box_y + 64
    bottom_limit = box_y + box_h - foot
    spare = max(0, (bottom_limit - top_limit) - block)
    top = top_limit + spare // 2
    line_y = top + q_band + box_half
    # axis (always)
    axis_fill = _blend(theme["navy"], white, 0.45)
    if use_break:
        draw.line([(x_left - 40, line_y), (brk_x0, line_y)], fill=axis_fill, width=3)
        draw.line([(brk_x1, line_y), (x_right + 30, line_y)], fill=axis_fill, width=3)
    else:
        draw.line([(x_left - 40, line_y), (x_right + 40, line_y)], fill=axis_fill, width=3)
    gold = theme["gold"]
    lit2 = _show(stage, 2)
    lit3 = _show(stage, 3)
    # fences plan: s1 box + whiskers, s2 fences + bracket Q3 -> upper fence, s3 values outside gold
    box_on = _show(stage, 1) if fences else lit3
    q_on = _show(stage, 1) if fences else lit2
    xq1, xq3 = x_at(q1), x_at(q3)
    outside = set()
    if fences:
        outside = {i for i, v in enumerate(s_nums) if v < fences[0] - 1e-9 or v > fences[1] + 1e-9}
        xf0, xf1 = x_at(fences[0]), x_at(fences[1])
        if lit2:
            fence_fill = _blend(gold, theme["navy"], 0.15)
            for fx in (xf0, xf1):
                yy = top + q_band - 8
                while yy < line_y + box_half:
                    draw.line([(fx, yy), (fx, min(yy + 16, line_y + box_half))], fill=fence_fill, width=5)
                    yy += 28
    if box_on:
        # whiskers: lowest -> Q1 and Q3 -> highest (inside the fences when drawn), with end caps
        inside = [x for i, x in enumerate(xs) if i not in outside] or xs
        wx0, wx1 = inside[0], inside[-1]
        draw.line([(wx0, line_y), (xq1, line_y)], fill=white, width=6)
        draw.line([(xq3, line_y), (wx1, line_y)], fill=white, width=6)
        for wx in (wx0, wx1):
            draw.line([(wx, line_y - 34), (wx, line_y + 34)], fill=white, width=6)
        # box
        draw.rounded_rectangle(
            [xq1, line_y - box_half, xq3, line_y + box_half],
            radius=14,
            fill=_blend(theme["navy"], white, 0.16),
            outline=gold,
            width=6,
        )
        if med is not None and q1 <= med <= q3:
            mx = x_at(med)
            draw.line([(mx, line_y - box_half + 6), (mx, line_y + box_half - 6)], fill=white, width=5)
    if use_break:
        # break marks over the axis / whisker
        cut_fill = theme["navy"]
        draw.rectangle([brk_x0 + 8, line_y - 10, brk_x1 - 8, line_y + 10], fill=cut_fill)
        for cxb in (brk_x0 + 14, brk_x1 - 14):
            draw.line([(cxb - 10, line_y + 18), (cxb + 10, line_y - 18)], fill=gold, width=5)
        for k in range(3):
            dx = (brk_x0 + brk_x1) / 2 + (k - 1) * 14
            draw.ellipse([dx - 3, line_y - 3, dx + 3, line_y + 3], fill=gold)
    # value dots and numbers (always)
    gaps = [b - a for a, b in zip(xs, xs[1:]) if b - a > 0]
    if stagger:
        gaps = [b - a for a, b in zip(xs, xs[2:]) if b - a > 0]
    min_gap = min(gaps or [400])
    num_w = int(max(70, min(220, min_gap - 10)))
    longest = max(s_cells, key=len)
    if fences and use_break and len(s_cells) > 2:
        longest = max(s_cells[:-1], key=len)  # the far value has room of its own past the break
    nf = fit_font(draw, longest, 44, num_w, True, 20, 1)
    q_places = set()
    if q_on:
        for target in (q1, q3):
            for i, v in enumerate(s_nums):
                if abs(v - target) < 1e-9 and i not in q_places:
                    q_places.add(i)
                    break
    ny0 = line_y + box_half + 14
    for i, (x, cell) in enumerate(zip(xs, s_cells)):
        is_q = i in q_places
        is_out = lit3 and i in outside
        r = 15 if (is_q or is_out) else 12
        if is_out:
            draw.ellipse([x - 30, line_y - 30, x + 30, line_y + 30], outline=gold, width=5)
        draw.ellipse([x - r, line_y - r, x + r, line_y + r], fill=gold if (is_q or is_out) else white)
        if stagger:
            nyy = ny0 + (40 if i % 2 else 0)
            _center(draw, (x - num_w / 2, nyy, x + num_w / 2, nyy + 60), cell, nf, gold if (is_q or is_out) else white)
        else:
            _center(draw, (x - num_w / 2, ny0, x + num_w / 2, ny0 + num_band), cell, nf, gold if (is_q or is_out) else white)
    # fence numbers above the dashed lines (language-neutral)
    if fences and lit2:
        ff = fit_font(draw, _box_fmt(fences[1]), 40, 220, True, 22, 1)
        for fv, fx in ((fences[0], xf0), (fences[1], xf1)):
            _center(draw, (fx - 110, top, fx + 110, top + q_band - 10), _box_fmt(fv), ff, _blend(gold, theme["navy"], 0.15))
    # Q1 / Q3 labels above the box (language-neutral)
    if q_on:
        qf = fit_font(draw, f"Q3 = {_box_fmt(q3)}", 40, 300, True, 22, 1)
        for name, val, qx in (("Q1", q1, xq1), ("Q3", q3, xq3)):
            if not any(abs(val - v) < 1e-9 for v in s_nums):
                draw.ellipse([qx - 9, line_y - 9, qx + 9, line_y + 9], fill=gold)
            lab = f"{name} = {_box_fmt(val)}"
            _center(draw, (qx - 150, top, qx + 150, top + q_band - 10), lab, qf, gold)
            draw.line([(qx, top + q_band - 8), (qx, line_y - box_half - 2)], fill=gold, width=3)
    # bracket under the box (fences: from Q3 out to the upper fence, on stage 2) + span text
    if (lit2 if fences else lit3):
        by = ny0 + num_band + 4
        tick = 18
        bx0, bx1 = (xq3, xf1) if fences else (xq1, xq3)
        draw.line([(bx0, by), (bx0, by + tick)], fill=white, width=4)
        draw.line([(bx1, by), (bx1, by + tick)], fill=white, width=4)
        draw.line([(bx0, by + tick), (bx1, by + tick)], fill=white, width=4)
        mid = (bx0 + bx1) / 2
        draw.line([(mid, by + tick), (mid, by + tick + 8)], fill=white, width=4)
        tw = max(520, int(bx1 - bx0) + 120)
        tx0 = max(100, min(W - 100 - tw, mid - tw / 2))
        sl = _block_layout(draw, span_text, tw, span_band, 46, 22, 0.66, 1, 1)
        _paint_block(draw, (tx0, by + tick + 10, tx0 + tw, by + tick + 10 + span_band), sl, gold, theme["bg"])
    if footer and lit3:
        fl = _block_layout(draw, footer, W - 240, foot - 24, 36, 20, 0.72, 1, 1)
        _paint_block(draw, (100, box_y + box_h - foot + 8, W - 100, box_y + box_h - 16), fl, gold, theme["bg"])


# ---------------------------------------------------------------- dev_bars
_DEV_TAG = {
    1: {"en": "DISTANCE FROM THE MEAN", "zh": "离平均数的距离", "zh_hk": "離平均數嘅距離"},
    2: {"en": "TIMES ITSELF", "zh": "自己乘自己", "zh_hk": "自己乘自己"},
    3: {"en": "CUBED", "zh": "立方", "zh_hk": "立方"},
    4: {"en": "FOURTH POWER", "zh": "四次方", "zh_hk": "四次方"},
}
_DEV_MEAN = {"en": "mean", "zh": "平均数", "zh_hk": "平均數"}


def _dev_list(beat: dict, key: str) -> list[float]:
    raw = beat.get(key)
    if raw in (None, ""):
        raw = beat.get(f"{key}_en")
    nums = []
    for cell in _split_balance_list(raw):
        num = _rank_number(cell)
        if num is None:
            return []
        nums.append(num)
    return nums


def _dev_count(beat: dict, key: str) -> int:
    raw = beat.get(key)
    if raw in (None, ""):
        raw = beat.get(f"{key}_en")
    return len(_split_balance_list(raw))


def dev_power(beat: dict) -> int:
    raw = beat.get("power")
    if raw in (None, ""):
        return 1
    try:
        return int(str(raw).strip())
    except ValueError:
        return 0


def dev_deviations(beat: dict, key: str = "values") -> list[float]:
    nums = _dev_list(beat, key)
    mean = balance_mean(beat)
    if mean is None:
        return []
    return [v - mean for v in nums]


def dev_standardize(beat: dict) -> bool:
    return str(beat.get("standardize", "")).strip().lower() in ("1", "true", "yes", "on")


def _dev_sigma(devs: list[float]) -> float:
    """Population SD of one row of deviations (divide by n, as in M01)."""
    if not devs:
        return 0.0
    return (sum(d * d for d in devs) / len(devs)) ** 0.5


def _dev_mark_token(beat: dict) -> str:
    return str(beat.get("mark") if beat.get("mark") is not None else "far").strip().lower()


def dev_marked(beat: dict) -> list[int]:
    """0-based bars lit gold on stage 3. far (default) = the largest distance(s)."""
    devs = dev_deviations(beat)
    n = len(devs)
    tok = _dev_mark_token(beat)
    if not n or tok in ("none", "", "false", "0"):
        return []
    if tok == "all":
        return list(range(n))
    if tok in ("far", "largest", "max"):
        top = max(abs(d) for d in devs)
        if top <= 0:
            return []
        return [i for i, d in enumerate(devs) if abs(abs(d) - top) < 1e-9]
    return [i - 1 for i in _rank_indices(tok, n)]


def dev_bars_problems(beat: dict) -> list[str]:
    problems = []
    n = _dev_count(beat, "values")
    if n < 3 or n > 6:
        problems.append(f"dev_bars needs 3 to 6 values, found {n}.")
    nums = _dev_list(beat, "values")
    if n and not nums:
        problems.append("dev_bars values must be numbers (e.g. 300;330;365;400;430).")
    if balance_mean(beat) is None:
        problems.append("dev_bars needs mean (e.g. mean: 365).")
    if beat.get("values_b") not in (None, ""):
        b = _dev_list(beat, "values_b")
        if not b or len(b) != len(nums):
            problems.append("dev_bars values_b must be numbers, as many as values.")
    if dev_power(beat) not in (1, 2, 3, 4):
        problems.append("dev_bars power must be 1, 2, 3, or 4.")
    if dev_standardize(beat):
        if dev_power(beat) < 2:
            problems.append("dev_bars standardize needs power 2, 3, or 4.")
        if nums and _dev_sigma(dev_deviations(beat)) <= 0:
            problems.append("dev_bars standardize needs values that are not all equal to the mean.")
    tok = _dev_mark_token(beat)
    if tok not in ("none", "", "false", "0", "all", "far", "largest", "max"):
        if not _rank_index_token(tok) or len(_rank_indices(tok, max(n, 1))) == 0:
            problems.append("dev_bars mark must be far, none, all, or 1-based places such as 1;5.")
    lab_lengths = [len(row) for row in (_balance_labels_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if lab_lengths and nums and any(ln != len(nums) for ln in lab_lengths):
        problems.append("dev_bars labels length must match the value count.")
    return problems


def _dev_fmt(v: float, signed: bool = False) -> str:
    if abs(v) < 1e-9:
        return "0"
    body = _box_fmt(abs(v))
    if v < 0:
        return f"\u2212{body}"
    return f"+{body}" if signed else body


def _dev_pair_text(table: dict, code: str, second, fmt: str) -> str:
    one = fmt.format(table.get(code, table["en"]))
    if second and second != code:
        other = fmt.format(table.get(second, table["en"]))
        if other != one:
            return f"{one}\n{other}"
    return one


def render_dev_bars(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Signed distance bars around a mean line.

    power 1 (default): stage 1 the days as dots above or below the mean line,
    stage 2 signed bars with their distance (−65 … +65), stage 3 the far bars
    gold + footer.
    power 2/3/4: stage 1 the products row under each day (−65 × −65) with the
    powered bars drawn muted and unlabelled, stage 2 the bars in full with their
    values (squares tower, odd powers keep the sign), stage 3 the far bars gold
    + footer. Even powers reserve no room below the mean line, so the bars fill
    the card. `signed_first: true` restores the older plan (stage 1 = the signed
    distance bars, which then keeps room below the line). Optional `values_b` draws a second shop
    beside each bar on the same scale. The mean line is pinned on every stage.
    `standardize: true` (power 2-4) divides each powered distance by sigma to
    the same power (sigma from that shop's own days, divide by n), so the bars
    read as small plain numbers (60^4 / 1,440^2 = 6.25); the mean of those is
    the variance ratio (power 2, = 1), skewness (3) or kurtosis (4).
    """
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    p = dev_power(beat)
    if p not in (1, 2, 3, 4):
        p = 1
    tag = field2(beat, "tag", code, second)
    if tag:
        a, b = _split_pair(tag)
        tag = f"{a}  {b}" if b else a
    else:
        table = _DEV_TAG[p]
        tag = table.get(code, table["en"])
        if second:
            other = table.get(second)
            if other and other != tag:
                tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    mean = balance_mean(beat)
    da = dev_deviations(beat, "values")
    if not da or mean is None:
        return
    db = dev_deviations(beat, "values_b") if beat.get("values_b") not in (None, "") else []
    if db and len(db) != len(da):
        db = []
    n = len(da)
    raw_a = _dev_list(beat, "values")
    labels = balance_labels(beat, code, second)
    while len(labels) < n:
        labels.append("")
    labels = labels[:n]
    footer = _minus_sign(field2(beat, "footer", code, second) or field2(beat, "note", code, second))
    white = theme.get("white") or (247, 244, 238)
    gold = theme["gold"]
    b_fill = _blend(theme["navy"], white, 0.5)
    muted = _blend(theme["navy"], white, 0.62)
    # ---- legend for two shops (tag row, right side)
    if db:
        def _leg(stem, default):
            txt = field2(beat, stem, code, second) or default
            a, b = _split_pair(txt)
            return f"{a}  {b}" if b else a
        items = [(_leg("name_a", "A"), white), (_leg("name_b", "B"), b_fill)]
        lf = font_for("A店 Shop A", 28, bold=True)
        x = W - 104
        for txt, col in reversed(items):
            tw = mixed_length(draw, txt, 28, bold=True)
            x -= tw
            draw_mixed(draw, (x, box_y + 14), txt, 28, theme["bg"], bold=True)
            x -= 40
            draw.rounded_rectangle([x, box_y + 18, x + 28, box_y + 46], radius=6, fill=col)
            x -= 44
    # ---- vertical plan (pinned)
    dual_labels = any(_split_pair(l)[1] for l in labels)
    has_labels = any(labels)
    label_band = (78 if dual_labels else 52) if has_labels else 0
    sub_band = 0 if db else 44
    foot = (104 if "\n" in (footer or "") else 80) if footer else 20
    lab = 48  # number label above / below the longest bars
    signed_first = p > 1 and str(beat.get("signed_first", "")).strip().lower() in ("1", "true", "yes", "on")
    top = box_y + 58
    bottom = box_y + box_h - foot - label_band - sub_band - 10
    H_ = max(120, bottom - top - 2 * lab)
    all_d = da + db
    fin_a = [d ** p for d in da]
    fin_b = [d ** p for d in db]
    std = p > 1 and dev_standardize(beat)
    if std:
        sa, sb = _dev_sigma(da), _dev_sigma(db)
        fin_a = [round(f / sa ** p, 2) for f in fin_a] if sa > 0 else fin_a
        fin_b = [round(f / sb ** p, 2) for f in fin_b] if sb > 0 else fin_b
    all_f = fin_a + fin_b
    pos_d, neg_d = max([0.0] + [d for d in all_d]), max([0.0] + [-d for d in all_d])
    pos_f, neg_f = max([0.0] + all_f), max([0.0] + [-f for f in all_f])
    if p == 1:
        down = neg_d / (pos_d + neg_d) if pos_d + neg_d > 0 else 0.5
    else:
        down = neg_f / (pos_f + neg_f) if pos_f + neg_f > 0 else 0.0
        if neg_d > 0 and signed_first:
            # room for the signed bars of stage 1; even powers then grow upward only
            down = max(down, 0.22)
    if down <= 0:
        # nothing is ever drawn below the line: give that label room to the bars
        H_ += lab - 14
    zero_y = int(top + lab + H_ * (1 - down))
    up_room = zero_y - (top + lab)
    down_room = top + lab + H_ - zero_y

    def _scale(pos, neg):
        cands = []
        if pos > 0:
            cands.append(up_room / pos)
        if neg > 0:
            cands.append(down_room / neg)
        return min(cands) if cands else 1.0

    s_d = _scale(pos_d, neg_d)
    s_f = _scale(pos_f, neg_f)
    # ---- horizontal plan
    gut = 200  # mean label gutter on the left
    x_left, x_right = 100 + gut, W - 110
    slot = (x_right - x_left) / n
    if db:
        bw = int(max(44, min(120, slot * 0.34)))
        offs = (-bw / 2 - 6, bw / 2 + 6)
    else:
        bw = int(max(56, min(168, slot * 0.5)))
        offs = (0.0,)
    centers = [x_left + slot * (i + 0.5) for i in range(n)]
    # mean line (always) + label in the gutter
    draw.line([(x_left - 24, zero_y), (x_right + 10, zero_y)], fill=gold, width=4)
    mtxt = _dev_pair_text(_DEV_MEAN, code, second, "{} = " + _box_fmt(mean))
    ml = _block_layout(draw, mtxt, gut - 16, 90, 30, 16, 0.8, 1, 1)
    _paint_block(draw, (96, zero_y - 46, 96 + gut - 24, zero_y + 46), ml, gold, gold, align="left")
    # stage plan
    power_stage = p > 1 and (_show(stage, 2) or not signed_first)
    ghost = p > 1 and not signed_first and not _show(stage, 2)  # muted, unlabelled
    dots_only = p == 1 and not _show(stage, 2)
    lit = set(dev_marked(beat)) if _show(stage, 3) else set()
    longest = max([_dev_fmt(v, True) for v in all_d] + ([_dev_fmt(v) for v in all_f] if p > 1 else []), key=len)
    # two shops: each number owns its half of the day slot, so it never runs into the twin bar
    half_w = int(slot / 2 - 8)
    nf = fit_font(draw, longest, 40 if not db else 34, half_w if db else int(max(bw + 24, min(slot - 12, bw * 2))), True, 18, 1)
    pending = []  # numbers are painted after every bar, so no bar covers a number
    for i in range(n):
        series = [(da[i], fin_a[i] if p > 1 else da[i], False)]
        if db:
            series.append((db[i], fin_b[i] if p > 1 else db[i], True))
        for (d, f, is_b), off in zip(series, offs):
            cx = centers[i] + off
            fill = b_fill if is_b else (gold if i in lit else white)
            if ghost:
                fill = _blend(theme["navy"], white, 0.32) if not is_b else _blend(theme["navy"], white, 0.2)
            txt_fill = b_fill if is_b else (gold if i in lit else theme["bg"])
            if dots_only:
                yy = zero_y - d * s_d
                r = 14 if not is_b else 11
                draw.line([(cx, zero_y), (cx, yy)], fill=muted, width=2)
                draw.ellipse([cx - r, yy - r, cx + r, yy + r], fill=fill)
                continue
            val, sc = (f, s_f) if power_stage else (d, s_d)
            h = val * sc
            if abs(h) < 6 and abs(val) > 0:
                h = 6 if h > 0 else -6
            y0, y1 = (zero_y - h, zero_y) if h >= 0 else (zero_y, zero_y - h)
            if abs(val) > 0:
                draw.rounded_rectangle([cx - bw / 2, y0, cx + bw / 2, y1], radius=min(12, max(2, int(abs(h) // 2))), fill=fill)
            else:
                draw.ellipse([cx - 9, zero_y - 9, cx + 9, zero_y + 9], fill=fill)
            if ghost:
                continue
            txt = _dev_fmt(val, signed=not power_stage or p % 2 == 1)
            lw = int(max(bw + 24, min(slot - 12, bw * 2)))
            if db:
                hx0 = centers[i] + 4 if is_b else centers[i] - slot / 2 + 4
                hx1 = centers[i] + slot / 2 - 4 if is_b else centers[i] - 4
            else:
                hx0, hx1 = cx - lw / 2, cx + lw / 2
            if h >= 0:
                lift = 14 if abs(val) == 0 else 4  # clear the zero dot
                pending.append(((hx0, y0 - lab - lift + 4, hx1, y0 - lift), txt, txt_fill))
            else:
                pending.append(((hx0, y1 + 4, hx1, y1 + lab), txt, txt_fill))
    for box_, txt, col in pending:
        _center(draw, box_, txt, nf, col)
    # day labels + sub row
    ly = bottom + 10
    for i, cx in enumerate(centers):
        if labels[i]:
            ll = _block_layout(draw, labels[i], int(slot - 12), label_band - 6, 34, 16, 0.72, 1, 1)
            _paint_block(draw, (cx - slot / 2 + 6, ly, cx + slot / 2 - 6, ly + label_band), ll, theme["bg"], gold, valign="top")
        if sub_band:
            if p == 1:
                sub = _box_fmt(raw_a[i])
            elif power_stage:
                d = _dev_fmt(da[i], True)
                sub = f"{d} × {d}" if p == 2 else f"({d})" + {3: "³", 4: "⁴"}[p]
                if std:
                    sub = f"({d})" + {2: "²", 3: "³", 4: "⁴"}[p] + " / σ" + {2: "²", 3: "³", 4: "⁴"}[p]
            else:
                sub = ""
            if sub:
                sf = fit_font(draw, sub, 30, int(slot - 16), True, 16, 1)
                _center(draw, (cx - slot / 2 + 8, ly + label_band, cx + slot / 2 - 8, ly + label_band + sub_band), sub, sf, muted)
    if footer and _show(stage, 3):
        fl = _block_layout(draw, footer, W - 240, foot - 24, 36, 20, 0.72, 1, 1)
        _paint_block(draw, (100, box_y + box_h - foot + 8, W - 100, box_y + box_h - 16), fl, gold, theme["bg"])


# ---------------------------------------------------------------- ratio_bars
_RATIO_TAG = {
    1: {"en": "SWING IN CUPS", "zh": "晃动（杯）", "zh_hk": "搖動（杯）"},
    2: {"en": "AGAINST ITS OWN AVERAGE", "zh": "跟自己的平均数比", "zh_hk": "同自己嘅平均數比"},
    3: {"en": "SWING AS A SHARE", "zh": "晃动占多少", "zh_hk": "搖動佔幾多"},
}
_RATIO_AVG = {"en": "average", "zh": "平均", "zh_hk": "平均"}


def ratio_means(beat: dict) -> list[float]:
    return _dev_list(beat, "means")


def ratio_sds(beat: dict) -> list[float]:
    return _dev_list(beat, "sds")


def ratio_cvs(beat: dict) -> list[float]:
    """Coefficient of variation in percent, one per bar (SD / mean × 100)."""
    m, s = ratio_means(beat), ratio_sds(beat)
    if not m or len(m) != len(s) or any(v <= 0 for v in m):
        return []
    return [100.0 * sd / mu for sd, mu in zip(s, m)]


def _ratio_pct(v: float) -> str:
    r = round(v, 1)
    return f"{int(r)}%" if float(r).is_integer() else f"{r:g}%"


def ratio_marked(beat: dict) -> list[int]:
    """0-based bars lit gold on stage 3. highest (default) = the largest CV."""
    cvs = ratio_cvs(beat)
    n = len(cvs)
    tok = str(beat.get("mark") if beat.get("mark") is not None else "highest").strip().lower()
    if not n or tok in ("none", "", "false", "0"):
        return []
    if tok == "all":
        return list(range(n))
    if tok in ("highest", "max", "largest"):
        top = max(cvs)
        return [i for i, c in enumerate(cvs) if abs(c - top) < 1e-9]
    if tok in ("lowest", "min", "smallest"):
        low = min(cvs)
        return [i for i, c in enumerate(cvs) if abs(c - low) < 1e-9]
    return [i - 1 for i in _rank_indices(tok, n)]


def ratio_bars_problems(beat: dict) -> list[str]:
    problems = []
    n = _dev_count(beat, "means")
    if n < 2 or n > 4:
        problems.append(f"ratio_bars needs 2 to 4 means, found {n}.")
    m = _dev_list(beat, "means")
    s = _dev_list(beat, "sds")
    if n and not m:
        problems.append("ratio_bars means must be numbers (e.g. 300;3000).")
    elif m and any(v <= 0 for v in m):
        problems.append("ratio_bars means must be above zero (the CV divides by them).")
    if not s or len(s) != len(m):
        problems.append("ratio_bars sds must be numbers, as many as means (e.g. 30;150).")
    elif any(v < 0 for v in s):
        problems.append("ratio_bars sds must not be negative.")
    elif m and any(sd > mu for sd, mu in zip(s, m)):
        problems.append("ratio_bars expects each sd to be at most its mean (the slice sits inside the bar).")
    tok = str(beat.get("mark") if beat.get("mark") is not None else "highest").strip().lower()
    if tok not in ("none", "", "false", "0", "all", "highest", "max", "largest", "lowest", "min", "smallest"):
        if not _rank_index_token(tok) or len(_rank_indices(tok, max(n, 1))) == 0:
            problems.append("ratio_bars mark must be highest, lowest, none, all, or 1-based places such as 2.")
    lab_lengths = [len(row) for row in (_balance_labels_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if lab_lengths and m and any(ln != len(m) for ln in lab_lengths):
        problems.append("ratio_bars labels length must match the number of means.")
    return problems


def render_ratio_bars(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Coefficient of variation as a slice of each shop's own average.

    Stage 1: the standard deviations as bars on one shared scale (30 vs 150 —
    the big shop looks jumpier). Stage 2: every bar becomes its own average at
    full height, with the standard deviation as the white slice on top (30 of
    300, 150 of 3,000). Stage 3: the share is written large in each bar (10%,
    5%), the `mark` bar(s) turn gold, and the footer shows. Bar slots, the
    baseline and the full height are pinned on every stage.
    """
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    st = 3 if stage in (None, 0) else max(1, min(3, int(stage)))
    tag = field2(beat, f"tag{st}", code, second) or field2(beat, "tag", code, second)
    if tag:
        a, b = _split_pair(tag)
        tag = f"{a}  {b}" if b else a
    else:
        table = _RATIO_TAG[st]
        tag = table.get(code, table["en"])
        if second:
            other = table.get(second)
            if other and other != tag:
                tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    means, sds = ratio_means(beat), ratio_sds(beat)
    if not means or len(sds) != len(means):
        return
    n = len(means)
    cvs = ratio_cvs(beat) or [0.0] * n
    labels = balance_labels(beat, code, second)
    while len(labels) < n:
        labels.append("")
    labels = labels[:n]
    unit = _split_pair(field2(beat, "unit", code, None) or "")[0]
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    white = theme.get("white") or (247, 244, 238)
    gold = theme["gold"]
    body = _blend(theme["navy"], white, 0.26)
    muted = _blend(theme["navy"], white, 0.62)
    lit = set(ratio_marked(beat)) if _show(stage, 3) else set()
    # ---- vertical plan (pinned)
    dual = any("\n" in l for l in labels)
    label_band = (84 if dual else 56) if any(labels) else 0
    foot = (104 if "\n" in (footer or "") else 80) if footer else 16
    val_band = 60
    top = box_y + 66
    base = box_y + box_h - foot - label_band - 14
    full = max(140, base - top - val_band)
    # ---- horizontal plan: bar on the left of each slot, notes on its right
    slot = (W - 200) / n
    bw = int(max(120, min(300, slot * 0.34)))
    xs = [100 + slot * i + max(40, slot * 0.16) for i in range(n)]
    note_w = int(slot - (xs[0] - 100) - bw - 48)
    max_sd = max(sds) or 1.0
    draw.line([(96, base), (W - 96, base)], fill=muted, width=3)
    big = 76 if n <= 2 else 60
    for i in range(n):
        x0 = xs[i]
        x1 = x0 + bw
        cx = (x0 + x1) / 2
        hot = i in lit
        sd_txt = _box_fmt(sds[i]) + (f" {unit}" if unit else "")
        if not _show(stage, 2):
            h = max(8, full * sds[i] / max_sd)
            draw.rounded_rectangle([x0, base - h, x1, base], radius=12, fill=white)
            vf = fit_font(draw, sd_txt, 44, int(slot * 0.9), True, 20, 1)
            _center(draw, (cx - slot * 0.45, base - h - val_band, cx + slot * 0.45, base - h - 6), sd_txt, vf, theme["bg"])
        else:
            slice_h = max(10, full * sds[i] / means[i])
            draw.rounded_rectangle([x0, base - full, x1, base], radius=12, fill=body)
            draw.rounded_rectangle([x0, base - full, x1, base - full + slice_h], radius=min(12, int(slice_h // 2)), fill=gold if hot else white)
            avg_txt = _RATIO_AVG.get(code, "average") + " " + _box_fmt(means[i])
            af = fit_font(draw, avg_txt, 40, int(slot * 0.9), True, 20, 1)
            _center(draw, (cx - slot * 0.45, base - full - val_band, cx + slot * 0.45, base - full - 6), avg_txt, af, theme["bg"])
            # bracket + SD note beside the slice
            bx = x1 + 16
            sy0, sy1 = base - full, base - full + slice_h
            draw.line([(bx, sy0), (bx + 12, sy0), (bx + 12, sy1), (bx, sy1)], fill=gold if hot else white, width=3)
            nsz = int(getattr(fit_font(draw, sd_txt, 42, note_w, True, 20, 1), "size", 42))
            draw_mixed(draw, (bx + 26, (sy0 + sy1) / 2 - nsz * 0.62), sd_txt, nsz, gold if hot else theme["bg"], True)
            if _show(stage, 3):
                pct = _ratio_pct(cvs[i])
                pf = fit_font(draw, pct, big, bw - 16, True, 28, 1)
                mid = (sy1 + base) / 2
                _center(draw, (x0 + 4, mid - big * 0.7, x1 - 4, mid + big * 0.7), pct, pf, gold if hot else white)
                eq = f"{_box_fmt(sds[i])} / {_box_fmt(means[i])}"
                esz = int(getattr(fit_font(draw, eq, 38, note_w, True, 20, 1), "size", 38))
                draw_mixed(draw, (bx + 26, mid - esz * 0.62), eq, esz, muted, True)
        if labels[i]:
            ll = _block_layout(draw, labels[i], int(slot * 0.9), label_band - 6, 36, 18, 0.7, 1, 1)
            _paint_block(draw, (cx - slot * 0.45, base + 10, cx + slot * 0.45, base + 10 + label_band), ll, theme["bg"], gold, valign="top")
    if footer and _show(stage, 3):
        fl = _block_layout(draw, footer, W - 240, foot - 24, 36, 20, 0.72, 1, 1)
        _paint_block(draw, (100, box_y + box_h - foot + 8, W - 100, box_y + box_h - 16), fl, gold, theme["bg"])


# ---------------------------------------------------------------- quad_scatter
_QUAD_TAG = {
    1: {"en": "FIVE SHOPS", "zh": "五家店", "zh_hk": "五間店"},
    2: {"en": "MEANS AND QUADRANTS", "zh": "平均数与象限", "zh_hk": "平均數同象限"},
    3: {"en": "PAIRED PRODUCTS", "zh": "成对乘积", "zh_hk": "成對乘積"},
}


def quad_xs(beat: dict) -> list[float]:
    return _dev_list(beat, "xs")


def quad_ys(beat: dict) -> list[float]:
    return _dev_list(beat, "ys")


def quad_mean_x(beat: dict):
    raw = beat.get("mean_x")
    if raw not in (None, ""):
        num = _rank_number(str(raw))
        if num is not None:
            return num
    xs = quad_xs(beat)
    return (sum(xs) / len(xs)) if xs else None


def quad_mean_y(beat: dict):
    raw = beat.get("mean_y")
    if raw not in (None, ""):
        num = _rank_number(str(raw))
        if num is not None:
            return num
    ys = quad_ys(beat)
    return (sum(ys) / len(ys)) if ys else None


def quad_products(beat: dict) -> list[float]:
    xs, ys = quad_xs(beat), quad_ys(beat)
    mx, my = quad_mean_x(beat), quad_mean_y(beat)
    if not xs or len(xs) != len(ys) or mx is None or my is None:
        return []
    return [(x - mx) * (y - my) for x, y in zip(xs, ys)]


def _quad_fmt(v: float) -> str:
    if abs(v) >= 1000 and float(v).is_integer():
        body = f"{int(abs(v)):,}"
    elif float(v).is_integer():
        body = str(int(abs(v)))
    else:
        body = f"{abs(v):g}"
    if v < 0:
        return f"−{body}"
    if v > 0:
        return f"+{body}"
    return "0"


def quad_marked(beat: dict) -> list[int]:
    """0-based points lit gold on stage 3. same (default) = same-sign products."""
    prods = quad_products(beat)
    n = len(prods)
    tok = str(beat.get("mark") if beat.get("mark") is not None else "same").strip().lower()
    if not n or tok in ("none", "", "false", "0"):
        return []
    if tok == "all":
        return list(range(n))
    if tok in ("same", "positive", "plus"):
        # light points whose product sign matches the sum (or + if sum is 0)
        total = sum(prods)
        want = 1 if total >= 0 else -1
        return [i for i, p in enumerate(prods) if (p > 0 and want > 0) or (p < 0 and want < 0)]
    if tok in ("opposite", "negative", "minus"):
        total = sum(prods)
        want = -1 if total >= 0 else 1
        return [i for i, p in enumerate(prods) if (p > 0 and want > 0) or (p < 0 and want < 0)]
    return [i - 1 for i in _rank_indices(tok, n)]


def quad_scatter_problems(beat: dict) -> list[str]:
    problems = []
    mode = str(beat.get("mode") or "scatter").strip().lower()
    if mode in ("ruler", "scale", "r_scale"):
        raw_r = beat.get("r") if beat.get("r") is not None else beat.get("value")
        if raw_r in (None, ""):
            problems.append("quad_scatter mode:ruler needs r (e.g. 0.99 or -0.4).")
        else:
            num = _rank_number(str(raw_r))
            if num is None:
                problems.append("quad_scatter r must be a number between -1 and +1.")
            elif num < -1.05 or num > 1.05:
                problems.append("quad_scatter r must sit near -1 to +1.")
        return problems
    xs, ys = quad_xs(beat), quad_ys(beat)
    n = len(xs)
    if n < 3 or n > 8:
        problems.append(f"quad_scatter needs 3 to 8 xs, found {n}.")
    if not xs:
        problems.append("quad_scatter xs must be numbers (e.g. 10000;12000;14000;16000;18000).")
    if not ys or len(ys) != n:
        problems.append("quad_scatter ys must be numbers, as many as xs (e.g. 300;330;360;400;450).")
    for key in ("mean_x", "mean_y"):
        if beat.get(key) not in (None, "") and _rank_number(str(beat.get(key))) is None:
            problems.append(f"quad_scatter {key} must be a number.")
    tok = str(beat.get("mark") if beat.get("mark") is not None else "same").strip().lower()
    ok = ("none", "", "false", "0", "all", "same", "positive", "plus", "opposite", "negative", "minus")
    if tok not in ok:
        if not _rank_index_token(tok) or len(_rank_indices(tok, max(n, 1))) == 0:
            problems.append("quad_scatter mark must be same, opposite, none, all, or 1-based places such as 1;5.")
    lab_lengths = [len(row) for row in (_balance_labels_for(beat, code) for code in ("en", "zh", "zh_hk")) if row]
    if lab_lengths and xs and any(ln != len(xs) for ln in lab_lengths):
        problems.append("quad_scatter labels length must match the number of points.")
    if mode not in ("scatter", "quad", "points", ""):
        problems.append("quad_scatter mode must be scatter or ruler.")
    return problems



_QUAD_RULER_TAG = {
    1: {"en": "THE RULER", "zh": "标尺", "zh_hk": "標尺"},
    2: {"en": "THREE PATTERNS", "zh": "三种形态", "zh_hk": "三種形態"},
    3: {"en": "OUR FILE", "zh": "这份数据", "zh_hk": "呢份數據"},
}


def quad_r_value(beat: dict):
    raw = beat.get("r") if beat.get("r") is not None else beat.get("value")
    if raw in (None, ""):
        return None
    return _rank_number(str(raw))


def render_quad_ruler(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Unit-free r scale from -1 to +1 with three mini clouds and a gold pin.

    Stage 1: the ruler. Stage 2: tight-up / loose / tight-down clouds.
    Stage 3: gold pin at `r` + footer. Layout is pinned from stage 1.
    """
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    st = 3 if stage in (None, 0) else max(1, min(3, int(stage)))
    tag = field2(beat, f"tag{st}", code, second) or field2(beat, "tag", code, second)
    if tag:
        a, b = _split_pair(tag)
        tag = f"{a}  {b}" if b else a
    else:
        table = _QUAD_RULER_TAG[st]
        tag = table.get(code, table["en"])
        if second:
            other = table.get(second)
            if other and other != tag:
                tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    white = theme.get("white") or (247, 244, 238)
    gold = theme["gold"]
    muted = _blend(theme["navy"], white, 0.62)
    ink = theme["bg"]
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    r_val = quad_r_value(beat)
    foot = (104 if "\n" in (footer or "") else 80) if footer else 20
    # pinned geometry
    rail_y = box_y + box_h - foot - 56
    rail_l, rail_r = 140, W - 140
    cloud_top = box_y + 78
    cloud_bot = rail_y - 28
    cloud_h = max(110, cloud_bot - cloud_top)

    def rx(v: float) -> float:
        # map [-1,1] -> rail
        return rail_l + (rail_r - rail_l) * (v + 1) / 2

    # ---- stage 1+: ruler
    draw.line([(rail_l, rail_y), (rail_r, rail_y)], fill=white, width=4)
    ticks = [-1.0, -0.5, 0.0, 0.5, 1.0]
    labels = ["−1", "−0.5", "0", "+0.5", "+1"]
    for tv, lab in zip(ticks, labels):
        xx = rx(tv)
        draw.line([(xx, rail_y - 10), (xx, rail_y + 10)], fill=white, width=3)
        tf = fit_font(draw, lab, 28, 90, True, 16, 1)
        _center(draw, (xx - 45, rail_y + 14, xx + 45, rail_y + 44), lab, tf, white)

    # ---- stage 2+: three mini clouds
    if _show(stage, 2):
        # centers on the ruler: -0.85, 0, +0.85
        specs = [
            (-0.85, "neg", field2(beat, "left", code, second) or {"en": "Near −1", "zh": "接近−1", "zh_hk": "接近−1"}.get(code, "Near −1")),
            (0.0, "loose", field2(beat, "mid", code, second) or field2(beat, "center", code, second) or {"en": "Near 0", "zh": "接近0", "zh_hk": "接近0"}.get(code, "Near 0")),
            (0.85, "pos", field2(beat, "right", code, second) or {"en": "Near +1", "zh": "接近+1", "zh_hk": "接近+1"}.get(code, "Near +1")),
        ]
        # if left/mid/right returned a dict somehow — already resolved to str above
        box_w = 200
        for center, kind, caption in specs:
            cx = rx(center)
            x0, x1 = cx - box_w / 2, cx + box_w / 2
            y0, y1 = cloud_top, cloud_top + cloud_h
            # frame
            draw.rounded_rectangle([x0, y0, x1, y1], radius=14, outline=muted, width=2)
            # synthetic points in local 0..1 coords
            import random as _rnd
            rng = _rnd.Random(41 if kind == "neg" else (42 if kind == "loose" else 43))
            pts = []
            if kind == "pos":
                for i in range(7):
                    u = 0.12 + 0.76 * i / 6
                    v = u + rng.uniform(-0.06, 0.06)
                    pts.append((u, max(0.08, min(0.92, v))))
            elif kind == "neg":
                for i in range(7):
                    u = 0.12 + 0.76 * i / 6
                    v = 1 - u + rng.uniform(-0.06, 0.06)
                    pts.append((u, max(0.08, min(0.92, v))))
            else:
                for _i in range(9):
                    pts.append((rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85)))
            pad = 18
            for u, v in pts:
                px = x0 + pad + (x1 - x0 - 2 * pad) * u
                py = y1 - pad - (y1 - y0 - 2 * pad) * v
                rr = 7
                draw.ellipse([px - rr, py - rr, px + rr, py + rr], fill=white, outline=ink, width=1)
            # caption under cloud, above rail
            cap = caption if isinstance(caption, str) else str(caption)
            cf = fit_font(draw, cap, 26, box_w - 8, True, 14, 1)
            _center(draw, (x0, y1 + 4, x1, rail_y - 12), cap, cf, gold)

    # ---- stage 3: gold pin at r
    if _show(stage, 3) and r_val is not None:
        rv = max(-1.0, min(1.0, float(r_val)))
        xx = rx(rv)
        # needle
        draw.polygon(
            [(xx, rail_y - 28), (xx - 12, rail_y - 8), (xx + 12, rail_y - 8)],
            fill=gold,
        )
        draw.ellipse([xx - 8, rail_y - 8, xx + 8, rail_y + 8], fill=gold, outline=ink, width=2)
        # value chip
        if abs(rv) >= 0.995:
            lab = "+1.00" if rv > 0 else "−1.00"
        else:
            lab = f"{rv:+.2f}".replace("+", "+").replace("-", "−")
        lf = fit_font(draw, lab, 32, 120, True, 18, 1)
        _center(draw, (xx - 60, rail_y - 66, xx + 60, rail_y - 32), lab, lf, gold)

    if footer and _show(stage, 3):
        fl = _block_layout(draw, footer, W - 240, foot - 24, 36, 20, 0.72, 1, 1)
        _paint_block(draw, (100, box_y + box_h - foot + 8, W - 100, box_y + box_h - 16), fl, gold, theme["bg"])



def render_quad_scatter(draw, beat, code, y, theme, stage=None, second=None) -> None:
    """Scatter with mean cross-hairs and quadrant product signs.

    Stage 1: the points on the axes. Stage 2: mean lines and + / − quadrant
    signs. Stage 3: golds the `mark` points, writes each paired product beside
    its point, and shows the footer. The plot box is pinned from stage 1.

    Set `mode: ruler` for the −1…+1 scale with three mini clouds and a gold pin
    at `r` (see render_quad_ruler).
    """
    mode = str(beat.get("mode") or "scatter").strip().lower()
    if mode in ("ruler", "scale", "r_scale"):
        return render_quad_ruler(draw, beat, code, y, theme, stage=stage, second=second)
    box_y = y + 8
    box_h = _fill_h(box_y, 360)
    _panel(draw, (64, box_y, W - 64, box_y + box_h), theme["navy"], theme)
    st = 3 if stage in (None, 0) else max(1, min(3, int(stage)))
    tag = field2(beat, f"tag{st}", code, second) or field2(beat, "tag", code, second)
    if tag:
        a, b = _split_pair(tag)
        tag = f"{a}  {b}" if b else a
    else:
        table = _QUAD_TAG[st]
        tag = table.get(code, table["en"])
        if second:
            other = table.get(second)
            if other and other != tag:
                tag = f"{tag}  {other}"
    _tag(draw, 108, box_y + 16, tag, theme)
    xs, ys = quad_xs(beat), quad_ys(beat)
    if not xs or len(xs) != len(ys):
        return
    n = len(xs)
    mx, my = quad_mean_x(beat), quad_mean_y(beat)
    if mx is None or my is None:
        return
    prods = quad_products(beat)
    labels = balance_labels(beat, code, second)
    while len(labels) < n:
        labels.append("")
    labels = labels[:n]
    x_axis = field2(beat, "x_axis", code, second) or field2(beat, "xlabel", code, second) or ""
    y_axis = field2(beat, "y_axis", code, second) or field2(beat, "ylabel", code, second) or ""
    footer = field2(beat, "footer", code, second) or field2(beat, "note", code, second)
    white = theme.get("white") or (247, 244, 238)
    gold = theme["gold"]
    muted = _blend(theme["navy"], white, 0.62)
    ink = theme["bg"]
    lit = set(quad_marked(beat)) if _show(stage, 3) else set()
    # ---- pinned layout
    dual = any("\n" in (l or "") for l in labels) or ("\n" in (x_axis or "")) or ("\n" in (y_axis or ""))
    foot = (104 if "\n" in (footer or "") else 80) if footer else 16
    axis_band = 44 if x_axis else 20
    left_pad = 118 if y_axis else 72
    plot_l = 64 + left_pad
    plot_r = W - 96
    plot_t = box_y + 70
    plot_b = box_y + box_h - foot - axis_band - 8
    # scale: pad 8% beyond data (and means)
    x_lo, x_hi = min(xs + [mx]), max(xs + [mx])
    y_lo, y_hi = min(ys + [my]), max(ys + [my])
    x_pad = max((x_hi - x_lo) * 0.12, abs(x_hi) * 0.02, 1.0)
    y_pad = max((y_hi - y_lo) * 0.14, abs(y_hi) * 0.02, 1.0)
    x_lo, x_hi = x_lo - x_pad, x_hi + x_pad
    y_lo, y_hi = y_lo - y_pad, y_hi + y_pad

    def px(v):
        return plot_l + (plot_r - plot_l) * (v - x_lo) / (x_hi - x_lo)

    def py(v):
        return plot_b - (plot_b - plot_t) * (v - y_lo) / (y_hi - y_lo)

    # axes
    draw.line([(plot_l, plot_b), (plot_r, plot_b)], fill=muted, width=3)
    draw.line([(plot_l, plot_t), (plot_l, plot_b)], fill=muted, width=3)
    # sparse ticks inside the plot so they never collide with axis titles
    for xv in sorted({min(xs), max(xs), mx}):
        xx = px(xv)
        draw.line([(xx, plot_b - 8), (xx, plot_b)], fill=muted, width=2)
        t = _box_fmt(xv)
        tf = fit_font(draw, t, 26, 110, True, 16, 1)
        _center(draw, (xx - 55, plot_b - 34, xx + 55, plot_b - 8), t, tf, white)
    for yv in sorted({min(ys), max(ys), my}):
        yy = py(yv)
        draw.line([(plot_l, yy), (plot_l + 8, yy)], fill=muted, width=2)
        t = _box_fmt(yv)
        tf = fit_font(draw, t, 26, left_pad - 28, True, 16, 1)
        _center(draw, (72, yy - 16, plot_l - 10, yy + 16), t, tf, white)
    if y_axis:
        yl = _block_layout(draw, y_axis, left_pad - 24, 64, 30, 15, 0.7, 2, 1)
        _paint_block(draw, (72, plot_t - 2, plot_l - 10, plot_t + 62), yl, white, gold, valign="top")
    if x_axis:
        xl = _block_layout(draw, x_axis, plot_r - plot_l, axis_band - 6, 32, 15, 0.7, 1, 1)
        _paint_block(draw, (plot_l, plot_b + 10, plot_r, plot_b + 10 + axis_band - 6), xl, white, gold)

    # stage 2: mean cross-hairs + quadrant signs
    if _show(stage, 2):
        cx, cy = px(mx), py(my)
        # dashed mean lines (horizontal, then vertical)
        x = plot_l
        while x < plot_r:
            draw.line([(x, cy), (min(x + 14, plot_r), cy)], fill=gold, width=3)
            x += 22
        yy = plot_t
        while yy < plot_b:
            draw.line([(cx, yy), (cx, min(yy + 14, plot_b))], fill=gold, width=3)
            yy += 22
        # mean chips sit on the tick numbers (gold over muted)
        mx_txt = _box_fmt(mx)
        my_txt = _box_fmt(my)
        mf = fit_font(draw, mx_txt, 28, 120, True, 16, 1)
        _center(draw, (cx - 60, plot_b - 34, cx + 60, plot_b - 8), mx_txt, mf, gold)
        _center(draw, (72, cy - 16, plot_l - 10, cy + 16), my_txt, mf, gold)
        # quadrant signs: + in Q1/QIII, − in QII/QIV (x right, y up)
        sign_sz = 56
        pads = 36
        quads = [
            (cx + pads, cy - pads - sign_sz, "+"),
            (cx - pads - sign_sz, cy - pads - sign_sz, "−"),
            (cx - pads - sign_sz, cy + pads, "+"),
            (cx + pads, cy + pads, "−"),
        ]
        sf = fit_font(draw, "+", sign_sz, sign_sz + 8, True, 32, 1)
        for qx, qy, s in quads:
            if qx < plot_l + 4 or qx + sign_sz > plot_r - 4 or qy < plot_t + 4 or qy + sign_sz > plot_b - 4:
                continue
            _center(draw, (qx, qy, qx + sign_sz, qy + sign_sz), s, sf, white)

    # points (always from stage 1)
    r = 14
    for i, (xv, yv) in enumerate(zip(xs, ys)):
        xx, yy = px(xv), py(yv)
        hot = i in lit
        fill = gold if hot else white
        draw.ellipse([xx - r, yy - r, xx + r, yy + r], fill=fill, outline=ink, width=2)
        lab = labels[i]
        if lab:
            ll = _block_layout(draw, lab, 120, 50 if dual else 32, 30, 14, 0.7, 1, 1)
            # place label above point, nudge if near top
            ly1 = yy - r - 8
            ly0 = ly1 - (50 if dual else 32)
            if ly0 < plot_t:
                ly0 = yy + r + 6
                ly1 = ly0 + (50 if dual else 32)
            _paint_block(draw, (xx - 60, ly0, xx + 60, ly1), ll, gold if hot else white, gold)
        if _show(stage, 3) and prods:
            pt = _quad_fmt(prods[i])
            pf = fit_font(draw, pt, 26, 120, True, 14, 1)
            above = (i % 2 == 0)
            ty0 = (yy - r - 30) if above else (yy + r + 4)
            ty1 = ty0 + 26
            if ty0 < plot_t + 2:
                ty0, ty1 = yy + r + 4, yy + r + 30
            if ty1 > plot_b - 2:
                ty0, ty1 = yy - r - 30, yy - r - 4
            tx0 = xx - 55
            if xx + 55 > plot_r - 4:
                tx0 = plot_r - 114
            if xx - 55 < plot_l + 4:
                tx0 = plot_l + 4
            _center(draw, (tx0, ty0, tx0 + 110, ty1), pt, pf, gold if hot else white)
    if footer and _show(stage, 3):
        fl = _block_layout(draw, footer, W - 240, foot - 24, 36, 20, 0.72, 1, 1)
        _paint_block(draw, (100, box_y + box_h - foot + 8, W - 100, box_y + box_h - 16), fl, gold, theme["bg"])


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
    "rank_line": render_rank_line,
    "freq_bars": render_freq_bars,
    "balance_line": render_balance_line,
    "box_line": render_box_line,
    "dev_bars": render_dev_bars,
    "ratio_bars": render_ratio_bars,
    "quad_scatter": render_quad_scatter,
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

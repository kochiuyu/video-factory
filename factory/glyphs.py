#!/usr/bin/env python3
"""Font coverage and per-character face selection for slides.

PIL reports a bbox for .notdef boxes, so a glyph is accepted only when its
ink differs from a known missing character.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from paths import cjk_bold, cjk_regular, extra_cjk, latin_bold, latin_regular

ON_SCREEN_STEMS = (
    "title",
    "kicker",
    "gloss",
    "left",
    "right",
    "setup",
    "result",
    "q1",
    "q2",
    "col1",
    "col2",
    "col3",
    "step1",
    "step2",
    "step3",
    "unit",
    "caption",
    "row_player",
    "col_player",
    "row1",
    "row2",
    "note",
)

ON_SCREEN_PLAIN = ("formula", "number", "kicker", "c11", "c12", "c21", "c22")

# Only used when no face in the stack can paint the original mark.
SAFE_AFTER_SANITIZE = {
    "\u00b7": " / ",
    "\u2022": " / ",
    "\u2219": " / ",
    "\u22c5": " / ",
    "\u30fb": " / ",
    "\uff65": " / ",
    "\u2013": "-",
    "\u2014": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
}

CJK_RANGES = (
    (0x3000, 0x303F),
    (0x3040, 0x30FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE4F),
    (0xFF00, 0xFFEF),
    (0x20000, 0x2FA1F),
)


def is_cjk(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in CJK_RANGES)


def face_paths(bold: bool = False) -> list[str]:
    ordered = [
        cjk_bold() if bold else cjk_regular(),
        extra_cjk(),
        latin_bold() if bold else latin_regular(),
    ]
    out: list[str] = []
    for path in ordered:
        if path and path not in out:
            out.append(path)
    return out


@lru_cache(maxsize=32)
def _font(path: str, size: int = 48) -> ImageFont.FreeTypeFont | None:
    if not path:
        return None
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        try:
            return ImageFont.truetype(path, size, index=0)
        except OSError:
            return None


@lru_cache(maxsize=32)
def _missing_ink(path: str) -> tuple[int, ...]:
    font = _font(path)
    if font is None:
        return tuple()
    img = Image.new("L", (72, 72), 255)
    ImageDraw.Draw(img).text((8, 8), "\ufffe", font=font, fill=0)
    return tuple(img.getdata())


def _ink(path: str, ch: str) -> tuple[int, ...]:
    font = _font(path)
    if font is None:
        return tuple()
    img = Image.new("L", (72, 72), 255)
    ImageDraw.Draw(img).text((8, 8), ch, font=font, fill=0)
    return tuple(img.getdata())


@lru_cache(maxsize=8192)
def paints(path: str, ch: str) -> bool:
    if not path or not ch or ch.isspace():
        return bool(ch and ch.isspace())
    ink = _ink(path, ch)
    if not ink or all(px > 248 for px in ink):
        return False
    missing = _missing_ink(path)
    return not (missing and ink == missing)


@lru_cache(maxsize=8192)
def font_path_for_char(ch: str, bold: bool = False) -> str:
    paths = face_paths(bold)
    if not paths:
        return ""
    if is_cjk(ch):
        ranked = [p for p in paths if p != latin_regular() and p != latin_bold()] + [
            p for p in paths if p in {latin_regular(), latin_bold()}
        ]
    else:
        ranked = [p for p in paths if p in {latin_regular(), latin_bold()}] + [
            p for p in paths if p not in {latin_regular(), latin_bold()}
        ]
    for path in ranked:
        if paints(path, ch):
            return path
    return paths[0]


@lru_cache(maxsize=8192)
def char_ok(ch: str) -> bool:
    if not ch or ch.isspace():
        return True
    return any(paints(path, ch) for path in face_paths(False) + face_paths(True))


# Directional marks and embeddings. Faces may "paint" them as empty ink.
BIDI_STRIP = frozenset(
    "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)


def sanitize(text: str) -> str:
    """Drop bidi controls; keep a character if some face can paint it."""
    if not text:
        return ""
    out: list[str] = []
    for ch in text:
        if ch in BIDI_STRIP:
            continue
        if char_ok(ch):
            out.append(ch)
            continue
        out.append(SAFE_AFTER_SANITIZE.get(ch, ch))
    return "".join(out).replace("  /  ", " / ").replace("  ", " ")


def missing_chars(text: str) -> list[str]:
    seen: list[str] = []
    for ch in sanitize(text or ""):
        if ch not in seen and not char_ok(ch):
            seen.append(ch)
    return seen


def on_screen_strings(lesson: dict) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for stem in ("title_en", "title_zh", "title_zh_hk"):
        val = (lesson.get(stem) or "").strip()
        if val:
            rows.append((f"lesson.{stem}", val))
    for i, beat in enumerate(lesson.get("beats") or [], start=1):
        bid = beat.get("id") or i
        for key in ON_SCREEN_PLAIN:
            val = beat.get(key)
            if val is not None and str(val).strip():
                rows.append((f"{bid}.{key}", str(val)))
        for stem in ON_SCREEN_STEMS:
            for suffix in ("", "_en", "_zh", "_zh_cn", "_zh_hk"):
                key = f"{stem}{suffix}"
                val = beat.get(key)
                if val is not None and str(val).strip():
                    rows.append((f"{bid}.{key}", str(val)))
    return rows


def scan_lesson(lesson: dict) -> list[str]:
    errors: list[str] = []
    for loc, text in on_screen_strings(lesson):
        bad = missing_chars(text)
        if bad:
            shown = " ".join(f"{ch!r} U+{ord(ch):04X}" for ch in bad)
            errors.append(f"{loc} uses glyphs the slide fonts cannot paint: {shown}")
    return errors

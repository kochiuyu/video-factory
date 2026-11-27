#!/usr/bin/env python3
"""Opt-in animated scenes (Manim). Importing this module does not import Manim.

A lesson with no ``visual: animated`` beat never reaches this renderer.
Manim is an optional install (``requirements-manim.txt``).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from cache import digest_obj, file_fingerprint
from scene_registry import (
    label_lang,
    labels_for,
    messy_spots,
    scene_problems,
    scene_spec,
    ordinal_visits,
    schedule_marks,
    step_count,
    ordinal_columns,
    group_columns,
    track_columns,
    track_slots,
)

CREAM = "#F7F4EE"
NAVY = "#0B1F3A"
GREEN = "#1F8A4C"
GOLD = "#E0A83A"
WHITE = "#FFFFFF"
# Chinese takeaway lines break only on these marks. The mark stays with the
# left piece, so a word such as 剩下 or 一個 is never cut in half.
_CLAUSE_MARKS = set("，。！？、；：")


def takeaway_pieces(text: str) -> list[str]:
    """Pieces a takeaway line may break between.

    Chinese breaks only at punctuation. English breaks only at spaces.
    """
    raw = (text or "").strip()
    if not raw:
        return [" "]
    if any("\u4e00" <= ch <= "\u9fff" for ch in raw):
        parts: list[str] = []
        buf = ""
        for ch in raw:
            buf += ch
            if ch in _CLAUSE_MARKS:
                piece = buf.strip()
                if piece:
                    parts.append(piece)
                buf = ""
        if buf.strip():
            parts.append(buf.strip())
        return parts or [raw]
    return [word for word in raw.split() if word]


# Takeaway cards use one grid. The numbers are fractions of the frame, not
# positions picked per lesson. A row gap of 25% of the row height wins over
# the 80% visual fit, so neighbouring pictures cannot touch.
TAKEAWAY_SIDE = 0.08
TAKEAWAY_HEADING_BAND = 0.12
TAKEAWAY_VISUAL_SHARE = 0.40
TAKEAWAY_TEXT_SHARE = 0.60
TAKEAWAY_VISUAL_FIT = 0.80
TAKEAWAY_ROW_GAP = 0.25
TAKEAWAY_FONT_OF_ROW = 0.42
TAKEAWAY_MIN_PX_LANDSCAPE = 44  # at 1080p
TAKEAWAY_MIN_PX_PORTRAIT = 52  # at 1920 tall
TAKEAWAY_PORTRAIT_VISUAL = 0.45
# Gap between a landscape picture (labels included) and the text column, at 1080p.
TAKEAWAY_COLUMN_GAP_PX = 40
# Width budget for the shared body size. The longest spoken line in these
# lessons. Every language uses the size this line allows, so English is not
# a smaller face than Chinese.
TAKEAWAY_WIDTH_PROBE = "Touch each one once. One, two, three, four, five."
TAKEAWAY_HEADING_PROBE = "Find the ten first"


def takeaway_caption_px(pixel_width: int, pixel_height: int) -> int:
    """Pixels reserved under the card for a one-line caption chip.

    Landscape scales the 1080p chip. Portrait matches the pill that is actually
    drawn (size 42, a 3% bottom margin), so the rows are not stranded above a
    band the caption does not use.
    """
    from mux import CAPTION_BOTTOM_PAD, CAPTION_SIZE_MAX, CAPTION_VERTICAL_PAD

    pw = max(1, int(pixel_width))
    ph = max(1, int(pixel_height))
    if ph > pw:
        size = 42
        bottom = max(36, int(ph * 0.03))
        line_h = max(22, int(size * 1.28))
        pill = bottom + 2 * CAPTION_VERTICAL_PAD + line_h
        return pill + max(16, int(ph * 0.015))
    line_h = max(30, int(CAPTION_SIZE_MAX * 1.28))
    chip = CAPTION_BOTTOM_PAD + 2 * CAPTION_VERTICAL_PAD + line_h + 10
    return max(48, int(round(chip * ph / 1080)))


def takeaway_grid(pixel_width: int, pixel_height: int, n: int) -> dict:
    """Equal row cells for a takeaway, in Manim units and reference pixels.

    The safe box is the frame minus 8% on the left and right, minus a heading
    band, minus the caption band. The rows tile the band between those two,
    so the card fills that height. Landscape is a 40/60 column split. Portrait
    stacks the picture over the sentence inside each cell.
    """
    pw = max(1, int(pixel_width))
    ph = max(1, int(pixel_height))
    count = max(1, int(n))
    portrait = ph > pw
    fw = 8.0 * pw / float(ph)
    fh = 8.0
    side = TAKEAWAY_SIDE * fw
    left = -fw / 2 + side
    right = fw / 2 - side
    safe_w = right - left
    top = fh / 2
    heading_h = TAKEAWAY_HEADING_BAND * fh
    cap_px = takeaway_caption_px(pw, ph)
    cap_h = cap_px / float(ph) * fh
    bottom = -fh / 2 + cap_h
    rows_top = top - heading_h
    rows_h = rows_top - bottom
    cell_h = rows_h / count
    # Centred pictures with height <= 75% of the cell leave a 25% gap.
    visual_of_cell = min(TAKEAWAY_VISUAL_FIT, 1.0 - TAKEAWAY_ROW_GAP)
    if portrait:
        vis_w = safe_w
        text_w = safe_w
        vis_left = left
        text_left = left
    else:
        vis_w = TAKEAWAY_VISUAL_SHARE * safe_w
        text_w = TAKEAWAY_TEXT_SHARE * safe_w
        vis_left = left
        text_left = right - text_w
    cells = []
    for i in range(count):
        cell_top = rows_top - i * cell_h
        cell_bottom = cell_top - cell_h
        cells.append(
            {
                "left": left,
                "right": right,
                "top": cell_top,
                "bottom": cell_bottom,
                "cy": (cell_top + cell_bottom) / 2.0,
            }
        )
    unit = ph / fh
    row_px = cell_h * unit
    ref = 1920.0 if portrait else 1080.0
    floor_px = (TAKEAWAY_MIN_PX_PORTRAIT if portrait else TAKEAWAY_MIN_PX_LANDSCAPE) * (ph / ref)
    preferred_px = max(floor_px, TAKEAWAY_FONT_OF_ROW * row_px)
    return {
        "portrait": portrait,
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "heading_h": heading_h,
        "rows_top": rows_top,
        "rows_bottom": bottom,
        "cell_h": cell_h,
        "visual_of_cell": visual_of_cell,
        "vis_left": vis_left,
        "vis_w": vis_w,
        "text_left": text_left,
        "text_w": text_w,
        "cells": cells,
        "floor_px": floor_px,
        "preferred_px": preferred_px,
        "row_px": row_px,
        "pw": pw,
        "ph": ph,
        "fw": fw,
        "fh": fh,
        "unit": unit,
    }


_FONTS: tuple[str, str] | None = None


class ManimNotInstalled(RuntimeError):
    """Raised only when a lesson actually asks for an animated scene."""


def frame_size(lesson: dict | None) -> tuple[int, int]:
    """Pixel size from the lesson. 16:9 unless the lesson opts into 9:16.

    PR 23 owns phone slide layout. This only reads ``format`` when it is
    already ``9:16`` and otherwise stays on the factory's 1920×1080 frame.
    """
    fmt = ""
    if isinstance(lesson, dict):
        fmt = str(lesson.get("format") or "").strip()
    if fmt == "9:16":
        return 1080, 1920
    return 1920, 1080


def anim_cache_dir(out_dir: Path, lesson: dict | None) -> Path:
    root = Path(out_dir)
    if frame_size(lesson) == (1080, 1920):
        return root / "9x16" / "anim"
    return root / "anim"


def step_durations(holds: list[float], still_idx: list[int], n: int) -> list[float]:
    """Seconds each animation step stays up. The sum equals the beat audio.

    ``still_idx`` is the stage index ``pages_for_stages`` already assigned to
    each caption card. The last step absorbs any rounding residual, which is
    where the breath and trailing silence sit. Audio is never shortened.
    """
    n = max(1, int(n))
    totals = [0.0] * n
    for idx, hold in zip(still_idx, holds):
        try:
            i = int(idx)
        except (TypeError, ValueError):
            i = 0
        if i < 0:
            i = 0
        if i >= n:
            i = n - 1
        totals[i] += float(hold)
    target = sum(float(h) for h in holds)
    if totals:
        totals[-1] += target - sum(totals)
        if totals[-1] < 0:
            totals[-1] = 0.0
    return totals


def cache_key(
    spec: dict,
    durations: list[float],
    lang: str,
    frame: tuple[int, int],
    manim_version: str,
    marks: list | None = None,
) -> str:
    return digest_obj(
        {
            "spec": spec,
            "durations": [round(float(d), 3) for d in durations],
            "marks": marks or [],
            # Bump when a scene's motion changes but the spec does not, so a
            # cached silent clip cannot keep an old hop.
            "motion": 6,
            "lang": label_lang(lang),
            "frame": [int(frame[0]), int(frame[1])],
            "manim": str(manim_version),
        }
    )


def pages_for_animated(beat, text, dur, sub_lang, words, keep_units):
    """Caption cards for an animated beat, one stage per authored step.

    This does not use ``stage_plan``. A short line still keeps every step,
    and the holds are the same ones the caption chip uses.
    """
    from mux import pages_for_stages, stage_scripts

    n = step_count(beat)
    chunks = stage_scripts(beat, sub_lang, n)
    pages, holds, still_idx, how = pages_for_stages(
        text, dur, n, chunks=chunks, words=words, keep_units=keep_units
    )
    plan = list(range(1, n + 1))
    return pages, holds, plan, still_idx, how


def require_manim():
    try:
        import manim  # noqa: F401
    except ImportError as exc:
        raise ManimNotInstalled(
            "This lesson has an animated scene (visual: animated), and Manim is not installed. "
            "Install the optional extra with: python -m pip install -r requirements-manim.txt "
            "Lessons without an animated scene do not need Manim."
        ) from exc
    prepare_fonts()
    return manim


def prepare_fonts() -> tuple[str, str]:
    """Register the factory CJK file and pick Noto Sans CJK when it is installed.

    Returns ``(latin_family, cjk_family)`` for the last language asked. Call
    :func:`cjk_family` for a specific language.
    """
    global _FONTS
    import manimpango

    from paths import bundled_cjk, bundled_latin

    for path in (bundled_cjk(), bundled_latin()):
        if path and Path(path).is_file():
            try:
                manimpango.register_font(path)
            except Exception:
                pass
    families = set(manimpango.list_fonts())
    latin = "DejaVu Sans" if "DejaVu Sans" in families else "Sans"
    _FONTS = (latin, "Droid Sans Fallback" if "Droid Sans Fallback" in families else latin)
    return _FONTS


def cjk_family(lang: str) -> str:
    prepare_fonts()
    import manimpango

    families = set(manimpango.list_fonts())
    if label_lang(lang) == "zh_hk":
        order = ["Noto Sans CJK HK", "Noto Sans CJK TC", "Noto Sans CJK SC", "Droid Sans Fallback"]
    else:
        order = ["Noto Sans CJK SC", "Noto Sans CJK TC", "Noto Sans CJK HK", "Droid Sans Fallback"]
    for name in order:
        if name in families:
            return name
    return _FONTS[1] if _FONTS else "Droid Sans Fallback"


def latin_family() -> str:
    prepare_fonts()
    return _FONTS[0] if _FONTS else "DejaVu Sans"


def _manim_version() -> str:
    manim = require_manim()
    return str(getattr(manim, "__version__", "unknown"))


def _silent_path(cache_dir: Path, lang: str, beat_id: str, key: str) -> Path:
    return Path(cache_dir) / label_lang(lang) / f"{beat_id}-{key}.mp4"


def animated_clip_key(
    beat: dict,
    lesson: dict,
    label: str,
    holds: list[float],
    still_idx: list[int],
    pages: list[str],
    audio: Path,
    *,
    captions: bool,
    progress_bar: bool,
    frame: tuple[int, int] | None = None,
    fps: int | None = None,
    words: list | None = None,
) -> str:
    from mux import clip_fps

    frame = frame or frame_size(lesson)
    durs = step_durations(holds, still_idx, step_count(beat))
    marks = schedule_marks(beat, durs, words)
    return digest_obj(
        {
            "silent": cache_key(scene_spec(beat, label), durs, label, frame, _manim_version(), marks),
            "pages": list(pages),
            "holds": [round(float(h), 3) for h in holds],
            "audio": file_fingerprint(Path(audio)),
            "captions": bool(captions),
            "bar": bool(progress_bar),
            "fps": int(fps if fps is not None else clip_fps()),
            "frame": [int(frame[0]), int(frame[1])],
        }
    )


def render_animated_clip(
    beat: dict,
    lesson: dict,
    *,
    label_lang_code: str,
    holds: list[float],
    still_idx: list[int],
    pages: list[str],
    audio: Path,
    dest: Path,
    cache_dir: Path,
    captions: bool = True,
    progress_bar: bool = True,
    frame: tuple[int, int] | None = None,
    fps: int | None = None,
    words: list | None = None,
) -> Path:
    """Render one language's moving scene and mux that language's audio onto it.

    The silent movie is cached by spec, step durations, language, frame size,
    and Manim version. Caption cards are overlaid afterwards, using the same
    holds as the slide pipeline. The output is at least as long as the audio.
    """
    from ff import probe_duration
    from mux import clip_fps

    require_manim()
    frame = frame or frame_size(lesson)
    fps = int(fps if fps is not None else clip_fps())
    n = step_count(beat)
    durs = step_durations(holds, still_idx, n)
    marks = schedule_marks(beat, durs, words)
    spec = scene_spec(beat, label_lang_code)
    key = cache_key(spec, durs, label_lang_code, frame, _manim_version(), marks)
    silent = _silent_path(cache_dir, label_lang_code, str(beat.get("id") or "beat"), key)
    if not silent.is_file() or silent.stat().st_size < 256:
        silent.parent.mkdir(parents=True, exist_ok=True)
        print(
            f"anim: render {beat.get('id')} {label_lang(label_lang_code)} "
            f"{frame[0]}x{frame[1]} steps {', '.join(f'{d:.2f}s' for d in durs)}",
            flush=True,
        )
        _render_silent(beat, spec, durs, marks, frame, fps, silent)
        silent.with_suffix(".json").write_text(
            json.dumps(
                {"steps": durs, "frame": list(frame), "scene": spec.get("scene"), "lang": spec.get("lang")},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    else:
        print(f"anim: reuse {silent.name}", flush=True)
    audio_len = probe_duration(Path(audio))
    total = max(audio_len, sum(durs), 0.05)
    _mux(silent, Path(audio), pages if captions else [], holds if captions else [], dest, frame, fps, total, progress_bar)
    return dest


def _render_silent(beat, spec, durs, marks, frame, fps, dest: Path) -> None:
    import logging

    from manim import tempconfig

    logging.getLogger("manim").setLevel(logging.ERROR)
    w, h = frame
    # Manim's frame is 8 units tall. Width follows the pixel aspect.
    frame_h = 8.0
    frame_w = 8.0 * (w / h)
    with tempfile.TemporaryDirectory(prefix="vf-manim-") as tmp:
        with tempconfig(
            {
                "pixel_width": int(w),
                "pixel_height": int(h),
                "frame_width": frame_w,
                "frame_height": frame_h,
                "frame_rate": int(fps),
                "background_color": CREAM,
                "media_dir": tmp,
                "output_file": "scene",
                "format": "mp4",
                "write_to_movie": True,
                "save_last_frame": False,
                "disable_caching": True,
                "preview": False,
                "progress_bar": "none",
            }
        ):
            scene = _make_scene(spec, durs, marks)
            scene.render(preview=False)
            movie = Path(scene.renderer.file_writer.movie_file_path)
        if not movie.is_file():
            found = list(Path(tmp).rglob("*.mp4"))
            if not found:
                raise RuntimeError(f"Manim did not write a movie for {beat.get('id')}")
            movie = found[0]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(movie, dest)


def _make_scene(spec: dict, durs: list[float], marks: list | None = None):
    classes = _scene_types()
    scene_name = spec.get("scene")
    cls = classes[scene_name]
    scene = cls()
    scene.vf_durations = list(durs)
    scene.vf_marks = [list(row) for row in (marks or [])]
    scene.vf_labels = spec.get("labels") or {}
    scene.vf_fonts = (latin_family(), cjk_family(str(spec.get("lang") or "en")))
    raw_count = spec.get("count", None)
    scene.vf_count = int(raw_count) if raw_count is not None else 13
    scene.vf_a = int(spec.get("a") or 9)
    scene.vf_b = int(spec.get("b") or 8)
    scene.vf_mode = str(spec.get("mode") or "")
    scene.vf_n = spec.get("n")
    scene.vf_mark = spec.get("mark")
    scene.vf_direction = str(spec.get("direction") or "")
    scene.vf_low = spec.get("low")
    scene.vf_high = spec.get("high")
    scene.vf_start = spec.get("start")
    scene.vf_end = spec.get("end")
    return scene


def _scene_types() -> dict:
    cached = getattr(_scene_types, "_cache", None)
    if cached:
        return cached
    from manim import (
        DOWN,
        LEFT,
        RIGHT,
        UP,
        AnimationGroup,
        Create,
        FadeIn,
        FadeOut,
        LaggedStart,
        Circle,
        Line,
        Rectangle,
        RoundedRectangle,
        Scene,
        Star,
        SurroundingRectangle,
        Text,
        VGroup,
        config,
    )

    def _ordinal_label_height() -> float:
        """Place and count labels, in Manim units.

        48px at 1080p and 56px on a 1920-tall 9:16 frame, which is past the
        44px and 52px floors. A short 一 stays a character at that size.
        """
        pw = int(getattr(config, "pixel_width", 0) or 0) or 1920
        ph = int(getattr(config, "pixel_height", 0) or 0) or 1080
        portrait = ph > pw
        ref = 1920.0 if portrait else 1080.0
        base = 56.0 if portrait else 48.0
        unit = ph / float(config.frame_height or 8.0)
        return (base * (ph / ref)) / unit

    def _count_label(word, latin, cjk, scale, *, size=48, color=None, max_width=None):
        """One count word at the shared scale.

        Callers seat it with ``_seat_count_label``. A thin 一 must not be placed
        from its own ink height, or it leaves the line shared with 二 and 三.
        """
        glyph = styled(str(word), latin, cjk, size)
        if color is not None:
            glyph.set_color(color)
        glyph.scale(scale)
        if max_width is not None and float(glyph.width) > max_width > 0:
            glyph.scale(max_width / float(glyph.width))
        return glyph

    def _seat_count_label(glyph, x: float, centre_y: float):
        """Put the ink centre on a fixed line. The line comes from a reference glyph."""
        glyph.move_to([x, centre_y, 0])

    def font_for(text: str, latin: str, cjk: str) -> str:
        if any("\u4e00" <= ch <= "\u9fff" for ch in text or ""):
            return cjk
        return latin

    def styled(text: str, latin: str, cjk: str, size: int):
        return Text(text or " ", font=font_for(text, latin, cjk), font_size=size, color=NAVY)

    def counter(color: str, radius: float = 0.28):
        from manim import Circle

        dot = Circle(radius=radius, stroke_color=NAVY, stroke_width=2.5, fill_color=color, fill_opacity=1)
        dot.set_z_index(2)
        return dot

    def _token_row(n: int, mark: int, cell: float = 0.46, one_row: bool = False):
        """Left-to-right tokens. The marked one holds a star. Returns the row group and the token list."""
        tokens = []
        for i in range(max(1, int(n))):
            box = RoundedRectangle(
                width=cell, height=cell, corner_radius=max(0.06, cell * 0.16),
                stroke_color=NAVY, stroke_width=2.5, fill_color=WHITE, fill_opacity=1,
            )
            if i + 1 == int(mark):
                star = Star(
                    n=5,
                    outer_radius=cell * 0.36,
                    inner_radius=cell * 0.15,
                    color=GOLD,
                    fill_opacity=1,
                    stroke_color=NAVY,
                    stroke_width=1.5,
                )
                star.move_to(box)
                star.set_z_index(4)
                piece = VGroup(box, star)
            else:
                dot = counter(GREEN, cell * 0.24)
                dot.move_to(box)
                piece = VGroup(box, dot)
            piece.set_z_index(3)
            tokens.append(piece)
        cols = n if one_row or n <= 6 else (6 if n <= 12 else 5)
        if n <= cols:
            row = VGroup(*tokens)
            row.arrange(RIGHT, buff=max(0.06, cell * 0.16))
            return row, tokens
        lines = VGroup()
        for start in range(0, n, cols):
            line = VGroup(*tokens[start:start + cols])
            line.arrange(RIGHT, buff=max(0.06, cell * 0.16))
            lines.add(line)
        lines.arrange(DOWN, buff=max(0.12, cell * 0.28))
        return lines, tokens

    def _ordinal_cue(n: int, mark: int, kind: str, latin: str, cjk: str, word: str = "", total: str = "", label_frac: float = 0.85, one_row: bool = False):
        """A takeaway or hook picture of the same row. ``kind`` is hook, total, left, right, or both."""
        token_cell = 0.42
        board, tokens = _token_row(n, mark, token_cell, one_row=one_row)
        dim = "#D5D0C6"
        if kind in {"left", "right"}:
            visits = set(ordinal_visits(n, mark, kind, "ordinal"))
            for i, piece in enumerate(tokens):
                if i in visits or i + 1 == mark:
                    continue
                inner = piece[1]
                if hasattr(inner, "set_fill"):
                    inner.set_fill(dim, opacity=1)
        extras = [board]
        if kind in {"left", "right", "both"}:
            ring = SurroundingRectangle(tokens[mark - 1], color=GOLD, buff=0.05, stroke_width=5)
            ring.set_z_index(5)
            extras.append(ring)
        group = VGroup(*extras)
        if word and kind in {"left", "right"}:
            tag = styled(word, latin, cjk, 36)
            # Nearly as tall as a token, then centred on the marked one.
            target = token_cell * label_frac
            if float(tag.height) > 0 and target > 0:
                tag.scale(target / float(tag.height))
            if float(tag.width) > token_cell * 1.35:
                tag.scale(token_cell * 1.35 / float(tag.width))
            tag.next_to(tokens[mark - 1], UP, buff=0.06)
            group.add(tag)
        if total and kind in {"total", "both"}:
            num = Text(str(total), font=latin, font_size=48, color=NAVY)
            target = float(board.height) * 0.92
            if float(num.height) > target > 0:
                num.scale(target / float(num.height))
            num.next_to(board, RIGHT, buff=0.16)
            group.add(num)
        return group

    def _pair_columns(slots: int, portrait: bool) -> int:
        slots = max(1, int(slots))
        if portrait:
            return min(3, slots)
        return min(5, slots)

    def _pair_static(n: int, radius: float = 0.15, ring: bool = False):
        """Paired counters for a hook or a takeaway cue.

        A leftover counter sits on the same row, with a gold ring when ``ring`` is set.
        """
        count = max(0, int(n))
        pairs, leftover = divmod(count, 2)
        slots = pairs + leftover
        if slots <= 0:
            empty = counter("#D5D0C6", radius)
            return VGroup(empty)
        portrait = False
        cols = _pair_columns(slots, portrait)
        # A takeaway cue stays one row through nine counters (four pairs and one left).
        if slots <= 5:
            cols = slots
        dot_r = radius
        inner = max(0.04, dot_r * 0.35)
        pitch = dot_r * 4 + inner + max(0.12, dot_r * 1.15)
        row_pitch = dot_r * 2 + max(0.16, dot_r * 1.5)
        rows = (slots + cols - 1) // cols
        dots = VGroup()
        lone = None
        for slot in range(slots):
            r, c = divmod(slot, cols)
            in_row = min(cols, slots - r * cols)
            cx = (c - (in_row - 1) / 2.0) * pitch
            cy = ((rows - 1) / 2.0 - r) * row_pitch
            if slot < pairs:
                left = counter(GREEN, dot_r)
                right = counter(GREEN, dot_r)
                left.move_to([cx - (dot_r + inner / 2.0), cy, 0])
                right.move_to([cx + (dot_r + inner / 2.0), cy, 0])
                dots.add(left, right)
            else:
                lone = counter(GREEN, dot_r)
                lone.move_to([cx, cy, 0])
                dots.add(lone)
        extras = []
        if ring and lone is not None:
            halo = SurroundingRectangle(lone, color=GOLD, buff=0.04, stroke_width=4)
            halo.set_z_index(5)
            extras.append(halo)
        group = VGroup(dots, *extras)
        group.move_to(UP * 0)
        return group

    def _part_columns(count: int, portrait: bool) -> int:
        count = max(1, int(count))
        # Five beside two (7 = 5 + 2) stays on one row in both aspects.
        # A longer part, such as eight, may wrap in portrait.
        if portrait and count > 5:
            return min(4, count)
        return count

    def _zero_mat(radius: float):
        """An empty mat: a place with nothing on it, not a counter taken away."""
        from manim import RoundedRectangle

        mat = RoundedRectangle(
            width=max(0.72, float(radius) * 3.4),
            height=max(0.48, float(radius) * 2.2),
            corner_radius=0.08,
            stroke_color=NAVY,
            stroke_width=3,
            fill_color=WHITE,
            fill_opacity=1,
        )
        mat.set_z_index(1)
        return mat

    def _part_dots(left_n: int, right_n: int, radius: float = 0.16, gone: int = 0, zero_mat: bool = False):
        """Two coloured parts, or one green whole when the right part is omitted.

        ``gone`` draws that many empty circles beside the left part: counters
        that have been taken away. ``zero_mat`` draws an empty mat for a part
        of 0, so zero stays visible and is not an empty circle.
        """
        left_n = max(0, int(left_n))
        right_n = max(0, int(right_n))
        gone = max(0, int(gone))
        gap = max(0.05, radius * 0.4)
        group_gap = max(0.2, radius * 1.5)
        mat_w = max(0.72, float(radius) * 3.4)

        def width_of(count: int) -> float:
            if count <= 0:
                return 0.0
            cols = _part_columns(count, False)
            return cols * (2 * radius) + (cols - 1) * gap

        def place(count: int, cx: float, color: str):
            made = []
            if count <= 0:
                return made
            cols = _part_columns(count, False)
            row_w = width_of(count)
            for i in range(count):
                r, c = divmod(i, cols)
                in_row = min(cols, count - r * cols)
                this_w = in_row * (2 * radius) + (in_row - 1) * gap
                left = cx - this_w / 2 + radius
                y = -r * (2 * radius + gap)
                dot = counter(color, radius)
                dot.move_to([left + c * (2 * radius + gap), y, 0])
                made.append(dot)
            return made

        show_left_mat = bool(zero_mat) and left_n == 0 and right_n > 0 and not gone
        show_right_mat = bool(zero_mat) and right_n == 0 and left_n > 0 and not gone
        right_count = gone if gone else right_n
        left_present = left_n > 0 or show_left_mat
        right_present = right_count > 0 or show_right_mat
        lw = width_of(left_n) if left_n else (mat_w if show_left_mat else 0.0)
        rw = width_of(right_count) if right_count else (mat_w if show_right_mat else 0.0)
        total = lw + (group_gap if left_present and right_present else 0.0) + rw
        lcx = (-total / 2 + lw / 2) if left_present else 0.0
        rcx = (total / 2 - rw / 2) if right_present else 0.0
        if left_present and not right_present:
            lcx = 0.0
        if right_present and not left_present:
            rcx = 0.0
        mats = []
        if show_left_mat:
            mat = _zero_mat(radius)
            mat.move_to([lcx, 0, 0])
            mats.append(mat)
        if show_right_mat:
            mat = _zero_mat(radius)
            mat.move_to([rcx, 0, 0])
            mats.append(mat)
        if gone:
            empties = []
            cols = _part_columns(gone, False)
            row_w = width_of(gone)
            for i in range(gone):
                r, c = divmod(i, cols)
                in_row = min(cols, gone - r * cols)
                this_w = in_row * (2 * radius) + (in_row - 1) * gap
                left = rcx - this_w / 2 + radius
                y = -r * (2 * radius + gap)
                ring = Circle(
                    radius=radius,
                    stroke_color=NAVY,
                    stroke_width=2.5,
                    fill_color=CREAM,
                    fill_opacity=1,
                )
                ring.move_to([left + c * (2 * radius + gap), y, 0])
                empties.append(ring)
            dots = mats + place(left_n, lcx, GREEN) + empties
        else:
            dots = mats + place(left_n, lcx, GREEN) + place(right_n, rcx, GOLD)
        group = VGroup(*dots) if dots else VGroup(counter("#D5D0C6", radius))
        group.move_to(UP * 0)
        return group

    def ten_cells():
        cells = VGroup()
        for _ in range(10):
            cell = RoundedRectangle(
                width=0.78,
                height=0.78,
                corner_radius=0.08,
                stroke_color=NAVY,
                stroke_width=3,
                fill_color=WHITE,
                fill_opacity=1,
            )
            cells.add(cell)
        cells.arrange_in_grid(rows=2, cols=5, buff=0.1)
        return cells

    def equation(tokens: list[str], latin: str, size: int = 56):
        """Digits and operators on one line. A hyphen token is drawn as a minus.

        U+2212 is the same width as ``=`` and ``+`` in DejaVu, and the same
        stroke weight as one bar of ``=``. The short hyphen is not.
        """
        minus = {"-", "−", "–"}
        glyphs = []
        for tok in tokens:
            shown = "−" if tok in minus else tok
            glyphs.append(Text(shown, font=latin, font_size=size, color=NAVY))
        equals = next((glyph for tok, glyph in zip(tokens, glyphs) if tok == "="), None)
        plus = next((glyph for tok, glyph in zip(tokens, glyphs) if tok == "+"), None)
        target = equals or plus
        if target is not None and float(target.width) > 0:
            for tok, glyph in zip(tokens, glyphs):
                if tok in minus and float(glyph.width) > 0:
                    glyph.scale_to_fit_width(float(target.width))
        parts = VGroup(*glyphs)
        parts.arrange(RIGHT, buff=0.22)
        return parts

    def _safe_limits():
        """Caption-safe box in Manim units, matching the slide chip.

        The bottom is the top of the largest caption the mux can draw, plus a
        small gap. The picture is centred in the frame and only lifted if it
        would cross that line.
        """
        from mux import caption_safe_top

        fh = float(config.frame_height)
        fw = float(config.frame_width)
        ph = int(getattr(config, "pixel_height", 0) or 0) or 1080
        safe_px = caption_safe_top(ph)
        bottom = fh / 2 - (safe_px / float(ph)) * fh + 0.12
        top = fh / 2 - 0.28
        side = 0.4
        return -fw / 2 + side, fw / 2 - side, bottom, top

    def _span_x(*mobs) -> float:
        left = min(float(m.get_left()[0]) for m in mobs)
        right = max(float(m.get_right()[0]) for m in mobs)
        return (left + right) / 2

    def settle(group):
        left_lim, right_lim, bot_lim, top_lim = _safe_limits()
        max_w = right_lim - left_lim
        max_h = top_lim - bot_lim
        if group.width > max_w and group.width > 0:
            group.scale(max_w / group.width)
        if group.height > max_h and group.height > 0:
            group.scale(max_h / group.height)
        # Same centre as a slide title: the middle of the frame, not the
        # upper band. Lift only when the caption chip would cover the bottom.
        group.move_to(UP * 0)
        if group.get_bottom()[1] < bot_lim:
            group.shift(UP * (bot_lim - float(group.get_bottom()[1])))
        if group.get_top()[1] > top_lim:
            group.shift(DOWN * (float(group.get_top()[1]) - top_lim))
        if group.get_bottom()[1] < bot_lim and group.height > 0:
            group.scale(0.92)
            group.shift(UP * (bot_lim - float(group.get_bottom()[1])))

    class _Board(Scene):
        def spend(self, index: int, *anims) -> None:
            total = 0.0
            durs = getattr(self, "vf_durations", []) or []
            if 0 <= index < len(durs):
                total = float(durs[index])
            fps = max(float(config.frame_rate or 15), 1.0)
            frame = 1.0 / fps
            if total <= frame / 2:
                return
            if not anims:
                self.wait(total)
                return
            move = min(total * 0.72, total)
            if total - move < frame:
                move = total
            move = max(move, frame)
            if move > total:
                move = total
            self.play(*anims, run_time=move)
            rest = total - move
            if rest > frame / 2:
                self.wait(rest)

        def spend_each(self, index: int, moves: list) -> None:
            """Play motions one by one inside this step. The step still lasts its full hold."""
            total = 0.0
            durs = getattr(self, "vf_durations", []) or []
            if 0 <= index < len(durs):
                total = float(durs[index])
            fps = max(float(config.frame_rate or 15), 1.0)
            frame = 1.0 / fps
            if total <= frame / 2 or not moves:
                self.spend(index)
                return
            move = min(total * 0.82, total)
            each = move / len(moves)
            if each < frame:
                # A function is called now, the same way the one-by-one path does.
                built = [
                    item() if callable(item) and not hasattr(item, "build") else item
                    for item in moves
                ]
                self.spend(index, LaggedStart(*built, lag_ratio=0.85))
                return
            for item in moves:
                built = item() if callable(item) and not hasattr(item, "build") else item
                self.play(built, run_time=each)
            rest = total - each * len(moves)
            if rest > frame / 2:
                self.wait(rest)

        def marks_for(self, index: int) -> list:
            rows = getattr(self, "vf_marks", None) or []
            if 0 <= index < len(rows):
                return list(rows[index])
            return []

        def spend_marked(self, index: int, anims: list, marks: list, intro=None) -> None:
            """Land each motion as its count word is spoken. The step still lasts its full hold."""
            total = 0.0
            durs = getattr(self, "vf_durations", []) or []
            if 0 <= index < len(durs):
                total = float(durs[index])
            fps = max(float(config.frame_rate or 15), 1.0)
            frame = 1.0 / fps
            if not marks or len(marks) != len(anims) or total <= frame / 2:
                # A function has to run at play time. Building every .animate
                # first makes one mobject share a single target.
                if any(callable(item) and not hasattr(item, "build") for item in anims):
                    sequence = ([intro] if intro is not None else []) + list(anims)
                    self.spend_each(index, sequence)
                    return
                if intro is not None and anims:
                    self.spend(index, intro, LaggedStart(*anims, lag_ratio=0.12))
                else:
                    self.spend_each(index, anims)
                return
            t = 0.0
            if intro is not None:
                intro_t = min(0.45, max(frame, total * 0.18), total)
                self.play(intro, run_time=intro_t)
                t = intro_t
            for i, anim in enumerate(anims):
                land = min(total, max(0.0, float(marks[i])))
                nxt = float(marks[i + 1]) if i + 1 < len(marks) else total
                gap = max(frame, nxt - land)
                hop = min(0.34, max(frame, gap * 0.5))
                start = min(total, max(t, land - hop))
                if start - t > frame / 2:
                    self.wait(start - t)
                    t = start
                run = min(hop, max(0.0, total - t))
                if run <= frame / 2:
                    break
                # A function is called now, so .animate reads the mobject where it
                # actually is. Building several .animate hops up front makes them
                # share one target, and the marker jumps to the last number.
                built = anim() if callable(anim) and not hasattr(anim, "build") else anim
                self.play(built, run_time=run)
                t += run
            if total - t > frame / 2:
                self.wait(total - t)

    class TenAndOnes(_Board):
        def construct(self):
            count = max(10, min(20, int(self.vf_count)))
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            frames_n = 2 if count >= 20 else 1
            ones_n = 0 if count >= 20 else count - 10
            # Two full frames stay side by side in 16:9. In 9:16 they stack so
            # both tens stay readable. One frame is unchanged.
            portrait = config.frame_width < config.frame_height
            frames = VGroup(*[ten_cells() for _ in range(frames_n)])
            if frames_n == 2 and portrait:
                frames.arrange(DOWN, buff=0.4)
            else:
                frames.arrange(RIGHT, buff=0.4)
            cells = [cell for frame in frames for cell in frame]
            dots = VGroup(*[counter(GREEN) for _ in range(count)])
            for i, dot in enumerate(dots):
                if i < len(cells):
                    dot.move_to(cells[i].get_center())
            extras = [dots[i] for i in range(len(cells), len(dots))]
            gap = 0.72
            title = styled(labels.get("title") or "", latin, cjk, 40)
            ten_label = styled(labels.get("one_ten") or "", latin, cjk, 34)
            ones_label = styled(labels.get("ones") or " ", latin, cjk, 34) if ones_n else None
            if extras and portrait:
                ten_label.next_to(frames, DOWN, buff=0.16)
                span = (len(extras) - 1) * gap
                y = float(ten_label.get_bottom()[1]) - 0.36 - 0.28
                x0 = float(frames.get_center()[0])
                for i, dot in enumerate(extras):
                    dot.move_to([x0 + i * gap - span / 2, y, 0])
                if ones_label is not None:
                    ones_label.next_to(VGroup(*extras), DOWN, buff=0.2)
            elif extras:
                origin = frames.get_right() + RIGHT * 0.75
                span = (len(extras) - 1) * gap
                for i, dot in enumerate(extras):
                    dot.move_to(origin + DOWN * (i * gap - span / 2))
                ten_label.next_to(frames, DOWN, buff=0.22)
                if ones_label is not None:
                    lowest = min(extras, key=lambda dot: float(dot.get_center()[1]))
                    ones_label.next_to(lowest, DOWN, buff=0.36)
            else:
                ten_label.next_to(frames, DOWN, buff=0.22)
            eq = equation(list(labels.get("equation") or [str(count)]), latin)
            anchor = VGroup(ten_label, ones_label) if ones_label is not None else ten_label
            eq.next_to(anchor, DOWN, buff=0.32)
            span = [frames, *extras] if extras else [frames]
            title.move_to([_span_x(*span), float(frames.get_top()[1]) + 0.35 + float(title.height) / 2, 0])
            from manim import Circle

            # Invisible discs the size of a counter, so the starting group
            # cannot overlap and settle() keeps every disc inside the frame.
            anchors = VGroup(*[
                Circle(radius=0.28, stroke_opacity=0, fill_opacity=0) for _ in range(count)
            ])
            cols = 4 if count >= 8 else max(1, count)
            anchors.arrange_in_grid(rows=(count + cols - 1) // cols, cols=cols, buff=0.2)
            if portrait:
                anchors.next_to(frames, UP, buff=0.32)
                title.next_to(anchors, UP, buff=0.22)
            else:
                anchors.next_to(frames, LEFT, buff=0.4)
                span = [anchors, frames, *extras] if extras else [anchors, frames]
                top = max(float(m.get_top()[1]) for m in span)
                title.move_to([_span_x(*span), top + 0.28 + float(title.height) / 2, 0])
            board = VGroup(title, frames, dots, anchors, ten_label, eq)
            if ones_label is not None:
                board.add(ones_label)
            settle(board)
            targets = [dot.get_center().copy() for dot in dots]
            for dot, pin in zip(dots, anchors):
                dot.move_to(pin.get_center())
            self.add(frames, dots)
            moves = [dot.animate.move_to(target) for dot, target in zip(dots, targets)]
            counted = self.marks_for(0)
            if counted and len(counted) == len(moves):
                self.spend_marked(0, moves, counted, intro=FadeIn(title))
            else:
                self.spend(0, FadeIn(title), LaggedStart(*moves, lag_ratio=0.08))
            ring = SurroundingRectangle(frames, color=GOLD, buff=0.12, stroke_width=6)
            step2 = [FadeIn(ten_label), Create(ring)]
            if ones_label is not None:
                step2.append(FadeIn(ones_label))
            self.spend(1, *step2)
            self.spend(2, LaggedStart(*[FadeIn(piece) for piece in eq], lag_ratio=0.18))

    class OneTen(_Board):
        """Ten loose counters gather into one frame, then ones sit beside it."""

        def construct(self):
            count = max(10, min(20, int(self.vf_count)))
            ones_n = 0 if count >= 20 else count - 10
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            cells = ten_cells()
            ten_dots = VGroup(*[counter(GREEN) for _ in range(10)])
            extra_dots = VGroup(*[counter(GREEN) for _ in range(ones_n)])
            for dot, cell in zip(ten_dots, cells):
                dot.move_to(cell.get_center())
            portrait = config.frame_width < config.frame_height
            gap = 0.72
            extras = list(extra_dots)
            title = styled(labels.get("title") or "", latin, cjk, 40)
            ten_label = styled(labels.get("one_ten") or "", latin, cjk, 34)
            ones_label = styled(labels.get("ones") or " ", latin, cjk, 34) if ones_n else None
            if extras and portrait:
                # The label sits between the frame and the ones, with a gap
                # taller than the counters, so it cannot cover them.
                ten_label.next_to(cells, DOWN, buff=0.16)
                span = (len(extras) - 1) * gap
                y = float(ten_label.get_bottom()[1]) - 0.36 - 0.28
                x0 = float(cells.get_center()[0])
                for i, dot in enumerate(extras):
                    dot.move_to([x0 + i * gap - span / 2, y, 0])
                if ones_label is not None:
                    ones_label.next_to(VGroup(*extras), DOWN, buff=0.2)
            elif extras:
                origin = cells.get_right() + RIGHT * 0.75
                span = (len(extras) - 1) * gap
                for i, dot in enumerate(extras):
                    dot.move_to(origin + DOWN * (i * gap - span / 2))
                ten_label.next_to(cells, DOWN, buff=0.22)
                if ones_label is not None:
                    ones_label.next_to(min(extras, key=lambda dot: float(dot.get_center()[1])), DOWN, buff=0.36)
            else:
                ten_label.next_to(cells, DOWN, buff=0.22)
            from manim import Circle

            anchors = VGroup(*[
                Circle(radius=0.28, stroke_opacity=0, fill_opacity=0) for _ in range(10)
            ])
            anchors.arrange_in_grid(rows=5, cols=2, buff=0.16)
            if portrait:
                anchors.next_to(cells, UP, buff=0.28)
                title.next_to(anchors, UP, buff=0.2)
            else:
                anchors.next_to(cells, LEFT, buff=0.36)
                span_mobs = [anchors, cells, *extras] if extras else [anchors, cells]
                title.move_to([_span_x(*span_mobs), float(cells.get_top()[1]) + 0.35 + float(title.height) / 2, 0])
            board = VGroup(title, cells, ten_dots, anchors, ten_label)
            if ones_n:
                board.add(extra_dots)
            if ones_label is not None:
                board.add(ones_label)
            settle(board)
            ten_targets = [dot.get_center().copy() for dot in ten_dots]
            extra_targets = [dot.get_center().copy() for dot in extra_dots]
            for dot, pin in zip(ten_dots, anchors):
                dot.move_to(pin.get_center())
            self.spend(
                0,
                FadeIn(title),
                FadeIn(cells),
                LaggedStart(*[FadeIn(dot) for dot in ten_dots], lag_ratio=0.05),
            )
            moves = [dot.animate.move_to(target) for dot, target in zip(ten_dots, ten_targets)]
            ring = SurroundingRectangle(cells, color=GOLD, buff=0.12, stroke_width=6)
            self.spend(1, LaggedStart(*moves, lag_ratio=0.08), FadeIn(ten_label), Create(ring))
            if ones_n and ones_label is not None:
                for dot, target in zip(extra_dots, extra_targets):
                    dot.move_to(target)
                self.spend(2, LaggedStart(*[FadeIn(dot) for dot in extra_dots], lag_ratio=0.12))
                self.spend(3, FadeIn(ones_label))
            else:
                self.spend(2)
                self.spend(3)

    class MakeTen(_Board):
        def construct(self):
            a = max(1, min(9, int(self.vf_a)))
            b = max(10 - a, int(self.vf_b))
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            move_n = 10 - a
            cells = ten_cells()
            greens = VGroup(*[counter(GREEN) for _ in range(a)])
            golds = VGroup(*[counter(GOLD) for _ in range(b)])
            for dot, cell in zip(greens, cells):
                dot.move_to(cell.get_center())
            empty_centers = [cells[a + i].get_center().copy() for i in range(move_n)]
            portrait = config.frame_width < config.frame_height
            cols = 4 if b > 4 else b
            rows = max(1, (b + cols - 1) // cols)
            golds.arrange_in_grid(rows=rows, cols=cols, buff=0.12)
            if portrait:
                golds.next_to(cells, DOWN, buff=0.45)
            else:
                golds.next_to(cells, RIGHT, buff=0.5)
            title = styled(labels.get("title") or "", latin, cjk, 40)
            title.move_to([
                _span_x(cells, golds),
                float(cells.get_top()[1]) + 0.35 + float(title.height) / 2,
                0,
            ])
            eq1 = equation(list(labels.get("equation1") or []), latin)
            eq2 = equation(list(labels.get("equation2") or []), latin)
            eq1.next_to(VGroup(cells, golds), DOWN, buff=0.4)
            eq2.move_to(eq1)
            board = VGroup(title, cells, greens, golds, eq1)
            settle(board)
            eq2.move_to(eq1)
            green_targets = [dot.get_center().copy() for dot in greens]
            gold_targets = [dot.get_center().copy() for dot in golds]
            empty_centers = [cells[a + i].get_center().copy() for i in range(move_n)]
            for i, dot in enumerate(greens):
                dot.move_to(cells.get_left() + LEFT * 1.15 + DOWN * ((i % 5) - 2) * 0.34)
            for i, dot in enumerate(golds):
                dot.shift(RIGHT * (config.frame_width * 0.35) + UP * 0.4)
            self.add(cells, greens, golds)
            moves = [dot.animate.move_to(t) for dot, t in zip(greens, green_targets)]
            moves += [dot.animate.move_to(t) for dot, t in zip(golds, gold_targets)]
            self.spend(0, FadeIn(title), LaggedStart(*moves, lag_ratio=0.06))
            into = [golds[i].animate.move_to(empty_centers[i]) for i in range(move_n)]
            ring = SurroundingRectangle(cells, color=GOLD, buff=0.1, stroke_width=6)
            self.spend(1, LaggedStart(*into, lag_ratio=0.15), FadeIn(eq1), Create(ring))
            self.spend(2, FadeOut(eq1), FadeIn(eq2))

    class CountObjects(_Board):
        """Light each counter once, move them, or show an empty tray as 0."""

        def construct(self):
            import math

            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            mode = str(self.vf_mode or labels.get("mode") or "count")
            count = max(0, int(self.vf_count))
            title = styled(labels.get("title") or "", latin, cjk, 40)
            question = styled(labels.get("question") or "", latin, cjk, 36)
            note = styled(labels.get("note") or "", latin, cjk, 34)
            answer = Text(str(labels.get("answer") or "0"), font=latin, font_size=78, color=NAVY)
            if mode == "rearrange":
                footer = VGroup(answer, note).arrange(RIGHT, buff=0.28)
            else:
                footer = VGroup(question, answer, note).arrange(RIGHT, buff=0.28)

            if mode == "zero" or count == 0:
                tray = RoundedRectangle(
                    width=5.4,
                    height=2.3,
                    corner_radius=0.18,
                    stroke_color=NAVY,
                    stroke_width=4,
                    fill_color=WHITE,
                    fill_opacity=1,
                )
                title.next_to(tray, UP, buff=0.32)
                footer.next_to(tray, DOWN, buff=0.32)
                settle(VGroup(title, tray, footer))
                self.spend(0, FadeIn(title), FadeIn(tray))
                self.spend(1, FadeIn(question))
                self.spend(2, FadeIn(answer), FadeIn(note))
                return

            radius = 0.34 if count >= 10 else 0.30
            dx = dy = radius * 2 + 0.24
            cols = min(5, count)
            rows_n = math.ceil(count / cols)
            starts = []
            for i in range(count):
                row, col = divmod(i, cols)
                row_n = cols if row < rows_n - 1 else count - row * cols
                starts.append((
                    (col - (row_n - 1) / 2) * dx,
                    ((rows_n - 1) / 2 - row) * dy,
                ))
            cx = sum(p[0] for p in starts) / count
            cy = sum(p[1] for p in starts) / count
            ring = min(dx * max(cols - 1, 1) / 2, 0.48 + 0.16 * count)
            ends = []
            for i in range(count):
                ang = math.pi / 2 - i * 2 * math.pi / count
                ends.append((cx + ring * math.cos(ang), cy + ring * math.sin(ang)))
            xs = [p[0] for p in starts] + ([p[0] for p in ends] if mode == "rearrange" else [])
            ys = [p[1] for p in starts] + ([p[1] for p in ends] if mode == "rearrange" else [])
            tray = RoundedRectangle(
                width=max(xs) - min(xs) + radius * 2 + 0.9,
                height=max(ys) - min(ys) + radius * 2 + 0.85,
                corner_radius=0.18,
                stroke_color=NAVY,
                stroke_width=4,
                fill_color=WHITE,
                fill_opacity=1,
            )
            tray.move_to([(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0])
            dim = "#D5D0C6"
            fill = GREEN if mode == "rearrange" else dim
            from manim import Dot

            pieces = []
            numbers = []
            anchors_end = VGroup()
            for i in range(count):
                dot = counter(fill, radius)
                num = _count_label(
                    str(i + 1), latin, cjk, 1.0,
                    size=28, color=WHITE, max_width=radius * 1.35,
                )
                num.set_z_index(4)
                if mode != "rearrange":
                    num.set_opacity(0)
                dot.move_to([starts[i][0], starts[i][1], 0])
                _seat_count_label(num, starts[i][0], starts[i][1])
                pieces.append(dot)
                numbers.append(num)
                pin = Dot([ends[i][0], ends[i][1], 0], radius=0.01, fill_opacity=0, stroke_opacity=0)
                anchors_end.add(pin)
            group = VGroup(tray, *pieces, *numbers, anchors_end)
            title.next_to(group, UP, buff=0.28)
            footer.next_to(group, DOWN, buff=0.28)
            settle(VGroup(title, group, footer))
            targets = [pin.get_center().copy() for pin in anchors_end]
            if mode == "rearrange":
                self.spend(0, FadeIn(title), FadeIn(tray), FadeIn(VGroup(*pieces)), FadeIn(VGroup(*numbers)))
            else:
                for num in numbers:
                    self.add(num)
                self.spend(0, FadeIn(title), FadeIn(tray), FadeIn(VGroup(*pieces)))
            if mode == "rearrange":
                moves = []
                for dot, num, target in zip(pieces, numbers, targets):
                    moves.append(AnimationGroup(dot.animate.move_to(target), num.animate.move_to(target)))
                self.spend_each(1, moves)
                self.spend(2, FadeIn(answer), FadeIn(note))
            else:
                lights = []
                for dot, num in zip(pieces, numbers):
                    lights.append(AnimationGroup(
                        dot.animate.set_fill(GREEN, opacity=1),
                        num.animate.set_opacity(1),
                    ))
                counted = self.marks_for(1)
                if counted and len(counted) == len(lights):
                    self.spend_marked(1, lights, counted)
                else:
                    self.spend_each(1, lights)
                self.spend(2, FadeIn(question), FadeIn(answer), FadeIn(note))

    class NumberTrack(_Board):
        """A 0–20 track (range is configurable) and a marker that hops on or back."""

        def construct(self):
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            low = int(self.vf_low if self.vf_low is not None else 0)
            high = int(self.vf_high if self.vf_high is not None else 20)
            start = int(self.vf_start if self.vf_start is not None else low)
            end = int(self.vf_end if self.vf_end is not None else high)
            low, high = min(low, high), max(low, high)
            start = min(high, max(low, start))
            end = min(high, max(low, end))
            values = list(range(low, high + 1))
            crosses = min(start, end) < 10 < max(start, end)
            # One row whenever the cells stay readable, so a hop across 10 is
            # a sideways move. A narrow frame wraps. Portrait rows read left
            # to right, and the next row starts at the left. Landscape keeps
            # the snake; a 16:9 track is one row, so it never turns.
            pw = int(getattr(config, "pixel_width", 0) or 1920)
            ph = int(getattr(config, "pixel_height", 0) or 1080)
            cols = track_columns(len(values), pw, ph)
            gap = 0.08
            usable = float(config.frame_width) - 1.15
            cell = min(0.82, max(0.34, (usable - gap * (cols - 1)) / cols))
            row_gap = cell * 0.34
            portrait = ph > pw
            if portrait:
                slots = track_slots(values, cols, left_to_right=True)
            else:
                slots = {}
                row_i, col_i, direction = 0, 0, 1
                for i, value in enumerate(values):
                    slots[value] = (row_i, col_i)
                    if i == len(values) - 1:
                        break
                    nxt = col_i + direction
                    if nxt < 0 or nxt >= cols:
                        row_i += 1
                        direction *= -1
                    else:
                        col_i = nxt
            cells = {}
            numerals = VGroup()
            grid = VGroup()
            for value, (r, c) in slots.items():
                x = (c - (cols - 1) / 2) * (cell + gap)
                y = -r * (cell + row_gap)
                box = RoundedRectangle(
                    width=cell,
                    height=cell * 0.86,
                    corner_radius=0.08,
                    stroke_color=NAVY,
                    stroke_width=4 if value == 10 else 2.5,
                    fill_color=WHITE,
                    fill_opacity=1,
                )
                box.move_to([x, y, 0])
                num = Text(str(value), font=latin, font_size=36, color=NAVY)
                if num.height > cell * 0.52:
                    num.scale(cell * 0.52 / num.height)
                if num.width > cell * 0.78:
                    num.scale(cell * 0.78 / num.width)
                num.move_to(box)
                num.set_z_index(4)
                cells[value] = box
                numerals.add(num)
                grid.add(box)
            shift = grid.get_center()
            grid.shift(-shift)
            numerals.shift(-shift)
            marker = RoundedRectangle(
                width=cell * 0.92,
                height=cell * 0.76,
                corner_radius=0.1,
                stroke_color=GOLD,
                stroke_width=7,
                fill_color=GOLD,
                fill_opacity=0.42,
            )
            marker.set_z_index(1)
            marker.move_to(cells[start])
            title = styled(labels.get("title") or "", latin, cjk, 40)
            start_line = styled(labels.get("start_at") or "", latin, cjk, 32)
            step = styled(labels.get("step") or "", latin, cjk, 34)
            answer = Text(str(labels.get("answer") or end), font=latin, font_size=72, color=NAVY)
            cross_text = labels.get("cross") or ""
            cross = styled(cross_text, latin, cjk, 34) if cross_text else None
            # The result stands alone. The short labels stack under it, one
            # line each, at the size they already use, so they do not sit
            # beside the number.
            notes = [step]
            if cross is not None and crosses:
                notes.append(cross)
            note_stack = VGroup(*notes).arrange(DOWN, buff=0.08)
            foot = VGroup(answer, note_stack).arrange(DOWN, buff=0.14)
            title.next_to(grid, UP, buff=0.28)
            start_line.next_to(grid, DOWN, buff=0.24)
            foot.next_to(start_line, DOWN, buff=0.2)
            board = VGroup(title, grid, numerals, marker, start_line, foot)
            settle(board)
            step_by = 1 if end >= start else -1
            visits = list(range(start, end + step_by, step_by)) if start != end else [start]
            counted = self.marks_for(1)
            if counted and len(counted) == len(visits):
                marker.set_opacity(0)
                marker.move_to(cells[start].get_center())
                # Each hop is built at the moment it plays. See spend_marked.
                hops = [lambda: marker.animate.set_opacity(1)]
                for n in visits[1:]:
                    if n not in cells:
                        continue
                    dest = cells[n].get_center().copy()
                    hops.append(lambda dest=dest: marker.animate.move_to(dest))
                self.spend(0, FadeIn(title), FadeIn(grid), FadeIn(numerals), FadeIn(start_line))
                self.spend_marked(1, hops, counted)
            else:
                hops = []
                for n in visits[1:]:
                    if n not in cells:
                        continue
                    dest = cells[n].get_center().copy()
                    hops.append(lambda dest=dest: marker.animate.move_to(dest))
                self.spend(0, FadeIn(title), FadeIn(grid), FadeIn(numerals), FadeIn(marker), FadeIn(start_line))
                self.spend_each(1, hops)
            shown = [FadeIn(answer), FadeIn(step)]
            if cross is not None and crosses:
                shown.append(FadeIn(cross))
            self.spend(2, *shown)

    class OrdinalRow(_Board):
        """Tokens in a row. Place labels, or a how-many count, land on the spoken words."""

        def construct(self):
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            n = int(self.vf_n if self.vf_n is not None else labels.get("n") or 6)
            mark = int(self.vf_mark if self.vf_mark is not None else labels.get("mark") or 1)
            direction = str(self.vf_direction or labels.get("direction") or "left")
            mode = str(self.vf_mode or labels.get("mode") or "ordinal")
            n = max(1, min(20, n))
            mark = max(1, min(n, mark))
            visits = ordinal_visits(n, mark, direction, mode)
            words = [str(item) for item in (labels.get("ordinals") or [])]
            if len(words) < len(visits):
                words = words + [str(i + 1) for i in range(len(words), len(visits))]
            words = words[: len(visits)]
            pw = int(getattr(config, "pixel_width", 0) or 1920)
            ph = int(getattr(config, "pixel_height", 0) or 1080)
            # 0.46 keeps six tokens on one row in 9:16. A higher floor would snake them.
            cols = ordinal_columns(n, pw, ph, one_row=bool(labels.get("one_row")))
            label_h = _ordinal_label_height()
            # Scale from a full character, not each glyph's ink. 一 is a flat stroke;
            # matching its ink height turns it into a bar and shrinks the row.
            cjk_labels = any("\u4e00" <= ch <= "\u9fff" for word in words for ch in word)
            ref = styled("三" if cjk_labels else "8", latin, cjk, 48)
            label_scale = (label_h / float(ref.height)) if float(ref.height) else 1.0
            widest = label_h
            for word in words:
                probe = styled(word, latin, cjk, 48)
                widest = max(widest, float(probe.width) * label_scale)
            left_lim, right_lim, bot_lim, top_lim = _safe_limits()
            portrait = ph > pw
            if portrait:
                # Labels set the width. A row of six uses the safe width, and
                # the centre spacing is at least the label plus 16px. A uniform
                # shrink holds the 44px floor.
                unit = ph / float(config.frame_height or 8.0)
                min_gap = 16.0 / unit
                floor_h = (44.0 * (ph / 1920.0)) / unit
                max_w = (right_lim - left_lim) * 0.98
                fit_w = (max_w - max(cols - 1, 0) * min_gap) / max(cols, 1)
                if widest > fit_w > 0:
                    shrink = fit_w / widest
                    if label_h > 0 and label_h * shrink < floor_h:
                        shrink = floor_h / label_h
                    label_scale *= shrink
                    widest *= shrink
                if cols > 1:
                    fill_pitch = (max_w - widest) / (cols - 1)
                else:
                    fill_pitch = widest + min_gap
                pitch = max(fill_pitch, widest + min_gap)
                if (cols - 1) * pitch + widest > max_w and cols > 1:
                    slack = (max_w - cols * widest) / (cols - 1)
                    pitch = widest + max(slack, 12.0 / unit)
                box = min(pitch * 0.62, max(0.12, pitch - min_gap))
                cell = max(0.2, box / 0.92)
                gap = max(0.02, pitch - cell)
            else:
                max_w = (right_lim - left_lim) * 0.96
                # About twice the old 0.78 cap. 9:16 clamps this to the safe width.
                gap = max(0.14, widest * 0.1)
                cell = min(1.56, (max_w - gap * (max(cols, 1) - 1)) / max(cols, 1))
                if cell + gap < widest * 1.06:
                    gap = max(0.1, widest * 1.06 - cell)
                    cell = min(cell, (max_w - gap * (max(cols, 1) - 1)) / max(cols, 1))
                cell = max(0.46, cell)
            # The next row's label has to clear the token above it.
            row_gap = label_h + 0.28
            slots: dict[int, tuple[int, int]] = {}
            row_i, col_i, step_dir = 0, 0, 1
            for i in range(n):
                slots[i] = (row_i, col_i)
                if i == n - 1:
                    break
                nxt = col_i + step_dir
                if nxt < 0 or nxt >= cols:
                    row_i += 1
                    step_dir *= -1
                else:
                    col_i = nxt
            tokens = VGroup()
            grid = VGroup()
            centers = {}
            for i, (r, c) in slots.items():
                x = (c - (cols - 1) / 2) * (cell + gap)
                y = -r * (cell + row_gap)
                box = RoundedRectangle(
                    width=cell * 0.92,
                    height=cell * 0.92,
                    corner_radius=cell * 0.14,
                    stroke_color=NAVY,
                    stroke_width=3,
                    fill_color=WHITE,
                    fill_opacity=1,
                )
                box.move_to([x, y, 0])
                if i + 1 == mark:
                    star = Star(
                        n=5,
                        outer_radius=cell * 0.32,
                        inner_radius=cell * 0.13,
                        color=GOLD,
                        fill_opacity=1,
                        stroke_color=NAVY,
                        stroke_width=1.5,
                    )
                    star.move_to(box)
                    star.set_z_index(4)
                    piece = VGroup(box, star)
                else:
                    dot = counter(GREEN, cell * 0.22)
                    dot.move_to(box)
                    piece = VGroup(box, dot)
                piece.set_z_index(3)
                tokens.add(piece)
                grid.add(box)
                centers[i] = box.get_center().copy()
            shift = grid.get_center()
            tokens.shift(-shift)
            for i in centers:
                centers[i] = centers[i] - shift
            tags = VGroup()
            pitch = cell + gap
            box_h = float(ref.height) * label_scale
            for word, index in zip(words, visits):
                # Landscape only. Portrait already reserved 16px between labels.
                cap = pitch * 0.96 if ph <= pw else None
                tag = _count_label(word, latin, cjk, label_scale, max_width=cap)
                token = tokens[index]
                # The reference box, not this glyph, sets the centre line.
                centre_y = float(token.get_top()[1]) + 0.12 + box_h / 2.0
                _seat_count_label(tag, float(token.get_center()[0]), centre_y)
                tag.set_opacity(0)
                tag.set_z_index(6)
                tags.add(tag)
            marker = RoundedRectangle(
                width=cell * 1.02,
                height=cell * 1.02,
                corner_radius=cell * 0.16,
                stroke_color=GOLD,
                stroke_width=7,
                fill_color=GOLD,
                fill_opacity=0.28,
            )
            marker.set_z_index(1)
            marker.set_opacity(0)
            marker.move_to(centers[visits[0]])
            title = styled(labels.get("title") or "", latin, cjk, 40)
            answer = styled(str(labels.get("answer") or ""), latin, cjk, 54)
            note = styled(labels.get("note") or "", latin, cjk, 32)
            foot = VGroup(answer, note).arrange(RIGHT, buff=0.28)
            if ph > pw:
                # A wide answer must not shrink the row, or the label gap collapses.
                limit = max(float(tokens.width), 0.2)
                if float(title.width) > limit:
                    title.scale(limit / float(title.width))
                if float(foot.width) > limit:
                    foot.scale(limit / float(foot.width))
            title.next_to(VGroup(tokens, tags), UP, buff=0.28)
            foot.next_to(tokens, DOWN, buff=0.28)
            board = VGroup(title, tokens, tags, marker, foot)
            settle(board)
            # settle moves the group. Read centres after that, then park the box.
            centres = [tokens[i].get_center().copy() for i in visits]
            marker.move_to(centres[0])
            self.add(tags)
            self.spend(0, FadeIn(title), FadeIn(tokens))
            hops = []
            for i, dest in enumerate(centres):
                tag = tags[i]
                if i == 0:
                    hops.append(lambda dest=dest, tag=tag: AnimationGroup(
                        marker.animate.move_to(dest).set_opacity(1),
                        tag.animate.set_opacity(1),
                    ))
                else:
                    hops.append(lambda dest=dest, tag=tag: AnimationGroup(
                        marker.animate.move_to(dest),
                        tag.animate.set_opacity(1),
                    ))
            counted = self.marks_for(1)
            if counted and len(counted) == len(hops):
                self.spend_marked(1, hops, counted)
            else:
                self.spend_each(1, hops)
            self.spend(2, FadeIn(answer), FadeIn(note))

    class PairCounters(_Board):
        """Counters slide into pairs. A leftover one gets a ring. Pair labels land on the count."""

        def construct(self):
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            n = int(self.vf_n if self.vf_n is not None else labels.get("n") or 0)
            n = max(0, min(20, n))
            pairs, leftover = divmod(n, 2)
            words = [str(w) for w in (labels.get("pairs") or [])]
            pw = int(getattr(config, "pixel_width", 0) or 0) or 1920
            ph = int(getattr(config, "pixel_height", 0) or 0) or 1080
            portrait = ph > pw
            unit = ph / float(config.frame_height or 8.0)
            left_lim, right_lim, _, _ = _safe_limits()
            # Leave a margin so the open pairs, before they slide together, stay inside the safe box.
            max_w = (right_lim - left_lim) * (0.86 if portrait else 0.84)
            slots = max(1, pairs + leftover)
            cols = _pair_columns(slots, portrait)
            pitch = max_w / cols
            label_h = _ordinal_label_height()
            # Scale from a full character. Matching 一's own ink height turns it into a bar.
            cjk_labels = any("\u4e00" <= ch <= "\u9fff" for word in words for ch in word)
            ref = styled("三" if cjk_labels else "8", latin, cjk, 48)
            label_scale = (label_h / float(ref.height)) if float(ref.height) else 1.0
            label_w = 0.0
            for word in words or ["8"]:
                probe = styled(word, latin, cjk, 48)
                label_w = max(label_w, float(probe.width) * label_scale)
            floor_h = (44.0 * (ph / (1920.0 if portrait else 1080.0))) / unit
            room = pitch - (16.0 / unit)
            if pairs and label_w > room > 0 and label_h > 0:
                fitted = room / label_w
                if label_h * fitted < floor_h:
                    fitted = floor_h / label_h
                fitted = min(1.0, fitted)
                label_scale *= fitted
                label_w *= fitted
                label_h *= fitted
            dot_r = min(0.32, max(0.10, pitch * 0.16))
            inner = max(0.03, dot_r * 0.28)
            pair_w = dot_r * 4 + inner
            if pair_w > pitch * 0.78:
                shrink = (pitch * 0.78) / pair_w
                dot_r *= shrink
                inner *= shrink
                pair_w = dot_r * 4 + inner
            row_pitch = label_h + dot_r * 2 + (0.28 if portrait else 0.34)
            rows_n = (slots + cols - 1) // cols
            centres = []
            lone_at = None
            for slot in range(slots):
                r, c = divmod(slot, cols)
                in_row = min(cols, slots - r * cols)
                cx = (c - (in_row - 1) / 2.0) * pitch
                cy = ((rows_n - 1) / 2.0 - r) * row_pitch
                centres.append((cx, cy))
                if slot >= pairs:
                    lone_at = (cx, cy)
            dots = VGroup()
            ends = []
            for i in range(pairs):
                cx, cy = centres[i]
                left = counter(GREEN, dot_r)
                right = counter(GREEN, dot_r)
                left.move_to([cx - (dot_r + inner / 2.0), cy, 0])
                right.move_to([cx + (dot_r + inner / 2.0), cy, 0])
                dots.add(left, right)
                ends.append(left.get_center().copy())
                ends.append(right.get_center().copy())
            lone = None
            if leftover and lone_at is not None:
                lone = counter(GREEN, dot_r)
                lone.move_to([lone_at[0], lone_at[1], 0])
                dots.add(lone)
            tags = VGroup()
            box_h = float(ref.height) * label_scale
            label_cap = max(0.05, pitch - 16.0 / unit)
            for i in range(pairs):
                word = words[i] if i < len(words) else str(i + 1)
                tag = _count_label(word, latin, cjk, label_scale, max_width=label_cap)
                cx, cy = centres[i]
                _seat_count_label(tag, cx, cy + dot_r + 0.08 + box_h / 2.0)
                tag.set_opacity(0)
                tag.set_z_index(6)
                tags.add(tag)
            title = styled(labels.get("title") or "", latin, cjk, 42)
            answer = styled(str(labels.get("answer") or ""), latin, cjk, 54)
            note = styled(labels.get("note") or "", latin, cjk, 32)
            foot = VGroup(answer, note).arrange(RIGHT, buff=0.24)
            marker = RoundedRectangle(
                width=pair_w + 0.16,
                height=dot_r * 2 + 0.16,
                corner_radius=0.08,
                stroke_color=GOLD,
                stroke_width=6,
                fill_color=GOLD,
                fill_opacity=0.18,
            )
            marker.set_z_index(1)
            marker.set_opacity(0)
            if pairs:
                marker.move_to([centres[0][0], centres[0][1], 0])
            ring = None
            if lone is not None:
                ring = Circle(
                    radius=dot_r + 0.07,
                    stroke_color=GOLD,
                    stroke_width=5,
                    fill_opacity=0,
                )
                ring.move_to(lone)
                ring.set_stroke(opacity=0)
                ring.set_z_index(5)
            anchor = dots if len(dots) else marker
            if portrait and len(dots):
                limit = max(float(dots.width), 0.2)
                if float(title.width) > limit:
                    title.scale(limit / float(title.width))
                if float(foot.width) > limit:
                    foot.scale(limit / float(foot.width))
            title.next_to(VGroup(anchor, tags) if len(tags) else anchor, UP, buff=0.26)
            foot.next_to(anchor, DOWN, buff=0.26)
            parts = [title, dots, tags, marker, foot]
            if ring is not None:
                parts.append(ring)
            board = VGroup(*parts)
            settle(board)
            # settle moves the group. Read the closed-pair centres after that.
            closed = [dot.get_center().copy() for dot in dots]
            pair_centres = []
            for i in range(pairs):
                pair_centres.append((closed[2 * i] + closed[2 * i + 1]) / 2)
                tags[i].move_to([
                    float(pair_centres[i][0]),
                    float(tags[i].get_center()[1]),
                    0,
                ])
            if pairs:
                marker.move_to(pair_centres[0])
            # The open pair is what has to stay inside the safe box. Closed
            # pairs sit inside that, so the slide inward cannot leave the margin.
            left_lim, right_lim, _, _ = _safe_limits()
            room = 0.2
            if len(dots):
                room = min(
                    float(dots.get_left()[0]) - left_lim,
                    right_lim - float(dots.get_right()[0]),
                )
            spread = min(0.28, max(0.0, (pitch - pair_w) / 2.0 - 0.04), max(0.0, room - 0.06))
            for i in range(pairs):
                dots[2 * i].shift(LEFT * spread)
                dots[2 * i + 1].shift(RIGHT * spread)
            self.add(tags)
            if ring is not None:
                self.add(ring)
            self.spend(0, FadeIn(title), FadeIn(dots))
            hops = []
            for i in range(pairs):
                dest_l = closed[2 * i]
                dest_r = closed[2 * i + 1]
                dest_m = pair_centres[i]
                tag = tags[i]

                def hop(dest_l=dest_l, dest_r=dest_r, dest_m=dest_m, tag=tag, i=i):
                    left_dot = dots[2 * i]
                    right_dot = dots[2 * i + 1]
                    return AnimationGroup(
                        left_dot.animate.move_to(dest_l),
                        right_dot.animate.move_to(dest_r),
                        marker.animate.move_to(dest_m).set_opacity(1),
                        tag.animate.set_opacity(1),
                    )

                hops.append(hop)
            counted = self.marks_for(1)
            if hops and counted and len(counted) == len(hops):
                self.spend_marked(1, hops, counted)
            else:
                self.spend_each(1, hops)
            closing = [FadeIn(answer), FadeIn(note)]
            if ring is not None:
                closing.append(ring.animate.set_stroke(opacity=1))
            self.spend(2, *closing)

    class PartWhole(_Board):
        """A whole splits into two coloured parts, then the parts join again.

        ``also`` moves the counters to a second split of the same whole.
        ``cover`` hides one part and reads the bond as a subtraction.
        ``leave`` moves that part away: the counters go on the spoken
        number for the part that leaves, and the difference lands on the
        spoken number that stays. An empty circle remains in each spot.
        The two part labels land on the spoken words, and the highlight
        box moves with them. Label centres share one reference glyph.
        """

        def construct(self):
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            raw_a = labels.get("a")
            raw_b = labels.get("b")
            a = 3 if raw_a is None else int(raw_a)
            b = 4 if raw_b is None else int(raw_b)
            whole = a + b
            also = labels.get("also")
            also = int(also) if also is not None else None
            cover = str(labels.get("cover") or "")
            leave = str(labels.get("leave") or "")
            departing = leave in {"a", "b"} and not cover
            if departing:
                cover = leave
            # Zero is an empty mat. When every counter leaves, the zero is only
            # the amount left, so the mat stays off and empty circles remain.
            take_all = departing and (
                (cover == "a" and a > 0 and b == 0) or (cover == "b" and b > 0 and a == 0)
            )
            show_zero_mat = (a == 0 or b == 0) and not take_all
            end_left = also if also is not None else a
            end_right = whole - end_left
            pw = int(getattr(config, "pixel_width", 0) or 0) or 1920
            ph = int(getattr(config, "pixel_height", 0) or 0) or 1080
            portrait = ph > pw
            unit = ph / float(config.frame_height or 8.0)
            left_lim, right_lim, bot_lim, top_lim = _safe_limits()
            max_w = (right_lim - left_lim) * (0.92 if portrait else 0.86)
            max_h = (top_lim - bot_lim) * 0.94

            left_word = str(labels.get("also_left") if also is not None else labels.get("left") or a)
            right_word = str(labels.get("also_right") if also is not None else labels.get("right") or b)
            whole_word = str(labels.get("whole_word") or whole)
            cjk_labels = any(
                "\u4e00" <= ch <= "\u9fff"
                for word in (left_word, right_word, whole_word)
                for ch in word
            )
            label_h = _ordinal_label_height()
            ref = styled("三" if cjk_labels else "8", latin, cjk, 48)
            label_scale = (label_h / float(ref.height)) if float(ref.height) else 1.0
            box_h = float(ref.height) * label_scale
            # The centre test reads a band of about half a unit above the dots.
            # Part labels sit inside it. The bond sits above it.
            label_gap = 16.0 / unit
            window = 46.0 / 720.0 * 8.0

            def label_of(word: str):
                glyph = _count_label(word, latin, cjk, label_scale)
                glyph.set_z_index(6)
                return glyph

            left_label = label_of(left_word)
            right_label = label_of(right_word)
            whole_label = label_of(whole_word)
            half_l = float(left_label.width) / 2
            half_r = float(right_label.width) / 2
            min_dx = half_l + half_r + label_gap

            def cols_for(count: int) -> int:
                return _part_columns(count, portrait)

            def group_width(count: int, radius: float, gap: float) -> float:
                if count <= 0:
                    return max(0.72, radius * 3.4) if show_zero_mat else 0.0
                cols = min(cols_for(count), count)
                return cols * (2 * radius) + (cols - 1) * gap

            def group_height(count: int, radius: float, gap: float) -> float:
                if count <= 0:
                    return max(0.48, radius * 2.2) if show_zero_mat else 0.0
                cols = min(cols_for(count), count)
                rows = (count + cols - 1) // cols
                return rows * (2 * radius) + (rows - 1) * gap

            def slots(count: int, radius: float, gap: float, cx: float, top: float):
                if count <= 0:
                    return []
                cols = min(cols_for(count), count)
                out = []
                for i in range(count):
                    r, c = divmod(i, cols)
                    in_row = min(cols, count - r * cols)
                    row_w = in_row * (2 * radius) + (in_row - 1) * gap
                    left = cx - row_w / 2 + radius
                    y = top - radius - r * (2 * radius + gap)
                    out.append((left + c * (2 * radius + gap), y))
                return out

            def split_at(left_n: int, right_n: int, radius: float, gap: float, group_gap: float, top: float):
                lw = group_width(left_n, radius, gap)
                rw = group_width(right_n, radius, gap)
                # Centres have to clear the two labels, not only the dots.
                group_gap = max(group_gap, min_dx - lw / 2 - rw / 2)
                total = lw + group_gap + rw
                lcx = -total / 2 + lw / 2
                rcx = total / 2 - rw / 2
                left_slots = slots(left_n, radius, gap, lcx, top)
                right_slots = slots(right_n, radius, gap, rcx, top)
                ordered = left_slots + right_slots
                height = max(group_height(left_n, radius, gap), group_height(right_n, radius, gap))
                return ordered, lcx, rcx, total, height

            title = styled(labels.get("title") or "", latin, cjk, 40)
            eq_tokens = list(labels.get("also_equation") if also is not None else labels.get("equation") or [])
            first_tokens = list(labels.get("equation") or eq_tokens)
            bond_eq = equation(eq_tokens or ["0"], latin, 46)
            first_eq = equation(first_tokens or ["0"], latin, 46)
            covered_tokens = list(labels.get("covered_equation") or [])
            covered_eq = equation(covered_tokens, latin, 46) if covered_tokens else None

            # Size the dots so the open split, the labels, and the bond fit.
            chrome = float(title.height) + box_h * 2 + float(bond_eq.height) + 1.15
            best = None
            for radius in (0.26, 0.22, 0.18, 0.15, 0.12, 0.10):
                gap = max(0.05, radius * 0.42)
                joined_gap = max(0.24, radius * 1.15)
                apart_gap = joined_gap + (0.42 if not portrait else 0.22)
                top = 0.0
                start, *_rest = split_at(a, b, radius, gap, apart_gap if not cover else joined_gap, top)
                mid, *_rest = split_at(end_left, end_right, radius, gap, apart_gap, top)
                end, *_rest = split_at(end_left, end_right, radius, gap, joined_gap, top)
                widths = []
                heights = []
                for spec in (
                    split_at(a, b, radius, gap, apart_gap if not cover else joined_gap, top),
                    split_at(end_left, end_right, radius, gap, apart_gap if also is not None else joined_gap, top),
                    split_at(end_left, end_right, radius, gap, joined_gap, top),
                ):
                    widths.append(spec[3])
                    heights.append(spec[4])
                if max(widths) <= max_w and max(heights) + chrome <= max_h:
                    best = (radius, gap, joined_gap, apart_gap, start, mid, end)
                    break
            if best is None:
                radius, gap = 0.09, 0.05
                joined_gap, apart_gap = 0.24, 0.4
                top = 0.0
                start = split_at(a, b, radius, gap, joined_gap if cover else apart_gap, top)[0]
                mid = split_at(end_left, end_right, radius, gap, apart_gap, top)[0]
                end = split_at(end_left, end_right, radius, gap, joined_gap, top)[0]
            else:
                radius, gap, joined_gap, apart_gap, start, mid, end = best

            # Labels sit just above the dot tops. The bond clears the label window.
            label_y = window * 0.55
            if label_y - box_h / 2 < 0.06:
                label_y = box_h / 2 + 0.06
            if label_y + box_h / 2 > window - 0.04:
                label_y = window - 0.04 - box_h / 2
            foot_y = window + 0.08
            apex_y = foot_y + 0.24
            whole_y = apex_y + 0.08 + box_h / 2

            start_pts, start_lcx, start_rcx, _, _ = split_at(
                a, b, radius, gap, joined_gap if cover else apart_gap, 0.0,
            )
            mid_pts, mid_lcx, mid_rcx, _, _ = split_at(
                end_left, end_right, radius, gap, apart_gap, 0.0,
            )
            end_pts, end_lcx, end_rcx, _, end_h = split_at(
                end_left, end_right, radius, gap, joined_gap, 0.0,
            )
            # Index i is one counter. It starts in the first split and ends in the last.
            def assign(points, left_n):
                # points are already left-then-right for that split.
                return list(points)

            start_pos = assign(start_pts, a)
            # Mid and end are grouped by the final split, so remap onto stable indices.
            # Stable index: counters 0..whole-1. Start groups them as a | b.
            # End groups them as end_left | end_right, which is a reordering of the same counters
            # only when also moves the boundary. Counters keep their index: the first
            # end_left counters are the new left part.
            mid_pos = list(mid_pts)
            end_pos = list(end_pts)

            def colour_for(index: int, left_n: int) -> str:
                return GREEN if index < left_n else GOLD

            dots = VGroup()
            for i in range(whole):
                dot = counter(colour_for(i, a), radius)
                x, y = end_pos[i]
                dot.move_to([x, y, 0])
                dots.add(dot)
            mats = VGroup()
            mat_plan = []
            if show_zero_mat and a == 0:
                mat = _zero_mat(radius)
                mat.move_to([end_lcx, -radius, 0])
                mats.add(mat)
                mat_plan.append((mat, (start_lcx, -radius)))
            if show_zero_mat and b == 0:
                mat = _zero_mat(radius)
                mat.move_to([end_rcx, -radius, 0])
                mats.add(mat)
                mat_plan.append((mat, (start_rcx, -radius)))

            _seat_count_label(left_label, end_lcx, label_y)
            _seat_count_label(right_label, end_rcx, label_y)
            _seat_count_label(whole_label, 0.0, whole_y)
            # Where the labels stand while the parts are still apart.
            show_lcx = start_lcx if also is None else mid_lcx
            show_rcx = start_rcx if also is None else mid_rcx
            if cover:
                show_lcx, show_rcx = end_lcx, end_rcx

            reach = max(0.32, min(1.15, abs(float(end_lcx)) * 0.55))
            bracket = VGroup(
                Line([-reach, foot_y, 0], [0.0, apex_y, 0], color=NAVY, stroke_width=5),
                Line([reach, foot_y, 0], [0.0, apex_y, 0], color=NAVY, stroke_width=5),
            )
            bracket.set_z_index(5)
            title.next_to(whole_label, UP, buff=0.16)
            eq_y = -end_h - 0.16 - float(bond_eq.height) / 2
            bond_eq.move_to([0, eq_y, 0])
            first_eq.move_to(bond_eq)
            if covered_eq is not None:
                covered_eq.move_to(bond_eq)

            # The cover is built after the counters are in place, so it matches them.
            card = None

            marker = RoundedRectangle(
                width=max(float(left_label.width), float(right_label.width)) + 0.12,
                height=box_h + 0.06,
                corner_radius=0.08,
                stroke_color=GOLD,
                stroke_width=5,
                fill_color=GOLD,
                fill_opacity=0.16,
            )
            # Behind the glyphs, so a thin 一 stays readable on the gold box.
            marker.set_z_index(5)
            marker.move_to(left_label)
            marker.set_opacity(0)

            left_label.set_opacity(0)
            right_label.set_opacity(0)
            show_bond = bool(cover) or also is not None
            if not show_bond:
                whole_label.set_opacity(0)
                bracket.set_opacity(0)
                bond_eq.set_opacity(0)
            if also is not None:
                # Step 0 shows the first split's bond. Step 1 swaps in the second.
                bond_eq.set_opacity(0)
                first_eq.set_opacity(1)
            if covered_eq is not None:
                covered_eq.set_opacity(0)

            pieces = [title, whole_label, bracket, dots, left_label, right_label, marker, bond_eq]
            if len(mats):
                pieces.append(mats)
            if also is not None:
                pieces.append(first_eq)
            if covered_eq is not None:
                pieces.append(covered_eq)
            # A clear pad as wide as the open split, so settle keeps that spread inside the frame.
            open_pts = start_pos if cover else (mid_pos if also is not None else start_pos)
            xs = [p[0] for p in open_pts + end_pos]
            pad_w = (max(xs) - min(xs)) + radius * 2 + 0.3
            pad = Rectangle(
                width=max(pad_w, float(title.width) + 0.2),
                height=max_h,
                stroke_opacity=0,
                fill_opacity=0,
            )
            pad.move_to(UP * 0)
            board = VGroup(*pieces, pad)
            old_center = board.get_center().copy()
            old_width = max(float(board.width), 1e-6)
            settle(board)
            scale = float(board.width) / old_width
            new_center = board.get_center()

            def mapped(point):
                import numpy as np

                src = np.array([point[0], point[1], 0.0])
                return (src - old_center) * scale + new_center

            board.remove(pad)
            end_centres = [dot.get_center().copy() for dot in dots]
            # Labels and the bond were seated at the joined x. Read them after settle,
            # then park the moving ones on the open split.
            end_left_at = left_label.get_center().copy()
            end_right_at = right_label.get_center().copy()
            whole_at = whole_label.get_center().copy()
            open_left = mapped((show_lcx, label_y, 0))
            open_right = mapped((show_rcx, label_y, 0))
            if not cover:
                left_label.move_to([float(open_left[0]), float(end_left_at[1]), 0])
                right_label.move_to([float(open_right[0]), float(end_right_at[1]), 0])
            marker.move_to(left_label)
            start_centres = [mapped((p[0], p[1], 0)) for p in start_pos]
            mid_centres = [mapped((p[0], p[1], 0)) for p in mid_pos]
            for i, dot in enumerate(dots):
                dot.move_to(start_centres[i])
            mat_ends = []
            for mat, start_xy in mat_plan:
                mat_ends.append(mat.get_center().copy())
                mat.move_to(mapped((start_xy[0], start_xy[1], 0)))
            covered_dots = []
            ghosts = VGroup()
            if cover in {"a", "b"}:
                covered_dots = list(dots[:a] if cover == "a" else dots[a:])
            if departing and covered_dots:
                for dot in covered_dots:
                    ghost = Circle(
                        radius=max(0.04, float(dot.width) / 2.0),
                        stroke_color=NAVY,
                        stroke_width=2.5,
                        fill_color=CREAM,
                        fill_opacity=1,
                    )
                    ghost.move_to(dot.get_center())
                    ghost.set_z_index(1)
                    ghost.set_opacity(0)
                    ghosts.add(ghost)
            elif cover in {"a", "b"} and covered_dots:
                covered_group = VGroup(*covered_dots)
                card = RoundedRectangle(
                    width=float(covered_group.width) + 0.18,
                    height=float(covered_group.height) + 0.16,
                    corner_radius=0.1,
                    stroke_color=NAVY,
                    stroke_width=3,
                    fill_color=WHITE,
                    fill_opacity=1,
                )
                card.move_to(covered_group)
                card.set_z_index(4)
                card.set_opacity(0)

            # Hidden pieces are already on the scene so a later opacity change can find them.
            # Pieces that fade in on the first line are not added twice.
            hidden = [left_label, right_label, marker]
            opening = [FadeIn(title), FadeIn(dots)]
            if len(mats):
                opening.append(FadeIn(mats))
            if show_bond:
                opening.append(FadeIn(bracket))
                opening.append(FadeIn(whole_label))
            else:
                hidden.extend([whole_label, bracket])
            if also is not None:
                opening.append(FadeIn(first_eq))
                hidden.append(bond_eq)
            elif show_bond:
                opening.append(FadeIn(bond_eq))
            else:
                hidden.append(bond_eq)
            if covered_eq is not None:
                hidden.append(covered_eq)
            if card is not None:
                hidden.append(card)
            if len(ghosts):
                hidden.extend(list(ghosts))
            self.add(*hidden)
            self.spend(0, *opening)

            def hop_left():
                return AnimationGroup(
                    left_label.animate.set_opacity(1),
                    marker.animate.move_to(left_label.get_center()).set_opacity(1),
                )

            def hop_right():
                return AnimationGroup(
                    right_label.animate.set_opacity(1),
                    marker.animate.move_to(right_label.get_center()),
                )

            intro = None
            if also is not None:
                moves = []
                for i, dot in enumerate(dots):
                    nxt = colour_for(i, end_left)
                    move = dot.animate.move_to(mid_centres[i])
                    if nxt != colour_for(i, a):
                        move = move.set_fill(nxt)
                    moves.append(move)
                intro = AnimationGroup(
                    *moves,
                    first_eq.animate.set_opacity(0),
                    bond_eq.animate.set_opacity(1),
                )
            self.spend_marked(1, [hop_left, hop_right], self.marks_for(1), intro=intro)

            kept = right_label if cover == "a" else left_label
            if departing:
                outward = LEFT if cover == "a" else RIGHT

                def leave_hop():
                    moves = []
                    for dot in covered_dots:
                        dest = (
                            dot.get_center()
                            + UP * float(dot.height) * 0.85
                            + outward * float(dot.width) * 0.45
                        )
                        moves.append(
                            dot.animate.move_to(dest).set_fill(opacity=0).set_stroke(opacity=0)
                        )
                    for ghost in ghosts:
                        moves.append(ghost.animate.set_opacity(1))
                    if not moves:
                        # Nothing leaves. A part of zero stays an empty mat.
                        return title.animate.set_opacity(1)
                    return AnimationGroup(*moves)

                def reveal_difference():
                    shown = [marker.animate.move_to(kept.get_center())]
                    if covered_eq is not None:
                        shown.extend([
                            bond_eq.animate.set_opacity(0),
                            covered_eq.animate.set_opacity(1),
                        ])
                    return AnimationGroup(*shown)

                self.spend_marked(2, [leave_hop, reveal_difference], self.marks_for(2))
            else:
                closing = [
                    left_label.animate.move_to(end_left_at),
                    right_label.animate.move_to(end_right_at),
                ]
                if also is not None or not cover:
                    for i, dot in enumerate(dots):
                        closing.append(dot.animate.move_to(end_centres[i]).set_fill(colour_for(i, end_left)))
                    for mat, end_at in zip(mats, mat_ends):
                        closing.append(mat.animate.move_to(end_at))
                if not show_bond:
                    closing.extend([
                        bracket.animate.set_opacity(1),
                        whole_label.animate.set_opacity(1),
                        bond_eq.animate.set_opacity(1),
                    ])
                if covered_eq is not None and card is not None:
                    closing.extend([
                        card.animate.set_opacity(1),
                        bond_eq.animate.set_opacity(0),
                        covered_eq.animate.set_opacity(1),
                    ])
                if cover:
                    closing.append(marker.animate.move_to(kept.get_center()))
                else:
                    closing.append(marker.animate.move_to(whole_at))
                self.spend(2, AnimationGroup(*closing))

    class LessonHook(_Board):
        """The title arrives, then the lesson's objects, with the opening question."""

        def construct(self):
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            motif = str(labels.get("motif") or "counters")
            grade = str(labels.get("grade") or "")
            if len(grade) <= 3 and any(ord(ch) > 127 for ch in grade):
                kicker = VGroup(*[
                    Text(ch, font=cjk, font_size=52, color="#5C6B7A") for ch in grade
                ]).arrange(RIGHT, buff=0.2)
            else:
                kicker = Text(grade or " ", font=latin, font_size=40, color="#5C6B7A")
            title = styled(labels.get("title") or "", latin, cjk, 54)
            cue = self._hook_cue(motif, latin, cjk, labels)
            portrait = int(getattr(config, "pixel_height", 0) or 0) > int(getattr(config, "pixel_width", 0) or 0)
            if portrait and motif == "parts":
                # A long English title wraps onto two centred lines at the
                # takeaway floor, and the grade tag is not shrunk with it.
                kicker, title, cue = self._layout_parts_hook(kicker, title, cue, grade, latin, cjk)
            elif portrait and motif in {"ordinal", "pairs"}:
                # Title and tokens each fill the safe width. A long English
                # title must not shrink the row.
                left_lim, right_lim, bot_lim, top_lim = _safe_limits()
                cap = (right_lim - left_lim) * 0.96
                title.next_to(kicker, DOWN, buff=0.22)
                word_w = max(float(title.width), float(kicker.width), 0.01)
                fitted = cap / word_w
                kicker.scale(fitted)
                title.scale(fitted)
                title.next_to(kicker, DOWN, buff=0.22)
                if float(cue.width) > 0:
                    cue.scale(cap / float(cue.width))
                cue.next_to(title, DOWN, buff=0.28)
                group = VGroup(kicker, title, cue)
                max_h = top_lim - bot_lim
                if float(group.height) > max_h > 0:
                    group.scale(max_h / float(group.height))
                group.move_to(UP * 0)
                if float(group.get_bottom()[1]) < bot_lim:
                    group.shift(UP * (bot_lim - float(group.get_bottom()[1])))
            else:
                if motif == "ordinal":
                    # Twice the old token row. A wide title is what the frame scales to,
                    # so the row stays at 2× under that same scale. A short title keeps
                    # the row inside the title width.
                    cue.scale(2)
                    left_lim, right_lim, _, _ = _safe_limits()
                    cap = (right_lim - left_lim) * 0.98
                    limit = max(float(title.width), float(kicker.width), cap)
                    if float(cue.width) > limit:
                        cue.scale(limit / float(cue.width))
                elif motif == "pairs":
                    left_lim, right_lim, _, _ = _safe_limits()
                    cap = (right_lim - left_lim) * 0.78
                    if float(cue.width) > 0:
                        cue.scale(cap / float(cue.width))
                elif motif == "parts":
                    # Same safe-width fill as the 9:16 parts hook.
                    left_lim, right_lim, _, _ = _safe_limits()
                    cap = (right_lim - left_lim) * 0.96
                    if float(cue.width) > 0:
                        cue.scale(cap / float(cue.width))
                title.next_to(kicker, DOWN, buff=0.28)
                cue.next_to(title, DOWN, buff=0.4)
                settle(VGroup(kicker, title, cue))
            total = float((self.vf_durations or [2.0])[0] or 0)
            fps = max(float(config.frame_rate or 15), 1.0)
            frame = 1.0 / fps
            if bool(labels.get("shown")):
                # The caption starts at once. The motif has to be there with it.
                self.add(kicker, title, cue)
                if total > frame / 2:
                    self.wait(total)
                return
            if total <= frame:
                self.add(kicker, title, cue)
                return
            a = max(frame, total * 0.22)
            b = max(frame, total * 0.24)
            c = max(frame, total * 0.36)
            used = a + b + c
            if used > total:
                scale = total / used
                a, b, c = a * scale, b * scale, c * scale
            self.play(FadeIn(kicker), run_time=a)
            self.play(FadeIn(title), run_time=b)
            bits = list(cue) if len(cue) > 1 else [cue]
            self.play(LaggedStart(*[FadeIn(bit) for bit in bits], lag_ratio=0.18), run_time=c)
            rest = total - (a + b + c)
            if rest > frame / 2:
                self.wait(rest)

        def _layout_parts_hook(self, kicker, title, cue, grade: str, latin: str, cjk: str):
            """Portrait parts hook. Title stays at least the takeaway floor.

            One line is used when it can fill the safe width and still clear
            1.5× the floor (52px at 1920 tall). A longer title wraps onto two
            centred lines, then the longer line fills the width. The grade tag
            keeps the size of 小一, and the counters fill the safe width.
            """
            left_lim, right_lim, bot_lim, top_lim = _safe_limits()
            cap = (right_lim - left_lim) * 0.96
            ph = int(getattr(config, "pixel_height", 0) or 0) or 1920
            unit = ph / float(config.frame_height or 8.0)
            floor_h = (52.0 * (ph / 1920.0)) / unit
            if not any(ord(ch) > 127 for ch in (grade or "")):
                ref = Text("小", font=cjk, font_size=52, color="#5C6B7A")
                if float(kicker.height) > 0 and float(ref.height) > 0:
                    kicker.scale(float(ref.height) / float(kicker.height))
            title = self._parts_hook_title(str(self.vf_labels.get("title") or ""), latin, cjk, cap, floor_h)
            if float(cue.width) > 0:
                cue.scale(cap / float(cue.width))
            title.next_to(kicker, DOWN, buff=0.2)
            cue.next_to(title, DOWN, buff=0.26)
            group = VGroup(kicker, title, cue)
            max_h = top_lim - bot_lim
            if float(group.height) > max_h > 0 and float(cue.height) > 0.5:
                overflow = float(group.height) - max_h
                spare = float(cue.height) - 0.45
                if spare > 0.05:
                    keep = max(0.45, float(cue.height) - min(overflow, spare))
                    cue.scale(keep / float(cue.height))
                    title.next_to(kicker, DOWN, buff=0.2)
                    cue.next_to(title, DOWN, buff=0.26)
                    group = VGroup(kicker, title, cue)
            if float(group.height) > max_h > 0:
                group.scale(max_h / float(group.height))
            group.move_to(UP * 0)
            if float(group.get_bottom()[1]) < bot_lim:
                group.shift(UP * (bot_lim - float(group.get_bottom()[1])))
            if float(group.get_top()[1]) > top_lim:
                group.shift(DOWN * (float(group.get_top()[1]) - top_lim))
            return kicker, title, cue

        def _parts_hook_title(self, text: str, latin: str, cjk: str, cap: float, floor_h: float):
            raw = (text or "").strip() or " "
            one = styled(raw, latin, cjk, 54)
            if float(one.width) <= 0:
                return one
            fill = cap / float(one.width)
            words = raw.split()
            # Two centred lines when one full-width line would sit near the floor.
            if len(words) >= 2 and float(one.height) * fill < floor_h * 1.5:
                best = None
                for cut in range(1, len(words)):
                    left = styled(" ".join(words[:cut]), latin, cjk, 54)
                    right = styled(" ".join(words[cut:]), latin, cjk, 54)
                    wider = max(float(left.width), float(right.width))
                    if best is None or wider < best[0]:
                        best = (wider, left, right)
                _wider, left, right = best
                block = VGroup(left, right).arrange(DOWN, buff=0.1)
                line_h = max(float(left.height), float(right.height), 0.01)
                wider = max(float(left.width), float(right.width), 0.01)
                scale = cap / wider
                if line_h * scale < floor_h:
                    scale = floor_h / line_h
                block.scale(scale)
                if float(block.width) > cap > 0:
                    block.scale(cap / float(block.width))
                return block
            scale = fill
            if float(one.height) * scale < floor_h:
                scale = floor_h / float(one.height)
            one.scale(scale)
            if float(one.width) > cap > 0:
                one.scale(cap / float(one.width))
            return one

        def _hook_cue(self, motif: str, latin: str, cjk: str, labels: dict | None = None):
            if motif == "ordinal":
                info = labels or {}
                n = max(1, int(info.get("n") or 6))
                mark = max(1, min(n, int(info.get("mark") or 3)))
                return _ordinal_cue(n, mark, "hook", latin, cjk, one_row=bool(info.get("one_row")))
            if motif == "pairs":
                info = labels or {}
                count = max(0, min(20, int(info.get("n") or 8)))
                return _pair_static(count, 0.18, ring=bool(count % 2))
            if motif == "parts":
                info = labels or {}
                raw_a = info.get("a")
                raw_b = info.get("b")
                part_a = 3 if raw_a is None else int(raw_a)
                part_b = 4 if raw_b is None else int(raw_b)
                return _part_dots(part_a, part_b, 0.2, zero_mat=(part_a == 0 or part_b == 0))
            if motif == "ten_frame":
                frame = ten_cells()
                frame.scale(0.85)
                dots = VGroup(*[counter(GREEN, 0.22) for _ in range(10)])
                for dot, cell in zip(dots, frame):
                    dot.move_to(cell)
                return VGroup(frame, dots)
            if motif == "track":
                return _mini_track(range(8, 13), 12, latin)
            dots = VGroup(*[counter(GREEN, 0.26) for _ in range(5)])
            dots.arrange(RIGHT, buff=0.18)
            return dots

    class LessonTakeaway(_Board):
        """Each spoken line fades in beside a small cue. Earlier lines stay."""

        def construct(self):
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            motif = str(labels.get("motif") or "counters")
            lines = list(labels.get("lines") or ["", "", ""])
            title = styled(labels.get("title") or "", latin, cjk, 48)
            pictures = labels.get("cues")
            if pictures:
                # Named cues replace the motif. The track motif's pictures are
                # a fixed row (9–12, 17–20, 12–9) and must not stand in for a
                # line that named its own picture.
                if len(pictures) != len(lines):
                    raise ValueError("takeaway cue fell back to the default")
                cues = [self._line_cue(picture, latin, cjk) for picture in pictures]
                rows = self._layout_takeaway(
                    title, cues, [str(line) for line in lines], latin, cjk, fit_heading=True,
                )
                title = getattr(self, "_placed_heading", title)
                self.spend(0, FadeIn(title), FadeIn(rows[0]))
                for index in range(1, len(rows)):
                    self.spend(index, FadeIn(rows[index]))
                return
            if len(lines) >= 4 and motif == "counters":
                self._counted_recap(title, lines, latin, cjk)
                return
            if len(lines) >= 4 and motif == "ten_frame":
                self._ten_recap(title, lines, latin, cjk)
                return
            if motif == "ordinal":
                self._ordinal_recap(title, lines, latin, cjk)
                return
            if motif == "pairs":
                self._pair_recap(title, lines, latin, cjk)
                return
            if motif == "parts":
                self._part_recap(title, lines, latin, cjk)
                return
            cues = [_takeaway_cue(motif, i, latin) for i in range(len(lines))]
            rows = self._layout_takeaway(title, cues, [str(line) for line in lines], latin, cjk)
            self.spend(0, FadeIn(title), FadeIn(rows[0]))
            for index in range(1, len(rows)):
                self.spend(index, FadeIn(rows[index]))

        def _body_font(self, latin: str, grid: dict) -> int:
            """One face size for every row and every language.

            The preferred size is 0.42× the row height, and never under the
            pixel floor. If the longest lesson line would overflow the text
            column at that size, every row uses the floor instead of a
            per-language shrink.
            """
            probe = Text(TAKEAWAY_WIDTH_PROBE, font=latin, font_size=48, color=NAVY)
            unit = float(grid["unit"])
            floor_size = 48.0 * (float(grid["floor_px"]) / unit) / float(probe.height)
            preferred_size = 48.0 * (float(grid["preferred_px"]) / unit) / float(probe.height)
            column = float(grid["text_w"]) * (0.96 if grid["portrait"] else 1.0)
            if float(probe.width) * (preferred_size / 48.0) <= column:
                size = preferred_size
            else:
                size = floor_size
            return max(12, int(round(size)))

        def _place_heading(self, heading, grid: dict, fit: bool = False) -> None:
            """Same heading size in every language: the probe title sets the scale."""
            latin = self.vf_fonts[0]
            ref = Text(TAKEAWAY_HEADING_PROBE, font=latin, font_size=48, color=NAVY)
            band = float(grid["heading_h"])
            safe_w = float(grid["right"] - grid["left"])
            scale = (band * 0.52) / float(ref.height) if float(ref.height) else 1.0
            if float(ref.width) * scale > safe_w * 0.92:
                scale = (safe_w * 0.92) / float(ref.width)
            heading.scale(scale)
            # A named-cue heading longer than the probe wraps onto two lines
            # once a single line would fall under the font floor. Headings that
            # already fit stay on one line at the probe size.
            if fit and float(heading.width) > safe_w * 0.92:
                factor = (safe_w * 0.92) / float(heading.width)
                ph = int(getattr(config, "pixel_height", 0) or 0) or 1080
                pw = int(getattr(config, "pixel_width", 0) or 0) or 1920
                portrait = ph > pw
                ref = 1920.0 if portrait else 1080.0
                floor_px = (52.0 if portrait else 44.0) * (ph / ref)
                unit = ph / float(grid["fh"])
                floor_h = floor_px / unit
                # A small extra squeeze stays one line. A long title wraps so
                # the words stay at the font floor.
                words = str(getattr(heading, "original_text", "") or getattr(heading, "text", "") or "")
                if factor < 0.75 and " " in words:
                    heading = self._wrap_heading(words, latin, safe_w * 0.92, band * 0.9, floor_h)
                else:
                    heading.scale(factor)
            cx = (float(grid["left"]) + float(grid["right"])) / 2.0
            cy = float(grid["top"]) - band / 2.0
            heading.move_to([cx, cy, 0])
            self._placed_heading = heading

        def _wrap_heading(self, text: str, latin: str, width: float, height: float, floor_h: float):
            words = text.split()
            best = None
            for cut in range(1, len(words)):
                top = Text(" ".join(words[:cut]), font=latin, font_size=48, color=NAVY)
                bot = Text(" ".join(words[cut:]), font=latin, font_size=48, color=NAVY)
                wide = max(float(top.width), float(bot.width))
                if best is None or wide < best[0]:
                    best = (wide, top, bot)
            group = VGroup(best[1], best[2]).arrange(DOWN, buff=0.08)
            fit = min(width / float(group.width), height / float(group.height))
            line_h = float(best[1].height) * fit
            if line_h < floor_h and float(best[1].height) > 0:
                fit = max(fit, floor_h / float(best[1].height))
                if float(group.width) * fit > width:
                    fit = width / float(group.width)
            group.scale(fit)
            return group

        def _cue_rod(self, width: float, height: float):
            return RoundedRectangle(
                width=width, height=height,
                corner_radius=min(0.08, height * 0.16),
                stroke_color=NAVY, stroke_width=3,
                fill_color=GREEN, fill_opacity=1,
            )

        def _cue_cube(self, side: float):
            return RoundedRectangle(
                width=side, height=side,
                corner_radius=side * 0.18,
                stroke_color=NAVY, stroke_width=3,
                fill_color=GOLD, fill_opacity=1,
            )

        def _cue_bundles(self, rods: int, ones: int):
            """Green ten-rods and gold one-cubes at one size.

            A rod is tall. A cube is a small square, much smaller than a rod.
            Ten rods are two rows of that same rod, not a shorter rod.
            """
            rod_w, rod_h, side, buff = 0.30, 0.70, 0.28, 0.05
            rod_mobs = []
            for _ in range(int(rods)):
                rod = self._cue_rod(rod_w, rod_h)
                rod.vf_block = "rod"
                rod_mobs.append(rod)
            cube_mobs = []
            for _ in range(int(ones)):
                cube = self._cue_cube(side)
                cube.vf_block = "cube"
                cube_mobs.append(cube)
            rods_g = None
            cubes_g = None
            parts = []
            if rod_mobs:
                rods_g = VGroup(*rod_mobs)
                cols = 5 if len(rod_mobs) > 5 else len(rod_mobs)
                rods_g.arrange_in_grid(rows=(len(rod_mobs) + cols - 1) // cols, cols=cols, buff=buff)
                parts.append(rods_g)
            if cube_mobs:
                cubes_g = VGroup(*cube_mobs)
                cols = 5 if len(cube_mobs) > 5 else len(cube_mobs)
                cubes_g.arrange_in_grid(rows=(len(cube_mobs) + cols - 1) // cols, cols=cols, buff=buff)
                parts.append(cubes_g)
            group = VGroup(*parts).arrange(DOWN, buff=buff) if len(parts) > 1 else parts[0]
            group.vf_share = "tens"
            group.vf_rods = rod_mobs
            group.vf_cubes = cube_mobs
            group.vf_rod_group = rods_g
            return group

        def _line_cue(self, picture, latin: str, cjk: str):
            """Draw one named takeaway picture. An unknown picture is an error."""
            kind = picture[0] if picture else ""
            if kind == "tens":
                return self._cue_bundles(int(picture[1]), int(picture[2]))
            if kind == "tens_mark" and len(picture) >= 3:
                return self._cue_pair(int(picture[1]), int(picture[2]), "tens", None, latin, cjk)
            if kind == "tens_mark":
                return self._cue_bundles(int(picture[1]), 0)
            if kind == "compare":
                return self._cue_pair(int(picture[1]), int(picture[2]), "larger", int(picture[3]), latin, cjk)
            if kind == "tiles":
                return self._cue_tiles(picture[1], latin)
            if kind == "pairs":
                return self._cue_pairs(int(picture[1]), int(picture[2]))
            if kind == "groups":
                return self._cue_groups(int(picture[1]), int(picture[2]), int(picture[3]))
            if kind == "counters":
                return self._cue_dots(int(picture[1]))
            raise ValueError(f"takeaway cue fell back to the default: {picture!r}")

        def _compare_card(self, number: int, latin: str, cjk: str, mark: str, larger):
            """One number, every ten-rod and every one-cube, at the shared unit size."""
            tens, ones = divmod(int(number), 10)
            bundles = self._cue_bundles(tens, ones)
            bundles.vf_share = None
            # Ones sit beside the rods, so a hundred still fits a takeaway row
            # and the cubes stay large enough to count.
            if bundles.vf_rod_group is not None and bundles.vf_cubes:
                bundles.arrange(RIGHT, buff=0.10)
            num = styled(str(number), latin, cjk, 42)
            if float(bundles.height) > 0 and float(num.height) > float(bundles.height) * 0.55:
                num.scale((float(bundles.height) * 0.55) / float(num.height))
            body = VGroup(num, bundles).arrange(DOWN, buff=0.08)
            body.vf_number = num
            body.vf_bundles = bundles
            body.vf_rods = bundles.vf_rods
            body.vf_cubes = bundles.vf_cubes
            body.vf_rod_group = bundles.vf_rod_group
            body.vf_value = int(number)
            body.vf_wants_ring = False
            body.vf_mark_target = None
            body.vf_highlight = None
            if mark == "larger" and int(number) == int(larger):
                body.vf_wants_ring = True
                body.vf_mark_target = body
            elif mark == "tens" and bundles.vf_rod_group is not None:
                body.vf_wants_ring = True
                body.vf_mark_target = bundles.vf_rod_group
            return body

        def _cue_pair(self, left: int, right: int, mark: str, larger, latin: str, cjk: str):
            pair = VGroup(
                self._compare_card(left, latin, cjk, mark, larger),
                self._compare_card(right, latin, cjk, mark, larger),
            ).arrange(RIGHT, buff=0.3)
            pair.vf_compare_cards = (pair[0], pair[1])
            pair.vf_share = None
            return pair

        def _open_rod_ring_gap(self, card, need: float) -> None:
            """Keep the ten-rod outline off the digits and off the one-cubes."""
            number = card.vf_number
            rods = card.vf_rod_group
            if rods is None:
                return
            gap = float(number.get_bottom()[1] - rods.get_top()[1])
            if gap < need:
                number.shift(UP * (need - gap))
            if not card.vf_cubes:
                return
            rod_right = float(rods.get_right()[0])
            cube_left = min(float(cube.get_left()[0]) for cube in card.vf_cubes)
            if cube_left - rod_right < need:
                shift = need - (cube_left - rod_right)
                for cube in card.vf_cubes:
                    cube.shift(RIGHT * shift)

        def _fit_compare_cards(self, group, vis_w: float, vis_h: float) -> None:
            """Same block size on both numbers, then a gap that stays 40px at 1080p.

            The gold ring is added after that scale, so its padding is in final
            units and surrounds the number and the blocks.
            """
            gap = 44.0 * 8.0 / 1080.0
            pad = 18.0 * 8.0 / 1080.0
            air = 8.0 * 8.0 / 1080.0
            left, right = group.vf_compare_cards
            tens = left.vf_mark_target is left.vf_rod_group

            def _opened(card) -> tuple[float, float]:
                """Extra width and height inserted after the scale, in final units."""
                if not tens:
                    return 0.0, 0.0
                extra_w = (pad + air) if card.vf_cubes else 0.0
                return extra_w, pad + air

            extra_w = _opened(left)[0] + _opened(right)[0]
            extra_h = max(_opened(left)[1], _opened(right)[1])
            pair_w = float(left.width) + float(right.width)
            pair_h = max(float(left.height), float(right.height))
            room_w = max(0.2, vis_w - gap - 2.0 * pad - extra_w)
            room_h = max(0.2, vis_h - 2.0 * pad - extra_h)
            scale = min(room_w / pair_w, room_h / pair_h) if pair_w > 0 and pair_h > 0 else 1.0
            left.scale(scale)
            right.scale(scale)
            if tens:
                self._open_rod_ring_gap(left, pad + air)
                self._open_rod_ring_gap(right, pad + air)
            right.next_to(left, RIGHT, buff=gap)
            for card in (left, right):
                if card.vf_wants_ring and card.vf_mark_target is not None:
                    ring = SurroundingRectangle(card.vf_mark_target, color=GOLD, buff=pad, stroke_width=5)
                    ring.set_fill(opacity=0)
                    card.add(ring)
                    card.vf_highlight = ring

        def _cue_tiles(self, values, latin: str):
            tiles = VGroup()
            for value in values:
                num = Text(str(value), font=latin, font_size=48, color=NAVY)
                box = RoundedRectangle(
                    width=max(float(num.width) + 0.18, 0.7),
                    height=float(num.height) + 0.2,
                    corner_radius=0.08,
                    stroke_color=NAVY, stroke_width=3,
                    fill_color=WHITE, fill_opacity=1,
                )
                num.move_to(box)
                tiles.add(VGroup(box, num))
            tiles.arrange(RIGHT, buff=0.08)
            return tiles

        def _cue_pair_box(self):
            dots = VGroup(counter(GREEN, 0.1), counter(GREEN, 0.1)).arrange(RIGHT, buff=0.05)
            frame = RoundedRectangle(
                width=float(dots.width) + 0.16,
                height=float(dots.height) + 0.14,
                corner_radius=0.08,
                stroke_color=NAVY, stroke_width=3,
                fill_color=WHITE, fill_opacity=1,
            )
            dots.move_to(frame)
            return VGroup(frame, dots)

        def _cue_pairs(self, boxes: int, extra: int):
            group = VGroup(*[self._cue_pair_box() for _ in range(boxes)])
            if boxes > 4:
                group.arrange_in_grid(rows=2, cols=3, buff=0.1)
            else:
                group.arrange(RIGHT, buff=0.1)
            if not extra:
                return group
            dot = counter(GOLD, 0.12)
            ring = SurroundingRectangle(dot, color=GOLD, buff=0.06, stroke_width=4)
            ring.set_fill(opacity=0)
            loose = VGroup(dot, ring)
            return VGroup(group, loose).arrange(RIGHT, buff=0.14)

        def _cue_group_box(self, size: int):
            """One box of equal counters. Five sit as three and two."""
            cols = size if size <= 3 else 3
            dots = VGroup(*[counter(GREEN, 0.08) for _ in range(size)])
            dots.arrange_in_grid(rows=(size + cols - 1) // cols, cols=cols, buff=0.04)
            frame = RoundedRectangle(
                width=float(dots.width) + 0.14,
                height=float(dots.height) + 0.12,
                corner_radius=0.08,
                stroke_color=NAVY, stroke_width=3,
                fill_color=WHITE, fill_opacity=1,
            )
            dots.move_to(frame)
            return VGroup(frame, dots)

        def _cue_groups(self, size: int, boxes: int, extra: int):
            """Boxes of the same size, plus any loose counters beside them."""
            group = VGroup(*[self._cue_group_box(size) for _ in range(boxes)])
            group.arrange(RIGHT, buff=0.08)
            if not extra:
                return group
            loose_dots = VGroup(*[counter(GOLD, 0.08) for _ in range(extra)])
            loose_dots.arrange(RIGHT, buff=0.04)
            ring = SurroundingRectangle(loose_dots, color=GOLD, buff=0.06, stroke_width=4)
            ring.set_fill(opacity=0)
            return VGroup(group, VGroup(loose_dots, ring)).arrange(RIGHT, buff=0.12)

        def _cue_dots(self, count: int):
            dots = VGroup(*[counter(GREEN, 0.12) for _ in range(count)])
            cols = 6 if count > 6 else count
            dots.arrange_in_grid(rows=(count + cols - 1) // cols, cols=cols, buff=0.08)
            return dots

        def _cue_vis(self, grid: dict, portrait: bool, compared: bool):
            """The picture box for one takeaway row.

            A comparison uses more of a portrait cell so the blocks stay
            readable. Every other cue keeps the original box.
            """
            if portrait:
                portion = 0.74 if compared else TAKEAWAY_PORTRAIT_VISUAL
                fit = 0.94 if compared else 0.88
                vis_h = float(grid["cell_h"]) * portion * fit
                vis_w = float(grid["vis_w"]) * 0.92
                return vis_w, vis_h, portion
            vis_h = float(grid["cell_h"]) * float(grid["visual_of_cell"])
            gutter = (TAKEAWAY_COLUMN_GAP_PX + 6) * 8.0 / 1080.0
            vis_w = max(0.4, float(grid["vis_w"]) - 2.0 * gutter)
            return vis_w, vis_h, TAKEAWAY_PORTRAIT_VISUAL

        def _layout_takeaway(self, heading, cues, lines, latin: str, cjk: str, text_fit: float = 0.96, fit_heading: bool = False) -> list:
            """Put each cue and its sentence into an equal row cell."""
            pw = int(getattr(config, "pixel_width", 0) or 0) or 1920
            ph = int(getattr(config, "pixel_height", 0) or 0) or 1080
            grid = takeaway_grid(pw, ph, len(lines))
            self._place_heading(heading, grid, fit=fit_heading)
            font = self._body_font(latin, grid)
            portrait = bool(grid["portrait"])
            words = [
                self._line_group(text, latin, cjk, font, float(grid["text_w"]) * text_fit, portrait)
                for text in lines
            ]
            if portrait:
                zone = float(grid["cell_h"]) * (1.0 - TAKEAWAY_PORTRAIT_VISUAL) * 0.92
                plain = []
                compared_words = []
                for word, cue in zip(words, cues):
                    if getattr(cue, "vf_compare_cards", None):
                        compared_words.append(word)
                    else:
                        plain.append(word)
                if plain:
                    tallest = max(float(word.height) for word in plain)
                    if tallest > zone > 0:
                        shrink = zone / tallest
                        for word in plain:
                            word.scale(shrink)
                if compared_words:
                    _vw, _vh, portion = self._cue_vis(grid, True, True)
                    band = float(grid["cell_h"]) * (1.0 - portion) * 0.90
                    tallest = max(float(word.height) for word in compared_words)
                    if tallest > band > 0:
                        shrink = band / tallest
                        for word in compared_words:
                            word.scale(shrink)
            rows = []
            # Tens rows share one scale, so a cube stays smaller than a rod and
            # ten rods are the same rod as four rods. Other cues still fill
            # their own cell.
            tens_scale = None
            if cues and all(getattr(cue, "vf_share", None) == "tens" for cue in cues):
                fits = []
                for cue in cues:
                    vis_w, vis_h, _portion = self._cue_vis(grid, portrait, False)
                    if float(cue.width) > 0 and float(cue.height) > 0:
                        fits.append(min(vis_w / float(cue.width), vis_h / float(cue.height)))
                tens_scale = min(fits) if fits else 1.0
            for cue, word, cell in zip(cues, words, grid["cells"]):
                compared = bool(getattr(cue, "vf_compare_cards", None))
                vis_w, vis_h, portion = self._cue_vis(grid, portrait, compared)
                if compared:
                    self._fit_compare_cards(cue, vis_w, vis_h)
                elif tens_scale is not None:
                    cue.scale(tens_scale)
                elif float(cue.width) > 0 and float(cue.height) > 0:
                    cue.scale(min(vis_w / float(cue.width), vis_h / float(cue.height)))
                if portrait:
                    zone_top = float(cell["top"])
                    zone_bot = zone_top - float(grid["cell_h"]) * portion
                    cue.move_to([(float(grid["left"]) + float(grid["right"])) / 2.0, (zone_top + zone_bot) / 2.0, 0])
                    text_top = zone_bot
                    text_bot = float(cell["bottom"])
                    word.move_to([(float(grid["left"]) + float(grid["right"])) / 2.0, (text_top + text_bot) / 2.0, 0])
                else:
                    cue.move_to([float(grid["vis_left"]) + float(grid["vis_w"]) / 2.0, float(cell["cy"]), 0])
                    word.move_to([float(grid["text_left"]) + float(word.width) / 2.0, float(cell["cy"]), 0])
                rows.append(VGroup(cue, word))
            if portrait and rows:
                block = VGroup(*rows)
                mid = (float(grid["rows_top"]) + float(grid["rows_bottom"])) / 2.0
                delta = mid - float(block.get_center()[1])
                top = float(block.get_top()[1]) + delta
                bot = float(block.get_bottom()[1]) + delta
                if top > float(grid["rows_top"]):
                    delta -= top - float(grid["rows_top"])
                bot = float(block.get_bottom()[1]) + delta
                if bot < float(grid["rows_bottom"]):
                    delta += float(grid["rows_bottom"]) - bot
                if abs(delta) > 1e-4:
                    block.shift(UP * delta)
            return rows

        def _balanced_pieces(self, text: str, latin: str, cjk: str, size: int, width: float) -> list[str]:
            """Fewest lines that fit, with the most even split. Pieces stay whole."""
            pieces = takeaway_pieces(text)
            cjk_text = any("\u4e00" <= ch <= "\u9fff" for ch in text)
            joiner = "" if cjk_text else " "

            def width_of(sample: str) -> float:
                return float(styled(sample, latin, cjk, size).width)

            def join(parts: list[str]) -> str:
                return joiner.join(parts)

            if width_of(text) <= width or len(pieces) <= 1:
                return [text]
            for count in range(2, len(pieces) + 1):
                fits: list[list[str]] = []

                def walk(start: int, left: int, acc: list[str]) -> None:
                    if left == 1:
                        fits.append(acc + [join(pieces[start:])])
                        return
                    for cut in range(start + 1, len(pieces) - left + 2):
                        walk(cut, left - 1, acc + [join(pieces[start:cut])])

                walk(0, count, [])
                ok = []
                for lines in fits:
                    widths = [width_of(line) for line in lines]
                    if max(widths) <= width + 0.02:
                        ok.append((max(widths) - min(widths), max(widths), lines))
                if ok:
                    ok.sort(key=lambda item: (item[0], item[1]))
                    return ok[0][2]
            return pieces

        def _line_group(self, text: str, latin: str, cjk: str, size: int, width: float, portrait: bool):
            """Keep a line whole when it fits. Otherwise break on a sentence or a word.

            Chinese breaks only at punctuation. English breaks at a sentence
            first, then at a balanced word boundary. The face size is not
            changed here, so every row stays on the shared size.
            """
            raw = (text or "").strip() or " "
            whole = styled(raw, latin, cjk, size)
            if float(whole.width) <= width:
                return whole
            # A sentence break beats a word break: "Find the ten first. Then…"
            # stays two sentences when each one fits the column.
            if not any("\u4e00" <= ch <= "\u9fff" for ch in raw):
                sentences: list[str] = []
                buf = ""
                for ch in raw:
                    buf += ch
                    if ch in ".!?" and len(buf.strip()) > 1:
                        sentences.append(buf.strip())
                        buf = ""
                if buf.strip():
                    sentences.append(buf.strip())
                if len(sentences) > 1 and float(styled(raw, latin, cjk, size).width) > width:
                    lines: list[str] = []
                    for sentence in sentences:
                        if float(styled(sentence, latin, cjk, size).width) <= width:
                            lines.append(sentence)
                        else:
                            lines.extend(self._balanced_pieces(sentence, latin, cjk, size, width))
                    group = VGroup(*[styled(line, latin, cjk, size) for line in lines])
                    self._stack_lines(group, portrait)
                    return group
            chosen = self._balanced_pieces(raw, latin, cjk, size, width)
            group = VGroup(*[styled(line, latin, cjk, size) for line in chosen])
            self._stack_lines(group, portrait)
            return group

        def _stack_lines(self, group, portrait: bool) -> None:
            """Portrait centres each line. Landscape keeps a left edge."""
            if portrait:
                group.arrange(DOWN, buff=0.06)
            else:
                group.arrange(DOWN, buff=0.06, aligned_edge=LEFT)

        def _counted_recap(self, title, lines, latin: str, cjk: str) -> None:
            """Four ideas: light five, a big 5, move into a circle, an empty tray."""
            import math

            from manim import Circle

            dim = "#D5D0C6"
            count = max(1, int(self.vf_labels.get("count") or 5))
            radius = 0.30
            dots = VGroup(*[counter(dim, radius) for _ in range(count)])
            dots.arrange(RIGHT, buff=0.14)
            numbers = VGroup()
            for i, dot in enumerate(dots):
                num = _count_label(
                    str(i + 1), latin, cjk, 1.0,
                    size=28, color=WHITE, max_width=float(dot.width) * 0.72,
                )
                _seat_count_label(num, float(dot.get_center()[0]), float(dot.get_center()[1]))
                num.set_z_index(4)
                num.set_opacity(0)
                numbers.add(num)
            cue0 = VGroup(dots, numbers)

            big = Text("5", font=latin, font_size=78, color=NAVY)
            cue1 = VGroup(big)

            ring = 0.58
            anchors = VGroup(*[
                Circle(radius=0.01, stroke_opacity=0, fill_opacity=0)
                for _ in range(count)
            ])
            for i, pin in enumerate(anchors):
                ang = math.pi / 2 - i * 2 * math.pi / count
                pin.move_to([ring * math.cos(ang), ring * math.sin(ang), 0])
            movers = VGroup(*[counter(GREEN, 0.20) for _ in range(count)])
            for dot, pin in zip(movers, anchors):
                dot.move_to(pin)
            still = Text("5", font=latin, font_size=42, color=NAVY)
            # The pins are tiny. Measure the counters themselves, or the 5 lands on a dot.
            cluster_right = max(float(dot.get_right()[0]) for dot in movers)
            still.move_to([
                cluster_right + 0.36 + float(still.width) / 2.0,
                float(anchors.get_center()[1]),
                0,
            ])
            cue2 = VGroup(anchors, movers, still)

            tray = RoundedRectangle(
                width=2.70, height=1.15, corner_radius=0.14,
                stroke_color=NAVY, stroke_width=4, fill_color=WHITE, fill_opacity=1,
            )
            zero = Text("0", font=latin, font_size=54, color=NAVY)
            zero.move_to(tray)
            cue3 = VGroup(tray, zero)
            cues = [cue0, cue1, cue2, cue3]
            line_strings = [str(line) for line in list(lines)[:4]]
            rows = self._layout_takeaway(title, cues, line_strings, latin, cjk)
            words = [row[1] for row in rows]
            targets = [dot.get_center().copy() for dot in movers]
            home = anchors.get_center()
            for dot in movers:
                dot.move_to(home)
            self.add(numbers)

            lights = []
            for dot, num in zip(dots, numbers):
                lights.append(lambda dot=dot, num=num: AnimationGroup(
                    dot.animate.set_fill(GREEN, opacity=1),
                    num.animate.set_opacity(1),
                ))
            counted = self.marks_for(0)
            total = float((self.vf_durations or [0])[0] or 0)
            if len(counted) != count and total > 0:
                gap = total / (count + 1)
                counted = [gap * (i + 1) for i in range(count)]
            intro = AnimationGroup(FadeIn(title), FadeIn(words[0]), FadeIn(dots))
            self.spend_marked(0, lights, counted, intro=intro)
            self.spend(1, FadeIn(rows[1]))
            self._move_into_circle(2, words[2], still, movers, targets)
            self.spend(3, FadeIn(rows[3]))

        def _move_into_circle(self, index: int, words, still, movers, targets) -> None:
            total = 0.0
            durs = getattr(self, "vf_durations", []) or []
            if 0 <= index < len(durs):
                total = float(durs[index])
            fps = max(float(config.frame_rate or 15), 1.0)
            frame = 1.0 / fps
            if total <= frame:
                self.add(words, still, movers)
                for dot, dest in zip(movers, targets):
                    dot.move_to(dest)
                return
            intro_t = min(0.6, max(frame, total * 0.28))
            self.play(FadeIn(words), FadeIn(still), FadeIn(movers), run_time=intro_t)
            move_t = min(1.15, max(frame, (total - intro_t) * 0.62))
            self.play(
                *[dot.animate.move_to(dest) for dot, dest in zip(movers, targets)],
                run_time=move_t,
            )
            rest = total - intro_t - move_t
            if rest > frame / 2:
                self.wait(rest)

        def _ten_recap(self, title, lines, latin: str, cjk: str) -> None:
            """Four ideas, one frame size: one ten, thirteen, twenty, then the ones."""
            dim = "#D5D0C6"
            line_strings = [str(line) for line in list(lines)[:4]]

            def filled():
                frame = ten_cells()
                cell = frame[0]
                radius = min(float(cell.width), float(cell.height)) * 0.30
                dots = VGroup(*[counter(GREEN, radius) for _ in range(10)])
                for dot, box in zip(dots, frame):
                    dot.move_to(box)
                return frame, dots

            def beside(frame, color: str):
                cell = frame[0]
                radius = min(float(cell.width), float(cell.height)) * 0.30
                dots = VGroup(*[counter(color, radius) for _ in range(3)])
                dots.arrange(RIGHT, buff=max(0.06, radius * 0.55))
                dots.next_to(frame, RIGHT, buff=0.18)
                return dots

            def number(label: str, anchor):
                num = Text(str(label), font=latin, font_size=54, color=NAVY)
                num.next_to(anchor, RIGHT, buff=0.14)
                num.set_y(float(anchor.get_y()))
                return num

            frame0, dots0 = filled()
            cue0 = VGroup(frame0, dots0)
            frame1, dots1 = filled()
            ones1 = beside(frame1, GREEN)
            cue1 = VGroup(frame1, dots1, ones1, number("13", ones1))
            frame_a, dots_a = filled()
            frame_b, dots_b = filled()
            pair = VGroup(VGroup(frame_a, dots_a), VGroup(frame_b, dots_b))
            pair.arrange(RIGHT, buff=0.16)
            cue2 = VGroup(pair, number("20", pair))
            frame3, dots3 = filled()
            ones3 = beside(frame3, dim)
            cue3 = VGroup(frame3, dots3, ones3)
            cues = [cue0, cue1, cue2, cue3]
            rows = self._layout_takeaway(title, cues, line_strings, latin, cjk)
            words = [row[1] for row in rows]
            ring = SurroundingRectangle(frame3, color=GOLD, buff=0.07, stroke_width=5)
            ring.set_z_index(5)

            self.spend(0, FadeIn(title), FadeIn(rows[0]))
            self.spend(1, FadeIn(rows[1]))
            self.spend(2, FadeIn(rows[2]))
            lights = [lambda dot=dot: dot.animate.set_fill(GREEN, opacity=1) for dot in ones3]
            counted = self.marks_for(3)
            total = float((self.vf_durations or [0, 0, 0, 0])[3] or 0)
            if len(counted) != 3 and total > 0:
                start = total * 0.42
                span = total * 0.5
                counted = [start + span * (i + 0.5) / 3 for i in range(3)]
            intro = AnimationGroup(
                FadeIn(words[3]), FadeIn(frame3), FadeIn(dots3), FadeIn(ones3), FadeIn(ring),
            )
            self.spend_marked(3, lights, counted, intro=intro)

        def _ordinal_recap(self, title, lines, latin: str, cjk: str) -> None:
            """How many, the place from the left, the place from the right, then both."""
            info = self.vf_labels
            n = max(1, int(info.get("n") or 6))
            mark = max(1, min(n, int(info.get("mark") or 3)))
            left = str(info.get("left") or "")
            right = str(info.get("right") or "")
            total = str(info.get("total") or n)
            portrait = int(getattr(config, "pixel_height", 0) or 0) > int(getattr(config, "pixel_width", 0) or 0)
            # A short place label keeps an 80%-wide portrait row inside the picture band.
            label_frac = 0.38 if portrait else 0.85
            one_row = bool(info.get("one_row"))
            cues = [
                _ordinal_cue(n, mark, "total", latin, cjk, total=total, label_frac=label_frac, one_row=one_row),
                _ordinal_cue(n, mark, "left", latin, cjk, word=left, label_frac=label_frac, one_row=one_row),
                _ordinal_cue(n, mark, "right", latin, cjk, word=right, label_frac=label_frac, one_row=one_row),
                _ordinal_cue(n, mark, "both", latin, cjk, total=total, label_frac=label_frac, one_row=one_row),
            ]
            # One token size and one left edge. The place label sits in the
            # shared height, so label-plus-row is centred as one picture.
            boards = [cue[0] for cue in cues]
            for cue, board in zip(cues, boards):
                cue.shift(LEFT * float(board.get_left()[0]))
                cue.shift(DOWN * float(board.get_center()[1]))
            pad_left = min(float(cue.get_left()[0]) for cue in cues)
            pad_right = max(float(cue.get_right()[0]) for cue in cues)
            pad_top = max(float(cue.get_top()[1]) for cue in cues)
            pad_bottom = min(float(cue.get_bottom()[1]) for cue in cues)
            for cue in cues:
                pad = Rectangle(
                    width=max(0.01, pad_right - pad_left),
                    height=max(0.01, pad_top - pad_bottom),
                    stroke_opacity=0,
                    fill_opacity=0,
                )
                pad.move_to([(pad_left + pad_right) / 2.0, (pad_top + pad_bottom) / 2.0, 0])
                cue.add(pad)
            shown = [str(line) for line in list(lines)[:4]]
            while len(shown) < 4:
                shown.append(" ")
            if portrait:
                rows = self._layout_ordinal_portrait(
                    title, cues[: len(lines)], boards[: len(lines)], shown[: len(lines)], latin, cjk,
                )
            else:
                rows = self._layout_takeaway(title, cues[: len(lines)], shown[: len(lines)], latin, cjk)
            self.spend(0, FadeIn(title), FadeIn(rows[0]))
            for index in range(1, len(rows)):
                self.spend(index, FadeIn(rows[index]))

        def _pair_recap(self, title, lines, latin: str, cjk: str) -> None:
            """Even, odd, a pair of two, and — when set — that count in two rows of pairs."""
            info = self.vf_labels
            even = int(info.get("n") or 8)
            odd = int(info.get("odd") if info.get("odd") is not None else min(20, even + 1))
            radius = 0.16
            built = [
                _pair_static(even, radius, ring=False),
                _pair_static(odd, radius, ring=True),
                _pair_static(2, radius, ring=False),
            ]
            if info.get("also") is not None:
                also_n = int(info.get("also"))
                # Same counter size as the odd row. Ten slots wrap to two rows of five,
                # so nine pairs and the ringed leftover stay countable inside the picture column.
                built.append(_pair_static(also_n, radius, ring=bool(also_n % 2)))
            shown = [str(line) for line in list(lines)]
            cues = []
            boards = []
            for i, board in enumerate(built):
                if i == 3:
                    cues.append(board)
                    boards.append(board[0])
                else:
                    cues.append(board)
                    boards.append(board[0] if len(board) else board)
            for cue, board in zip(cues, boards):
                cue.shift(LEFT * float(board.get_left()[0]))
                cue.shift(DOWN * float(board.get_center()[1]))
            pad_left = min(float(cue.get_left()[0]) for cue in cues)
            pad_right = max(float(cue.get_right()[0]) for cue in cues)
            pad_top = max(float(cue.get_top()[1]) for cue in cues)
            pad_bottom = min(float(cue.get_bottom()[1]) for cue in cues)
            for cue in cues:
                pad = Rectangle(
                    width=max(0.01, pad_right - pad_left),
                    height=max(0.01, pad_top - pad_bottom),
                    stroke_opacity=0,
                    fill_opacity=0,
                )
                pad.move_to([(pad_left + pad_right) / 2.0, (pad_top + pad_bottom) / 2.0, 0])
                cue.add(pad)
            while len(shown) < len(cues):
                shown.append(" ")
            use = min(len(shown), len(cues))
            portrait = int(getattr(config, "pixel_height", 0) or 0) > int(getattr(config, "pixel_width", 0) or 0)
            if portrait:
                rows = self._layout_ordinal_portrait(
                    title, cues[:use], boards[:use], shown[:use], latin, cjk,
                )
            else:
                # The full text column, so "Eight makes four pairs. Eight is even."
                # stays one line at the floor size. Other motifs keep the 4% inset.
                rows = self._layout_takeaway(title, cues[:use], shown[:use], latin, cjk, text_fit=1.0)
            self.spend(0, FadeIn(title), FadeIn(rows[0]))
            for index in range(1, len(rows)):
                self.spend(index, FadeIn(rows[index]))

        def _heading_that_fits(self, heading, latin: str, cjk: str, n: int):
            """Keep a parts heading inside the safe width at the shared size.

            English wraps onto two centred lines when one line would cross the
            margin. A heading with no break shrinks only enough to fit.
            """
            pw = int(getattr(config, "pixel_width", 0) or 0) or 1920
            ph = int(getattr(config, "pixel_height", 0) or 0) or 1080
            grid = takeaway_grid(pw, ph, max(1, int(n)))
            ref = Text(TAKEAWAY_HEADING_PROBE, font=latin, font_size=48, color=NAVY)
            band = float(grid["heading_h"])
            safe_w = float(grid["right"] - grid["left"])
            scale = (band * 0.52) / float(ref.height) if float(ref.height) else 1.0
            if float(ref.width) * scale > safe_w * 0.92:
                scale = (safe_w * 0.92) / float(ref.width)
            limit = safe_w * 0.96
            text = str(self.vf_labels.get("title") or "")
            words = text.split()

            def too_wide(mob) -> bool:
                return float(mob.width) * scale > limit

            if len(words) >= 2 and too_wide(heading):
                best = None
                for cut in range(1, len(words)):
                    left = styled(" ".join(words[:cut]), latin, cjk, 48)
                    right = styled(" ".join(words[cut:]), latin, cjk, 48)
                    wider = max(float(left.width), float(right.width))
                    if best is None or wider < best[0]:
                        best = (wider, left, right)
                block = VGroup(best[1], best[2]).arrange(DOWN, buff=0.06)
                if not too_wide(block) and float(block.height) * scale <= band * 0.92:
                    return block
                heading = block
            if too_wide(heading) and float(heading.width) > 0:
                heading.scale(limit / (float(heading.width) * scale))
            if float(heading.height) * scale > band * 0.92 > 0:
                heading.scale((band * 0.92) / (float(heading.height) * scale))
            return heading

        def _part_recap(self, title, lines, latin: str, cjk: str) -> None:
            """Each bond is two coloured parts, or one green whole."""
            title = self._heading_that_fits(title, latin, cjk, len(lines))
            info = self.vf_labels
            bonds = list(info.get("bonds") or [[3, 4], [5, 2], [7], [4, 8]])
            cues = []
            boards = []
            for bond in bonds:
                nums = [int(n) for n in bond]
                if len(nums) == 1:
                    cue = _part_dots(nums[0], 0, 0.15)
                elif len(nums) == 2 and nums[1] < 0:
                    cue = _part_dots(nums[0], 0, 0.15, gone=-nums[1])
                else:
                    cue = _part_dots(nums[0], nums[1], 0.15, zero_mat=True)
                cues.append(cue)
                boards.append(cue)
            for cue in cues:
                cue.shift(LEFT * float(cue.get_left()[0]))
                cue.shift(DOWN * float(cue.get_center()[1]))
            pad_left = min(float(cue.get_left()[0]) for cue in cues)
            pad_right = max(float(cue.get_right()[0]) for cue in cues)
            pad_top = max(float(cue.get_top()[1]) for cue in cues)
            pad_bottom = min(float(cue.get_bottom()[1]) for cue in cues)
            for cue in cues:
                pad = Rectangle(
                    width=max(0.01, pad_right - pad_left),
                    height=max(0.01, pad_top - pad_bottom),
                    stroke_opacity=0,
                    fill_opacity=0,
                )
                pad.move_to([(pad_left + pad_right) / 2.0, (pad_top + pad_bottom) / 2.0, 0])
                cue.add(pad)
            shown = [str(line) for line in list(lines)]
            while len(shown) < len(cues):
                shown.append(" ")
            use = min(len(shown), len(cues))
            portrait = int(getattr(config, "pixel_height", 0) or 0) > int(getattr(config, "pixel_width", 0) or 0)
            if portrait:
                rows = self._layout_ordinal_portrait(
                    title, cues[:use], boards[:use], shown[:use], latin, cjk,
                )
            else:
                rows = self._layout_takeaway(title, cues[:use], shown[:use], latin, cjk, text_fit=1.0)
            self.spend(0, FadeIn(title), FadeIn(rows[0]))
            for index in range(1, len(rows)):
                self.spend(index, FadeIn(rows[index]))

        def _layout_ordinal_portrait(self, heading, cues, boards, lines, latin: str, cjk: str) -> list:
            """Portrait ordinal rows share one size, about 80% of the safe width."""
            pw = int(getattr(config, "pixel_width", 0) or 0) or 1080
            ph = int(getattr(config, "pixel_height", 0) or 0) or 1920
            grid = takeaway_grid(pw, ph, len(lines))
            self._place_heading(heading, grid)
            font = self._body_font(latin, grid)
            words = [
                self._line_group(text, latin, cjk, font, float(grid["text_w"]) * 0.96, True)
                for text in lines
            ]
            zone = float(grid["cell_h"]) * (1.0 - TAKEAWAY_PORTRAIT_VISUAL) * 0.92
            tallest = max((float(word.height) for word in words), default=0.0)
            if tallest > zone > 0:
                shrink = zone / tallest
                for word in words:
                    word.scale(shrink)
            safe_w = float(grid["right"] - grid["left"])
            board_w = max((float(board.width) for board in boards), default=1.0) or 1.0
            scale = (0.80 * safe_w) / board_w
            for cue in cues:
                cue.scale(scale)
            # Stay in the top half of the cell so the sentence underneath still fits.
            vis_h = float(grid["cell_h"]) * 0.50
            tall = max((float(cue.height) for cue in cues), default=0.0)
            if tall > vis_h > 0:
                fit = vis_h / tall
                for cue in cues:
                    cue.scale(fit)
            rows = []
            for cue, word, cell in zip(cues, words, grid["cells"]):
                zone_top = float(cell["top"])
                half = zone_top - float(grid["cell_h"]) * 0.50
                cx = (float(grid["left"]) + float(grid["right"])) / 2.0
                cue.move_to([cx, (zone_top + half) / 2.0, 0])
                if float(cue.get_top()[1]) > zone_top:
                    cue.shift(DOWN * (float(cue.get_top()[1]) - zone_top))
                text_top = min(half, float(cue.get_bottom()[1]) - 0.04)
                text_bot = float(cell["bottom"])
                word.move_to([cx, (text_top + text_bot) / 2.0, 0])
                rows.append(VGroup(cue, word))
            return rows

    def _wrapped(text: str, latin: str, cjk: str, size: int):
        raw = (text or "").strip() or " "
        parts: list[str] = []
        buf = ""
        limit = 18 if any("\u4e00" <= ch <= "\u9fff" for ch in raw) else 32
        for ch in raw:
            buf += ch
            if ch in ".!?。！？" and len(buf.strip()) > 6:
                parts.append(buf.strip())
                buf = ""
            elif ch == " " and len(buf) >= limit:
                parts.append(buf.strip())
                buf = ""
        if buf.strip():
            parts.append(buf.strip())
        lines = VGroup(*[styled(part, latin, cjk, size) for part in (parts or [raw])])
        lines.arrange(DOWN, buff=0.06, aligned_edge=LEFT)
        return lines

    def _mini_track(values, marked, latin: str):
        cells = VGroup()
        nums = VGroup()
        for value in values:
            box = RoundedRectangle(
                width=0.46, height=0.4, corner_radius=0.06,
                stroke_color=NAVY, stroke_width=2.5, fill_color=WHITE, fill_opacity=1,
            )
            num = Text(str(value), font=latin, font_size=18, color=NAVY)
            num.move_to(box)
            cells.add(box)
            nums.add(num)
        cells.arrange(RIGHT, buff=0.05)
        for num, box in zip(nums, cells):
            num.move_to(box)
        marker = RoundedRectangle(
            width=0.42, height=0.34, corner_radius=0.05,
            stroke_color=GOLD, stroke_width=4, fill_color=GOLD, fill_opacity=0.4,
        )
        marker.set_z_index(1)
        marker.move_to(cells[list(values).index(marked)])
        return VGroup(cells, nums, marker)

    def _takeaway_cue(motif: str, index: int, latin: str):
        if motif == "ten_frame":
            if index == 1:
                frames = VGroup(ten_cells(), ten_cells()).arrange(RIGHT, buff=0.12)
                frames.scale(0.28)
                return frames
            frame = ten_cells()
            frame.scale(0.32)
            return frame
        if motif == "track":
            if index == 0:
                return _mini_track(range(9, 13), 12, latin)
            if index == 1:
                return _mini_track(range(17, 21), 17, latin)
            return _mini_track([12, 11, 10, 9], 9, latin)
        if index == 2:
            tray = RoundedRectangle(
                width=1.3, height=0.7, corner_radius=0.1,
                stroke_color=NAVY, stroke_width=3, fill_color=WHITE, fill_opacity=1,
            )
            return tray
        n = 5 if index == 1 else 3
        dots = VGroup(*[counter(GREEN, 0.12) for _ in range(n)])
        dots.arrange(RIGHT, buff=0.08)
        return dots

    class NumberBlocks(_Board):
        """Tens bundles up to 100, a comparison, an order, a short hop, or equal groups."""

        def construct(self):
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            mode = str(labels.get("mode") or self.vf_mode or "tens")
            ph = int(getattr(config, "pixel_height", 0) or 0) or 1080
            pw = int(getattr(config, "pixel_width", 0) or 0) or 1920
            portrait = ph > pw
            title = self._label(labels.get("title") or "", latin, cjk)
            if mode == "compare":
                self._compare(labels, latin, cjk, portrait, title)
            elif mode == "order":
                self._order(labels, latin, cjk, portrait, title)
            elif mode == "hop":
                self._hop(labels, latin, cjk, title)
            elif mode == "groups":
                self._groups(labels, latin, cjk, portrait, title)
            else:
                self._tens(labels, latin, cjk, title)

        def _label(self, text, latin, cjk, scale=1.0):
            glyph = styled(str(text) if str(text).strip() else " ", latin, cjk, 64)
            target = _ordinal_label_height() * scale
            if float(glyph.height) > 0:
                glyph.scale(target / float(glyph.height))
            return glyph

        def _limits(self):
            left, right, bot, top = _safe_limits()
            return left, right, bot, top, right - left, top - bot

        def _fit_width(self, mob, max_w):
            if float(mob.width) > max_w > 0:
                mob.scale(max_w / float(mob.width))
            return mob

        def _seat(self, stack):
            left, right, bot, top, max_w, max_h = self._limits()
            self._fit_width(stack, max_w * 0.98)
            if float(stack.height) > max_h and float(stack.height) > 0:
                stack.scale(max_h / float(stack.height))
            stack.move_to([(left + right) / 2.0, (bot + top) / 2.0, 0])
            return stack

        def _rod(self, w, h):
            return RoundedRectangle(
                width=w,
                height=h,
                corner_radius=min(0.08, h * 0.12),
                stroke_color=NAVY,
                stroke_width=3,
                fill_color=GREEN,
                fill_opacity=1,
            )

        def _bundles(self, count, latin, cjk, *, rod_w, rod_h, cols, pair_ones=False, show_zero=True):
            tens, ones = divmod(int(count), 10)
            rods = VGroup(*[self._rod(rod_w, rod_h) for _ in range(tens)])
            if tens:
                used = min(cols, tens)
                rods.arrange_in_grid(rows=(tens + used - 1) // used, cols=used, buff=0.1)
            if ones:
                cube_r = _ordinal_label_height() * 0.62 if pair_ones else min(0.15, rod_h * 0.2)
                cubes = [counter(GOLD, cube_r) for _ in range(ones)]
                if pair_ones and ones >= 2:
                    bits = []
                    i = 0
                    while i + 1 < ones:
                        pair = VGroup(cubes[i], cubes[i + 1]).arrange(RIGHT, buff=0.12)
                        frame = RoundedRectangle(
                            width=float(pair.width) + 0.36,
                            height=float(pair.height) + 0.32,
                            corner_radius=0.1,
                            stroke_color=NAVY,
                            stroke_width=4,
                            fill_color=WHITE,
                            fill_opacity=1,
                        )
                        pair.move_to(frame)
                        bits.append(VGroup(frame, pair))
                        i += 2
                    if i < ones:
                        lone = cubes[i]
                        ring = SurroundingRectangle(lone, color=GOLD, buff=0.2, stroke_width=8)
                        ring.set_fill(opacity=0)
                        bits.append(VGroup(lone, ring))
                    loose = VGroup(*bits).arrange(RIGHT, buff=0.28)
                else:
                    loose = VGroup(*cubes).arrange(RIGHT, buff=0.08)
            elif show_zero:
                zero = self._label("0", latin, cjk)
                mat = RoundedRectangle(
                    width=max(float(zero.width) + 0.42, rod_w * 2.4),
                    height=float(zero.height) + 0.34,
                    corner_radius=0.1,
                    stroke_color=NAVY,
                    stroke_width=3,
                    fill_color=WHITE,
                    fill_opacity=1,
                )
                zero.move_to(mat)
                loose = VGroup(mat, zero)
            else:
                loose = VGroup()
            if tens and len(loose):
                pic = VGroup(rods, loose).arrange(DOWN, buff=0.16)
            elif tens:
                pic = rods
            else:
                pic = loose
            return pic, rods, loose

        def _show(self, index, *mobs):
            chosen = [mob for mob in mobs if mob is not None]
            if not chosen:
                self.spend(index)
                return
            self.spend_each(index, [lambda chosen=chosen: AnimationGroup(*[mob.animate.set_opacity(1) for mob in chosen])])

        def _tens(self, labels, latin, cjk, title):
            count = int(labels.get("count") or 0)
            rods_only = bool(labels.get("rods_only")) and count % 10 == 0
            pair_ones = bool(labels.get("pair_ones"))
            pic, rods, loose = self._bundles(
                count, latin, cjk, rod_w=0.46, rod_h=1.02, cols=5,
                pair_ones=pair_ones, show_zero=not rods_only,
            )
            number = self._label(str(count), latin, cjk, 1.4)
            left, right, bot, top, max_w, max_h = self._limits()
            room = max_h - float(title.height if not rods_only else 0) - float(number.height) - 0.7
            # A paired leftover has to stay at the label floor. Shorten the
            # rods instead of shrinking the pair and its ring.
            if pair_ones and len(rods) and len(loose) and room > float(loose.height) + 0.2:
                spare = room - float(loose.height) - 0.16
                if float(rods.height) > spare > 0.2:
                    rods.scale(spare / float(rods.height))
                    pic = VGroup(rods, loose).arrange(DOWN, buff=0.16)
            elif float(pic.height) > room > 0.4:
                pic.scale(room / float(pic.height))
            self._fit_width(pic, max_w * 0.96)
            shown = VGroup(pic, number) if rods_only else VGroup(title, pic, number)
            stack = self._seat(shown.arrange(DOWN, buff=0.2))
            rod_list = list(rods)
            fading = [loose, number, *rod_list] if rods_only else [title, loose, number, *rod_list]
            for mob in fading:
                mob.set_opacity(0)
            self.add(stack)
            marks = self.marks_for(0)
            if rod_list and marks and len(marks) == len(rod_list):
                hops = [lambda rod=rod: rod.animate.set_opacity(1) for rod in rod_list]
                intro = None if rods_only else title.animate.set_opacity(1)
                self.spend_marked(0, hops, marks, intro=intro)
            elif rods_only:
                self._show(0, *rod_list)
            else:
                self._show(0, title, *rod_list)
            if pair_ones and len(loose):
                def reveal_pairs(loose=loose, title=title):
                    # set_opacity would fill the leftover ring. Keep it a stroke.
                    loose.set_opacity(1)
                    for part in loose:
                        ring = part[-1] if len(part) else None
                        if isinstance(ring, SurroundingRectangle):
                            ring.set_fill(opacity=0)
                            ring.set_stroke(opacity=1)
                    return title.animate.set_opacity(1)

                self.spend_each(1, [reveal_pairs])
            elif len(loose):
                self._show(1, loose)
            else:
                self.spend(1)
            self._show(2, number)

        def _card(self, count, latin, cjk):
            pic, _rods, _loose = self._bundles(count, latin, cjk, rod_w=0.3, rod_h=0.58, cols=5)
            num = self._label(str(count), latin, cjk, 1.25)
            return VGroup(num, pic).arrange(DOWN, buff=0.12), num

        def _compare(self, labels, latin, cjk, portrait, title):
            a, b = int(labels.get("a") or 0), int(labels.get("b") or 0)
            left_card, left_num = self._card(a, latin, cjk)
            right_card, right_num = self._card(b, latin, cjk)
            pair = VGroup(left_card, right_card)
            pair.arrange(DOWN if portrait else RIGHT, buff=0.36 if portrait else 0.7)
            _left, _right, _bot, _top, max_w, max_h = self._limits()
            room = max_h - float(title.height) - 0.45
            if float(pair.height) > room > 0.4:
                pair.scale(room / float(pair.height))
            self._fit_width(pair, max_w * 0.96)
            stack = self._seat(VGroup(title, pair).arrange(DOWN, buff=0.24))
            winner = left_num if a > b else right_num
            ring = SurroundingRectangle(winner, color=GOLD, buff=0.12, stroke_width=7)
            for mob in (title, left_card, right_card):
                mob.set_opacity(0)
            self.add(stack)
            self._show(0, title, left_card)
            self._show(1, right_card)
            self.spend(2, Create(ring))

        def _order(self, labels, latin, cjk, portrait, title):
            values = [int(v) for v in (labels.get("values") or [])]
            cards = []
            for value in values:
                num = self._label(str(value), latin, cjk, 1.45)
                box = RoundedRectangle(
                    width=float(num.width) + 0.46,
                    height=float(num.height) + 0.38,
                    corner_radius=0.12,
                    stroke_color=NAVY,
                    stroke_width=4,
                    fill_color=WHITE,
                    fill_opacity=1,
                )
                num.move_to(box)
                cards.append(VGroup(box, num))
            row = VGroup(*cards)
            if portrait and len(cards) >= 4:
                row.arrange_in_grid(rows=2, cols=2, buff=0.24)
            else:
                row.arrange(RIGHT, buff=0.3)
            stack = self._seat(VGroup(title, row).arrange(DOWN, buff=0.36))
            for mob in (title, *cards):
                mob.set_opacity(0)
            self.add(stack)
            self._show(0, title, cards[0])
            middle = cards[1:-1]
            self._show(1, *middle)
            self._show(2, cards[-1])

        def _hop(self, labels, latin, cjk, title):
            start = int(labels.get("start") or 0)
            end = int(labels.get("end") or start)
            lo, hi = min(start, end), max(start, end)
            values = list(range(lo, hi + 1))
            sample = self._label(str(max(values, key=lambda n: len(str(n)))), latin, cjk)
            _left, _right, _bot, _top, max_w, _max_h = self._limits()
            gap = 0.12
            cell = max(float(sample.width) + 0.36, float(sample.height) + 0.32)
            row_w = cell * len(values) + gap * (len(values) - 1)
            if row_w > max_w * 0.96 and row_w > 0:
                cell *= (max_w * 0.96) / row_w
            boxes = {}
            grid = VGroup()
            for i, value in enumerate(values):
                box = RoundedRectangle(
                    width=cell,
                    height=cell * 0.86,
                    corner_radius=0.1,
                    stroke_color=NAVY,
                    stroke_width=3,
                    fill_color=WHITE,
                    fill_opacity=1,
                )
                num = self._label(str(value), latin, cjk)
                if float(num.width) > cell * 0.82:
                    num.scale(cell * 0.82 / float(num.width))
                if float(num.height) > cell * 0.62:
                    num.scale(cell * 0.62 / float(num.height))
                num.set_z_index(12)
                num.move_to(box)
                card = VGroup(box, num)
                card.move_to([(i - (len(values) - 1) / 2.0) * (cell + gap), 0, 0])
                boxes[value] = card
                grid.add(card)
            marker = RoundedRectangle(
                width=cell * 1.14,
                height=cell * 1.02,
                corner_radius=0.14,
                stroke_color=GOLD,
                stroke_width=8,
                fill_opacity=0,
            )
            marker.set_z_index(4)
            marker.set_fill(opacity=0)
            answer = self._label(str(end), latin, cjk, 1.4)
            body = VGroup(title, grid, answer).arrange(DOWN, buff=0.28)
            stack = self._seat(body)
            marker.move_to(boxes[start])
            answer.set_opacity(0)
            marker.set_stroke(opacity=0)
            title.set_opacity(0)
            self.add(stack, marker)
            self._show(0, title, grid)
            step_by = 1 if end >= start else -1
            visits = list(range(start, end + step_by, step_by))
            counted = self.marks_for(1)
            hops = [lambda: marker.animate.set_stroke(opacity=1)]
            for value in visits[1:]:
                dest = boxes[value].get_center().copy()
                hops.append(lambda dest=dest: marker.animate.move_to(dest))
            if counted and len(counted) == len(hops):
                self.spend_marked(1, hops, counted)
            else:
                self.spend_each(1, hops)
            self._show(2, answer)

        def _groups(self, labels, latin, cjk, portrait, title):
            size = max(2, int(labels.get("a") or 2))
            boxes_n = max(1, int(labels.get("n") or 1))
            extra = max(0, int(labels.get("extra") or 0))
            cols = group_columns(boxes_n, size, portrait)
            columns = []
            tags = []
            for i in range(boxes_n):
                dots = VGroup(*[counter(GREEN, 0.13) for _ in range(size)])
                dots.arrange(RIGHT, buff=0.07)
                pad = RoundedRectangle(
                    width=float(dots.width) + 0.32,
                    height=float(dots.height) + 0.3,
                    corner_radius=0.1,
                    stroke_color=NAVY,
                    stroke_width=3,
                    fill_color=WHITE,
                    fill_opacity=1,
                )
                dots.move_to(pad)
                tag = self._label(str((i + 1) * size), latin, cjk)
                columns.append(VGroup(VGroup(pad, dots), tag).arrange(DOWN, buff=0.1))
                tags.append(tag)
            used = min(cols, boxes_n)
            row = VGroup(*columns)
            row.arrange_in_grid(rows=(boxes_n + used - 1) // used, cols=used, buff=0.22)
            loose = None
            if extra:
                loose_dots = VGroup(*[counter(GOLD, 0.18) for _ in range(extra)])
                loose_dots.arrange(RIGHT, buff=0.16)
                ring = SurroundingRectangle(loose_dots, color=GOLD, buff=0.1, stroke_width=5)
                ring.set_fill(opacity=0)
                loose = VGroup(loose_dots, ring)
                loose.next_to(row, RIGHT if not portrait else DOWN, buff=0.28)
            total = self._label(str(size * boxes_n + extra), latin, cjk, 1.35)
            parts = [title, VGroup(row, loose) if loose is not None else row, total]
            stack = self._seat(VGroup(*parts).arrange(DOWN, buff=0.24))
            for mob in (title, total, *tags):
                mob.set_opacity(0)
            if loose is not None:
                loose[0].set_opacity(0)
                loose[1].set_fill(opacity=0)
                loose[1].set_stroke(opacity=0)
            self.add(stack)
            pads = [column[0] for column in columns]
            self._show(0, title, *pads)
            marks = self.marks_for(1)
            reveals = [lambda tag=tag: tag.animate.set_opacity(1) for tag in tags]
            if marks and len(marks) == len(reveals):
                self.spend_marked(1, reveals, marks)
            else:
                self.spend_each(1, reveals)
            if loose is None:
                self._show(2, total)
            else:
                dot, ring = loose[0], loose[1]

                def reveal_loose(dot=dot, ring=ring, total=total):
                    # The ring and the loose counter pop on this line. A
                    # grouped .animate would share one target and stay hidden.
                    dot.set_opacity(1)
                    ring.set_fill(opacity=0)
                    ring.set_stroke(opacity=1)
                    return total.animate.set_opacity(1)

                self.spend_each(2, [reveal_loose])

    class EstimateGroup(_Board):
        """One paced step. The ten-frame never sits on top of the pile."""

        def construct(self):
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            part = str(labels.get("part") or "pile")
            count = int(labels.get("count") or 23)
            tens, ones = divmod(count, 10)
            ph = int(getattr(config, "pixel_height", 0) or 0) or 1080
            pw = int(getattr(config, "pixel_width", 0) or 0) or 1920
            portrait = ph > pw
            left, right, bot, top = _safe_limits()
            cx = (left + right) / 2.0
            # Diameter matches the shared label floor, so a counter stays readable.
            radius = _ordinal_label_height() * 0.5
            cell = radius * 2.0 + 0.14

            def number(text):
                glyph = styled(str(text), latin, cjk, 64)
                target = _ordinal_label_height()
                if float(glyph.height) > 0:
                    glyph.scale(target / float(glyph.height))
                return glyph

            def make_frame():
                group = VGroup()
                for _ in range(10):
                    box = RoundedRectangle(
                        width=cell, height=cell, corner_radius=0.08,
                        stroke_color=NAVY, stroke_width=3, fill_color=WHITE, fill_opacity=1,
                    )
                    box.set_z_index(1)
                    group.add(box)
                group.arrange_in_grid(rows=2, cols=5, buff=0.07)
                return group

            title = number(labels.get("title") or "")
            max_w = (right - left) * 0.92
            if float(title.width) > max_w:
                title.scale(max_w / float(title.width))
            title.move_to([cx, top - float(title.height) / 2.0 - 0.06, 0])
            guide_num = number("10")
            guess_num = number(str(tens * 10))
            final_num = number(str(count))
            self.vf_title = title
            self.vf_answer = final_num
            self.vf_guess = guess_num

            frame1 = make_frame()
            frame2 = make_frame()
            if portrait:
                frames = VGroup(frame1, frame2).arrange(DOWN, buff=0.32)
            else:
                frames = VGroup(frame1, frame2).arrange(RIGHT, buff=0.4)
            body_top = float(title.get_bottom()[1]) - 0.2
            body_h = body_top - bot
            if portrait:
                frames.move_to([cx, body_top - float(frames.height) / 2.0, 0])
            else:
                frames.move_to([
                    left + float(frames.width) / 2.0 + 0.08,
                    bot + body_h * 0.58,
                    0,
                ])
            if float(frames.get_top()[1]) > body_top:
                frames.shift(DOWN * (float(frames.get_top()[1]) - body_top))
            if portrait:
                # The second frame is under the first, so "10" sits beside
                # its frame, clear of the gold outline, instead of on the next frame.
                guide_num.next_to(frame1, RIGHT, buff=0.34)
                over = float(guide_num.get_right()[0]) - (right - 0.04)
                if over > 0:
                    frames.shift(LEFT * over)
                    guide_num.shift(LEFT * over)
                guess_num.next_to(frame2, DOWN, buff=0.14)
            else:
                guide_num.next_to(frame1, DOWN, buff=0.12)
                guess_num.next_to(frame2, DOWN, buff=0.12)
            if float(guess_num.get_bottom()[1]) < bot + 0.02:
                guess_num.next_to(guide_num, RIGHT, buff=0.28)
            if float(guess_num.get_right()[0]) > right:
                guess_num.next_to(guide_num, DOWN, buff=0.08)

            ones_row = VGroup(*[counter(GREEN, radius) for _ in range(ones)])
            for dot in ones_row:
                dot.set_z_index(4)
            ones_row.arrange(RIGHT, buff=0.16)
            final_num.next_to(ones_row, DOWN, buff=0.12)
            block = VGroup(ones_row, final_num)
            block.move_to([cx, bot + float(block.height) / 2.0 + 0.04, 0])
            one_at = [dot.get_center().copy() for dot in ones_row]

            def zone_beside_frames():
                gap = 0.42
                if portrait:
                    zone_top = min(float(guide_num.get_bottom()[1]), float(guess_num.get_bottom()[1])) - gap
                    zone_bot = float(block.get_top()[1]) + gap
                    return left + 0.05, right - 0.05, zone_bot, zone_top
                zone_left = float(frames.get_right()[0]) + gap
                zone_top = body_top - 0.05
                zone_bot = float(block.get_top()[1]) + gap
                return zone_left, right - 0.05, zone_bot, zone_top

            zx0, zx1, zy0, zy1 = zone_beside_frames()
            pile_w = max(radius * 4, zx1 - zx0)
            pile_h = max(radius * 4, zy1 - zy0)
            # Spots are centred, then shifted into the zone that is not the frames.
            cloud = messy_spots(count, pile_w * 0.92, pile_h * 0.9, radius * 2.35)
            anchor_x = (zx0 + zx1) / 2.0
            anchor_y = (zy0 + zy1) / 2.0
            pile_at = [(anchor_x + x, anchor_y + y) for x, y in cloud]
            if pile_at:
                low = min(y for _x, y in pile_at)
                high = max(y for _x, y in pile_at)
                west = min(x for x, _y in pile_at)
                east = max(x for x, _y in pile_at)
                shift_x = 0.0
                shift_y = 0.0
                if west < zx0 + radius:
                    shift_x = zx0 + radius - west
                if east + shift_x > zx1 - radius:
                    shift_x -= (east + shift_x) - (zx1 - radius)
                if low < zy0 + radius:
                    shift_y = zy0 + radius - low
                if high + shift_y > zy1 - radius:
                    shift_y -= (high + shift_y) - (zy1 - radius)
                pile_at = [(x + shift_x, y + shift_y) for x, y in pile_at]

            dots = VGroup(*[counter(GREEN, radius) for _ in range(count)])
            for dot in dots:
                dot.set_z_index(4)
            self.vf_dots = dots
            self.vf_frame = frame1
            self.vf_frame2 = frame2
            cell1 = [box.get_center().copy() for box in frame1]
            cell2 = [box.get_center().copy() for box in frame2]

            # The opening pile uses the middle of the safe area, with no frame.
            open_w = (right - left) * (0.78 if portrait else 0.62)
            open_h = max(radius * 4, (body_top - bot) * (0.62 if portrait else 0.7))
            open_cloud = messy_spots(count, open_w, open_h, radius * 2.4)
            open_at = [(cx + x, (bot + body_top) / 2.0 + y) for x, y in open_cloud]

            def put(dot, spot):
                dot.move_to([spot[0], spot[1], 0])

            halo = SurroundingRectangle(frame1, color=GOLD, buff=0.1, stroke_width=6)
            halo.set_fill(opacity=0)
            halo.set_stroke(opacity=0)
            halo.set_z_index(3)

            show_frames = part != "pile"
            grouped = part in {"guess", "count", "close"}
            second = part == "close"
            for i, dot in enumerate(dots):
                if part == "pile":
                    put(dot, open_at[i])
                elif i < 10 and grouped:
                    put(dot, (cell1[i][0], cell1[i][1]))
                elif i < 20 and second:
                    put(dot, (cell2[i - 10][0], cell2[i - 10][1]))
                elif i >= 20 and second:
                    put(dot, (one_at[i - 20][0], one_at[i - 20][1]))
                else:
                    put(dot, pile_at[i])

            hidden = []
            if not show_frames:
                hidden.extend([frame1, frame2, guide_num, guess_num, final_num, halo])
            else:
                if not second:
                    hidden.append(frame2)
                if part == "ten":
                    hidden.extend([guess_num, final_num, halo])
                elif part == "guess":
                    hidden.extend([guess_num, final_num, halo])
                elif part == "count":
                    hidden.extend([final_num, halo])
            for mob in hidden:
                mob.set_opacity(0)
            self.add(title, dots, frame1, frame2, guide_num, guess_num, final_num, halo)
            # Ones-row placeholders are the same counters, already in `dots`.
            # Drop the extra row so it cannot sit under the picture.
            title.set_opacity(0 if part == "pile" else 1)
            if part != "pile":
                dots.set_opacity(1)
                if show_frames:
                    frame1.set_opacity(1)
                    if part != "ten":
                        guide_num.set_opacity(1)
                if part in {"count", "close"}:
                    guess_num.set_opacity(1)
                if part == "close":
                    frame2.set_opacity(1)
                    final_num.set_opacity(1)

            if part == "pile":
                total = float((self.vf_durations or [1.0])[0] or 0)
                fps = max(float(config.frame_rate or 15), 1.0)
                frame_t = 1.0 / fps
                fade = min(0.5, max(frame_t, total * 0.28))
                if total <= frame_t:
                    title.set_opacity(1)
                    dots.set_opacity(1)
                    return
                self.play(
                    title.animate.set_opacity(1),
                    dots.animate.set_opacity(1),
                    run_time=min(fade, total),
                )
                rest = total - min(fade, total)
                if rest > frame_t / 2:
                    self.wait(rest)
                return

            if part == "ten":
                guide_num.set_opacity(0)
                moves = [dots[i].animate.move_to(cell1[i]) for i in range(min(10, count))]
                self.spend(0, AnimationGroup(*moves), guide_num.animate.set_opacity(1))
                return

            if part == "guess":
                self.spend(0, guess_num.animate.set_opacity(1))
                return

            if part == "close":
                self.spend(0)
                return

            def hop_ten():
                return halo.animate.set_stroke(opacity=1)

            def hop_twenty():
                moves = [dots[10 + k].animate.move_to(cell2[k]) for k in range(min(10, count - 10))]
                return AnimationGroup(frame2.animate.set_opacity(1), *moves)

            def hop_one(j):
                def play(j=j):
                    shown = [dots[20 + j].animate.move_to(one_at[j])]
                    if j == ones - 1:
                        shown.append(final_num.animate.set_opacity(1))
                    return AnimationGroup(*shown)
                return play

            hops = [hop_ten, hop_twenty] + [hop_one(j) for j in range(ones)]
            self.spend_marked(0, hops, self.marks_for(0))

    class RowMatch(_Board):
        """Two rows, matched one to one, then the unmatched counters."""

        def construct(self):
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            part = str(labels.get("part") or "rows")
            a = int(labels.get("a") or 0)
            b = int(labels.get("b") or 0)
            left, right, bot_lim, top_lim = _safe_limits()
            radius = _ordinal_label_height() * 0.5
            gap = radius * 0.7

            def glyph(text, scale=1.0):
                mob = styled(str(text), latin, cjk, 64)
                target = _ordinal_label_height() * scale
                if float(mob.height) > 0:
                    mob.scale(target / float(mob.height))
                return mob

            def make_row(n, color):
                dots = VGroup(*[counter(color, radius) for _ in range(n)])
                if n > 1:
                    dots.arrange(RIGHT, buff=gap)
                return dots

            top = make_row(a, GREEN)
            bottom = make_row(b, GOLD)
            if a and b:
                bottom.next_to(top, DOWN, buff=radius * 2.4)
                bottom.align_to(top, LEFT)
            lines = VGroup()
            for i in range(min(a, b)):
                line = Line(
                    top[i].get_center(), bottom[i].get_center(),
                    color=GOLD, stroke_width=6,
                )
                lines.add(line)
            longer = top if a >= b else bottom
            rings = VGroup()
            for i in range(min(a, b), max(a, b)):
                ring = Circle(radius=radius * 1.18, color=GOLD, stroke_width=6)
                ring.set_fill(opacity=0)
                ring.move_to(longer[i].get_center())
                rings.add(ring)
            rows = VGroup(top, bottom)
            answer = glyph(str(abs(a - b)), 1.45)
            anchor = rows if len(rows) else answer
            answer.next_to(anchor, DOWN, buff=0.32)
            title = glyph(str(labels.get("title") or " "), 1.05)
            picture = VGroup(rows, lines, rings, answer)
            title.next_to(picture, UP, buff=0.28)
            group = VGroup(title, picture)
            max_w = (right - left) * 0.96
            max_h = (top_lim - bot_lim) * 0.96
            if float(group.width) > max_w > 0:
                group.scale(max_w / float(group.width))
            if float(group.height) > max_h > 0:
                group.scale(max_h / float(group.height))
            group.move_to([(left + right) / 2.0, (bot_lim + top_lim) / 2.0, 0])
            self.vf_title = title
            self.vf_top = top
            self.vf_bottom = bottom
            self.vf_lines = lines
            self.vf_rings = rings
            self.vf_answer = answer
            show_rings = part in {"gap", "hold"} and len(rings)
            show_number = part in {"hold", "equal"} or (part == "gap" and abs(a - b) == 0)
            title.set_opacity(0)
            for dot in list(top) + list(bottom):
                dot.set_opacity(0)
            for line in lines:
                line.set_stroke(opacity=0)
            for ring in rings:
                ring.set_stroke(opacity=0)
            answer.set_opacity(0)
            self.add(group)
            if part == "rows":
                title.set_opacity(1)
                for dot in list(top) + list(bottom):
                    dot.set_opacity(1)
                self.spend(0)
                return
            for dot in list(top) + list(bottom):
                dot.set_opacity(1)
            title.set_opacity(1)
            if part == "match":
                self.spend(0, *[line.animate.set_stroke(opacity=1) for line in lines])
                return
            for line in lines:
                line.set_stroke(opacity=1)
            if part == "gap" and len(rings):
                def reveal(i):
                    def play(i=i):
                        shown = [rings[i].animate.set_stroke(opacity=1)]
                        if i == len(rings) - 1:
                            shown.append(answer.animate.set_opacity(1))
                        return AnimationGroup(*shown)
                    return play
                self.spend_marked(0, [reveal(i) for i in range(len(rings))], self.marks_for(0))
                return
            if show_rings:
                for ring in rings:
                    ring.set_stroke(opacity=1)
            if part in {"hold", "equal"} or show_number:
                answer.set_opacity(1)
            self.spend(0)

    _scene_types._cache = {
        "one_ten": OneTen,
        "ten_and_ones": TenAndOnes,
        "make_ten": MakeTen,
        "count_objects": CountObjects,
        "number_track": NumberTrack,
        "ordinal_row": OrdinalRow,
        "pair_counters": PairCounters,
        "part_whole": PartWhole,
        "number_blocks": NumberBlocks,
        "estimate_group": EstimateGroup,
        "row_match": RowMatch,
        "lesson_hook": LessonHook,
        "lesson_takeaway": LessonTakeaway,
    }
    return _scene_types._cache


def _write_caption_overlay(text: str, dest: Path, frame: tuple[int, int]) -> Path:
    w, h = int(frame[0]), int(frame[1])
    if (w, h) == (1920, 1080):
        from mux import _caption_card

        return _caption_card(text, dest)
    from PIL import Image, ImageDraw

    from mux import CAPTION_PAD_X, CAPTION_VERTICAL_PAD
    from slides import draw_mixed, mixed_length

    portrait = h > w
    size = 42 if portrait or h >= 720 else max(18, int(42 * h / 1080))
    if portrait:
        pill_max = int(w * 0.86)
        bottom = max(36, int(h * 0.03))
    else:
        pill_max = min(int(1180 * w / 1920), int(w * 0.86))
        bottom = max(12, int(28 * h / 1080))
    pad_x, pad_y = CAPTION_PAD_X, CAPTION_VERTICAL_PAD
    max_w = max(80, pill_max - 2 * pad_x)
    raw = (text or "").strip() or " "
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()] or [" "]
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    while size > 16 and any(mixed_length(probe, ln, size) > max_w for ln in lines):
        size -= 2
    line_h = max(22, int(size * 1.28))
    text_w = max(mixed_length(probe, ln, size) for ln in lines)
    pill_w = int(min(pill_max, max(160, text_w + 2 * pad_x)))
    pill_h = int(2 * pad_y + line_h * len(lines))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x0 = (w - pill_w) // 2
    y0 = h - pill_h - bottom
    draw.rounded_rectangle([x0, y0, x0 + pill_w, y0 + pill_h], radius=18, fill=(16, 15, 10, 184))
    y = y0 + pad_y
    for ln in lines:
        tw = mixed_length(draw, ln, size)
        draw_mixed(draw, (x0 + (pill_w - tw) / 2, y), ln, size, (255, 255, 255, 255), False)
        y += line_h
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def _mux(video, audio, pages, holds, dest, frame, fps, total, progress_bar: bool) -> None:
    from ff import atomic_replace, check_call
    from mux import CLIP_A, clip_v_args

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    w, h = int(frame[0]), int(frame[1])
    overlay_dir = dest.parent / f".cap-{dest.stem}"
    if overlay_dir.exists():
        shutil.rmtree(overlay_dir, ignore_errors=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlays: list[Path] = []
    spans: list[tuple[float, float]] = []
    t = 0.0
    for i, (page, hold) in enumerate(zip(pages, holds)):
        hold = max(float(hold), 0.0)
        start, end = t, t + hold
        t = end
        if hold <= 0:
            continue
        png = overlay_dir / f"{i:02d}.png"
        _write_caption_overlay(page, png, (w, h))
        overlays.append(png)
        spans.append((start, end))
    cmd: list[str] = ["-y", "-i", str(video), "-i", str(audio)]
    for png in overlays:
        cmd += ["-loop", "1", "-i", str(png)]
    pad = max(total, 0.05) + 1.0
    parts = [
        f"[0:v]scale={w}:{h}:flags=bicubic,fps={int(fps)},setsar=1,format=yuv420p,"
        f"tpad=stop_mode=clone:stop_duration={pad:.3f}[base]"
    ]
    current = "base"
    for i, (start, end) in enumerate(spans):
        parts.append(f"[{i + 2}:v]format=rgba[ov{i}]")
        nxt = f"c{i}"
        parts.append(
            f"[{current}][ov{i}]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[{nxt}]"
        )
        current = nxt
    if progress_bar and total > 0:
        parts.append(f"color=c=0xC4A35A@0.28:s={w}x8:d={total + 1:.3f},format=rgba[rail]")
        parts.append(f"color=c=0xC4A35A:s={w}x8:d={total + 1:.3f},format=rgba[gold]")
        parts.append(f"[{current}][rail]overlay=0:0[vrail]")
        parts.append(f"[vrail][gold]overlay=x='-{w}+{w}*t/{total:.3f}':y=0[vout]")
        vout = "vout"
    else:
        parts.append(f"[{current}]format=yuv420p[vout]")
        vout = "vout"
    tmp = dest.with_suffix(".tmp.mp4")
    cmd += [
        "-filter_complex",
        ";".join(parts),
        "-map",
        f"[{vout}]",
        "-map",
        "1:a:0",
        "-af",
        f"aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur={total:.3f}",
        *clip_v_args(),
        *CLIP_A,
        "-t",
        f"{total:.3f}",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    try:
        check_call(cmd, timeout=300)
    finally:
        shutil.rmtree(overlay_dir, ignore_errors=True)
    atomic_replace(tmp, dest)


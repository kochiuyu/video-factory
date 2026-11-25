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
    scene_problems,
    scene_spec,
    ordinal_visits,
    schedule_marks,
    step_count,
    track_columns,
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
            "motion": 4,
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

    def _token_row(n: int, mark: int, cell: float = 0.46):
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
        cols = n if n <= 6 else (6 if n <= 12 else 5)
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

    def _ordinal_cue(n: int, mark: int, kind: str, latin: str, cjk: str, word: str = "", total: str = "", label_frac: float = 0.85):
        """A takeaway or hook picture of the same row. ``kind`` is hook, total, left, right, or both."""
        token_cell = 0.42
        board, tokens = _token_row(n, mark, token_cell)
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
        parts = VGroup(*[Text(tok, font=latin, font_size=size, color=NAVY) for tok in tokens])
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
                self.spend(index, LaggedStart(*moves, lag_ratio=0.85))
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
                num = Text(str(i + 1), font=latin, font_size=28, color=WHITE)
                if num.width > radius * 1.35:
                    num.scale(radius * 1.35 / num.width)
                num.set_z_index(4)
                if mode != "rearrange":
                    num.set_opacity(0)
                dot.move_to([starts[i][0], starts[i][1], 0])
                num.move_to(dot)
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
            # a sideways move. A narrow frame snakes: the next number sits
            # beside the previous one, including the turn onto the next row.
            pw = int(getattr(config, "pixel_width", 0) or 1920)
            ph = int(getattr(config, "pixel_height", 0) or 1080)
            cols = track_columns(len(values), pw, ph)
            gap = 0.08
            usable = float(config.frame_width) - 1.15
            cell = min(0.82, max(0.34, (usable - gap * (cols - 1)) / cols))
            row_gap = cell * 0.34
            slots: dict[int, tuple[int, int]] = {}
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
            foot_items = [answer, step]
            if cross is not None and crosses:
                foot_items.append(cross)
            foot = VGroup(*foot_items).arrange(RIGHT, buff=0.26)
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
            cols = track_columns(n, pw, ph, min_cell=0.46)
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
            for word, index in zip(words, visits):
                tag = styled(word, latin, cjk, 48)
                tag.scale(label_scale)
                # Landscape only. Portrait already reserved 16px between labels.
                if ph <= pw and float(tag.width) > pitch * 0.96:
                    tag.scale(pitch * 0.96 / float(tag.width))
                tag.next_to(tokens[index], UP, buff=0.12)
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
            if motif == "ordinal" and portrait:
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
                title.next_to(kicker, DOWN, buff=0.28)
                cue.next_to(title, DOWN, buff=0.4)
                settle(VGroup(kicker, title, cue))
            total = float((self.vf_durations or [2.0])[0] or 0)
            fps = max(float(config.frame_rate or 15), 1.0)
            frame = 1.0 / fps
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

        def _hook_cue(self, motif: str, latin: str, cjk: str, labels: dict | None = None):
            if motif == "ordinal":
                info = labels or {}
                n = max(1, int(info.get("n") or 6))
                mark = max(1, min(n, int(info.get("mark") or 3)))
                return _ordinal_cue(n, mark, "hook", latin, cjk)
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
            if len(lines) >= 4 and motif == "counters":
                self._counted_recap(title, lines, latin, cjk)
                return
            if len(lines) >= 4 and motif == "ten_frame":
                self._ten_recap(title, lines, latin, cjk)
                return
            if motif == "ordinal":
                self._ordinal_recap(title, lines, latin, cjk)
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

        def _place_heading(self, heading, grid: dict) -> None:
            """Same heading size in every language: the probe title sets the scale."""
            latin = self.vf_fonts[0]
            ref = Text(TAKEAWAY_HEADING_PROBE, font=latin, font_size=48, color=NAVY)
            band = float(grid["heading_h"])
            safe_w = float(grid["right"] - grid["left"])
            scale = (band * 0.52) / float(ref.height) if float(ref.height) else 1.0
            if float(ref.width) * scale > safe_w * 0.92:
                scale = (safe_w * 0.92) / float(ref.width)
            heading.scale(scale)
            cx = (float(grid["left"]) + float(grid["right"])) / 2.0
            cy = float(grid["top"]) - band / 2.0
            heading.move_to([cx, cy, 0])

        def _layout_takeaway(self, heading, cues, lines, latin: str, cjk: str) -> list:
            """Put each cue and its sentence into an equal row cell."""
            pw = int(getattr(config, "pixel_width", 0) or 0) or 1920
            ph = int(getattr(config, "pixel_height", 0) or 0) or 1080
            grid = takeaway_grid(pw, ph, len(lines))
            self._place_heading(heading, grid)
            font = self._body_font(latin, grid)
            portrait = bool(grid["portrait"])
            words = [
                self._line_group(text, latin, cjk, font, float(grid["text_w"]) * 0.96, portrait)
                for text in lines
            ]
            if portrait:
                zone = float(grid["cell_h"]) * (1.0 - TAKEAWAY_PORTRAIT_VISUAL) * 0.92
                tallest = max(float(word.height) for word in words)
                if tallest > zone > 0:
                    shrink = zone / tallest
                    for word in words:
                        word.scale(shrink)
            rows = []
            for cue, word, cell in zip(cues, words, grid["cells"]):
                if portrait:
                    vis_h = float(grid["cell_h"]) * TAKEAWAY_PORTRAIT_VISUAL * 0.88
                    vis_w = float(grid["vis_w"]) * 0.92
                else:
                    vis_h = float(grid["cell_h"]) * float(grid["visual_of_cell"])
                    # 40px at 1080p, plus a few pixels so a stroke still clears the column.
                    gutter = (TAKEAWAY_COLUMN_GAP_PX + 6) * 8.0 / 1080.0
                    vis_w = max(0.4, float(grid["vis_w"]) - 2.0 * gutter)
                if float(cue.width) > 0 and float(cue.height) > 0:
                    cue.scale(min(vis_w / float(cue.width), vis_h / float(cue.height)))
                if portrait:
                    zone_top = float(cell["top"])
                    zone_bot = zone_top - float(grid["cell_h"]) * TAKEAWAY_PORTRAIT_VISUAL
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
                num = Text(str(i + 1), font=latin, font_size=28, color=WHITE)
                if float(num.width) > float(dot.width) * 0.72:
                    num.scale(float(dot.width) * 0.72 / float(num.width))
                num.move_to(dot)
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
            cues = [
                _ordinal_cue(n, mark, "total", latin, cjk, total=total, label_frac=label_frac),
                _ordinal_cue(n, mark, "left", latin, cjk, word=left, label_frac=label_frac),
                _ordinal_cue(n, mark, "right", latin, cjk, word=right, label_frac=label_frac),
                _ordinal_cue(n, mark, "both", latin, cjk, total=total, label_frac=label_frac),
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

    _scene_types._cache = {
        "one_ten": OneTen,
        "ten_and_ones": TenAndOnes,
        "make_ten": MakeTen,
        "count_objects": CountObjects,
        "number_track": NumberTrack,
        "ordinal_row": OrdinalRow,
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


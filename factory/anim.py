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
    schedule_marks,
    step_count,
    track_columns,
)

CREAM = "#F7F4EE"
NAVY = "#0B1F3A"
GREEN = "#1F8A4C"
GOLD = "#E0A83A"
WHITE = "#FFFFFF"

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
            "motion": 2,
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
        RoundedRectangle,
        Scene,
        SurroundingRectangle,
        Text,
        VGroup,
        config,
    )

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
            cue = self._hook_cue(motif, latin, cjk)
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

        def _hook_cue(self, motif: str, latin: str, cjk: str):
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
            title = styled(labels.get("title") or "", latin, cjk, 40)
            rows = []
            for i, line in enumerate(labels.get("lines") or ["", "", ""]):
                cue = _takeaway_cue(motif, i, latin)
                words = _wrapped(str(line or " "), latin, cjk, 30)
                row = VGroup(cue, words).arrange(RIGHT, buff=0.28)
                rows.append(row)
            stack = VGroup(*rows).arrange(DOWN, buff=0.32, aligned_edge=LEFT)
            title.next_to(stack, UP, buff=0.36)
            board = VGroup(title, stack)
            board.move_to(UP * 0.1)
            settle(board)
            self.spend(0, FadeIn(title), FadeIn(rows[0]))
            self.spend(1, FadeIn(rows[1]))
            self.spend(2, FadeIn(rows[2]))

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


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

# Three authored motions per scene. Each one is one s1 / s2 / s3 narration line.
STEP_COUNTS = {"one_ten": 4, "ten_and_ones": 3, "make_ten": 3}
SCENES = tuple(STEP_COUNTS)

CREAM = "#F7F4EE"
NAVY = "#0B1F3A"
GREEN = "#1F8A4C"
GOLD = "#E0A83A"
WHITE = "#FFFFFF"

_FONTS: tuple[str, str] | None = None


class ManimNotInstalled(RuntimeError):
    """Raised only when a lesson actually asks for an animated scene."""


def label_lang(lang: str) -> str:
    """Slide-label language: en, zh (简体), or zh_hk (繁體)."""
    key = str(lang or "en").strip().lower().replace("-", "_")
    if key in {"zh_hk", "hk", "yue", "zh_yue"}:
        return "zh_hk"
    if key in {"zh", "zh_cn", "zhcn", "zh_hans", "cmn"}:
        return "zh"
    return "en"


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


def step_count(beat: dict) -> int:
    scene = str((beat or {}).get("scene") or "").strip()
    return STEP_COUNTS.get(scene, 3)


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


def _copy(lang: str) -> dict[str, str]:
    table = {
        "en": {
            "ten_title": "A ten and some ones",
            "one_ten": "one ten",
            "two_tens": "two tens",
            "ones": "{n} ones",
            "make_title": "Make ten",
            "full_frame": "A full frame is one ten",
        },
        "zh": {
            "ten_title": "一个十和一些一",
            "one_ten": "一个十",
            "two_tens": "两个十",
            "ones": "{n}个一",
            "make_title": "凑成十",
            "full_frame": "满框就是一个十",
        },
        "zh_hk": {
            "ten_title": "一個十和一些一",
            "one_ten": "一個十",
            "two_tens": "兩個十",
            "ones": "{n}個一",
            "make_title": "湊成十",
            "full_frame": "滿框就係一個十",
        },
    }
    return table[label_lang(lang)]


def labels_for(beat: dict, lang: str) -> dict:
    """On-screen strings for one language. Digits stay in the equation."""
    copy = _copy(lang)
    scene = str(beat.get("scene") or "").strip()
    if scene == "make_ten":
        a = int(beat.get("a"))
        b = int(beat.get("b"))
        move = 10 - a
        rest = b - move
        return {
            "title": copy["make_title"],
            "equation1": [str(a), "+", str(move), "=", "10"],
            "equation2": ["10", "+", str(rest), "=", str(a + b)],
        }
    if scene == "one_ten":
        count = int(beat.get("count"))
        ones = 0 if count >= 20 else max(0, count - 10)
        return {
            "title": copy["full_frame"],
            "one_ten": copy["one_ten"],
            "ones": copy["ones"].format(n=ones) if ones else "",
        }
    count = int(beat.get("count"))
    ones = 0 if count >= 20 else max(0, count - 10)
    if count >= 20:
        equation = ["20", "=", "10", "+", "10"]
        ten_label = copy["two_tens"]
    elif ones == 0:
        equation = ["10", "=", "10", "+", "0"]
        ten_label = copy["one_ten"]
    else:
        equation = [str(count), "=", "10", "+", str(ones)]
        ten_label = copy["one_ten"]
    return {
        "title": copy["ten_title"],
        "one_ten": ten_label,
        "ones": copy["ones"].format(n=ones) if ones else "",
        "equation": equation,
    }


def scene_spec(beat: dict, lang: str) -> dict:
    scene = str(beat.get("scene") or "").strip()
    spec: dict = {"scene": scene, "lang": label_lang(lang)}
    if scene in {"one_ten", "ten_and_ones"}:
        spec["count"] = int(beat.get("count"))
    elif scene == "make_ten":
        spec["a"] = int(beat.get("a"))
        spec["b"] = int(beat.get("b"))
    spec["labels"] = labels_for(beat, lang) if scene in SCENES else {}
    return spec


def cache_key(spec: dict, durations: list[float], lang: str, frame: tuple[int, int], manim_version: str) -> str:
    return digest_obj(
        {
            "spec": spec,
            "durations": [round(float(d), 3) for d in durations],
            "lang": label_lang(lang),
            "frame": [int(frame[0]), int(frame[1])],
            "manim": str(manim_version),
        }
    )


def _filled(beat: dict, suffix: str, n: int) -> list[str]:
    missing = []
    for i in range(1, n + 1):
        key = f"s{i}_{suffix}"
        if not str(beat.get(key) or "").strip():
            missing.append(key)
    return missing


def scene_problems(beat: dict) -> list[str]:
    """Schema errors for one animated beat. Does not import Manim."""
    if str(beat.get("visual") or "") != "animated":
        return []
    problems: list[str] = []
    scene = str(beat.get("scene") or "").strip()
    if scene not in STEP_COUNTS:
        problems.append(f"animated scene must be one_ten, ten_and_ones, or make_ten, not {scene!r}.")
        return problems
    n = STEP_COUNTS[scene]
    for suffix, name in (("en", "English"), ("zh", "简体")):
        missing = _filled(beat, suffix, n)
        if missing:
            problems.append(f"animated {scene} needs {name} lines {', '.join(missing)} (one per step).")
    hk_keys = [k for k in beat if "zh_hk" in str(k) and str(beat.get(k) or "").strip()]
    if hk_keys:
        missing = _filled(beat, "zh_hk", n)
        if missing:
            problems.append(f"animated {scene} needs Cantonese lines {', '.join(missing)} (one per step).")
    if scene in {"one_ten", "ten_and_ones"}:
        try:
            count = int(beat.get("count"))
        except (TypeError, ValueError):
            count = None
        if count is None or not 10 <= count <= 20:
            problems.append(f"{scene} count must be an integer from 10 to 20.")
    else:
        try:
            a = int(beat.get("a"))
            b = int(beat.get("b"))
        except (TypeError, ValueError):
            a = b = None
        if a is None or b is None or not (1 <= a <= 9 and 1 <= b <= 12 and (10 - a) <= b and a + b <= 20):
            problems.append("make_ten needs a from 1 to 9 and enough b to fill the ten without passing 20.")
    return problems


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
) -> str:
    from mux import clip_fps

    frame = frame or frame_size(lesson)
    durs = step_durations(holds, still_idx, step_count(beat))
    return digest_obj(
        {
            "silent": cache_key(scene_spec(beat, label), durs, label, frame, _manim_version()),
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
    spec = scene_spec(beat, label_lang_code)
    key = cache_key(spec, durs, label_lang_code, frame, _manim_version())
    silent = _silent_path(cache_dir, label_lang_code, str(beat.get("id") or "beat"), key)
    if not silent.is_file() or silent.stat().st_size < 256:
        silent.parent.mkdir(parents=True, exist_ok=True)
        print(
            f"anim: render {beat.get('id')} {label_lang(label_lang_code)} "
            f"{frame[0]}x{frame[1]} steps {', '.join(f'{d:.2f}s' for d in durs)}",
            flush=True,
        )
        _render_silent(beat, spec, durs, frame, fps, silent)
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


def _render_silent(beat, spec, durs, frame, fps, dest: Path) -> None:
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
            scene = _make_scene(spec, durs)
            scene.render(preview=False)
            movie = Path(scene.renderer.file_writer.movie_file_path)
        if not movie.is_file():
            found = list(Path(tmp).rglob("*.mp4"))
            if not found:
                raise RuntimeError(f"Manim did not write a movie for {beat.get('id')}")
            movie = found[0]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(movie, dest)


def _make_scene(spec: dict, durs: list[float]):
    classes = _scene_types()
    scene_name = spec.get("scene")
    cls = classes[scene_name]
    scene = cls()
    scene.vf_durations = list(durs)
    scene.vf_labels = spec.get("labels") or {}
    scene.vf_fonts = (latin_family(), cjk_family(str(spec.get("lang") or "en")))
    scene.vf_count = int(spec.get("count") or 13)
    scene.vf_a = int(spec.get("a") or 9)
    scene.vf_b = int(spec.get("b") or 8)
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

    def counter(color: str):
        from manim import Circle

        dot = Circle(radius=0.28, stroke_color=NAVY, stroke_width=2.5, fill_color=color, fill_opacity=1)
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

    class TenAndOnes(_Board):
        def construct(self):
            count = max(10, min(20, int(self.vf_count)))
            labels = self.vf_labels
            latin, cjk = self.vf_fonts
            frames_n = 2 if count >= 20 else 1
            ones_n = 0 if count >= 20 else count - 10
            frames = VGroup(*[ten_cells() for _ in range(frames_n)]).arrange(RIGHT, buff=0.4)
            cells = [cell for frame in frames for cell in frame]
            dots = VGroup(*[counter(GREEN) for _ in range(count)])
            for i, dot in enumerate(dots):
                if i < len(cells):
                    dot.move_to(cells[i].get_center())
            extras = [dots[i] for i in range(len(cells), len(dots))]
            portrait = config.frame_width < config.frame_height
            gap = 0.72
            if extras:
                span = (len(extras) - 1) * gap
                if portrait:
                    origin = frames.get_bottom() + DOWN * 0.75
                    for i, dot in enumerate(extras):
                        dot.move_to(origin + RIGHT * (i * gap - span / 2))
                else:
                    origin = frames.get_right() + RIGHT * 0.75
                    for i, dot in enumerate(extras):
                        dot.move_to(origin + DOWN * (i * gap - span / 2))
            title = styled(labels.get("title") or "", latin, cjk, 40)
            ten_label = styled(labels.get("one_ten") or "", latin, cjk, 34)
            ten_label.next_to(frames, DOWN, buff=0.22)
            ones_label = styled(labels.get("ones") or " ", latin, cjk, 34) if ones_n else None
            if ones_label is not None and extras:
                lowest = min(extras, key=lambda dot: float(dot.get_center()[1]))
                ones_label.next_to(lowest, DOWN, buff=0.36)
            eq = equation(list(labels.get("equation") or [str(count)]), latin)
            anchor = VGroup(ten_label, ones_label) if ones_label is not None else ten_label
            eq.next_to(anchor, DOWN, buff=0.32)
            span = [frames, *extras] if extras else [frames]
            title.move_to([_span_x(*span), float(frames.get_top()[1]) + 0.35 + float(title.height) / 2, 0])
            board = VGroup(title, frames, dots, ten_label, eq)
            if ones_label is not None:
                board.add(ones_label)
            settle(board)
            targets = [dot.get_center().copy() for dot in dots]
            left = frames.get_left() + LEFT * 1.3
            for i, dot in enumerate(dots):
                col = i % 4
                row = i // 4
                dot.move_to(left + RIGHT * col * 0.34 + DOWN * row * 0.36)
            self.add(frames, dots)
            moves = [dot.animate.move_to(target) for dot, target in zip(dots, targets)]
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
            if extras:
                span = (len(extras) - 1) * gap
                if portrait:
                    origin = cells.get_bottom() + DOWN * 0.75
                    for i, dot in enumerate(extras):
                        dot.move_to(origin + RIGHT * (i * gap - span / 2))
                else:
                    origin = cells.get_right() + RIGHT * 0.75
                    for i, dot in enumerate(extras):
                        dot.move_to(origin + DOWN * (i * gap - span / 2))
            title = styled(labels.get("title") or "", latin, cjk, 40)
            ten_label = styled(labels.get("one_ten") or "", latin, cjk, 34)
            ten_label.next_to(cells, DOWN, buff=0.22)
            ones_label = styled(labels.get("ones") or " ", latin, cjk, 34) if ones_n else None
            if ones_label is not None and extras:
                lowest = min(extras, key=lambda dot: float(dot.get_center()[1]))
                ones_label.next_to(lowest, DOWN, buff=0.36)
            span = [cells, *extras] if extras else [cells]
            title.move_to([_span_x(*span), float(cells.get_top()[1]) + 0.35 + float(title.height) / 2, 0])
            board = VGroup(title, cells, ten_dots, ten_label)
            if ones_n:
                board.add(extra_dots)
            if ones_label is not None:
                board.add(ones_label)
            settle(board)
            ten_targets = [dot.get_center().copy() for dot in ten_dots]
            extra_targets = [dot.get_center().copy() for dot in extra_dots]
            # A short stack in the left margin. The frame stays where settle put it.
            col_gap = 0.64
            row_gap = 0.36
            radius = 0.28
            right_col_x = float(cells.get_left()[0]) - 0.5 - radius
            mid_y = float(cells.get_center()[1])
            for i, dot in enumerate(ten_dots):
                col = i % 2
                row = i // 2
                dot.move_to([right_col_x - (1 - col) * col_gap, mid_y + (2 - row) * row_gap, 0])
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

    _scene_types._cache = {"one_ten": OneTen, "ten_and_ones": TenAndOnes, "make_ten": MakeTen}
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


#!/usr/bin/env python3
"""Registry of parameterised animated scenes.

Drawing stays in ``anim.py`` and imports Manim only when a lesson renders.
This module checks the YAML and builds the on-screen label table. Importing
it does not import Manim, so slide lessons never need the optional install.

Add a scene in four steps:

1. Subclass :class:`SceneKind`. Set ``name`` and ``steps``. Implement
   ``problems`` (parameter errors), ``labels`` (per-language on-screen
   strings), and ``parameters`` (values stored in the cache key).
2. ``register`` an instance. Order in :data:`REGISTRY` is the documented order.
3. Draw the scene in ``anim._scene_types`` under the same ``name``. One
   narration line (``s1``, ``s2``, …) is one motion. ``steps`` is how many.
4. Add the YAML fields and an example to ``docs/ANIMATED_SCENES.md``.

``title_card`` and ``takeaway`` are slide visuals. They are not in this
registry. A beat chooses one or the other with ``visual``.
"""

from __future__ import annotations


def label_lang(lang: str) -> str:
    """On-screen language: en, zh (简体), or zh_hk (繁體)."""
    key = str(lang or "en").strip().lower().replace("-", "_")
    if key in {"zh_hk", "hk", "yue", "zh_yue"}:
        return "zh_hk"
    if key in {"zh", "zh_cn", "zhcn", "zh_hans", "cmn"}:
        return "zh"
    return "en"


def _as_int(value):
    """YAML integer, or None when the field is missing or not a whole number."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(("+", "-")):
            rest = text[1:]
            if rest.isdigit():
                return int(text)
            return None
        if text.isdigit():
            return int(text)
    return None


def crosses_ten(start: int, end: int) -> bool:
    """True when a hop from start to end passes the 10 boundary."""
    lo, hi = (start, end) if start <= end else (end, start)
    return lo < 10 < hi


def _copy(lang: str) -> dict[str, str]:
    """On-screen phrases. zh is 简体. zh_hk is 繁體, including spoken Cantonese."""
    table = {
        "en": {
            "ten_title": "A ten and some ones",
            "one_ten": "one ten",
            "two_tens": "two tens",
            "ones": "{n} ones",
            "make_title": "Make ten",
            "full_frame": "A full frame is one ten",
            "count_title": "Count each one",
            "touch_once": "Touch once",
            "how_many": "How many?",
            "last_number": "The last number",
            "still": "Still {n}",
            "moved": "Same counters",
            "empty_tray": "Empty tray",
            "zero_word": "zero",
            "on_title": "Count on",
            "back_title": "Count back",
            "one_more": "One more",
            "one_less": "One less",
            "cross_ten": "Cross ten",
            "start_at": "Start at {n}",
            "grade": "P1",
        },
        "zh": {
            "ten_title": "一个十和一些一",
            "one_ten": "一个十",
            "two_tens": "两个十",
            "ones": "{n}个一",
            "make_title": "凑成十",
            "full_frame": "满框就是一个十",
            "count_title": "逐个点清楚",
            "touch_once": "每个只点一次",
            "how_many": "有几个？",
            "last_number": "最后的数",
            "still": "还是{n}个",
            "moved": "还是这些",
            "empty_tray": "空盘",
            "zero_word": "零",
            "on_title": "接着数",
            "back_title": "倒着数",
            "one_more": "多一个",
            "one_less": "少一个",
            "cross_ten": "跨过十",
            "start_at": "从{n}开始",
            "grade": "小一",
        },
        "zh_hk": {
            "ten_title": "一個十和一些一",
            "one_ten": "一個十",
            "two_tens": "兩個十",
            "ones": "{n}個一",
            "make_title": "湊成十",
            "full_frame": "滿框就係一個十",
            "count_title": "逐個指清楚",
            "touch_once": "每個只指一次",
            "how_many": "有幾多個？",
            "last_number": "最後嘅數",
            "still": "仲係{n}個",
            "moved": "仲係呢啲",
            "empty_tray": "空盤",
            "zero_word": "零",
            "on_title": "順住數",
            "back_title": "倒轉數",
            "one_more": "多一個",
            "one_less": "少一個",
            "cross_ten": "跨過十",
            "start_at": "由{n}開始",
            "grade": "小一",
        },
    }
    return table[label_lang(lang)]


class SceneKind:
    """One parameterised scene. Subclasses validate, label, and name parameters."""

    name = ""
    steps = 3

    def step_count(self, beat: dict) -> int:
        return self.steps

    def problems(self, beat: dict) -> list[str]:
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        return {}

    def parameters(self, beat: dict) -> dict:
        """JSON-friendly values that change the picture. Included in the cache key."""
        return {}


REGISTRY: dict[str, SceneKind] = {}


def register(kind: SceneKind) -> SceneKind:
    REGISTRY[kind.name] = kind
    return kind


def _filled(beat: dict, suffix: str, n: int) -> list[str]:
    missing = []
    for i in range(1, n + 1):
        key = f"s{i}_{suffix}"
        if not str(beat.get(key) or "").strip():
            missing.append(key)
    return missing


class OneTen(SceneKind):
    """Ten loose counters gather into one frame. The ones sit beside it."""

    name = "one_ten"
    steps = 4

    def problems(self, beat: dict) -> list[str]:
        count = _as_int(beat.get("count"))
        if count is None or not 10 <= count <= 20:
            return ["one_ten count must be an integer from 10 to 20."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        count = int(beat.get("count"))
        ones = 0 if count >= 20 else max(0, count - 10)
        return {
            "title": copy["full_frame"],
            "one_ten": copy["one_ten"],
            "ones": copy["ones"].format(n=ones) if ones else "",
        }

    def parameters(self, beat: dict) -> dict:
        return {"count": int(beat.get("count"))}


class TenAndOnes(SceneKind):
    """A full ten-frame, the ones beside it, and the number sentence.

    ``count: 20`` draws two full frames and ``20 = 10 + 10``.
    """

    name = "ten_and_ones"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        count = _as_int(beat.get("count"))
        if count is None or not 10 <= count <= 20:
            return ["ten_and_ones count must be an integer from 10 to 20."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
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

    def parameters(self, beat: dict) -> dict:
        return {"count": int(beat.get("count"))}


class MakeTen(SceneKind):
    """Move ones into the empty cells of a ten-frame, then read what is left."""

    name = "make_ten"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        a = _as_int(beat.get("a"))
        b = _as_int(beat.get("b"))
        if a is None or b is None or not (1 <= a <= 9 and 1 <= b <= 12 and (10 - a) <= b and a + b <= 20):
            return ["make_ten needs a from 1 to 9 and enough b to fill the ten without passing 20."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        a = int(beat.get("a"))
        b = int(beat.get("b"))
        move = 10 - a
        rest = b - move
        return {
            "title": copy["make_title"],
            "equation1": [str(a), "+", str(move), "=", "10"],
            "equation2": ["10", "+", str(rest), "=", str(a + b)],
        }

    def parameters(self, beat: dict) -> dict:
        return {"a": int(beat.get("a")), "b": int(beat.get("b"))}


class CountObjects(SceneKind):
    """Counters light one by one, move without changing the total, or show 0.

    ``mode`` is ``count``, ``rearrange``, or ``zero``. ``count`` is how many
    counters (1–20), or 0 when the tray is empty.
    """

    name = "count_objects"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        mode = str(beat.get("mode") or "").strip()
        if mode not in {"count", "rearrange", "zero"}:
            return [f"count_objects mode must be count, rearrange, or zero, not {mode!r}."]
        count = _as_int(beat.get("count"))
        if mode == "zero":
            if count != 0:
                return ["count_objects mode zero needs count 0 (an empty tray)."]
            return []
        if count is None or not 1 <= count <= 20:
            return [f"count_objects mode {mode} needs a count from 1 to 20."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        mode = str(beat.get("mode") or "").strip()
        count = _as_int(beat.get("count"))
        count = 0 if count is None else count
        if mode == "zero":
            title, note = copy["empty_tray"], copy["zero_word"]
            answer = "0"
        elif mode == "rearrange":
            title, note = copy["moved"], copy["still"].format(n=count)
            answer = str(count)
        else:
            title, note = copy["count_title"], copy["last_number"]
            answer = str(count)
        return {
            "title": title,
            "question": copy["how_many"],
            "touch": copy["touch_once"],
            "note": note,
            "answer": answer,
            "mode": mode,
        }

    def parameters(self, beat: dict) -> dict:
        return {"mode": str(beat.get("mode") or "").strip(), "count": int(beat.get("count"))}


class NumberTrack(SceneKind):
    """A number track and a marker that hops on or back, including across 10.

    ``low`` and ``high`` are the track ends (default classroom track: 0 to 20).
    ``start`` and ``end`` are where the marker begins and where it lands.
    """

    name = "number_track"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        low, high = _as_int(beat.get("low")), _as_int(beat.get("high"))
        start, end = _as_int(beat.get("start")), _as_int(beat.get("end"))
        if None in (low, high, start, end):
            return ["number_track needs integer low, high, start, and end."]
        if not (0 <= low < high <= 30) or (high - low) > 20:
            return ["number_track needs 0 <= low < high <= 30, with at most 20 steps on the track."]
        if not (low <= start <= high and low <= end <= high):
            return [f"number_track start and end must lie on the track from {low} to {high}."]
        if start == end:
            return ["number_track start and end must be different, so the marker can hop."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        start = int(beat.get("start"))
        end = int(beat.get("end"))
        onward = end > start
        return {
            "title": copy["on_title"] if onward else copy["back_title"],
            "step": copy["one_more"] if onward else copy["one_less"],
            "cross": copy["cross_ten"] if crosses_ten(start, end) else "",
            "start_at": copy["start_at"].format(n=start),
            "answer": str(end),
        }

    def parameters(self, beat: dict) -> dict:
        start = int(beat.get("start"))
        end = int(beat.get("end"))
        return {
            "low": int(beat.get("low")),
            "high": int(beat.get("high")),
            "start": start,
            "end": end,
            "crosses_ten": crosses_ten(start, end),
        }


_MOTIFS = {"counters", "ten_frame", "track"}


def _motif(beat: dict) -> str:
    return str((beat or {}).get("motif") or "").strip()


def _beat_line(beat: dict, lang: str, index: int) -> str:
    """Spoken line s1/s2/s3 for this language. The on-screen takeaway uses the same words."""
    code = label_lang(lang)
    suffix = {"en": "en", "zh": "zh", "zh_hk": "zh_hk"}[code]
    return str(beat.get(f"s{index}_{suffix}") or "").strip()


def _title_line(beat: dict, lang: str) -> str:
    code = label_lang(lang)
    suffix = {"en": "en", "zh": "zh", "zh_hk": "zh_hk"}[code]
    return str(beat.get(f"title_{suffix}") or beat.get("title_en") or "").strip()


class LessonHook(SceneKind):
    """Title and the lesson's objects arrive with the opening question.

    One spoken line. ``motif`` is ``counters``, ``ten_frame``, or ``track``.
    """

    name = "lesson_hook"
    steps = 1

    def problems(self, beat: dict) -> list[str]:
        if _motif(beat) not in _MOTIFS:
            return [f"lesson_hook motif must be counters, ten_frame, or track, not {_motif(beat)!r}."]
        if not _title_line(beat, "en"):
            return ["lesson_hook needs title_en (and title_zh / title_zh_hk)."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        return {
            "grade": copy["grade"],
            "title": _title_line(beat, lang),
            "motif": _motif(beat),
        }

    def parameters(self, beat: dict) -> dict:
        return {"motif": _motif(beat), "title": _title_line(beat, "en")}


class LessonTakeaway(SceneKind):
    """Each spoken line appears with a small cue: counters, a ten-frame, or a track.

    Three spoken lines, or four when ``s4`` is written. The words on screen are
    those same lines. ``count`` on a four-line counters recap lights that many
    counters during the first line.
    """

    name = "lesson_takeaway"
    steps = 3

    def step_count(self, beat: dict) -> int:
        if str((beat or {}).get("s4_en") or "").strip():
            return 4
        return self.steps

    def problems(self, beat: dict) -> list[str]:
        if _motif(beat) not in _MOTIFS:
            return [f"lesson_takeaway motif must be counters, ten_frame, or track, not {_motif(beat)!r}."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        n = self.step_count(beat)
        return {
            "title": _title_line(beat, lang) or copy["grade"],
            "lines": [_beat_line(beat, lang, i) for i in range(1, n + 1)],
            "motif": _motif(beat),
            "count": _as_int(beat.get("count")) or 0,
        }

    def parameters(self, beat: dict) -> dict:
        params = {"motif": _motif(beat)}
        if self.step_count(beat) != self.steps:
            params["lines"] = self.step_count(beat)
        # Every takeaway uses the same row grid. The value is part of the
        # cache key, so a layout change does not reuse an older silent clip.
        params["arrangement"] = "grid-gap"
        count = _as_int(beat.get("count"))
        if count is not None:
            params["count"] = count
        return params


def track_columns(count: int, pixel_width: int, pixel_height: int, min_cell: float = 0.42) -> int:
    """Numbers on one row of the track.

    A 0–20 track fits on one row at 16:9, so a hop across 10 stays a sideways
    move. 9:16 wraps only when a cell would be smaller than ``min_cell``.
    """
    count = max(1, int(count))
    pw = max(1, int(pixel_width))
    ph = max(1, int(pixel_height))
    usable = 8.0 * (pw / ph) - 1.15
    gap = 0.08

    def cell(cols: int) -> float:
        return (usable - gap * (max(cols, 1) - 1)) / max(cols, 1)

    if cell(count) >= min_cell:
        return count
    cols = count
    while cols > 1 and cell(cols) < min_cell:
        cols -= 1
    return max(1, cols)


def count_event(beat: dict) -> tuple[int, int] | None:
    """(step index, how many count landings) for a beat that counts aloud.

    The landing count includes the number the marker is already on, so
    "Nine. Ten. Eleven. Twelve." is four landings. ``ten_and_ones`` counts
    during its first line. A beat whose speech is not a count returns None
    from :func:`count_marks` and keeps an even motion.
    """
    scene = str((beat or {}).get("scene") or "").strip()
    if scene == "number_track":
        start, end = _as_int(beat.get("start")), _as_int(beat.get("end"))
        if start is None or end is None or start == end:
            return None
        return 1, abs(end - start) + 1
    if scene == "count_objects" and str(beat.get("mode") or "").strip() == "count":
        count = _as_int(beat.get("count"))
        if count is None or count < 1:
            return None
        return 1, count
    if scene == "ten_and_ones":
        count = _as_int(beat.get("count"))
        if count is None or count < 1:
            return None
        return 0, count
    if scene == "lesson_takeaway":
        # A ten-frame recap counts the three ones on its last line
        # ("Find the ten first. Then count the rest.").
        if _motif(beat) == "ten_frame" and str(beat.get("s4_en") or "").strip():
            return 3, 3
        # A counters recap counts on its first line ("… one, two, three, four, five.").
        count = _as_int(beat.get("count"))
        if count is None or count < 1:
            return None
        return 0, count
    return None


def count_marks(words, step_start: float, step_dur: float, n: int) -> list[float] | None:
    """Offsets inside one step for ``n`` count landings, from TTS word starts.

    A count line is often a short lead-in and then one word per number, so the
    last ``n`` words that begin inside the step are the count. Returns None
    when the sidecar does not have that many words; the scene then spaces the
    motions evenly across the step. Audio is never trimmed.
    """
    n = int(n)
    if n <= 0 or step_dur <= 0 or not words:
        return None
    begin = float(step_start)
    end = begin + float(step_dur)
    inside: list[float] = []
    for word in words:
        if not isinstance(word, dict):
            continue
        try:
            start = float(word.get("start"))
        except (TypeError, ValueError):
            continue
        if begin - 0.08 <= start < end - 0.04:
            inside.append(start)
    if len(inside) < n:
        return None
    chosen = inside[-n:]
    offsets = [max(0.0, start - begin) for start in chosen]
    if any(offsets[i] > offsets[i + 1] + 1e-6 for i in range(len(offsets) - 1)):
        return None
    if offsets[-1] >= float(step_dur):
        return None
    return offsets


def schedule_marks(beat: dict, durations: list[float], words) -> list[list[float]]:
    """Per-step landing offsets. An empty list means even spacing for that step."""
    n_steps = step_count(beat)
    marks: list[list[float]] = [[] for _ in range(n_steps)]
    event = count_event(beat)
    if not event or not durations:
        return marks
    index, n = event
    if not 0 <= index < len(durations):
        return marks
    found = count_marks(words, sum(float(d) for d in durations[:index]), float(durations[index]), n)
    if found:
        marks[index] = [round(float(x), 3) for x in found]
    return marks


register(OneTen())
register(TenAndOnes())
register(MakeTen())
register(CountObjects())
register(NumberTrack())
register(LessonHook())
register(LessonTakeaway())

SCENES = tuple(REGISTRY)
STEP_COUNTS = {name: kind.steps for name, kind in REGISTRY.items()}


def step_count(beat: dict) -> int:
    scene = str((beat or {}).get("scene") or "").strip()
    kind = REGISTRY.get(scene)
    if kind is None:
        return 3
    return kind.step_count(beat or {})


def labels_for(beat: dict, lang: str) -> dict:
    """On-screen strings for one language. Digits stay in the equation."""
    scene = str((beat or {}).get("scene") or "").strip()
    kind = REGISTRY.get(scene)
    if kind is None:
        return {}
    return kind.labels(beat, lang)


def scene_spec(beat: dict, lang: str) -> dict:
    scene = str(beat.get("scene") or "").strip()
    spec: dict = {"scene": scene, "lang": label_lang(lang)}
    kind = REGISTRY.get(scene)
    if kind is not None:
        spec.update(kind.parameters(beat))
        spec["labels"] = kind.labels(beat, lang)
    else:
        spec["labels"] = {}
    return spec


def scene_problems(beat: dict) -> list[str]:
    """Schema errors for one animated beat. Does not import Manim."""
    if str(beat.get("visual") or "") != "animated":
        return []
    problems: list[str] = []
    scene = str(beat.get("scene") or "").strip()
    kind = REGISTRY.get(scene)
    if kind is None:
        names = ", ".join(SCENES)
        problems.append(f"animated scene must be one of {names}, not {scene!r}.")
        return problems
    n = kind.step_count(beat)
    for suffix, name in (("en", "English"), ("zh", "简体")):
        missing = _filled(beat, suffix, n)
        if missing:
            problems.append(f"animated {scene} needs {name} lines {', '.join(missing)} (one per step).")
    hk_keys = [k for k in beat if "zh_hk" in str(k) and str(beat.get(k) or "").strip()]
    if hk_keys:
        missing = _filled(beat, "zh_hk", n)
        if missing:
            problems.append(f"animated {scene} needs Cantonese lines {', '.join(missing)} (one per step).")
    problems.extend(kind.problems(beat))
    return problems

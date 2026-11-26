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


def en_ordinal(n: int) -> str:
    """1st, 2nd, 3rd, 4th, including the teens."""
    n = int(n)
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def zh_cardinal(n: int) -> str:
    """一 … 二十. Used inside 第一, 第二, and the spoken count labels."""
    n = int(n)
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + digits[n - 10]
    if n == 20:
        return "二十"
    return str(n)


def zh_ordinal(n: int) -> str:
    return "第" + zh_cardinal(n)


def ordinal_word(lang: str, n: int) -> str:
    if label_lang(lang) == "en":
        return en_ordinal(n)
    return zh_ordinal(n)


def ordinal_visits(n: int, mark: int, direction: str, mode: str) -> list[int]:
    """0-based token indexes in the order they are counted.

    ``mark`` is 1-based from the left, so the same token stays put when the
    count starts at the other end. ``mode`` ``total`` visits every token.
    ``ordinal`` stops on the marked token.
    """
    order = list(range(int(n)))
    if str(direction) == "right":
        order.reverse()
    if str(mode) == "total":
        return order
    return order[: order.index(int(mark) - 1) + 1]


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
            "place_title": "Which place?",
            "how_many_title": "How many?",
            "from_left": "From the left",
            "from_right": "From the right",
            "pair_title": "Make pairs",
            "none_left": "None left",
            "one_left": "One left",
            "even_word": "Even",
            "odd_word": "Odd",
            "part_title": "Two parts",
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
            "place_title": "第几个？",
            "how_many_title": "有多少个？",
            "from_left": "从左边",
            "from_right": "从右边",
            "pair_title": "两个配成一对",
            "none_left": "没有剩下",
            "one_left": "剩下一个",
            "even_word": "双数",
            "odd_word": "单数",
            "part_title": "两部分",
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
            "place_title": "第幾個？",
            "how_many_title": "有幾多個？",
            "from_left": "由左邊",
            "from_right": "由右邊",
            "pair_title": "兩個配成一對",
            "none_left": "冇剩低",
            "one_left": "剩低一個",
            "even_word": "雙數",
            "odd_word": "單數",
            "part_title": "兩部分",
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


class OrdinalRow(SceneKind):
    """A row of tokens. One is marked. Count a place, or count how many.

    ``n`` is how many tokens (1–20). ``mark`` is the marked token, 1-based
    from the left, so it stays put when the count starts at the other end.
    ``direction`` is ``left`` or ``right``. ``mode`` ``ordinal`` pops place
    labels up to that token. ``mode`` ``total`` counts every token and shows
    how many. A later lesson can reuse the same scene with a different row.
    """

    name = "ordinal_row"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        n = _as_int(beat.get("n"))
        mark = _as_int(beat.get("mark"))
        direction = str(beat.get("direction") or "").strip()
        mode = str(beat.get("mode") or "").strip()
        problems = []
        if n is None or not 1 <= n <= 20:
            problems.append("ordinal_row n must be an integer from 1 to 20.")
        if direction not in {"left", "right"}:
            problems.append(f"ordinal_row direction must be left or right, not {direction!r}.")
        if mode not in {"ordinal", "total"}:
            problems.append(f"ordinal_row mode must be ordinal or total, not {mode!r}.")
        if n is not None and 1 <= n <= 20:
            if mark is None or not 1 <= mark <= n:
                problems.append(f"ordinal_row mark must be an integer from 1 to {n}.")
        elif mark is None:
            problems.append("ordinal_row needs an integer mark.")
        return problems

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        n = int(beat.get("n"))
        mark = int(beat.get("mark"))
        direction = str(beat.get("direction") or "").strip()
        mode = str(beat.get("mode") or "").strip()
        places = len(ordinal_visits(n, mark, direction, mode))
        if mode == "total":
            words = [zh_cardinal(i) if label_lang(lang) != "en" else str(i) for i in range(1, places + 1)]
            title = copy["how_many_title"]
            note = copy["how_many"]
            answer = zh_cardinal(n) if label_lang(lang) != "en" else str(n)
        else:
            words = [ordinal_word(lang, i) for i in range(1, places + 1)]
            title = copy["place_title"]
            note = copy["from_left"] if direction == "left" else copy["from_right"]
            answer = words[-1] if words else ""
        return {
            "title": title,
            "note": note,
            "answer": answer,
            "ordinals": words,
            "mode": mode,
            "direction": direction,
            "n": n,
            "mark": mark,
        }

    def parameters(self, beat: dict) -> dict:
        return {
            "n": int(beat.get("n")),
            "mark": int(beat.get("mark")),
            "direction": str(beat.get("direction") or "").strip(),
            "mode": str(beat.get("mode") or "").strip(),
        }


class PairCounters(SceneKind):
    """Counters slide into pairs. One leftover counter is marked.

    ``n`` is how many counters (0–20). ``n // 2`` pairs form on the second
    spoken line, and ``n % 2`` stays alone. A later lesson can reuse the
    scene with a different count.
    """

    name = "pair_counters"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        n = _as_int(beat.get("n"))
        if n is None or not 0 <= n <= 20:
            return ["pair_counters n must be an integer from 0 to 20."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        n = int(beat.get("n"))
        pairs, leftover = divmod(n, 2)
        if label_lang(lang) == "en":
            words = [str(i) for i in range(1, pairs + 1)]
        else:
            words = [zh_cardinal(i) for i in range(1, pairs + 1)]
        even = leftover == 0
        return {
            "title": copy["pair_title"],
            "note": copy["none_left"] if even else copy["one_left"],
            "answer": copy["even_word"] if even else copy["odd_word"],
            "pairs": words,
            "n": n,
            "pair_count": pairs,
            "leftover": leftover,
        }

    def parameters(self, beat: dict) -> dict:
        return {"n": int(beat.get("n"))}


def _part_bonds(beat: dict) -> list[list[int]] | None:
    """Takeaway cues. Each bond is ``[left, right]`` or ``[whole]``."""
    raw = (beat or {}).get("bonds")
    if not isinstance(raw, list) or not raw:
        return None
    bonds: list[list[int]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or not item:
            return None
        nums = [_as_int(n) for n in item]
        if any(n is None for n in nums):
            return None
        bonds.append([int(n) for n in nums])
    return bonds


def _part_bond_problems(beat: dict) -> list[str]:
    bonds = _part_bonds(beat)
    if bonds is None:
        return ["parts takeaway needs bonds, a list of [left, right] or [whole]."]
    if not 1 <= len(bonds) <= 4:
        return ["parts takeaway bonds must be 1 to 4 cues."]
    for bond in bonds:
        if len(bond) == 1:
            if not 1 <= bond[0] <= 18:
                return ["a parts whole must be an integer from 1 to 18."]
            continue
        if len(bond) != 2:
            return ["each parts bond is one whole or two parts."]
        a, b = bond
        if b < 0:
            if not 0 <= a <= 9 or not 1 <= -b <= 9 or not 1 <= a - b <= 18:
                return ["a removed part is a negative right-hand count from -1 to -9 beside a kept part from 0 to 9."]
            continue
        if not 0 <= a <= 9 or not 0 <= b <= 9 or not 1 <= a + b <= 18:
            return ["parts bonds use parts from 0 to 9 whose sum is from 1 to 18."]
    return []


def _part_word(lang: str, n: int) -> str:
    if label_lang(lang) == "en":
        return str(int(n))
    return zh_cardinal(n)


def _part_pair(beat: dict) -> tuple[int, int] | None:
    """The two parts. Each is 0–9, not both zero, and the whole is 1–18."""
    a = _as_int((beat or {}).get("a"))
    b = _as_int((beat or {}).get("b"))
    if a is None or b is None:
        return None
    return a, b


def _part_pair_problems(beat: dict) -> list[str]:
    pair = _part_pair(beat)
    if pair is None:
        return ["part_whole needs integers a and b."]
    a, b = pair
    if not 0 <= a <= 9 or not 0 <= b <= 9 or a + b < 1 or not 1 <= a + b <= 18:
        return ["part_whole a and b must be integers from 0 to 9, not both 0, whose sum is from 1 to 18."]
    whole = _as_int((beat or {}).get("whole"))
    if whole is not None and whole != a + b:
        return [f"part_whole whole must equal a + b ({a + b})."]
    return []


class PartWhole(SceneKind):
    """A whole splits into two coloured parts, then joins again.

    ``a`` and ``b`` are the parts (each 0–9, not both 0, sum 1–18). A part of
    0 is an empty mat. ``also`` is a second
    left-hand part of the same whole: the counters move, and the whole stays.
    ``cover`` is ``a`` or ``b``: that part is covered and the bond is read
    as a subtraction. ``leave`` is ``a`` or ``b``: that part moves away on
    the last line, landing on the spoken number words, and an empty circle
    stays where each counter was. The two part labels land on the spoken words.
    """

    name = "part_whole"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        found = _part_pair_problems(beat)
        if found:
            return found
        a, b = _part_pair(beat)
        whole = a + b
        also = _as_int(beat.get("also")) if "also" in beat else None
        cover = str(beat.get("cover") or "").strip()
        if "also" in beat and (also is None or not 1 <= also <= whole - 1 or also == a):
            return [f"part_whole also must be an integer from 1 to {whole - 1}, other than {a}."]
        if cover and cover not in {"a", "b"}:
            return ["part_whole cover must be a or b."]
        leave = str(beat.get("leave") or "").strip()
        if leave and leave not in {"a", "b"}:
            return ["part_whole leave must be a or b."]
        if also is not None and cover:
            return ["part_whole uses either also or cover, not both."]
        if also is not None and leave:
            return ["part_whole uses either also or leave, not both."]
        if cover and leave:
            return ["part_whole uses either cover or leave, not both."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        a, b = _part_pair(beat)
        whole = a + b
        also = _as_int(beat.get("also")) if "also" in beat else None
        cover = str(beat.get("cover") or "").strip()
        out = {
            "title": copy["part_title"],
            "a": a,
            "b": b,
            "whole": whole,
            "left": _part_word(lang, a),
            "right": _part_word(lang, b),
            "whole_word": _part_word(lang, whole),
            "equation": [str(whole), "=", str(a), "+", str(b)],
            "cover": cover,
        }
        if also is not None:
            out["also"] = also
            out["also_left"] = _part_word(lang, also)
            out["also_right"] = _part_word(lang, whole - also)
            out["also_equation"] = [str(whole), "=", str(also), "+", str(whole - also)]
        leave = str(beat.get("leave") or "").strip()
        if leave in {"a", "b"}:
            out["leave"] = leave
        if cover in {"a", "b"} or leave in {"a", "b"}:
            which = cover if cover in {"a", "b"} else leave
            kept = b if which == "a" else a
            covered = a if which == "a" else b
            out["covered_equation"] = [str(whole), "-", str(covered), "=", str(kept)]
        return out

    def parameters(self, beat: dict) -> dict:
        a, b = _part_pair(beat)
        params: dict = {"a": a, "b": b}
        if "also" in beat:
            params["also"] = _as_int(beat.get("also"))
        cover = str(beat.get("cover") or "").strip()
        if cover:
            params["cover"] = cover
        leave = str(beat.get("leave") or "").strip()
        if leave:
            params["leave"] = leave
        return params


_MOTIFS = {"counters", "ten_frame", "track", "ordinal", "pairs", "parts"}


def _pair_n(beat: dict, default: int = 8) -> int:
    """Even example for a pairs hook or takeaway. Missing ``n`` is 8."""
    n = _as_int((beat or {}).get("n"))
    if n is None or not 0 <= n <= 20:
        return default
    return n


def _pair_n_problems(beat: dict) -> list[str]:
    if "n" not in (beat or {}):
        return []
    n = _as_int(beat.get("n"))
    if n is None or not 0 <= n <= 20:
        return ["pairs n must be an integer from 0 to 20."]
    return []


def _pair_also(beat: dict) -> int | None:
    if "also" not in (beat or {}):
        return None
    return _as_int(beat.get("also"))


def _pair_also_problems(beat: dict) -> list[str]:
    if "also" not in (beat or {}):
        return []
    n = _as_int(beat.get("also"))
    if n is None or not 0 <= n <= 20:
        return ["pairs also must be an integer from 0 to 20."]
    return []


def _motif(beat: dict) -> str:
    return str((beat or {}).get("motif") or "").strip()


def _ordinal_pair(beat: dict) -> tuple[int, int]:
    """Token count and 1-based mark. A missing pair defaults to six tokens, mark 3."""
    n = _as_int((beat or {}).get("n"))
    mark = _as_int((beat or {}).get("mark"))
    if n is None and mark is None:
        return 6, 3
    if n is None or mark is None or not 1 <= n <= 20 or not 1 <= mark <= n:
        return n or 0, mark or 0
    return n, mark


def _ordinal_pair_problems(beat: dict, required: bool = False) -> list[str]:
    n = _as_int((beat or {}).get("n"))
    mark = _as_int((beat or {}).get("mark"))
    if n is None and mark is None and not required:
        return []
    if n is None or not 1 <= n <= 20:
        return ["ordinal n must be an integer from 1 to 20."]
    if mark is None or not 1 <= mark <= n:
        return [f"ordinal mark must be an integer from 1 to {n}."]
    return []


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

    One spoken line. ``motif`` is ``counters``, ``ten_frame``, ``track``,
    ``ordinal``, ``pairs``, or ``parts``. An ordinal hook may set ``n`` and
    ``mark`` (defaults: 6 tokens, mark 3). A pairs hook may set ``n`` (default
    8). A parts hook may set ``a`` and ``b`` (defaults: 3 and 4).
    """

    name = "lesson_hook"
    steps = 1

    def problems(self, beat: dict) -> list[str]:
        if _motif(beat) not in _MOTIFS:
            return [f"lesson_hook motif must be counters, ten_frame, track, ordinal, pairs, or parts, not {_motif(beat)!r}."]
        if not _title_line(beat, "en"):
            return ["lesson_hook needs title_en (and title_zh / title_zh_hk)."]
        if _motif(beat) == "ordinal":
            return _ordinal_pair_problems(beat, required=False)
        if _motif(beat) == "pairs":
            return _pair_n_problems(beat)
        if _motif(beat) == "parts" and ("a" in beat or "b" in beat):
            return _part_pair_problems(beat)
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        out = {
            "grade": copy["grade"],
            "title": _title_line(beat, lang),
            "motif": _motif(beat),
        }
        if _motif(beat) == "ordinal":
            n, mark = _ordinal_pair(beat)
            out["n"] = n
            out["mark"] = mark
        if _motif(beat) == "pairs":
            out["n"] = _pair_n(beat)
        if _motif(beat) == "parts":
            pair = _part_pair(beat) or (3, 4)
            out["a"], out["b"] = pair
        return out

    def parameters(self, beat: dict) -> dict:
        params = {"motif": _motif(beat), "title": _title_line(beat, "en")}
        if _motif(beat) == "ordinal":
            n, mark = _ordinal_pair(beat)
            params["n"] = n
            params["mark"] = mark
        if _motif(beat) == "pairs":
            params["n"] = _pair_n(beat)
        if _motif(beat) == "parts":
            pair = _part_pair(beat) or (3, 4)
            params["a"], params["b"] = pair
        return params


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
            return [f"lesson_takeaway motif must be counters, ten_frame, track, ordinal, pairs, or parts, not {_motif(beat)!r}."]
        if _motif(beat) == "ordinal":
            return _ordinal_pair_problems(beat, required=False)
        if _motif(beat) == "pairs":
            return _pair_n_problems(beat) + _pair_also_problems(beat)
        if _motif(beat) == "parts":
            return _part_bond_problems(beat)
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        copy = _copy(lang)
        n = self.step_count(beat)
        out = {
            "title": _title_line(beat, lang) or copy["grade"],
            "lines": [_beat_line(beat, lang, i) for i in range(1, n + 1)],
            "motif": _motif(beat),
            "count": _as_int(beat.get("count")) or 0,
        }
        if _motif(beat) == "ordinal":
            count, mark = _ordinal_pair(beat)
            out["n"] = count
            out["mark"] = mark
            out["left"] = ordinal_word(lang, mark)
            out["right"] = ordinal_word(lang, count - mark + 1)
            out["total"] = str(count) if label_lang(lang) == "en" else zh_cardinal(count)
        if _motif(beat) == "pairs":
            even = _pair_n(beat)
            if even % 2:
                even = max(0, even - 1)
            odd = min(20, even + 1)
            out["n"] = even
            out["odd"] = odd
            out["examples"] = [even, odd, 2]
            also = _pair_also(beat)
            if also is not None and 0 <= also <= 20:
                out["also"] = also
                out["also_word"] = str(also) if label_lang(lang) == "en" else zh_cardinal(also)
        if _motif(beat) == "parts":
            out["bonds"] = _part_bonds(beat) or []
        return out

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
        if _motif(beat) == "ordinal":
            count_n, mark = _ordinal_pair(beat)
            params["n"] = count_n
            params["mark"] = mark
        if _motif(beat) == "pairs":
            params["n"] = _pair_n(beat)
            also = _pair_also(beat)
            if also is not None:
                params["also"] = also
        if _motif(beat) == "parts":
            params["bonds"] = _part_bonds(beat) or []
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
    if scene == "ordinal_row":
        n = _as_int(beat.get("n"))
        mark = _as_int(beat.get("mark"))
        direction = str(beat.get("direction") or "").strip()
        mode = str(beat.get("mode") or "").strip()
        if n is None or mark is None or direction not in {"left", "right"} or mode not in {"ordinal", "total"}:
            return None
        if not 1 <= n <= 20 or not 1 <= mark <= n:
            return None
        return 1, len(ordinal_visits(n, mark, direction, mode))
    if scene == "pair_counters":
        n = _as_int(beat.get("n"))
        if n is None or not 0 <= n <= 20:
            return None
        pairs = n // 2
        if pairs < 1:
            return None
        return 1, pairs
    if scene == "part_whole":
        pair = _part_pair(beat)
        if pair is None:
            return None
        a, b = pair
        if _part_pair_problems(beat) or a < 0 or b < 0:
            return None
        return 1, 2
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


_EN_NUMBER = {
    0: "zero",
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
    7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve",
    13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen",
    17: "seventeen", 18: "eighteen",
}
_CJK_NUMBER = {
    0: ("零",),
    1: ("一",),
    2: ("二", "两", "兩"),
    3: ("三",),
    4: ("四",),
    5: ("五",),
    6: ("六",),
    7: ("七",),
    8: ("八",),
    9: ("九",),
    10: ("十",),
    11: ("十一",),
    12: ("十二",),
    13: ("十三",),
    14: ("十四",),
    15: ("十五",),
    16: ("十六",),
    17: ("十七",),
    18: ("十八",),
}


def _spoken_number(text: str, n: int) -> bool:
    """True when a TTS word is the number ``n`` in English or Chinese."""
    raw = str(text or "").strip().strip(".,!?;:。？，、")
    if not raw or n not in _EN_NUMBER:
        return False
    if raw.lower() == _EN_NUMBER[n] or raw == str(n):
        return True
    # "None are left" is zero. The counters still leave on "four" and the
    # difference lands on this word.
    if n == 0 and raw.lower() == "none":
        return True
    core = raw
    for suffix in ("个", "個"):
        if core.endswith(suffix) and len(core) > len(suffix):
            core = core[: -len(suffix)]
            break
    return core in _CJK_NUMBER[n]


def removal_marks(words, step_start: float, step_dur: float, covered: int, kept: int) -> list[float] | None:
    """Offsets for a part leaving, then the part that stays.

    The first word in the step that names ``covered`` is the departure.
    The next word that names ``kept`` is the amount left. Returns None when
    either word is missing, and the scene then shares the step evenly.
    """
    if step_dur <= 0 or not words:
        return None
    begin = float(step_start)
    end = begin + float(step_dur)
    covered_at = None
    kept_at = None
    for word in words:
        if not isinstance(word, dict):
            continue
        try:
            start = float(word.get("start"))
        except (TypeError, ValueError):
            continue
        if not (begin - 0.08 <= start < end - 0.04):
            continue
        text = str(word.get("text") or "")
        if covered_at is None and _spoken_number(text, int(covered)):
            covered_at = start
            continue
        if covered_at is not None and _spoken_number(text, int(kept)):
            kept_at = start
            break
    if covered_at is None or kept_at is None:
        return None
    offsets = [max(0.0, covered_at - begin), max(0.0, kept_at - begin)]
    if offsets[1] < offsets[0] or offsets[-1] >= float(step_dur):
        return None
    return offsets


def schedule_marks(beat: dict, durations: list[float], words) -> list[list[float]]:
    """Per-step landing offsets. An empty list means even spacing for that step."""
    n_steps = step_count(beat)
    marks: list[list[float]] = [[] for _ in range(n_steps)]
    event = count_event(beat)
    if event and durations:
        index, n = event
        if 0 <= index < len(durations):
            found = count_marks(words, sum(float(d) for d in durations[:index]), float(durations[index]), n)
            if found:
                marks[index] = [round(float(x), 3) for x in found]
    leave = str((beat or {}).get("leave") or "").strip()
    pair = _part_pair(beat) if str((beat or {}).get("scene") or "") == "part_whole" else None
    if leave in {"a", "b"} and pair and durations and len(durations) >= 3:
        a, b = pair
        covered = a if leave == "a" else b
        kept = b if leave == "a" else a
        found = removal_marks(words, sum(float(d) for d in durations[:2]), float(durations[2]), covered, kept)
        if found:
            marks[2] = [round(float(x), 3) for x in found]
    return marks


register(OneTen())
register(TenAndOnes())
register(MakeTen())
register(CountObjects())
register(NumberTrack())
register(OrdinalRow())
register(PairCounters())
register(PartWhole())
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

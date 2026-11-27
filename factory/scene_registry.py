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
            "none_left": "All in pairs",
            "one_left": "One left over",
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
            "none_left": "全部配成对",
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
            "none_left": "全部配成對",
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
        out = {
            "title": title,
            "note": note,
            "answer": answer,
            "ordinals": words,
            "mode": mode,
            "direction": direction,
            "n": n,
            "mark": mark,
        }
        if beat.get("one_row"):
            out["one_row"] = True
        return out

    def parameters(self, beat: dict) -> dict:
        out = {
            "n": int(beat.get("n")),
            "mark": int(beat.get("mark")),
            "direction": str(beat.get("direction") or "").strip(),
            "mode": str(beat.get("mode") or "").strip(),
        }
        if beat.get("one_row"):
            out["one_row"] = True
        return out


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


_MOTIFS = {"counters", "ten_frame", "track", "ordinal", "pairs", "parts", "shapes"}


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
            return [f"lesson_hook motif must be counters, ten_frame, track, ordinal, pairs, parts, or shapes, not {_motif(beat)!r}."]
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
            if beat.get("one_row"):
                out["one_row"] = True
        if _motif(beat) == "pairs":
            out["n"] = _pair_n(beat)
        if _motif(beat) == "parts":
            pair = _part_pair(beat) or (3, 4)
            out["a"], out["b"] = pair
        if _motif(beat) == "shapes":
            out["kind"] = str(beat.get("kind") or "triangle").strip()
        if beat.get("shown"):
            out["shown"] = True
        return out

    def parameters(self, beat: dict) -> dict:
        params = {"motif": _motif(beat), "title": _title_line(beat, "en")}
        if _motif(beat) == "ordinal":
            n, mark = _ordinal_pair(beat)
            params["n"] = n
            params["mark"] = mark
            if beat.get("one_row"):
                params["one_row"] = True
        if _motif(beat) == "pairs":
            params["n"] = _pair_n(beat)
        if _motif(beat) == "parts":
            pair = _part_pair(beat) or (3, 4)
            params["a"], params["b"] = pair
        if _motif(beat) == "shapes":
            params["kind"] = str(beat.get("kind") or "triangle").strip()
        if beat.get("shown"):
            params["shown"] = True
        return params


# Pictures the track motif always draws. A takeaway that sets ``cues`` must
# not land on these. Index 2 and 3 are the same row, which is why a four-line
# track takeaway repeats 12, 11, 10, 9.
DEFAULT_TRACK_CUES = (
    (9, 10, 11, 12),
    (17, 18, 19, 20),
    (12, 11, 10, 9),
    (12, 11, 10, 9),
)


def takeaway_cue_picture(spec) -> tuple | None:
    """What one takeaway line draws. None means the cue is not a real picture.

    Callers must not substitute the track placeholder when this returns None.
    """
    if not isinstance(spec, dict):
        return None
    kind = str(spec.get("kind") or "").strip()
    if kind == "tens":
        count = _as_int(spec.get("count"))
        if count is None or not 0 <= count <= 100:
            return None
        return ("tens", count // 10, count % 10)
    if kind == "compare":
        left, right = _as_int(spec.get("a")), _as_int(spec.get("b"))
        if left is None or right is None or left == right:
            return None
        if not 0 <= left <= 100 or not 0 <= right <= 100:
            return None
        return ("compare", left, right, left if left > right else right)
    if kind == "tens_mark":
        left, right = _as_int(spec.get("a")), _as_int(spec.get("b"))
        if left is not None or right is not None:
            if left is None or right is None or left == right:
                return None
            if not 0 <= left <= 100 or not 0 <= right <= 100:
                return None
            return ("tens_mark", left, right)
        rods = _as_int(spec.get("rods"))
        if rods is None:
            rods = 4
        if not 1 <= rods <= 10:
            return None
        return ("tens_mark", rods)
    if kind == "tiles":
        values = spec.get("values")
        if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 6:
            return None
        numbers = []
        for value in values:
            number = _as_int(value)
            if number is None or not 0 <= number <= 100:
                return None
            numbers.append(number)
        return ("tiles", tuple(numbers))
    if kind == "pairs":
        boxes = _as_int(spec.get("n"))
        extra = _as_int(spec.get("extra")) or 0
        if boxes is None or not 1 <= boxes <= 6 or extra not in (0, 1):
            return None
        return ("pairs", boxes, extra)
    if kind == "groups":
        size = _as_int(spec.get("a"))
        boxes = _as_int(spec.get("n"))
        extra = _as_int(spec.get("extra")) or 0
        if size is None or boxes is None or not 2 <= size <= 5 or not 1 <= boxes <= 6:
            return None
        if extra < 0 or extra >= size or size * boxes + extra > 20:
            return None
        return ("groups", size, boxes, extra)
    if kind == "counters":
        count = _as_int(spec.get("n"))
        if count is None or not 1 <= count <= 12:
            return None
        return ("counters", count)
    if kind == "line":
        mode = str(spec.get("mode") or "").strip()
        if mode == "marks":
            count = _as_int(spec.get("n"))
            if count is None or not 1 <= count <= 4:
                return None
            return ("line", "marks", count)
        if mode in {"straight", "curve", "routes"}:
            return ("line", mode)
        return None
    if kind == "flat":
        shape = str(spec.get("shape") or "").strip()
        if shape not in {"triangle", "quad", "pentagon", "hexagon", "circle"}:
            return None
        turn = _as_int(spec.get("turn")) or 0
        if not -180 <= turn <= 180:
            return None
        return ("flat", shape, turn)
    if kind == "solid":
        shape = str(spec.get("shape") or "").strip()
        if shape not in {"prism", "cylinder", "pyramid", "cone", "sphere"}:
            return None
        return ("solid", shape)
    if kind == "join":
        result = str(spec.get("result") or "").strip()
        if result not in {"quad", "triangle", "pentagon", "hexagon"}:
            return None
        return ("join", result)
    return None


def takeaway_cue_problems(beat: dict) -> list[str]:
    """Reject a cue list that is missing, the wrong length, or not a real picture."""
    raw = (beat or {}).get("cues")
    if raw is None:
        return []
    lines = 4 if str((beat or {}).get("s4_en") or "").strip() else 3
    if not isinstance(raw, list) or len(raw) != lines:
        return [f"lesson_takeaway cues must be one picture per spoken line ({lines})."]
    problems = []
    for index, spec in enumerate(raw, start=1):
        if takeaway_cue_picture(spec) is None:
            kind = spec.get("kind") if isinstance(spec, dict) else spec
            problems.append(
                f"lesson_takeaway cue {index} is {kind!r}, which is not a line picture. "
                "It must not fall back to the default track."
            )
    return problems


def takeaway_cue_list(beat: dict) -> list[tuple]:
    raw = (beat or {}).get("cues")
    if not isinstance(raw, list):
        return []
    pictures = []
    for spec in raw:
        picture = takeaway_cue_picture(spec)
        if picture is None:
            return []
        pictures.append(picture)
    return pictures


class LessonTakeaway(SceneKind):
    """Each spoken line appears with a small cue: counters, a ten-frame, or a track.

    Three spoken lines, or four when ``s4`` is written. The words on screen are
    those same lines. ``count`` on a four-line counters recap lights that many
    counters during the first line. ``cues`` gives each line its own picture
    and is not drawn as the track placeholder.
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
            found = _ordinal_pair_problems(beat, required=False)
        elif _motif(beat) == "pairs":
            found = _pair_n_problems(beat) + _pair_also_problems(beat)
        elif _motif(beat) == "parts":
            found = _part_bond_problems(beat)
        else:
            found = []
        return found + takeaway_cue_problems(beat)

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
            if beat.get("one_row"):
                out["one_row"] = True
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
        cues = takeaway_cue_list(beat)
        if cues:
            out["cues"] = cues
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
            if beat.get("one_row"):
                params["one_row"] = True
        if _motif(beat) == "pairs":
            params["n"] = _pair_n(beat)
            also = _pair_also(beat)
            if also is not None:
                params["also"] = also
        if _motif(beat) == "parts":
            params["bonds"] = _part_bonds(beat) or []
        cues = takeaway_cue_list(beat)
        if cues:
            params["cues"] = [list(picture) for picture in cues]
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


def group_columns(boxes: int, size: int, portrait: bool) -> int:
    """Columns of equal groups. Fives use two columns in 9:16 so the totals stay readable."""
    boxes = max(1, int(boxes))
    if portrait and int(size) >= 5:
        return min(2, boxes)
    if portrait:
        return min(3, boxes)
    return min(6, boxes)


def ordinal_columns(n: int, pixel_width: int, pixel_height: int, one_row: bool = False) -> int:
    """Columns for an ordinal row. ``one_row`` never snakes, even in 9:16."""
    n = max(1, int(n))
    if one_row:
        return n
    return track_columns(n, pixel_width, pixel_height, min_cell=0.46)


def track_slots(values: list[int], cols: int, *, left_to_right: bool) -> dict[int, tuple[int, int]]:
    """Map each track value to ``(row, column)``.

    Portrait rows read left to right, and the next row starts at the left.
    Landscape keeps the snake. A one-row track never turns, so 16:9 is the
    same line of numbers either way.
    """
    cols = max(1, int(cols))
    slots: dict[int, tuple[int, int]] = {}
    if left_to_right:
        for i, value in enumerate(values):
            slots[int(value)] = (i // cols, i % cols)
        return slots
    row_i, col_i, direction = 0, 0, 1
    for i, value in enumerate(values):
        slots[int(value)] = (row_i, col_i)
        if i == len(values) - 1:
            break
        nxt = col_i + direction
        if nxt < 0 or nxt >= cols:
            row_i += 1
            direction *= -1
        else:
            col_i = nxt
    return slots


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
    if scene == "number_blocks":
        mode = str(beat.get("mode") or "").strip()
        if mode == "tens":
            count = _as_int(beat.get("count"))
            if count is None or not 0 <= count <= 100:
                return None
            tens = count // 10
            if tens < 1:
                return None
            return 0, tens
        if mode == "hop":
            start, end = _as_int(beat.get("start")), _as_int(beat.get("end"))
            if start is None or end is None or start == end:
                return None
            if abs(end - start) > 5:
                return None
            return 1, abs(end - start) + 1
        if mode == "groups":
            boxes = _as_int(beat.get("n"))
            if boxes is None or not 1 <= boxes <= 6:
                return None
            return 1, boxes
        return None
    if scene == "estimate_group":
        if str(beat.get("part") or "").strip() != "count":
            return None
        count = _as_int(beat.get("count"))
        if count is None or not 11 <= count <= 29 or count % 10 == 0:
            return None
        tens, ones = divmod(count, 10)
        return 0, tens + ones
    if scene == "row_match":
        if str(beat.get("part") or "").strip() != "gap":
            return None
        a, b = _as_int(beat.get("a")), _as_int(beat.get("b"))
        if a is None or b is None or a == b:
            return None
        return 0, abs(a - b)
    if scene == "shape_line":
        if str(beat.get("part") or "").strip() != "marks":
            return None
        count = _as_int(beat.get("n")) or 3
        if not 1 <= count <= 4:
            return None
        return 1, count
    if scene == "flat_shape":
        if str(beat.get("part") or "one").strip() != "one":
            return None
        sides = {"triangle": 3, "quad": 4, "pentagon": 5, "hexagon": 6}.get(str(beat.get("kind") or "").strip())
        if not sides:
            return None
        return 1, sides
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


class NumberBlocks(SceneKind):
    """Tens bundles up to 100, a comparison, an order, a short hop, or equal groups.

    ``mode`` is ``tens``, ``compare``, ``order``, ``hop``, or ``groups``.
    ``tens`` draws ``count`` (0–100) as bundles of ten and the leftover ones.
    Zero ones are an empty mat. ``compare`` shows ``a`` and ``b``. ``order``
    shows ``a``, ``b``, and optional ``n`` and ``mark``, left to right.
    ``hop`` is a short row from ``start`` to ``end``, at most five steps
    apart. ``groups`` draws ``n`` boxes of ``a``, plus ``b`` loose counters.
    """

    name = "number_blocks"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        mode = str(beat.get("mode") or "").strip()
        if mode == "tens":
            count = _as_int(beat.get("count"))
            if count is None or not 0 <= count <= 100:
                return ["number_blocks mode tens needs a count from 0 to 100."]
            return []
        if mode == "compare":
            a, b = _as_int(beat.get("a")), _as_int(beat.get("b"))
            if a is None or b is None or not (0 <= a <= 100 and 0 <= b <= 100):
                return ["number_blocks mode compare needs a and b from 0 to 100."]
            if a == b:
                return ["number_blocks mode compare needs two different numbers."]
            return []
        if mode == "order":
            values = _block_values(beat)
            if len(values) < 2:
                return ["number_blocks mode order needs a and b, and may add n and mark."]
            if any(v is None or not 0 <= v <= 100 for v in values):
                return ["number_blocks mode order needs values from 0 to 100."]
            return []
        if mode == "hop":
            start, end = _as_int(beat.get("start")), _as_int(beat.get("end"))
            if start is None or end is None:
                return ["number_blocks mode hop needs integer start and end."]
            if not (0 <= start <= 100 and 0 <= end <= 100):
                return ["number_blocks mode hop needs start and end from 0 to 100."]
            if start == end:
                return ["number_blocks mode hop needs a different start and end."]
            if abs(end - start) > 5:
                return ["number_blocks mode hop stays within five steps, so the row stays readable."]
            return []
        if mode == "groups":
            size, boxes, extra = _as_int(beat.get("a")), _as_int(beat.get("n")), _as_int(beat.get("b"))
            extra = 0 if extra is None else extra
            if size is None or boxes is None or not 2 <= size <= 5 or not 1 <= boxes <= 6:
                return ["number_blocks mode groups needs a from 2 to 5 and n from 1 to 6."]
            if not 0 <= extra < size:
                return ["number_blocks mode groups extra b must be fewer than one group."]
            if size * boxes + extra > 20:
                return ["number_blocks mode groups total must stay within 20."]
            return []
        return [f"number_blocks mode must be tens, compare, order, hop, or groups, not {mode!r}."]

    def labels(self, beat: dict, lang: str) -> dict:
        code = label_lang(lang)
        mode = str(beat.get("mode") or "").strip()
        titles = {
            "en": {
                "tens": "Tens and ones",
                "compare": "Which is larger?",
                "order": "In order",
                "hop": "Count on",
                "groups": "Equal groups",
            },
            "zh": {
                "tens": "十和个",
                "compare": "哪个大？",
                "order": "排好了",
                "hop": "接着数",
                "groups": "一组一组数",
            },
            "zh_hk": {
                "tens": "十同個",
                "compare": "邊個大呀？",
                "order": "排好咗",
                "hop": "跟住數",
                "groups": "一組一組數",
            },
        }
        title = titles.get(code, titles["en"]).get(mode, titles["en"]["tens"])
        out = {"title": title, "mode": mode}
        if mode == "tens":
            out["count"] = int(beat.get("count"))
            if beat.get("pair_ones"):
                out["pair_ones"] = True
            if beat.get("rods_only"):
                out["rods_only"] = True
        elif mode == "compare":
            out["a"] = int(beat.get("a"))
            out["b"] = int(beat.get("b"))
        elif mode == "order":
            out["values"] = _block_values(beat)
        elif mode == "hop":
            out["start"] = int(beat.get("start"))
            out["end"] = int(beat.get("end"))
        elif mode == "groups":
            extra = _as_int(beat.get("b"))
            out["a"] = int(beat.get("a"))
            out["n"] = int(beat.get("n"))
            out["extra"] = 0 if extra is None else extra
        return out

    def parameters(self, beat: dict) -> dict:
        mode = str(beat.get("mode") or "").strip()
        out = {"mode": mode}
        if mode == "tens":
            out["count"] = int(beat.get("count"))
            if beat.get("pair_ones"):
                out["pair_ones"] = True
            if beat.get("rods_only"):
                out["rods_only"] = True
        elif mode == "compare":
            out["a"] = int(beat.get("a"))
            out["b"] = int(beat.get("b"))
        elif mode == "order":
            out["values"] = _block_values(beat)
        elif mode == "hop":
            out["start"] = int(beat.get("start"))
            out["end"] = int(beat.get("end"))
        elif mode == "groups":
            extra = _as_int(beat.get("b"))
            out["a"] = int(beat.get("a"))
            out["n"] = int(beat.get("n"))
            out["extra"] = 0 if extra is None else extra
        return out


def messy_spots(n: int, width: float, height: float, gap: float) -> list[tuple[float, float]]:
    """Deterministic messy centres inside a box, at least ``gap`` apart.

    The same count always lands in the same pile, so the clip cache stays stable.
    """
    n = max(0, int(n))
    gap = max(0.05, float(gap))
    width = max(float(width), gap)
    height = max(float(height), gap)
    spots: list[tuple[float, float]] = []
    state = 23

    def rnd() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    guard = 0
    while len(spots) < n and guard < n * 200:
        guard += 1
        x = (rnd() - 0.5) * width
        y = (rnd() - 0.5) * height
        if all((x - px) ** 2 + (y - py) ** 2 >= gap * gap for px, py in spots):
            spots.append((x, y))
    cols = max(1, int(width / gap))
    col = row = 0
    while len(spots) < n:
        spots.append((-width / 2 + (col + 0.5) * gap, height / 2 - (row + 0.5) * gap))
        col += 1
        if col >= cols:
            col = 0
            row += 1
    return spots


_ESTIMATE_PARTS = ("pile", "ten", "guess", "count", "close")


class EstimateGroup(SceneKind):
    """One step of an estimate: the pile, one ten, the guess, the count, or the check.

    ``count`` is 11 to 29, so there is at least one ten to guess with and at
    least one one left to find. ``part`` picks the beat. The guess is that many
    tens. The count beat lands on every ten and every one.
    """

    name = "estimate_group"
    steps = 1

    def problems(self, beat: dict) -> list[str]:
        found = []
        count = _as_int(beat.get("count"))
        if count is None or not 11 <= count <= 29 or count % 10 == 0:
            found.append("estimate_group count must be an integer from 11 to 29 with some ones left.")
        part = str(beat.get("part") or "").strip()
        if part not in _ESTIMATE_PARTS:
            found.append("estimate_group part must be pile, ten, guess, count, or close.")
        return found

    def labels(self, beat: dict, lang: str) -> dict:
        code = label_lang(lang)
        titles = {
            "en": "About how many?",
            "zh": "大约有多少个？",
            "zh_hk": "大約有幾多個呀？",
        }
        count = int(beat.get("count"))
        tens, ones = divmod(count, 10)
        return {
            "title": titles.get(code, titles["en"]),
            "count": count,
            "tens": tens,
            "ones": ones,
            "guess": tens * 10,
            "part": str(beat.get("part") or "").strip(),
        }

    def parameters(self, beat: dict) -> dict:
        count = int(beat.get("count"))
        tens, ones = divmod(count, 10)
        return {
            "count": count,
            "tens": tens,
            "ones": ones,
            "guess": tens * 10,
            "part": str(beat.get("part") or "").strip(),
        }


def _block_values(beat: dict) -> list[int]:
    values = []
    for key in ("a", "b", "n", "mark"):
        number = _as_int(beat.get(key))
        if number is None:
            if key in {"a", "b"}:
                return []
            break
        values.append(number)
    return values


register(OneTen())
register(TenAndOnes())
register(MakeTen())
register(CountObjects())
register(NumberTrack())
register(OrdinalRow())
register(PairCounters())
register(PartWhole())
register(NumberBlocks())
def _place_values(beat: dict) -> list[int]:
    values = []
    for key in ("a", "b", "c"):
        number = _as_int(beat.get(key))
        if number is None:
            break
        values.append(number)
    return values


class PlaceSum(SceneKind):
    """Line up ones and tens, then add or take away. No borrowing.

    ``op`` is ``add`` or ``sub``. ``a`` and ``b`` are 0 to 99, and ``c`` is an
    optional third number for an addition. A subtraction stays within each
    column. The answer stays within 99. Three spoken lines: the numbers, the
    ones, then the tens.
    """

    name = "place_sum"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        op = str(beat.get("op") or "").strip()
        values = _place_values(beat)
        if op not in {"add", "sub"}:
            return ["place_sum op must be add or sub."]
        if len(values) < 2 or any(not 0 <= v <= 99 for v in values):
            return ["place_sum needs two or three numbers from 0 to 99."]
        if op == "sub" and len(values) != 2:
            return ["place_sum subtraction uses two numbers."]
        if op == "sub":
            if values[0] % 10 < values[1] % 10 or values[0] // 10 < values[1] // 10:
                return ["place_sum subtraction stays inside each column."]
        elif sum(values) > 99:
            return ["place_sum addition stays within 99."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        code = label_lang(lang)
        op = str(beat.get("op") or "add").strip()
        titles = {
            "add": {"en": "Ones, then tens", "zh": "先个位，再十位", "zh_hk": "先個位，再十位"},
            "sub": {"en": "Ones, then tens", "zh": "先个位，再十位", "zh_hk": "先個位，再十位"},
        }
        table = titles.get(op, titles["add"])
        return {
            "title": table.get(code, table["en"]),
            "op": op,
            "values": _place_values(beat),
        }

    def parameters(self, beat: dict) -> dict:
        return {"op": str(beat.get("op") or "add").strip(), "values": _place_values(beat)}



_ROW_PARTS = ("rows", "match", "gap", "hold", "equal")


class RowMatch(SceneKind):
    """Match two rows, then count the counters with no partner.

    ``a`` and ``b`` are 0 to 12. ``part`` is ``rows``, ``match``, ``gap``,
    ``hold``, or ``equal``. ``equal`` needs the same count on both rows.
    ``gap`` counts the unmatched counters, one landing per spoken number.
    """

    name = "row_match"
    steps = 1

    def problems(self, beat: dict) -> list[str]:
        found = []
        a, b = _as_int(beat.get("a")), _as_int(beat.get("b"))
        if a is None or b is None or not (0 <= a <= 12 and 0 <= b <= 12):
            found.append("row_match needs a and b from 0 to 12.")
        part = str(beat.get("part") or "").strip()
        if part not in _ROW_PARTS:
            found.append("row_match part must be rows, match, gap, hold, or equal.")
        elif part == "equal" and a is not None and b is not None and a != b:
            found.append("row_match part equal needs the same count on both rows.")
        elif part == "gap" and a is not None and b is not None and a == b:
            found.append("row_match part gap needs one row with counters left over.")
        return found

    def labels(self, beat: dict, lang: str) -> dict:
        code = label_lang(lang)
        titles = {"en": "How many more?", "zh": "多多少？", "zh_hk": "多幾多呀？"}
        return {
            "title": titles.get(code, titles["en"]),
            "a": int(beat.get("a")),
            "b": int(beat.get("b")),
            "part": str(beat.get("part") or "").strip(),
        }

    def parameters(self, beat: dict) -> dict:
        return {
            "a": int(beat.get("a")),
            "b": int(beat.get("b")),
            "part": str(beat.get("part") or "").strip(),
        }



register(EstimateGroup())
register(RowMatch())
register(PlaceSum())


_FLAT_KINDS = ("triangle", "quad", "pentagon", "hexagon", "circle")
_SOLID_KINDS = ("prism", "cylinder", "pyramid", "cone", "sphere")
_LINE_PARTS = ("marks", "lines", "routes")
_FLAT_PARTS = ("one", "row", "turn")
_JOIN_RESULTS = ("quad", "triangle", "pentagon", "hexagon")
_FLAT_NAMES = {
    "triangle": {"en": "Triangle", "zh": "三角形", "zh_hk": "三角形"},
    "quad": {"en": "Four sides", "zh": "四条边", "zh_hk": "四條邊"},
    "pentagon": {"en": "Five sides", "zh": "五条边", "zh_hk": "五條邊"},
    "hexagon": {"en": "Six sides", "zh": "六条边", "zh_hk": "六條邊"},
    "circle": {"en": "Round", "zh": "圆形", "zh_hk": "圓形"},
}
_SOLID_NAMES = {
    "prism": {"en": "Prism", "zh": "柱体", "zh_hk": "柱體"},
    "cylinder": {"en": "Cylinder", "zh": "圆柱体", "zh_hk": "圓柱體"},
    "pyramid": {"en": "Pyramid", "zh": "锥体", "zh_hk": "錐體"},
    "cone": {"en": "Cone", "zh": "圆锥体", "zh_hk": "圓錐體"},
    "sphere": {"en": "Sphere", "zh": "球体", "zh_hk": "球體"},
}
_LINE_WORDS = {
    "straight": {"en": "Straight", "zh": "直的", "zh_hk": "直嘅"},
    "curve": {"en": "Curved", "zh": "弯的", "zh_hk": "彎嘅"},
}


def _shape_heading(beat: dict, lang: str, fallback: dict[str, str]) -> str:
    code = label_lang(lang)
    suffix = {"en": "en", "zh": "zh", "zh_hk": "zh_hk"}[code]
    written = str(beat.get(f"title_{suffix}") or "").strip()
    return written or fallback.get(code, fallback["en"])


def _named(table: dict, key: str, lang: str) -> str:
    code = label_lang(lang)
    row = table.get(key) or {}
    return row.get(code, row.get("en", ""))


class ShapeLine(SceneKind):
    """Points, a straight line, and a curve. Three spoken lines.

    ``part`` is ``marks``, ``lines``, or ``routes``. ``marks`` counts ``n``
    places (1 to 4) on the second line.
    """

    name = "shape_line"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        part = str(beat.get("part") or "").strip()
        if part not in _LINE_PARTS:
            return ["shape_line part must be marks, lines, or routes."]
        if part == "marks":
            count = _as_int(beat.get("n")) or 3
            if not 1 <= count <= 4:
                return ["shape_line marks need n from 1 to 4."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        part = str(beat.get("part") or "").strip()
        count = _as_int(beat.get("n")) or 3
        return {
            "title": _shape_heading(beat, lang, {
                "en": "Points and lines",
                "zh": "点和线",
                "zh_hk": "點同線",
            }),
            "part": part,
            "n": count,
            "straight": _named(_LINE_WORDS, "straight", lang),
            "curve": _named(_LINE_WORDS, "curve", lang),
        }

    def parameters(self, beat: dict) -> dict:
        return {"part": str(beat.get("part") or "").strip(), "n": _as_int(beat.get("n")) or 3}


class FlatShape(SceneKind):
    """A flat shape, a row of up to three, or the same shape turned.

    ``part`` is ``one``, ``row``, or ``turn``. ``one`` counts the straight
    sides on the second line. A circle has no straight sides. ``row`` uses
    ``items``. ``turn`` is degrees, default 20.
    """

    name = "flat_shape"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        part = str(beat.get("part") or "one").strip()
        if part not in _FLAT_PARTS:
            return ["flat_shape part must be one, row, or turn."]
        if part == "row":
            items = beat.get("items")
            if not isinstance(items, list) or not 1 <= len(items) <= 3:
                return ["flat_shape row needs one to three items."]
            if any(str(item) not in _FLAT_KINDS for item in items):
                return ["flat_shape items must be triangle, quad, pentagon, hexagon, or circle."]
            return []
        kind = str(beat.get("kind") or "").strip()
        if kind not in _FLAT_KINDS:
            return ["flat_shape kind must be triangle, quad, pentagon, hexagon, or circle."]
        if part == "turn":
            turn = _as_int(beat.get("turn")) or 20
            if not -180 <= turn <= 180:
                return ["flat_shape turn must be from -180 to 180."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        part = str(beat.get("part") or "one").strip()
        kind = str(beat.get("kind") or "").strip()
        items = [str(item) for item in (beat.get("items") or [])]
        return {
            "title": _shape_heading(beat, lang, {
                "en": "Name the shape",
                "zh": "认识这个图形",
                "zh_hk": "認識呢個圖形",
            }),
            "part": part,
            "kind": kind,
            "items": items,
            "name": _named(_FLAT_NAMES, kind, lang),
            "names": [_named(_FLAT_NAMES, item, lang) for item in items],
            "turn": _as_int(beat.get("turn")) or 20,
        }

    def parameters(self, beat: dict) -> dict:
        part = str(beat.get("part") or "one").strip()
        return {
            "part": part,
            "kind": str(beat.get("kind") or "").strip(),
            "items": [str(item) for item in (beat.get("items") or [])],
            "turn": _as_int(beat.get("turn")) or 20,
        }


class ShapeJoin(SceneKind):
    """Two pieces meet. The last line shows only the outside sides.

    ``result`` is ``quad``, ``triangle``, ``pentagon``, or ``hexagon``.
    """

    name = "shape_join"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        result = str(beat.get("result") or "").strip()
        if result not in _JOIN_RESULTS:
            return ["shape_join result must be quad, triangle, pentagon, or hexagon."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        result = str(beat.get("result") or "").strip()
        return {
            "title": _shape_heading(beat, lang, {
                "en": "Put shapes together",
                "zh": "拼在一起",
                "zh_hk": "拼埋一齊",
            }),
            "result": result,
            "name": _named(_FLAT_NAMES, result if result != "quad" else "quad", lang),
        }

    def parameters(self, beat: dict) -> dict:
        return {"result": str(beat.get("result") or "").strip()}


class SolidShape(SceneKind):
    """One solid, two solids, or the same solid turned. Three spoken lines.

    ``items`` lists one or two of prism, cylinder, pyramid, cone, sphere.
    ``part`` ``turn`` rotates a single solid.
    """

    name = "solid_shape"
    steps = 3

    def problems(self, beat: dict) -> list[str]:
        items = beat.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 2:
            return ["solid_shape needs one or two items."]
        if any(str(item) not in _SOLID_KINDS for item in items):
            return ["solid_shape items must be prism, cylinder, pyramid, cone, or sphere."]
        part = str(beat.get("part") or "pair").strip()
        if part not in {"pair", "turn"}:
            return ["solid_shape part must be pair or turn."]
        if part == "turn" and len(items) != 1:
            return ["solid_shape turn uses one item."]
        return []

    def labels(self, beat: dict, lang: str) -> dict:
        items = [str(item) for item in beat.get("items") or []]
        return {
            "title": _shape_heading(beat, lang, {
                "en": "Solid shapes",
                "zh": "认识立体",
                "zh_hk": "認識立體",
            }),
            "part": str(beat.get("part") or "pair").strip(),
            "items": items,
            "names": [_named(_SOLID_NAMES, item, lang) for item in items],
            "turn": _as_int(beat.get("turn")) or 25,
        }

    def parameters(self, beat: dict) -> dict:
        return {
            "part": str(beat.get("part") or "pair").strip(),
            "items": [str(item) for item in (beat.get("items") or [])],
            "turn": _as_int(beat.get("turn")) or 25,
        }


register(ShapeLine())
register(FlatShape())
register(ShapeJoin())
register(SolidShape())
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

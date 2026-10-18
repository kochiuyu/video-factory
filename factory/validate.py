#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from glyphs import scan_lesson
from langs import beat_text, stage_lines
from youtube import youtube_errors, youtube_warnings


def _stem(beat: dict, name: str) -> str:
    if name == "number":
        return "" if beat.get("number") is None else str(beat.get("number")).strip()
    if name.startswith("c") and len(name) == 3 and name[1:].isdigit():
        return str(
            beat.get(name)
            or beat.get(f"{name}_en")
            or beat.get(f"{name}_zh")
            or beat.get(f"{name}_zh_hk")
            or ""
        ).strip()
    if name == "formula" and (
        beat.get("formula_tex")
        or beat.get("formula_tex_en")
        or beat.get("formula_tex_zh")
        or beat.get("formula_tex_zh_hk")
    ):
        return "tex"
    return (
        beat.get(f"{name}_en")
        or beat.get(name)
        or beat.get(f"{name}_zh")
        or beat.get(f"{name}_zh_cn")
        or beat.get(f"{name}_zh_hk")
        or ""
    ).strip()


def _has(beat: dict, *names: str) -> bool:
    return all(_stem(beat, n) for n in names)


# Every listed stem must be present. example / big_number have extra branches below.
REQUIRED_STEMS = {
    "title_card": ("title",),
    "definition_card": ("formula",),
    "formula": ("formula",),
    "two_column": ("left", "right"),
    "takeaway": ("q1", "q2"),
    "three_column": ("col1", "col2", "col3"),
    "steps": ("step1", "step2"),
    "module_open": ("item1",),
    "module_close": ("claim",),
    "payoff_matrix": ("row1", "col1", "c11"),
    "table_grid": ("row1", "col1", "c11"),
    "series": ("row1", "col1", "c11"),
    "pair": ("left", "right", "lc11"),
    "pair_chart": ("left", "right"),
    "pair_box": ("left", "right"),
    "pair_slope": ("left", "right"),
}


ALLOWED_VISUALS = {
    "title_card",
    "definition_card",
    "two_column",
    "formula",
    "takeaway",
    "example",
    "three_column",
    "big_number",
    "steps",
    "module_open",
    "module_close",
    "payoff_matrix",
    "table_grid",
    "series",
    "rank_line",
    "freq_bars",
    "balance_line",
    "box_line",
    "dev_bars",
    "ratio_bars",
    "quad_scatter",
    "pair",
    "pair_chart",
    "pair_box",
    "pair_slope",
    "redraw",
    "turns",
    "shrink",
    "mix",
    "coin",
    "schematic_chart",
    "dag",
}


def _steps_rows(beat: dict) -> int:
    n = 0
    for i in range(1, 7):
        if any(str(beat.get(f"step{i}{sfx}") or "").strip() for sfx in ("", "_en", "_zh", "_zh_hk")):
            n = i
    return n


def _speech_stages(beat: dict) -> int:
    n = 0
    for i in range(1, 9):
        if any(str(beat.get(f"s{i}_{lg}") or "").strip() for lg in ("en", "zh", "zh_hk")):
            n = i
    return n


def steps_stage_problems(beat: dict) -> list[str]:
    """A steps card shows 3 columns, or a 4-5 row stack with one still per row.

    The voice follows s1, s2, ...; each still needs its own spoken stage, or the
    speech runs ahead of the rows and the extra rows sit silent.
    """
    if beat.get("visual") != "steps" or beat.get("stage") is False:
        return []
    rows = _steps_rows(beat)
    stages = _speech_stages(beat)
    if not stages:
        return []  # whole-card speech is split automatically
    if rows >= 4 and stages != rows:
        return [f"steps has {rows} rows but {stages} speech stages (s1..s{rows} needed, one per row)."]
    if rows <= 3 and stages > 3:
        return [f"steps has {rows} rows but {stages} speech stages (a 3-column steps card takes s1..s3)."]
    return []


# Bilingual on-screen budgets: (Latin chars for _en, CJK chars for _zh / _zh_hk).
# Warnings only. Long fields crowd a two-language card (zh+en, hk+en).
TEXT_BUDGETS = {
    "title": (32, 14),
    "left": (28, 12),
    "right": (28, 12),
    "step_stack": (30, 14),
    "step_cols": (40, 18),
    "chip": (10, 4),
    "footer": (36, 16),
    "formula": (40, 18),
    "q1": (45, 20),
    "q2": (45, 20),
    "gloss": (40, 18),
    "item": (30, 14),
    "setup": (40, 18),
    "result": (40, 18),
    "col": (40, 18),
    "claim": (45, 20),
    "next": (45, 20),
}

_LANG_SFX = (("_en", 0), ("_zh", 1), ("_zh_hk", 1))


def _cjk_len(text: str) -> int:
    return sum(1 for ch in str(text) if "\u2e80" <= ch <= "\u9fff" or "\uf900" <= ch <= "\ufaff" or "\uff00" <= ch <= "\uffef")


def _measure(text: str, cjk: int) -> int:
    return _cjk_len(text) if cjk else len(str(text))


def text_length_warnings(lesson: dict) -> list[str]:
    warns: list[str] = []
    for i, beat in enumerate(lesson.get("beats") or [], start=1):
        bid = beat.get("id", i)
        vis = beat.get("visual")

        def check(stem: str, budget_key: str, split_lines: bool = False, split_chips: bool = False):
            lat, cjk_cap = TEXT_BUDGETS[budget_key]
            for sfx, cjk in _LANG_SFX:
                raw = beat.get(f"{stem}{sfx}")
                if raw is None and sfx == "_en":
                    raw = beat.get(stem)
                if raw is None or isinstance(raw, (int, float)):
                    continue
                parts = [str(raw)]
                if split_lines:
                    parts = [p for p in str(raw).splitlines() if p.strip()]
                if split_chips:
                    parts = [p for p in (raw if isinstance(raw, list) else str(raw).split(";")) if str(p).strip()]
                cap = cjk_cap if cjk else lat
                for part in parts:
                    n = _measure(part, cjk)
                    if n > cap:
                        warns.append(f"Beat {bid} {stem}{sfx} is {n} {'CJK' if cjk else 'Latin'} chars (bilingual budget {cap}).")

        check("title", "title")
        if vis in ("two_column", "pair", "pair_chart", "pair_box", "pair_slope", "coin", "mix", "redraw"):
            check("left", "left"); check("right", "right")
        if vis == "steps":
            stack = _steps_rows(beat) >= 4
            for k in range(1, 7):
                check(f"step{k}", "step_stack" if stack else "step_cols")
        if vis == "three_column":
            for k in (1, 2, 3):
                check(f"col{k}", "col")
        if vis in ("definition_card", "formula"):
            check("formula", "formula", split_lines=True); check("gloss", "gloss")
        if vis == "takeaway":
            check("q1", "q1"); check("q2", "q2")
        if vis == "example":
            check("setup", "setup"); check("result", "result")
        if vis == "module_open":
            for k in range(1, 6):
                check(f"item{k}", "item")
        if vis == "module_close":
            check("claim", "claim"); check("next", "next")
        if vis in ("rank_line", "freq_bars", "balance_line", "box_line", "dev_bars", "ratio_bars", "quad_scatter", "turns"):
            for stem in ("values", "labels", "days"):
                check(stem, "chip", split_chips=True)
            for k in range(1, 7):
                check(f"v{k}", "chip"); check(f"l{k}", "chip")
        if beat.get("footer_en") or beat.get("footer"):
            check("footer", "footer")
        if vis in ("rank_line", "box_line") and (beat.get("span_en") or beat.get("span_zh")):
            check("span", "footer")
    return warns


def load_lesson(path: Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Lesson file must be a mapping.")
    return data


def validate(lesson: dict, glyphs: bool = True) -> list[str]:
    errors: list[str] = []
    for key in ("id", "title_en", "title_zh", "beats"):
        if key not in lesson:
            errors.append(f"Missing field: {key}")
    beats = lesson.get("beats") or []
    errors.extend(youtube_errors(lesson))
    if not beats:
        errors.append("No beats.")
        return errors
    total = 0.0
    for i, beat in enumerate(beats, start=1):
        if "id" not in beat:
            errors.append(f"Beat {i} has no id.")
        if beat.get("visual") not in ALLOWED_VISUALS:
            errors.append(f"Beat {beat.get('id', i)} has unknown visual {beat.get('visual')!r}.")
        en = beat_text(beat, "en")
        zh = beat_text(beat, "zh")
        hk = beat_text(beat, "zh_hk")
        if not en:
            errors.append(f"Beat {beat.get('id', i)} missing English speech (en or s1_en).")
        if not zh:
            errors.append(f"Beat {beat.get('id', i)} missing 简体 speech (zh or s1_zh).")
        vis = beat.get("visual")
        bid = beat.get("id", i)
        if vis == "example":
            if not (_has(beat, "setup", "result") or _has(beat, "left", "right")):
                errors.append(f"Beat {bid} example needs setup+result or left+right.")
        elif vis == "dag":
            if not (_has(beat, "n1") or _has(beat, "n1_label") or str(beat.get("n1_id") or "").strip() or str(beat.get("nodes") or "").strip()):
                errors.append(f"Beat {bid} dag needs n1 / n1_id or nodes.")
        elif vis == "schematic_chart":
            if not (_has(beat, "x") or _has(beat, "y") or str(beat.get("chart") or beat.get("kind") or "").strip()):
                errors.append(f"Beat {bid} schematic_chart needs chart/kind or x/y labels.")
        elif vis == "big_number":
            if not (_stem(beat, "number") or _stem(beat, "formula")):
                errors.append(f"Beat {bid} big_number needs number or formula.")
            if not _stem(beat, "unit"):
                errors.append(f"Beat {bid} big_number needs unit.")
        elif vis == "rank_line":
            from slides import rank_line_problems

            for msg in rank_line_problems(beat):
                errors.append(f"Beat {bid} {msg}")
        elif vis == "freq_bars":
            from slides import freq_bars_problems

            for msg in freq_bars_problems(beat):
                errors.append(f"Beat {bid} {msg}")
        elif vis == "balance_line":
            from slides import balance_problems

            for msg in balance_problems(beat):
                errors.append(f"Beat {bid} {msg}")
        elif vis == "box_line":
            from slides import box_line_problems

            for msg in box_line_problems(beat):
                errors.append(f"Beat {bid} {msg}")
        elif vis == "dev_bars":
            from slides import dev_bars_problems

            for msg in dev_bars_problems(beat):
                errors.append(f"Beat {bid} {msg}")
        elif vis == "ratio_bars":
            from slides import ratio_bars_problems

            for msg in ratio_bars_problems(beat):
                errors.append(f"Beat {bid} {msg}")
        elif vis == "quad_scatter":
            from slides import quad_scatter_problems

            for msg in quad_scatter_problems(beat):
                errors.append(f"Beat {bid} {msg}")
        else:
            missing = [s for s in REQUIRED_STEMS.get(vis, ()) if not _stem(beat, s)]
            if missing:
                errors.append(f"Beat {bid} {vis} missing {', '.join(missing)}.")
        for msg in steps_stage_problems(beat):
            errors.append(f"Beat {bid} {msg}")
        total += float(beat.get("seconds") or 0)
    if any(beat_text(b, "zh_hk") for b in beats) and any(not beat_text(b, "zh_hk") for b in beats):
        errors.append("Some beats have zh_hk and others do not; fill every beat.")
    target = float(lesson.get("duration_target_s") or 0)
    if target and total and abs(total - target) > 20:
        errors.append(f"Beat seconds sum to {total}, target is {target}.")
    if glyphs:
        errors.extend(scan_lesson(lesson))
    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: validate.py LESSON.yaml", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    lesson = load_lesson(path)
    errors = validate(lesson)
    warns = text_length_warnings(lesson)
    warns.extend(youtube_warnings(lesson))
    if errors:
        print("INVALID")
        for e in errors:
            print(" -", e)
        for w in warns:
            print(" ~ WARN", w)
        return 1
    print("OK", lesson["id"], f"{len(lesson['beats'])} beats")
    for w in warns:
        print(" ~ WARN", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

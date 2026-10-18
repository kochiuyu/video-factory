#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from glyphs import scan_lesson
from langs import beat_text, stage_lines


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
        else:
            missing = [s for s in REQUIRED_STEMS.get(vis, ()) if not _stem(beat, s)]
            if missing:
                errors.append(f"Beat {bid} {vis} missing {', '.join(missing)}.")
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
    if errors:
        print("INVALID")
        for e in errors:
            print(" -", e)
        return 1
    print("OK", lesson["id"], f"{len(lesson['beats'])} beats")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

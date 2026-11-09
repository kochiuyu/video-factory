#!/usr/bin/env python3
"""Join short lessons into a 5–10 minute teaching module."""

from __future__ import annotations

from pathlib import Path

import yaml

from ff import probe_duration
from mux import concat_clips
from pack import parse_speeds, write_experiment_pack
from quiz import export_module_quiz
from catalog import MODULES, lesson_path, out_dir as lesson_out_dir
from validate import load_lesson, validate

ROOT = Path(__file__).resolve().parents[1]


def is_minicourse(data: dict | Path) -> bool:
    if isinstance(data, Path):
        if data.parent.name == "minicourses":
            return True
        try:
            data = yaml.safe_load(data.read_text(encoding="utf-8"))
        except Exception:
            return False
    return isinstance(data, dict) and data.get("kind") == "minicourse"


def is_module(data: dict | Path) -> bool:
    if isinstance(data, Path):
        if data.parent.name == "minicourses":
            return False
        if data.parent.name == "modules":
            return True
        try:
            data = yaml.safe_load(data.read_text(encoding="utf-8"))
        except Exception:
            return False
    if not isinstance(data, dict) or data.get("kind") == "minicourse":
        return False
    return data.get("kind") == "module" or bool(data.get("lessons"))


def load_module(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Module file must be a mapping.")
    data["_path"] = path
    return data


def module_errors(mod: dict) -> list[str]:
    errors: list[str] = []
    if not mod.get("id"):
        errors.append("Missing field: id")
    if not mod.get("title_en"):
        errors.append("Missing field: title_en")
    ids = list(mod.get("lessons") or [])
    if len(ids) < 2:
        errors.append("A module needs at least two lessons.")
    if len(ids) > 6:
        errors.append("A module should stay under six lessons (5–10 minutes).")
    seen = set()
    total = 0.0
    for lid in ids:
        if lid in seen:
            errors.append(f"Duplicate lesson {lid}.")
        seen.add(lid)
        path = lesson_path(lid)
        if path is None:
            errors.append(f"Lesson not found: {lid}.yaml")
            continue
        try:
            lesson = load_lesson(path)
            errs = [e for e in validate(lesson, glyphs=False) if not e.startswith("Beat seconds")]
            errors.extend(f"{lid}: {e}" for e in errs)
            total += float(lesson.get("duration_target_s") or 0)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{lid}: {exc}")
    if total and (total < 240 or total > 720):
        errors.append(f"Stacked target is {int(total)}s; grant modules are 5–10 minutes.")
    return errors


def build_minicourse(
    course_path: Path,
    out_root: Path,
    *,
    label_lang: str = "en",
    tts: bool = True,
    force_tts: bool = False,
    wanted_cells: list[str] | None = None,
    match_titles: bool = False,
    theme_name: str | None = None,
    progress_bar: bool = True,
    stage_cards: bool = True,
    experiment_pack: bool = False,
    pack_speeds: list[float] | None = None,
    pack_nocap: bool = False,
    slides_only: bool = False,
    caption_preview: bool = False,
) -> None:
    """Paint each short. Do not concatenate, and do not apply the six-lesson module cap."""
    from build import build

    course = load_module(course_path)
    ids = list(course.get("lessons") or [])
    errors: list[str] = []
    if not course.get("id"):
        errors.append("Missing field: id")
    if len(ids) < 2:
        errors.append("A mini-course needs at least two lessons.")
    seen = set()
    for lid in ids:
        if lid in seen:
            errors.append(f"Duplicate lesson {lid}.")
        seen.add(lid)
        if lesson_path(lid) is None:
            errors.append(f"Lesson not found: {lid}.yaml")
    if errors:
        print("INVALID mini-course:")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)
    print(f"mini-course: {course['id']} <- {len(ids)} shorts, not joined")
    child_kw = dict(
        label_lang=label_lang,
        tts=tts,
        force_tts=force_tts,
        slides_only=slides_only,
        caption_preview=caption_preview,
        wanted_cells=wanted_cells,
        match_titles=match_titles,
        theme_name=theme_name,
        progress_bar=progress_bar,
        stage_cards=stage_cards,
        experiment_pack=experiment_pack,
        pack_speeds=pack_speeds,
        pack_nocap=pack_nocap,
    )
    for lid in ids:
        print(f"\n######## {lid} ########")
        build(lesson_path(lid), out_root, **child_kw)
    print(f"mini-course: finished {len(ids)} shorts; no concat")


def list_modules() -> list[Path]:
    MODULES.mkdir(exist_ok=True)
    return sorted(MODULES.glob("*.yaml"))


def _shift_srt(text: str, offset: float, start_index: int) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    index = start_index
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.isdigit() and i + 1 < len(lines) and " --> " in lines[i + 1]:
            out.append(str(index))
            index += 1
            out.append(_shift_stamp_line(lines[i + 1], offset))
            i += 2
            while i < len(lines) and lines[i].strip():
                out.append(lines[i])
                i += 1
            out.append("")
            continue
        i += 1
    return "\n".join(out).rstrip() + "\n", index


def _shift_stamp_line(line: str, offset: float) -> str:
    a, b = line.split(" --> ", 1)
    return f"{_add(a.strip(), offset)} --> {_add(b.strip(), offset)}"


def _add(stamp: str, offset: float) -> str:
    hh, mm, rest = stamp.replace(".", ",").split(":")
    ss, ms = (rest + ",000").split(",")[:2]
    total = int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms[:3].ljust(3, "0")) / 1000.0 + offset
    total = max(0.0, total)
    h = int(total // 3600)
    m = int(total % 3600 // 60)
    s = int(total % 60)
    milli = int(round((total - int(total)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def _concat_srts(parts: list[tuple[Path, float]], dest: Path) -> Path | None:
    if not any(p.is_file() for p, _d in parts):
        return None
    chunks: list[str] = []
    idx = 1
    t = 0.0
    for path, dur in parts:
        if path.is_file():
            body, idx = _shift_srt(path.read_text(encoding="utf-8"), t, idx)
            chunks.append(body)
        t += max(dur, 0.0)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(chunks).strip() + "\n", encoding="utf-8")
    return dest


def build_module(
    module_path: Path,
    out_root: Path,
    *,
    label_lang: str = "en",
    tts: bool = True,
    force_tts: bool = False,
    wanted_cells: list[str] | None = None,
    match_titles: bool = False,
    theme_name: str | None = None,
    progress_bar: bool = True,
    stage_cards: bool = True,
    experiment_pack: bool = False,
    pack_speeds: list[float] | None = None,
    pack_nocap: bool = False,
    slides_only: bool = False,
    caption_preview: bool = False,
) -> None:
    from build import StepClock, build

    mod = load_module(module_path)
    errors = module_errors(mod)
    fatal = [e for e in errors if "Stacked target" not in e]
    if fatal:
        print("INVALID module:")
        for e in fatal:
            print(" -", e)
        raise SystemExit(1)
    for e in errors:
        print("note:", e)
    mid = mod["id"]
    members = list(mod["lessons"])
    print(f"module: {mid} <- {' + '.join(members)}")
    export_module_quiz(mod, lesson_out_dir(mid, module=True, root=out_root))
    child_kw = dict(
        label_lang=label_lang,
        tts=tts,
        force_tts=force_tts,
        slides_only=slides_only,
        caption_preview=caption_preview,
        wanted_cells=wanted_cells,
        match_titles=match_titles,
        theme_name=theme_name,
        progress_bar=progress_bar,
        stage_cards=stage_cards,
        experiment_pack=False,
        pack_speeds=None,
        pack_nocap=False,
        write_pdfs=False,
    )
    n = len(members)
    clock = StepClock()
    for i, lid in enumerate(members, start=1):
        print(f"progress: module {i}/{n} build {lid}")
        print(f"######## {lid} (module part {i}/{n}) ########")
        child = lesson_path(lid)
        if child is None:
            raise FileNotFoundError(f"Lesson not found: {lid}.yaml")
        build(child, out_root, **child_kw)
        clock.lap(lid)
    if slides_only or caption_preview:
        n_png = 0
        kind = "preview" if caption_preview else "slides"
        for lid in members:
            folder = lesson_out_dir(lid, module=False, root=out_root) / kind
            if folder.is_dir():
                n_png += sum(1 for _ in folder.rglob("*.png"))
        print(f"module: {n_png} {kind} PNG across {len(members)} shorts; skip module mux")
        print(f"{'caption-preview' if caption_preview else 'slides-only'}: wrote {n_png} PNG files; skipped TTS and mux")
        try:
            from pdfexport import export_preview_pdfs

            kind = ("captions",) if caption_preview else ("slides",)
            pdfs = export_preview_pdfs(mid, out_root, kind)
            if pdfs:
                print("pdf:", ", ".join(p.name for p in pdfs))
        except Exception as exc:  # noqa: BLE001
            print(f"pdf skip: {exc}")
        clock.total()
        return
    out_dir = lesson_out_dir(mid, module=True, root=out_root)
    cell_dir = out_dir / "cells"
    cell_dir.mkdir(parents=True, exist_ok=True)
    srt_dir = out_dir / "srt"
    srt_dir.mkdir(parents=True, exist_ok=True)
    cell_alias = {
        "en": ("en", "en-en"),
        "zh": ("zh", "zhcn", "zh-zh"),
        "hk": ("hk", "zhhk", "zh_hk"),
        "en+zh": ("en+zh", "en-en-zh"),
        "en+hk": ("en+hk", "en-en-hk"),
        "zh+en": ("zh+en", "zh-zh-en"),
        "zh+hk": ("zh+hk", "zh-zh-hk"),
        "hk+en": ("hk+en", "hk-hk-en"),
        "hk+zh": ("hk+zh", "hk-hk-zh"),
    }

    def _clip(lid: str, name: str):
        folder = lesson_out_dir(lid, module=False, root=out_root) / "cells"
        for cand in cell_alias.get(name, (name,)):
            hit = folder / f"{lid}_{cand}.mp4"
            if hit.is_file():
                return hit
        return None

    names: set[str] = set()
    for lid in members:
        folder = lesson_out_dir(lid, module=False, root=out_root) / "cells"
        if not folder.is_dir():
            continue
        for mp4 in folder.glob("*.mp4"):
            raw = mp4.stem
            prefix = f"{lid}_"
            suf = raw[len(prefix) :] if raw.startswith(prefix) else raw
            if suf.endswith("_nocap"):
                continue
            names.add(suf)
            if suf in {"en", "en-en"}:
                names.add("en")
            if suf in {"zh", "zhcn", "zh-zh"}:
                names.add("zh")
            if suf in {"hk", "zhhk", "zh_hk"}:
                names.add("hk")
    print("module child versions:", ", ".join(sorted(names)) or "(none)")
    if wanted_cells:
        file_name = {
            "en": "en",
            "en-en": "en",
            "zh": "zh",
            "zh_cn": "zh",
            "zhcn": "zh",
            "zh-zh": "zh",
            "hk": "hk",
            "zh_hk": "hk",
            "zhhk": "hk",
            "en+zh": "en+zh",
            "en-en-zh": "en+zh",
            "en+hk": "en+hk",
            "en-en-hk": "en+hk",
            "zh+en": "zh+en",
            "zh-zh-en": "zh+en",
            "zh+hk": "zh+hk",
            "zh-zh-hk": "zh+hk",
            "hk+en": "hk+en",
            "hk-hk-en": "hk+en",
            "hk+zh": "hk+zh",
            "hk-hk-zh": "hk+zh",
        }
        wanted = {file_name.get(w, w) for w in wanted_cells}
        names = {file_name.get(n, n) for n in names if file_name.get(n, n) in wanted}
        for w in sorted(wanted):
            if w not in names:
                print(f"module missing {w}: no child wrote that video — join will skip it")
    if not names:
        raise SystemExit(f"No child videos found for module {mid}.")
    for name in sorted(names):
        clips: list[Path] = []
        srt_parts: list[tuple[Path, float]] = []
        missing = []
        for lid in members:
            clip = _clip(lid, name)
            if clip is None:
                missing.append(f"{lid}_{name}.mp4")
                continue
            clips.append(clip)
            dur = probe_duration(clip)
            base = name.removesuffix("_nocap")
            srt_parts.append((lesson_out_dir(lid, module=False, root=out_root) / "srt" / f"{base}.srt", dur))
        if missing:
            print(f"module skip {name}: missing {', '.join(missing)}")
            continue
        dest = cell_dir / f"{mid}_{name}.mp4"
        print(f"progress: module-join {name}")
        print(f"module concat: {dest.name} ({len(clips)} lessons)")
        concat_clips(clips, dest)
        if not name.endswith("_nocap"):
            _concat_srts(srt_parts, srt_dir / f"{name}.srt")
        print("cell:", dest, f"({probe_duration(dest):.1f}s)")
    if experiment_pack:
        from langs import selected_cells

        first_path = lesson_path(members[0])
        if first_path is None:
            return
        first = load_lesson(first_path)
        cells = selected_cells(first, wanted_cells)
        csv_path = write_experiment_pack(out_dir, mid, cells, pack_speeds or parse_speeds(None))
        print("experiment-pack:", csv_path)
    clock.lap("join")
    print(f"module: done {mid}")
    clock.total()

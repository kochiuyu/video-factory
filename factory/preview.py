#!/usr/bin/env python3
"""Stamp caption bars onto slides so wrapping can be checked before mux."""

from __future__ import annotations

import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

import hashlib
import json
import os
import time

from langs import bilingual_pair, label_code, script_langs
from mux import _caption_card, _caption_letters, caption_pages, stage_scripts
from slides import lesson_stamp, list_slide_pngs, render_lesson_slides, stamp_matches, write_stamp, write_stage_slides


def _preview_workers() -> int:
    raw = os.environ.get("VF_PREVIEW_JOBS") or os.environ.get("VF_CLIP_JOBS", "3")
    try:
        n = int(str(raw).strip() or "3")
    except ValueError:
        n = 3
    cpu = os.cpu_count() or 2
    return max(1, min(n, 4, cpu))


def _stamp_caption_frame(slide: Path, page: str, bar_path: Path, dest: Path) -> tuple[Path, str | None]:
    try:
        if not slide.is_file():
            raise FileNotFoundError(slide)
        bar = _caption_card(page, bar_path)
        base = Image.open(slide).convert("RGBA")
        overlay = Image.open(bar).convert("RGBA")
        if overlay.size != base.size:
            overlay = overlay.resize(base.size)
        base.paste(overlay, (0, 0), overlay)
        dest.parent.mkdir(parents=True, exist_ok=True)
        base.convert("RGB").save(dest, "PNG")
        return dest, None
    except Exception as exc:  # noqa: BLE001
        return dest, f"{type(exc).__name__}: {exc}"


def _beat_for_slide(path: Path, beats: list[dict]) -> dict | None:
    stem = path.stem
    core = re.sub(r"_s\d+$", "", stem)
    core = re.sub(r"_c\d+$", "", core)
    bid = core.split("_", 1)[1] if "_" in core else core
    for beat in beats:
        if beat.get("id") == bid:
            return beat
    print(f"preview warn: no beat id {bid!r} for {path.name}")
    return None


def render_caption_previews(
    lesson: dict,
    slides: list[Path],
    out_dir: Path,
    langs: list[str] | None = None,
    match_titles: bool = False,
    shared_slides: list[Path] | None = None,
    theme: dict | None = None,
    stage_cards: bool = True,
    cells: dict[str, tuple[str, str, str]] | None = None,
) -> list[Path]:
    langs = list(langs) if langs else script_langs(lesson)
    beats = lesson["beats"]
    written: list[Path] = []
    failures: list[str] = []
    durations = [float(beat.get("seconds") or 20) for beat in beats]
    plans: list[tuple[str, str, str, str | None, str]] = []
    if cells:
        for name, (voice, _cap, slide) in cells.items():
            code, second = bilingual_pair(voice, _cap, slide)
            slide_folder = code if not second else f"{code}+{second}"
            plans.append((name, voice, code, second, slide_folder))
    if not plans:
        for lang in langs:
            code = label_code(lang) if match_titles else label_code(langs[0])
            plans.append((lang, lang, code, None, code))
    keep = {folder for _name, _voice, _code, _second, folder in plans}
    preview_root = out_dir / "preview"
    if preview_root.is_dir():
        for child in preview_root.iterdir():
            if child.is_dir() and child.name not in keep and child.name != "_bars":
                shutil.rmtree(child, ignore_errors=True)
    done_folders: set[str] = set()
    unique = []
    for _n, _v, _c, _s, folder in plans:
        if folder not in unique:
            unique.append(folder)
    plan_n = max(1, len(unique))
    plan_i = 0
    for name, lang, code, second, folder in plans:
        if folder in done_folders:
            continue
        done_folders.add(folder)
        plan_i += 1
        fold_t0 = time.perf_counter()
        slide_dir = out_dir / "slides" / folder
        pack = sorted(p for p in slide_dir.glob("*.png")) if slide_dir.is_dir() else []
        need = lesson_stamp(lesson, theme, code, second, stage_cards)
        try:
            if not pack or not stamp_matches(slide_dir, need):
                pack = render_lesson_slides(
                    lesson, slide_dir, label_lang=code, theme=theme, second_lang=second
                )
                write_stamp(slide_dir, need)
                print(f"preview slides rebuilt {folder} ({len(pack)} png)")
            if stage_cards:
                staged, _holds = write_stage_slides(
                    lesson,
                    slide_dir,
                    code,
                    durations,
                    theme=theme,
                    force=True,
                    second_lang=second,
                )
                if staged:
                    pack = staged
        except Exception as exc:  # noqa: BLE001
            msg = f"preview cannot paint slides {folder}: {type(exc).__name__}: {exc}"
            print(msg)
            failures.append(msg)
            continue
        pack = [p for p in pack if p.is_file()]
        if not pack:
            msg = f"preview skip {folder}: no slide PNGs in {slide_dir}"
            print(msg)
            failures.append(msg)
            continue
        dest_dir = out_dir / "preview" / folder
        cap_opts = {
            "size": os.environ.get("VF_CAPTION_SIZE", ""),
            "align": os.environ.get("VF_CAPTION_ALIGN", ""),
            "lines": os.environ.get("VF_CAPTION_LINES", ""),
            "opacity": os.environ.get("VF_CAPTION_OPACITY", ""),
            "lang": lang,
            "slides": lesson_stamp(lesson, theme, code, second, stage_cards),
            "scripts": [stage_scripts(beat, lang, 8) for beat in beats],
            "v": "2026-09-19-preview-stage-lines",
        }
        cap_stamp = hashlib.sha256(
            json.dumps(cap_opts, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:20]
        if stamp_matches(dest_dir, cap_stamp):
            kept = list_slide_pngs(dest_dir)
            written.extend(kept)
            print(f"preview reuse {folder} ({len(kept)} png)")
            print(f"progress: preview {plan_i}/{plan_n} {folder} reuse")
            print(f"timing: captions {folder} {time.perf_counter() - fold_t0:.1f}s")
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        for stale in dest_dir.glob("*.png"):
            stale.unlink()
        cap_dir = out_dir / "preview" / "_bars" / lang
        jobs: list[tuple[Path, str, Path, Path]] = []

        def stage_num(path: Path) -> int:
            m = re.search(r"_s(\d+)$", path.stem)
            return int(m.group(1)) if m else 0

        grouped: dict[str, list[tuple[Path, dict]]] = {}
        for slide in pack:
            beat = _beat_for_slide(slide, beats)
            if beat is None:
                failures.append(f"preview skip unmatched {slide.name}")
                continue
            grouped.setdefault(beat["id"], []).append((slide, beat))
        for items in grouped.values():
            beat = items[0][1]
            slides_for = [s for s, _ in items]
            staged = [s for s in slides_for if stage_num(s)]
            if staged:
                slides_for = sorted(staged, key=stage_num)
            else:
                slides_for = sorted(slides_for, key=lambda p: p.name)
            chunks = stage_scripts(beat, lang, len(slides_for))
            pages_all: list[str] = []
            for slide, chunk in zip(slides_for, chunks):
                pages = caption_pages(chunk)
                pages_all.extend(pages)
                for i, page in enumerate(pages, start=1):
                    stem = slide.stem if len(pages) == 1 else f"{slide.stem}_c{i}"
                    jobs.append((slide, page, cap_dir / f"{stem}.png", dest_dir / f"{stem}.png"))
            expected = "".join(chunks)
            if _caption_letters(expected) != _caption_letters("".join(pages_all)):
                print(f"preview coverage miss {beat.get('id')} {lang}")
        workers = _preview_workers()
        print(f"preview stamp {folder}: {len(jobs)} frames, {workers} workers")
        if jobs:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = [pool.submit(_stamp_caption_frame, *job) for job in jobs]
                for fut in as_completed(futs):
                    dest, err = fut.result()
                    if err:
                        msg = f"preview fail {folder}/{dest.stem}: {err}"
                        print(msg)
                        failures.append(msg)
                    else:
                        written.append(dest)
        if any(dest_dir.glob("*.png")):
            write_stamp(dest_dir, cap_stamp)
        print(f"progress: preview {plan_i}/{plan_n} {folder}")
        print(f"timing: captions {folder} {time.perf_counter() - fold_t0:.1f}s")
    if not written:
        detail = "; ".join(failures[:6]) or "no caption frames"
        raise RuntimeError(f"caption preview wrote no frames ({detail})")
    if failures:
        print(f"preview notes: {len(failures)} issue(s), {len(written)} frames kept")
    return written

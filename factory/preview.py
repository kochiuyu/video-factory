#!/usr/bin/env python3
"""Stamp caption bars onto slides so wrapping can be checked before mux."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from PIL import Image

import hashlib
import json
import os

from langs import beat_text, bilingual_pair, label_code, script_langs
from mux import _caption_card, _caption_letters, caption_pages, script_chunks
from slides import lesson_stamp, list_slide_pngs, render_lesson_slides, stamp_matches, write_stamp, write_stage_slides


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
        slide_dir = out_dir / "slides" / folder
        pack = sorted(p for p in slide_dir.glob("*.png")) if slide_dir.is_dir() else []
        need = lesson_stamp(lesson, theme, code, second, stage_cards)
        if not pack or not stamp_matches(slide_dir, need):
            try:
                pack = render_lesson_slides(
                    lesson, slide_dir, label_lang=code, theme=theme, second_lang=second
                )
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
                write_stamp(slide_dir, need)
                print(f"preview slides rebuilt {folder} ({len(pack)} png)")
            except Exception as exc:  # noqa: BLE001
                msg = f"preview cannot paint slides {folder}: {type(exc).__name__}: {exc}"
                print(msg)
                failures.append(msg)
                continue
        pack = [p for p in pack if p.is_file()]
        staged = [p for p in pack if re.search(r"_s\d+$", p.stem)]
        if staged:
            pack = staged
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
            "scripts": [beat_text(beat, lang) for beat in beats],
            "v": "2026-09-13-full-script",
        }
        cap_stamp = hashlib.sha256(
            json.dumps(cap_opts, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:20]
        if stamp_matches(dest_dir, cap_stamp):
            kept = list_slide_pngs(dest_dir)
            written.extend(kept)
            print(f"preview reuse {folder} ({len(kept)} png)")
            print(f"progress: preview {plan_i}/{plan_n} {folder} reuse")
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        for stale in dest_dir.glob("*.png"):
            stale.unlink()
        cap_dir = out_dir / "preview" / "_bars" / lang

        def stamp(slide: Path, page: str, stem: str) -> None:
            try:
                if not slide.is_file():
                    raise FileNotFoundError(slide)
                bar = _caption_card(page, cap_dir / f"{stem}.png")
                base = Image.open(slide).convert("RGBA")
                overlay = Image.open(bar).convert("RGBA")
                if overlay.size != base.size:
                    overlay = overlay.resize(base.size)
                base.paste(overlay, (0, 0), overlay)
                dest = dest_dir / f"{stem}.png"
                base.convert("RGB").save(dest, "PNG")
                written.append(dest)
                print(f"preview {lang}/{stem}")
            except Exception as exc:  # noqa: BLE001
                msg = f"preview fail {folder}/{stem}: {type(exc).__name__}: {exc}"
                print(msg)
                failures.append(msg)

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
            text = beat_text(beat, lang)
            pages_all: list[str] = []
            if len(slides_for) > 1:
                chunks = script_chunks(text, len(slides_for))
                for slide, chunk in zip(slides_for, chunks):
                    pages = caption_pages(chunk)
                    pages_all.extend(pages)
                    for i, page in enumerate(pages, start=1):
                        stem = slide.stem if len(pages) == 1 else f"{slide.stem}_c{i}"
                        stamp(slide, page, stem)
            else:
                pages = caption_pages(text)
                pages_all = pages
                slide = slides_for[0]
                for i, page in enumerate(pages, start=1):
                    stem = slide.stem if len(pages) == 1 else f"{slide.stem}_c{i}"
                    stamp(slide, page, stem)
            if _caption_letters(text) != _caption_letters("".join(pages_all)):
                print(f"preview coverage miss {beat.get('id')} {lang}")
        if any(dest_dir.glob("*.png")):
            write_stamp(dest_dir, cap_stamp)
        print(f"progress: preview {plan_i}/{plan_n} {folder}")
    if not written:
        detail = "; ".join(failures[:6]) or "no caption frames"
        raise RuntimeError(f"caption preview wrote no frames ({detail})")
    if failures:
        print(f"preview notes: {len(failures)} issue(s), {len(written)} frames kept")
    return written

#!/usr/bin/env python3
"""Local web console for the video factory.

After a YAML file exists, open this page and click Build.
No further typing is required for production.

  python3 factory/app.py
  # then open http://127.0.0.1:8765
"""

from __future__ import annotations

import sys
from pathlib import Path as _PathForBoot

_FACTORY = _PathForBoot(__file__).resolve().parent
sys.path.insert(0, str(_FACTORY))
try:
    from utf8io import force_utf8  # noqa: E402
except ModuleNotFoundError:
    import os as _os

    def force_utf8() -> None:
        _os.environ.setdefault("PYTHONUTF8", "1")
        _os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            reconf = getattr(stream, "reconfigure", None)
            if reconf is None:
                continue
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass

force_utf8()

import argparse
import html
import json
import mimetypes
import os
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
import re
import yaml
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
FACTORY = Path(__file__).resolve().parent
LESSONS = ROOT / "lessons"
MODULES = ROOT / "modules"
sys.path.insert(0, str(FACTORY))


def _rel_to_root(path: Path | str) -> str:
    """Project-relative POSIX path so a Dropbox copy works on another PC."""
    raw = Path(path)
    try:
        return raw.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        name = raw.name
        if raw.parent.name and raw.parent.name != ".":
            return f"{raw.parent.name}/{name}"
        return name

from langs import beat_text, bilingual_pair, cells_for, is_tri, script_langs, selected_cells  # noqa: E402
from build import write_cell_covers  # noqa: E402
from modules import load_module, module_errors  # noqa: E402
from catalog import existing_out_dir as lesson_out_dir, media_href, migrate_out_layout, out_dir as new_out_dir, out_root  # noqa: E402
from quiz import export_lesson_quiz, export_module_quiz  # noqa: E402
from pdfexport import export_preview_pdfs  # noqa: E402
from bundle import COURSES, course_of, write_course_zip, write_ra_zip, write_sop  # noqa: E402
from glyphs import scan_lesson  # noqa: E402
from validate import load_lesson, validate  # noqa: E402
from xlsx_lesson import export_lesson, import_workbook  # noqa: E402
from theme import list_themes  # noqa: E402

CELL_LABELS = {
    "en": "English · matched",
    "zh": "Putonghua · matched",
    "hk": "Cantonese · matched",
    "en+zh": "English · 简 slides",
    "en+hk": "English · 繁 slides",
    "zh+en": "Putonghua · EN slides",
    "zh+hk": "Putonghua · 繁 slides",
    "hk+en": "Cantonese · EN slides",
    "hk+zh": "Cantonese · 简 slides",
}

HOST = "127.0.0.1"
PORT = 8765

_job_lock = threading.Lock()
_job: dict = {
    "status": "idle",
    "log": "",
    "step": "Idle",
    "detail": "",
    "pct": 0,
    "lesson": None,
    "cells": [],
    "slides": [],
    "previews": [],
    "log_url": "/media/last_build.log",
    "latest_url": "/media/last_build.log",
    "log_path": "",
    "elapsed": "0:00",
    "elapsed_s": 0,
    "timing": "",
}


def _member_ids(lid: str) -> list[str]:
    from catalog import MINICOURSES
    path = MODULES / f"{lid}.yaml"
    if not path.exists():
        path = MINICOURSES / f"{lid}.yaml"
    if not path.exists():
        return []
    try:
        mod = load_module(path)
    except Exception:
        return []
    return [str(x) for x in (mod.get("lessons") or []) if x]


def _preview_urls(lid: str) -> list[str]:
    folder = lesson_out_dir(lid) / "preview"
    lang_order = {"en": 0, "zh_cn": 1, "zh": 1, "zh_hk": 2}
    rows = []
    if folder.is_dir():
        for lang_dir in folder.iterdir():
            if not lang_dir.is_dir() or lang_dir.name == "_bars":
                continue
            names = _drop_base_if_staged(sorted(p.name for p in lang_dir.glob("*.png")))
            for name in names:
                rows.append((name, lang_order.get(lang_dir.name, 9), lang_dir.name))
    rows.sort()
    urls = [media_href(lid, "preview", lang, fname) for fname, _rank, lang in rows]
    for child in _member_ids(lid):
        if child != lid:
            urls.extend(_preview_urls(child))
    return urls


def _cell_urls(lid: str) -> list[str]:
    urls: list[str] = []
    folder = lesson_out_dir(lid) / "cells"
    if folder.is_dir():
        urls.extend(media_href(lid, "cells", p.name) for p in sorted(folder.glob("*.mp4")))
    pack = lesson_out_dir(lid) / "pack"
    if pack.is_dir():
        urls.extend(media_href(lid, "pack", p.name) for p in sorted(pack.glob("*.mp4")))
    for child in _member_ids(lid):
        if child != lid:
            urls.extend(_cell_urls(child))
    return urls


def _all_cell_urls() -> list[str]:
    urls: list[str] = []
    root = out_root()
    if not root.is_dir():
        return urls
    for kind in ("lessons", "modules"):
        base = root / kind
        if not base.is_dir():
            continue
        for folder in sorted(base.iterdir()):
            cells = folder / "cells"
            if not cells.is_dir():
                continue
            for mp4 in sorted(cells.glob("*.mp4")):
                urls.append(media_href(folder.name, "cells", mp4.name))
    return urls


def _drop_base_if_staged(names: list[str]) -> list[str]:
    import re

    staged = {
        re.sub(r"_s\d+$", "", Path(n).stem)
        for n in names
        if re.search(r"_s\d+$", Path(n).stem)
    }
    out = []
    for name in names:
        stem = Path(name).stem
        if re.search(r"_s\d+$", stem) or re.search(r"_c\d+$", stem):
            out.append(name)
            continue
        if stem in staged:
            continue
        out.append(name)
    return out


def _slide_urls(lid: str) -> list[str]:
    root = lesson_out_dir(lid) / "slides"
    rank = {"en": 0, "zh": 1, "zh_cn": 1, "zh_hk": 2}
    rows = []
    if root.is_dir():
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            names = _drop_base_if_staged(sorted(p.name for p in folder.glob("*.png")))
            for name in names:
                rows.append((rank.get(folder.name, 8), folder.name, name))
    rows.sort()
    urls = [media_href(lid, "slides", lang, fname) for _rank, lang, fname in rows]
    for child in _member_ids(lid):
        if child != lid:
            urls.extend(_slide_urls(child))
    return urls


def _cover_urls(lid: str) -> list[str]:
    urls: list[str] = []
    folder = lesson_out_dir(lid) / "covers"
    if folder.is_dir():
        urls.extend(media_href(lid, "covers", item.name) for item in sorted(folder.glob("*.png")))
    for child in _member_ids(lid):
        if child != lid:
            urls.extend(_cover_urls(child))
    return urls


def resolve_yaml(filename: str) -> Path | None:
    from catalog import lesson_path

    name = Path(filename).name
    found = lesson_path(name)
    if found is not None:
        return found
    path = MODULES / name
    if path.suffix in {".yaml", ".yml"} and path.exists():
        return path
    from catalog import MINICOURSES
    path = MINICOURSES / name
    if path.suffix in {".yaml", ".yml"} and path.exists():
        return path
    return None


def _speech_errors(errors: list[str], lesson: dict) -> list[str]:
    """Drop stale 'missing en' flags when s1/s2 speech is present."""
    import re

    beats = {str(b.get("id")): b for b in (lesson.get("beats") or [])}
    out = []
    for err in errors:
        m = re.match(r"Beat (\S+) missing (en|zh / zh_cn) narration", str(err))
        if m:
            lang = "en" if "en narration" in str(err) else "zh"
            if beat_text(beats.get(m.group(1), {}), lang):
                continue
        if str(err).startswith("Some beats have zh_hk") and all(
            beat_text(b, "zh_hk") for b in (lesson.get("beats") or [])
        ):
            continue
        out.append(err)
    return out


def lesson_inspect(filename: str) -> dict:
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "error": "Lesson file not found."}
    try:
        raw = path.read_text(encoding="utf-8")
        if path.parent.name == "minicourses":
            mod = load_module(path)
            errors = []
            if not mod.get("id"):
                errors.append("Missing field: id")
            ids = list(mod.get("lessons") or [])
            if len(ids) < 2:
                errors.append("A mini-course needs at least two lessons.")
            members = []
            for i, lid in enumerate(ids, start=1):
                from catalog import lesson_path as _lesson_path
                child = _lesson_path(lid)
                title = lid
                seconds = ""
                if child is None:
                    errors.append(f"Lesson not found: {lid}.yaml")
                else:
                    les = load_lesson(child)
                    title = les.get("title_en") or lid
                    seconds = les.get("duration_target_s") or ""
                members.append({"n": i, "id": lid, "title": {"en": title, "zh": "", "zh_hk": ""}, "seconds": seconds, "visual": "lesson", "formula": {}, "gloss": {}, "script": {"en": "", "zh": "", "zh_hk": ""}})
            return {
                "ok": True,
                "file": path.name,
                "kind": "minicourse",
                "id": mod.get("id") or path.stem,
                "title": {"en": mod.get("title_en") or "", "zh": mod.get("title_zh") or "", "zh_hk": mod.get("title_zh_hk") or ""},
                "course": {"en": mod.get("course_en") or "", "zh": mod.get("course_zh") or "", "zh_hk": mod.get("course_zh_hk") or ""},
                "audience": {"en": "", "zh": "", "zh_hk": ""},
                "objective": {"en": mod.get("objective_en") or "", "zh": mod.get("objective_zh") or "", "zh_hk": mod.get("objective_zh_hk") or ""},
                "errors": errors,
                "beats": members,
                "glossary": [],
                "quiz": [],
                "raw": raw,
            }
        if path.parent.name == "modules":
            mod = load_module(path)
            errors = module_errors(mod)
            members = []
            for i, lid in enumerate(mod.get("lessons") or [], start=1):
                from catalog import lesson_path as _lesson_path

                child = _lesson_path(lid)
                title = lid
                seconds = ""
                if child is not None:
                    les = load_lesson(child)
                    title = les.get("title_en") or lid
                    seconds = les.get("duration_target_s") or ""
                members.append({"n": i, "id": lid, "title": {"en": title, "zh": "", "zh_hk": ""}, "seconds": seconds, "visual": "lesson", "formula": {}, "gloss": {}, "script": {"en": "", "zh": "", "zh_hk": ""}})
            return {
                "ok": True,
                "file": path.name,
                "id": mod.get("id") or path.stem,
                "kind": "module",
                "title": {
                    "en": mod.get("title_en") or "",
                    "zh": mod.get("title_zh") or "",
                    "zh_hk": mod.get("title_zh_hk") or "",
                },
                "course": {
                    "en": mod.get("course_en") or mod.get("course") or "",
                    "zh": mod.get("course_zh") or "",
                    "zh_hk": mod.get("course_zh_hk") or "",
                },
                "audience": {},
                "children": [
                    {"file": f"{m['id']}.yaml", "id": m["id"], "title": m["title"]["en"]}
                    for m in members
                ],
                "objective": {
                    "en": mod.get("objective_en") or "",
                    "zh": mod.get("objective_zh") or "",
                    "zh_hk": mod.get("objective_zh_hk") or "",
                },
                "duration": mod.get("duration_target_s") or "",
                "beats": members,
                "used": [],
                "gaps": [e for e in errors if "Stacked target" not in e],
                "errors": errors,
                "valid": not [e for e in errors if "Stacked target" not in e],
                "yaml": raw,
            }
        lesson = load_lesson(path)
        errors = _speech_errors(validate(lesson, glyphs=False), lesson)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    langs = (("en", "EN"), ("zh", "简"), ("zh_hk", "繁"))

    def trio(obj: dict, stem: str) -> dict:
        return {
            "en": (obj.get(f"{stem}_en") or "").strip(),
            "zh": (obj.get(f"{stem}_zh") or obj.get(f"{stem}_zh_cn") or "").strip(),
            "zh_hk": (obj.get(f"{stem}_zh_hk") or "").strip(),
        }

    def need(values: dict, where: str, label: str, required: bool = False) -> None:
        if required or any(values.values()):
            for key, lab in langs:
                if not values.get(key):
                    gaps.append(f"{where}: missing {label} ({lab})")

    beats = []
    gaps = []
    need(trio(lesson, "title"), "lesson", "title", required=True)
    for stem in ("course", "audience", "objective", "kicker"):
        need(trio(lesson, stem), "lesson", stem)
    extra = ("left", "right", "mid", "setup", "result", "q1", "q2",
             "col1", "col2", "col3", "step1", "step2", "step3", "unit", "caption",
             "claim", "body", "note", "row_player", "col_player", "row1", "row2",
             "item1", "item2", "item3", "item4", "next", "s1", "s2", "s3", "s4", "s5")
    used = set()
    known = ["kicker", "formula", "gloss", "left", "right", "mid", "setup", "result",
             "col1", "col2", "col3", "step1", "step2", "step3", "q1", "q2",
             "number", "unit", "caption", "claim", "body", "note"]

    def stems_of(obj: dict) -> list[str]:
        found = []
        for key in obj:
            if not isinstance(key, str):
                continue
            for suf in ("_zh_hk", "_zh_cn", "_en", "_zh"):
                if key.endswith(suf):
                    stem = key[: -len(suf)]
                    if stem and stem not in {"title"} and stem not in found:
                        found.append(stem)
                    break
        return found
    for i, beat in enumerate(lesson.get("beats") or [], start=1):
        titles = trio(beat, "title")
        scripts = {
            "en": (beat.get("en") or "").strip(),
            "zh": (beat.get("zh") or beat.get("zh_cn") or "").strip(),
            "zh_hk": (beat.get("zh_hk") or "").strip(),
        }
        if not any(scripts.values()):
            from langs import beat_text as _beat_text, stage_lines as _stage_lines
            if not any(_stage_lines(beat, "en")):
                scripts = {
                    "en": _beat_text(beat, "en"),
                    "zh": _beat_text(beat, "zh"),
                    "zh_hk": _beat_text(beat, "zh_hk"),
                }
        formula = {
            "en": (beat.get("formula_en") or beat.get("formula") or "").strip(),
            "zh": (beat.get("formula_zh") or beat.get("formula_zh_cn") or "").strip(),
            "zh_hk": (beat.get("formula_zh_hk") or "").strip(),
        }
        gloss = trio(beat, "gloss")
        kicker = trio(beat, "kicker")
        bid = beat.get("id") or f"beat-{i}"
        row = {
            "n": i,
            "id": bid,
            "visual": beat.get("visual") or "",
            "seconds": beat.get("seconds") or "",
            "kicker": kicker,
            "title": titles,
            "formula": formula,
            "gloss": gloss,
            "script": scripts,
            "number": "" if beat.get("number") is None else str(beat.get("number")),
        }
        for stem in extra:
            row[stem] = trio(beat, stem)
            if any(row[stem].values()):
                used.add(stem)
        for stem in stems_of(beat):
            if stem in {"en", "zh", "zh_cn", "zh_hk"}:
                continue
            if stem not in row:
                row[stem] = trio(beat, stem)
            if any(row[stem].values()):
                used.add(stem)
        local = []
        if any(kicker.values()):
            used.add("kicker")
            local.append("kicker")
        if any(formula.values()):
            used.add("formula")
            local.append("formula")
        if any(gloss.values()):
            used.add("gloss")
            local.append("gloss")
        if row["number"]:
            used.add("number")
        beats.append(row)
        need(titles, bid, "title", required=True)
        if any(scripts.values()):
            need(scripts, bid, "speech", required=True)
        elif not any((row.get("s1") or {}).values()):
            need(scripts, bid, "speech", required=True)
        if beat.get("visual") == "takeaway":
            need(row.get("q1") or {}, bid, "q1", required=True)
            need(row.get("q2") or {}, bid, "q2", required=True)
        for stem in local:
            need(row[stem], bid, stem)
        for stem in extra:
            if stem in row and isinstance(row[stem], dict) and any(row[stem].values()):
                need(row[stem], bid, stem)
    glossary = []
    for gi, raw_g in enumerate(lesson.get("glossary") or [], start=1):
        if not isinstance(raw_g, dict):
            continue
        item = {
            "en": (raw_g.get("en") or "").strip(),
            "zh": (raw_g.get("zh") or raw_g.get("zh_cn") or "").strip(),
            "zh_hk": (raw_g.get("zh_hk") or "").strip(),
        }
        glossary.append(item)
        need(item, f"glossary {gi}", "term", required=True)
    quiz_rows = []
    for qi, qraw in enumerate(lesson.get("quiz") or [], start=1):
        if not isinstance(qraw, dict):
            continue
        qid = str(qraw.get("id") or f"Q{qi}")
        prompt = {
            "en": (qraw.get("en") or qraw.get("prompt_en") or "").strip(),
            "zh": (qraw.get("zh") or qraw.get("prompt_zh") or "").strip(),
            "zh_hk": (qraw.get("zh_hk") or qraw.get("prompt_zh_hk") or "").strip(),
        }
        answer = {
            "en": (qraw.get("answer_en") or "").strip(),
            "zh": (qraw.get("answer_zh") or "").strip(),
            "zh_hk": (qraw.get("answer_zh_hk") or "").strip(),
        }
        need(prompt, f"quiz {qid}", "prompt", required=True)
        if any(answer.values()):
            need(answer, f"quiz {qid}", "answer")
        quiz_rows.append({"id": qid, "type": qraw.get("type") or "", "prompt": prompt, "answer": answer})
    return {
        "ok": True,
        "file": path.name,
        "kind": "lesson",
        "id": lesson.get("id") or path.stem,
        "title": trio(lesson, "title"),
        "course": trio(lesson, "course"),
        "audience": trio(lesson, "audience"),
        "objective": trio(lesson, "objective"),
        "duration": lesson.get("duration_target_s") or "",
        "beats": beats,
        "columns": known,
        "used": sorted(used, key=lambda s: known.index(s) if s in known else 80 + len(s)),
        "quiz": quiz_rows,
        "glossary": glossary,
        "gaps": list(dict.fromkeys(list(errors) + gaps)),
        "errors": errors,
        "has_backup": path.with_suffix(path.suffix + ".bak").exists(),
        "valid": not [e for e in errors if not str(e).startswith("Beat seconds")],
        "yaml": raw,
    }


def _dump_yaml(data: dict) -> str:
    def represent_str(dumper, value):
        style = "|" if "\n" in value else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)

    yaml.add_representer(str, represent_str)
    return yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=92,
    )


def _apply_trio(obj: dict, stem: str, values: dict | None, *, plain: dict | None = None) -> None:
    if not values:
        return
    mapping = plain or {
        "en": f"{stem}_en",
        "zh": f"{stem}_zh",
        "zh_hk": f"{stem}_zh_hk",
    }
    for lang, key in mapping.items():
        if lang not in values:
            continue
        text = values[lang]
        if text is None:
            continue
        obj[key] = text
        cn_key = f"{stem}_zh_cn" if stem else "zh_cn"
        if lang == "zh" and cn_key in obj:
            obj[cn_key] = text


def restore_lesson_backup(filename: str) -> dict:
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "error": "Lesson file not found."}
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        return {"ok": False, "error": "No backup yet. Save once in Author to create a .bak."}
    path.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
    invalidate_list_cache()
    invalidate_paint_cache(path.stem)
    return {"ok": True, "file": path.name, "restored": bak.name}


def save_light_edits(filename: str, payload: dict) -> dict:
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "error": "Lesson file not found."}
    if payload.get("restore"):
        return restore_lesson_backup(filename)
    if path.parent.name == "modules":
        data = load_module(path)
        data.pop("_path", None)
        _apply_trio(data, "title", payload.get("title"))
        _apply_trio(data, "objective", payload.get("objective"))
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(_dump_yaml(data), encoding="utf-8")
        invalidate_list_cache()
        invalidate_paint_cache(data.get("id") or path.stem)
        return {"ok": True, "file": path.name, "kind": "module", "backup": bak.name}

    lesson = load_lesson(path)
    _apply_trio(lesson, "title", payload.get("title"))
    _apply_trio(lesson, "objective", payload.get("objective"))
    _apply_trio(lesson, "course", payload.get("course"))
    _apply_trio(lesson, "audience", payload.get("audience"))
    if payload.get("duration") not in (None, ""):
        try:
            lesson["duration_target_s"] = int(float(payload["duration"]))
        except (TypeError, ValueError):
            pass
    by_id = {str(b.get("id")): b for b in lesson.get("beats") or []}
    rebuilt = []
    for row in payload.get("beats") or []:
        bid = str(row.get("id") or "").strip() or f"beat-{len(rebuilt)+1}"
        beat = by_id.get(bid) or {"id": bid}
        beat["id"] = bid
        visual = (row.get("visual") or beat.get("visual") or "title_card").strip()
        beat["visual"] = visual
        _apply_trio(beat, "title", row.get("title"))
        fields = row.get("fields") or {}
        staged = any(isinstance(fields.get(f"s{i}"), dict) and any((fields.get(f"s{i}") or {}).values()) for i in range(1, 6))
        script = row.get("script") or {}
        zh_key = "zh_cn" if "zh_cn" in beat else "zh"
        if staged:
            for key in ("en", "zh", "zh_cn", "zh_hk"):
                beat.pop(key, None)
        else:
            _apply_trio(
                beat,
                "",
                script,
                plain={"en": "en", "zh": zh_key, "zh_hk": "zh_hk"},
            )
        if row.get("seconds") not in (None, ""):
            try:
                beat["seconds"] = float(row["seconds"])
            except (TypeError, ValueError):
                pass
        for stem, values in fields.items():
            if stem in {"en", "zh", "zh_cn", "zh_hk", "id", "visual"}:
                continue
            if not isinstance(values, dict):
                beat[stem] = values
                continue
            _apply_trio(beat, stem, values)
        rebuilt.append(beat)
    if rebuilt:
        lesson["beats"] = rebuilt
    if payload.get("quiz") is not None:
        quiz_out = []
        for i, row in enumerate(payload.get("quiz") or [], start=1):
            if not isinstance(row, dict):
                continue
            qid = str(row.get("id") or f"Q{i}").strip() or f"Q{i}"
            prompt = row.get("prompt") or {}
            answer = row.get("answer") or {}
            quiz_out.append({
                "id": qid,
                "type": row.get("type") or "comprehension",
                "en": prompt.get("en") or "",
                "zh": prompt.get("zh") or "",
                "zh_hk": prompt.get("zh_hk") or "",
                "answer_en": answer.get("en") or "",
                "answer_zh": answer.get("zh") or "",
                "answer_zh_hk": answer.get("zh_hk") or "",
            })
        lesson["quiz"] = quiz_out
    if payload.get("glossary") is not None:
        gloss_out = []
        for row in payload.get("glossary") or []:
            if not isinstance(row, dict):
                continue
            item = {
                "en": row.get("en") or "",
                "zh": row.get("zh") or "",
                "zh_hk": row.get("zh_hk") or "",
            }
            if row.get("lock"):
                item["lock"] = True
            gloss_out.append(item)
        lesson["glossary"] = gloss_out
    errors = validate(lesson, glyphs=False)
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(_dump_yaml(lesson), encoding="utf-8")
    invalidate_list_cache()
    invalidate_paint_cache(lesson.get("id") or path.stem)
    return {
        "ok": True,
        "file": path.name,
        "kind": "lesson",
        "backup": bak.name,
        "errors": errors,
        "valid": not [e for e in errors if not e.startswith("Beat seconds")],
    }


def export_quiz_now(filename: str) -> dict:
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "error": "Select a lesson first."}
    if path.parent.name == "modules":
        mod = load_module(path)
        lid = mod.get("id") or path.stem
        files = export_module_quiz(mod, lesson_out_dir(lid, module=True))
    else:
        lesson = load_lesson(path)
        lid = lesson.get("id") or path.stem
        files = export_lesson_quiz(lesson, lesson_out_dir(lid, module=False))
    urls = [media_href(lid, "quiz", p.name) for p in files]
    return {"ok": True, "id": lid, "files": urls, "count": len(files)}


def export_pdf_now(filename: str, kind: str = "") -> dict:
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "error": "Select a lesson or module first."}
    if path.parent.name == "modules":
        lid = (load_module(path).get("id") or path.stem)
    else:
        lid = (load_lesson(path).get("id") or path.stem)
    try:
        kinds = ("slides",) if kind == "slides" else (("captions",) if kind == "captions" else ("slides", "captions"))
        files = export_preview_pdfs(lid, out_root(), kinds)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    if not files:
        return {"ok": False, "error": "No slide or caption PNGs yet. Preview first."}
    urls = [media_href(lid, "pdf", p.name) for p in files]
    return {"ok": True, "id": lid, "files": urls, "count": len(files)}


def _quiz_urls(lid: str) -> list[str]:
    folder = lesson_out_dir(lid) / "quiz"
    urls = []
    if folder.is_dir():
        urls.extend(media_href(lid, "quiz", p.name) for p in sorted(folder.iterdir()) if p.is_file())
    for child in _member_ids(lid):
        if child != lid:
            urls.extend(_quiz_urls(child))
    return urls


def _wipe_paint_tree(root: Path) -> list[str]:
    """Delete painted outputs only. Do not walk audio/."""
    if not root.is_dir():
        return []
    removed = []
    for name in ("slides", "preview", "clips", "pack", "captions", "srt", "covers"):
        target = root / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed.append(name)
    cells = root / "cells"
    if cells.is_dir():
        for mp4 in list(cells.glob("*.mp4")):
            mp4.unlink(missing_ok=True)
            removed.append(mp4.name)
    return removed


def clear_lesson_cache(filename: str) -> dict:
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "error": "Select a lesson first."}
    try:
        data = load_module(path) if path.parent.name == "modules" else load_lesson(path)
        lid = data.get("id") or path.stem
    except Exception:
        lid = path.stem
        data = {}
    removed = _wipe_paint_tree(lesson_out_dir(lid))
    for child in _member_ids(lid):
        if child != lid:
            extra = _wipe_paint_tree(lesson_out_dir(child))
            removed.extend(f"{child}/{n}" for n in extra)
    invalidate_list_cache()
    invalidate_paint_cache(lid)
    return {"ok": True, "id": lid, "cleared": removed or ["(already empty)"]}


_LIST_CACHE: dict = {"key": None, "rows": []}


_LANG_MARK = {
    "en": "EN",
    "zh": "简",
    "zh_cn": "简",
    "zhcn": "简",
    "hk": "繁",
    "zh_hk": "繁",
    "zhhk": "繁",
}


def _lang_marks(names: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in names:
        key = (raw or "").replace(".mp4", "")
        token = ""
        if "+" in key:
            token = "+".join(_LANG_MARK.get(p, p) for p in key.split("+"))
        elif key in _LANG_MARK:
            token = _LANG_MARK[key]
        elif "_" in key and key.rsplit("_", 1)[-1] in _LANG_MARK:
            token = _LANG_MARK[key.rsplit("_", 1)[-1]]
        elif "-" in key:
            head = key.split("-")[0]
            token = _LANG_MARK.get(head, "")
        if token and token not in seen:
            seen.append(token)
    order = {"EN": 0, "简": 1, "繁": 2}
    seen.sort(key=lambda t: (0 if t in order else 1, order.get(t, 9), t))
    return seen


def _folder_langs(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    names = [
        child.name
        for child in root.iterdir()
        if child.is_dir() and child.name != "_bars" and any(child.glob("*.png"))
    ]
    return _lang_marks(names)


def _video_langs(root: Path) -> list[str]:
    cells = root / "cells"
    if not cells.is_dir():
        return []
    return _lang_marks([p.stem for p in cells.glob("*.mp4")])


def _paint_langs(lid: str) -> tuple[list[str], list[str], list[str]]:
    root = lesson_out_dir(lid)
    slides = list(_folder_langs(root / "slides"))
    caps = list(_folder_langs(root / "preview"))
    videos = list(_video_langs(root))
    for child in _member_ids(lid):
        if child == lid:
            continue
        cr = lesson_out_dir(child)
        for bucket, extra in (
            (slides, _folder_langs(cr / "slides")),
            (caps, _folder_langs(cr / "preview")),
            (videos, _video_langs(cr)),
        ):
            for token in extra:
                if token not in bucket:
                    bucket.append(token)
    return slides, caps, videos


def _list_cache_key() -> tuple:
    parts = []
    from catalog import iter_lesson_paths, iter_module_paths

    for path in list(iter_lesson_paths()) + list(iter_module_paths()):
        st = path.stat()
        parts.append((str(path), int(st.st_mtime), st.st_size))
    root = out_root()
    for kind in ("lessons", "modules"):
        base = root / kind
        if not base.is_dir():
            continue
        for folder in base.iterdir():
            if not folder.is_dir():
                continue
            for sub in ("cells", "slides", "preview", "covers"):
                target = folder / sub
                if target.is_dir():
                    parts.append((str(target), int(target.stat().st_mtime), target.name))
    return tuple(parts)


def lesson_glyphs(filename: str) -> dict:
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "gaps": [], "error": "Lesson file not found."}
    if path.parent.name == "modules":
        return {"ok": True, "file": path.name, "gaps": []}
    try:
        lesson = load_lesson(path)
        return {"ok": True, "file": path.name, "gaps": scan_lesson(lesson)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "gaps": [], "error": str(exc)}



def make_covers(filename: str, wanted: list[str] | None = None) -> dict:
    """Paint the YouTube covers for one short. No slides, no speech, no video."""
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "error": "Pick a short first. Covers are per video."}
    if path.parent.name in {"modules", "minicourses"}:
        return {"ok": False, "error": "Pick a short, not the mini-course. Covers are a few pictures for one video."}
    lesson = load_lesson(path)
    # Covers are a few pictures. Always paint the full speech x slides grid,
    # including the off-diagonal mixes. The video checkboxes do not apply.
    grid = [
        "en", "en+zh", "en+hk",
        "zh+en", "zh", "zh+hk",
        "hk+en", "hk+zh", "hk",
    ]
    cells = selected_cells(lesson, grid)
    cell_slides = {name: bilingual_pair(voice, cap, slide) for name, (voice, cap, slide) in cells.items()}
    out_dir = lesson_out_dir(lesson.get("id") or path.stem)
    cover_dir = out_dir / "covers"
    if cover_dir.is_dir():
        for old in cover_dir.glob("*.png"):
            old.unlink()
    write_cell_covers(path, lesson, cells, cell_slides, out_dir)
    covers = _cover_urls(lesson.get("id") or path.stem)
    return {"ok": True, "covers": covers, "count": len(covers)}


def lesson_outputs(filename: str) -> dict:
    migrate_out_layout()
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "slides": [], "previews": [], "covers": [], "quiz": [], "cells": [], "pack": []}
    try:
        data = load_module(path) if path.parent.name == "modules" else load_lesson(path)
        lid = data.get("id") or path.stem
    except Exception:
        lid = path.stem
    return {
        "ok": True,
        "id": lid,
        "slides": _slide_urls(lid),
        "previews": _preview_urls(lid),
        "covers": _cover_urls(lid),
        "quiz": _quiz_urls(lid),
        "cells": _cell_urls(lid),
    }


def list_lessons() -> list[dict]:
    LESSONS.mkdir(exist_ok=True)
    MODULES.mkdir(exist_ok=True)
    key = _list_cache_key()
    if _LIST_CACHE["key"] == key and _LIST_CACHE["rows"]:
        return _LIST_CACHE["rows"]
    rows = []
    from catalog import iter_lesson_paths, iter_module_paths, iter_minicourse_paths

    lesson_files = iter_lesson_paths()
    module_files = iter_module_paths()
    minicourse_files = iter_minicourse_paths()
    parsed: dict[str, dict] = {}
    for path in lesson_files:
        try:
            parsed[path.stem] = load_lesson(path)
        except Exception:
            parsed[path.stem] = {"id": path.stem, "title_en": path.name}
    files = lesson_files + module_files + minicourse_files
    for path in files:
        try:
            if path.parent.name in {"modules", "minicourses"}:
                lesson = load_module(path)
                errors = []
                if not lesson.get("id"):
                    errors.append("Missing field: id")
                ids = list(lesson.get("lessons") or [])
                if len(ids) < 2:
                    errors.append("A module needs at least two lessons.")
                for lid0 in ids:
                    from catalog import lesson_path as _lp

                    if _lp(lid0) is None:
                        errors.append(f"Lesson not found: {lid0}.yaml")
            else:
                lesson = parsed.get(path.stem) or load_lesson(path)
                errors = [e for e in _speech_errors(validate(lesson, glyphs=False), lesson) if not e.startswith("Beat seconds")]
        except Exception as exc:  # noqa: BLE001
            lesson, errors = {"id": path.stem, "title_en": path.name}, [str(exc)]
        lid = lesson.get("id") or path.stem
        kind = "module" if path.parent.name == "modules" else ("minicourse" if path.parent.name == "minicourses" else "lesson")
        slide_langs, cap_langs, video_langs = _paint_langs(lid)
        cell_dir = lesson_out_dir(lid) / "cells"
        cells = sorted(p.name for p in cell_dir.glob("*.mp4")) if cell_dir.exists() else []
        pack_dir = lesson_out_dir(lid) / "pack"
        packs = sorted(p.name for p in pack_dir.glob("*.mp4")) if pack_dir.is_dir() else []
        children = []
        if kind in {"module", "minicourse"}:
            child_mode = "cross"
            for lid0 in lesson.get("lessons") or []:
                child_les = parsed.get(lid0)
                if child_les:
                    child_mode = "tri" if is_tri(child_les) else "cross"
                    children.append({
                        "file": f"{lid0}.yaml",
                        "id": lid0,
                        "title_en": child_les.get("title_en") or lid0,
                    })
                else:
                    children.append({"file": f"{lid0}.yaml", "id": lid0, "title_en": lid0})
            mode = child_mode
        else:
            mode = "tri" if is_tri(lesson) else "cross"
        rows.append(
            {
                "file": path.name,
                "id": lid,
                "title_en": lesson.get("title_en", ""),
                "title_zh": lesson.get("title_zh", ""),
                "title_zh_hk": lesson.get("title_zh_hk", ""),
                "kind": kind,
                "area": (lid.split("-")[0] if lid else path.stem.split("-")[0]),
                "children": children,
                "beats": len(lesson.get("lessons") or lesson.get("beats") or []),
                "valid": not errors,
                "errors": errors,
                "cells": cells,
                "slide_langs": slide_langs,
                "cap_langs": cap_langs,
                "video_langs": video_langs,
                "pack": packs,
                "slides": [],
                "previews": [],
                "quiz": [],
                "mode": mode,
                "tracks": script_langs(lesson),
                "expected_cells": list(cells_for(lesson).keys()),
            }
        )
    _LIST_CACHE["key"] = key
    _LIST_CACHE["rows"] = rows
    return rows


def invalidate_list_cache() -> None:
    _LIST_CACHE["key"] = None
    _LIST_CACHE["rows"] = []


def invalidate_paint_cache(lid: str) -> None:
    """Drop slide/preview stamps so the next preview paints from the saved YAML."""
    root = lesson_out_dir(lid)
    if not root.is_dir():
        return
    for folder in (root / "slides", root / "preview"):
        if not folder.is_dir():
            continue
        for stamp in folder.rglob("*.stamp"):
            stamp.unlink(missing_ok=True)
        mark = folder / ".stamp"
        if mark.is_file():
            mark.unlink(missing_ok=True)


_CELL_LAB = {
    "en": "EN",
    "zh": "简",
    "hk": "繁",
    "zh_cn": "简",
    "zh_hk": "繁",
    "en+zh": "EN · 简 slides",
    "en+hk": "EN · 繁 slides",
    "zh+en": "简 · EN slides",
    "zh+hk": "简 · 繁 slides",
    "hk+en": "繁 · EN slides",
    "hk+zh": "繁 · 简 slides",
    "en+zh_hk": "EN · 繁 slides",
    "zh_hk+en": "繁 · EN slides",
}


_DUR_TAIL = re.compile(r"((?:\d+h\s+)?(?:\d+m\s+)?[\d.]+s)$")


def _split_timing_line(body: str) -> tuple[str, str] | None:
    raw = (body or "").strip()
    match = _DUR_TAIL.search(raw)
    if not match:
        return None
    name = raw[: match.start()].strip()
    if not name or name.startswith("total") or name.startswith("breakdown"):
        return None
    return name, match.group(1).strip()


def _timing_label(name: str) -> str:
    if name.startswith("video "):
        return _CELL_LAB.get(name[6:].strip(), name[6:].strip())
    if name.startswith("slides "):
        folder = name[7:].strip()
        return "slides · " + _CELL_LAB.get(folder, folder)
    if name.startswith("captions ") or name.startswith("caption "):
        folder = name.split(" ", 1)[-1].strip()
        if folder in {"preview", ""}:
            return "captions"
        return "captions · " + _CELL_LAB.get(folder, folder)
    return name


def _timing_report(log: str, fallback: str = "") -> str:
    """Group factory timing lines by short, then by language / version."""
    current = (fallback or "lesson").replace(".yaml", "")
    parts: list[tuple[str, list[tuple[str, str]]]] = []
    rows: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal rows
        if rows:
            parts.append((current, rows))
            rows = []

    for raw in (log or "").splitlines():
        line = raw.strip()
        if line.startswith("########"):
            flush()
            current = line.strip("# ").split()[0].replace(".yaml", "")
            continue
        if not line.lower().startswith("timing:"):
            continue
        parsed = _split_timing_line(line.split(":", 1)[-1])
        if not parsed:
            continue
        name, dur = parsed
        label = _timing_label(name)
        if label == current or label in {"slides", "caption preview", "captions"}:
            continue
        rows.append((label, dur))
    flush()
    if not parts:
        return ""
    by_lang: dict[str, list[str]] = {}
    lines = []
    for pid, items in parts:
        lines.append(pid)
        for name, dur in items:
            lines.append(f"  {name:<22} {dur}")
            if name in {"EN", "简", "繁"} or "voice" in name:
                by_lang.setdefault(name, []).append(dur)
        lines.append("")
    if by_lang:
        lines.append("By version")
        for name, durs in by_lang.items():
            lines.append(f"  {name:<22} {', '.join(durs)}")
    return "\n".join(lines).rstrip()


def _fmt_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def _parse_frac(text: str) -> tuple[int, int] | None:
    bits = (text or "").split()
    for bit in bits:
        if "/" in bit:
            a, b = bit.split("/", 1)
            if a.isdigit() and b.isdigit() and int(b) > 0:
                return int(a), int(b)
    return None


def _blend(lo: int, hi: int, a: int, b: int) -> int:
    return lo + int(round((hi - lo) * min(1.0, max(0.0, a / b))))


class ProgressMeter:
    """Map build-log lines onto a monotonic percent that matches real work."""

    def __init__(self, slides_only: bool = False, caption_preview: bool = False):
        self.slides_only = slides_only
        self.caption_preview = caption_preview
        self.pct = 2
        self.label = "Starting"
        self.detail = ""
        self.module_i = 1
        self.module_n = 1
        self.part = ""
        self.folder = ""

    def _bump(self, value: int) -> None:
        cap = 99 if self.module_n > 1 and self.module_i < self.module_n else 99
        self.pct = max(self.pct, min(cap, int(value)))

    def _band(self) -> tuple[int, int]:
        n = max(1, self.module_n)
        i = min(max(1, self.module_i), n)
        span = 90
        lo = 4 + int(span * (i - 1) / n)
        hi = 4 + int(span * i / n)
        return lo, max(lo + 1, hi)

    def _where(self) -> str:
        bits = []
        if self.module_n > 1:
            bits.append(f"{self.module_i}/{self.module_n}")
        if self.part:
            bits.append(self.part)
        if self.folder:
            bits.append(_CELL_LAB.get(self.folder, self.folder))
        return " · ".join(bits)

    def _set(self, label: str, detail: str = "") -> None:
        self.label = label
        self.detail = detail or self._where()

    def eat(self, line: str, friendly: tuple[str, str, int] | None) -> None:
        raw = (line or "").strip()
        low = raw.lower()
        if low.startswith("progress: module"):
            frac = _parse_frac(low)
            if frac:
                self.module_i, self.module_n = frac[0], max(1, frac[1])
            bits = raw.split()
            if "build" in bits:
                self.part = bits[bits.index("build") + 1]
            elif "part" in low:
                self.part = bits[-1]
            lo, _hi = self._band()
            self._bump(lo)
            self._set("Building section", self._where())
            return
        if raw.startswith("########"):
            token = raw.strip("# ").split()[0]
            if token:
                self.part = token
            self._set("Opening section", self._where())
            return
        if low.startswith("progress: slides"):
            frac = _parse_frac(low)
            folder = ""
            bits = raw.split()
            if len(bits) >= 4 and bits[2] not in {"start", "reuse"}:
                folder = bits[3] if bits[2].count("/") else bits[2]
            if "/" in (bits[2] if len(bits) > 2 else ""):
                folder = bits[3] if len(bits) > 3 else ""
            self.folder = folder or self.folder
            lo, hi = self._band()
            sub_hi = lo + int((hi - lo) * (0.55 if self.slides_only else 0.25))
            if frac:
                self._bump(_blend(lo + 1, sub_hi, frac[0], frac[1]))
            self._set("Painting slides", self._where() + (f" · folder {frac[0]}/{frac[1]}" if frac else ""))
            return
        if low.startswith("progress: preview"):
            frac = _parse_frac(low)
            bits = raw.split()
            if len(bits) >= 4:
                self.folder = bits[3]
            lo, hi = self._band()
            if frac:
                self._bump(_blend(lo + int((hi - lo) * 0.45), hi - 1, frac[0], frac[1]))
            self._set("Stamping captions", self._where() + (f" · {frac[0]}/{frac[1]}" if frac else ""))
            return
        if low.startswith("progress: speech"):
            frac = _parse_frac(low)
            lo, hi = self._band()
            if frac:
                self._bump(_blend(lo + int((hi - lo) * 0.25), lo + int((hi - lo) * 0.45), frac[0], frac[1]))
            self._set("Recording speech", self._where())
            return
        if low.startswith("progress: clip"):
            parts = [p for p in low.split() if "/" in p]
            lo, hi = self._band()
            if len(parts) >= 2:
                c = _parse_frac(parts[0])
                b = _parse_frac(parts[1])
                if c and b:
                    total = c[1] * b[1]
                    done = (c[0] - 1) * b[1] + b[0]
                    self._bump(_blend(lo + int((hi - lo) * 0.45), hi - 2, done, total))
            self._set("Encoding video", self._where() + " · " + raw.replace("progress:", "").strip())
            return
        if low.startswith("progress: concat") or low.startswith("progress: module-join"):
            frac = _parse_frac(low)
            lo, hi = self._band()
            if frac:
                self._bump(_blend(hi - 4, hi - 1, frac[0], frac[1]))
            name = raw.split()[-1]
            self._set("Joining video", name)
            return
        last_child = self.module_n <= 1 or self.module_i >= self.module_n
        if low.startswith("slides-only") or low.startswith("caption-preview") or low.startswith("timing: total"):
            if last_child:
                self._bump(99)
                self._set("Finishing", self._where())
            else:
                _, hi = self._band()
                self._bump(hi)
                self._set("Next section", self._where())
            return
        if friendly and friendly[0] not in {"Painting slides", "Build time", "Time by step", "Slides ready", "Caption preview ready"}:
            self._set(friendly[0], self._where() or friendly[1])


def _friendly_step(line: str) -> tuple[str, str, int] | None:
    text = (line or "").strip()
    if not text:
        return None
    rules = (
        ("########", "Opening lesson", 5),
        ("slide fonts", "Checking fonts", 10),
        ("glyph:", "Checking slide text", 12),
        ("slides-only", "Slides ready", 99),
        ("caption-preview", "Caption preview ready", 99),
        ("timing: total", "Section time", 0),
        ("timing: breakdown", "Section time", 0),
        ("tts retry", "Speech service hiccup; retrying", 42),
        ("replacing broken", "Re-recording a damaged audio file", 42),
        ("tts:", "Recording speech", 40),
        ("Could not read duration", "A leftover audio file is damaged", 40),
        ("titles:", "Choosing slide language", 20),
        ("silent master", "Building the picture", 70),
        ("motion:", "Setting dissolve and fade", 58),
        ("stage stills", "Drawing reveal frames", 55),
        ("clip:", "Encoding a section", 75),
        ("concat:", "Joining sections", 88),
        ("cell:", "Version ready", 90),
        ("experiment-pack", "Experiment pack ready", 100),
        ("pack:", "Writing experiment pack", 95),
        ("module concat", "Joining lessons", 90),
        ("module:", "Building module", 20),
        ("Skip cell", "Waiting on speech files", 60),
        ("FAILED", "This lesson failed", 0),
        ("INVALID", "The YAML did not pass checks", 0),
        ("speech.platform", "Speech service is unreachable", 40),
        ("ClientConnectorError", "Speech service is unreachable", 40),
        ("ConnectionReset", "Speech service dropped the connection", 40),
        ("Speech service dropped", "Speech service dropped the connection", 40),
    )
    low = text.lower()
    for needle, label, pct in rules:
        if needle.lower() in low:
            return label, text[:160], pct
    return None


def run_build(
    filename: str,
    force_tts: bool,
    labels: str,
    slides_only: bool = False,
    caption_preview: bool = False,
    options: dict | None = None,
    all_lessons: bool = False,
) -> None:
    opts = options or {}
    path = resolve_yaml(filename) if filename else None
    if not all_lessons and path is None:
        with _job_lock:
            _job.update(status="error", log="YAML file not found.", step="Build failed", detail="YAML file not found.", pct=0, cells=[])
        return
    cmd = [sys.executable, str(FACTORY / "build.py"), "--out", str(out_root())]
    if all_lessons:
        cmd.append("--all")
    else:
        cmd.append(str(path))
    cmd += ["--labels", labels]
    if force_tts and not slides_only and not caption_preview:
        cmd.append("--force-tts")
    if slides_only:
        cmd.append("--slides-only")
    if caption_preview:
        cmd.append("--caption-preview")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cells = opts.get("cells")
    if isinstance(cells, list) and cells:
        cmd += ["--cells", ",".join(str(c) for c in cells)]
    elif isinstance(cells, str) and cells.strip():
        cmd += ["--cells", cells.strip()]
    if opts.get("match_titles"):
        cmd.append("--match-titles")
    if opts.get("theme"):
        cmd += ["--theme", str(opts["theme"])]
    mapping = {
        "voice_en": "VF_VOICE_EN",
        "voice_zh_cn": "VF_VOICE_ZH_CN",
        "voice_zh_hk": "VF_VOICE_ZH_HK",
        "tts_backend": "VF_TTS",
        "tts_rate": "VF_TTS_RATE",
        "tts_volume": "VF_TTS_VOLUME",
        "tts_pitch": "VF_TTS_PITCH",
        "caption_size": "VF_CAPTION_SIZE",
        "caption_align": "VF_CAPTION_ALIGN",
        "caption_lines": "VF_CAPTION_LINES",
        "caption_opacity": "VF_CAPTION_OPACITY",
        "caption_bar": "VF_CAPTION_BAR",
        "progress_bar": "VF_PROGRESS_BAR",
        "stage_cards": "VF_STAGE_CARDS",
        "experiment_pack": "VF_EXPERIMENT_PACK",
        "pack_speeds": "VF_PACK_SPEEDS",
        "pack_nocap": "VF_PACK_NOCAP",
        "still_fade": "VF_STILL_FADE",
        "beat_fade": "VF_BEAT_FADE",
    }
    for key, var in mapping.items():
        val = opts.get(key)
        if val is not None and str(val) != "":
            env[var] = str(val)
    with _job_lock:
        _job.update(
            status="running",
            log="Starting batch…" if all_lessons else "Starting build…\n",
            step="Starting",
            detail=path.name if path else "all lessons",
            pct=2,
            lesson="--all" if all_lessons else path.name,
            cells=[],
            elapsed="0:00",
            elapsed_s=0,
            timing="",
            timing_total="",
        )
    started = time.time()
    lesson = None
    meter = ProgressMeter(slides_only=slides_only, caption_preview=caption_preview)
    try:
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        chunks: list[str] = []
        assert proc.stdout is not None
        for raw in proc.stdout:
            chunks.append(raw)
            parsed = _friendly_step(raw)
            elapsed_s = time.time() - started
            low = raw.strip().lower()
            with _job_lock:
                _job["log"] = "".join(chunks)[-12000:]
                _job["elapsed_s"] = elapsed_s
                _job["elapsed"] = _fmt_elapsed(elapsed_s)
                if low.startswith("timing: breakdown"):
                    _job["timing"] = raw.strip().split("breakdown", 1)[-1].strip()
                if low.startswith("timing: total"):
                    _job["timing_total"] = raw.strip().split("total", 1)[-1].strip()
                meter.eat(raw, parsed)
                _job["step"] = meter.label
                _job["detail"] = meter.detail
                _job["pct"] = meter.pct
        proc.wait()
        log = "".join(chunks) + ("" if proc.returncode == 0 else f"\n(exit {proc.returncode})")
        if all_lessons:
            lid = "batch"
            lesson_name = "--all"
        else:
            lesson = load_lesson(path)
            lid = lesson.get("id") or path.stem
            lesson_name = path.name
        lesson_log = lesson_out_dir(lid) / "build.log" if lid != "batch" else out_root() / "last_build.log"
        latest = out_root() / "last_build.log"
        latest.parent.mkdir(parents=True, exist_ok=True)
        lesson_log.parent.mkdir(parents=True, exist_ok=True)
        stamp = f"\n===== console {lesson_name} =====\n"
        latest.write_text(
            (latest.read_text(encoding="utf-8") if latest.exists() else "") + stamp + log,
            encoding="utf-8",
        )
        if not lesson_log.exists():
            lesson_log.write_text(stamp + log, encoding="utf-8")
        if all_lessons:
            cell_urls = _all_cell_urls()
            slides, previews = [], []
        elif path.parent.name == "minicourses":
            cell_urls, slides, previews = [], [], []
            for child in lesson.get("lessons") or []:
                found = sorted((lesson_out_dir(child) / "cells").glob("*.mp4")) if (lesson_out_dir(child) / "cells").exists() else []
                cell_urls += [media_href(child, "cells", item.name) for item in found]
                slides += _slide_urls(child)
                previews += _preview_urls(child)
        else:
            found = sorted((lesson_out_dir(lid) / "cells").glob("*.mp4")) if (lesson_out_dir(lid) / "cells").exists() else []
            packed = sorted((lesson_out_dir(lid) / "pack").glob("*.mp4")) if (lesson_out_dir(lid) / "pack").exists() else []
            cell_urls = [media_href(lid, "cells", item.name) for item in found]
            cell_urls += [media_href(lid, "pack", item.name) for item in packed]
            slides = _slide_urls(lid)
            previews = _preview_urls(lid)
        ok = proc.returncode == 0 and (
            all_lessons
            or (caption_preview and len(previews) > 0)
            or (slides_only and len(slides) > 0)
            or (not caption_preview and not slides_only and len(cell_urls) >= 1)
        )
        invalidate_list_cache()
        elapsed_s = time.time() - started
        elapsed = _fmt_elapsed(elapsed_s)
        timing_total = elapsed
        report = _timing_report(log, lesson_name)
        done_step = f"Done in {elapsed}" if ok else "Build failed"
        done_detail = "Open Timing for a per-short, per-version split." if (ok and report) else (
            log.strip().splitlines()[-1] if log.strip() else "See the log"
        )
        with _job_lock:
            _job.update(
                status="ok" if ok else "error",
                log=log,
                step=done_step,
                detail=done_detail,
                pct=100 if ok else int(_job.get("pct") or 0),
                elapsed=elapsed,
                elapsed_s=elapsed_s,
                timing=report,
                timing_total=timing_total,
                lesson=lesson_name,
                cells=cell_urls,
                slides=slides,
                previews=previews,
                log_url="/media/last_build.log" if all_lessons else media_href(lid, "build.log"),
                latest_url="/media/last_build.log",
                log_path=_rel_to_root(latest if all_lessons else lesson_log),
                mode="batch" if all_lessons or lesson is None else ("tri" if is_tri(lesson) else "cross"),
            )
    except Exception as exc:  # noqa: BLE001
        elapsed_s = time.time() - started
        with _job_lock:
            _job.update(
                status="error",
                log=str(exc),
                step="Build failed",
                detail=str(exc),
                pct=int(_job.get("pct") or 0),
                elapsed=_fmt_elapsed(elapsed_s),
                elapsed_s=elapsed_s,
                cells=_all_cell_urls() if all_lessons else list(_job.get("cells") or []),
            )


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video factory</title>
<style>
  :root {
    --navy:#0b1f3a;
    --navy-2:#16345a;
    --gold:#c4a35a;
    --gold-deep:#a4843d;
    --gold-soft:#e8d7a8;
    --gold-wash:#f6edd8;
    --cream:#f3eee6;
    --paper:#fffcf8;
    --ink:#141c28;
    --muted:#5a6473;
    --line:#ddd4c4;
    --ok:#1f6f5b;
    --ok-wash:#e8f2ee;
    --bad:#9b2c2c;
    --bad-wash:#f6e8e8;
    --shadow: 0 12px 28px rgba(11,31,58,.07);
    color-scheme: light;
  }
  * { box-sizing: border-box; }
  html, body { margin:0; }
  body {
    font-family: "Segoe UI", "Noto Sans", "Helvetica Neue", Arial, sans-serif;
    background:
      radial-gradient(820px 380px at 0% -8%, rgba(196,163,90,.16), transparent 58%),
      radial-gradient(640px 320px at 100% 0%, rgba(11,31,58,.07), transparent 52%),
      var(--cream);
    color: var(--ink);
    min-height: 100vh;
  }
  header.appbar {
    background: linear-gradient(180deg, var(--navy) 0%, #0a1a31 100%);
    color: #fff;
    padding: 22px 36px 20px;
    border-bottom: 3px solid var(--gold);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
  }
  .brand { display:flex; align-items:center; gap:16px; min-width:0; }
  .mark {
    width:44px; height:44px; border-radius:12px;
    background: linear-gradient(145deg, var(--gold), #a4843d);
    color: var(--navy);
    display:grid; place-items:center;
    font-weight:700; letter-spacing:.04em; font-size:15px;
    flex: 0 0 auto;
  }
  header h1 { margin:0; font-size:22px; font-weight:650; letter-spacing:.01em; }
  header .lede { margin:4px 0 0; color:rgba(255,255,255,.72); font-size:13px; line-height:1.45; }
  .status-chip {
    display:inline-flex; align-items:center; gap:8px;
    background: rgba(255,255,255,.08);
    border: 1px solid rgba(196,163,90,.35);
    color: var(--gold-soft);
    border-radius: 999px;
    padding: 8px 14px;
    font-size: 12px;
    letter-spacing: .04em;
    text-transform: uppercase;
    white-space: nowrap;
  }
  .status-chip i {
    width:8px; height:8px; border-radius:50%; background: var(--gold); display:block;
  }
  .status-chip.run i { background:#7ec8b4; box-shadow:0 0 0 4px rgba(126,200,180,.18); }
  .status-chip.ok i { background:#7ec8b4; }
  .status-chip.err i { background:#e08a8a; }
  main {
    display:grid;
    grid-template-columns: 320px minmax(0,1fr);
    gap: 22px;
    padding: 24px 28px 56px;
    align-items: start;
  }
  .sidebar { position: sticky; top: 18px; max-height: calc(100vh - 36px); overflow:auto; }
  .list-filter { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 8px; }
  .list-filter button {
    flex:1; border:1px solid var(--line); background:#fff; color:var(--navy);
    border-radius:999px; padding:5px 8px; font-size:12px; font-weight:650; cursor:pointer;
  }
  .list-filter.areas button { flex:0 0 auto; padding:4px 10px; font-size:11px; letter-spacing:.04em; }
  .list-filter button.on { background:var(--navy); color:#fff; border-color:var(--navy); }
  #listsearch {
    width:100%; margin:0 0 10px; padding:7px 10px; border:1px solid var(--line);
    border-radius:8px; font:13px/1.3 inherit; background:#fff;
  }
  .list-head {
    font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:#6b7380;
    font-weight:700; margin:12px 0 6px;
  }
  .child-link {
    display:inline-block; margin:0 6px 6px 0; padding:4px 8px; border-radius:8px;
    border:1px solid var(--line); background:#fff; font-size:12px; cursor:pointer; color:var(--navy);
  }
  .workspace { min-width: 0; }
  .wshead {
    background:#fff; border:1px solid var(--line); border-radius:12px;
    padding:12px 16px; margin:0 0 10px; font-size:15px;
    border-left:4px solid var(--gold);
  }
  .wshead b { color:var(--navy); }
  .wshead span { color:var(--muted); margin-left:8px; font-size:13px; }
  .wshead #mode { margin:4px 0 0; }
  .painted-row { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 0; }
  .painted-row[hidden] { display:none; }
  .painted-row .pill { font-size:12px; }
  .crumb-row { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:0 0 8px; font-size:13px; }
  .crumb-row[hidden] { display:none; }
  .crumb {
    border:1px solid var(--line); background:#fff; color:var(--navy);
    border-radius:999px; padding:3px 10px; font-size:12px; font-weight:700; cursor:pointer;
  }
  .crumb:hover { border-color:var(--navy); }
  .crumb-sep { color:var(--muted); font-weight:700; }
  .lesson.ctx { box-shadow: inset 3px 0 0 var(--gold); }
  .modnav { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 0; }
  .modnav[hidden] { display:none; }
  .modnav button {
    border:1px solid var(--line); background:#fff; color:var(--navy);
    border-radius:8px; padding:4px 9px; font-size:12px; font-weight:650; cursor:pointer;
  }
  .modnav button.on { background:var(--navy); color:#fff; border-color:var(--navy); }
  .modnav .modnav-mod { border-radius:999px; font-weight:700; }
  .dock {
    position: sticky; top: 0; z-index: 6;
    background: var(--cream);
    padding: 0 0 10px;
  }
  .tabs {
    display:flex; flex-wrap:wrap; gap:6px;
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 12px;
    margin: 0;
    padding: 10px 12px;
    box-shadow: 0 8px 18px rgba(11,31,58,.05);
  }
  .tabs button {
    border:1px solid var(--line); background:#fff; color:var(--navy);
    border-radius:999px; padding:7px 13px; font-size:13px; font-weight:650;
    cursor:pointer;
  }
  .tabs button.on {
    background:var(--navy); color:#fff; border-color:var(--navy);
    box-shadow: 0 1px 0 var(--gold-deep);
  }
  .tabs button .count {
    display:inline-block; min-width:1.2em; margin-left:6px;
    font-size:11px; color:var(--gold-deep); font-weight:700;
  }
  .tabs button.on .count { color:var(--gold-soft); }
  .tab-panel { display:none; }
  .tab-panel.on { display:block; }
  .tab-panel > .card { margin-top:0; }
  section.card {
    background: var(--paper);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 20px 20px 18px;
    box-shadow: var(--shadow);
  }
  section.card + section.card { margin-top: 16px; }
  .sec-head {
    display:flex; align-items:baseline; justify-content:space-between; gap:12px;
    margin: 0 0 14px;
  }
  h2 {
    margin:0;
    font-size:12px;
    letter-spacing:.14em;
    text-transform:uppercase;
    color:#6b7380;
    font-weight:700;
  }
  .hint { color:var(--muted); font-size:13px; line-height:1.5; margin:0 0 14px; }
  .howto { margin:0 0 16px; padding:12px 14px; background:var(--gold-wash); border-radius:12px; border:1px solid var(--line); }
  .howto ol { margin:8px 0 0; padding-left:18px; color:#3d4754; font-size:13px; line-height:1.55; }
  .howto li { margin:0 0 4px; }
  .def-note { font-size:12px; color:var(--muted); margin:4px 0 10px; }
  .badge-def {
    display:inline-block; margin-left:6px; padding:1px 7px; border-radius:999px;
    background:#eef6f1; color:#2f6b55; font-size:10px; letter-spacing:.04em;
    text-transform:uppercase; font-weight:700; vertical-align:middle;
  }
  .motion-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; width:100%; }
  .mix-grid {
    display:grid;
    grid-template-columns: minmax(92px, 120px) 1fr 1fr 1fr;
    gap:8px;
    align-items:center;
    margin-top:8px;
  }
  .mix-grid .mh, .mix-grid .rh {
    font-size:11px; color:#6a7380; font-weight:650; letter-spacing:.03em;
    text-transform:uppercase;
  }
  .mix-grid .mh { text-align:center; }
  .mix-grid label.cell {
    display:flex; align-items:center; justify-content:center; gap:6px;
    margin:0; padding:8px 6px; background:var(--paper); border-radius:10px;
    border:1px solid var(--line); font-size:12px; cursor:pointer;
  }
  .mix-grid label.cell.on { background:var(--gold-wash); border-color:var(--gold); }
  .mix-grid label.cell input { margin:0; }
  .speed-row {
    display:flex; flex-wrap:wrap; gap:8px; align-items:center;
    margin:8px 0 4px; font-size:13px;
  }
  .speed-row .lbl { color:#6a7380; font-size:11px; font-weight:650; letter-spacing:.04em; text-transform:uppercase; margin-right:4px; }
  .speed-row label.cell {
    display:flex; gap:6px; align-items:center;
    border:1px solid var(--line); border-radius:8px; padding:6px 10px; background:#fff;
  }
  .speed-row label.cell.on { background:var(--gold-wash); border-color:var(--gold); }
  .motion-field label { display:block; font-size:12px; font-weight:650; margin:0 0 6px; color:var(--ink); }
  .motion-field input[type=number] {
    width:100%; border:1px solid var(--line); border-radius:8px;
    padding:8px 10px; font:inherit; background:#fff;
  }
  .presets { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  .presets button {
    border:1px solid var(--line); background:#fff; border-radius:999px;
    padding:3px 9px; font-size:11px; cursor:pointer; color:var(--muted);
  }
  .presets button:hover, .presets button.on { border-color:var(--gold); color:var(--navy); background:#fff8ea; }
  .muted { color:var(--muted); font-size:12px; }
  .drop {
    border:1px dashed #c9bda8;
    background: #faf6ee;
    border-radius:12px;
    padding:18px 14px;
    text-align:center;
    margin-bottom:14px;
    color: var(--muted);
    font-size:13px;
    cursor:pointer;
    transition: border-color .15s, background .15s;
  }
  .drop:hover, .drop.over { border-color: var(--gold); background:#fff8ea; }
  .drop input { display:block; margin:10px auto 0; font-size:12px; max-width:100%; }
  .lesson {
    border:1px solid var(--line);
    background:#fff;
    border-radius:12px;
    padding:12px 13px 11px;
    margin:0 0 8px;
    cursor:pointer;
    transition: border-color .15s, box-shadow .15s, transform .15s;
  }
  .lesson:hover { border-color:#d3c4a2; box-shadow:0 4px 14px rgba(11,31,58,.06); }
  .lesson.on {
    border-color: var(--gold);
    background: linear-gradient(180deg, #fffaf0, #f7eed8);
    box-shadow: inset 3px 0 0 var(--gold);
  }
  .lesson-top { display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .lesson b { display:block; font-size:14px; letter-spacing:.01em; }
  .lesson-title { margin:4px 0 8px; font-size:13px; color:#3d4754; line-height:1.35; }
  .meta-row { display:flex; flex-wrap:wrap; gap:6px; }
  .pill {
    display:inline-flex; align-items:center;
    border-radius:999px; padding:2px 8px;
    font-size:11px; letter-spacing:.02em;
    background:#eef1f4; color:#44505e;
  }
  .pill.ok { background:#e5f3ee; color:var(--ok); }
  .pill.bad { background:#f8e8e8; color:var(--bad); }
  .pill.gold { background:#f4ead3; color:#7a5d20; }
  .ok { color:var(--ok); } .bad { color:var(--bad); }
  .selected-box {
    background:var(--gold-wash);
    border:1px solid var(--line);
    border-radius:12px;
    padding:12px 14px;
    margin-bottom:14px;
  }
  .selected-box #sel { margin:0; font-size:14px; color:var(--ink); font-weight:600; }
  .selected-box #mode { margin:4px 0 0; }
  .group {
    border:1px solid var(--line);
    border-radius:12px;
    padding:12px 14px 8px;
    margin:0 0 12px;
    background:#fff;
  }
  .group h3 {
    margin:0 0 8px;
    font-size:11px;
    letter-spacing:.12em;
    text-transform:uppercase;
    color:#7a8492;
  }
  .checks { display:grid; grid-template-columns:1fr 1fr; gap:4px 16px; }
  .checks .span2 { grid-column: 1 / -1; }
  label.row {
    display:flex; gap:8px; align-items:center;
    margin:7px 0; font-size:13.5px; color:#243040;
  }
  label.field {
    display:flex; flex-direction:column; gap:5px;
    margin:0; font-size:12px; color:var(--muted); font-weight:600;
  }
  .fields { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  select {
    width:100%;
    border:1px solid #d7d0c4;
    background:#fff;
    border-radius:8px;
    padding:8px 10px;
    font-size:13px;
    color:var(--ink);
  }
  select:focus { outline:2px solid rgba(196,163,90,.35); border-color:var(--gold); }
  .hint { margin:4px 0 8px; font-size:12px; color:var(--muted); line-height:1.45; }
  #shared_labels_wrap { margin:8px 0 0; }
  details.options {
    border:1px solid var(--line);
    border-radius:12px;
    background:#fff;
    padding:4px 14px 10px;
    margin: 0 0 14px;
  }
  details.options summary {
    cursor:pointer;
    list-style:none;
    padding:10px 0;
    font-size:13px;
    font-weight:650;
    color:var(--navy);
  }
  details.options summary::-webkit-details-marker { display:none; }
  details.options summary::after { content:" ▾"; color:var(--gold); }
  .opt-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:12px 14px; }
  .actions {
    display:flex; flex-wrap:wrap; gap:8px;
    margin: 2px 0 10px;
  }
  .actions.primary { margin-top: 12px; }
  .actions.more { margin: 0 0 14px; }
  button, .btn {
    border:0; border-radius:10px;
    padding:10px 14px;
    font-size:13.5px;
    font-weight:650;
    cursor:pointer;
    letter-spacing:.01em;
  }
  button:disabled { opacity:.45; cursor:not-allowed; }
  #build {
    background: var(--navy);
    color:#fff;
    padding:12px 22px;
    font-size:15px;
    box-shadow: 0 6px 16px rgba(11,31,58,.18);
  }
  #build:hover { background: var(--navy-2); }
  .actions.more button {
    background:#fff;
    color:var(--navy);
    border:1px solid #d4cbb8;
    padding:7px 12px;
    font-size:12.5px;
    font-weight:600;
  }
  .progress {
    margin: 8px 0 0;
    padding: 12px 16px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: #fff;
  }
  .progress-top {
    display:flex; justify-content:space-between; gap:12px; align-items:baseline;
    margin-bottom:8px;
  }
  .progress-top strong { font-size:15px; color:var(--ink); }
  .progress-top span { font-size:12px; color:var(--muted); }
  .progress-bar {
    height:8px; border-radius:99px; background:#ece6da; overflow:hidden;
  }
  body.busy { cursor: progress; }
  body.busy .workspace { pointer-events: none; }
  body.busy .dock { pointer-events: auto; }
  .dock.busy .progress { border-color: var(--gold); }
  .dock.busy #progstep::after { content: ""; }
  @keyframes vfpulse { 50% { opacity: .55; } }
  .dock.busy .progress-bar i { animation: vfpulse 1.2s ease-in-out infinite; }
  .progress-bar i {
    display:block; height:100%; width:0%;
    background: linear-gradient(90deg, var(--gold-deep), var(--gold));
    transition: width .25s ease;
  }
  .progress-detail {
    margin:8px 0 0; font-size:12px; color:var(--muted); line-height:1.4;
    min-height:1.2em;
  }
  .progress-timing {
    margin:6px 0 0;
    font-size:12px;
    color:var(--ink);
  }
  .progress-timing summary {
    cursor:pointer;
    font-weight:700;
    color:var(--navy);
  }
  .progress-timing pre {
    margin:8px 0 0;
    padding:10px 12px;
    background:#fff;
    color:#141c28;
    border:1px solid var(--line);
    border-radius:8px;
    font-size:13px;
    line-height:1.5;
    font-weight:550;
    white-space:pre-wrap;
    max-height:220px;
    overflow:auto;
  }
  .logbox {
    border:1px solid #1b2430;
    border-radius:12px;
    overflow:hidden;
    background:#111820;
  }
  .logbar {
    display:flex; justify-content:space-between; align-items:center; gap:12px;
    padding:8px 12px;
    background:#0c121a;
    color:#cfc6b4;
    font-size:11px;
    letter-spacing:.06em;
    text-transform:uppercase;
  }
  .logbar a { color:var(--gold-soft); text-decoration:none; }
  .logbar a:hover { text-decoration:underline; }
  pre {
    margin:0;
    background:#111820;
    color:#e8e0d0;
    padding:12px 14px;
    max-height:220px;
    overflow:auto;
    font-size:12px;
    line-height:1.45;
  }
  #logpath { margin:8px 0 0; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .video-board { display:grid; gap:10px; align-items:start; margin:0 0 18px; }
  .video-board .head, .video-board .beat { display:contents; }
  .video-board .lbl {
    font-size:11px; color:#6a7380; padding-top:8px;
    letter-spacing:.04em; text-transform:uppercase; font-weight:650;
  }
  .video-block h3 {
    margin:0 0 8px; font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:#7a8492;
  }
  .cell-card {
    background:#0d1520;
    border-radius:12px;
    overflow:hidden;
    border:1px solid #1c2734;
  }
  .cell-card header {
    padding:10px 12px 8px;
    background:#121b27;
    color:#d9d1c2;
  }
  .cell-card header strong { display:block; font-size:13px; }
  .cell-card header span { font-size:11px; color:#8b93a0; }
  video { width:100%; background:#000; display:block; }
  .slides, .preview-table { display:grid; gap:10px; align-items:start; }
  .slides .head, .slides .beat,
  .preview-table .head, .preview-table .beat { display:contents; }
  .slides .lbl, .preview-table .lbl {
    font-size:11px; color:#6a7380; padding-top:8px;
    letter-spacing:.04em; text-transform:uppercase; font-weight:650;
  }
  .slides figure, .preview-table figure {
    margin:0; background:#101820; border-radius:10px; overflow:hidden;
    border:1px solid #1d2834;
    transition: transform .15s ease, box-shadow .15s ease;
  }
  .slides figure:hover, .preview-table figure:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 22px rgba(11,31,58,.16);
  }
  .slides img, .preview-table img { width:100%; display:block; cursor:zoom-in; }
  #lightbox {
    position:fixed; inset:0; z-index:80; background:rgba(8,14,24,.88);
    display:flex; align-items:center; justify-content:center; padding:28px 72px 48px;
  }
  #lightbox[hidden] { display:none; }
  #lightbox img {
    max-width:min(1600px, calc(100vw - 160px)); max-height:calc(100vh - 88px);
    object-fit:contain; border-radius:8px; box-shadow:0 16px 40px rgba(0,0,0,.4);
  }
  #lightbox .lb-nav, #lightbox .lb-close {
    position:absolute; border:0; background:rgba(255,255,255,.12); color:#fff;
    font-size:28px; width:48px; height:48px; border-radius:999px; cursor:pointer;
  }
  #lightbox .lb-close { top:16px; right:16px; font-size:26px; }
  #lightbox .lb-prev { left:16px; }
  #lightbox .lb-next { right:16px; }
  #lightbox .lb-nav:hover, #lightbox .lb-close:hover { background:rgba(255,255,255,.28); }
  #lblabel { position:absolute; bottom:14px; left:0; right:0; text-align:center; color:#fff; font-size:13px; letter-spacing:.04em; }
  #lblangs { position:absolute; top:16px; left:50%; transform:translateX(-50%); display:flex; gap:6px; }
  #lblangs button {
    border:1px solid rgba(255,255,255,.28); background:rgba(255,255,255,.08); color:#fff;
    border-radius:999px; padding:4px 12px; font-size:12px; font-weight:700; cursor:pointer;
  }
  #lblangs button.on { background:#fff; color:#102038; }
  .slides figure.stack, .preview-table figure.stack { display:flex; flex-direction:column; gap:6px; padding:6px; background:#101820; }
  .slides figure.stack a, .preview-table figure.stack a { display:block; border-radius:8px; overflow:hidden; }
  .slides .lb-gap, .preview-table .lb-gap {
    min-height:72px; border-radius:8px; background:rgba(16,24,32,.35);
    border:1px dashed rgba(255,255,255,.12);
  }
  .slides figcaption, .preview-table figcaption {
    color:#c9c1b3; font-size:11px; padding:6px 8px; background:#161f2a;
  }
  .inspect-head { border:1px solid var(--line); border-radius:12px; background:#fff; padding:12px 14px; margin:0 0 12px; }
  .inspect-head .who { display:flex; flex-wrap:wrap; align-items:baseline; gap:8px 12px; margin:0 0 8px; }
  .inspect-head .who strong { font-size:15px; letter-spacing:.02em; }
  .inspect-head .who .ename { font-size:15px; font-weight:650; }
  .inspect-head .chips { display:flex; flex-wrap:wrap; gap:6px; }
  .inspect-head .chip {
    font-size:11px; font-weight:650; color:#4b5563; background:#f3eee6;
    border:1px solid var(--line); border-radius:999px; padding:2px 8px;
  }
  .inspect-dl { display:flex; flex-direction:column; }
  .inspect-dl .inspect-field:first-child { border-top:0; padding-top:2px; }
  .inspect-gaps { background:#f8eee6; border:1px solid #e4d0bc; border-radius:10px; padding:8px 12px; margin:0 0 12px; font-size:12px; color:#6a3b16; }
  .inspect-ok { background:var(--ok-wash); border:1px solid #b7c9ae; border-radius:10px; padding:8px 12px; margin:0 0 12px; font-size:12px; color:var(--ok); }
  .inspect-table { width:100%; border-collapse:collapse; font-size:12px; }
  .inspect-table th, .inspect-table td { border-bottom:1px solid var(--line); padding:8px 8px; vertical-align:top; text-align:left; }
  .inspect-table th { color:#6a7380; font-weight:650; letter-spacing:.03em; text-transform:uppercase; font-size:11px; }
  .inspect-table .lang { display:block; margin:0 0 4px; }
  .inspect-table .lang b { color:#6a7380; font-weight:650; margin-right:6px; }
  .inspect-table .miss { color:#9a3412; }
  .inspect-beats { display:flex; flex-direction:column; gap:10px; max-height:min(70vh, 720px); overflow:auto; padding-right:4px; }
  .inspect-beat { border:1px solid var(--line); border-radius:12px; background:#fff; padding:10px 12px; }
  .inspect-beat h4 { margin:0 0 6px; font-size:13px; }
  .inspect-beat h4 span { color:var(--muted); font-weight:600; margin-left:8px; font-size:12px; }
  .inspect-field { display:grid; grid-template-columns: 88px minmax(0,1fr); gap:4px 10px; padding:6px 0; border-top:1px solid var(--line); font-size:12px; }
  .inspect-field .fname { color:#6a7380; font-weight:700; letter-spacing:.03em; text-transform:uppercase; font-size:11px; padding-top:2px; }
  .inspect-field .lang { display:block; margin:0 0 3px; }
  .edit-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px 10px; margin:0; }
  .edit-grid.named { grid-template-columns:148px repeat(3, minmax(0,1fr)); align-items:start; }
  .edit-row { margin:0 0 14px; }
  .edit-name { padding-top:2px; }
  .edit-name strong { display:block; font-size:13px; color:var(--navy); font-weight:750; }
  .edit-name span { display:block; margin-top:3px; font-size:11px; color:var(--muted); font-weight:500; line-height:1.35; }
  .edit-label { font-size:12px; font-weight:700; color:var(--navy); }
  .edit-help { margin:2px 0 6px; font-size:12px; color:var(--muted); }
  @media (max-width: 900px) {
    .edit-grid.named { grid-template-columns:repeat(3, minmax(0,1fr)); }
    .edit-name { grid-column:1 / -1; }
  }
  .edit-card { border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin:0 0 10px; background:#fff; }
  .edit-card h4 { margin:0 0 8px; font-size:13px; color:var(--navy); }
  .edit-card textarea {
    width:100%; min-height:54px; resize:vertical; border:1px solid #d7d0c4;
    border-radius:8px; padding:6px 8px; font:13px/1.4 ui-sans-serif, system-ui, sans-serif;
  }
  .edit-card textarea.tall { min-height:78px; }
  #saveedits { margin-top:4px; }
  .author-bar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0 0 12px; }
  .author-bar .hint { margin:0; }
  .count-ok { color:var(--ok); font-size:11px; }
  .count-warn { color:#9a3412; font-size:11px; font-weight:650; }
  .beat-tools { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 8px; }
  .beat-tools button, .ghost-btn {
    background:#fff; border:1px solid var(--line); border-radius:8px;
    padding:4px 8px; font-size:12px; cursor:pointer;
  }
  details.edit-card > summary {
    cursor:pointer; font-weight:650; color:var(--navy); list-style:none;
  }
  details.edit-card > summary::-webkit-details-marker { display:none; }
  .yaml-view { max-height:280px; overflow:auto; background:#121b27; color:#d9d1c2; padding:12px; border-radius:10px; font-size:11px; line-height:1.45; }
  .empty {
    border:1px dashed var(--line);
    border-radius:12px;
    padding:22px 16px;
    text-align:center;
    color:var(--muted);
    background:#faf7f1;
    font-size:13px;
  }
  .empty .empty-go {
    margin-top:12px;
    background:var(--navy);
    color:#fff;
    border:0;
    border-radius:10px;
    padding:8px 14px;
    font-size:13px;
    font-weight:650;
    cursor:pointer;
  }
  @media (max-width: 1080px) {
    main { grid-template-columns: 1fr; }
    .sidebar { position:static; max-height:none; }
    .opt-grid, .fields, .checks { grid-template-columns:1fr; }
  }
</style>
</head>
<body>
<header class="appbar">
  <div class="brand">
    <div class="mark">VF</div>
    <div>
      <h1>Video factory</h1>
      <p class="lede">One lesson, three videos: English, Putonghua + Simplified, Cantonese + Traditional.</p>
    </div>
  </div>
  <div class="status-chip" id="jobchip"><i></i><span id="joblabel">Idle</span></div>
</header>
<main>
  <aside class="sidebar">
    <section class="card">
      <div class="sec-head"><h2>Catalog</h2></div>
      <label class="drop" id="drop">
        Drop a lesson file here, or choose a file
        <input type="file" id="file" accept=".yaml,.yml">
      </label>
      <div class="list-filter" id="listfilter">
        <button type="button" data-filter="all" class="on">All</button>
        <button type="button" data-filter="lesson">Shorts</button>
        <button type="button" data-filter="module">Modules</button>
        <button type="button" data-filter="minicourse">Mini-courses</button>
      </div>
      <div class="list-filter areas" id="listarea"></div>
      <input id="listsearch" type="search" placeholder="Search id or title…" autocomplete="off">
      <div id="list"></div>
    </section>
  </aside>
  <div class="workspace">
    <div class="wshead" id="wshead">
      <div id="crumb" class="crumb-row" hidden></div>
      <div id="sel">Pick a short or a module on the left.</div>
      <div id="painted" class="painted-row" hidden></div>
      <div id="modnav" class="modnav" hidden></div>
      <p id="mode" class="muted"></p>
    </div>
    <div class="dock">
    <nav class="tabs" id="tabs">
      <button type="button" data-tab="build" class="on">Build</button>
      <button type="button" data-tab="author">Author</button>
      <button type="button" data-tab="check">Check</button>
      <button type="button" data-tab="slides">Slides <span class="count" id="tab-slides-n"></span></button>
      <button type="button" data-tab="covers">Covers <span class="count" id="tab-covers-n"></span></button>
      <button type="button" data-tab="captions">Captions <span class="count" id="tab-caps-n"></span></button>
      <button type="button" data-tab="quiz">Quiz <span class="count" id="tab-quiz-n"></span></button>
      <button type="button" data-tab="videos">Videos <span class="count" id="tab-vids-n"></span></button>
    </nav>
    <div class="progress" id="progress">
      <div class="progress-top">
        <strong id="progstep">Idle</strong>
        <span><span id="progelapsed">0:00</span> · <span id="progpct">0%</span></span>
      </div>
      <div class="progress-bar"><i id="progbar"></i></div>
      <p class="progress-detail" id="prognow">Choose a lesson, then make slides or build the videos.</p>
      <details class="progress-timing" id="progtiming" hidden>
        <summary>Timing by short and version</summary>
        <pre id="progdetail"></pre>
      </details>
    </div>
    </div>
    <section class="tab-panel on" data-panel="build">
    <section class="card">
      <div class="howto" id="howto">
        <strong>Usual path</strong>
        <ol>
          <li>Pick a lesson on the left.</li>
          <li>Leave the three matched boxes ticked (the diagonal).</li>
          <li>An RA opens <em>Author</em> to fix wording. Check is the audit. Then click <em>Build this lesson</em>.</li>
        </ol>
      </div>
      <div class="actions primary">
        <button id="build">Build this lesson</button>
      </div>
      <div class="actions more">
        <button id="slidesonly" type="button" title="Paint slides only. No speech, no video.">Preview slides only</button>
        <button id="captionpreview" type="button" title="Stamp caption chips on slides. No speech, no video.">Preview captions</button>
        <button id="makecovers" type="button" title="Paint the YouTube covers only. A few pictures, no speech, no video.">Make covers</button>
        <button id="exportquiz" type="button" title="Write student HTML, answer key, and CSV.">Export quiz</button>
        <button id="clearcache" type="button" title="Delete cached slides, caption previews, clips, and videos. Speech stays.">Paint this lesson from scratch</button>
      </div>
      <div class="group">
        <h3>Versions to make <span class="badge-def">default: matched diagonal</span></h3>
        <div class="mix-grid" id="mixgrid">
          <div></div>
          <div class="mh">Slides EN</div>
          <div class="mh">Slides 简</div>
          <div class="mh">Slides 繁</div>
          <div class="rh">Speech EN</div>
          <label class="cell"><input type="checkbox" data-cell="en" checked> EN</label>
          <label class="cell"><input type="checkbox" data-cell="en+zh"> 简</label>
          <label class="cell"><input type="checkbox" data-cell="en+hk"> 繁</label>
          <div class="rh">Speech 简</div>
          <label class="cell"><input type="checkbox" data-cell="zh+en"> EN</label>
          <label class="cell"><input type="checkbox" data-cell="zh" checked> 简</label>
          <label class="cell"><input type="checkbox" data-cell="zh+hk"> 繁</label>
          <div class="rh">Speech 繁</div>
          <label class="cell"><input type="checkbox" data-cell="hk+en"> EN</label>
          <label class="cell"><input type="checkbox" data-cell="hk+zh"> 简</label>
          <label class="cell"><input type="checkbox" data-cell="hk" checked> 繁</label>
        </div>
      </div>
      <details class="options">
        <summary>Experiment pack, RA zip, faculty zip</summary>
      <div class="group">
        <h3>Experiment pack <span class="badge-def">grant treatments</span></h3>
        <p class="def-note">After the videos exist, write labelled copies for the trial: playback speed and a no-caption twin. Does not re-record speech. Uses ffmpeg atempo. A treatments.csv lists every file.</p>
        <label class="row"><input type="checkbox" id="experiment_pack"> Write experiment pack after this build</label>
        <div class="speed-row" id="packspeeds">
          <span class="lbl">Speeds</span>
          <label class="cell on"><input type="checkbox" data-speed="1" checked> 1×</label>
          <label class="cell on"><input type="checkbox" data-speed="1.25" checked> 1.25×</label>
          <label class="cell on"><input type="checkbox" data-speed="1.5" checked> 1.5×</label>
          <label class="cell on"><input type="checkbox" data-speed="2" checked> 2×</label>
        </div>
        <label class="row"><input type="checkbox" id="pack_nocap" checked> Also make a no-caption twin of each video</label>
      </div>
      <div class="group">
        <h3>RA review zip <span class="badge-def">one sitting</span></h3>
        <p class="def-note">YAML, Excel edit sheets, slide PDFs, caption PDFs, and built videos for the short or module now selected. No experiment-speed twins. Build slides and video first if the zip looks thin.</p>
        <div class="actions" style="margin:8px 0 0">
          <button id="bundle-ra" type="button">Zip this for RA</button>
        </div>
        <p class="hint" id="rahint">Lands in __OUT_ROOT__/_packs/ as RA-&lt;id&gt;.zip.</p>
        <h3>Course pack for faculty <span class="badge-def">pilots</span></h3>
        <p class="def-note">One A4 SOP plus videos, quizzes, and treatments already built for that course. No source YAML. Build the modules first if the zip looks thin.</p>
        <div class="actions" style="margin:8px 0 0">
          <button id="bundle-econ" type="button">Zip Economics</button>
          <button id="bundle-acc" type="button">Zip Accounting</button>
          <button id="bundle-gba" type="button">Zip GBA</button>
          <button id="bundle-lae" type="button">Zip LAE</button>
          <button id="bundle-game" type="button">Zip Game</button>
        </div>
        <p class="hint" id="bundlehint">Lands in __OUT_ROOT__/_packs/ as CUHK-VF-ECON.zip and the other course names.</p>
      </div>
      </details>
      <details class="options">
        <summary>Advanced — leave closed unless you need to change a default</summary>
        <p class="def-note" style="margin-top:10px">Recommended: progress bar on, card reveal on, dissolve 0.18s, no fade-to-black between sections, slide language follows the video, do not re-record speech if audio already exists.</p>
        <div class="checks">
          <label class="row span2"><input type="checkbox" id="force"> Re-record speech <span class="badge-def">off</span></label>
          <label class="row span2"><input type="checkbox" id="progress_bar" checked> Gold progress bar at the top <span class="badge-def">on</span></label>
          <label class="row span2"><input type="checkbox" id="stage_cards" checked> Reveal cards one by one in a section <span class="badge-def">on</span></label>
          <div class="motion-grid span2">
            <div class="motion-field">
              <label for="still_fade">Card dissolve (seconds) <span class="badge-def">0.18</span></label>
              <input id="still_fade" type="number" min="0" max="0.5" step="0.02" value="0.18">
              <div class="presets" data-for="still_fade">
                <button type="button" data-v="0">cut</button>
                <button type="button" data-v="0.12">0.12</button>
                <button type="button" data-v="0.18" class="on">0.18</button>
                <button type="button" data-v="0.30">0.30</button>
              </div>
            </div>
            <div class="motion-field">
              <label for="beat_fade">Fade to black between sections (seconds) <span class="badge-def">off</span></label>
              <input id="beat_fade" type="number" min="0" max="0.5" step="0.02" value="0">
              <div class="presets" data-for="beat_fade">
                <button type="button" data-v="0" class="on">cut</button>
                <button type="button" data-v="0.08">0.08</button>
                <button type="button" data-v="0.12">0.12</button>
                <button type="button" data-v="0.20">0.20</button>
              </div>
            </div>
          </div>
        </div>
        <div class="group" style="margin-top:14px">
          <h3>Slide titles</h3>
          <label class="row"><input type="checkbox" id="match_titles" checked> Slide language follows the video <span class="badge-def">on</span></label>
          <p class="hint" id="titles_hint">Speech and captions stay on their own languages. This only changes words painted on the slide.</p>
          <div class="fields" id="shared_labels_wrap">
            <label class="field">Same title language on every video
              <select id="labels">
                <option value="en">English on all slides</option>
                <option value="zh">Simplified Chinese on all slides</option>
                <option value="zh_hk">Traditional Chinese on all slides</option>
              </select>
            </label>
          </div>
        </div>
        <div class="fields">
          <label class="field">Slide theme <span class="badge-def">cuhk-navy</span>
            <select id="theme"></select>
          </label>
        </div>
        <h3 style="margin-top:16px">Voice and captions</h3>
        <div class="opt-grid" style="margin-top:6px">
        <label class="field">Speech service
          <select id="tts_backend">
            <option value="edge" selected>Edge (free)</option>
            <option value="google">Google Cloud TTS</option>
            <option value="edge-then-google">Edge, then Google if Edge fails</option>
          </select>
        </label>
        <p class="hint span2" id="tts_hint">Edge is free and needs no key. Google needs an API key in VF_GOOGLE_TTS_KEY, GOOGLE_API_KEY, a .env in the video-factory root, or secrets/google-tts-key.txt. A service-account JSON is not an API key. Restart the console after you set the key.</p>
        <label class="field">English voice
          <select id="voice_en">
            <option value="en-US-GuyNeural">Guy (US male)</option>
            <option value="en-US-JennyNeural">Jenny (US female)</option>
            <option value="en-GB-RyanNeural">Ryan (UK male)</option>
            <option value="en-GB-SoniaNeural">Sonia (UK female)</option>
            <option value="en-HK-SamNeural">Sam (HK English male)</option>
            <option value="en-HK-YanNeural">Yan (HK English female)</option>
          </select>
        </label>
        <label class="field">Putonghua voice
          <select id="voice_zh_cn">
            <option value="zh-CN-YunxiNeural">Yunxi (male)</option>
            <option value="zh-CN-YunyangNeural">Yunyang (male, news)</option>
            <option value="zh-CN-XiaoxiaoNeural">Xiaoxiao (female)</option>
            <option value="zh-CN-XiaoyiNeural">Xiaoyi (female)</option>
          </select>
        </label>
        <label class="field">Cantonese voice
          <select id="voice_zh_hk">
            <option value="zh-HK-WanLungNeural">WanLung (male)</option>
            <option value="zh-HK-HiuMaanNeural">HiuMaan (female)</option>
            <option value="zh-HK-HiuGaaiNeural">HiuGaai (female)</option>
          </select>
        </label>
        <label class="field">Speech rate
          <select id="tts_rate">
            <option value="-20%">−20%</option>
            <option value="-10%">−10%</option>
            <option value="+0%" selected>normal</option>
            <option value="+10%">+10%</option>
            <option value="+20%">+20%</option>
          </select>
        </label>
        <label class="field">Speech volume
          <select id="tts_volume">
            <option value="-20%">−20%</option>
            <option value="-10%">−10%</option>
            <option value="+0%" selected>normal</option>
            <option value="+10%">+10%</option>
            <option value="+20%">+20%</option>
          </select>
        </label>
        <label class="field">Speech pitch
          <select id="tts_pitch">
            <option value="-20Hz">−20 Hz</option>
            <option value="-10Hz">−10 Hz</option>
            <option value="+0Hz" selected>normal</option>
            <option value="+10Hz">+10 Hz</option>
            <option value="+20Hz">+20 Hz</option>
          </select>
        </label>
        <label class="field">Caption size
          <select id="caption_size">
            <option value="34">small 34</option>
            <option value="42" selected>chip 42</option>
            <option value="48">large 48</option>
          </select>
        </label>
        <label class="field">Caption align
          <select id="caption_align">
            <option value="left">left</option>
            <option value="center" selected>center</option>
          </select>
        </label>
        <label class="field">Caption max lines
          <select id="caption_lines">
            <option value="1" selected>1</option>
            <option value="2">2</option>
            <option value="3">3</option>
          </select>
        </label>
        <label class="field">Caption opacity
          <select id="caption_opacity">
            <option value="60">60%</option>
            <option value="72" selected>72%</option>
            <option value="88">88%</option>
          </select>
        </label>
        </div>
      </details>
      <details class="options">
        <summary>Show log</summary>
      <div class="logbox">
        <div class="logbar">
          <span>Raw build output</span>
          <span>
            <a id="loglink" href="/media/last_build.log" target="_blank">last_build.log</a>
            ·
            <a id="lessonlog" href="#" target="_blank">lesson log</a>
          </span>
        </div>
        <pre id="log">Idle.</pre>
      </div>
      <p class="muted" id="logpath">Logs: <a href="/media/last_build.log" id="logpathlink">__OUT_ROOT__/last_build.log</a></p>
      </details>
    </section>
    </section>
    <section class="tab-panel" data-panel="author">
    <section class="card">
      <div class="sec-head"><h2>Author</h2></div>
      <p class="hint">RA workspace. Fix speech here, or download Excel, edit the yellow cells, and import. YAML stays the file the factory builds from. Save and import keep a one-time .bak.</p>
      <div id="author"><div class="empty">Pick a short on the left.</div></div>
    </section>
    </section>
    <section class="tab-panel" data-panel="check">
    <section class="card">
      <div class="sec-head"><h2>Check</h2></div>
      <p class="hint">Read-only audit. Gaps, field table, raw YAML. Edit in Author.</p>
      <div id="inspect"><div class="empty">Pick a short or a module on the left.</div></div>
    </section>
    </section>
    <section class="tab-panel" data-panel="slides">
    <section class="card">
      <div class="sec-head"><h2>Slides</h2></div>
      <p class="hint">One frame per section and language. Click a frame to open it full size.</p>
      <div class="slides" id="slides"><div class="empty">Slides appear here after a preview or a build.<p><button type="button" class="empty-go" data-run="slidesonly">Preview slides only</button></p></div></div>
    </section>
    </section>
    <section class="tab-panel" data-panel="covers">
    <section class="card">
      <div class="sec-head"><h2>Covers</h2></div>
      <p class="hint">One 1920×1080 YouTube cover per cell. The title is the lesson title. The panels say the slide language and the speech language.</p>
      <div class="slides" id="covers"><div class="empty">No covers yet.<p><button type="button" class="empty-go" data-run="makecovers">Make covers</button></p></div></div>
    </section>
    </section>
    <section class="tab-panel" data-panel="captions">
    <section class="card">
      <div class="sec-head"><h2>Captions</h2></div>
      <p class="hint">The spoken line is split across the section. With card reveal on, each step gets its own caption chip.</p>
      <div class="preview-table" id="previews"><div class="empty">No caption previews yet.<p><button type="button" class="empty-go" data-run="captionpreview">Preview captions</button></p></div></div>
    </section>
    </section>
    <section class="tab-panel" data-panel="quiz">
    <section class="card">
      <div class="sec-head"><h2>Quiz</h2></div>
      <p class="hint">100 points from the YAML quiz block and takeaway q1/q2. Student sheet has no answers. The key is for marking.</p>
      <div id="quizbox"><div class="empty">No quiz files yet.<p><button type="button" class="empty-go" data-run="exportquiz">Export quiz</button></p></div></div>
    </section>
    </section>
    <section class="tab-panel" data-panel="videos">
    <section class="card">
      <div class="sec-head"><h2>Videos</h2></div>
      <p class="hint">One column per language. On a module: combined unit first, then each short in lesson order.</p>
      <div id="cells"><div class="empty">No videos yet.<p><button type="button" class="empty-go" data-run="build">Build this lesson</button></p></div></div>
    </section>
    </section>
  </div>
</main>
<div id="lightbox" hidden>
  <button type="button" class="lb-close" data-lb="close" aria-label="Close">×</button>
  <button type="button" class="lb-nav lb-prev" data-lb="prev" aria-label="Previous">‹</button>
  <img id="lbimg" alt="">
  <button type="button" class="lb-nav lb-next" data-lb="next" aria-label="Next">›</button>
  <div id="lblangs"></div>
  <div id="lblabel"></div>
</div>
<script>
let selected = null;
let selectedMeta = null;
let moduleContext = null;
function showTab(name) {
  document.querySelectorAll('#tabs [data-tab]').forEach(b => b.classList.toggle('on', b.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('on', p.dataset.panel === name));
  try { localStorage.setItem('vf-tab', name); } catch (e) {}
}
function tabCount(id, n) {
  const el = document.getElementById(id);
  if (el) el.textContent = n ? String(n) : '';
}
document.getElementById('tabs').onclick = (ev) => {
  const btn = ev.target.closest('[data-tab]');
  if (btn) showTab(btn.dataset.tab);
};
document.querySelector('.workspace').addEventListener('click', (ev) => {
  const go = ev.target.closest('[data-run]');
  if (go) {
    if (go.dataset.run === 'makecovers') { makeCovers(); return; }
    const target = document.getElementById(go.dataset.run);
    if (target) target.click();
    return;
  }
  const a = ev.target.closest('a.lb-open');
  if (!a) return;
  ev.preventDefault();
  const box = a.closest('#slides, #previews, #covers');
  openLightboxFrom(a, box);
});
const LB_LANG = {en:'English', zh:'简体', hk:'繁體', zh_cn:'简体', zh_hk:'繁體', 'en+zh':'EN · 简', 'zh+en':'简 · EN', 'en+hk':'EN · 繁', 'hk+en':'繁 · EN', 'zh+hk':'简 · 繁', 'hk+zh':'繁 · 简'};
let lbByLang = {};
let lbLangs = [];
let lbLang = '';
let lbIdx = 0;
function lbItems() { return lbByLang[lbLang] || []; }
function paintLightbox() {
  const items = lbItems();
  const img = document.getElementById('lbimg');
  const lab = document.getElementById('lblabel');
  const chips = document.getElementById('lblangs');
  if (!img || !items.length) return;
  img.src = items[lbIdx].url;
  const name = (items[lbIdx].url.split('/').pop() || '').split('?')[0];
  if (lab) lab.textContent = (LB_LANG[lbLang]||lbLang) + '  ·  ' + (lbIdx + 1) + ' / ' + items.length + '  ·  ' + name + '   ← →  same language   ↑ ↓  language';
  if (chips) {
    chips.innerHTML = lbLangs.map(l => '<button type="button" class="'+(l===lbLang?'on':'')+'" data-lb-lang="'+l+'">'+(LB_LANG[l]||l)+'</button>').join('');
  }
}
function openLightboxFrom(anchor, box) {
  const nodes = Array.from((box || document).querySelectorAll('a.lb-open'));
  lbByLang = {};
  nodes.forEach(n => {
    const lang = n.dataset.lang || 'en';
    (lbByLang[lang] = lbByLang[lang] || []).push({url: n.getAttribute('href'), core: n.dataset.core || ''});
  });
  lbLangs = Object.keys(lbByLang);
  lbLang = anchor.dataset.lang || lbLangs[0] || 'en';
  const url = anchor.getAttribute('href');
  const list = lbItems();
  lbIdx = Math.max(0, list.findIndex(it => it.url === url));
  const overlay = document.getElementById('lightbox');
  if (overlay) overlay.hidden = false;
  paintLightbox();
}
function closeLightbox() {
  const box = document.getElementById('lightbox');
  if (box) box.hidden = true;
  lbByLang = {};
  lbLangs = [];
}
function stepLightbox(d) {
  const items = lbItems();
  if (!items.length) return;
  lbIdx = (lbIdx + d + items.length) % items.length;
  paintLightbox();
}
function switchLbLang(lang) {
  if (!lang || !lbByLang[lang]) return;
  const cur = (lbItems()[lbIdx] || {}).core;
  lbLang = lang;
  const list = lbItems();
  let i = list.findIndex(it => it.core === cur);
  if (i < 0) i = Math.min(lbIdx, list.length - 1);
  lbIdx = Math.max(0, i);
  paintLightbox();
}
function cycleLbLang(d) {
  if (!lbLangs.length) return;
  const i = lbLangs.indexOf(lbLang);
  switchLbLang(lbLangs[(i + d + lbLangs.length) % lbLangs.length]);
}
document.getElementById('lightbox').addEventListener('click', (ev) => {
  const langBtn = ev.target.closest('[data-lb-lang]');
  if (langBtn) { switchLbLang(langBtn.dataset.lbLang); return; }
  const act = ev.target.closest('[data-lb]');
  if (act && act.dataset.lb === 'prev') { stepLightbox(-1); return; }
  if (act && act.dataset.lb === 'next') { stepLightbox(1); return; }
  if (act && act.dataset.lb === 'close') { closeLightbox(); return; }
  if (ev.target.id === 'lightbox') closeLightbox();
});
document.addEventListener('keydown', (ev) => {
  const box = document.getElementById('lightbox');
  if (!box || box.hidden) return;
  if (ev.key === 'Escape') { closeLightbox(); ev.preventDefault(); }
  if (ev.key === 'ArrowRight' || ev.key === 'j') { stepLightbox(1); ev.preventDefault(); }
  if (ev.key === 'ArrowLeft' || ev.key === 'k') { stepLightbox(-1); ev.preventDefault(); }
  if (ev.key === 'ArrowDown' || ev.key === ']') { cycleLbLang(1); ev.preventDefault(); }
  if (ev.key === 'ArrowUp' || ev.key === '[') { cycleLbLang(-1); ev.preventDefault(); }
  if (ev.key >= '1' && ev.key <= '9') {
    const pick = lbLangs[Number(ev.key) - 1];
    if (pick) { switchLbLang(pick); ev.preventDefault(); }
  }
});
try {
  const saved = localStorage.getItem('vf-tab');
  if (saved && document.querySelector('[data-panel="'+saved+'"]')) showTab(saved);
} catch (e) {}
const CELL_LABELS = {
  en: 'English · matched',
  zh: 'Putonghua · matched',
  hk: 'Cantonese · matched',
  'en+zh': 'English · 简 slides',
  'en+hk': 'English · 繁 slides',
  'zh+en': 'Putonghua · EN slides',
  'zh+hk': 'Putonghua · 繁 slides',
  'hk+en': 'Cantonese · EN slides',
  'hk+zh': 'Cantonese · 简 slides'
};
const MIX_WORD = {en:'EN', zh:'简', hk:'繁'};
function mixLabel(key) {
  if (CELL_LABELS[key]) return CELL_LABELS[key];
  if (key.includes('__')) {
    const bits = key.split('__').filter(Boolean);
    return bits.slice(1).join(' · ') || key;
  }
  if (key.includes('+')) {
    const p = key.split('+');
    return (MIX_WORD[p[0]]||p[0]) + ' · ' + (MIX_WORD[p[1]]||p[1]) + ' slides';
  }
  return key;
}
function cellKey(url) {
  const name = (url.split('/').pop() || '').replace(/[.]mp4$/,'');
  if (name.includes('__')) return name;
  const bits = String(url).split('/');
  const mi = bits.indexOf('media');
  const owner = mi >= 0 && bits[mi+1] ? bits[mi+1] : '';
  if (owner && name.indexOf(owner + '_') === 0) return name.slice(owner.length + 1);
  const parts = name.split('_');
  return parts.slice(1).join('_') || name;
}
function setJob(state, label) {
  const chip = document.getElementById('jobchip');
  const text = document.getElementById('joblabel');
  if (text) text.textContent = label;
  if (chip) chip.className = 'status-chip' + (state ? ' ' + state : '');
}
function setBusy(on, label) {
  document.body.classList.toggle('busy', !!on);
  const dock = document.querySelector('.dock');
  if (dock) dock.classList.toggle('busy', !!on);
  const ids = ['build','slidesonly','captionpreview','makecovers','clearcache','exportquiz'];
  ids.forEach(id => { const el = document.getElementById(id); if (el) el.disabled = !!on; });
  const btn = document.getElementById('build');
  if (on) {
    if (btn) btn.textContent = label || 'Working…';
  } else if (selectedMeta) {
    applyMeta(selectedMeta);
  } else if (btn) {
    btn.textContent = 'Build this lesson';
  }
}
function setProgress(step, pct, detail, elapsed, report) {
  const s = document.getElementById('progstep');
  const p = document.getElementById('progpct');
  const e = document.getElementById('progelapsed');
  const b = document.getElementById('progbar');
  const now = document.getElementById('prognow');
  const d = document.getElementById('progdetail');
  const box = document.getElementById('progtiming');
  if (s) s.textContent = step || 'Idle';
  const n = Math.max(0, Math.min(100, Number(pct) || 0));
  if (p) p.textContent = n + '%';
  if (e) e.textContent = elapsed || '0:00';
  if (b) b.style.width = n + '%';
  if (now) now.textContent = detail || '';
  if (box && d) {
    const text = (report || '').trim();
    if (text) {
      box.hidden = false;
      d.textContent = text;
    } else if (!text && step && String(step).startsWith('Done')) {
      box.hidden = !d.textContent;
    }
  }
}
function showQuiz(urls) {
  const box = document.getElementById('quizbox');
  tabCount('tab-quiz-n', (urls || []).length);
  if (!box) return;
  if (!urls || !urls.length) {
    box.innerHTML = '<div class="empty">No quiz files yet.<p><button type="button" class="empty-go" data-run="exportquiz">Export quiz</button></p></div>';
    return;
  }
  box.innerHTML = urls.map(u => {
    const name = u.split('/').pop();
    const kind = name.endsWith('_key.html') ? 'Answer key' : name.endsWith('.html') ? 'Student sheet' : name.endsWith('.csv') ? 'CSV' : 'File';
    return `<a class="btn" href="${u}" target="_blank" style="margin:0 8px 8px 0;display:inline-block">${kind} · ${name}</a>`;
  }).join('');
}
function showCells(urls) {
  tabCount('tab-vids-n', (urls || []).length);
  const g = document.getElementById('cells');
  if (!g) return;
  if (!urls || !urls.length) {
    g.innerHTML = '<div class="empty">No videos yet.<p><button type="button" class="empty-go" data-run="build">Build this lesson</button></p></div>';
    return;
  }
  const COL_RANK = {en:0, zh:1, hk:2};
  const COL_NAME = {en:'English', zh:'Putonghua / 简', hk:'Cantonese / 繁'};
  function ownerOf(u) {
    const bits = String(u).split('/').filter(Boolean);
    const i = bits.indexOf('media');
    if (i < 0) return '';
    let j = i + 1;
    if (bits[j] === 'lessons' || bits[j] === 'modules') j += 1;
    return bits[j] || '';
  }
  function colOf(u) {
    return cellKey(u).replace(/_nocap$/,'');
  }
  function card(u) {
    const key = cellKey(u);
    return `<article class="cell-card"><header><strong>${mixLabel(key)}</strong><span>${(u.split('/').pop()||'')}</span></header><video controls preload="metadata" src="${u}"></video></article>`;
  }
  function grid(rows) {
    const cols = [];
    rows.forEach(r => Object.keys(r.byCol).forEach(c => { if (!cols.includes(c)) cols.push(c); }));
    cols.sort((a,b) => (COL_RANK[a] ?? 8) - (COL_RANK[b] ?? 8) || a.localeCompare(b));
    const html = ['<div class="video-board" style="grid-template-columns:108px '+cols.map(()=> '1fr').join(' ')+'">'];
    html.push('<div class="head"><div></div>'+cols.map(c => '<div class="lbl">'+(COL_NAME[c]||mixLabel(c))+'</div>').join('')+'</div>');
    rows.forEach(r => {
      html.push('<div class="beat"><div class="lbl">'+esc(r.label)+'</div>');
      cols.forEach(c => {
        html.push(r.byCol[c] ? card(r.byCol[c]) : '<div></div>');
      });
      html.push('</div>');
    });
    html.push('</div>');
    return html.join('');
  }
  const byOwner = {};
  urls.forEach(u => {
    if (u.indexOf('/pack/') >= 0) return;
    const owner = ownerOf(u);
    const col = colOf(u);
    (byOwner[owner] = byOwner[owner] || {})[col] = u;
  });
  const mid = selectedMeta && selectedMeta.kind === 'module' ? selectedMeta.id : '';
  const children = ((selectedMeta && selectedMeta.children) || []).map(c => String(c.id || '').replace(/[.]ya?ml$/,''));
  const parts = [];
  if (mid && byOwner[mid]) {
    parts.push('<div class="video-block"><h3>Combined unit</h3>'+grid([{label: mid, byCol: byOwner[mid]}])+'</div>');
  }
  const shortIds = children.length ? children.filter(id => id !== mid) : Object.keys(byOwner).filter(id => id !== mid);
  const shortRows = shortIds.filter(id => byOwner[id]).map(id => ({
    label: id.replace(/^[A-Z]+-/, ''),
    byCol: byOwner[id]
  }));
  if (shortRows.length && mid) {
    parts.push('<div class="video-block"><h3>Shorts</h3>'+grid(shortRows)+'</div>');
  } else if (!mid) {
    const id = Object.keys(byOwner)[0];
    parts.push(grid([{label: (selectedMeta && selectedMeta.id) || id || 'Lesson', byCol: byOwner[id] || {}}]));
  }
  const packs = urls.filter(u => u.indexOf('/pack/') >= 0);
  if (packs.length) {
    parts.push('<div class="video-block"><h3>Experiment pack</h3><div class="grid">'+packs.map(u => card(u)).join('')+'</div></div>');
  }
  g.innerHTML = parts.join('') || '<div class="empty">No videos yet.</div>';
}
function applyMeta(row) {
  selectedMeta = row || null;
  const mode = document.getElementById('mode');
  const btn = document.getElementById('build');
  const painted = document.getElementById('painted');
  if (!row) {
    mode.textContent = '';
    btn.textContent = 'Build this lesson';
    if (painted) { painted.hidden = true; painted.innerHTML = ''; }
    return;
  }
  if (painted) {
    const bits = [
      langPill('slides', row.slide_langs),
      langPill('caps', row.cap_langs),
      langPill('vid', row.video_langs)
    ].join('');
    painted.innerHTML = bits;
    painted.hidden = !bits;
  }
  const hkOff = row.mode !== 'tri';
  document.querySelectorAll('#mixgrid [data-cell]').forEach(el => {
    const usesHk = (el.dataset.cell || '').includes('hk');
    el.disabled = hkOff && usesHk;
    if (el.disabled) el.checked = false;
    el.parentElement.classList.toggle('on', el.checked);
  });
  if (row.mode === 'tri') {
    mode.textContent = 'Tick any of the nine speech × slide pairs. Diagonal = one language.';
  } else {
    mode.textContent = 'This lesson has no Cantonese track. The 繁 row and column are off.';
  }
  btn.textContent = row.kind === 'module' ? 'Build this module' : 'Build this lesson';
  if (row.kind === 'module') {
    const n = (row.children || []).length;
    mode.textContent = 'Module: Preview slides / Preview captions paints every child (open, shorts, close) and shows them here. Build this module then joins the videos.';
    if (n) mode.textContent += ' ' + n + ' parts in this unit.';
  }
  if (row.kind === 'minicourse') {
    const n = (row.children || []).length;
    btn.textContent = 'Build these shorts';
    mode.textContent = 'Mini-course: ' + n + ' standalone shorts. Build paints each short and does not join the videos.';
  }
}
function showLangGrid(box, urls, emptyMsg, actionId, actionLabel) {
  if (!box) return;
  if (!urls || !urls.length) {
    const go = actionId
      ? `<p><button type="button" class="empty-go" data-run="${actionId}">${actionLabel}</button></p>`
      : '';
    box.innerHTML = `<div class="empty">${emptyMsg}${go}</div>`;
    box.style.gridTemplateColumns = '';
    return;
  }
  const stamp = Date.now();
  const LABELS = {
    en:'English', zh:'Putonghua / 简', hk:'Cantonese / 繁',
    zh_cn:'Putonghua / 简', zh_hk:'Cantonese / 繁',
    'en+zh':'EN · 简 slides', 'zh+en':'简 · EN slides',
    'en+hk':'EN · 繁 slides', 'hk+en':'繁 · EN slides',
    'zh+hk':'简 · 繁 slides', 'hk+zh':'繁 · 简 slides',
    'en+zh_hk':'EN · 繁 slides', 'zh_hk+en':'繁 · EN slides'
  };
  const RANK = {en:0, zh:1, zh_cn:1, hk:2, zh_hk:2};
  const byBeat = {};
  const langsSeen = new Set();
  function fileName(u) {
    return ((u.split('/').pop() || '').split('?')[0] || '');
  }
  function stageKey(u) {
    const name = fileName(u).replace(/[.]png$/,'');
    const s = name.match(/_s(\\d+)/);
    const c = name.match(/_c(\\d+)/);
    return String(s ? Number(s[1]) : 0) + '.' + String(c ? Number(c[1]) : 0);
  }
  function beatCore(u) {
    const bits = u.split('/');
    const lang = bits[bits.length-2];
    const file = fileName(u);
    const owner = bits.length >= 5 ? bits[bits.length-4] : '';
    const stem = file.replace(/_c\\d+(?=\\.png$)/,'');
    const core = (owner && owner !== 'slides' && owner !== 'preview' ? owner + '/' : '') + stem;
    return {lang, core};
  }
  urls.forEach(u => {
    const {lang, core} = beatCore(u);
    langsSeen.add(lang);
    const pack = (byBeat[core] = byBeat[core] || {});
    (pack[lang] = pack[lang] || []).push(u);
  });
  const cols = Array.from(langsSeen).sort((a,b) => (RANK[a] ?? 8) - (RANK[b] ?? 8) || a.localeCompare(b));
  const memberOrder = ((selectedMeta && selectedMeta.children) || []).map(c => String(c.id || c.file || '').replace(/[.]ya?ml$/,''));
  function ownerOf(core) {
    const owner = String(core).split('/')[0] || '';
    return owner.replace(/[.]png$/,'');
  }
  function baseStem(core) {
    return (String(core).split('/').pop() || core).replace(/_s\\d+$/,'').replace(/[.]png$/,'');
  }
  function stageOf(core) {
    const name = (String(core).split('/').pop() || core).replace(/[.]png$/,'');
    const m = name.match(/_s(\\d+)$/);
    return m ? Number(m[1]) : 0;
  }
  const beats = Object.keys(byBeat).sort((a,b) => {
    const oa = ownerOf(a), ob = ownerOf(b);
    const ia = memberOrder.indexOf(oa);
    const ib = memberOrder.indexOf(ob);
    const ra = ia < 0 ? 50 : ia;
    const rb = ib < 0 ? 50 : ib;
    if (ra !== rb) return ra - rb;
    const ba = baseStem(a), bb = baseStem(b);
    if (ba !== bb) return ba.localeCompare(bb);
    const sa = stageOf(a), sb = stageOf(b);
    if (sa !== sb) return sa - sb;
    return a.localeCompare(b);
  });
  box.style.gridTemplateColumns = (memberOrder.length ? '108px ' : '72px ') + cols.map(() => '1fr').join(' ');
  let html = '<div class="head"><div></div>' + cols.map(l => `<div class="lbl">${LABELS[l]||l}</div>`).join('') + '</div>';
  beats.forEach(file => {
    const clean = file.replace(/[.]png$/,'');
    const bits = clean.split('/');
    const stem = bits.pop() || clean;
    const owner = bits[0] || '';
    const beat = stem.replace(/^[0-9]+_/, '').replace(/[.]png$/,'');
    const sm = beat.match(/^(.*)_s(\\d+)$/);
    const shown = sm ? (sm[1] + ' · s' + sm[2]) : beat;
    const lbl = (memberOrder.length && owner)
      ? owner.replace(/^[A-Z]+-/,'') + ' · ' + shown
      : shown;
    html += `<div class="beat"><div class="lbl">${lbl}</div>`;
    const keys = [];
    cols.forEach(l => {
      (byBeat[file][l] || []).forEach(u => {
        const k = stageKey(u);
        if (keys.indexOf(k) < 0) keys.push(k);
      });
    });
    keys.sort((a,b) => {
      const pa = a.split('.').map(Number), pb = b.split('.').map(Number);
      return (pa[0]-pb[0]) || (pa[1]-pb[1]);
    });
    const beatHasStage = keys.some(k => Number(k.split('.')[0]) > 0);
    cols.forEach(l => {
      const raw = (byBeat[file][l] || []).slice();
      const byKey = {};
      raw.forEach(u => { byKey[stageKey(u)] = u; });
      const list = keys.map(k => {
        if (beatHasStage && k === '0.0') return null;
        return byKey[k] || null;
      }).filter((u, i, arr) => {
        if (u) return true;
        return arr.some(Boolean);
      });
      if (!list.some(Boolean)) { html += '<div></div>'; return; }
      const thumbs = list.map(u => {
        if (!u) return '<div class="lb-gap"></div>';
        return `<a class="lb-open" href="${u}?t=${stamp}" data-lang="${l}" data-core="${file}"><img src="${u}?t=${stamp}" alt="${l}"></a>`;
      }).join('');
      const n = list.filter(Boolean).length;
      const extras = n > 1 ? `<figcaption>${n} cards · aligned by stage</figcaption>` : `<figcaption>${l}</figcaption>`;
      html += `<figure class="stack">${thumbs}${extras}</figure>`;
    });
    html += '</div>';
  });
  box.innerHTML = html;
}
function esc(s) {
  return String(s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}
function langBlock(obj) {
  if (!obj) return '';
  return ['en','zh','zh_hk'].map(k => {
    const lab = {en:'EN', zh:'简', zh_hk:'繁'}[k];
    const v = obj[k] || '';
    return `<span class="lang ${v?'':'miss'}"><b>${lab}</b>${v?esc(v):'—'}</span>`;
  }).join('');
}
async function showInspect(file) {
  const box = document.getElementById('inspect');
  if (!file) { box.innerHTML = '<div class="empty">Pick a short or a module on the left.</div>'; return; }
  let data;
  try {
    const res = await fetch('/api/lesson?file='+encodeURIComponent(file)+'&t='+Date.now());
    data = await res.json();
  } catch (err) {
    box.innerHTML = '<div class="empty">Could not load check. '+esc(err && err.message || err)+'</div>';
    return;
  }
  if (selected && selected !== file) return;
  if (!data.ok) { box.innerHTML = '<div class="empty">'+(data.error||'Could not read lesson')+'</div>'; return; }
  const allGaps = data.gaps || [];
  const gaps = allGaps.slice(0, 20).map(g => esc(g)).join('<br>');
  const langGaps = allGaps.filter(g => /\\(EN\\)|\\(简\\)|\\(繁\\)/.test(String(g)));
  const otherN = allGaps.length - langGaps.length;
  const gapLabel = langGaps.length
    ? (langGaps.length + ' language gap' + (langGaps.length>1?'s':''))
    : 'Check flags';
  const gapBox = allGaps.length
    ? `<div class="inspect-gaps"><strong>${gapLabel}${otherN ? ' · ' + otherN + ' other' : ''}</strong><br>${gaps}${allGaps.length>20?'<br>…':''}</div>`
    : '<div class="inspect-ok">Every listed field has English, 简体, and 繁體.</div>';
  const labels = {kicker:'Kicker',formula:'Formula',gloss:'Gloss',left:'Left',right:'Right',
    mid:'Mid',setup:'Setup',result:'Result',col1:'Col 1',col2:'Col 2',col3:'Col 3',
    step1:'Step 1',step2:'Step 2',step3:'Step 3',q1:'Q1',q2:'Q2',
    number:'Number',unit:'Unit',caption:'Caption',claim:'Claim',body:'Body',note:'Note',
    row_player:'Row player',col_player:'Col player',row1:'Row 1',row2:'Row 2',
    item1:'Item 1',item2:'Item 2',item3:'Item 3',item4:'Item 4',next:'Next'};
  const extraCols = data.used || [];
  const fieldOrder = ['title','script'].concat(extraCols.filter(c => c !== 'title' && c !== 'script' && c !== 'speech'));
  const fieldName = Object.assign({title:'Title', script:'Speech'}, labels, {s1:'Speech s1',s2:'Speech s2',s3:'Speech s3',s4:'Speech s4',s5:'Speech s5'});
  function filled(val) {
    if (val == null || val === '') return false;
    if (typeof val === 'object') return !!(val.en || val.zh || val.zh_hk);
    return String(val).trim() !== '';
  }
  const beatCards = (data.beats||[]).map(b => {
    const rows = fieldOrder.map(c => {
      if (c === 'number') {
        if (!b.number) return '';
        return `<div class="inspect-field"><div class="fname">Number</div><div>${esc(b.number)}</div></div>`;
      }
      const val = c === 'script' ? (b.script||{}) : (c === 'title' ? (b.title||{}) : (b[c]||{}));
      if (!filled(val)) return '';
      return `<div class="inspect-field"><div class="fname">${esc(fieldName[c]||c)}</div><div>${langBlock(val)}</div></div>`;
    }).join('');
    return `<article class="inspect-beat"><h4>${esc(b.id)}<span>${esc(b.visual||'')}${b.seconds? ' · '+b.seconds+'s':''}</span></h4>${rows}</article>`;
  }).join('');
  const chips = [
    data.duration ? data.duration + 's' : '',
    (data.beats||[]).length ? (data.beats||[]).length + ' sections' : '',
    data.kind === 'module' ? 'module' : 'short'
  ].filter(Boolean);
  box.innerHTML = `
    <div class="inspect-head">
      <div class="who">
        <strong>${esc(data.id)}</strong>
        <span class="ename">${esc((data.title && data.title.en) || '')}</span>
        <div class="chips">${chips.map(c => `<span class="chip">${esc(c)}</span>`).join('')}</div>
      </div>
      <div class="inspect-dl">
        <div class="inspect-field"><div class="fname">Title</div><div>${langBlock(data.title||{})}</div></div>
        <div class="inspect-field"><div class="fname">Course</div><div>${langBlock(data.course||{})}</div></div>
        <div class="inspect-field"><div class="fname">Audience</div><div>${langBlock(data.audience||{})}</div></div>
        <div class="inspect-field"><div class="fname">Objective</div><div>${langBlock(data.objective||{})}</div></div>
      </div>
    </div>
    <div id="inspect-gapbox">${gapBox}</div>
    <p class="hint">Edit wording in the Author tab. This page is the audit.</p>
    <div>${(data.children||[]).map(c => `<button type="button" class="child-link" data-open="${esc(c.file || (c.id+'.yaml'))}">${esc(c.id || c.file)} · ${esc((c.title && c.title.en) || c.title || '')}</button>`).join('')}</div>
    <details class="options" style="margin-top:12px"><summary>Field table</summary>
    ${(data.glossary||[]).length ? `<h3 style="margin:12px 0 6px">Glossary · ${data.glossary.length}</h3>
    <div style="overflow:auto"><table class="inspect-table">
      <thead><tr><th>#</th><th>Term</th></tr></thead>
      <tbody>${data.glossary.map((g,i)=>`<tr><td>${i+1}</td><td>${langBlock(g)}</td></tr>`).join('')}</tbody>
    </table></div>` : ''}
    <div class="inspect-beats">${beatCards}</div>
    ${(data.quiz||[]).length ? `<h3 style="margin:16px 0 8px">Quiz · ${(data.quiz||[]).length} items</h3>
    <div style="overflow:auto"><table class="inspect-table">
      <thead><tr><th>Item</th><th>Prompt</th><th>Answer</th></tr></thead>
      <tbody>${(data.quiz||[]).map(q => `<tr>
        <td><b>${esc(q.id)}</b><div class="muted">${esc(q.type||'')}</div></td>
        <td>${langBlock(q.prompt||{})}</td>
        <td>${langBlock(q.answer||{})}</td>
      </tr>`).join('')}</tbody></table></div>` : ''}
    </details>
    <details class="options" style="margin-top:12px"><summary>Raw YAML</summary><pre class="yaml-view">${esc(data.yaml)}</pre></details>`;
  document.querySelectorAll('#inspect .child-link[data-open]').forEach(btn => {
    btn.onclick = () => selectLesson(btn.dataset.open);
  });
  loadGlyphs(file);
  showAuthor(file, data, extraCols, labels);
}
function paintGapBox(allGaps) {
  const host = document.getElementById('inspect-gapbox');
  if (!host) return;
  if (!allGaps.length) {
    host.innerHTML = '<div class="inspect-ok">Every listed field has English, 简体, and 繁體. Slide fonts can paint the on-screen text.</div>';
    return;
  }
  host.innerHTML = `<div class="inspect-gaps"><strong>${allGaps.length} check note${allGaps.length>1?'s':''}</strong><br>${allGaps.slice(0,20).map(g=>esc(g)).join('<br>')}${allGaps.length>20?'<br>…':''}</div>`;
}
async function loadGlyphs(file) {
  try {
    const g = await (await fetch('/api/glyphs?file='+encodeURIComponent(file)+'&t='+Date.now())).json();
    if (selected !== file || !g.ok) return;
    const extra = g.gaps || [];
    if (!extra.length) return;
    paintGapBox(extra);
  } catch (e) {}
}
const VISUALS = ['title_card','definition_card','two_column','formula','takeaway','example','three_column','big_number','steps','module_open','module_close','payoff_matrix','table_grid','series','rank_line','pair','pair_chart','pair_box','schematic_chart','dag'];
const VISUAL_NAMES = {
  title_card:'Title card',
  definition_card:'Definition card',
  two_column:'Two columns',
  formula:'Formula card',
  takeaway:'Takeaway card',
  example:'Example card',
  three_column:'Three columns',
  big_number:'Big number',
  steps:'Steps card',
  module_open:'Module open',
  module_close:'Module close',
  payoff_matrix:'Payoff table',
  table_grid:'Table grid',
  series:'Five-day series',
  rank_line:'Rank line',
  pair:'Pair of tables',
  pair_chart:'Pair of histograms',
  pair_box:'Pair of boxplots',
  schematic_chart:'Schematic chart',
  dag:'DAG'
};
const VISUAL_FIELDS = {
  title_card: ['kicker'],
  definition_card: ['kicker','formula','gloss','s1','s2'],
  two_column: ['kicker','left','right','s1','s2','s3'],
  formula: ['kicker','formula','s1','s2'],
  takeaway: ['kicker','q1','q2','s1','s2','s3'],
  example: ['kicker','setup','result','s1','s2','s3'],
  three_column: ['kicker','col1','col2','col3','s1','s2','s3'],
  steps: ['kicker','step1','step2','step3','step4','step5','ex1','s1','s2','s3'],
  big_number: ['kicker','unit'],
  module_open: ['kicker','item1','item2','item3','item4'],
  module_close: ['kicker','claim','next'],
  payoff_matrix: ['kicker','row_player','col_player','row1','row2','col1','col2','note','s1','s2','s3','s4','s5'],
  table_grid: ['kicker','row1','row2','row3','row4','col1','col2','footer','s1','s2','s3'],
  series: ['kicker','row1','row2','col1','col2','col3','col4','col5','footer','s1','s2','s3'],
  rank_line: ['kicker','values','footer','s1','s2','s3'],
  pair: ['kicker','left','right','footer','s1','s2','s3'],
  pair_chart: ['kicker','left','right','footer','s1','s2','s3'],
  pair_box: ['kicker','left','right','footer','s1','s2','s3'],
  schematic_chart: ['kicker','x','y','note','event','s1','s2','s3'],
  dag: ['kicker','n1','n2','n3','role','s1','s2','s3']
};
const FIELD_META = {
  title: ['Lesson title', 'Name of this short. Students see a shorter on-screen title in each section.'],
  objective: ['Objective', 'One sentence: what they can do after this short.'],
  course: ['Course label', 'Shown in the factory list. Usually Game Theory / 博弈论.'],
  audience: ['Audience', 'Who the short is for.'],
  'on-title': ['Title', 'Large line on the card. Keep it short.'],
  speech: ['Speech', 'Whole-card voice if you do not split by stage. A 20s card is comfortable near 70 English words or 140 简/繁 characters; longer is allowed.'],
  s1: ['Speech · stage 1', 'What is said while the first stage of this card is on screen.'],
  s2: ['Speech · stage 2', 'What is said when the second stage appears.'],
  s3: ['Speech · stage 3', 'What is said when the third stage appears.'],
  s4: ['Speech · stage 4', 'What is said when the fourth stage appears.'],
  s5: ['Speech · stage 5', 'What is said when the fifth stage appears.'],
  kicker: ['Kicker', 'Small label at the top left of the card. Example: This part.'],
  formula: ['Formula or definition line', 'The sentence or equation in the middle of a definition card.'],
  gloss: ['Gloss', 'One short line under the formula.'],
  left: ['Left column', 'Left box on a two-column card.'],
  right: ['Right column', 'Right box on a two-column card.'],
  mid: ['Middle column', 'Centre box on a three-column card.'],
  setup: ['Setup', 'The situation before the result.'],
  result: ['Result', 'What follows from the setup.'],
  col1: ['Column 1', 'First box on a three-column card.'],
  col2: ['Column 2', 'Second box on a three-column card.'],
  col3: ['Column 3', 'Third box on a three-column card.'],
  step1: ['Step 1', 'First line of a steps card.'],
  step2: ['Step 2', 'Second line of a steps card.'],
  step3: ['Step 3', 'Third line of a steps card.'],
  step4: ['Step 4', 'Fourth line. Four or five steps stack down the card.'],
  step5: ['Step 5', 'Fifth line of a stacked steps card.'],
  ex1: ['Example under step 1', 'Short coffee example. ex2 … ex5 match the other steps.'],
  q1: ['Takeaway 1', 'First recap line on a takeaway card.'],
  q2: ['Takeaway 2', 'Second recap line on a takeaway card.'],
  number: ['Number', 'The big figure on a number card.'],
  unit: ['Unit', 'What the number is measured in.'],
  caption: ['On-card caption', 'Small line under the main claim.'],
  claim: ['Closing claim', 'The sentence on a module-close card.'],
  body: ['Body', 'Supporting line on the card.'],
  note: ['Table note', 'Small line under a payoff table.'],
  row_player: ['Row player', 'Name of the player who chooses the row. Usually A or You.'],
  col_player: ['Column player', 'Name of the player who chooses the column.'],
  row1: ['Row 1 label', 'Top strategy name. Example: Left, Yield, High.'],
  row2: ['Row 2 label', 'Bottom strategy name.'],
  col1: ['Column 1 label', 'Left strategy name for the other player.'],
  col2: ['Column 2 label', 'Right strategy name for the other player.'],
  item1: ['Agenda item 1', 'First bullet on a module-open card.'],
  item2: ['Agenda item 2', 'Second bullet on a module-open card.'],
  item3: ['Agenda item 3', 'Third bullet on a module-open card.'],
  item4: ['Agenda item 4', 'Fourth bullet on a module-open card.'],
  next: ['Next-unit line', 'What the close card says comes next.'],
  values: ['Values', 'Semicolon list of 3 to 6 chips. Example: 80;200;120. The same numbers can sit in every language. v1 … v6 is the other shape, one chip per line.'],
  footer: ['Footer', 'Gold line on the last stage. Example: Middle = 120, or Share 200 and 300.'],
  term: ['Locked term', 'Word the voice must keep. Same in all three languages.'],
  prompt: ['Question students see', 'The quiz stem. No answer here.'],
  answer: ['Answer key', 'For the marking sheet. Not shown to students.']
};
function trioAreas(prefix, obj, rows, tall) {
  const labs = [['en','EN'],['zh','简'],['zh_hk','繁']];
  return labs.map(([k,lab]) =>
    `<label class="field">${lab}<textarea data-trio="${esc(prefix)}" data-lang="${k}" rows="${rows}" class="${tall?'tall':''}">${esc((obj&&obj[k])||'')}</textarea></label>`
  ).join('');
}
function fieldLabel(key) {
  return (FIELD_META[key] && FIELD_META[key][0]) || key;
}
function fieldHelp(key) {
  return (FIELD_META[key] && FIELD_META[key][1]) || '';
}
function trioBlock(key, prefix, obj, rows, tall) {
  const help = fieldHelp(key);
  return `<div class="edit-row">
    <div class="edit-grid named">
      <div class="edit-name"><strong>${esc(fieldLabel(key))}</strong>${help ? `<span>${esc(help)}</span>` : ''}</div>
      ${trioAreas(prefix, obj||{}, rows, tall)}
    </div>
  </div>`;
}
function readTrio(prefix, root) {
  const o = {};
  (root || document).querySelectorAll('[data-trio="'+prefix+'"]').forEach(el => { o[el.dataset.lang] = el.value; });
  return o;
}
function speechCount(text, lang) {
  text = (text || '').trim();
  if (!text) return {n:0, ok:true, label:'0'};
  if (lang === 'en') {
    const n = text.split(/\\s+/).filter(Boolean).length;
    return {n, ok: n <= 120, label: n + ' words'};
  }
  const n = text.replace(/\\s+/g,'').length;
  return {n, ok: n <= 240, label: n + ' chars'};
}
function bindSpeechCounts(root) {
  root.querySelectorAll('textarea[data-trio^="bs-"]').forEach(el => {
    const paint = () => {
      const host = el.closest('label');
      if (!host) return;
      let tag = host.querySelector('.count-ok, .count-warn');
      if (!tag) { tag = document.createElement('span'); host.appendChild(tag); }
      const c = speechCount(el.value, el.dataset.lang);
      tag.className = c.ok ? 'count-ok' : 'count-warn';
      tag.textContent = c.label + (c.ok ? '' : (el.dataset.lang==='en' ? ' · split this section' : ' · too long'));
    };
    el.addEventListener('input', paint);
    paint();
  });
}
function beatCard(b, extraCols, labels, open) {
  extraCols = extraCols || [];
  const vis = b.visual || 'title_card';
  const want = VISUAL_FIELDS[vis] || ['kicker'];
  const fields = Array.from(new Set(want.concat(extraCols.filter(c => c !== 'number' && b[c] && (b[c].en || b[c].zh || b[c].zh_hk)))));
  const opts = VISUALS.map(v => `<option value="${v}" ${v===vis?'selected':''}>${VISUAL_NAMES[v]||v}</option>`).join('');
  return `<details class="edit-card" data-beat="${esc(b.id)}" ${open?'open':''}>
    <summary>${esc(b.id)} · ${esc(VISUAL_NAMES[vis]||vis)}${b.seconds? ' · '+b.seconds+'s':''}</summary>
    <div class="beat-tools">
      <label class="field">Id <input data-beat-id type="text" value="${esc(b.id)}"></label>
      <label class="field">Card <select data-visual>${opts}</select></label>
      <label class="field">Seconds <input data-seconds type="number" min="4" max="40" step="1" value="${esc(String(b.seconds||''))}"></label>
      <button type="button" data-up>Up</button>
      <button type="button" data-down>Down</button>
      <button type="button" data-del>Remove</button>
    </div>
    ${trioBlock('on-title', 'bt-'+b.id, b.title||{}, 2)}
    ${fields.includes('s1') ? '' : trioBlock('speech', 'bs-'+b.id, b.script||{}, 3, true)}
    ${fields.map(c => trioBlock(c, 'bf-'+b.id+'-'+c, b[c]||{}, /^s\\d$/.test(c) ? 3 : 2, /^s\\d$/.test(c))).join('')}
  </details>`;
}
function showAuthor(file, data, extraCols, labels) {
  const box = document.getElementById('author');
  if (!box) return;
  if (!data || !data.ok) {
    box.innerHTML = '<div class="empty">Pick a short on the left.</div>';
    return;
  }
  if (data.kind === 'module') {
    box.innerHTML = `<p class="hint">A module only names children. Open a short to edit speech.</p>
      <div>${(data.children||[]).map(c => `<button type="button" class="child-link" data-open="${esc(c.file || (c.id+'.yaml'))}">${esc(c.id || c.file)} · ${esc((c.title && c.title.en) || c.title || '')}</button>`).join('')}</div>`;
    box.querySelectorAll('[data-open]').forEach(btn => btn.onclick = () => selectLesson(btn.dataset.open));
    return;
  }
  extraCols = extraCols || data.used || [];
  labels = labels || {};
  box.innerHTML = `
    <div class="author-bar">
      <button id="saveedits" type="button">Save lesson</button>
      <button id="restoreedits" type="button" class="ghost-btn" ${data.has_backup?'':'disabled'}>Restore .bak</button>
      <button id="dl-yaml" type="button" class="ghost-btn">Download YAML</button>
      <button id="dl-xlsx" type="button" class="ghost-btn">Download Excel</button>
      <button id="ul-xlsx" type="button" class="ghost-btn">Import Excel</button>
      <input id="xlsx-file" type="file" accept=".xlsx" hidden>
      <span class="hint" id="editstatus"></span>
    </div>
    <div class="edit-card">
      <h4>Lesson</h4>
      <label class="field">Target seconds <input id="ed-duration" type="number" min="30" max="900" step="1" value="${esc(String(data.duration||''))}"></label>
      ${trioBlock('title', 'title', data.title||{}, 2)}
      ${trioBlock('objective', 'objective', data.objective||{}, 2)}
      ${trioBlock('course', 'course', data.course||{}, 1)}
      ${trioBlock('audience', 'audience', data.audience||{}, 1)}
    </div>
    <div id="gloss-list">${(data.glossary||[]).map((g,i)=>`<div class="edit-card" data-gloss="${i}"><h4>Glossary ${i+1} <button type="button" class="ghost-btn" data-del-gloss>Remove</button></h4>${trioBlock('term', 'gloss-'+i, g, 2)}</div>`).join('')}</div>
    <button type="button" class="ghost-btn" id="add-gloss">Add glossary row</button>
    <div id="quiz-list">${(data.quiz||[]).map(q=>`<div class="edit-card" data-quiz="${esc(q.id)}"><h4>Quiz <input data-qid value="${esc(q.id)}" style="width:6em"> <button type="button" class="ghost-btn" data-del-quiz>Remove</button></h4>
      ${trioBlock('prompt', 'qp-'+q.id, q.prompt||{}, 3)}
      ${trioBlock('answer', 'qa-'+q.id, q.answer||{}, 2)}
    </div>`).join('')}</div>
    <button type="button" class="ghost-btn" id="add-quiz">Add quiz item</button>
    <div id="beat-list">${(data.beats||[]).map((b,i)=>beatCard(b, extraCols, labels, i===0)).join('')}</div>
    <button type="button" class="ghost-btn" id="add-beat">Add section</button>`;
  bindSpeechCounts(box);
  const saveBtn = document.getElementById('saveedits');
  if (saveBtn) saveBtn.onclick = () => saveLightEdits(file, extraCols);
  const rest = document.getElementById('restoreedits');
  if (rest) rest.onclick = () => restoreEdits(file);
  const dl = document.getElementById('dl-yaml');
  if (dl) dl.onclick = () => {
    const blob = new Blob([data.yaml||''], {type:'text/yaml'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = file;
    a.click();
  };
  const xlsx = document.getElementById('dl-xlsx');
  if (xlsx) xlsx.onclick = () => { window.location = '/api/lesson/xlsx?file=' + encodeURIComponent(file); };
  const xfile = document.getElementById('xlsx-file');
  const xbtn = document.getElementById('ul-xlsx');
  if (xbtn && xfile) {
    xbtn.onclick = () => xfile.click();
    xfile.onchange = async () => {
      const picked = xfile.files && xfile.files[0];
      xfile.value = '';
      if (!picked) return;
      const status = document.getElementById('editstatus');
      if (status) status.textContent = 'Importing…';
      const res = await fetch('/api/lesson/xlsx-import?file=' + encodeURIComponent(file), {method:'POST', body: picked});
      const body = await res.json();
      if (!body.ok) {
        if (status) status.textContent = body.error || 'Import refused.';
        alert((body.error || 'Import refused.') + (body.errors ? '\\n' + body.errors.join('\\n') : ''));
        return;
      }
      if (status) status.textContent = 'Imported. ' + (body.notes || []).join(' ');
      selectLesson(file);
    };
  }
  document.getElementById('add-gloss').onclick = () => {
    const list = document.getElementById('gloss-list');
    const i = list.querySelectorAll('[data-gloss]').length;
    const wrap = document.createElement('div');
    wrap.innerHTML = `<div class="edit-card" data-gloss="${i}"><h4>Glossary ${i+1} <button type="button" class="ghost-btn" data-del-gloss>Remove</button></h4>${trioBlock('term', 'gloss-'+i, {}, 2)}</div>`;
    list.appendChild(wrap.firstChild);
  };
  document.getElementById('add-quiz').onclick = () => {
    const list = document.getElementById('quiz-list');
    const id = 'Q' + (list.querySelectorAll('[data-quiz]').length + 1);
    const wrap = document.createElement('div');
    wrap.innerHTML = `<div class="edit-card" data-quiz="${id}"><h4>Quiz <input data-qid value="${id}" style="width:6em"> <button type="button" class="ghost-btn" data-del-quiz>Remove</button></h4>
      ${trioBlock('prompt', 'qp-'+id, {}, 3)}
      ${trioBlock('answer', 'qa-'+id, {}, 2)}</div>`;
    list.appendChild(wrap.firstChild);
  };
  document.getElementById('add-beat').onclick = () => {
    const list = document.getElementById('beat-list');
    const id = 'beat-' + (list.querySelectorAll('[data-beat]').length + 1);
    const wrap = document.createElement('div');
    wrap.innerHTML = beatCard({id, visual:'title_card', seconds:24, title:{}, script:{}}, extraCols, labels, true);
    list.appendChild(wrap.firstChild);
    bindSpeechCounts(wrap);
  };
  box.onclick = (ev) => {
    const card = ev.target.closest('[data-beat]');
    if (ev.target.closest('[data-del-gloss]')) { ev.target.closest('[data-gloss]').remove(); return; }
    if (ev.target.closest('[data-del-quiz]')) { ev.target.closest('[data-quiz]').remove(); return; }
    if (!card) return;
    if (ev.target.closest('[data-del]')) {
      if (document.querySelectorAll('#beat-list [data-beat]').length < 2) return;
      if (confirm('Remove this section?')) card.remove();
      return;
    }
    const list = document.getElementById('beat-list');
    if (ev.target.closest('[data-up]') && card.previousElementSibling) list.insertBefore(card, card.previousElementSibling);
    if (ev.target.closest('[data-down]') && card.nextElementSibling) list.insertBefore(card.nextElementSibling, card);
  };
}
async function saveLightEdits(file, extraCols) {
  extraCols = extraCols || [];
  const beats = Array.from(document.querySelectorAll('#beat-list [data-beat]')).map(card => {
    const oldId = card.dataset.beat;
    const id = ((card.querySelector('[data-beat-id]')||{}).value || oldId).trim() || oldId;
    const fields = {};
    card.querySelectorAll('[data-trio^="bf-"]').forEach(el => {
      const stem = el.dataset.trio.slice(('bf-'+oldId+'-').length);
      if (stem && !fields[stem]) fields[stem] = readTrio(el.dataset.trio, card);
    });
    extraCols.forEach(c => {
      if (c === 'number') return;
      if (card.querySelector('[data-trio="bf-'+oldId+'-'+c+'"]')) fields[c] = readTrio('bf-'+oldId+'-'+c, card);
    });
    return {
      id,
      visual: (card.querySelector('[data-visual]')||{}).value || '',
      seconds: (card.querySelector('[data-seconds]')||{}).value || '',
      title: readTrio('bt-'+oldId, card),
      script: readTrio('bs-'+oldId, card),
      fields
    };
  });
  const quiz = Array.from(document.querySelectorAll('#quiz-list [data-quiz]')).map(card => {
    const oldId = card.dataset.quiz;
    const id = ((card.querySelector('[data-qid]')||{}).value || oldId).trim() || oldId;
    return {id, prompt: readTrio('qp-'+oldId, card), answer: readTrio('qa-'+oldId, card)};
  });
  const glossary = Array.from(document.querySelectorAll('#gloss-list [data-gloss]')).map(card => {
    const i = card.dataset.gloss;
    return readTrio('gloss-'+i, card);
  });
  const status = document.getElementById('editstatus');
  if (status) status.textContent = 'Saving…';
  const res = await fetch('/api/lesson/save', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      file,
      title: readTrio('title'),
      objective: readTrio('objective'),
      course: readTrio('course'),
      audience: readTrio('audience'),
      duration: (document.getElementById('ed-duration')||{}).value || '',
      beats, quiz, glossary
    })
  });
  const data = await res.json();
  if (!data.ok) {
    if (status) status.textContent = data.error || 'Save failed';
    alert(data.error || 'Save failed');
    return;
  }
  if (status) status.textContent = 'Saved. Backup: ' + (data.backup||'') + (data.valid===false ? ' · checker still has notes.' : '');
  showInspect(file);
  refresh();
}
async function restoreEdits(file) {
  if (!confirm('Replace the current YAML with the .bak from the first save?')) return;
  const status = document.getElementById('editstatus');
  if (status) status.textContent = 'Restoring…';
  const res = await fetch('/api/lesson/save', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({file, restore:true})
  });
  const data = await res.json();
  if (!data.ok) {
    if (status) status.textContent = data.error || 'Restore failed';
    alert(data.error || 'Restore failed');
    return;
  }
  if (status) status.textContent = 'Restored from ' + (data.restored||'.bak');
  showInspect(file);
  refresh();
}
function showPreviews(urls) {
  tabCount('tab-caps-n', (urls || []).length);
  showLangGrid(document.getElementById('previews'), urls, 'No caption previews yet.', 'captionpreview', 'Preview captions');
}
function showSlides(urls) {
  tabCount('tab-slides-n', (urls || []).length);
  showLangGrid(document.getElementById('slides'), urls, 'No slides yet for this lesson.', 'slidesonly', 'Preview slides only');
}
function showCovers(urls) {
  tabCount('tab-covers-n', (urls || []).length);
  const box = document.getElementById('covers');
  if (!box) return;
  if (!urls || !urls.length) {
    box.innerHTML = '<div class="empty">No covers yet.<p><button type="button" class="empty-go" data-run="makecovers">Make covers</button></p></div>';
    box.style.gridTemplateColumns = '';
    return;
  }
  const labels = {
    en:'English · matched',
    zh:'Putonghua · matched',
    hk:'Cantonese · matched',
    'en+zh':'English · 简 slides',
    'en+hk':'English · 繁 slides',
    'zh+en':'Putonghua · EN slides',
    'zh+hk':'Putonghua · 繁 slides',
    'hk+en':'Cantonese · EN slides',
    'hk+zh':'Cantonese · 简 slides'
  };
  const stamp = Date.now();
  box.style.gridTemplateColumns = 'repeat(auto-fill, minmax(320px, 1fr))';
  box.innerHTML = urls.map(u => {
    const name = ((u.split('/').pop() || '').split('?')[0] || '');
    const stem = name.replace(/\\.png$/, '');
    const cell = stem.split('_').pop() || stem;
    const label = labels[cell] || cell;
    return '<figure><a class="lb-open" data-lang="'+cell+'" href="'+u+'?t='+stamp+'"><img src="'+u+'?t='+stamp+'" alt="'+label+'"></a><figcaption>'+label+'</figcaption></figure>';
  }).join('');
}
async function loadThemes() {
  const sel = document.getElementById('theme');
  if (!sel || sel.options.length) return;
  const rows = await (await fetch('/api/themes')).json();
  sel.innerHTML = rows.map(t =>
    `<option value="${t.id}">${t.label || t.id}</option>`
  ).join('');
}
let lessonRows = [];
let listFilter = 'all';
let listArea = 'all';
let listQuery = '';
const AREA_ORDER = ['ECON','ACC','AUD','GBA','GAME'];
function renderAreaFilters() {
  const box = document.getElementById('listarea');
  if (!box) return;
  const seen = {};
  lessonRows.forEach(r => { if (r.area) seen[r.area] = true; });
  const areas = AREA_ORDER.filter(a => seen[a]).concat(Object.keys(seen).filter(a => AREA_ORDER.indexOf(a) < 0).sort());
  const chips = ['all'].concat(areas);
  box.innerHTML = chips.map(a => {
    const label = a === 'all' ? 'All areas' : a;
    const on = listArea === a ? ' on' : '';
    return '<button type="button" data-area="'+a+'" class="'+on.trim()+'">'+label+'</button>';
  }).join('');
}
function langPill(label, langs) {
  const bits = langs || [];
  if (!bits.length) return '';
  return '<span class="pill">'+label+' '+bits.join(' ')+'</span>';
}
function cardHtml(r) {
  const on = selected===r.file ? ' on' : '';
  const ctx = (moduleContext && r.file===moduleContext && selected!==r.file) ? ' ctx' : '';
  return `<div class="lesson${on}${ctx}" data-file="${r.file}">
      <div class="lesson-top">
        <b>${r.id}</b>
        <span class="pill ${r.valid?'ok':'bad'}">${r.valid?'Valid':'Invalid'}</span>
      </div>
      <div class="lesson-title">${r.title_en || r.file}</div>
      <div class="meta-row">
        <span class="pill">${r.kind==='lesson' ? r.beats+' sections' : r.beats+' shorts'}</span>
        <span class="pill gold">${r.kind==='module'?'Module':(r.kind==='minicourse'?'Mini-course':(r.mode==='tri'?'EN / 普 / 粵':'EN + 普'))}</span>
      </div>
    </div>`;
}
function renderList() {
  const box = document.getElementById('list');
  const q = (listQuery || '').trim().toLowerCase();
  const rows = lessonRows.filter(r => {
    if (listFilter !== 'all' && r.kind !== listFilter) return false;
    if (listArea !== 'all' && r.area !== listArea) return false;
    if (!q) return true;
    const hay = [r.id, r.file, r.title_en, r.title_zh, r.title_zh_hk, ...(r.children||[]).map(c => c.id+' '+(c.title_en||''))].join(' ').toLowerCase();
    return hay.includes(q);
  });
  const mods = rows.filter(r => r.kind === 'module');
  const minis = rows.filter(r => r.kind === 'minicourse');
  const shorts = rows.filter(r => r.kind === 'lesson');
  if (!rows.length) {
    box.innerHTML = '<div class="empty">'+(q ? 'No match for “'+esc(listQuery)+'”.' : 'Nothing in this filter.')+'</div>';
    return;
  }
  if (listFilter === 'all') {
    box.innerHTML =
      (minis.length ? '<div class="list-head">Mini-courses · standalone shorts, not joined</div>' + minis.map(cardHtml).join('') : '') +
      (mods.length ? '<div class="list-head">Modules · 5–10 min units</div>' + mods.map(cardHtml).join('') : '') +
      (shorts.length ? '<div class="list-head">Shorts · 1–3 min lessons</div>' + shorts.map(cardHtml).join('') : '');
  } else {
    box.innerHTML = rows.map(cardHtml).join('');
  }
}
function parentModuleOf(file) {
  if (!file) return null;
  const id = String(file).replace(/\\.ya?ml$/,'');
  const hits = lessonRows.filter(r => r.kind === 'module' && (r.children||[]).some(c => c.file === file || c.id === file || c.id === id));
  if (moduleContext) {
    const hold = hits.find(r => r.file === moduleContext || r.id === moduleContext);
    if (hold) return hold;
  }
  return hits.length ? hits[0] : null;
}
function setWorkspace(row, file) {
  const sel = document.getElementById('sel');
  const crumb = document.getElementById('crumb');
  const howto = document.getElementById('howto');
  if (howto) howto.hidden = !!(row || file);
  if (!sel) return;
  if (row && row.kind === 'module') moduleContext = row.file;
  const parent = (row && row.kind === 'module') ? null : parentModuleOf(file);
  if (parent) moduleContext = parent.file;
  if (crumb) {
    if (parent) {
      crumb.hidden = false;
      crumb.innerHTML =
        '<button type="button" class="crumb" data-back="'+esc(parent.file)+'">← '+esc(parent.id)+'</button>' +
        '<span class="crumb-sep">in module</span>' +
        '<span>'+esc(parent.title_en || '')+'</span>';
    } else if (row && row.kind === 'module') {
      crumb.hidden = false;
      crumb.innerHTML = '<span class="crumb-sep">Module</span><span>'+esc(row.id)+'</span>';
    } else {
      crumb.hidden = true;
      crumb.innerHTML = '';
    }
  }
  if (!row) {
    sel.textContent = file ? ('Selected ' + file) : 'Pick a short or a module on the left.';
    renderModuleNav(null, file);
    return;
  }
  const kind = row.kind === 'module' ? 'Module' : 'Part';
  sel.innerHTML = '<b>'+esc(row.id)+'</b> · '+esc(kind)+'<span>'+esc(row.title_en||'')+'</span><span>'+esc(row.title_zh||'')+'</span>';
  renderModuleNav(row, file);
}
function partLabel(modId, childId) {
  const id = String(childId || '');
  if (modId && id.indexOf(modId + '-') === 0) return id.slice(modId.length + 1);
  const bits = id.split('-');
  return bits.length > 1 ? bits.slice(1).join('-') : id;
}
function renderModuleNav(row, file) {
  const nav = document.getElementById('modnav');
  if (!nav) return;
  const parent = (row && row.kind === 'module') ? row : parentModuleOf(file);
  const kids = (parent && parent.children) || [];
  if (!parent || !kids.length) {
    nav.hidden = true;
    nav.innerHTML = '';
    return;
  }
  const curFile = (row && row.file) || file || '';
  const curId = (row && row.id) || String(curFile).replace(/\\.ya?ml$/,'');
  const onMod = row && row.kind === 'module';
  let html = '<button type="button" class="modnav-mod'+(onMod?' on':'')+'" data-open="'+esc(parent.file)+'">'+esc(parent.id)+'</button>';
  kids.forEach(c => {
    const f = c.file || (c.id + '.yaml');
    const on = (!onMod && (f === curFile || c.id === curId)) ? ' on' : '';
    html += '<button type="button" class="modnav-part'+on+'" data-open="'+esc(f)+'" title="'+esc(c.title_en || c.id)+'">'+esc(partLabel(parent.id, c.id))+'</button>';
  });
  nav.hidden = false;
  nav.innerHTML = html;
}
function selectLesson(file) {
  if (!file) return;
  selected = file;
  const row = lessonRows.find(r => r.file === file || r.id === file);
  setWorkspace(row, file);
  if (row) applyMeta(row);
  showInspect(file);
  loadOutputs(file);
  renderList();
}
async function loadOutputs(file) {
  const j = await (await fetch('/api/outputs?file='+encodeURIComponent(file)+'&t='+Date.now())).json();
  if (selected !== file) return;
  showSlides(j.slides || []);
  showCovers(j.covers || []);
  showPreviews(j.previews || []);
  showQuiz(j.quiz || []);
  showCells(j.cells || []);
}
async function refresh() {
  await loadThemes();
  lessonRows = await (await fetch('/api/lessons')).json();
  renderAreaFilters();
  renderList();
}
document.getElementById('wshead').addEventListener('click', (ev) => {
  const back = ev.target.closest('[data-back]');
  if (back) { selectLesson(back.dataset.back); return; }
  const open = ev.target.closest('[data-open]');
  if (open) selectLesson(open.dataset.open);
});
document.getElementById('list').onclick = (ev) => {
  const el = ev.target.closest('.lesson');
  if (!el || !el.dataset.file) return;
  selectLesson(el.dataset.file);
};
document.getElementById('listfilter').onclick = (ev) => {
  const btn = ev.target.closest('[data-filter]');
  if (!btn) return;
  listFilter = btn.dataset.filter;
  document.querySelectorAll('#listfilter [data-filter]').forEach(b => b.classList.toggle('on', b === btn));
  renderList();
};
document.getElementById('listarea').onclick = (ev) => {
  const btn = ev.target.closest('[data-area]');
  if (!btn) return;
  listArea = btn.dataset.area;
  document.querySelectorAll('#listarea [data-area]').forEach(b => b.classList.toggle('on', b === btn));
  renderList();
};
async function uploadYaml(f) {
  if (!f) return;
  const body = new FormData();
  body.append('file', f);
  const res = await fetch('/api/upload', {method:'POST', body});
  const data = await res.json();
  if (!data.ok) { alert(data.error); return; }
  selected = data.file;
  document.getElementById('sel').textContent = 'Selected: ' + selected;
  refresh();
}
document.getElementById('file').onchange = (e) => uploadYaml(e.target.files[0]);
const drop = document.getElementById('drop');
;['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.classList.add('over');
}));
;['dragleave','drop'].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.classList.remove('over');
}));
drop.addEventListener('drop', e => {
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  uploadYaml(f);
});
function syncTitleControls() {
  const match = document.getElementById('match_titles').checked;
  const wrap = document.getElementById('shared_labels_wrap');
  const hint = document.getElementById('titles_hint');
  wrap.style.display = match ? 'none' : 'block';
  hint.textContent = match
    ? 'Each video paints titles in its own language. Speech and captions stay on their own languages.'
    : 'Every video uses the same slide language below. Use this only if you want one shared picture.';
}
document.getElementById('match_titles').addEventListener('change', syncTitleControls);
syncTitleControls();
function clampFade(el) {
  let n = Number(el.value);
  if (!Number.isFinite(n)) n = 0;
  n = Math.max(0, Math.min(0.5, n));
  el.value = String(Math.round(n * 100) / 100);
  if (el.value === '') el.value = '0';
  document.querySelectorAll('.presets[data-for="'+el.id+'"] button').forEach(b => {
    b.classList.toggle('on', Number(b.dataset.v) === Number(el.value));
  });
}
['still_fade','beat_fade'].forEach(id => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener('change', () => clampFade(el));
});
document.querySelectorAll('.presets button').forEach(b => {
  b.addEventListener('click', () => {
    const el = document.getElementById(b.parentElement.dataset.for);
    if (!el) return;
    el.value = b.dataset.v;
    clampFade(el);
  });
});
document.getElementById('mixgrid').addEventListener('change', (e) => {
  const box = e.target.closest('label.cell');
  if (box) box.classList.toggle('on', e.target.checked);
});
document.getElementById('packspeeds').addEventListener('change', (e) => {
  const box = e.target.closest('label.cell');
  if (box) box.classList.toggle('on', e.target.checked);
});
document.querySelectorAll('#mixgrid [data-cell]').forEach(el => {
  el.parentElement.classList.toggle('on', el.checked);
});
function selectedCells() {
  return Array.from(document.querySelectorAll('#mixgrid [data-cell]:checked'))
    .filter(el => !el.disabled)
    .map(el => el.dataset.cell);
}
async function startJob(slidesOnly, captionPreview) {
  if (!selected) { alert('Pick a short or a module first.'); return; }
  const cells = selectedCells();
  if (!cells.length) { alert('Tick a matched video, or tick both Speech and Slides under Mix languages.'); return; }
  if (cells.length > 12 && !confirm('This will build '+cells.length+' videos. Continue?')) return;
  const runningMsg = captionPreview ? 'Stamping captions…' : (slidesOnly ? 'Painting slides…' : 'Building…');
  document.getElementById('log').textContent = runningMsg;
  setBusy(true, runningMsg);
  setJob('run', runningMsg.replace('…',''));
  const timingBox = document.getElementById('progtiming');
  if (timingBox) timingBox.hidden = true;
  setProgress(runningMsg.replace('…',''), 4, selected || '', '0:00', '');
  if (captionPreview) showTab('captions');
  else if (slidesOnly) showTab('slides');
  try {
  await fetch('/api/build', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      file: selected,
      force_tts: document.getElementById('force').checked,
      labels: document.getElementById('labels').value,
      slides_only: slidesOnly,
      caption_preview: captionPreview,
      all: false,
      options: {
        voice_en: document.getElementById('voice_en').value,
        voice_zh_cn: document.getElementById('voice_zh_cn').value,
        voice_zh_hk: document.getElementById('voice_zh_hk').value,
        tts_backend: document.getElementById('tts_backend').value,
        tts_rate: document.getElementById('tts_rate').value,
        tts_volume: document.getElementById('tts_volume').value,
        tts_pitch: document.getElementById('tts_pitch').value,
        caption_size: document.getElementById('caption_size').value,
        caption_align: document.getElementById('caption_align').value,
        caption_lines: document.getElementById('caption_lines').value,
        caption_opacity: document.getElementById('caption_opacity').value,
        cells: cells,
        match_titles: document.getElementById('match_titles').checked,
        theme: document.getElementById('theme').value,
        progress_bar: document.getElementById('progress_bar').checked ? '1' : '0',
        stage_cards: document.getElementById('stage_cards').checked ? '1' : '0',
        experiment_pack: document.getElementById('experiment_pack').checked ? '1' : '0',
        pack_speeds: Array.from(document.querySelectorAll('#packspeeds [data-speed]:checked')).map(el => el.dataset.speed).join(','),
        pack_nocap: document.getElementById('pack_nocap').checked ? '1' : '0',
        still_fade: document.getElementById('still_fade').value,
        beat_fade: document.getElementById('beat_fade').value
      }
    })
  });
  } catch (err) {
    setBusy(false);
    setJob('err', 'Error');
    document.getElementById('log').textContent = String(err && err.message || err);
    return;
  }
  const poll = setInterval(async () => {
    const j = await (await fetch('/api/job')).json();
    document.getElementById('log').textContent = j.log || j.status;
    setProgress(j.step || j.status, j.pct, j.detail || '', j.elapsed || '0:00', j.timing || '');
    if (j.log_path) {
      const box = document.getElementById('logpath');
      const href = j.log_url || ('/media/' + String(j.log_path).replace(/^out\\//,''));
      if (box) box.innerHTML = 'Log: <a href="'+href+'" target="_blank">'+j.log_path+'</a>';
    }
    if (j.log_url) {
      const a = document.getElementById('lessonlog');
      if (a) a.href = j.log_url;
    }
    if (j.status === 'running') return;
    clearInterval(poll);
    setBusy(false);
    setJob(j.status === 'ok' ? 'ok' : 'err', j.status === 'ok' ? 'Complete' : 'Error');
    showCells(j.cells || []);
    showSlides(j.slides || []);
    showPreviews(j.previews || []);
    if (j.status === 'ok') {
      if (captionPreview) showTab('captions');
      else if (slidesOnly) showTab('slides');
      else if ((j.cells || []).length) showTab('videos');
      else if ((j.previews || []).length) showTab('captions');
      else if ((j.slides || []).length) showTab('slides');
    }
    refresh();
    if (selected) loadOutputs(selected);
  }, 1000);
}
document.getElementById('build').onclick = () => startJob(false, false);
document.getElementById('slidesonly').onclick = () => startJob(true, false);
document.getElementById('captionpreview').onclick = () => startJob(false, true);
document.getElementById('makecovers').onclick = () => makeCovers();
const VOICE_SETS = {
  edge: {
    en: [
      ['en-US-GuyNeural', 'Guy (US male)'],
      ['en-US-JennyNeural', 'Jenny (US female)'],
      ['en-GB-RyanNeural', 'Ryan (UK male)'],
      ['en-GB-SoniaNeural', 'Sonia (UK female)'],
      ['en-HK-SamNeural', 'Sam (HK English male)'],
      ['en-HK-YanNeural', 'Yan (HK English female)']
    ],
    zh: [
      ['zh-CN-YunxiNeural', 'Yunxi (male)'],
      ['zh-CN-YunyangNeural', 'Yunyang (male, news)'],
      ['zh-CN-XiaoxiaoNeural', 'Xiaoxiao (female)'],
      ['zh-CN-XiaoyiNeural', 'Xiaoyi (female)']
    ],
    hk: [
      ['zh-HK-WanLungNeural', 'WanLung (male)'],
      ['zh-HK-HiuMaanNeural', 'HiuMaan (female)'],
      ['zh-HK-HiuGaaiNeural', 'HiuGaai (female)']
    ]
  },
  google: {
    en: [
      ['en-US-Neural2-D', 'Neural2 D (US male)'],
      ['en-US-Neural2-C', 'Neural2 C (US female)'],
      ['en-US-Neural2-J', 'Neural2 J (US male)'],
      ['en-GB-Neural2-B', 'Neural2 B (UK male)'],
      ['en-GB-Neural2-A', 'Neural2 A (UK female)']
    ],
    zh: [
      ['cmn-CN-Neural2-C', 'Neural2 C (male)'],
      ['cmn-CN-Neural2-B', 'Neural2 B (male)'],
      ['cmn-CN-Neural2-A', 'Neural2 A (female)'],
      ['cmn-CN-Neural2-D', 'Neural2 D (female)']
    ],
    hk: [
      ['yue-HK-Neural2-D', 'Neural2 D (male)'],
      ['yue-HK-Neural2-A', 'Neural2 A (female)'],
      ['yue-HK-Neural2-B', 'Neural2 B (male)'],
      ['yue-HK-Neural2-C', 'Neural2 C (female)']
    ]
  }
};
function fillVoices(selectId, pairs, prefer) {
  const el = document.getElementById(selectId);
  if (!el) return;
  const keep = prefer || el.value;
  el.innerHTML = pairs.map(([v, label]) => '<option value="'+v+'">'+label+'</option>').join('');
  if (pairs.some(([v]) => v === keep)) el.value = keep;
}
function applyTtsBackend() {
  const backend = document.getElementById('tts_backend').value;
  const set = backend === 'google' ? VOICE_SETS.google : VOICE_SETS.edge;
  fillVoices('voice_en', set.en);
  fillVoices('voice_zh_cn', set.zh);
  fillVoices('voice_zh_hk', set.hk);
  const hint = document.getElementById('tts_hint');
  if (hint) {
    hint.textContent = backend === 'edge'
      ? 'Edge is free and needs no key.'
      : 'Google needs an API key in VF_GOOGLE_TTS_KEY, GOOGLE_API_KEY, a .env in the video-factory root, or secrets/google-tts-key.txt. Restart the console after you set the key.';
  }
}
const ttsBackend = document.getElementById('tts_backend');
if (ttsBackend) ttsBackend.addEventListener('change', applyTtsBackend);
async function makeCovers() {
  if (!selected) { alert('Pick a short first.'); return; }
  const box = document.getElementById('covers');
  setBusy(true, 'Making covers…');
  setProgress('Making covers', 40, selected || '');
  showTab('covers');
  if (box) box.innerHTML = '<div class="empty">Making the nine covers…</div>';
  try {
    const res = await fetch('/api/covers', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({file: selected})
    });
    const raw = await res.text();
    let data = {};
    try { data = JSON.parse(raw); } catch (e) { data = {ok:false, error: raw.slice(0, 240) || ('HTTP '+res.status)}; }
    if (!data.ok) {
      if (box) box.innerHTML = '<div class="empty">'+(data.error || 'Could not make covers')+'</div>';
      alert(data.error || 'Could not make covers');
      return;
    }
    showCovers(data.covers || []);
    showTab('covers');
    setProgress('Covers ready', 100, (data.count || 0) + ' covers');
  } catch (err) {
    if (box) box.innerHTML = '<div class="empty">'+String(err)+'</div>';
    alert(String(err));
  } finally {
    setBusy(false);
  }
}
const listSearch = document.getElementById('listsearch');
if (listSearch) listSearch.addEventListener('input', (ev) => {
  listQuery = ev.target.value || '';
  renderList();
});
async function zipCourse(course) {
  setBusy(true, 'Writing course zip…');
  setProgress('Writing zip', 30, course);
  const res = await fetch('/api/bundle', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({course})
  });
  const data = await res.json();
  setBusy(false);
  const hint = document.getElementById('bundlehint');
  if (!data.ok) {
    if (hint) hint.textContent = data.error || 'Could not write zip';
    alert(data.error || 'Could not write zip');
    return;
  }
  const mb = ((data.bytes || 0)/1048576).toFixed(1);
  if (hint) hint.innerHTML = 'Wrote <a href="'+data.zip+'" download> '+data.zip.split('/').pop()+'</a> ('+mb+' MB). <a href="'+data.sop+'" target="_blank">SOP</a>';
  document.getElementById('log').textContent = 'Course pack ' + data.course + ' → ' + data.zip;
}
async function zipRa() {
  if (!selected) { alert('Pick a short or a module first.'); return; }
  setBusy(true, 'Writing RA zip…');
  setProgress('Writing RA zip', 30, selected);
  const res = await fetch('/api/ra-zip', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({file: selected})
  });
  const data = await res.json();
  setBusy(false);
  const hint = document.getElementById('rahint');
  if (!data.ok) {
    if (hint) hint.textContent = data.error || 'Could not write RA zip';
    alert(data.error || 'Could not write RA zip');
    return;
  }
  const mb = ((data.bytes || 0)/1048576).toFixed(1);
  const miss = (data.missing && data.missing.length) ? ' Missing: ' + data.missing.length + '.' : '';
  if (hint) hint.innerHTML = 'Wrote <a href="'+data.zip+'" download>'+data.zip.split('/').pop()+'</a> ('+mb+' MB).'+miss;
  document.getElementById('log').textContent = 'RA pack ' + data.id + ' → ' + data.zip;
}
document.getElementById('bundle-ra').onclick = zipRa;
document.getElementById('bundle-econ').onclick = () => zipCourse('ECON');
document.getElementById('bundle-acc').onclick = () => zipCourse('ACC');
document.getElementById('bundle-gba').onclick = () => zipCourse('GBA');
document.getElementById('bundle-lae').onclick = () => zipCourse('LAE');
document.getElementById('bundle-game').onclick = () => zipCourse('GAME');
document.getElementById('exportquiz').onclick = async () => {
  if (!selected) { alert('Pick a short or a module first.'); return; }
  setBusy(true, 'Exporting quiz…');
  setProgress('Exporting quiz', 20, selected);
  const res = await fetch('/api/quiz', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({file: selected})
  });
  const data = await res.json();
  setBusy(false);
  if (!data.ok) { alert(data.error || 'Could not export quiz'); return; }
  document.getElementById('log').textContent = 'Wrote quiz for ' + data.id + ' (' + data.count + ' files).';
  setProgress('Quiz ready', 100, data.id);
  showQuiz(data.files || []);
  refresh();
};
document.getElementById('clearcache').onclick = async () => {
  if (!selected) { alert('Pick a short or a module first.'); return; }
  if (!confirm('Delete cached slides, caption previews, clips, and videos for this lesson? Speech files stay.')) return;
  setBusy(true, 'Clearing cache…');
  const res = await fetch('/api/clear', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({file: selected})
  });
  const data = await res.json();
  setBusy(false);
  if (!data.ok) { alert(data.error || 'Could not clear cache'); return; }
  document.getElementById('log').textContent = 'Cleared ' + (data.cleared||[]).join(', ') + ' for ' + data.id + '. Next preview or build will paint from scratch.';
  setProgress('Cache cleared', 100, data.id);
  showSlides([]);
  showPreviews([]);
  showCells([]);
  await refresh();
  if (selected) loadOutputs(selected);
};
refresh();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _bytes(self, code: int, data: bytes, mime: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in {"/", "/index.html"}:
            page = HTML.replace("__OUT_ROOT__", html.escape(str(out_root())))
            self._bytes(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/lessons":
            self._json(200, list_lessons())
            return
        if path == "/api/lesson":
            file = (parse_qs(parsed.query).get("file") or [""])[0]
            try:
                self._json(200, lesson_inspect(file))
            except Exception as exc:  # noqa: BLE001
                self._json(200, {"ok": False, "error": str(exc)})
            return
        if path == "/api/outputs":
            file = (parse_qs(parsed.query).get("file") or [""])[0]
            self._json(200, lesson_outputs(file))
            return
        if path == "/api/lesson/xlsx":
            file = (parse_qs(parsed.query).get("file") or [""])[0]
            yaml_path = resolve_yaml(file)
            if yaml_path is None or yaml_path.parent.name in {"modules", "minicourses"}:
                self._json(404, {"ok": False, "error": "Pick a short, not a module or mini-course."})
                return
            dest = out_root() / "_packs" / f"{yaml_path.stem}.xlsx"
            export_lesson(load_lesson(yaml_path), dest)
            data = dest.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="{yaml_path.stem}.xlsx"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/glyphs":
            file = (parse_qs(parsed.query).get("file") or [""])[0]
            self._json(200, lesson_glyphs(file))
            return
        if path == "/api/themes":
            rows = [{"id": t["id"], "label": t["label"]} for t in list_themes()]
            self._json(200, rows)
            return
        if path == "/api/job":
            with _job_lock:
                self._json(200, dict(_job))
            return
        if path.startswith("/media/"):
            rel = path[len("/media/") :]
            root = out_root().resolve()
            target = (root / rel).resolve()
            if root not in target.parents and target != root:
                self._json(403, {"error": "forbidden"})
                return
            if not target.is_file():
                self._json(404, {"error": "missing"})
                return
            mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._bytes(200, target.read_bytes(), mime)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if parsed.path == "/api/covers":
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
                wanted = body.get("cells") if isinstance(body.get("cells"), list) else None
                self._json(200, make_covers(body.get("file", ""), wanted))
            except Exception as exc:  # noqa: BLE001
                self._json(200, {"ok": False, "error": str(exc)})
            return
        if parsed.path == "/api/build":
            body = json.loads(raw.decode("utf-8") or "{}")
            with _job_lock:
                if _job["status"] == "running":
                    self._json(409, {"error": "a build is already running"})
                    return
            t = threading.Thread(
                target=run_build,
                args=(
                    body.get("file", ""),
                    bool(body.get("force_tts")),
                    body.get("labels") or "en",
                    bool(body.get("slides_only")),
                    bool(body.get("caption_preview")),
                    body.get("options") or {},
                    bool(body.get("all")),
                ),
                daemon=True,
            )
            t.start()
            self._json(200, {"ok": True})
            return
        if parsed.path == "/api/bundle":
            body = json.loads(raw.decode("utf-8") or "{}")
            cid = (body.get("course") or "").upper()
            if not cid and body.get("file"):
                stem = Path(body["file"]).stem.upper()
                cid = course_of(stem) or ""
            if cid not in COURSES:
                self._json(400, {"ok": False, "error": "Pick ECON, ACC, GBA, LAE, or GAME."})
                return
            zpath = write_course_zip(cid, out_root())
            sop = write_sop(out_root() / "_packs" / f"SOP-{cid}.html", cid)
            self._json(200, {
                "ok": True,
                "course": cid,
                "zip": f"/media/_packs/{zpath.name}",
                "sop": f"/media/_packs/{sop.name}",
                "bytes": zpath.stat().st_size,
            })
            return
        if parsed.path == "/api/ra-zip":
            body = json.loads(raw.decode("utf-8") or "{}")
            stem = Path(body.get("file") or "").stem
            if not stem:
                self._json(400, {"ok": False, "error": "Pick a short or a module first."})
                return
            zpath, meta = write_ra_zip(stem, out_root())
            self._json(200, {
                "ok": True,
                "id": meta.get("id") or stem,
                "zip": f"/media/_packs/{zpath.name}",
                "bytes": zpath.stat().st_size,
                "missing": meta.get("missing") or [],
                "members": meta.get("members") or [],
            })
            return
        if parsed.path == "/api/lesson/xlsx-import":
            file = (parse_qs(parsed.query).get("file") or [""])[0]
            yaml_path = resolve_yaml(file)
            if yaml_path is None or yaml_path.parent.name in {"modules", "minicourses"}:
                self._json(400, {"ok": False, "error": "Pick a short, not a module or mini-course."})
                return
            if not raw:
                self._json(400, {"ok": False, "error": "No workbook uploaded."})
                return
            tmp = out_root() / "_packs" / f"{yaml_path.stem}.import.xlsx"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(raw)
            result = import_workbook(yaml_path, tmp, _dump_yaml)
            if result.get("ok"):
                invalidate_list_cache()
                invalidate_paint_cache(yaml_path.stem)
            self._json(200, result)
            return
        if parsed.path == "/api/lesson/save":
            body = json.loads(raw.decode("utf-8") or "{}")
            with _job_lock:
                if _job["status"] == "running":
                    self._json(409, {"ok": False, "error": "a build is already running"})
                    return
            self._json(200, save_light_edits(body.get("file") or "", body))
            return
        if parsed.path == "/api/quiz":
            body = json.loads(raw.decode("utf-8") or "{}")
            self._json(200, export_quiz_now(body.get("file") or ""))
            return
        if parsed.path == "/api/pdf":
            body = json.loads(raw.decode("utf-8") or "{}")
            self._json(200, export_pdf_now(body.get("file") or "", body.get("kind") or ""))
            return
        if parsed.path == "/api/clear":
            body = json.loads(raw.decode("utf-8") or "{}")
            with _job_lock:
                if _job["status"] == "running":
                    self._json(409, {"ok": False, "error": "a build is already running"})
                    return
            self._json(200, clear_lesson_cache(body.get("file") or ""))
            return
        if parsed.path == "/api/upload":
            # Minimal multipart: filename in Content-Disposition, body after blank line
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                self._json(400, {"ok": False, "error": "expected multipart upload"})
                return
            try:
                name, data = _parse_upload(ctype, raw)
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            if not name.endswith((".yaml", ".yml")):
                self._json(400, {"ok": False, "error": "only .yaml files"})
                return
            from catalog import lesson_dest

            dest = lesson_dest(name)
            dest.write_bytes(data)
            self._json(200, {"ok": True, "file": dest.name})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def _parse_upload(content_type: str, raw: bytes) -> tuple[str, bytes]:
    bound = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            bound = part.split("=", 1)[1].strip('"').encode()
    if not bound:
        raise ValueError("no multipart boundary")
    chunks = raw.split(b"--" + bound)
    for chunk in chunks:
        if b"Content-Disposition" not in chunk:
            continue
        header, _, body = chunk.partition(b"\r\n\r\n")
        if not body:
            continue
        if body.endswith(b"\r\n"):
            body = body[:-2]
        name = "upload.yaml"
        for line in header.decode("utf-8", "replace").split("\r\n"):
            if "filename=" in line:
                name = line.split("filename=")[-1].strip().strip('"')
        return name, body
    raise ValueError("no file part")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local web console for the video factory.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Lesson output root. Default: $VF_OUT if set, otherwise <repo>/out.",
    )
    args = parser.parse_args()
    if args.out is not None:
        os.environ["VF_OUT"] = str(Path(args.out).expanduser())
    root = out_root()
    LESSONS.mkdir(exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    for row in migrate_out_layout(root):
        print("out-migrate:", row)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"Video factory console: {url}")
    print(f"Output root: {root}")
    print("Leave this terminal open. Choose a YAML in the browser and click Build.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    server.serve_forever()


if __name__ == "__main__":
    main()

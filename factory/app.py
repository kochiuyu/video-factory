#!/usr/bin/env python3
"""Local web console for the video factory.

After a YAML file exists, open this page and click Build.
No further typing is required for production.

  python3 factory/app.py
  # then open http://127.0.0.1:8765
"""

from __future__ import annotations

import json
import mimetypes
import os
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
OUT = ROOT / "out"
sys.path.insert(0, str(FACTORY))

from langs import cells_for, is_tri, script_langs  # noqa: E402
from modules import load_module, module_errors  # noqa: E402
from quiz import export_lesson_quiz, export_module_quiz  # noqa: E402
from bundle import COURSES, course_of, write_course_zip, write_sop  # noqa: E402
from glyphs import scan_lesson  # noqa: E402
from validate import load_lesson, validate  # noqa: E402
from theme import list_themes  # noqa: E402

CELL_LABELS = {
    "en": "English · English captions",
    "zhcn": "Putonghua · Simplified captions",
    "zhhk": "Cantonese · Traditional captions",
    "en-en": "EN speech · EN captions",
    "en-zh": "EN speech · ZH captions",
    "zh-en": "ZH speech · EN captions",
    "zh-zh": "ZH speech · ZH captions",
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
    path = MODULES / f"{lid}.yaml"
    if not path.exists():
        return []
    try:
        mod = load_module(path)
    except Exception:
        return []
    return [str(x) for x in (mod.get("lessons") or []) if x]


def _preview_urls(lid: str) -> list[str]:
    folder = OUT / lid / "preview"
    lang_order = {"en": 0, "zh_cn": 1, "zh": 1, "zh_hk": 2}
    rows = []
    if folder.is_dir():
        for lang_dir in folder.iterdir():
            if not lang_dir.is_dir() or lang_dir.name == "_bars":
                continue
            for png in lang_dir.glob("*.png"):
                rows.append((png.name, lang_order.get(lang_dir.name, 9), lang_dir.name))
    rows.sort()
    urls = [f"/media/{lid}/preview/{lang}/{fname}" for fname, _rank, lang in rows]
    for child in _member_ids(lid):
        if child != lid:
            urls.extend(_preview_urls(child))
    return urls


def _cell_urls(lid: str) -> list[str]:
    urls: list[str] = []
    folder = OUT / lid / "cells"
    if folder.is_dir():
        urls.extend(f"/media/{lid}/cells/{p.name}" for p in sorted(folder.glob("*.mp4")))
    pack = OUT / lid / "pack"
    if pack.is_dir():
        urls.extend(f"/media/{lid}/pack/{p.name}" for p in sorted(pack.glob("*.mp4")))
    for child in _member_ids(lid):
        if child != lid:
            urls.extend(_cell_urls(child))
    return urls


def _all_cell_urls() -> list[str]:
    urls: list[str] = []
    if not OUT.is_dir():
        return urls
    for folder in sorted(OUT.iterdir()):
        cells = folder / "cells"
        if not cells.is_dir():
            continue
        for mp4 in sorted(cells.glob("*.mp4")):
            urls.append(f"/media/{folder.name}/cells/{mp4.name}")
    return urls


def _slide_urls(lid: str) -> list[str]:
    root = OUT / lid / "slides"
    rank = {"en": 0, "zh": 1, "zh_cn": 1, "zh_hk": 2}
    rows = []
    if root.is_dir():
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            for png in sorted(folder.glob("*.png")):
                rows.append((rank.get(folder.name, 8), folder.name, png.name))
    rows.sort()
    urls = [f"/media/{lid}/slides/{lang}/{fname}" for _rank, lang, fname in rows]
    for child in _member_ids(lid):
        if child != lid:
            urls.extend(_slide_urls(child))
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
    return None


def lesson_inspect(filename: str) -> dict:
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "error": "Lesson file not found."}
    try:
        raw = path.read_text(encoding="utf-8")
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
        errors = validate(lesson, glyphs=False)
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
             "item1", "item2", "item3", "item4", "next")
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


def save_light_edits(filename: str, payload: dict) -> dict:
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "error": "Lesson file not found."}
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
    by_id = {str(b.get("id")): b for b in lesson.get("beats") or []}
    for row in payload.get("beats") or []:
        beat = by_id.get(str(row.get("id") or ""))
        if not beat:
            continue
        _apply_trio(beat, "title", row.get("title"))
        script = row.get("script") or {}
        zh_key = "zh_cn" if "zh_cn" in beat else "zh"
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
        fields = row.get("fields") or {}
        for stem, values in fields.items():
            if stem in {"en", "zh", "zh_cn", "zh_hk", "id", "visual"}:
                continue
            _apply_trio(beat, stem, values)
    if isinstance(lesson.get("quiz"), list) and payload.get("quiz"):
        by_q = {str(q.get("id")): q for q in lesson["quiz"] if isinstance(q, dict)}
        for row in payload["quiz"]:
            item = by_q.get(str(row.get("id") or ""))
            if not item:
                continue
            prompt = row.get("prompt") or {}
            if "en" in prompt:
                item["en"] = prompt["en"]
            if "zh" in prompt:
                item["zh"] = prompt["zh"]
            if "zh_hk" in prompt:
                item["zh_hk"] = prompt["zh_hk"]
            answer = row.get("answer") or {}
            if "en" in answer:
                item["answer_en"] = answer["en"]
            if "zh" in answer:
                item["answer_zh"] = answer["zh"]
            if "zh_hk" in answer:
                item["answer_zh_hk"] = answer["zh_hk"]
    if isinstance(lesson.get("glossary"), list) and payload.get("glossary"):
        for i, row in enumerate(payload["glossary"]):
            if i >= len(lesson["glossary"]) or not isinstance(lesson["glossary"][i], dict):
                continue
            item = lesson["glossary"][i]
            if "en" in row:
                item["en"] = row["en"]
            if "zh" in row:
                item["zh"] = row["zh"]
            if "zh_hk" in row:
                item["zh_hk"] = row["zh_hk"]
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
        files = export_module_quiz(mod, OUT / lid)
    else:
        lesson = load_lesson(path)
        lid = lesson.get("id") or path.stem
        files = export_lesson_quiz(lesson, OUT / lid)
    urls = [f"/media/{lid}/quiz/{p.name}" for p in files]
    return {"ok": True, "id": lid, "files": urls, "count": len(files)}


def _quiz_urls(lid: str) -> list[str]:
    folder = OUT / lid / "quiz"
    if not folder.is_dir():
        return []
    return [f"/media/{lid}/quiz/{p.name}" for p in sorted(folder.iterdir()) if p.is_file()]


def _wipe_paint_tree(root: Path) -> list[str]:
    """Delete painted outputs only. Do not walk audio/."""
    if not root.is_dir():
        return []
    removed = []
    for name in ("slides", "preview", "clips", "pack", "captions", "srt"):
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
    removed = _wipe_paint_tree(OUT / lid)
    for child in _member_ids(lid):
        if child != lid:
            extra = _wipe_paint_tree(OUT / child)
            removed.extend(f"{child}/{n}" for n in extra)
    invalidate_list_cache()
    invalidate_paint_cache(lid)
    return {"ok": True, "id": lid, "cleared": removed or ["(already empty)"]}


_LIST_CACHE: dict = {"key": None, "rows": []}


def _list_cache_key() -> tuple:
    parts = []
    from catalog import iter_lesson_paths, iter_module_paths

    for path in list(iter_lesson_paths()) + list(iter_module_paths()):
        st = path.stat()
        parts.append((str(path), int(st.st_mtime), st.st_size))
    if OUT.is_dir():
        for folder in OUT.iterdir():
            cells = folder / "cells"
            if cells.is_dir():
                n = sum(1 for _ in cells.glob("*.mp4"))
                parts.append((folder.name, int(cells.stat().st_mtime), n))
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


def lesson_outputs(filename: str) -> dict:
    path = resolve_yaml(filename)
    if path is None:
        return {"ok": False, "slides": [], "previews": [], "quiz": [], "cells": [], "pack": []}
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
    from catalog import iter_lesson_paths, iter_module_paths

    lesson_files = iter_lesson_paths()
    module_files = iter_module_paths()
    parsed: dict[str, dict] = {}
    for path in lesson_files:
        try:
            parsed[path.stem] = load_lesson(path)
        except Exception:
            parsed[path.stem] = {"id": path.stem, "title_en": path.name}
    files = lesson_files + module_files
    for path in files:
        try:
            if path.parent.name == "modules":
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
                errors = [e for e in validate(lesson, glyphs=False) if not e.startswith("Beat seconds")]
        except Exception as exc:  # noqa: BLE001
            lesson, errors = {"id": path.stem, "title_en": path.name}, [str(exc)]
        lid = lesson.get("id") or path.stem
        kind = "module" if path.parent.name == "modules" else "lesson"
        cell_dir = OUT / lid / "cells"
        cells = sorted(p.name for p in cell_dir.glob("*.mp4")) if cell_dir.exists() else []
        pack_dir = OUT / lid / "pack"
        packs = sorted(p.name for p in pack_dir.glob("*.mp4")) if pack_dir.is_dir() else []
        children = []
        if kind == "module":
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
    root = OUT / lid
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
        self.step = "Starting"

    def _bump(self, value: int) -> None:
        self.pct = max(self.pct, min(99, int(value)))

    def eat(self, line: str, friendly: tuple[str, str, int] | None) -> None:
        low = (line or "").strip().lower()
        if friendly:
            self.step = friendly[0]
        if low.startswith("progress: slides"):
            frac = _parse_frac(low)
            if frac:
                hi = 92 if self.slides_only else (42 if self.caption_preview else 18)
                self._bump(_blend(6, hi, frac[0], frac[1]))
            return
        if low.startswith("progress: preview"):
            frac = _parse_frac(low)
            if frac:
                self._bump(_blend(45, 96, frac[0], frac[1]))
            return
        if low.startswith("progress: speech"):
            frac = _parse_frac(low)
            if frac:
                self._bump(_blend(20, 42, frac[0], frac[1]))
            return
        if low.startswith("progress: clip"):
            # progress: clip cell/n_cells beat/n_beats
            parts = [p for p in low.split() if "/" in p]
            if len(parts) >= 2:
                c = _parse_frac(parts[0])
                b = _parse_frac(parts[1])
                if c and b:
                    total = c[1] * b[1]
                    done = (c[0] - 1) * b[1] + b[0]
                    self._bump(_blend(48, 90, done, total))
            return
        if low.startswith("progress: concat"):
            frac = _parse_frac(low)
            if frac:
                self._bump(_blend(88, 93, frac[0], frac[1]))
            return
        if low.startswith("progress: module"):
            frac = _parse_frac(low)
            if frac:
                self._bump(_blend(8, 88, frac[0], frac[1]))
            return
        if low.startswith("progress: pack"):
            frac = _parse_frac(low)
            if frac:
                self._bump(_blend(93, 99, frac[0], frac[1]))
            return
        if low.startswith("slides-only") or low.startswith("caption-preview") or low.startswith("timing: total"):
            self.pct = 100
            return
        if friendly and friendly[2] in {0, 100}:
            if friendly[2] == 100:
                self.pct = 100
            return
        if friendly and friendly[2] and self.pct < 5:
            self._bump(min(friendly[2], 8))


def _friendly_step(line: str) -> tuple[str, str, int] | None:
    text = (line or "").strip()
    if not text:
        return None
    rules = (
        ("########", "Opening lesson", 5),
        ("slide fonts", "Checking fonts", 10),
        ("glyph:", "Checking slide text", 12),
        ("slides:", "Painting slides", 25),
        ("slides-only", "Slides ready", 100),
        ("caption-preview", "Caption preview ready", 100),
        ("timing: total", "Build time", 100),
        ("timing: breakdown", "Time by step", 100),
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
    cmd = [sys.executable, str(FACTORY / "build.py")]
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
                if parsed:
                    step, detail, _old = parsed
                    if not str(_job.get("step") or "").startswith("Finished"):
                        _job["step"] = step
                    _job["detail"] = detail
                elif raw.strip().lower().startswith("progress:"):
                    _job["detail"] = raw.strip()[10:].strip()[:160]
                    if "slides" in raw.lower():
                        _job["step"] = "Painting slides"
                    elif "speech" in raw.lower():
                        _job["step"] = "Recording speech"
                    elif "clip" in raw.lower():
                        _job["step"] = "Encoding a section"
                    elif "concat" in raw.lower():
                        _job["step"] = "Joining sections"
                    elif "pack" in raw.lower():
                        _job["step"] = "Writing experiment pack"
                    elif "preview" in raw.lower():
                        _job["step"] = "Stamping captions"
                _job["pct"] = meter.pct
        proc.wait()
        log = "".join(chunks) + ("" if proc.returncode == 0 else f"\n(exit {proc.returncode})")
        if all_lessons:
            lid = "batch"
            lesson_name = "--all"
        else:
            lesson = load_lesson(path)
            lid = lesson["id"]
            lesson_name = path.name
        lesson_log = OUT / lid / "build.log"
        latest = OUT / "last_build.log"
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
        else:
            found = sorted((OUT / lid / "cells").glob("*.mp4")) if (OUT / lid / "cells").exists() else []
            packed = sorted((OUT / lid / "pack").glob("*.mp4")) if (OUT / lid / "pack").exists() else []
            cell_urls = [f"/media/{lid}/cells/{p.name}" for p in found]
            cell_urls += [f"/media/{lid}/pack/{p.name}" for p in packed]
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
        timing_total = _job.get("timing_total") or elapsed
        timing = _job.get("timing") or ""
        done_step = f"Done in {timing_total}" if ok else "Build failed"
        done_detail = timing if ok else (log.strip().splitlines()[-1] if log.strip() else "See the log")
        with _job_lock:
            _job.update(
                status="ok" if ok else "error",
                log=log,
                step=done_step,
                detail=done_detail,
                pct=100 if ok else int(_job.get("pct") or 0),
                elapsed=elapsed,
                elapsed_s=elapsed_s,
                timing=timing,
                timing_total=timing_total,
                lesson=lesson_name,
                cells=cell_urls,
                slides=slides,
                previews=previews,
                log_url="/media/last_build.log" if all_lessons else f"/media/{lid}/build.log",
                latest_url="/media/last_build.log",
                log_path=str(latest if all_lessons else lesson_log),
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
  #buildall {
    background: transparent;
    color:var(--muted);
    border:1px solid var(--line);
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
  .slides figure.stack, .preview-table figure.stack { display:flex; flex-direction:column; gap:6px; padding:6px; background:#101820; }
  .slides figure.stack a, .preview-table figure.stack a { display:block; border-radius:8px; overflow:hidden; }
  .slides figcaption, .preview-table figcaption {
    color:#c9c1b3; font-size:11px; padding:6px 8px; background:#161f2a;
  }
  .inspect-meta { display:flex; flex-wrap:wrap; gap:8px 16px; margin:0 0 12px; font-size:13px; color:var(--muted); }
  .inspect-gaps { background:#f8eee6; border:1px solid #e4d0bc; border-radius:10px; padding:8px 12px; margin:0 0 12px; font-size:12px; color:#6a3b16; }
  .inspect-ok { background:var(--ok-wash); border:1px solid #b7c9ae; border-radius:10px; padding:8px 12px; margin:0 0 12px; font-size:12px; color:var(--ok); }
  .inspect-table { width:100%; border-collapse:collapse; font-size:12px; }
  .inspect-table th, .inspect-table td { border-bottom:1px solid var(--line); padding:8px 8px; vertical-align:top; text-align:left; }
  .inspect-table th { color:#6a7380; font-weight:650; letter-spacing:.03em; text-transform:uppercase; font-size:11px; }
  .inspect-table .lang { display:block; margin:0 0 4px; }
  .inspect-table .lang b { color:#6a7380; font-weight:650; margin-right:6px; }
  .inspect-table .miss { color:#9a3412; }
  .edit-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px 10px; margin:0 0 12px; }
  .edit-card { border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin:0 0 10px; background:#fff; }
  .edit-card h4 { margin:0 0 8px; font-size:13px; color:var(--navy); }
  .edit-card textarea {
    width:100%; min-height:54px; resize:vertical; border:1px solid #d7d0c4;
    border-radius:8px; padding:6px 8px; font:13px/1.4 ui-sans-serif, system-ui, sans-serif;
  }
  .edit-card textarea.tall { min-height:78px; }
  #saveedits { margin-top:4px; }
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
      </div>
      <div class="list-filter areas" id="listarea"></div>
      <input id="listsearch" type="search" placeholder="Search id or title…" autocomplete="off">
      <div id="list"></div>
    </section>
  </aside>
  <div class="workspace">
    <div class="wshead" id="wshead">
      <div id="sel">Pick a short or a module on the left.</div>
      <p id="mode" class="muted"></p>
    </div>
    <div class="dock">
    <nav class="tabs" id="tabs">
      <button type="button" data-tab="build" class="on">Build</button>
      <button type="button" data-tab="check">Check</button>
      <button type="button" data-tab="slides">Slides <span class="count" id="tab-slides-n"></span></button>
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
      <p class="progress-detail" id="progdetail">Choose a lesson, then make slides or build the videos.</p>
    </div>
    </div>
    <section class="tab-panel on" data-panel="build">
    <section class="card">
      <div class="howto" id="howto">
        <strong>Usual path</strong>
        <ol>
          <li>Pick a lesson on the left.</li>
          <li>Leave the three matched boxes ticked (the diagonal).</li>
          <li>Open Check if you want to confirm q1/q2 and the three languages. Then click <em>Build this lesson</em>. A module joins its shorts into one 5–10 minute unit.</li>
        </ol>
      </div>
      <div class="actions primary">
        <button id="build">Build this lesson</button>
      </div>
      <div class="actions more">
        <button id="slidesonly" type="button" title="Paint slides only. No speech, no video.">Preview slides only</button>
        <button id="captionpreview" type="button" title="Stamp caption chips on slides. No speech, no video.">Preview captions</button>
        <button id="exportquiz" type="button" title="Write student HTML, answer key, and CSV.">Export quiz</button>
        <button id="clearcache" type="button" title="Delete cached slides, caption previews, clips, and videos. Speech stays.">Paint this lesson from scratch</button>
        <button id="buildall" type="button" title="Build every short. Asks for confirm.">Build every lesson</button>
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
          <label class="cell"><input type="checkbox" data-cell="en-en-zh"> 简</label>
          <label class="cell"><input type="checkbox" data-cell="en-en-hk"> 繁</label>
          <div class="rh">Speech 简</div>
          <label class="cell"><input type="checkbox" data-cell="zh-zh-en"> EN</label>
          <label class="cell"><input type="checkbox" data-cell="zhcn" checked> 简</label>
          <label class="cell"><input type="checkbox" data-cell="zh-zh-hk"> 繁</label>
          <div class="rh">Speech 繁</div>
          <label class="cell"><input type="checkbox" data-cell="hk-hk-en"> EN</label>
          <label class="cell"><input type="checkbox" data-cell="hk-hk-zh"> 简</label>
          <label class="cell"><input type="checkbox" data-cell="zhhk" checked> 繁</label>
        </div>
      </div>
      <details class="options">
        <summary>Experiment pack and course zip</summary>
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
        <h3>Course pack for faculty <span class="badge-def">3 pilots</span></h3>
        <p class="def-note">One A4 SOP plus a zip of whatever videos, quizzes, and treatments already exist for that course. Build the modules first if the zip looks thin.</p>
        <div class="actions" style="margin:8px 0 0">
          <button id="bundle-econ" type="button">Zip Economics</button>
          <button id="bundle-acc" type="button">Zip Accounting</button>
          <button id="bundle-gba" type="button">Zip GBA</button>
        </div>
        <p class="hint" id="bundlehint">Zips land in out/_packs/ as CUHK-VF-ECON.zip, CUHK-VF-ACC.zip, CUHK-VF-GBA.zip.</p>
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
      <p class="muted" id="logpath">Logs are written to out\\&lt;ID&gt;\\build.log and out\\last_build.log</p>
      </details>
    </section>
    </section>
    <section class="tab-panel" data-panel="check">
    <section class="card">
      <div class="sec-head"><h2>Check</h2></div>
      <p class="hint">Gaps first, then wording. The field table and raw YAML stay closed.</p>
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
<script>
let selected = null;
let selectedMeta = null;
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
  if (!go) return;
  const target = document.getElementById(go.dataset.run);
  if (target) target.click();
});
try {
  const saved = localStorage.getItem('vf-tab');
  if (saved && document.querySelector('[data-panel="'+saved+'"]')) showTab(saved);
} catch (e) {}
const CELL_LABELS = {
  en: 'English · matched',
  zhcn: 'Putonghua · matched',
  zhhk: 'Cantonese · matched',
  'en-en': 'Voice EN · Captions EN',
  'en-zh': 'Voice EN · Captions ZH',
  'zh-en': 'Voice ZH · Captions EN',
  'zh-zh': 'Voice ZH · Captions ZH'
};
const MIX_WORD = {en:'EN', zh:'简', hk:'繁'};
function mixLabel(key) {
  if (CELL_LABELS[key]) return CELL_LABELS[key];
  if (key.includes('__')) {
    const bits = key.split('__').filter(Boolean);
    return bits.slice(1).join(' · ') || key;
  }
  const p = key.split('-');
  if (p.length === 3) return 'Voice '+ (MIX_WORD[p[0]]||p[0]) +' · Captions '+ (MIX_WORD[p[1]]||p[1]) +' · Slides '+ (MIX_WORD[p[2]]||p[2]);
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
  const ids = ['build','slidesonly','captionpreview','buildall','clearcache','exportquiz'];
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
function setProgress(step, pct, detail, elapsed) {
  const s = document.getElementById('progstep');
  const p = document.getElementById('progpct');
  const e = document.getElementById('progelapsed');
  const b = document.getElementById('progbar');
  const d = document.getElementById('progdetail');
  if (s) s.textContent = step || 'Idle';
  const n = Math.max(0, Math.min(100, Number(pct) || 0));
  if (p) p.textContent = n + '%';
  if (e) e.textContent = elapsed || '0:00';
  if (b) b.style.width = n + '%';
  if (d) d.textContent = detail || '';
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
  const COL_RANK = {en:0, zhcn:1, zhhk:2};
  const COL_NAME = {en:'English', zhcn:'Putonghua / 简', zhhk:'Cantonese / 繁'};
  function ownerOf(u) {
    const bits = String(u).split('/');
    const i = bits.indexOf('media');
    return i >= 0 && bits[i+1] ? bits[i+1] : '';
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
  if (!row) {
    mode.textContent = '';
    btn.textContent = 'Build this lesson';
    return;
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
    en:'English', zhcn:'Putonghua / 简体', zhhk:'Cantonese / 繁體',
    zh_cn:'Putonghua / 简体', zh:'简体', zh_hk:'Cantonese / 繁體',
    'en+zh':'EN + 简', 'zh+en':'简 + EN', 'en+zh_hk':'EN + 繁', 'zh_hk+en':'繁 + EN',
    'zh+zh_hk':'简 + 繁', 'zh_hk+zh':'繁 + 简',
    'en-en-zh':'EN speech · 简 slides', 'en-en-hk':'EN speech · 繁 slides',
    'zh-zh-en':'简 speech · EN slides', 'zh-zh-hk':'简 speech · 繁 slides',
    'hk-hk-en':'繁 speech · EN slides', 'hk-hk-zh':'繁 speech · 简 slides'
  };
  const RANK = {en:0, zhcn:1, zh:1, zh_cn:1, zhhk:2, zh_hk:2};
  const byBeat = {};
  const langsSeen = new Set();
  urls.forEach(u => {
    const bits = u.split('/');
    const lang = bits[bits.length-2];
    const file = bits[bits.length-1];
    langsSeen.add(lang);
    const owner = bits.length >= 5 ? bits[bits.length-4] : '';
    const core = (owner && owner !== 'slides' && owner !== 'preview' ? owner + '/' : '')
      + file.replace(/_s\\d+(?=\\.png$)/,'').replace(/_c\\d+(?=\\.png$)/,'');
    const pack = (byBeat[core] = byBeat[core] || {});
    (pack[lang] = pack[lang] || []).push(u);
  });
  const cols = Array.from(langsSeen).sort((a,b) => (RANK[a] ?? 8) - (RANK[b] ?? 8) || a.localeCompare(b));
  const memberOrder = ((selectedMeta && selectedMeta.children) || []).map(c => String(c.id || c.file || '').replace(/[.]ya?ml$/,''));
  function ownerOf(core) {
    const owner = String(core).split('/')[0] || '';
    return owner.replace(/[.]png$/,'');
  }
  const beats = Object.keys(byBeat).sort((a,b) => {
    const oa = ownerOf(a), ob = ownerOf(b);
    const ia = memberOrder.indexOf(oa);
    const ib = memberOrder.indexOf(ob);
    const ra = ia < 0 ? 50 : ia;
    const rb = ib < 0 ? 50 : ib;
    if (ra !== rb) return ra - rb;
    return a.localeCompare(b);
  });
  box.style.gridTemplateColumns = (memberOrder.length ? '108px ' : '72px ') + cols.map(() => '1fr').join(' ');
  let html = '<div class="head"><div></div>' + cols.map(l => `<div class="lbl">${LABELS[l]||l}</div>`).join('') + '</div>';
  beats.forEach(file => {
    const clean = file.replace(/[.]png$/,'');
    const bits = clean.split('/');
    const stem = bits.pop() || clean;
    const owner = bits[0] || '';
    const beat = stem.replace(/^[0-9]+_/, '');
    const lbl = (memberOrder.length && owner)
      ? owner.replace(/^[A-Z]+-/,'') + ' · ' + beat
      : beat;
    html += `<div class="beat"><div class="lbl">${lbl}</div>`;
    cols.forEach(l => {
      const list = (byBeat[file][l] || []).slice().sort((a,b) => {
        const name = u => (u.split('/').pop() || '');
        const rank = u => {
          const s = name(u).match(/_s(\\d+)/);
          const c = name(u).match(/_c(\\d+)/);
          if (s) return Number(s[1]);
          if (c) return 50 + Number(c[1]);
          return 99;
        };
        return rank(a) - rank(b) || name(a).localeCompare(name(b));
      });
      if (!list.length) { html += '<div></div>'; return; }
      const thumbs = list.map(u => `<a href="${u}?t=${stamp}" target="_blank"><img src="${u}?t=${stamp}" alt="${l}"></a>`).join('');
      const extras = list.length > 1 ? `<figcaption>${list.length} cards · s1 first</figcaption>` : `<figcaption>${l}</figcaption>`;
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
  const head = extraCols.map(c => `<th>${labels[c]||c}</th>`).join('');
  const rows = (data.beats||[]).map(b => {
    const extra = extraCols.map(c => {
      if (c === 'number') return `<td>${esc(b.number||'—')}</td>`;
      return `<td>${langBlock(b[c]||{})}</td>`;
    }).join('');
    return `<tr>
      <td>${b.n}<br><b>${esc(b.id)}</b><div class="muted">${esc(b.visual)}${b.seconds? ' · '+b.seconds+'s':''}</div></td>
      <td>${langBlock(b.title)}</td>
      ${extra}
      <td>${langBlock(b.script)}</td>
    </tr>`;
  }).join('');
  box.innerHTML = `
    <div class="inspect-meta">
      <strong>${esc(data.id)}</strong>
      <span>${esc(data.title.en||'')}</span>
      <span>${esc(data.title.zh||'')}</span>
      <span>${esc(data.title.zh_hk||'')}</span>
      <span>${data.duration? data.duration+'s':''}</span>
      <span>${(data.beats||[]).length} sections</span>
      <span>${(data.used||[]).length} extra fields</span>
    </div>
    <div class="inspect-meta">
      <span>Course ${langBlock(data.course||{})}</span>
      <span>Audience ${langBlock(data.audience||{})}</span>
      <span>Objective ${langBlock(data.objective||{})}</span>
    </div>
    <div id="inspect-gapbox">${gapBox}</div>
    <details class="options" style="margin-top:12px" open>
      <summary>Light edit — wording only, no new sections</summary>
      <p class="hint">Fix a title, a spoken line, a quiz stem, or a glossary pair. AI still owns the draft. Save writes the YAML and keeps a one-time .bak.</p>
      <div class="edit-card">
        <h4>Lesson</h4>
        <div class="edit-grid">${trioAreas('title', data.title||{}, 2)}</div>
        <div class="edit-grid">${trioAreas('objective', data.objective||{}, 2)}</div>
      </div>
      ${(data.glossary||[]).map((g,i)=>`<div class="edit-card"><h4>Glossary ${i+1}</h4><div class="edit-grid">${trioAreas('gloss-'+i, g, 2)}</div></div>`).join('')}
      ${(data.quiz||[]).map(q=>`<div class="edit-card"><h4>Quiz ${esc(q.id)} · prompt</h4>
        <div class="edit-grid">${trioAreas('qp-'+q.id, q.prompt||{}, 3)}</div>
        <h4>Quiz ${esc(q.id)} · answer</h4>
        <div class="edit-grid">${trioAreas('qa-'+q.id, q.answer||{}, 2)}</div>
      </div>`).join('')}
      ${data.kind==='module' ? `<p class="hint">A module only names shorts. Click a child to edit speech. Build the module to join them.</p>
        <div>${(data.children||data.beats||[]).map(c => `<button type="button" class="child-link" data-open="${esc(c.file || (c.id+'.yaml'))}">${esc(c.id || c.file)} · ${esc((c.title && c.title.en) || c.title || '')}</button>`).join('')}</div>` : (data.beats||[]).map(b=>`<div class="edit-card" data-beat="${esc(b.id)}">
        <h4>${b.n}. ${esc(b.id)} · ${esc(b.visual||'')}</h4>
        <label class="field">Seconds <input data-seconds="${esc(b.id)}" type="number" min="4" max="40" step="1" value="${esc(String(b.seconds||''))}"></label>
        <div class="edit-grid">${trioAreas('bt-'+b.id, b.title||{}, 2)}</div>
        <div class="edit-grid">${trioAreas('bs-'+b.id, b.script||{}, 3, true)}</div>
        ${extraCols.filter(c=>c!=='number' && b[c]).map(c=>`<div class="edit-grid">${trioAreas('bf-'+b.id+'-'+c, b[c]||{}, 2)}</div>`).join('')}
      </div>`).join('')}
      <button id="saveedits" type="button">Save light edits</button>
      <span class="hint" id="editstatus"></span>
    </details>
    <details class="options" style="margin-top:12px"><summary>Field table</summary>
    ${(data.glossary||[]).length ? `<h3 style="margin:12px 0 6px">Glossary · ${data.glossary.length}</h3>
    <div style="overflow:auto"><table class="inspect-table">
      <thead><tr><th>#</th><th>Term</th></tr></thead>
      <tbody>${data.glossary.map((g,i)=>`<tr><td>${i+1}</td><td>${langBlock(g)}</td></tr>`).join('')}</tbody>
    </table></div>` : ''}
    <div style="overflow:auto">
      <table class="inspect-table">
        <thead><tr><th>Section</th><th>Title</th>${head}<th>Speech</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
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
  const saveBtn = document.getElementById('saveedits');
  if (saveBtn) saveBtn.onclick = () => saveLightEdits(file, extraCols);
  document.querySelectorAll('.child-link[data-open]').forEach(btn => {
    btn.onclick = () => selectLesson(btn.dataset.open);
  });
  loadGlyphs(file);
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
function trioAreas(prefix, obj, rows, tall) {
  const labs = [['en','EN'],['zh','简'],['zh_hk','繁']];
  return labs.map(([k,lab]) =>
    `<label class="field">${lab}<textarea data-trio="${esc(prefix)}" data-lang="${k}" rows="${rows}" class="${tall?'tall':''}">${esc((obj&&obj[k])||'')}</textarea></label>`
  ).join('');
}
function readTrio(prefix) {
  const o = {};
  document.querySelectorAll('[data-trio="'+prefix+'"]').forEach(el => { o[el.dataset.lang] = el.value; });
  return o;
}
async function saveLightEdits(file, extraCols) {
  extraCols = extraCols || [];
  const beats = Array.from(document.querySelectorAll('.edit-card[data-beat]')).map(card => {
    const id = card.dataset.beat;
    const fields = {};
    extraCols.forEach(c => {
      if (c === 'number') return;
      if (document.querySelector('[data-trio="bf-'+id+'-'+c+'"]')) fields[c] = readTrio('bf-'+id+'-'+c);
    });
    return {
      id,
      seconds: (document.querySelector('[data-seconds="'+id+'"]')||{}).value || '',
      title: readTrio('bt-'+id),
      script: readTrio('bs-'+id),
      fields
    };
  });
  const quiz = Array.from(document.querySelectorAll('[data-trio^="qp-"]')).reduce((acc, el) => {
    const id = el.dataset.trio.slice(3);
    if (!acc.find(q => q.id === id)) acc.push({id, prompt: readTrio('qp-'+id), answer: readTrio('qa-'+id)});
    return acc;
  }, []);
  const glossary = [];
  for (let i=0; document.querySelector('[data-trio="gloss-'+i+'"]'); i++) glossary.push(readTrio('gloss-'+i));
  const status = document.getElementById('editstatus');
  if (status) status.textContent = 'Saving…';
  const res = await fetch('/api/lesson/save', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      file,
      title: readTrio('title'),
      objective: readTrio('objective'),
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
function showPreviews(urls) {
  tabCount('tab-caps-n', (urls || []).length);
  showLangGrid(document.getElementById('previews'), urls, 'No caption previews yet.', 'captionpreview', 'Preview captions');
}
function showSlides(urls) {
  tabCount('tab-slides-n', (urls || []).length);
  showLangGrid(document.getElementById('slides'), urls, 'No slides yet for this lesson.', 'slidesonly', 'Preview slides only');
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
function cardHtml(r) {
  return `<div class="lesson ${selected===r.file?'on':''}" data-file="${r.file}">
      <div class="lesson-top">
        <b>${r.id}</b>
        <span class="pill ${r.valid?'ok':'bad'}">${r.valid?'Valid':'Invalid'}</span>
      </div>
      <div class="lesson-title">${r.title_en || r.file}</div>
      <div class="meta-row">
        <span class="pill">${r.kind==='module' ? r.beats+' shorts' : r.beats+' sections'}</span>
        <span class="pill gold">${r.kind==='module'?'Module':(r.mode==='tri'?'EN / 普 / 粵':'EN + 普')}</span>
        ${r.cells.length? `<span class="pill">${r.cells.length} videos</span>`:''}
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
  const shorts = rows.filter(r => r.kind !== 'module');
  if (!rows.length) {
    box.innerHTML = '<div class="empty">'+(q ? 'No match for “'+esc(listQuery)+'”.' : 'Nothing in this filter.')+'</div>';
    return;
  }
  if (listFilter === 'all') {
    box.innerHTML =
      (mods.length ? '<div class="list-head">Modules · 5–10 min units</div>' + mods.map(cardHtml).join('') : '') +
      (shorts.length ? '<div class="list-head">Shorts · 1–3 min lessons</div>' + shorts.map(cardHtml).join('') : '');
  } else {
    box.innerHTML = rows.map(cardHtml).join('');
  }
}
function setWorkspace(row, file) {
  const sel = document.getElementById('sel');
  const howto = document.getElementById('howto');
  if (howto) howto.hidden = !!(row || file);
  if (!sel) return;
  if (!row) {
    sel.textContent = file ? ('Selected ' + file) : 'Pick a short or a module on the left.';
    return;
  }
  const kind = row.kind === 'module' ? 'Module' : 'Short';
  sel.innerHTML = '<b>'+esc(row.id)+'</b> · '+esc(kind)+'<span>'+esc(row.title_en||'')+'</span><span>'+esc(row.title_zh||'')+'</span>';
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
  if (!window._vfAll && !selected) { alert('Pick a short or a module first.'); return; }
  const cells = selectedCells();
  if (!cells.length) { alert('Tick a matched video, or tick both Speech and Slides under Mix languages.'); return; }
  if (cells.length > 12 && !confirm('This will build '+cells.length+' videos. Continue?')) return;
  const runningMsg = captionPreview ? 'Stamping captions…' : (slidesOnly ? 'Painting slides…' : (window._vfAll ? 'Building every lesson…' : 'Building…'));
  document.getElementById('log').textContent = runningMsg;
  setBusy(true, runningMsg);
  setJob('run', runningMsg.replace('…',''));
  setProgress(runningMsg.replace('…',''), 4, selected || 'all lessons');
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
      all: !!window._vfAll,
      options: {
        voice_en: document.getElementById('voice_en').value,
        voice_zh_cn: document.getElementById('voice_zh_cn').value,
        voice_zh_hk: document.getElementById('voice_zh_hk').value,
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
    setProgress(j.step || j.status, j.pct, j.detail || '', j.elapsed || '0:00');
    if (j.log_path) document.getElementById('logpath').textContent = 'Log file: ' + j.log_path;
    if (j.log_url) document.getElementById('lessonlog').href = j.log_url;
    if (j.status === 'running') return;
    clearInterval(poll);
    setBusy(false);
    window._vfAll = false;
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
document.getElementById('build').onclick = () => { window._vfAll = false; startJob(false, false); };
document.getElementById('slidesonly').onclick = () => { window._vfAll = false; startJob(true, false); };
document.getElementById('captionpreview').onclick = () => { window._vfAll = false; startJob(false, true); };
const listSearch = document.getElementById('listsearch');
if (listSearch) listSearch.addEventListener('input', (ev) => {
  listQuery = ev.target.value || '';
  renderList();
});
document.getElementById('buildall').onclick = () => {
  const n = lessonRows.length || 41;
  const shorts = lessonRows.filter(r => r.kind !== 'module').length;
  const mods = lessonRows.filter(r => r.kind === 'module').length;
  const msg = 'Build every file now?\\n\\n'
    + shorts + ' shorts + ' + mods + ' modules (' + n + ' jobs).\\n'
    + 'Uses the boxes ticked above. Already-built speech is reused unless Re-record is on.\\n\\n'
    + 'This can take a long time.';
  if (!confirm(msg)) return;
  window._vfAll = true;
  startJob(false, false);
};
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
document.getElementById('bundle-econ').onclick = () => zipCourse('ECON');
document.getElementById('bundle-acc').onclick = () => zipCourse('ACC');
document.getElementById('bundle-gba').onclick = () => zipCourse('GBA');
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
            self._bytes(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
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
            target = (OUT / rel).resolve()
            if OUT.resolve() not in target.parents and target != OUT.resolve():
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
                self._json(400, {"ok": False, "error": "Pick ECON, ACC, or GBA."})
                return
            zpath = write_course_zip(cid, OUT)
            sop = write_sop(OUT / "_packs" / f"SOP-{cid}.html", cid)
            self._json(200, {
                "ok": True,
                "course": cid,
                "zip": f"/media/_packs/{zpath.name}",
                "sop": f"/media/_packs/{sop.name}",
                "bytes": zpath.stat().st_size,
            })
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
    LESSONS.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"Video factory console: {url}")
    print("Leave this terminal open. Choose a YAML in the browser and click Build.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    server.serve_forever()


if __name__ == "__main__":
    main()

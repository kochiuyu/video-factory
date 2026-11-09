#!/usr/bin/env python3
"""YouTube title and description sidecars for each cell.

The lesson ``title_*`` fields stay the short cover title. This module appends
the language tag, picks the description for the speech language, and writes
one paste file next to the cell MP4. It does not call the YouTube API.

Series numbering: ids like ``STAT-M01-T09-CV`` get a ``STAT 1.09 · `` title
prefix and a ``Series: …`` first description line, plus previous / next /
playlist links when known (lesson ``youtube.series`` or ``series_links.json``).
``VF_LEGACY_YT_SERIES=1`` turns this off.

YouTube Studio rejects ASCII ``<`` and ``>`` in the title and the description.
``normalize_description`` and ``sidecar_text`` replace them with fullwidth
``＜`` and ``＞`` so the paste file can be saved. Lesson YAML is left as written.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from langs import is_tri, language_label, parse_cell, slide_folder

TITLE_GUIDE = 100
# Exclusive ceiling. len(description) >= DESCRIPTION_MAX is an error:
# the body must be strictly less than 2500 so mixed-language uploads
# keep headroom. Counted after normalize_description (newline normalize,
# trim, and ASCII angle-bracket replacement). The replacement does not
# change the count.
DESCRIPTION_MAX = 2500
DESCRIPTION_KEYS = ("description_en", "description_zh", "description_zh_hk")
# Built description (series header + links + body) above this is a warning.
DESCRIPTION_WARN = 2300
SERIES_FILE_NAMES = ("series_links.json", "series_links.yaml", "series_links.yml")

# ---------------------------------------------------------------------------
# Series numbering (title prefix, description header, prev/next links).
# VF_LEGACY_YT_SERIES=1 turns all of it off and restores the old output.
# ---------------------------------------------------------------------------
_SERIES_ID = re.compile(r"^([A-Za-z]+)-M(\d{1,3})-T(\d{1,3})(?:-|$)")


def legacy_series() -> bool:
    return os.environ.get("VF_LEGACY_YT_SERIES", "").strip() not in {"", "0", "false", "no"}


def series_parts(lesson_id: str):
    """``STAT-M01-T09-CV`` -> ``("STAT", 1, 9)``. Odd ids give ``None``."""
    m = _SERIES_ID.match(str(lesson_id or "").strip())
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2)), int(m.group(3))


def series_number(lesson_id: str) -> str:
    """``"1.09"`` for STAT-M01-T09-CV; empty when the id does not match."""
    parts = series_parts(lesson_id)
    if not parts:
        return ""
    _course, module, topic = parts
    return f"{module}.{topic:02d}"


# Course word in the title prefix, by course code and speech voice key.
# Unknown course (or voice) -> the course code itself.
COURSE_WORDS = {
    "STAT": {"en": "STAT", "zh": "统计", "zh_hk": "統計"},
}


def course_word(course: str, voice: str = "en") -> str:
    words = COURSE_WORDS.get(str(course or "").upper()) or {}
    return words.get(_voice_key(voice)) or str(course or "").upper()


def series_prefix(lesson_id: str, voice: str = "en") -> str:
    """The one place the title prefix format lives: ``"STAT 1.09 · "``
    (English speech), ``"统计 1.09 · "`` (Putonghua), ``"統計 1.09 · "``
    (Cantonese). The cover chip stays numeric (``series_number``)."""
    parts = series_parts(lesson_id)
    if not parts or legacy_series():
        return ""
    return f"{course_word(parts[0], voice)} {series_number(lesson_id)} · "


# ---------------------------------------------------------------------------
# Module title from minicourses/<COURSE>-M<mm>.yaml (title_en / _zh / _zh_hk).
# ---------------------------------------------------------------------------
_MODULE_CACHE: dict = {}


def _minicourse_dirs(lesson_path=None) -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("VF_MINICOURSES", "").strip()
    if env:
        dirs.append(Path(env))
    if lesson_path is not None:
        # Walk up from the lesson file: <root>/lessons/STAT/x.yaml -> <root>/minicourses
        for parent in Path(lesson_path).resolve().parents:
            dirs.append(parent / "minicourses")
    dirs.append(Path(__file__).resolve().parent.parent / "minicourses")  # repo root
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def module_titles(lesson_id: str, lesson_path=None) -> dict:
    """``{"en": ..., "zh": ..., "zh_hk": ...}`` (non-empty only); ``{}`` when
    the minicourse file is missing, broken or has no title."""
    key = _module_key(lesson_id)
    if not key:
        return {}
    for folder in _minicourse_dirs(lesson_path):
        path = folder / f"{key}.yaml"
        if not path.is_file():
            continue
        cache_key = str(path)
        if cache_key not in _MODULE_CACHE:
            try:
                import yaml

                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
            titles = {}
            if isinstance(data, dict):
                for voice, field in (("en", "title_en"), ("zh", "title_zh"), ("zh_hk", "title_zh_hk")):
                    value = data.get(field)
                    if isinstance(value, str) and value.strip():
                        titles[voice] = value.strip()
            _MODULE_CACHE[cache_key] = titles
        return dict(_MODULE_CACHE[cache_key])
    return {}


def module_title(lesson_id: str, voice: str, titles: dict | None = None, lesson_path=None) -> str:
    """Module title in the speech language. ``zh_hk`` falls back to ``zh``."""
    if titles is None:
        titles = module_titles(lesson_id, lesson_path)
    vk = _voice_key(voice)
    if vk == "zh_hk":
        return titles.get("zh_hk") or titles.get("zh") or ""
    return titles.get(vk) or ""


# Slide-script names. Speech labels are separate: English / 普通话 / 粵語.
_SLIDE_LABEL = {
    "en": "English",
    "zh": "简体",
    "zh_hk": "繁體",
}


def _voice_and_second(cell: str) -> tuple[str, str | None]:
    parsed = parse_cell(cell)
    if not parsed:
        raise ValueError(f"Unknown cell {cell!r}.")
    voice, _caption, slide = parsed
    primary = slide_folder(voice)
    second = slide_folder(slide)
    if second == primary:
        return voice, None
    return voice, second


def base_title(lesson: dict, voice: str) -> str:
    """Cover title for the speech language. Traditional falls back to 简体."""
    if voice == "zh_hk":
        return str(lesson.get("title_zh_hk") or lesson.get("title_zh") or "").strip()
    if voice in {"zh", "zh_cn"}:
        return str(lesson.get("title_zh") or "").strip()
    return str(lesson.get("title_en") or "").strip()


def youtube_title(lesson: dict, cell: str) -> str:
    """Base title plus a language tag.

    Mono cells name the speech language only. Mixed cells name speech and
    the extra slide language. English tags use halfwidth parentheses.
    Chinese tags use fullwidth parentheses. Putonghua tags stay in 简体
    (画面); Cantonese tags stay in 繁體 (畫面). ASCII ``<`` and ``>`` in the
    base title are replaced with fullwidth forms.
    """
    return sanitize_youtube_text(
        series_prefix(lesson.get("id", ""), _voice_and_second(cell)[0])
        + unprefixed_title(lesson, cell)
    )


def unprefixed_title(lesson: dict, cell: str) -> str:
    """Base title plus language tag, without the series prefix."""
    voice, second = _voice_and_second(cell)
    base = base_title(lesson, voice)
    return sanitize_youtube_text(base + language_label(voice, second, "title"))


def sanitize_youtube_text(value: str) -> str:
    """Replace ASCII ``<`` and ``>`` with fullwidth ``＜`` and ``＞``.

    YouTube Studio will not save a title or description that contains the
    ASCII brackets. Fullwidth forms keep an arrow such as ``->`` readable
    as ``-＞``. The swap is one character for one character.
    """
    if "<" not in value and ">" not in value:
        return value
    return value.replace("<", "＜").replace(">", "＞")


def normalize_description(value: str) -> str:
    """Trim the body and make it safe to paste into YouTube Studio.

    Newlines are normalized and surrounding whitespace is removed. ASCII
    ``<`` and ``>`` become fullwidth ``＜`` and ``＞``. Length is counted
    after this step; the bracket swap does not change it.
    """
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return sanitize_youtube_text(text)


def _description_key(voice: str) -> str:
    if voice == "zh_hk":
        return "description_zh_hk"
    if voice in {"zh", "zh_cn"}:
        return "description_zh"
    return "description_en"


def description_body(lesson: dict, cell: str) -> str:
    """Description of the primary speech language. Missing text is empty."""
    block = lesson.get("youtube")
    if not isinstance(block, dict):
        return ""
    voice, _second = _voice_and_second(cell)
    raw = block.get(_description_key(voice))
    if not isinstance(raw, str):
        return ""
    return normalize_description(raw)


_SERIES_WORDS = {
    # voice: (series, lesson fmt with total, lesson fmt, prev, next, playlist)
    "en": ("Series: ", "Lesson {t}/{n}", "Lesson {t}", "Previous: ", "Next: ", "Playlist: "),
    "zh": ("系列：", "第 {t}/{n} 课", "第 {t} 课", "上一课：", "下一课：", "播放列表："),
    "zh_hk": ("系列：", "第 {t}/{n} 課", "第 {t} 課", "上一課：", "下一課：", "播放清單："),
}


def _voice_key(voice: str) -> str:
    if voice in {"zh", "zh_cn"}:
        return "zh"
    if voice in {"hk", "zh_hk"}:
        return "zh_hk"
    return "en"


def load_series_links(lesson_path=None, lesson_id: str = "") -> dict:
    """Links file plus, when the file gives no total, a total counted from
    ``<COURSE>-M<mm>-T*.yaml`` siblings of the lesson."""
    data = _read_series_links(lesson_path)
    key = _module_key(lesson_id)
    if key and lesson_path is not None:
        entry = data.get(key) if isinstance(data.get(key), dict) else {}
        if not isinstance(entry.get("total"), int):
            count = len(list(Path(lesson_path).parent.glob(f"{key}-T*.yaml")))
            if count:
                data = dict(data, **{key: dict(entry, total=count)})
    if key and lesson_path is not None:
        entry = data.get(key) if isinstance(data.get(key), dict) else {}
        if not isinstance(entry.get("module_title"), dict):
            titles = module_titles(lesson_id, lesson_path)
            if titles:
                data = dict(data, **{key: dict(entry, module_title=titles)})
    return data


def _read_series_links(lesson_path=None) -> dict:
    """Read ``series_links.json`` (or .yaml). ``VF_SERIES_LINKS`` wins, then
    the lesson's folder. Missing or broken file -> ``{}``."""
    candidates = []
    env = os.environ.get("VF_SERIES_LINKS", "").strip()
    if env:
        candidates.append(Path(env))
    if lesson_path is not None:
        folder = Path(lesson_path).parent
        candidates.extend(folder / name for name in SERIES_FILE_NAMES)
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".json":
                data = json.loads(text)
            else:
                import yaml

                data = yaml.safe_load(text)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _module_key(lesson_id: str) -> str:
    parts = series_parts(lesson_id)
    return f"{parts[0]}-M{parts[1]:02d}" if parts else ""


def series_info(lesson: dict, cell: str, links: dict | None = None) -> dict:
    """``total``, ``prev``, ``next``, ``playlist`` for one cell (same mix only).

    Lesson ``youtube.series`` (``prev_url_<cell>`` etc., ``total``) wins over
    the links file. Unknown values are left out, never blank.
    """
    lid = str(lesson.get("id") or "")
    info: dict = {}
    entry = (links or {}).get(_module_key(lid)) or {}
    if isinstance(entry, dict):
        if isinstance(entry.get("total"), int):
            info["total"] = entry["total"]
        if isinstance(entry.get("module_title"), dict):
            info["module_title"] = entry["module_title"]
        cell_entry = entry.get(cell) or {}
        if isinstance(cell_entry, dict):
            urls = cell_entry.get("urls") or {}
            order = list(entry.get("order") or cell_entry.get("order") or [])
            if cell_entry.get("playlist_url"):
                info["playlist"] = str(cell_entry["playlist_url"])
            if lid in order:
                i = order.index(lid)
                if i > 0 and urls.get(order[i - 1]):
                    info["prev"] = str(urls[order[i - 1]])
                if i + 1 < len(order) and urls.get(order[i + 1]):
                    info["next"] = str(urls[order[i + 1]])
    block = lesson.get("youtube")
    series = block.get("series") if isinstance(block, dict) else None
    if isinstance(series, dict):
        if isinstance(series.get("total"), int):
            info["total"] = series["total"]
        for key in ("prev", "next", "playlist"):
            value = series.get(f"{key}_url_{cell}")
            if isinstance(value, str) and value.strip():
                info[key] = value.strip()
    return info


def series_header(lesson: dict, cell: str, total: int | None = None, titles: dict | None = None) -> str:
    """``Series: STAT M01 · <module title> · English · Lesson 09/15`` in the
    speech language. ``titles`` comes from the links dict (``load_series_links``);
    otherwise the repo-root ``minicourses/`` file is read. No title -> omitted."""
    parts = series_parts(lesson.get("id", ""))
    if not parts or legacy_series():
        return ""
    course, module, topic = parts
    voice, second = _voice_and_second(cell)
    words = _SERIES_WORDS[_voice_key(voice)]
    t = f"{topic:02d}"
    lesson_part = words[1].format(t=t, n=f"{total:02d}") if total else words[2].format(t=t)
    label = language_label(voice, second, "tag")
    mtitle = module_title(str(lesson.get("id") or ""), voice, titles)
    mpart = f" · {mtitle}" if mtitle else ""
    return sanitize_youtube_text(f"{words[0]}{course} M{module:02d}{mpart} · {label} · {lesson_part}")


def series_block(lesson: dict, cell: str, links: dict | None = None) -> str:
    info = series_info(lesson, cell, links)
    header = series_header(lesson, cell, info.get("total"), info.get("module_title"))
    if not header:
        return ""
    voice, _second = _voice_and_second(cell)
    words = _SERIES_WORDS[_voice_key(voice)]
    lines = [header]
    for key, label in (("prev", words[3]), ("next", words[4]), ("playlist", words[5])):
        if info.get(key):
            lines.append(label + info[key])
    return sanitize_youtube_text("\n".join(lines))


def description_for_cell(lesson: dict, cell: str, links: dict | None = None) -> str:
    """Series block (unless legacy), a blank line, then the speech-language body."""
    body = description_body(lesson, cell)
    block = series_block(lesson, cell, links)
    if block and body:
        return f"{block}\n\n{body}"
    return block or body


def sidecar_text(title: str, description: str) -> str:
    """Line 1 is the title, then a blank line, then the description body.

    The title and the body are both sanitized, so the paste file contains
    no ASCII ``<`` or ``>`` even when the caller passes raw lesson text.
    """
    safe_title = sanitize_youtube_text(title)
    body = normalize_description(description) if description else ""
    if body:
        return f"{safe_title}\n\n{body}\n"
    return f"{safe_title}\n\n"


def _uses_hk(lesson: dict) -> bool:
    if str(lesson.get("title_zh_hk") or "").strip():
        return True
    beats = lesson.get("beats")
    if isinstance(beats, list) and beats and all(isinstance(b, dict) for b in beats):
        return is_tri(lesson)
    return False


def cells_to_check(lesson: dict) -> list[str]:
    """Mono cells, plus mixed pairs, for length checks."""
    names = ["en", "zh"]
    if _uses_hk(lesson):
        names.append("hk")
    out = list(names)
    for voice in names:
        for slide in names:
            if voice != slide:
                out.append(f"{voice}+{slide}")
    return out


def title_issue(lesson: dict, cell: str) -> tuple[str, str]:
    """``ok``, ``warn``, or ``error`` for one cell's YouTube title.

    Over 100 characters is an error for a mono cell whose base title still
    fits in 100. It is a warning when the base title is already over 100,
    and a warning for every mixed cell: the speech/slides tag is longer,
    and existing English cover titles plus that tag already pass 100.
    """
    title = youtube_title(lesson, cell)
    if len(title) <= TITLE_GUIDE:
        return "ok", ""
    voice, _second = _voice_and_second(cell)
    base = base_title(lesson, voice)
    message = (
        f"YouTube title for {cell} is {len(title)} characters"
        f" (guidance {TITLE_GUIDE}): {title}"
    )
    if "+" in cell or len(base) > TITLE_GUIDE:
        return "warn", message
    if len(unprefixed_title(lesson, cell)) <= TITLE_GUIDE:
        # Only the series prefix pushed it over: shorten, but do not fail.
        return "warn", message
    return "error", message


def youtube_errors(lesson: dict) -> list[str]:
    errors: list[str] = []
    raw = lesson.get("youtube", None)
    if raw is not None:
        if not isinstance(raw, dict):
            errors.append(
                "youtube must be a mapping with description_en, description_zh,"
                " and description_zh_hk."
            )
        else:
            known = set(DESCRIPTION_KEYS)
            for key, value in raw.items():
                if key == "series":
                    if value is not None and not isinstance(value, dict):
                        errors.append("youtube.series must be a mapping of prev_url_<cell>, next_url_<cell>, playlist_url_<cell>, total.")
                    elif isinstance(value, dict):
                        for sk, sv in value.items():
                            if sk == "total":
                                if not isinstance(sv, int):
                                    errors.append("youtube.series.total must be an integer.")
                            elif not re.match(r"^(prev|next|playlist)_url_.+$", str(sk)):
                                errors.append(f"youtube.series has unknown field {sk}.")
                            elif sv is not None and not isinstance(sv, str):
                                errors.append(f"youtube.series.{sk} must be a string URL.")
                    continue
                if key not in known:
                    errors.append(f"youtube has unknown field {key}.")
                    continue
                if value is None:
                    continue
                if not isinstance(value, str):
                    errors.append(f"youtube.{key} must be a string.")
                    continue
                body = normalize_description(value)
                if len(body) >= DESCRIPTION_MAX:
                    errors.append(
                        f"youtube.{key} is {len(body)} characters;"
                        f" it must be strictly less than {DESCRIPTION_MAX}."
                    )
    for cell in cells_to_check(lesson):
        status, message = title_issue(lesson, cell)
        if status == "error":
            errors.append(message)
    return errors


def youtube_warnings(lesson: dict, cells=None, links: dict | None = None) -> list[str]:
    """Title-length warnings. ``cells`` limits the check to a build selection."""
    if cells is None:
        names = cells_to_check(lesson)
    elif isinstance(cells, dict):
        names = list(cells)
    else:
        names = list(cells)
    warnings: list[str] = []
    for name in names:
        status, message = title_issue(lesson, name)
        if status == "warn":
            warnings.append(message)
        try:
            built = description_for_cell(lesson, name, links)
        except ValueError:
            continue
        if len(built) > DESCRIPTION_WARN:
            warnings.append(
                f"YouTube description for {name} is {len(built)} characters with the"
                f" series header and links (warning above {DESCRIPTION_WARN},"
                f" limit {DESCRIPTION_MAX})."
            )
    return warnings


def write_youtube_sidecars(lesson: dict, cells: dict, out_dir: Path, links: dict | None = None) -> list[Path]:
    """Write ``<id>_<cell>.youtube.txt`` beside each requested cell MP4."""
    folder = Path(out_dir) / "cells"
    folder.mkdir(parents=True, exist_ok=True)
    lid = str(lesson.get("id") or "lesson").strip() or "lesson"
    written: list[Path] = []
    for name in cells:
        title = youtube_title(lesson, name)
        body = description_for_cell(lesson, name, links)
        path = folder / f"{lid}_{name}.youtube.txt"
        path.write_text(sidecar_text(title, body), encoding="utf-8")
        written.append(path)
    return written

#!/usr/bin/env python3
"""YouTube title and description sidecars for each cell.

The lesson ``title_*`` fields stay the short cover title. This module appends
the language tag, picks the description for the speech language, and writes
one paste file next to the cell MP4. It does not call the YouTube API.
"""

from __future__ import annotations

from pathlib import Path

from langs import is_tri, parse_cell, slide_folder

TITLE_GUIDE = 100
DESCRIPTION_MAX = 5000
DESCRIPTION_KEYS = ("description_en", "description_zh", "description_zh_hk")

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
    (画面); Cantonese tags stay in 繁體 (畫面).
    """
    voice, second = _voice_and_second(cell)
    base = base_title(lesson, voice)
    if voice == "en":
        if not second:
            return f"{base} (English)"
        return f"{base} (Speech: English · Slides: {_SLIDE_LABEL[second]})"
    speech = "普通话" if voice in {"zh", "zh_cn"} else "粵語"
    if not second:
        return f"{base} ({speech})"
    picture = "画面" if voice in {"zh", "zh_cn"} else "畫面"
    return f"{base}（旁白：{speech} · {picture}：{_SLIDE_LABEL[second]}）"


def normalize_description(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _description_key(voice: str) -> str:
    if voice == "zh_hk":
        return "description_zh_hk"
    if voice in {"zh", "zh_cn"}:
        return "description_zh"
    return "description_en"


def description_for_cell(lesson: dict, cell: str) -> str:
    """Description of the primary speech language. Missing text is empty."""
    block = lesson.get("youtube")
    if not isinstance(block, dict):
        return ""
    voice, _second = _voice_and_second(cell)
    raw = block.get(_description_key(voice))
    if not isinstance(raw, str):
        return ""
    return normalize_description(raw)


def sidecar_text(title: str, description: str) -> str:
    """Line 1 is the title, then a blank line, then the description body."""
    body = normalize_description(description) if description else ""
    if body:
        return f"{title}\n\n{body}\n"
    return f"{title}\n\n"


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
                if key not in known:
                    errors.append(f"youtube has unknown field {key}.")
                    continue
                if value is None:
                    continue
                if not isinstance(value, str):
                    errors.append(f"youtube.{key} must be a string.")
                    continue
                body = normalize_description(value)
                if len(body) > DESCRIPTION_MAX:
                    errors.append(
                        f"youtube.{key} is {len(body)} characters;"
                        f" the maximum is {DESCRIPTION_MAX}."
                    )
    for cell in cells_to_check(lesson):
        status, message = title_issue(lesson, cell)
        if status == "error":
            errors.append(message)
    return errors


def youtube_warnings(lesson: dict, cells=None) -> list[str]:
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
    return warnings


def write_youtube_sidecars(lesson: dict, cells: dict, out_dir: Path) -> list[Path]:
    """Write ``<id>_<cell>.youtube.txt`` beside each requested cell MP4."""
    folder = Path(out_dir) / "cells"
    folder.mkdir(parents=True, exist_ok=True)
    lid = str(lesson.get("id") or "lesson").strip() or "lesson"
    written: list[Path] = []
    for name in cells:
        title = youtube_title(lesson, name)
        body = description_for_cell(lesson, name)
        path = folder / f"{lid}_{name}.youtube.txt"
        path.write_text(sidecar_text(title, body), encoding="utf-8")
        written.append(path)
    return written

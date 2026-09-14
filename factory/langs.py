#!/usr/bin/env python3
"""Which narration tracks a lesson carries."""

from __future__ import annotations


def beat_text(beat: dict, lang: str) -> str:
    if lang == "zh_cn":
        return (beat.get("zh_cn") or beat.get("zh") or "").strip()
    return (beat.get(lang) or "").strip()


def script_langs(lesson: dict) -> list[str]:
    beats = lesson.get("beats") or []
    if any(beat_text(b, "zh_hk") for b in beats):
        return ["en", "zh_cn", "zh_hk"]
    return ["en", "zh"]


def is_tri(lesson: dict) -> bool:
    return script_langs(lesson) == ["en", "zh_cn", "zh_hk"]


def cells_for(lesson: dict) -> dict[str, tuple[str, str, str]]:
    """cell name -> (voice, caption, slide). Defaults are matched languages."""
    if is_tri(lesson):
        return {
            "en": ("en", "en", "en"),
            "zhcn": ("zh_cn", "zh_cn", "zh"),
            "zhhk": ("zh_hk", "zh_hk", "zh_hk"),
        }
    return {
        "en-en": ("en", "en", "en"),
        "en-zh": ("en", "zh", "en"),
        "zh-en": ("zh", "en", "zh"),
        "zh-zh": ("zh", "zh", "zh"),
    }


# Console checkbox ids -> audio language folder.
TRACK_ALIASES = {
    "en": "en",
    "zhcn": "zh_cn",
    "zh_cn": "zh_cn",
    "zh": "zh",
    "zhhk": "zh_hk",
    "zh_hk": "zh_hk",
    "hk": "zh_hk",
}

# Short token used in mix names: en-zh-hk
_MIX_TOKEN = {
    "en": "en",
    "zh": "zh_cn",
    "zh_cn": "zh_cn",
    "zhcn": "zh_cn",
    "hk": "zh_hk",
    "zh_hk": "zh_hk",
    "zhhk": "zh_hk",
}
_SHORT = {
    "en": "en",
    "zh": "zh",
    "zh_cn": "zh",
    "zh_hk": "hk",
}


def slide_folder(lang: str) -> str:
    return label_code(lang)


def bilingual_pair(voice: str, caption: str, slide: str) -> tuple[str, str | None]:
    """When a mix uses more than one language, paint EN + that Chinese on the slide."""
    folders: list[str] = []
    for lang in (voice, caption, slide):
        folder = slide_folder(lang)
        if folder not in folders:
            folders.append(folder)
    primary = slide_folder(slide)
    if len(folders) <= 1:
        return primary, None
    if primary == "en":
        second = next((folder for folder in folders if folder != "en"), "zh")
    else:
        second = "en" if "en" in folders else next((folder for folder in folders if folder != primary), None)
    if second == primary:
        second = None
    return primary, second


def mix_name(voice: str, caption: str, slide: str) -> str:
    return f"{_SHORT.get(voice, voice)}-{_SHORT.get(caption, caption)}-{_SHORT.get(slide, slide)}"


def parse_mix(token: str) -> tuple[str, str, str] | None:
    raw = (token or "").strip().lower().replace("/", "-").replace("+", "-")
    parts = [p for p in raw.split("-") if p]
    if len(parts) != 3:
        return None
    if not all(p in _MIX_TOKEN for p in parts):
        return None
    voice = _MIX_TOKEN[parts[0]]
    caption = _MIX_TOKEN[parts[1]]
    slide = slide_folder(_MIX_TOKEN[parts[2]])
    return voice, caption, slide


def parse_wanted(raw) -> list[str] | None:
    if raw is None or raw == "" or raw == []:
        return None
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in raw if str(p).strip()]
    out: list[str] = []
    for part in parts:
        key = TRACK_ALIASES.get(part, part)
        if key not in out:
            out.append(key)
    return out or None


def selected_cells(lesson: dict, wanted: list[str] | None) -> dict[str, tuple[str, str, str]]:
    cells = cells_for(lesson)
    if not wanted:
        return cells
    out: dict[str, tuple[str, str, str]] = {}
    allow = set(wanted)
    if "zh_cn" in allow:
        allow.add("zh")
    for token in wanted:
        mix = parse_mix(token)
        if mix:
            out[mix_name(*mix)] = mix
            continue
        key = TRACK_ALIASES.get(token, token)
        for name, triple in cells.items():
            if name == token or triple[0] == key or name in allow:
                out[name] = triple
    return out or cells


def selected_langs(lesson: dict, wanted: list[str] | None) -> list[str]:
    have = script_langs(lesson)
    cells = selected_cells(lesson, wanted)
    voices: list[str] = []
    for voice, _cap, _slide in cells.values():
        if voice == "zh_cn" and "zh_cn" not in have and "zh" in have:
            voice = "zh"
        if voice in have and voice not in voices:
            voices.append(voice)
    return voices or have


def label_code(lang: str) -> str:
    """Which slide-field suffix to use for a narration track."""
    if lang in {"zh_hk", "zhhk"}:
        return "zh_hk"
    if lang in {"zh", "zh_cn", "zhcn"}:
        return "zh"
    return "en"


def field(obj: dict, stem: str, code: str) -> str:
    if code == "zh_hk":
        return (
            obj.get(f"{stem}_zh_hk") or obj.get(f"{stem}_zh") or obj.get(f"{stem}_en") or ""
        ).strip()
    if code == "zh":
        return (
            obj.get(f"{stem}_zh_cn") or obj.get(f"{stem}_zh") or obj.get(f"{stem}_en") or ""
        ).strip()
    return (obj.get(f"{stem}_en") or "").strip()


def field_native(obj: dict, stem: str, code: str) -> str:
    """Same as field() but do not fall back to English on a Chinese slide."""
    if code == "zh_hk":
        return (obj.get(f"{stem}_zh_hk") or obj.get(f"{stem}_zh") or "").strip()
    if code == "zh":
        return (obj.get(f"{stem}_zh_cn") or obj.get(f"{stem}_zh") or "").strip()
    return (obj.get(f"{stem}_en") or "").strip()

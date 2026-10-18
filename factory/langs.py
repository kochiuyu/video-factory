#!/usr/bin/env python3
"""Which narration tracks a lesson carries."""

from __future__ import annotations


def _lang_value(beat: dict, stem: str, lang: str) -> str:
    if lang in {"zh_cn", "zhcn"}:
        return (beat.get(f"{stem}_zh_cn") or beat.get(f"{stem}_zh") or "").strip()
    if lang == "zh_hk":
        return (beat.get(f"{stem}_zh_hk") or beat.get(f"{stem}_zh") or "").strip()
    if lang == "zh":
        return (beat.get(f"{stem}_zh") or beat.get(f"{stem}_zh_cn") or "").strip()
    if stem == "":
        return (beat.get(lang) or beat.get("en") or "").strip()
    return (beat.get(f"{stem}_en") or "").strip()


def stage_lines(beat: dict, lang: str, n: int = 8) -> list[str]:
    """Speech written on s1 / s2 / … for each visual stage."""
    lines: list[str] = []
    for i in range(1, max(1, int(n)) + 1):
        text = _lang_value(beat, f"s{i}", lang) or _lang_value(beat, f"stage{i}", lang)
        lines.append(text)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def beat_text(beat: dict, lang: str) -> str:
    staged = [p for p in stage_lines(beat, lang) if p]
    if staged:
        return " ".join(staged)
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
    """cell name -> (voice, caption, slide).

    Primary language sets voice, captions, and primary slide labels.
    A name with +second (en+zh) adds that language on the slides.
    """
    if is_tri(lesson):
        return {
            "en": ("en", "en", "en"),
            "zh": ("zh_cn", "zh_cn", "zh"),
            "hk": ("zh_hk", "zh_hk", "zh_hk"),
        }
    return {
        "en": ("en", "en", "en"),
        "zh": ("zh", "zh", "zh"),
    }


# Console checkbox ids and short names -> internal language.
TRACK_ALIASES = {
    "en": "en",
    "zh": "zh_cn",
    "zhcn": "zh_cn",
    "zh_cn": "zh_cn",
    "hk": "zh_hk",
    "zhhk": "zh_hk",
    "zh_hk": "zh_hk",
}

# Short token used in cell names: en, zh, hk, en+zh, zh+en, …
_PRIMARY = {
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
    "zhcn": "zh",
    "hk": "hk",
    "zh_hk": "hk",
    "zhhk": "hk",
}


def slide_folder(lang: str) -> str:
    return label_code(lang)


def bilingual_pair(voice: str, caption: str, slide: str) -> tuple[str, str | None]:
    """Primary slide language follows the voice. A different slide language is the second."""
    primary = slide_folder(voice)
    second = None
    for lang in (caption, slide):
        folder = slide_folder(lang)
        if folder != primary:
            second = folder
            break
    return primary, second


def cell_name(voice: str, second: str | None = None) -> str:
    """primary, or primary+second when slides are bilingual."""
    p = _SHORT.get(voice, voice)
    if not second:
        return p
    s = _SHORT.get(second, second)
    if s == p:
        return p
    return f"{p}+{s}"


def parse_cell(token: str) -> tuple[str, str, str] | None:
    """Parse primary or primary+second into (voice, caption, slide).

    Voice equals caption equals the primary slide language.
    The part after + is the second slide language.
    """
    raw = (token or "").strip().lower().replace("/", "+")
    if not raw:
        return None
    if "+" in raw:
        parts = [p for p in raw.split("+") if p]
        if len(parts) != 2:
            return None
        voice = _PRIMARY.get(parts[0])
        second = _PRIMARY.get(parts[1])
        if not voice or not second or voice == second:
            return None
        return voice, voice, label_code(second)
    voice = _PRIMARY.get(raw)
    if not voice:
        return None
    return voice, voice, label_code(voice)


def mix_name(voice: str, caption: str, slide: str) -> str:
    """Backward-compatible name from a triple. Caption is ignored; slide is the second if different."""
    primary = slide_folder(voice)
    second = slide_folder(slide)
    if second == primary:
        return cell_name(voice)
    return cell_name(voice, second)


def parse_mix(token: str) -> tuple[str, str, str] | None:
    """Accept primary+second. Old three-part voice-caption-slide is not used."""
    return parse_cell(token)


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
    for token in wanted:
        parsed = parse_cell(token)
        if parsed:
            voice, _cap, slide = parsed
            second = None if slide_folder(slide) == slide_folder(voice) else slide
            out[cell_name(voice, second)] = parsed
            continue
        key = TRACK_ALIASES.get(token, token)
        for name, triple in cells.items():
            if name == token or triple[0] == key:
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


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def field(obj: dict, stem: str, code: str) -> str:
    bare = _as_text(obj.get(stem))
    if code == "zh_hk":
        return _as_text(
            obj.get(f"{stem}_zh_hk") or obj.get(f"{stem}_zh") or obj.get(f"{stem}_en") or bare
        ).strip()
    if code == "zh":
        return _as_text(
            obj.get(f"{stem}_zh_cn") or obj.get(f"{stem}_zh") or obj.get(f"{stem}_en") or bare
        ).strip()
    return _as_text(obj.get(f"{stem}_en") or bare).strip()


def field_native(obj: dict, stem: str, code: str) -> str:
    """Same as field() but do not fall back to English on a Chinese slide."""
    bare = _as_text(obj.get(stem))
    if code == "zh_hk":
        return _as_text(obj.get(f"{stem}_zh_hk") or obj.get(f"{stem}_zh") or bare).strip()
    if code == "zh":
        return _as_text(obj.get(f"{stem}_zh_cn") or obj.get(f"{stem}_zh") or bare).strip()
    return _as_text(obj.get(f"{stem}_en") or bare).strip()

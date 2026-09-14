#!/usr/bin/env python3
"""Slide palettes. Layout stays in slides.py; colour lives here."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
THEMES = ROOT / "themes"

DEFAULTS = {
    "id": "cuhk-navy",
    "label": "CUHK navy / gold",
    "bg": "#F7F4EE",
    "ink": "#141C28",
    "muted": "#5A6473",
    "white": "#FFFFFF",
    "navy": "#0B1F3A",
    "gold": "#C4A35A",
    "emerald": "#1F6F5B",
    "wash": "#ECE4D2",
    "wash2": "#E8E0CE",
    "blobs": True,
    "corner": True,
}


def hex_rgb(value: str) -> tuple[int, int, int]:
    raw = str(value).strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        raise ValueError(f"Bad colour {value!r}")
    return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def resolve(raw: dict | None) -> dict:
    src = dict(DEFAULTS)
    if raw:
        src.update({k: v for k, v in raw.items() if v is not None})
    theme = {
        "id": str(src.get("id") or "custom"),
        "label": str(src.get("label") or src.get("id") or "custom"),
        "blobs": _as_bool(src.get("blobs"), True),
        "corner": _as_bool(src.get("corner"), True),
    }
    for key in ("bg", "ink", "muted", "white", "navy", "gold", "emerald", "wash", "wash2"):
        theme[key] = hex_rgb(src[key])
    return theme


def themes_dir() -> Path:
    return THEMES


def list_themes() -> list[dict]:
    rows = []
    if THEMES.is_dir():
        for path in sorted(THEMES.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
            theme = resolve(data)
            theme["file"] = path.name
            rows.append(theme)
    if not rows:
        rows.append(resolve(None))
    return rows


def load_theme(name: str | None) -> dict:
    wanted = (name or "").strip() or DEFAULTS["id"]
    if wanted in {"default", "cuhk", "navy"}:
        wanted = DEFAULTS["id"]
    path = THEMES / f"{wanted}.yaml"
    if not path.exists():
        # allow passing a stem that matches id: inside the file
        for candidate in THEMES.glob("*.yaml"):
            data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            if str(data.get("id") or candidate.stem) == wanted:
                path = candidate
                break
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        theme = resolve(data)
        print("theme:", theme["id"], path)
        return theme
    print(f"theme: {wanted!r} not found; using {DEFAULTS['id']}")
    return resolve(None)

#!/usr/bin/env python3
"""Tiny content stamps so a step can skip when its inputs did not change."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def digest_obj(obj) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def file_fingerprint(path: Path) -> dict:
    if not path.is_file():
        return {"path": path.name, "missing": True}
    st = path.stat()
    return {"path": path.name, "size": st.st_size, "mtime": int(st.st_mtime)}


def mark_path(target: Path) -> Path:
    return target.with_name(target.name + ".stamp")


def stamp_ok(target: Path, expected: str) -> bool:
    if not target.is_file() or not expected:
        return False
    mark = mark_path(target)
    return mark.is_file() and mark.read_text(encoding="utf-8").strip() == expected


def write_mark(target: Path, digest: str) -> None:
    mark_path(target).write_text(digest + "\n", encoding="utf-8")

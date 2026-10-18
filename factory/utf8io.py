#!/usr/bin/env python3
"""Force UTF-8 on Windows so Chinese YAML does not hit a charmap crash."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


def force_utf8() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is None:
            continue
        try:
            reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_yaml(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a YAML mapping.")
    return data


def write_yaml(path: str | Path, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")

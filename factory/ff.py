#!/usr/bin/env python3
"""Locate ffmpeg on Windows, macOS, or Linux and run it."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from paths import ffmpeg_candidates, replace_file

_FFMPEG: str | None = None


def _usable(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if p.is_file() and p.name not in {".", ".."}:
        return str(p)
    return None


def ffmpeg_exe() -> str:
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    env = (os.environ.get("FFMPEG") or os.environ.get("VF_FFMPEG") or "").strip()
    hit = _usable(env)
    if hit:
        _FFMPEG = hit
        return _FFMPEG
    hit = _usable(shutil.which("ffmpeg") or shutil.which("ffmpeg.exe"))
    if hit:
        _FFMPEG = hit
        return _FFMPEG
    for cand in ffmpeg_candidates():
        hit = _usable(cand)
        if hit:
            _FFMPEG = hit
            return _FFMPEG
    try:
        import imageio_ffmpeg

        hit = _usable(imageio_ffmpeg.get_ffmpeg_exe())
        if hit:
            _FFMPEG = hit
            return _FFMPEG
    except Exception:
        pass
    raise FileNotFoundError(
        "ffmpeg was not found. The factory cannot assemble video without it.\n\n"
        "Windows:\n"
        "  winget install Gyan.FFmpeg\n"
        "  pip install imageio-ffmpeg\n\n"
        "macOS:\n"
        "  brew install ffmpeg\n"
        "  pip install imageio-ffmpeg\n\n"
        "Linux:\n"
        "  sudo apt install ffmpeg\n"
        "  sudo dnf install ffmpeg\n"
        "  pip install imageio-ffmpeg\n\n"
        "Then open a new terminal. Or set FFMPEG to the full path of the binary."
    )


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_exe(), *args]
    if sys.platform.startswith("win"):
        kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.run(cmd, **kwargs)


def check_call(args: list[str]) -> None:
    proc = run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = ((proc.stderr or "") + (proc.stdout or ""))[-2000:]
        raise RuntimeError(
            f"ffmpeg failed with code {proc.returncode}\n{tail}"
        )


def audio_ok(path: Path) -> bool:
    """True if the file looks like playable audio, not an empty leftover."""
    try:
        if not path.is_file() or path.stat().st_size < 256:
            return False
        return probe_duration(path) > 0.05
    except Exception:
        return False


def probe_duration(path: Path) -> float:
    proc = run(
        ["-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
    )
    text = (proc.stderr or "") + (proc.stdout or "")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        raise RuntimeError(f"Could not read duration of {path}\n{text[-800:]}")
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def concat_escape(path: Path) -> str:
    return path.resolve().as_posix().replace("'", r"'\''")


def require() -> str:
    exe = ffmpeg_exe()
    print(f"ffmpeg: {exe}", file=sys.stderr)
    return exe


atomic_replace = replace_file

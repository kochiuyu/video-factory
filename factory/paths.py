#!/usr/bin/env python3
"""OS-specific font and tool locations (Windows, macOS, Linux)."""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def _file(path: Path | str) -> str | None:
    p = Path(path)
    return str(p) if p.is_file() else None


def _dir(path: Path | str) -> str | None:
    p = Path(path)
    return str(p) if p.is_dir() else None


def _home_fonts() -> list[Path]:
    home = Path.home()
    return [
        home / "Library" / "Fonts",
        home / ".fonts",
        home / ".local" / "share" / "fonts",
    ]


def font_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    extra = os.environ.get("VF_FONTSDIR")
    if extra:
        dirs.append(Path(extra))
    if IS_WIN:
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        dirs.append(windir / "Fonts")
    elif IS_MAC:
        dirs.extend(
            [
                Path("/System/Library/Fonts"),
                Path("/System/Library/Fonts/Supplemental"),
                Path("/Library/Fonts"),
                Path.home() / "Library" / "Fonts",
                Path("/opt/homebrew/share/fonts"),
                Path("/usr/local/share/fonts"),
            ]
        )
    else:
        dirs.extend(
            [
                Path("/usr/share/fonts"),
                Path("/usr/share/fonts/opentype/noto"),
                Path("/usr/share/fonts/truetype/noto"),
                Path("/usr/share/fonts/truetype/dejavu"),
                Path("/usr/local/share/fonts"),
                Path.home() / ".fonts",
                Path.home() / ".local" / "share" / "fonts",
            ]
        )
    return [d for d in dirs if d.is_dir()]


def _named(names: list[str]) -> str | None:
    for folder in font_search_dirs():
        for name in names:
            hit = _file(folder / name)
            if hit:
                return hit
    return None


def bundled_latin() -> str:
    p = Path(__file__).resolve().parents[1] / "fonts" / "LatinFallback.ttf"
    return str(p) if p.is_file() else ""


def bundled_latin_bold() -> str:
    p = Path(__file__).resolve().parents[1] / "fonts" / "LatinFallback-Bold.ttf"
    return str(p) if p.is_file() else ""


def _renders_latin(path: str) -> bool:
    if not path:
        return False
    try:
        from PIL import Image, ImageDraw, ImageFont

        font = ImageFont.truetype(path, 48)
        img = Image.new("RGB", (80, 80), "white")
        draw = ImageDraw.Draw(img)
        draw.text((4, 4), "Ag", font=font, fill="black")
        # Reject empty/tofu: at least some dark pixels must appear.
        return any(px[0] < 250 for px in img.getdata())
    except Exception:
        return False


def latin_regular() -> str:
    env = os.environ.get("VF_FONT_LATIN")
    if env and _renders_latin(env):
        return env
    bundled = bundled_latin()
    if bundled and _renders_latin(bundled):
        return bundled
    for name in (
        "segoeui.ttf",
        "arial.ttf",
        "Arial.ttf",
        "calibri.ttf",
        "DejaVuSans.ttf",
        "Helvetica.ttc",
        "NotoSans-Regular.ttf",
        "NotoSans-Regular.otf",
    ):
        hit = _named([name])
        if hit and _renders_latin(hit):
            return hit
    return bundled or ""


def latin_bold() -> str:
    env = os.environ.get("VF_FONT_LATIN_BOLD")
    if env and _renders_latin(env):
        return env
    bundled = bundled_latin_bold()
    if bundled and _renders_latin(bundled):
        return bundled
    for name in (
        "segoeuib.ttf",
        "arialbd.ttf",
        "Arial Bold.ttf",
        "calibrib.ttf",
        "DejaVuSans-Bold.ttf",
        "NotoSans-Bold.ttf",
    ):
        hit = _named([name])
        if hit and _renders_latin(hit):
            return hit
    return latin_regular()


def bundled_cjk() -> str:
    bundled = Path(__file__).resolve().parents[1] / "fonts" / "CJKFallback.ttf"
    return str(bundled) if bundled.is_file() else ""


def extra_cjk() -> str:
    """System CJK face used after the bundle for punctuation and rare marks."""
    env = os.environ.get("VF_FONT_CJK_EXTRA")
    if env and Path(env).is_file():
        return env
    return (
        _named(
            [
                "NotoSansCJK-Regular.ttc",
                "NotoSansCJK-Regular.otf",
                "NotoSansCJKsc-Regular.otf",
                "NotoSansSC-Regular.otf",
                "NotoSansSC-Regular.ttf",
                "NotoSansCJKtc-Regular.otf",
                "SourceHanSansSC-Regular.otf",
                "msyh.ttc",
                "msyh.ttf",
                "PingFang.ttc",
                "PingFang SC.ttc",
            ]
        )
        or ""
    )


def cjk_regular() -> str:
    env = os.environ.get("VF_FONT_CJK")
    if env and Path(env).is_file():
        return env
    bundled = bundled_cjk()
    if bundled:
        return bundled
    return (
        _named(
            [
                "NotoSansCJK-Regular.ttc",
                "NotoSansCJK-Regular.otf",
                "NotoSansCJKsc-Regular.otf",
                "NotoSansSC-Regular.otf",
                "NotoSansSC-Regular.ttf",
                "msyh.ttc",
                "msyh.ttf",
                "simhei.ttf",
                "Deng.ttf",
                "simsun.ttc",
                "mingliu.ttc",
                "PingFang.ttc",
                "PingFang SC.ttc",
                "STHeiti Light.ttc",
                "STHeiti Medium.ttc",
                "Hiragino Sans GB.ttc",
                "Songti.ttc",
                "Songti SC.ttc",
                "Arial Unicode.ttf",
            ]
        )
        or ""
    )


def cjk_bold() -> str:
    env = os.environ.get("VF_FONT_CJK_BOLD")
    if env and Path(env).is_file():
        return env
    return (
        _named(
            [
                "NotoSansCJK-Bold.ttc",
                "msyhbd.ttc",
                "msyhbd.ttf",
                "simhei.ttf",
                "STHeiti Medium.ttc",
                "PingFang.ttc",
            ]
        )
        or cjk_regular()
    )


def fonts_dir() -> str:
    env = os.environ.get("VF_FONTSDIR")
    if env and Path(env).is_dir():
        return env
    if IS_WIN:
        return str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")
    if IS_MAC:
        for candidate in (
            Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
        ):
            if candidate.is_dir():
                return str(candidate)
    for candidate in (
        Path("/usr/share/fonts/opentype/noto"),
        Path("/usr/share/fonts"),
    ):
        if candidate.is_dir():
            return str(candidate)
    dirs = font_search_dirs()
    return str(dirs[0]) if dirs else ""


def caption_font_name() -> str:
    env = os.environ.get("VF_CAPTION_FONT")
    if env:
        return env
    if IS_WIN:
        return "Microsoft YaHei"
    if IS_MAC:
        return "PingFang SC"
    return "Noto Sans CJK SC"


def ffmpeg_candidates() -> list[Path]:
    home = Path.home()
    raw = os.environ.get("FFMPEG") or os.environ.get("VF_FFMPEG") or ""
    items = [
        Path(raw) if raw.strip() else None,
        Path("/opt/homebrew/bin/ffmpeg"),
        Path("/usr/local/bin/ffmpeg"),
        Path("/usr/bin/ffmpeg"),
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
        home / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / "ffmpeg.exe",
        home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
    ]
    return [p for p in items if p is not None and p.is_file()]


def replace_file(src: Path, dest: Path, attempts: int = 8) -> Path:
    """Replace dest with src. Retries WinError 32 (Dropbox / Defender / preview lock)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    last: BaseException | None = None
    for i in range(attempts):
        try:
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass
            try:
                src.replace(dest)
                return dest
            except OSError:
                shutil.copy2(src, dest)
                try:
                    src.unlink()
                except OSError:
                    pass
                return dest
        except OSError as exc:
            last = exc
            time.sleep(0.2 * (i + 1))
    assert last is not None
    raise last

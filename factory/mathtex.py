#!/usr/bin/env python3
"""Render a LaTeX math fragment to a transparent PNG (matplotlib mathtext)."""

from __future__ import annotations

import hashlib
import io
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image

_LATEXISH = re.compile(r"[\\^_{}]|\\frac|\\sum|\\int|\\sqrt|\\cdot|\\times|\\leq|\\geq")


def cache_dir() -> Path:
    """Reserved math-PNG directory under the lesson output root."""
    from catalog import out_root

    return out_root() / "_mathtex"


def looks_like_tex(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if raw.startswith("$") or raw.startswith(r"\(") or raw.startswith(r"\["):
        return True
    return bool(_LATEXISH.search(raw))


def wrap_tex(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if raw.startswith("$$") and raw.endswith("$$"):
        return raw
    if raw.startswith("$") and raw.endswith("$") and len(raw) > 2:
        return raw
    if raw.startswith(r"\(") or raw.startswith(r"\["):
        return raw
    return f"${raw}$"


def tex_field(beat: dict, code: str) -> str:
    if not isinstance(beat, dict):
        return ""
    aliases = {
        "en": ("formula_tex_en", "formula_tex"),
        "zh": ("formula_tex_zh", "formula_tex_zh_cn", "formula_tex"),
        "zh_cn": ("formula_tex_zh", "formula_tex_zh_cn", "formula_tex"),
        "zh_hk": ("formula_tex_zh_hk", "formula_tex_zh", "formula_tex"),
    }
    for key in aliases.get(code, ("formula_tex",)):
        val = (beat.get(key) or "").strip()
        if val:
            return val
    return ""


def _hex(color) -> str:
    if isinstance(color, str) and color.startswith("#") and len(color) >= 7:
        return color[:7]
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return "#{:02x}{:02x}{:02x}".format(int(color[0]), int(color[1]), int(color[2]))
    return "#F7F1E3"


@lru_cache(maxsize=128)
def render_math(
    tex: str,
    color: str = "#F7F1E3",
    fontsize: int = 36,
    max_w: int = 1600,
    max_h: int = 280,
) -> Image.Image | None:
    """Return an RGBA image of the equation, or None if mathtext fails."""
    source = wrap_tex(tex)
    if not source:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
    except Exception:
        return None
    try:
        fig = Figure(figsize=(14, 3.2), dpi=160)
        fig.patch.set_alpha(0.0)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.text(
            0.5,
            0.5,
            source,
            ha="center",
            va="center",
            color=_hex(color),
            fontsize=fontsize,
            usetex=False,
        )
        canvas.draw()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=160, transparent=True, bbox_inches="tight", pad_inches=0.08)
        try:
            import matplotlib.pyplot as plt

            plt.close(fig)
        except Exception:
            pass
        buf.seek(0)
        img = Image.open(buf).convert("RGBA")
    except Exception:
        return None
    if img.width <= 2 or img.height <= 2:
        return None
    alpha = img.split()[-1]
    box = alpha.getbbox()
    if box:
        pad = 8
        box = (
            max(0, box[0] - pad),
            max(0, box[1] - pad),
            min(img.width, box[2] + pad),
            min(img.height, box[3] + pad),
        )
        img = img.crop(box)
    if img.width > max_w or img.height > max_h:
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return img


def paste_math(draw, box: tuple[int, int, int, int], tex: str, color, fontsize: int = 36) -> bool:
    canvas = getattr(draw, "_vf_img", None)
    if canvas is None or not tex:
        return False
    x0, y0, x1, y1 = (int(v) for v in box)
    piece = render_math(tex, color=_hex(color), fontsize=fontsize, max_w=max(80, x1 - x0), max_h=max(40, y1 - y0))
    if piece is None:
        return False
    x = x0 + max(0, (x1 - x0 - piece.width) // 2)
    y = y0 + max(0, (y1 - y0 - piece.height) // 2)
    if canvas.mode != "RGBA" and piece.mode == "RGBA":
        canvas.paste(piece, (x, y), piece)
    else:
        canvas.paste(piece, (x, y), piece if piece.mode == "RGBA" else None)
    return True

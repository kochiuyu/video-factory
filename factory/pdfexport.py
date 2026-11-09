#!/usr/bin/env python3
"""Write slide + caption preview PNGs to A4-ish landscape PDFs for RA review."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from PIL import Image, ImageDraw

from catalog import out_dir as lesson_out_dir
from modules import load_module
from slides import draw_mixed

LANG_ORDER = ("en", "zh", "zh_cn", "zh_hk", "zh+en", "en+zh", "zh_hk+en", "en+zh_hk")
LANG_LABEL = {
    "en": "EN",
    "zh": "简",
    "zh_cn": "简",
    "zh_hk": "繁",
    "zh+en": "简+EN",
    "en+zh": "EN+简",
    "zh_hk+en": "繁+EN",
    "en+zh_hk": "EN+繁",
}


def _drop_base_if_staged(names: list[str]) -> list[str]:
    staged = {
        re.sub(r"_s\d+$", "", Path(n).stem)
        for n in names
        if re.search(r"_s\d+$", Path(n).stem)
    }
    out = []
    for name in names:
        stem = Path(name).stem
        if re.search(r"_s\d+$", stem) or re.search(r"_c\d+$", stem):
            out.append(name)
            continue
        if stem in staged:
            continue
        out.append(name)
    return out


def _pngs(folder: Path) -> list[Path]:
    if not folder.is_file() and folder.is_dir():
        names = _drop_base_if_staged(sorted(p.name for p in folder.glob("*.png")))
        return [folder / n for n in names]
    return []


def _banner(title: str, subtitle: str) -> Image.Image:
    img = Image.new("RGB", (1920, 1080), "#F3EEE6")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 18, 1080], fill="#0B1F3A")
    draw.rectangle([1902, 0, 1920, 1080], fill="#0B1F3A")
    draw.rectangle([0, 1062, 1920, 1080], fill="#0B1F3A")
    draw.rectangle([0, 0, 1920, 160], fill="#0B1F3A")
    draw_mixed(draw, (64, 40), title[:80], 64, "#F7F1E3", bold=True)
    draw_mixed(draw, (64, 220), subtitle[:120], 36, "#0B1F3A", bold=False)
    draw_mixed(draw, (64, 980), "Video factory preview pack", 28, "#5A6473", bold=False)
    return img


def _to_rgb(path: Path) -> Image.Image:
    im = Image.open(path)
    if im.mode != "RGB":
        im = im.convert("RGB")
    return im


def _write_pdf(pages: list[Image.Image], dest: Path) -> Path | None:
    if not pages:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    first, rest = pages[0], pages[1:]
    first.save(
        dest,
        "PDF",
        save_all=bool(rest),
        append_images=rest,
        resolution=120,
    )
    for im in pages:
        im.close()
    return dest


def _member_ids(out_root: Path, lid: str) -> list[str]:
    root = Path(__file__).resolve().parents[1]
    path = root / "modules" / f"{lid}.yaml"
    if not path.is_file():
        return [lid]
    try:
        mod = load_module(path)
    except Exception:
        return [lid]
    ids = [str(x) for x in (mod.get("lessons") or []) if x]
    return ids or [lid]


def _folders_for(out_root: Path, lids: list[str], kind: str) -> list[str]:
    found: list[str] = []
    for lid in lids:
        root = lesson_out_dir(lid, root=out_root) / kind
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and child.name != "_bars" and child.name not in found:
                found.append(child.name)
    order = {name: i for i, name in enumerate(LANG_ORDER)}
    found.sort(key=lambda n: (order.get(n, 50), n))
    return found


def _pdf_key(out_root: Path, lids: list[str], folder: str, root_name: str) -> str:
    parts: list[str] = []
    for child in lids:
        for path in _pngs(lesson_out_dir(child, module=False, root=out_root) / root_name / folder):
            try:
                st = path.stat()
            except OSError:
                continue
            parts.append(f"{child}/{path.name}:{st.st_mtime_ns}:{st.st_size}")
    raw = "v2-cjk\n" + "\n".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def export_preview_pdfs(lid: str, out_root: Path, kinds: tuple[str, ...] = ("slides", "captions")) -> list[Path]:
    """Write slides PDFs, caption PDFs, or both."""
    lids = _member_ids(out_root, lid)
    langs = _folders_for(out_root, lids, "slides")
    for name in _folders_for(out_root, lids, "preview"):
        if name not in langs:
            langs.append(name)
    written: list[Path] = []
    dest_dir = lesson_out_dir(lid, root=out_root) / "pdf"
    dest_dir.mkdir(parents=True, exist_ok=True)

    def pack(folder: str, kind: str, title: str, root_name: str) -> None:
        label = LANG_LABEL.get(folder, folder)
        pages: list[Image.Image] = [_banner(f"{lid}  ·  {label}", title)]
        total = 0
        for child in lids:
            files = _pngs(lesson_out_dir(child, module=False, root=out_root) / root_name / folder)
            if not files:
                continue
            pages.append(_banner(child, f"{title} · {label} · {len(files)} cards"))
            pages.extend(_to_rgb(p) for p in files)
            total += len(files)
        if total == 0:
            for im in pages:
                im.close()
            return
        dest = dest_dir / f"{lid}_{folder.replace('+', '-')}_{kind}.pdf"
        key = _pdf_key(out_root, lids, folder, root_name)
        mark = dest.with_name(dest.name + ".stamp")
        if dest.is_file() and mark.is_file() and mark.read_text(encoding="utf-8").strip() == key:
            written.append(dest)
            print(f"pdf: reuse {dest.name}")
            for im in pages:
                im.close()
            return
        path = _write_pdf(pages, dest)
        if path:
            mark.write_text(key + "\n", encoding="utf-8")
            written.append(path)
            print(f"pdf: {path.name}")

    wanted = {k for k in kinds if k in {"slides", "captions"}}
    if not wanted:
        wanted = {"slides", "captions"}
    for folder in langs:
        if "slides" in wanted:
            pack(folder, "slides", "Slides", "slides")
        if "captions" in wanted:
            pack(folder, "captions", "Captions", "preview")
    return written

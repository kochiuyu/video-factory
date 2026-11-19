"""Experimental Mean focus preview.

Builds captioned phone-size contact sheets from the production Mean lesson.
It does not write lesson YAML, call a TTS service, or invent narration.
"""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from langs import bilingual_pair, selected_cells
from mux import _caption_card, caption_pages, caption_safe_top, stage_scripts
from paths import latin_regular
from slides import H, W, render_beat, stage_count
from theme import load_theme
from validate import load_lesson


ROOT = Path(__file__).resolve().parents[1]
MEAN_PATH = ROOT / "lessons" / "STAT" / "STAT-M01-T02-MEAN.yaml"
SHEET_DIR = ROOT / "factory" / "fixtures" / "experimental" / "mean-focus" / "sheets"
PHONE_W = 390
MIXES = ("zh", "hk+en", "zh+en", "en+zh")

# Exact slices of the production data-beat s1. Joining them restores that line.
# The opening stays with Shop A. The closing question stays with Shop D.
# This is not a replacement for s2 and s3.
SHOP_CUTS = {
    "en": ("Shop A sold 250. ", "Shop B sold 300. ", "Shop C sold 350. "),
    "zh": ("A店卖了250杯，", "B店卖了300杯，", "C店卖了350杯，"),
    "zh_hk": ("A店賣咗250杯，", "B店賣咗300杯，", "C店賣咗350杯，"),
}

COMPARE_ROWS = (
    ("Hook", "hook", None),
    ("Data, first shop", "data", 1),
    ("Data, equal share", "data", 6),
    ("Result, 350", "arithmetic", 3),
    ("Check, 1,400", "arithmetic", 4),
    ("Name", "name_mean", None),
    ("Formula steps", "formula", 4),
    ("Balance", "balance", 3),
    ("Limit", "limit", 3),
    ("Takeaway", "answer", 3),
)


def load_production_mean() -> dict:
    return load_lesson(MEAN_PATH)


def focus_preview_lesson(lesson: dict) -> dict:
    """Same beats, numbers, and speech. Opt in to focus spacing and the result row."""
    out = copy.deepcopy(lesson)
    out["id"] = "EXPERIMENTAL-MEAN-FOCUS-PREVIEW"
    out["slide_style"] = "focus"
    out["experimental"] = (
        "Renderer preview only. Original narration, numbers, and teaching order. "
        "Not a replacement for STAT-M01-T02-MEAN."
    )
    for beat in out["beats"]:
        if beat.get("id") == "arithmetic":
            beat["layout"] = "calculation"
    return out


def partition_shop_narration(text: str, lang: str) -> list[str]:
    """Split one spoken stage into four shop slices without adding or dropping characters."""
    rest = text
    parts: list[str] = []
    for cut in SHOP_CUTS[lang]:
        idx = rest.find(cut)
        if idx < 0:
            raise ValueError(f"{lang} narration has no exact slice {cut!r}")
        end = idx + len(cut)
        parts.append(rest[:end])
        rest = rest[end:]
    if not rest.strip():
        raise ValueError(f"{lang} shop partition dropped the closing")
    parts.append(rest)
    if "".join(parts) != text:
        raise ValueError(f"{lang} shop partition is not lossless")
    if len(parts) != 4:
        raise ValueError(f"{lang} shop partition produced {len(parts)} slices")
    return parts


def shop_reveal_prototype(data_beat: dict) -> dict:
    """One card that speaks only the original s1, one shop at a time.

    s2 and s3 of the data beat are not on this card. The sheet is a fixture
    for the reveal, not a production-aligned replacement of the three-stage beat.
    """
    beat = copy.deepcopy(data_beat)
    beat["id"] = "experimental-shop-reveal"
    beat["reveal"] = "row_cells"
    beat["rows"] = "1"
    beat["experimental_note"] = (
        "Lossless split of data s1 only. Original s2 and s3 are not on this card."
    )
    for key in list(beat):
        if key.startswith("footer") or key.startswith("row2") or key.startswith("c2"):
            beat.pop(key)
    for lang, suffix in (("en", "en"), ("zh", "zh"), ("zh_hk", "zh_hk")):
        parts = partition_shop_narration(str(data_beat[f"s1_{suffix}"]), lang)
        for i, part in enumerate(parts, start=1):
            beat[f"s{i}_{suffix}"] = part
    return beat


def tex_probe_lesson(style: str | None = None) -> dict:
    """In-memory copy of the accounting equation card. The source file is not written."""
    src = load_lesson(ROOT / "lessons" / "ACC" / "ACC-M01-EQ.yaml")
    beat = next(item for item in src["beats"] if item.get("formula_tex"))
    lesson = {
        "id": "EXPERIMENTAL-TEX-PROBE",
        "title_en": "TeX probe",
        "title_zh": "公式探针",
        "title_zh_hk": "公式探針",
        "beats": [copy.deepcopy(beat)],
    }
    if style:
        lesson["slide_style"] = style
    return lesson


def content_below(image: Image.Image, y: int) -> bool:
    """True when teaching pixels sit at or below y. Side rails are ignored."""
    rgb = image.convert("RGB")
    bg = rgb.getpixel((W // 2, 8))
    px = rgb.load()
    width, height = rgb.size
    for yy in range(max(0, y), height):
        for xx in range(28, width - 28):
            if px[xx, yy] != bg:
                return True
    return False


def _beat(lesson: dict, beat_id: str) -> tuple[int, dict]:
    for index, beat in enumerate(lesson["beats"], start=1):
        if beat.get("id") == beat_id:
            return index, beat
    raise KeyError(beat_id)


def _mix(lesson: dict, token: str) -> tuple[str, str, str | None]:
    cells = selected_cells(lesson, [token])
    _name, (voice, caption, slide) = next(iter(cells.items()))
    code, second = bilingual_pair(voice, caption, slide)
    return voice, code, second


def stage_caption(beat: dict, voice: str, stage: int | None) -> str:
    count = stage_count(beat)
    chunks = stage_scripts(beat, voice, count)
    if stage in (None, 0):
        text = chunks[0] if chunks else ""
    else:
        index = min(count, int(stage)) - 1
        text = chunks[index] if 0 <= index < len(chunks) else ""
    pages = caption_pages(text) if text.strip() else []
    return pages[0] if pages else ""


def paint(lesson: dict, beat: dict, index: int, code: str, second: str | None, stage: int | None) -> Image.Image:
    theme = load_theme(None)
    return render_beat(
        beat, lesson, index, len(lesson["beats"]),
        lang_labels=code, theme=theme, stage=stage, second_lang=second,
    )


def stamp_caption(image: Image.Image, text: str) -> Image.Image:
    if not text.strip():
        return image.convert("RGB")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        slide = root / "slide.png"
        bar = root / "bar.png"
        image.convert("RGB").save(slide)
        _caption_card(text, bar)
        base = Image.open(slide).convert("RGBA")
        overlay = Image.open(bar).convert("RGBA")
        base.paste(overlay, (0, 0), overlay)
        return base.convert("RGB")


def phone(image: Image.Image, width: int = PHONE_W) -> Image.Image:
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = latin_regular()
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _labeled_sheet(title: str, rows: list[tuple[str, Image.Image, Image.Image]]) -> Image.Image:
    label_w = 210
    gap = 10
    head = 52
    sample = rows[0][1]
    cell_w, cell_h = sample.size
    width = label_w + gap + cell_w + gap + cell_w + 16
    height = head + len(rows) * (cell_h + gap) + 16
    sheet = Image.new("RGB", (width, height), (247, 244, 238))
    draw = ImageDraw.Draw(sheet)
    font = _font(22)
    small = _font(16)
    draw.text((16, 14), title, font=font, fill=(11, 31, 58))
    y = head
    for label, left, right in rows:
        draw.text((12, y + 8), label, font=small, fill=(20, 28, 40))
        sheet.paste(left, (label_w, y))
        sheet.paste(right, (label_w + cell_w + gap, y))
        y += cell_h + gap
    return sheet


def _captioned(lesson: dict, beat: dict, index: int, voice: str, code: str, second: str | None, stage: int | None) -> Image.Image:
    frame = paint(lesson, beat, index, code, second, stage)
    return stamp_caption(frame, stage_caption(beat, voice, stage))


def comparison_rows(base: dict, focus: dict, token: str) -> list[tuple[str, Image.Image, Image.Image]]:
    voice, code, second = _mix(base, token)
    rows = []
    for label, beat_id, stage in COMPARE_ROWS:
        b_index, b_beat = _beat(base, beat_id)
        f_index, f_beat = _beat(focus, beat_id)
        left = phone(_captioned(base, b_beat, b_index, voice, code, second, stage))
        right = phone(_captioned(focus, f_beat, f_index, voice, code, second, stage))
        rows.append((label, left, right))
    return rows


def shop_rows(base: dict, token: str) -> list[tuple[str, Image.Image]]:
    voice, code, second = _mix(base, token)
    _index, data = _beat(base, "data")
    beat = shop_reveal_prototype(data)
    lesson = {
        "id": "EXPERIMENTAL-SHOP-REVEAL",
        "title_en": "Experimental shop reveal",
        "title_zh": "实验分店揭示",
        "title_zh_hk": "實驗分店揭示",
        "slide_style": "focus",
        "beats": [beat],
        "experimental": "Not production-aligned. s1 partition only.",
    }
    frames = []
    for stage, number in enumerate(("250", "300", "350", "500"), start=1):
        count = stage_count(beat)
        chunks = stage_scripts(beat, voice, count)
        pages = caption_pages(chunks[stage - 1]) if chunks[stage - 1].strip() else []
        named = [page for page in pages if number in page]
        text = named[0] if named else (pages[0] if pages else "")
        which = pages.index(text) + 1 if text in pages else 1
        frame = phone(stamp_caption(paint(lesson, beat, 1, code, second, stage), text))
        frames.append((f"{stage}. {number}  card {which}/{max(1, len(pages))}", frame))
    return frames


def _single_column(title: str, rows: list[tuple[str, Image.Image]]) -> Image.Image:
    blank = Image.new("RGB", rows[0][1].size, (247, 244, 238))
    paired = [(label, image, blank) for label, image in rows]
    return _labeled_sheet(title, paired)


def write_sheets(dest: Path | None = None) -> list[Path]:
    dest = Path(dest or SHEET_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    base = load_production_mean()
    focus = focus_preview_lesson(base)
    written: list[Path] = []
    manifest = {
        "source_lesson": "lessons/STAT/STAT-M01-T02-MEAN.yaml",
        "source_bytes_unchanged": True,
        "mixes": list(MIXES),
        "caption_safe_top": caption_safe_top(H),
        "phone_width": PHONE_W,
        "columns": ["baseline default layout", "focus layout"],
        "sheets": [],
        "limitations": [
            "Still caption previews only. No audio and no TTS.",
            "Focus preview keeps the original speech, numbers, quiz, and beat order.",
            "The arithmetic card opts into layout: calculation. The third row is the 350 result.",
            "Per-shop sheets partition data s1 only. They do not include s2 or s3.",
            "row_cells is not claimed to be production-aligned with the three-stage data beat.",
            "The busiest/quietest explanation stays on the original hook.",
            "No new stock-planning claim was added.",
        ],
    }
    for token in MIXES:
        compare = comparison_rows(base, focus, token)
        path = dest / f"compare-{token.replace('+', '-')}.png"
        _labeled_sheet(f"{token}  baseline | focus", compare).save(path, "PNG")
        written.append(path)
        manifest["sheets"].append({"file": path.name, "mix": token, "kind": "baseline-vs-focus"})
        shop = shop_rows(base, token)
        shop_path = dest / f"shop-partition-{token.replace('+', '-')}.png"
        _single_column(f"{token}  experimental s1 partition, not a lesson replacement", shop).save(shop_path, "PNG")
        written.append(shop_path)
        manifest["sheets"].append({"file": shop_path.name, "mix": token, "kind": "s1-partition-only"})
    tex_base = tex_probe_lesson()
    tex_focus = tex_probe_lesson("focus")
    beat = tex_base["beats"][0]
    left = phone(stamp_caption(paint(tex_base, beat, 1, "en", None, 2), stage_caption(beat, "en", 2)))
    right = phone(stamp_caption(paint(tex_focus, beat, 1, "en", None, 2), stage_caption(beat, "en", 2)))
    tex_path = dest / "tex-equation-en.png"
    _labeled_sheet("ACC equation TeX  baseline | focus", [("A = L + E", left, right)]).save(tex_path, "PNG")
    written.append(tex_path)
    manifest["sheets"].append({"file": tex_path.name, "mix": "en", "kind": "production-tex-card"})
    manifest_path = dest / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    written.append(manifest_path)
    return written


if __name__ == "__main__":
    for path in write_sheets():
        print(path)

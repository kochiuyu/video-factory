"""Opt-in 1080×1920 phone layout. Landscape 1920×1080 stays the default."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from mux import caption_pages, caption_safe_top, stamp_caption
from slides import (
    LAYOUT_VERSION,
    PHONE_CAPTION_LINES,
    PHONE_CAPTION_PAD,
    PHONE_CAPTION_SIZE,
    PHONE_CENTER_TOLERANCE,
    PHONE_ROLES,
    PhoneFitError,
    _phone_measure,
    new_canvas,
    PHONE_SAFE_L,
    PHONE_SAFE_R,
    PHONE_SAFE_TOP,
    canvas_scope,
    lesson_stamp,
    render_beat,
)
from theme import load_theme
from validate import load_lesson, validate


ROOT = Path(__file__).resolve().parents[1]
FACTORY = Path(__file__).resolve().parent
FIXTURE = FACTORY / "fixtures" / "vertical_smoke.yaml"
CARDS = FACTORY / "fixtures" / "vertical_cards.yaml"
IMAGE = FACTORY / "fixtures" / "still_image.png"
RED = (220, 30, 40)
BLUE = (30, 90, 200)


def _paint(lesson, index=0):
    theme = load_theme("cuhk-navy")
    beat = lesson["beats"][index]
    return render_beat(beat, lesson, index + 1, len(lesson["beats"]), "en", theme), theme


def _offenders(image, theme, y_limit):
    """Teaching pixels outside the phone safe rect. Side bars, washes, and the corner are chrome."""
    px = image.load()
    chrome = {theme["bg"], theme["wash"], theme["wash2"]}
    bad = []
    for y in range(image.height):
        for x in range(image.width):
            color = px[x, y]
            if x < 28 or x >= image.width - 28:
                continue
            if color in chrome:
                continue
            if y < PHONE_SAFE_TOP and color == theme["gold"]:
                continue
            if x < PHONE_SAFE_L or x > PHONE_SAFE_R or y < PHONE_SAFE_TOP or y >= y_limit:
                bad.append((x, y, color))
                if len(bad) >= 8:
                    return bad
    return bad


def _dense_runs(image, color, need=400):
    """Vertical runs where a card fill, not a glyph, covers the safe width."""
    px = image.load()
    rows = []
    for y in range(PHONE_SAFE_TOP, image.height - 40):
        hits = sum(1 for x in range(PHONE_SAFE_L, PHONE_SAFE_R) if px[x, y] == color)
        if hits > need:
            rows.append(y)
    if not rows:
        return []
    runs = []
    start = prev = rows[0]
    for y in rows[1:]:
        if y == prev + 1:
            prev = y
        else:
            runs.append((start, prev))
            start = prev = y
    runs.append((start, prev))
    return runs


def _rows_with(image, color, y0, y1):
    px = image.load()
    rows = []
    for y in range(y0, y1):
        if any(px[x, y] == color for x in range(PHONE_SAFE_L, PHONE_SAFE_R)):
            rows.append(y)
    return rows


class VerticalLayout(unittest.TestCase):
    def test_layout_version_and_landscape_stamp_stay_put(self):
        self.assertEqual(LAYOUT_VERSION, "2026-11-04-reveal-steps-type-v1")
        lesson = load_lesson(FIXTURE)
        self.assertEqual(validate(lesson, glyphs=False, source=FIXTURE), [])
        theme = load_theme("cuhk-navy")
        plain = copy.deepcopy(lesson)
        plain.pop("format", None)
        forced = copy.deepcopy(plain)
        forced["format"] = "16:9"
        phone = copy.deepcopy(plain)
        phone["format"] = "9:16"
        landscape = lesson_stamp(plain, theme, "en", None, True)
        self.assertEqual(landscape, lesson_stamp(forced, theme, "en", None, True))
        self.assertNotEqual(landscape, lesson_stamp(phone, theme, "en", None, True))

        bad = copy.deepcopy(plain)
        bad["format"] = "4:3"
        errors = validate(bad, glyphs=False, source=FIXTURE)
        self.assertTrue(any("format must be 16:9 or 9:16" in err for err in errors), errors)

    def test_default_render_is_landscape_and_phone_is_a_redesign(self):
        lesson = load_lesson(FIXTURE)
        lesson["_yaml"] = str(FIXTURE)
        plain = copy.deepcopy(lesson)
        plain.pop("format", None)
        landscape, _theme = _paint(plain, 0)
        self.assertEqual(landscape.size, (1920, 1080))

        phone_lesson = copy.deepcopy(lesson)
        phone_lesson["format"] = "9:16"
        title, theme = _paint(phone_lesson, 0)
        table, _theme = _paint(phone_lesson, 1)
        still, _theme = _paint(phone_lesson, 2)
        self.assertEqual(title.size, (1080, 1920))
        self.assertEqual(table.size, (1080, 1920))
        self.assertEqual(still.size, (1080, 1920))
        # The phone caption strip. Teaching content, including the footer, stops above it.
        limit = caption_safe_top(
            1920,
            size=PHONE_CAPTION_SIZE,
            lines=PHONE_CAPTION_LINES,
            bottom_pad=PHONE_CAPTION_PAD,
        )
        self.assertLess(PHONE_CAPTION_PAD, 100)
        self.assertGreater(limit, 1600)
        self.assertLess(limit, 1760)
        for name, image in (("title", title), ("table", table), ("still", still)):
            bad = _offenders(image, theme, limit)
            self.assertEqual(bad, [], name)

        # The eyebrow and title are one group, centered in the teaching area.
        navy_rows = _rows_with(title, theme["navy"], PHONE_SAFE_TOP, limit)
        self.assertTrue(navy_rows, "title should paint navy type")
        self.assertGreater(len(navy_rows), 40)
        teach_top, teach_bot = PHONE_SAFE_TOP, limit - 56
        center = (min(navy_rows) + max(navy_rows)) / 2
        self.assertLess(abs(center - (teach_top + teach_bot) / 2), 0.06 * (teach_bot - teach_top))

        white = theme.get("white") or (255, 255, 255)
        cell_rows = _rows_with(table, white, PHONE_SAFE_TOP, limit)
        self.assertGreater(max(cell_rows) - min(cell_rows), 80)
        self.assertLess(max(cell_rows), limit)

        art = _bbox(still, lambda pixel: pixel in {RED, BLUE})
        self.assertIsNotNone(art)
        left, top, right, bottom = art
        self.assertGreaterEqual(left, PHONE_SAFE_L)
        self.assertLess(right, PHONE_SAFE_R)
        self.assertGreaterEqual(top, PHONE_SAFE_TOP)
        self.assertLess(bottom, limit)
        self.assertAlmostEqual((right - left) / (bottom - top), 0.5, delta=0.08)
        self.assertLess(right - left, PHONE_SAFE_R - PHONE_SAFE_L - 80)
        self.assertGreater(bottom - top, right - left)
        red = _bbox(still, lambda pixel: pixel == RED)
        blue = _bbox(still, lambda pixel: pixel == BLUE)
        self.assertIsNotNone(red)
        self.assertIsNotNone(blue)
        self.assertLess(red[3], blue[1])
        px = still.load()
        self.assertNotIn(px[left - 12, (top + bottom) // 2], {RED, BLUE})

    def _phone_limit(self):
        return caption_safe_top(
            1920,
            size=PHONE_CAPTION_SIZE,
            lines=PHONE_CAPTION_LINES,
            bottom_pad=PHONE_CAPTION_PAD,
        )

    def _phone(self, beat):
        lesson = {
            "id": "PHONE-COLUMN",
            "format": "9:16",
            "title_en": "Column",
            "title_zh": "栏",
            "beats": [beat],
        }
        image, theme = _paint(lesson, 0)
        self.assertEqual(image.size, (1080, 1920))
        self.assertEqual(_offenders(image, theme, self._phone_limit()), [])
        return image, theme

    def test_long_row_labels_stack_and_short_definitions_fit(self):
        table, theme = self._phone({
            "id": "stack",
            "visual": "table_grid",
            "title_en": "Keep versus close",
            "rows": 2,
            "cols": 2,
            "row1_en": "Avoidable branch costs",
            "row2_en": "Head-office expenditure",
            "col1_en": "Keep",
            "col2_en": "Close",
            "c11_en": "550,000",
            "c12_en": "0",
            "c21_en": "200,000",
            "c22_en": "200,000",
        })
        white = theme.get("white") or (255, 255, 255)
        px = table.load()
        cell_left = min(
            x for y in range(PHONE_SAFE_TOP, self._phone_limit())
            for x in range(PHONE_SAFE_L, PHONE_SAFE_R)
            if px[x, y] == white
        )
        self.assertLess(cell_left, 140)
        cell_rows = _rows_with(table, white, PHONE_SAFE_TOP, self._phone_limit())
        # Cells hug the numerals. They are readable and not stretched down the column.
        self.assertGreater(max(cell_rows) - min(cell_rows), 80)
        self.assertLess(max(cell_rows) - min(cell_rows), 420)

        panel, theme = self._phone({
            "id": "define",
            "visual": "definition_card",
            "title_en": "How to read",
            "formula_en": "A is the row.",
        })
        dense = _dense_runs(panel, theme["navy"])
        self.assertGreaterEqual(len(dense), 2)
        body = dense[-1]
        self.assertLess(body[1] - body[0], 420)
        self.assertLess(body[1], self._phone_limit() - 80)

    def test_takeaways_and_contrast_hug_text_and_stay_centered(self):
        cards, theme = self._phone({
            "id": "points",
            "visual": "takeaway",
            "title_en": "Tonight's choice",
            "q1_en": "The difference in cash from here",
            "q2_en": "Sunk cost; compare the next-best use",
        })
        emerald = _rows_with(cards, theme["emerald"], PHONE_SAFE_TOP, self._phone_limit())
        self.assertTrue(emerald)
        self.assertLess(max(emerald) - min(emerald), 420)
        self.assertGreater(max(emerald) - min(emerald), 70)

        contrast, theme = self._phone({
            "id": "sides",
            "visual": "whatis_contrast",
            "what_en": "An everyday name.",
            "not_en": "The legal name for SUA.",
        })
        px = contrast.load()
        for y in range(PHONE_SAFE_TOP):
            for x in range(PHONE_SAFE_L, 900):
                self.assertNotEqual(px[x, y], theme["gold"], (x, y))
        navy = _rows_with(contrast, theme["navy"], PHONE_SAFE_TOP, self._phone_limit())
        self.assertGreaterEqual(min(navy), PHONE_SAFE_TOP - 2)
        runs = _dense_runs(contrast, theme["navy"])
        self.assertGreaterEqual(len(runs), 2)
        for run in runs:
            self.assertLess(run[1] - run[0], 520)
        teach_top, teach_bot = PHONE_SAFE_TOP, self._phone_limit() - 56
        center = (min(navy) + max(navy)) / 2
        self.assertLess(abs(center - (teach_top + teach_bot) / 2), 0.06 * (teach_bot - teach_top))

    def test_phone_fit_names_the_beat_and_does_not_clip(self):
        long = "word " * 80
        with self.assertRaises(PhoneFitError) as caught:
            self._phone({
                "id": "too-long",
                "visual": "title_card",
                "title_en": long,
            })
        message = str(caught.exception)
        self.assertIn("beat=too-long", message)
        self.assertIn("lang=en", message)
        self.assertIn("role=title", message)
        self.assertIn("size=64", message)
        self.assertNotIn("…", message)

        with self.assertRaises(PhoneFitError) as missing:
            render_beat(
                {"id": "gap", "visual": "title_card"},
                {"id": "GAP", "format": "9:16", "beats": [{}]},
                1, 1, "zh", load_theme("cuhk-navy"),
            )
        self.assertIn("lang=zh", str(missing.exception))
        self.assertIn("missing locale text", str(missing.exception))

    def test_landscape_pixels_and_stamp_stay_on_the_baseline(self):
        lesson = load_lesson(FIXTURE)
        lesson.pop("format", None)
        image, theme = _paint(lesson, 0)
        self.assertEqual(image.size, (1920, 1080))
        self.assertEqual(LAYOUT_VERSION, "2026-11-04-reveal-steps-type-v1")
        px = image.load()
        self.assertEqual(px[10, 100], theme["navy"])
        self.assertEqual(px[960, 806], theme["gold"])
        title_ink = [y for y in range(280, 820) if px[960, y] == theme["navy"]]
        self.assertGreater(len(title_ink), 40)
        self.assertGreater(min(title_ink), 300)
        self.assertLess(max(title_ink), 800)
        forced = copy.deepcopy(lesson)
        forced["format"] = "16:9"
        self.assertEqual(
            lesson_stamp(lesson, theme, "en", None, True),
            lesson_stamp(forced, theme, "en", None, True),
        )
        self.assertLessEqual(PHONE_CENTER_TOLERANCE, 0.06)

    def test_card_fixture_measures_every_language_and_clears_the_caption(self):
        lesson = load_lesson(CARDS)
        lesson["_yaml"] = str(CARDS)
        self.assertEqual(validate(lesson, glyphs=False, source=CARDS), [])
        self.assertEqual(lesson["id"], "VERTICAL-CARDS")
        theme = load_theme("cuhk-navy")
        with canvas_scope("9:16"):
            _img, draw = new_canvas(theme)
            title = _phone_measure(draw, "Which row is first?", 920, "title", beat="ask", lang="en")
            self.assertGreaterEqual(title["size"], 88)
            self.assertGreaterEqual(title["size"], PHONE_ROLES["title"][1])
            zh = _phone_measure(draw, "哪一行是第一行", 920, "title", beat="ask", lang="zh")
            self.assertGreaterEqual(zh["size"], PHONE_ROLES["title"][1])
            self.assertGreaterEqual(zh["lh"], int(zh["size"] * 1.35))
            number = _phone_measure(draw, "550,000", 400, "numeral", beat="ledger", lang="en")
            self.assertGreaterEqual(number["size"], PHONE_ROLES["numeral"][1])
            label = _phone_measure(draw, "Avoidable sample cost", 860, "row_label", beat="ledger", lang="en")
            self.assertGreaterEqual(label["size"], PHONE_ROLES["row_label"][1])
            self.assertLessEqual(len(label["lines"]), 2)
        for code in ("en", "zh", "zh_hk"):
            for index, beat in enumerate(lesson["beats"]):
                image = render_beat(beat, lesson, index + 1, len(lesson["beats"]), code, theme)
                self.assertEqual(image.size, (1080, 1920), beat["id"])
                self.assertEqual(_offenders(image, theme, self._phone_limit()), [], (code, beat["id"]))
        still = render_beat(lesson["beats"][-1], lesson, 11, 11, "en", theme)
        blue = _bbox(still, lambda pixel: pixel == (40, 90, 160))
        gold = _bbox(still, lambda pixel: pixel == (196, 150, 60))
        self.assertIsNotNone(blue)
        self.assertIsNotNone(gold)
        self.assertLess(blue[3], gold[1])
        width = blue[2] - blue[0] + 1
        height = gold[3] - blue[1] + 1
        self.assertGreater(height, width)
        self.assertAlmostEqual(width / height, 400 / 700, delta=0.08)

        bare = render_beat(lesson["beats"][0], lesson, 1, 11, "en", theme)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "ask.png"
            dest = Path(tmp) / "ask-cap.png"
            bare.save(src)
            # The phone reserve allows three caption lines. Stamp that card, not a shrunk one-liner.
            old_lines = os.environ.get("VF_CAPTION_LINES")
            os.environ["VF_CAPTION_LINES"] = "3"
            try:
                with canvas_scope("9:16"):
                    page = caption_pages(lesson["beats"][0]["en"])[0]
            finally:
                if old_lines is None:
                    os.environ.pop("VF_CAPTION_LINES", None)
                else:
                    os.environ["VF_CAPTION_LINES"] = old_lines
            self.assertEqual(page.count("\n"), 2)
            stamp_caption(src, page, dest)
            with Image.open(dest) as stamped:
                stamped = stamped.convert("RGB")
                self.assertEqual(stamped.size, (1080, 1920))
                base_px = bare.load()
                px = stamped.load()
                top = stamped.height
                bottom = -1
                for y in range(stamped.height):
                    if any(px[x, y] != base_px[x, y] for x in range(stamped.width)):
                        top = min(top, y)
                        bottom = max(bottom, y)
        self.assertGreater(bottom, 0)
        self.assertAlmostEqual(bottom, 1920 - PHONE_CAPTION_PAD, delta=8)
        self.assertGreater(top, self._phone_limit() - 8)

    def test_pair_stacks_and_series_columns_fit(self):
        theme = load_theme("cuhk-navy")
        pair = {
            "id": "PAIR-PHONE",
            "format": "9:16",
            "title_en": "Pair",
            "title_zh": "对照",
            "beats": [{
                "id": "shops",
                "visual": "pair",
                "title_en": "Two tables, stacked",
                "left_en": "Left",
                "right_en": "Right",
                "lrow1_en": "A",
                "rrow1_en": "B",
                "lcol1_en": "1",
                "rcol1_en": "1",
                "lc11_en": "3",
                "rc11_en": "4",
                "s1_en": "Left.",
                "s2_en": "Right.",
                "s3_en": "Both.",
            }],
        }
        image = render_beat(pair["beats"][0], pair, 1, 1, "en", theme)
        self.assertEqual(image.size, (1080, 1920))
        white = theme.get("white") or (255, 255, 255)
        rows = _rows_with(image, white, 200, 1700)
        gaps = [b - a for a, b in zip(rows, rows[1:]) if b - a > 12]
        self.assertTrue(gaps, "a stacked pair should leave a gap between the two tables")
        self.assertLess(
            max(rows),
            caption_safe_top(
                1920,
                size=PHONE_CAPTION_SIZE,
                lines=PHONE_CAPTION_LINES,
                bottom_pad=PHONE_CAPTION_PAD,
            ),
        )

        shops = {
            "id": "BOX-PHONE",
            "format": "9:16",
            "title_en": "Boxes",
            "title_zh": "箱",
            "beats": [{
                "id": "boxes",
                "visual": "pair_box",
                "title_en": "Same scale",
                "left_en": "West",
                "right_en": "East",
                "s1_en": "West.",
                "s2_en": "East.",
                "s3_en": "Far.",
            }],
        }
        boxes = render_beat(shops["beats"][0], shops, 1, 1, "en", theme)
        px = boxes.load()
        gold_x = [
            x for y in range(200, 1600) for x in range(40, 1040)
            if px[x, y] == theme["gold"]
        ]
        self.assertTrue(gold_x)
        self.assertGreater(max(gold_x), 600)
        self.assertLess(max(gold_x), PHONE_SAFE_R)

        series = {
            "id": "SERIES-PHONE",
            "format": "9:16",
            "title_en": "Days",
            "title_zh": "天",
            "beats": [{
                "id": "days",
                "visual": "series",
                "cols": 6,
                "title_en": "Six days",
                "row1_en": "Cups",
                **{f"col{i}_en": f"D{i}" for i in range(1, 7)},
                **{f"c1{i}_en": str(i) for i in range(1, 7)},
                "s1_en": "Days.",
                "s2_en": "Counts.",
                "s3_en": "Done.",
            }],
        }
        grid = render_beat(series["beats"][0], series, 1, 1, "en", theme)
        cell_rows = _rows_with(grid, white, 200, 1600)
        self.assertTrue(cell_rows)
        y = cell_rows[len(cell_rows) // 2]
        xs = [x for x in range(40, 1060) if grid.getpixel((x, y)) == white]
        self.assertGreater(max(xs), 700)
        self.assertLess(max(xs), 1040)

    def test_caption_pill_is_narrow_and_sits_on_the_phone_pad(self):
        lesson = load_lesson(FIXTURE)
        lesson["format"] = "9:16"
        lesson["_yaml"] = str(FIXTURE)
        still, _theme = _paint(lesson, 2)
        line = lesson["beats"][2]["en"]
        with canvas_scope("9:16"):
            pages = caption_pages(line)
        with canvas_scope(None):
            wide = caption_pages(line)
        self.assertTrue(pages)
        self.assertGreaterEqual(len(pages[0]), 8)
        # The phone wrap is the narrower measure, so the first card is not the landscape card.
        self.assertNotEqual(pages[0], wide[0])
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            slide = folder / "still.png"
            dest = folder / "capped.png"
            still.save(slide)
            stamp_caption(slide, pages[0], dest)
            stamped = Image.open(dest).convert("RGB")
        self.assertEqual(stamped.size, (1080, 1920))
        base_px = still.load()
        # The chip is the only difference from the bare slide. Compare in place.
        px = stamped.load()
        left, top, right, bottom = stamped.width, stamped.height, -1, -1
        for y in range(stamped.height):
            for x in range(stamped.width):
                if px[x, y] != base_px[x, y]:
                    left = min(left, x)
                    right = max(right, x)
                    top = min(top, y)
                    bottom = max(bottom, y)
        pill = None if right < 0 else (left, top, right, bottom)
        self.assertIsNotNone(pill)
        left, top, right, bottom = pill
        self.assertLessEqual(right - left, 920)
        self.assertGreater(right - left, 400)
        self.assertGreaterEqual(left, PHONE_SAFE_L - 2)
        self.assertLessEqual(right, PHONE_SAFE_R + 2)
        self.assertAlmostEqual(bottom, 1920 - PHONE_CAPTION_PAD, delta=4)
        self.assertGreater(top, 1920 - PHONE_CAPTION_PAD - 220)

    def test_build_writes_phone_files_only_under_9x16(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            cmd = [
                sys.executable, str(FACTORY / "build.py"), str(FIXTURE),
                "--slides-only", "--no-tts", "--cells", "en",
                "--format", "9:16", "--out", str(out),
            ]
            done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + "\n" + done.stderr)
            lesson_dir = out / "lessons" / "VERTICAL-SMOKE"
            phone = lesson_dir / "9x16"
            slides = list((phone / "slides").rglob("*.png"))
            self.assertTrue(slides)
            self.assertFalse((lesson_dir / "slides").exists())
            for path in slides:
                with Image.open(path) as im:
                    self.assertEqual(im.size, (1080, 1920), path)
            covers = list((phone / "covers").glob("*.png"))
            self.assertTrue(covers)
            for path in covers:
                with Image.open(path) as im:
                    self.assertEqual(im.size, (1080, 1920), path)
            jobs = json.loads((lesson_dir / "narration_jobs.json").read_text(encoding="utf-8"))
            self.assertTrue(jobs)
            for job in jobs:
                dest = job["dest_path"].replace("\\", "/")
                self.assertIn("/audio/", dest)
                self.assertNotIn("9x16/audio", dest)

            land_out = out / "land"
            forced = subprocess.run(
                [
                    sys.executable, str(FACTORY / "build.py"), str(FIXTURE),
                    "--slides-only", "--no-tts", "--cells", "en",
                    "--format", "16:9", "--out", str(land_out),
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(forced.returncode, 0, forced.stdout + "\n" + forced.stderr)
            land = land_out / "lessons" / "VERTICAL-SMOKE"
            land_slides = list((land / "slides").rglob("*.png"))
            self.assertTrue(land_slides)
            self.assertFalse((land / "9x16").exists())
            for path in land_slides:
                with Image.open(path) as im:
                    self.assertEqual(im.size, (1920, 1080), path)

            bare = out / "bare.yaml"
            text = FIXTURE.read_text(encoding="utf-8")
            bare.write_text("\n".join(
                line for line in text.splitlines() if not line.startswith("format:")
            ) + "\n", encoding="utf-8")
            bare_out = out / "bare"
            default = subprocess.run(
                [
                    sys.executable, str(FACTORY / "build.py"), str(bare),
                    "--slides-only", "--no-tts", "--cells", "en",
                    "--out", str(bare_out),
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(default.returncode, 0, default.stdout + "\n" + default.stderr)
            bare_dir = bare_out / "lessons" / "VERTICAL-SMOKE"
            bare_slides = list((bare_dir / "slides").rglob("*.png"))
            self.assertTrue(bare_slides)
            self.assertFalse((bare_dir / "9x16").exists())
            with Image.open(bare_slides[0]) as im:
                self.assertEqual(im.size, (1920, 1080))


def _bbox(image, predicate):
    px = image.load()
    left, top, right, bottom = image.width, image.height, -1, -1
    for y in range(image.height):
        for x in range(image.width):
            if predicate(px[x, y]):
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < 0:
        return None
    return left, top, right, bottom


if __name__ == "__main__":
    unittest.main()

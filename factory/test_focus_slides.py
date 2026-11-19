"""Opt-in focus layout. Production lessons stay on the default renderer."""

from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image

import focus_preview
from mux import _caption_card, caption_safe_top
from slides import H, W, render_beat, stage_count
from theme import load_theme
from validate import load_lesson


ROOT = Path(__file__).resolve().parents[1]
MEAN = ROOT / "lessons" / "STAT" / "STAT-M01-T02-MEAN.yaml"
# Byte identity of the production Mean lesson on main 55af61b. CI checks out
# only the pull-request merge commit, so this does not ask git for origin/main.
MEAN_SHA256 = "55e7d014230d1687de559f34b60707f1aee16a44757758ec103b32b45abad121"


def _beat(lesson, beat_id):
    for index, beat in enumerate(lesson["beats"], start=1):
        if beat.get("id") == beat_id:
            return index, beat
    raise AssertionError(beat_id)


class ProductionLessonsStayPut(unittest.TestCase):
    def test_mean_yaml_matches_main(self):
        self.assertEqual(sha256(MEAN.read_bytes()).hexdigest(), MEAN_SHA256)

    def test_no_production_lesson_opts_into_focus(self):
        opted = []
        for path in (ROOT / "lessons").rglob("*.yaml"):
            text = path.read_text(encoding="utf-8")
            if "slide_style:" in text:
                opted.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(opted, [])

    def test_focus_copy_keeps_speech_numbers_and_order(self):
        original = load_lesson(MEAN)
        preview = focus_preview.focus_preview_lesson(original)
        self.assertEqual(original["id"], "STAT-M01-T02-MEAN")
        self.assertNotIn("slide_style", original)
        self.assertEqual(preview["slide_style"], "focus")
        self.assertEqual([beat["id"] for beat in preview["beats"]], [beat["id"] for beat in original["beats"]])
        for before, after in zip(original["beats"], preview["beats"]):
            if before["id"] == "arithmetic":
                self.assertEqual(after["layout"], "calculation")
                self.assertNotIn("layout", before)
                after = {key: value for key, value in after.items() if key != "layout"}
            self.assertEqual(before, after)
        hook = preview["beats"][0]
        self.assertEqual(hook["visual"], "title_card")
        self.assertIn("busiest", hook["en"])
        self.assertIn("quietest", hook["en"])
        self.assertIn("最忙", hook["zh"])
        self.assertIn("最清闲", hook["zh"])
        self.assertNotIn("按各店自己的销量备货", hook["zh"])
        self.assertNotIn("plan its stock", preview["beats"][-1]["s1_en"])


class ShopPartition(unittest.TestCase):
    def test_s1_partition_is_lossless_and_stops_there(self):
        lesson = load_lesson(MEAN)
        _index, data = _beat(lesson, "data")
        original_s2 = {suffix: data[f"s2_{suffix}"] for suffix in ("en", "zh", "zh_hk")}
        for lang, suffix, number in (
            ("en", "en", "250"),
            ("zh", "zh", "250"),
            ("zh_hk", "zh_hk", "250"),
        ):
            parts = focus_preview.partition_shop_narration(data[f"s1_{suffix}"], lang)
            self.assertEqual("".join(parts), data[f"s1_{suffix}"])
            self.assertIn(number, parts[0])
            self.assertIn("300", parts[1])
            self.assertIn("350", parts[2])
            self.assertIn("500", parts[3])
        prototype = focus_preview.shop_reveal_prototype(data)
        self.assertEqual(prototype["reveal"], "row_cells")
        self.assertEqual(stage_count(prototype), 4)
        self.assertEqual("".join(prototype[f"s{i}_en"] for i in range(1, 5)), data["s1_en"])
        self.assertNotEqual(prototype["s2_en"], original_s2["en"])
        self.assertNotIn(original_s2["en"], "".join(prototype[f"s{i}_en"] for i in range(1, 5)))
        self.assertNotIn("row2_en", prototype)
        self.assertNotIn("footer_en", prototype)


class DefaultRenderRegression(unittest.TestCase):
    def test_default_data_slide_still_uses_the_lower_band(self):
        lesson = load_lesson(MEAN)
        index, beat = _beat(lesson, "data")
        theme = load_theme(None)
        image = render_beat(beat, lesson, index, len(lesson["beats"]), "en", theme, stage=1)
        self.assertTrue(focus_preview.content_below(image, caption_safe_top(H)))
        self.assertEqual(stage_count(beat), 6)

    def test_default_slide_is_stable_and_ignores_a_focus_render(self):
        lesson = load_lesson(MEAN)
        index, beat = _beat(lesson, "hook")
        theme = load_theme(None)
        first = render_beat(beat, lesson, index, len(lesson["beats"]), "zh", theme)
        second = render_beat(beat, lesson, index, len(lesson["beats"]), "zh", theme)
        self.assertEqual(list(first.getdata()), list(second.getdata()))
        focus = focus_preview.focus_preview_lesson(lesson)
        other = render_beat(focus["beats"][0], focus, 1, len(focus["beats"]), "zh", theme)
        self.assertNotEqual(list(first.getdata()), list(other.getdata()))


class FocusOptIn(unittest.TestCase):
    def test_caption_reservation_matches_three_large_lines(self):
        with tempfile_dir() as temp, patch.dict(
            "os.environ", {"VF_CAPTION_SIZE": "56", "VF_CAPTION_LINES": "3"}
        ):
            dest = Path(temp) / "caption.png"
            _caption_card("First line\nSecond line\nThird line", dest)
            with Image.open(dest) as image:
                self.assertEqual(image.getchannel("A").getbbox()[1], caption_safe_top(H))

    def test_focus_frames_stay_above_the_caption(self):
        lesson = focus_preview.focus_preview_lesson(load_lesson(MEAN))
        theme = load_theme(None)
        safe = caption_safe_top(H)
        for beat_id, stage in (
            ("hook", None),
            ("data", 1),
            ("data", 6),
            ("arithmetic", 3),
            ("arithmetic", 4),
            ("answer", 3),
            ("balance", 3),
            ("limit", 3),
        ):
            index, beat = _beat(lesson, beat_id)
            image = render_beat(beat, lesson, index, len(lesson["beats"]), "zh", theme, stage=stage, second_lang="en")
            self.assertFalse(
                focus_preview.content_below(image, safe),
                f"{beat_id} stage {stage} crosses the caption",
            )

    def test_calculation_result_is_the_strong_row_and_default_steps_are_not(self):
        lesson = load_lesson(MEAN)
        focus = focus_preview.focus_preview_lesson(lesson)
        theme = load_theme(None)
        _index, plain = _beat(lesson, "arithmetic")
        index, strong = _beat(focus, "arithmetic")
        before = render_beat(plain, lesson, _index, len(lesson["beats"]), "en", theme, stage=3)
        after = render_beat(strong, focus, index, len(focus["beats"]), "en", theme, stage=3)
        self.assertNotEqual(list(before.getdata()), list(after.getdata()))
        navy = (11, 31, 58)
        wash = (236, 228, 210)
        self.assertGreater(_count_color(after, navy), 40)
        self.assertGreater(_count_color(after, wash), _count_color(before, wash))
        self.assertFalse(focus_preview.content_below(after, caption_safe_top(H)))

    def test_row_cells_reveal_one_shop_at_a_time(self):
        lesson = load_lesson(MEAN)
        _index, data = _beat(lesson, "data")
        beat = focus_preview.shop_reveal_prototype(data)
        holder = {"id": "EXPERIMENTAL-SHOP-REVEAL", "slide_style": "focus", "title_en": "x", "beats": [beat]}
        theme = load_theme(None)
        first = render_beat(beat, holder, 1, 1, "en", theme, stage=1)
        second = render_beat(beat, holder, 1, 1, "en", theme, stage=2)
        diff = _diff_box(first, second)
        self.assertIsNotNone(diff)
        self.assertGreater(diff[0], first.width // 5)
        self.assertLess(diff[2], first.width * 3 // 4)
        self.assertLess(diff[3], caption_safe_top(H))

    def test_first_row_does_not_change_cells_reveal(self):
        lesson = load_lesson(MEAN)
        _index, data = _beat(lesson, "data")
        self.assertEqual(data["reveal"], "cells")
        self.assertEqual(stage_count(data), 6)
        probe = dict(data)
        probe["reveal"] = "first_row"
        self.assertEqual(stage_count(probe), 3)
        holder = {"id": "EXPERIMENTAL-FIRST-ROW", "slide_style": "focus", "title_en": "t", "beats": [probe]}
        theme = load_theme(None)
        early = render_beat(probe, holder, 1, 1, "en", theme, stage=1)
        late = render_beat(probe, holder, 1, 1, "en", theme, stage=3)
        self.assertIsNotNone(_diff_box(early, late))
        self.assertFalse(focus_preview.content_below(late, caption_safe_top(H)))

    def test_production_tex_card_still_paints_under_both_layouts(self):
        from mathtex import render_math

        formula = focus_preview.tex_probe_lesson()["beats"][0]["formula_tex"]
        math = render_math(formula, color="#F7F4EE", fontsize=64, max_w=1600, max_h=400)
        self.assertIsNotNone(math)
        self.assertGreater(math.getbbox()[2], 40)
        theme = load_theme(None)
        for lesson in (focus_preview.tex_probe_lesson(), focus_preview.tex_probe_lesson("focus")):
            beat = lesson["beats"][0]
            image = render_beat(beat, lesson, 1, 1, "en", theme, stage=2)
            self.assertGreater(_light_pixels(image), 80)
            if lesson.get("slide_style") == "focus":
                self.assertFalse(focus_preview.content_below(image, caption_safe_top(H)))
            else:
                self.assertTrue(focus_preview.content_below(image, caption_safe_top(H)))


def tempfile_dir():
    import tempfile
    return tempfile.TemporaryDirectory()


def _count_color(image, color, slack=18):
    px = image.convert("RGB").load()
    found = 0
    for y in range(0, H, 3):
        for x in range(28, W - 28, 3):
            pixel = px[x, y]
            if all(abs(pixel[i] - color[i]) <= slack for i in range(3)):
                found += 1
    return found


def _light_pixels(image):
    px = image.convert("RGB").load()
    found = 0
    for y in range(200, caption_safe_top(H), 2):
        for x in range(120, W - 120, 2):
            pixel = px[x, y]
            if pixel[0] > 220 and pixel[1] > 220 and pixel[2] > 210:
                found += 1
    return found


def _diff_box(left, right):
    from PIL import ImageChops
    return ImageChops.difference(left.convert("RGB"), right.convert("RGB")).getbbox()


if __name__ == "__main__":
    unittest.main()

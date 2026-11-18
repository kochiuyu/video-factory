from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops

from mux import _caption_card, caption_safe_top, stage_scripts
from slides import H, render_beat, stage_count
from theme import load_theme
from validate import load_lesson

MEAN = Path(__file__).resolve().parents[1] / "lessons" / "STAT" / "STAT-M01-T02-MEAN.yaml"


class FocusSlideTests(unittest.TestCase):
    def test_hook_has_a_spoken_stage_for_each_shop(self):
        lesson = load_lesson(MEAN)
        hook = lesson["beats"][0]
        count = stage_count(hook)
        self.assertEqual(count, 4)
        for language in ("en", "zh_cn", "zh_hk"):
            for chunk, sales in zip(stage_scripts(hook, language, count), (250, 300, 350, 500)):
                self.assertIn(str(sales), chunk)
        theme = load_theme(None)
        a = render_beat(hook, lesson, 1, len(lesson["beats"]), "en", theme, stage=1)
        b = render_beat(hook, lesson, 1, len(lesson["beats"]), "en", theme, stage=2)
        box = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox()
        self.assertIsNotNone(box)
        self.assertGreater(box[0], a.width // 4)
        self.assertLess(box[2], 2 * a.width // 3)
        self.assertLess(box[3], caption_safe_top(H))

    def test_caption_reservation_matches_three_large_lines(self):
        with TemporaryDirectory() as temp, patch.dict(
            "os.environ", {"VF_CAPTION_SIZE": "56", "VF_CAPTION_LINES": "3"}
        ):
            dest = Path(temp) / "caption.png"
            _caption_card("First line\nSecond line\nThird line", dest)
            with Image.open(dest) as image:
                self.assertEqual(image.getchannel("A").getbbox()[1], caption_safe_top(H))

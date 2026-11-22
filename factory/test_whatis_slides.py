"""Opt-in What-is cards. Existing visuals keep their required stems."""

import unittest

from slides import WHATIS_VISUALS, stage_count
from validate import validate


def _lesson(beats):
    return {
        "id": "LAE-W-TEST",
        "title_en": "What is LAE?",
        "title_zh": "什么是低空经济？",
        "title_zh_hk": "咩係低空經濟？",
        "duration_target_s": sum(beat["seconds"] for beat in beats),
        "beats": beats,
    }


class WhatisValidation(unittest.TestCase):
    def test_example_stamp_is_required_and_old_takeaway_still_needs_two_questions(self):
        broken = _lesson([{
            "id": "example",
            "visual": "whatis_example",
            "seconds": 12,
            "body_en": "A medical sample needs to reach a hospital quickly.",
            "en": "An example.",
            "zh": "一个例子。",
            "zh_hk": "一個例子。",
        }])
        errors = validate(broken, glyphs=False)
        self.assertTrue(any("stamp" in err for err in errors), errors)

        old = _lesson([{
            "id": "close",
            "visual": "takeaway",
            "seconds": 12,
            "q1_en": "One question?",
            "en": "Speech.",
            "zh": "旁白。",
            "zh_hk": "旁白。",
        }])
        old_errors = validate(old, glyphs=False)
        self.assertTrue(any("q2" in err for err in old_errors), old_errors)

    def test_whatis_lesson_validates_without_touching_old_visuals(self):
        beats = [
            {
                "id": "hook", "visual": "whatis_title", "seconds": 12,
                "title_en": "What is LAE?", "title_zh": "什么是低空经济？", "title_zh_hk": "咩係低空經濟？",
                "en": "Too narrow.", "zh": "太窄了。", "zh_hk": "太窄。",
            },
            {
                "id": "define", "visual": "whatis_definition", "seconds": 12,
                "sentence_en": "Economic activity in low-altitude airspace.",
                "sentence_zh": "使用低空空域的经济活动。",
                "sentence_zh_hk": "用低空空域嘅經濟活動。",
                "en": "A definition.", "zh": "一个定义。", "zh_hk": "一個定義。",
            },
            {
                "id": "contrast", "visual": "whatis_contrast", "seconds": 12,
                "what_en": "A policy working description.",
                "what_zh": "政策工作描述。",
                "what_zh_hk": "政策工作描述。",
                "not_en": "Not a Cap. 448G flying-height limit.",
                "not_zh": "不是飞行高度限制。",
                "not_zh_hk": "唔係飛行高度限制。",
                "en": "Two rulers.", "zh": "两把尺子。", "zh_hk": "兩把尺。",
            },
            {
                "id": "rule", "visual": "whatis_takeaway", "seconds": 12,
                "rule_en": "LAE is the whole chain.",
                "rule_zh": "低空经济是整条链条。",
                "rule_zh_hk": "低空經濟係成條鏈。",
                "en": "One rule.", "zh": "一条规则。", "zh_hk": "一條規則。",
            },
        ]
        self.assertEqual(validate(_lesson(beats), glyphs=False), [])
        for beat in beats:
            self.assertIn(beat["visual"], WHATIS_VISUALS)
            self.assertEqual(stage_count(beat), 1)
        self.assertEqual(stage_count({"visual": "takeaway"}), 3)
        self.assertEqual(stage_count({"visual": "definition_card"}), 2)
        self.assertEqual(stage_count({"visual": "two_column"}), 3)

    def test_whatis_body_is_cream_and_old_two_column_keeps_emerald(self):
        from theme import load_theme
        from slides import render_beat
        from validate import load_lesson

        theme = load_theme("cuhk-navy")
        lesson = _lesson([{
            "id": "define",
            "visual": "whatis_definition",
            "seconds": 12,
            "sentence_en": "Economic activity that uses low-altitude airspace.",
            "en": "A definition.",
            "zh": "一个定义。",
            "zh_hk": "一個定義。",
        }])
        img = render_beat(lesson["beats"][0], lesson, 1, 1, "en", theme)
        self.assertEqual(img.getpixel((960, 860)), theme["bg"])
        self.assertEqual(img.getpixel((960, 200)), theme["navy"])
        emerald = sum(1 for px in img.get_flattened_data() if px == theme["emerald"])
        self.assertEqual(emerald, 0)

        old = load_lesson("lessons/LAE/LAE-M01-LY.yaml")
        compare = next(beat for beat in old["beats"] if beat.get("visual") == "two_column")
        old_img = render_beat(compare, old, 1, len(old["beats"]), "en", theme)
        old_emerald = sum(1 for px in old_img.get_flattened_data() if px == theme["emerald"])
        self.assertGreater(old_emerald, 1000)

    def test_whatis_nbsp_keeps_a_phrase_and_plain_latin_still_uses_wrap(self):
        from PIL import Image, ImageDraw
        from slides import _whatis_wrap, font_for, wrap

        image = Image.new("RGB", (400, 80), "white")
        draw = ImageDraw.Draw(image)
        plain = "An unmanned aircraft not more than 150 kg, under Cap. 448G."
        self.assertEqual(
            _whatis_wrap(draw, plain, 72, 1728, True),
            wrap(draw, plain, font_for(plain, 72, True), 1728, True),
        )
        glued = "An unmanned aircraft not more than 150\u00a0kg, under Cap. 448G."
        lines = _whatis_wrap(draw, glued, 72, 1728, True)
        self.assertEqual(lines[-1], "150 kg, under Cap. 448G.")
        self.assertTrue(all("\u00a0" not in line for line in lines))
        phrase = "Start with the craft’s weight and what\u00a0it\u00a0is\u00a0doing, then check which legal\u00a0category it falls into."
        kept = _whatis_wrap(draw, phrase, 72, 1728, True)
        self.assertTrue(any("what it is doing" in line for line in kept))
        self.assertFalse(any(line.endswith("what it") for line in kept))

    def test_whatis_fullwidth_punctuation_does_not_keep_a_whole_em(self):
        from PIL import Image, ImageDraw
        from slides import _whatis_length, mixed_length

        image = Image.new("RGB", (400, 80), "white")
        draw = ImageDraw.Draw(image)
        tight = _whatis_length(draw, "动，连", 72, True)
        full = mixed_length(draw, "动，连", 72, True)
        self.assertLess(tight, full * 0.85)


class WhatisContrastStages(unittest.TestCase):
    def test_unstaged_contrast_stays_one_card_and_staged_speech_rejoins(self):
        from langs import beat_text
        from slides import _whatis_contrast_visible, stage_count

        plain = {
            "id": "contrast", "visual": "whatis_contrast",
            "what_en": "An everyday name.", "not_en": "The legal name.",
            "en": "One line.", "zh": "一句。", "zh_hk": "一句。",
        }
        self.assertEqual(stage_count(plain), 1)
        self.assertEqual(_whatis_contrast_visible(plain, None), (True, True))

        two = {
            "id": "contrast", "visual": "whatis_contrast",
            "s1_en": "SUA is a legal category with a weight limit.",
            "s2_en": "It is not just another word.",
            "s1_zh": "SUA 是一个有重量限制的法律类别。",
            "s2_zh": "它不是所有「drone」的另一个叫法。",
        }
        self.assertEqual(stage_count(two), 2)
        self.assertEqual(_whatis_contrast_visible(two, 1), (True, False))
        self.assertEqual(_whatis_contrast_visible(two, 2), (True, True))
        self.assertEqual(
            beat_text(two, "en"),
            "SUA is a legal category with a weight limit. It is not just another word.",
        )
        self.assertEqual(
            beat_text(two, "zh"),
            "SUA 是一个有重量限制的法律类别。它不是所有「drone」的另一个叫法。",
        )
        stat = {"id": "open", "visual": "title_card", "s1_zh": "甲。", "s2_zh": "乙。"}
        self.assertEqual(beat_text(stat, "zh"), "甲。 乙。")

    def test_three_contrast_stages_focus_the_not_line_last(self):
        from slides import _whatis_contrast_visible, stage_count

        beat = {
            "visual": "whatis_contrast",
            "s1_en": "A.", "s2_en": "B.", "s3_en": "C.",
        }
        self.assertEqual(stage_count(beat), 3)
        self.assertEqual(_whatis_contrast_visible(beat, 1), (True, False))
        self.assertEqual(_whatis_contrast_visible(beat, 2), (True, True))
        self.assertEqual(_whatis_contrast_visible(beat, 3), (False, True))


class WhatisClock(unittest.TestCase):
    def test_default_clock_is_per_language_and_shared_is_opt_in(self):
        from build import capped_durations, owns_speech_clock, speech_breath_durations

        whatis = _lesson([{
            "id": "hook", "visual": "whatis_title", "seconds": 12,
            "title_en": "What is LAE?", "en": "Narrow.", "zh": "窄。", "zh_hk": "窄。",
        }])
        stat = _lesson([{
            "id": "open", "visual": "title_card", "seconds": 12,
            "title_en": "Intro", "en": "Hello.", "zh": "你好。", "zh_hk": "你好。",
        }])
        mixed = _lesson([
            stat["beats"][0],
            whatis["beats"][0],
        ])
        self.assertTrue(owns_speech_clock(stat))
        self.assertTrue(owns_speech_clock(whatis))
        self.assertTrue(owns_speech_clock(mixed))
        self.assertFalse(owns_speech_clock({**stat, "clock": "shared"}))
        self.assertTrue(owns_speech_clock({**stat, "clock": "own"}))
        self.assertFalse(owns_speech_clock({**whatis, "clock": "shared"}))
        self.assertTrue(owns_speech_clock({**whatis, "clock": "own"}))

        raw = {"en": [6.6, 29.9], "zh_hk": [7.1, 32.9]}
        own = speech_breath_durations(raw, 0.4)
        self.assertAlmostEqual(own["en"][0], 7.0)
        self.assertAlmostEqual(own["en"][1], 30.3)
        self.assertAlmostEqual(own["zh_hk"][1], 33.3)
        self.assertLess(own["en"][1], own["zh_hk"][1])
        shared = capped_durations(raw, [7.1, 32.9], None)
        self.assertEqual(shared["en"], [7.1, 32.9])
        self.assertEqual(shared["zh_hk"], [7.1, 32.9])

    def test_clock_field_accepts_only_own_or_shared(self):
        lesson = _lesson([{
            "id": "hook", "visual": "whatis_title", "seconds": 12,
            "title_en": "What is LAE?", "en": "Narrow.", "zh": "窄。", "zh_hk": "窄。",
        }])
        self.assertEqual(validate(lesson, glyphs=False), [])
        self.assertEqual(validate({**lesson, "clock": "own"}, glyphs=False), [])
        self.assertEqual(validate({**lesson, "clock": "shared"}, glyphs=False), [])
        self.assertEqual(validate({**lesson, "clock": "OWN"}, glyphs=False), [])
        errors = validate({**lesson, "clock": "together"}, glyphs=False)
        self.assertEqual(errors, ["clock must be own or shared, not 'together'."])


if __name__ == "__main__":
    unittest.main()

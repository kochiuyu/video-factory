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


if __name__ == "__main__":
    unittest.main()

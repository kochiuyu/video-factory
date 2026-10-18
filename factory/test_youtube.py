#!/usr/bin/env python3
"""Title tags, description inheritance, and YouTube length checks."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from validate import load_lesson, validate
from youtube import (
    DESCRIPTION_MAX,
    TITLE_GUIDE,
    description_for_cell,
    sidecar_text,
    write_youtube_sidecars,
    youtube_errors,
    youtube_title,
    youtube_warnings,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "youtube_titles.yaml"
ROOT = Path(__file__).resolve().parents[1]


class YoutubeTitles(unittest.TestCase):
    def setUp(self) -> None:
        self.lesson = load_lesson(FIXTURE)

    def test_mono_and_bilingual_tags(self) -> None:
        self.assertEqual(youtube_title(self.lesson, "en"), "What is the mean? (English)")
        self.assertEqual(youtube_title(self.lesson, "zh"), "什么是平均数？ (普通话)")
        self.assertEqual(youtube_title(self.lesson, "hk"), "咩係平均數？ (粵語)")
        self.assertEqual(
            youtube_title(self.lesson, "en+zh"),
            "What is the mean? (Speech: English · Slides: 简体)",
        )
        self.assertEqual(
            youtube_title(self.lesson, "zh+en"),
            "什么是平均数？（旁白：普通话 · 画面：English）",
        )
        self.assertEqual(
            youtube_title(self.lesson, "en+hk"),
            "What is the mean? (Speech: English · Slides: 繁體)",
        )
        self.assertEqual(
            youtube_title(self.lesson, "hk+en"),
            "咩係平均數？（旁白：粵語 · 畫面：English）",
        )
        self.assertEqual(
            youtube_title(self.lesson, "zh+hk"),
            "什么是平均数？（旁白：普通话 · 画面：繁體）",
        )
        self.assertEqual(
            youtube_title(self.lesson, "hk+zh"),
            "咩係平均數？（旁白：粵語 · 畫面：简体）",
        )

    def test_bilingual_description_follows_speech(self) -> None:
        self.assertEqual(
            description_for_cell(self.lesson, "en+zh"),
            "The mean is the total divided by the number of days.",
        )
        self.assertEqual(
            description_for_cell(self.lesson, "zh+en"),
            "平均数就是把总数除以天数。",
        )
        self.assertEqual(
            description_for_cell(self.lesson, "hk"),
            "平均數就係將總數除以日數。",
        )
        self.assertEqual(description_for_cell(self.lesson, "zh+hk"), description_for_cell(self.lesson, "zh"))

    def test_missing_description_still_writes_title(self) -> None:
        lesson = {
            "id": "YT-BARE",
            "title_en": "What is the mean?",
            "title_zh": "什么是平均数？",
            "title_zh_hk": "咩係平均數？",
        }
        text = sidecar_text(youtube_title(lesson, "en"), description_for_cell(lesson, "en"))
        self.assertEqual(text, "What is the mean? (English)\n\n")
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_youtube_sidecars(lesson, {"en": ("en", "en", "en"), "en+zh": ("en", "en", "zh")}, Path(tmp))
            names = sorted(p.name for p in paths)
            self.assertEqual(names, ["YT-BARE_en+zh.youtube.txt", "YT-BARE_en.youtube.txt"])
            en_zh = (Path(tmp) / "cells" / "YT-BARE_en+zh.youtube.txt").read_text(encoding="utf-8")
            self.assertEqual(en_zh, "What is the mean? (Speech: English · Slides: 简体)\n\n")
            self.assertFalse((Path(tmp) / "cells" / "YT-BARE_zh.youtube.txt").exists())

    def test_fixture_sidecar_uses_speech_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_youtube_sidecars(self.lesson, {"zh+en": ("zh_cn", "zh_cn", "en")}, Path(tmp))
            text = (Path(tmp) / "cells" / "YT-TITLE-FIXTURE_zh+en.youtube.txt").read_text(encoding="utf-8")
        self.assertEqual(
            text,
            "什么是平均数？（旁白：普通话 · 画面：English）\n\n平均数就是把总数除以天数。\n",
        )

    def test_description_length(self) -> None:
        ok = {"id": "YT", "title_en": "Mean", "title_zh": "平均数", "youtube": {"description_en": "a" * DESCRIPTION_MAX}}
        self.assertEqual(youtube_errors(ok), [])
        over = {
            "id": "YT",
            "title_en": "Mean",
            "title_zh": "平均数",
            "youtube": {"description_zh": "字" * (DESCRIPTION_MAX + 1)},
        }
        errors = youtube_errors(over)
        self.assertTrue(any("description_zh" in e and str(DESCRIPTION_MAX) in e for e in errors))
        self.assertTrue(any("youtube.description_zh" in e for e in validate(over, glyphs=False)))

    def test_mono_title_over_guide_is_an_error(self) -> None:
        room = TITLE_GUIDE - len(" (English)")
        fits = {"id": "YT", "title_en": "M" * room, "title_zh": "短"}
        self.assertEqual([e for e in youtube_errors(fits) if e.startswith("YouTube title")], [])
        self.assertEqual(len(youtube_title(fits, "en")), TITLE_GUIDE)
        over = {"id": "YT", "title_en": "M" * (room + 1), "title_zh": "短"}
        errors = youtube_errors(over)
        self.assertTrue(any(e.startswith("YouTube title for en ") for e in errors))
        self.assertFalse(any(e.startswith("YouTube title for zh ") for e in errors))

    def test_base_title_already_over_guide_warns(self) -> None:
        lesson = {"id": "YT", "title_en": "E" * (TITLE_GUIDE + 1), "title_zh": "短"}
        self.assertFalse(any(e.startswith("YouTube title for en ") for e in youtube_errors(lesson)))
        warnings = youtube_warnings(lesson, ["en"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("guidance 100", warnings[0])

    def test_existing_long_bilingual_title_warns(self) -> None:
        path = ROOT / "lessons" / "STAT" / "STAT-M06-T04-OLSCR.yaml"
        lesson = yaml.safe_load(path.read_text(encoding="utf-8"))
        errors = [e for e in youtube_errors(lesson) if e.startswith("YouTube title")]
        self.assertEqual(errors, [])
        self.assertLessEqual(len(youtube_title(lesson, "en")), TITLE_GUIDE)
        self.assertGreater(len(youtube_title(lesson, "en+zh")), TITLE_GUIDE)
        warnings = youtube_warnings(lesson, ["en", "en+zh"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("en+zh", warnings[0])
        self.assertEqual(youtube_warnings(lesson, ["en"]), [])

    def test_unknown_youtube_field(self) -> None:
        lesson = {"id": "YT", "title_en": "Mean", "title_zh": "平均数", "youtube": {"description_cn": "nope", "tags": ["a"]}}
        errors = youtube_errors(lesson)
        self.assertTrue(any("description_cn" in e for e in errors))
        self.assertTrue(any("tags" in e for e in errors))


if __name__ == "__main__":
    unittest.main()

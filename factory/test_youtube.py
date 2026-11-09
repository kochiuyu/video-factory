#!/usr/bin/env python3
"""Title tags, description inheritance, and YouTube length checks."""

from __future__ import annotations

import json
import os
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
    load_series_links,
    normalize_description,
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
            "What is the mean? (English narration · bilingual slides 中英)",
        )
        self.assertEqual(
            youtube_title(self.lesson, "zh+en"),
            "什么是平均数？（普通话讲解 · 中英双语画面）",
        )
        self.assertEqual(
            youtube_title(self.lesson, "en+hk"),
            "What is the mean? (English narration · bilingual slides 中英)",
        )
        self.assertEqual(
            youtube_title(self.lesson, "hk+en"),
            "咩係平均數？（粵語講解 · 中英雙語畫面）",
        )
        self.assertEqual(
            youtube_title(self.lesson, "zh+hk"),
            "什么是平均数？（旁白：普通话 · 画面：繁體）",
        )
        self.assertEqual(
            youtube_title(self.lesson, "hk+zh"),
            "咩係平均數？（旁白：粵語 · 畫面：简体）",
        )

    def test_legacy_lang_tag_env(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"VF_LEGACY_LANG_TAG": "1"}):
            self.assertEqual(youtube_title(self.lesson, "en+zh"), "What is the mean? (Speech: English · Slides: 简体)")
            self.assertEqual(youtube_title(self.lesson, "zh+en"), "什么是平均数？（旁白：普通话 · 画面：English）")
            self.assertEqual(youtube_title(self.lesson, "hk+en"), "咩係平均數？（旁白：粵語 · 畫面：English）")
            self.assertEqual(youtube_title(self.lesson, "zh"), "什么是平均数？ (普通话)")

    def test_one_label_for_title_chip_playlist(self) -> None:
        from langs import language_label, playlist_name

        self.assertEqual(language_label("zh", "en", "chip"), "普通话讲解 · 中英双语画面")
        self.assertEqual(language_label("hk", "en", "chip"), "粵語講解 · 中英雙語畫面")
        self.assertEqual(language_label("en", "zh", "chip"), "English narration · bilingual slides 中英")
        self.assertEqual(language_label("en", None, "title"), " (English)")
        self.assertEqual(playlist_name("STAT M01", "zh", "en"), "STAT M01 · 普通话讲解 · 中英双语画面")
        self.assertEqual(playlist_name("STAT M01", "hk"), "STAT M01 · 粵語")

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
            self.assertEqual(en_zh, "What is the mean? (English narration · bilingual slides 中英)\n\n")
            self.assertFalse((Path(tmp) / "cells" / "YT-BARE_zh.youtube.txt").exists())

    def test_fixture_sidecar_uses_speech_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_youtube_sidecars(self.lesson, {"zh+en": ("zh_cn", "zh_cn", "en")}, Path(tmp))
            text = (Path(tmp) / "cells" / "YT-TITLE-FIXTURE_zh+en.youtube.txt").read_text(encoding="utf-8")
        self.assertEqual(
            text,
            "什么是平均数？（普通话讲解 · 中英双语画面）\n\n平均数就是把总数除以天数。\n",
        )

    def test_description_length(self) -> None:
        # Strictly less than 2500: 2499 is valid, 2500 is an error.
        self.assertEqual(DESCRIPTION_MAX, 2500)
        ok = {
            "id": "YT",
            "title_en": "Mean",
            "title_zh": "平均数",
            "youtube": {"description_en": "a" * (DESCRIPTION_MAX - 1)},
        }
        self.assertEqual(len(ok["youtube"]["description_en"]), 2499)
        self.assertEqual(youtube_errors(ok), [])
        over = {
            "id": "YT",
            "title_en": "Mean",
            "title_zh": "平均数",
            "youtube": {"description_zh": "字" * DESCRIPTION_MAX},
        }
        self.assertEqual(len(over["youtube"]["description_zh"]), 2500)
        errors = youtube_errors(over)
        self.assertTrue(any("description_zh" in e and str(DESCRIPTION_MAX) in e for e in errors))
        self.assertTrue(any("strictly less than 2500" in e for e in errors))
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
        os.environ["VF_LEGACY_YT_SERIES"] = "1"
        self.addCleanup(os.environ.pop, "VF_LEGACY_YT_SERIES", None)
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

    def test_ascii_angle_brackets_become_fullwidth(self) -> None:
        # Studio rejects ASCII < and >. Arrows stay readable; length is unchanged.
        raw = "Nearest rank: 1.25 -> 2 and 3.75 -> 4. Also a < b, a > b, a <= b, a >= b."
        normalized = normalize_description(" \r\n" + raw + "\r\n ")
        self.assertNotIn("<", normalized)
        self.assertNotIn(">", normalized)
        self.assertEqual(
            normalized,
            "Nearest rank: 1.25 -＞ 2 and 3.75 -＞ 4. Also a ＜ b, a ＞ b, a ＜= b, a ＞= b.",
        )
        self.assertEqual(len(normalized), len(raw))
        self.assertEqual(normalize_description(normalized), normalized)
        self.assertEqual(normalize_description("1.25 → 2 and ＜already＞"), "1.25 → 2 and ＜already＞")

        lesson = {
            "id": "YT-BRACKETS",
            "title_en": "When x < y",
            "title_zh": "当 x > y",
            "title_zh_hk": "當 x < y",
            "youtube": {
                "description_en": "Place 1.25 -> 2.\n",
                "description_zh": "位置 3.75 -> 4。\n",
                "description_zh_hk": "位置 1.25 -> 2。\n",
            },
        }
        self.assertEqual(youtube_title(lesson, "en"), "When x ＜ y (English)")
        self.assertEqual(youtube_title(lesson, "zh"), "当 x ＞ y (普通话)")
        self.assertEqual(
            youtube_title(lesson, "en+zh"),
            "When x ＜ y (English narration · bilingual slides 中英)",
        )
        self.assertEqual(description_for_cell(lesson, "en+zh"), "Place 1.25 -＞ 2.")
        self.assertEqual(description_for_cell(lesson, "zh"), "位置 3.75 -＞ 4。")
        self.assertEqual(youtube_errors(lesson), [])

        direct = sidecar_text("Raw <title>", "body a -> b")
        self.assertNotRegex(direct, r"[<>]")
        self.assertEqual(direct, "Raw ＜title＞\n\nbody a -＞ b\n")
        self.assertEqual(sidecar_text("Plain title", ""), "Plain title\n\n")

        capped = ">" * (DESCRIPTION_MAX - 1)
        at_limit = {
            "id": "YT",
            "title_en": "Mean",
            "title_zh": "平均数",
            "youtube": {"description_en": capped},
        }
        self.assertEqual(youtube_errors(at_limit), [])
        self.assertEqual(description_for_cell(at_limit, "en"), "＞" * (DESCRIPTION_MAX - 1))

        with tempfile.TemporaryDirectory() as tmp:
            write_youtube_sidecars(
                lesson,
                {"en": ("en", "en", "en"), "zh": ("zh_cn", "zh_cn", "zh_cn"), "hk": ("zh_hk", "zh_hk", "zh_hk")},
                Path(tmp),
            )
            cells = Path(tmp) / "cells"
            for name in ("en", "zh", "hk"):
                text = (cells / f"YT-BRACKETS_{name}.youtube.txt").read_text(encoding="utf-8")
                self.assertNotRegex(text, r"[<>]")
            en = (cells / "YT-BRACKETS_en.youtube.txt").read_text(encoding="utf-8")
            zh = (cells / "YT-BRACKETS_zh.youtube.txt").read_text(encoding="utf-8")
        self.assertEqual(en, "When x ＜ y (English)\n\nPlace 1.25 -＞ 2.\n")
        self.assertEqual(zh, "当 x ＞ y (普通话)\n\n位置 3.75 -＞ 4。\n")

    def test_unknown_youtube_field(self) -> None:
        lesson = {"id": "YT", "title_en": "Mean", "title_zh": "平均数", "youtube": {"description_cn": "nope", "tags": ["a"]}}
        errors = youtube_errors(lesson)
        self.assertTrue(any("description_cn" in e for e in errors))
        self.assertTrue(any("tags" in e for e in errors))


class YoutubeSeries(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("VF_LEGACY_YT_SERIES", None)
        os.environ.pop("VF_SERIES_LINKS", None)
        self.lesson = {
            "id": "STAT-M01-T09-CV",
            "title_en": "Which is more spread out?",
            "title_zh": "哪个更分散？",
            "title_zh_hk": "邊個更分散？",
            "youtube": {"description_en": "Body EN.", "description_zh": "正文。"},
        }

    def tearDown(self) -> None:
        os.environ.pop("VF_LEGACY_YT_SERIES", None)

    def test_prefix_parse(self) -> None:
        from youtube import series_number, series_parts, series_prefix

        self.assertEqual(series_parts("STAT-M01-T09-CV"), ("STAT", 1, 9))
        self.assertEqual(series_number("STAT-M12-T15-RECAP"), "12.15")
        self.assertEqual(series_prefix("STAT-M01-T09-CV"), "STAT 1.09 · ")
        self.assertTrue(youtube_title(self.lesson, "en").startswith("STAT 1.09 · Which"))
        self.assertTrue(youtube_title(self.lesson, "zh+en").startswith("统计 1.09 · 哪个"))
        self.assertTrue(youtube_title(self.lesson, "zh").startswith("统计 1.09 · 哪个"))
        self.assertTrue(youtube_title(self.lesson, "hk+en").startswith("統計 1.09 · 邊個"))
        self.assertTrue(youtube_title(self.lesson, "en+zh").startswith("STAT 1.09 · Which"))
        self.assertEqual(series_prefix("STAT-M01-T09-CV", "zh_hk"), "統計 1.09 · ")
        self.assertEqual(series_prefix("ECON-M02-T03-X", "zh"), "ECON 2.03 · ")  # unknown course -> code

    def test_module_title_in_header(self) -> None:
        from youtube import module_titles, series_header

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "minicourses").mkdir()
            (root / "lessons" / "STAT").mkdir(parents=True)
            (root / "minicourses" / "STAT-M07.yaml").write_text(
                "id: STAT-M07\ntitle_en: Shop <tests>\ntitle_zh: 门店实验\n", encoding="utf-8")
            lp = root / "lessons" / "STAT" / "STAT-M07-T05-X.yaml"
            lp.write_text("id: STAT-M07-T05-X\n", encoding="utf-8")
            links = load_series_links(lp, "STAT-M07-T05-X")
            lesson = dict(self.lesson, id="STAT-M07-T05-X")
            head = description_for_cell(lesson, "en", links).split("\n")[0]
            self.assertEqual(head, "Series: STAT M07 · Shop ＜tests＞ · English · Lesson 05/01")
            # zh_hk falls back to title_zh
            self.assertIn("· 门店实验 ·", description_for_cell(lesson, "hk", links).split("\n")[0])
            # missing minicourse file / no title -> omitted gracefully
            self.assertEqual(module_titles("STAT-M99-T01-X", lp), {})
            (root / "minicourses" / "STAT-M98.yaml").write_text("id: STAT-M98\n", encoding="utf-8")
            self.assertEqual(series_header(dict(lesson, id="STAT-M98-T01-X"), "en", 15, module_titles("STAT-M98-T01-X", lp)),
                             "Series: STAT M98 · English · Lesson 01/15")
            self.assertEqual(series_header(dict(lesson, id="STAT-M99-T01-X"), "en", 15, {}),
                             "Series: STAT M99 · English · Lesson 01/15")

    def test_no_prefix_for_odd_ids(self) -> None:
        from youtube import series_prefix, series_header

        for odd in ("YT", "STAT-01-09", "LAE-T03-X", "", "STAT-M1"):
            self.assertEqual(series_prefix(odd), "")
        lesson = dict(self.lesson, id="LESSON-X")
        self.assertEqual(youtube_title(lesson, "en"), "Which is more spread out? (English)")
        self.assertEqual(series_header(lesson, "en"), "")
        self.assertEqual(description_for_cell(lesson, "en"), "Body EN.")

    def test_legacy_switch(self) -> None:
        os.environ["VF_LEGACY_YT_SERIES"] = "1"
        self.assertEqual(youtube_title(self.lesson, "en"), "Which is more spread out? (English)")
        self.assertEqual(description_for_cell(self.lesson, "en"), "Body EN.")

    def test_header_languages_and_unknown_links_omitted(self) -> None:
        en = description_for_cell(self.lesson, "en")
        self.assertEqual(en, "Series: STAT M01 · Descriptive measures for a coffee chain · English · Lesson 09\n\nBody EN.")
        zh = description_for_cell(self.lesson, "zh")
        self.assertTrue(zh.startswith("系列：STAT M01 · 咖啡连锁的描述性指标 · 普通话 · 第 09 课\n\n"))
        for cell in ("en", "zh", "hk+en", "en+zh"):
            text = description_for_cell(self.lesson, cell)
            for word in ("Previous", "Next", "Playlist", "上一", "下一", "播放"):
                self.assertNotIn(word, text)

    def test_links_from_yaml_and_file(self) -> None:
        lesson = dict(self.lesson)
        lesson["youtube"] = dict(self.lesson["youtube"], series={"total": 15, "next_url_en+zh": "https://youtu.be/N"})
        text = description_for_cell(lesson, "en+zh")
        self.assertIn("Lesson 09/15", text)
        self.assertIn("Next: https://youtu.be/N", text)
        self.assertNotIn("Previous", text)
        self.assertNotIn("youtu.be/N", description_for_cell(lesson, "en"))  # same mix only
        self.assertEqual(youtube_errors(lesson), [])
        links = {"STAT-M01": {"total": 15, "order": ["STAT-M01-T08-VARSTD", "STAT-M01-T09-CV", "STAT-M01-T10-OUTLIER"],
                 "zh": {"playlist_url": "https://www.youtube.com/playlist?list=PLx",
                        "urls": {"STAT-M01-T08-VARSTD": "https://youtu.be/P"}}}}
        zh = description_for_cell(self.lesson, "zh", links)
        self.assertEqual(zh.split("\n")[:3], ["系列：STAT M01 · 咖啡连锁的描述性指标 · 普通话 · 第 09/15 课", "上一课：https://youtu.be/P",
                                             "播放列表：https://www.youtube.com/playlist?list=PLx"])
        self.assertNotIn("下一课", zh)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "series_links.json").write_text(json.dumps(links), encoding="utf-8")
            from youtube import load_series_links

            self.assertEqual(load_series_links(Path(tmp) / "x.yaml"), links)

    def test_bad_series_field_errors(self) -> None:
        lesson = dict(self.lesson)
        lesson["youtube"] = {"series": {"foo": "x", "total": "15"}}
        errors = youtube_errors(lesson)
        self.assertTrue(any("unknown field foo" in e for e in errors))
        self.assertTrue(any("total must be an integer" in e for e in errors))

    def test_sanitized(self) -> None:
        lesson = dict(self.lesson, title_en="a <b> c")
        lesson["youtube"] = {"description_en": "x -> y", "series": {"prev_url_en": "https://e/?a<b"}}
        text = sidecar_text(youtube_title(lesson, "en"), description_for_cell(lesson, "en"))
        self.assertNotIn("<", text)
        self.assertNotIn(">", text)

    def test_prefix_over_guide_warns_not_errors(self) -> None:
        lesson = dict(self.lesson, title_en="E" * 85)  # 85 + " (English)" = 95; +12 prefix = 107
        self.assertFalse(any(e.startswith("YouTube title for en ") for e in youtube_errors(lesson)))
        self.assertTrue(any("guidance 100" in w for w in youtube_warnings(lesson, ["en"])))

    def test_description_length_warning(self) -> None:
        lesson = dict(self.lesson)
        lesson["youtube"] = {"description_en": "x" * 2290}
        self.assertEqual(youtube_errors(lesson), [])
        warnings = youtube_warnings(lesson, ["en"])
        self.assertTrue(any("warning above 2300" in w for w in warnings))
        self.assertLess(len(description_for_cell(lesson, "en")), DESCRIPTION_MAX)

    def test_series_links_script(self) -> None:
        import series_links

        with tempfile.TemporaryDirectory() as tmp:
            tsv = Path(tmp) / "r.tsv"
            tsv.write_text("topic\tzh\ten+zh\nT01\taaa\tbbb\nT02\tccc\t\n", encoding="utf-8")
            data = series_links.build_links(tsv, "STAT-M01", ["STAT-M01-T01-INTRO", "STAT-M01-T02-MEAN"],
                                            {"zh": "PLz"})
            m = data["STAT-M01"]
            self.assertEqual(m["total"], 2)
            self.assertEqual(m["zh"]["urls"]["STAT-M01-T02-MEAN"], "https://youtu.be/ccc")
            self.assertEqual(m["zh"]["playlist_url"], "https://www.youtube.com/playlist?list=PLz")
            self.assertNotIn("STAT-M01-T02-MEAN", m["en+zh"]["urls"])
            self.assertNotIn("playlist_url", m["en+zh"])


if __name__ == "__main__":
    unittest.main()
